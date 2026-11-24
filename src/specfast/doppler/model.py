"""The forward model of one fit block (one exposure, channel and order).

    F(x) = R(x) * C(x) * Pixel[ LSF (x) ( prod_i factor_i(ln lambda) ) ](x)

(DESIGN.md, "The forward model"): the spectral factors (star, gas cell,
tellurics) are multiplied on the fine ln(lambda) grid, convolved once
with the LSF, averaged over each pixel between the edges given by the
wavelength solution, and multiplied by the continuum.

The optional detector map (:class:`~specfast.doppler.library.DetectorMap`)
is the detector frame, kept apart from the optics: it moves the pixel edges
before the wavelength solution maps them (``lambda(x_edge + dx)``) and
multiplies by a per-pixel response ``R``.

Parameters are passed as ``{component_name: {param_name: array}}``.
:class:`ParameterLayout` maps the free ones to and from a flat vector for an
external solver. Assembling many blocks with shared parameters (scopes) is
the fitting engine's job and is not here yet.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np

from specfast.doppler.components import Component, ExposureContext, ParameterSpec
from specfast.doppler.grid import LnGrid, convolve, pixel_integrate

ModelParams = Mapping[str, Mapping[str, np.ndarray]]


@dataclass(frozen=True, eq=False)
class ForwardModel:
    """One block's model: components plus the static grid and pixels."""

    wavelength: Component
    continuum: Component
    lsf: Component
    #: Multiplicative factors on the fine grid (star, gas cell, ...).
    factors: tuple[Component, ...]
    grid: LnGrid
    #: Pixel centres [px] of the block (consecutive pixels).
    pixels: np.ndarray
    #: Detector-frame map (pixel-edge offsets, response); None = perfect.
    detector: Component | None = None
    #: Serial charge-transfer inefficiency (detector frame), applied to the
    #: model flux after the continuum; None = none.
    cti: Component | None = None

    def __post_init__(self) -> None:
        names = [c.name for c in self.components]
        if len(set(names)) != len(names):
            raise ValueError(f"component names must be unique: {names}")
        px = np.asarray(self.pixels, dtype=np.float64)
        if px.ndim != 1 or px.size < 2 or np.any(np.diff(px) != 1.0):
            raise ValueError("pixels must be consecutive pixel centres")
        object.__setattr__(self, "pixels", px)

    @property
    def components(self) -> tuple[Component, ...]:
        det = () if self.detector is None else (self.detector,)
        cti = () if self.cti is None else (self.cti,)
        return (self.wavelength, self.continuum, self.lsf, *self.factors, *det, *cti)

    def factor(self, name: str) -> Component:
        """The spectral factor called ``name``."""
        for f in self.factors:
            if f.name == name:
                return f
        raise KeyError(f"no spectral factor {name!r}")

    @property
    def pixel_edges(self) -> np.ndarray:
        return np.concatenate([self.pixels - 0.5, self.pixels[-1:] + 0.5])

    def parameter_specs(self) -> list[tuple[str, ParameterSpec]]:
        """Every declared parameter as (component name, spec)."""
        return [(c.name, s) for c in self.components for s in c.parameters()]

    # ------------------------------------------------------------- evaluation
    def fine_spectrum(
        self, params: ModelParams, ctx: ExposureContext, skip: Iterable[str] = ()
    ) -> np.ndarray:
        """Product of the spectral factors on the fine grid (before the LSF),
        leaving out the factors named in ``skip``."""
        ln = self.grid.lnlam
        skip = set(skip)
        out = np.ones_like(ln)
        for f in self.factors:
            if f.name not in skip:
                out = out * f.evaluate(params.get(f.name, {}), ln, ctx)
        return out

    def kernel(self, params: ModelParams, ctx: ExposureContext) -> np.ndarray:
        """The LSF kernel on the fine grid (for an LSF varying along the
        order, its representative kernel; see :meth:`node_kernels`)."""
        return self.lsf.evaluate(params[self.lsf.name], self.grid, ctx)

    def node_kernels(
        self, params: ModelParams, ctx: ExposureContext
    ) -> tuple[list[np.ndarray], np.ndarray | None]:
        """The LSF kernels and their per-pixel blending weights.

        An LSF that varies along the order (one exposing ``kernels`` and
        ``node_weights``, e.g. :class:`~specfast.doppler.library.
        GaussHermiteLSF`) is evaluated exactly at a few nodes; the model is
        convolved once per node and blended per pixel. Returns (kernels,
        weights (nnode, npix)), or ([kernel], None) for a single kernel.
        """
        if hasattr(self.lsf, "kernels"):
            ks = self.lsf.kernels(params[self.lsf.name], self.grid)
            if len(ks) > 1:
                return ks, self.lsf.node_weights(self.pixels)
            return ks, None
        return [self.kernel(params, ctx)], None

    def broaden_and_bin(
        self,
        fine: np.ndarray,
        kernels: list[np.ndarray],
        weights: np.ndarray | None,
        ln_edges: np.ndarray,
    ) -> np.ndarray:
        """Convolve a fine-grid spectrum with the node kernels, average over
        the pixels and blend: the LSF and pixel part of the model."""
        if weights is None:
            return pixel_integrate(convolve(fine, kernels[0]), self.grid, ln_edges)
        out = np.zeros(ln_edges.size - 1)
        for k, ker in enumerate(kernels):
            out += weights[k] * pixel_integrate(convolve(fine, ker), self.grid, ln_edges)
        return out

    def ln_edges(self, params: ModelParams, ctx: ExposureContext) -> np.ndarray:
        """ln(lambda) at the (detector-corrected) pixel edges."""
        edges = self.pixel_edges
        if self.detector is not None:
            edges = self.detector.edges(params[self.detector.name], edges)
        return np.log(self.wavelength.evaluate(params[self.wavelength.name], edges, ctx))

    def pixel_factor(self, params: ModelParams, ctx: ExposureContext) -> np.ndarray:
        """Continuum times detector response, per pixel."""
        out = self.continuum.evaluate(params[self.continuum.name], self.pixels, ctx)
        if self.detector is not None:
            out = out * self.detector.evaluate(params[self.detector.name], self.pixels, ctx)
        return out

    def evaluate(self, params: ModelParams, ctx: ExposureContext) -> np.ndarray:
        """Model flux per pixel."""
        ks, w = self.node_kernels(params, ctx)
        binned = self.broaden_and_bin(
            self.fine_spectrum(params, ctx), ks, w, self.ln_edges(params, ctx)
        )
        out = self.pixel_factor(params, ctx) * binned
        if self.cti is not None:
            out = self.cti.evaluate(params[self.cti.name], self.pixels, ctx, flux=out)
        return out

    def cti_loss(self, params: ModelParams, ctx: ExposureContext) -> np.ndarray | None:
        """Per-pixel CTI loss fraction at the current model (None without CTI)."""
        if self.cti is None:
            return None
        flux = self.pixel_factor(params, ctx) * self.broaden_and_bin(
            self.fine_spectrum(params, ctx),
            *self.node_kernels(params, ctx),
            self.ln_edges(params, ctx),
        )
        return self.cti.loss(params[self.cti.name], flux, self.pixels)


@dataclass(frozen=True)
class ParameterLayout:
    """Flat-vector view of a chosen set of free parameters.

    ``entries`` lists (component, parameter, size) in vector order.
    """

    entries: tuple[tuple[str, str, int], ...]

    @classmethod
    def free(cls, model: ForwardModel, exclude: Iterable[tuple[str, str]] = ()) -> ParameterLayout:
        """All parameters not declared ``fixed`` and not in ``exclude``."""
        skip = set(exclude)
        return cls(
            tuple(
                (comp, s.name, s.size)
                for comp, s in model.parameter_specs()
                if not s.fixed and (comp, s.name) not in skip
            )
        )

    @property
    def size(self) -> int:
        return sum(n for _, _, n in self.entries)

    def pack(self, params: ModelParams) -> np.ndarray:
        if not self.entries:
            return np.zeros(0)
        return np.concatenate(
            [np.asarray(params[c][p], dtype=np.float64).reshape(n) for c, p, n in self.entries]
        )

    def unpack(self, theta: np.ndarray, base: ModelParams) -> dict[str, dict[str, np.ndarray]]:
        """``base`` with the free parameters replaced from ``theta``."""
        out = {c: dict(v) for c, v in base.items()}
        i = 0
        for c, p, n in self.entries:
            out.setdefault(c, {})[p] = np.asarray(theta[i : i + n], dtype=np.float64)
            i += n
        if i != len(theta):
            raise ValueError(f"theta has {len(theta)} values, layout needs {i}")
        return out

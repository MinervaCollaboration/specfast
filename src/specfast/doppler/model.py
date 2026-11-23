"""The forward model of one fit block (one exposure, channel and order).

    F(x) = C(x) * Pixel[ LSF (x) ( prod_i factor_i(ln lambda) ) ](x)

(DESIGN.md, "The forward model"): the spectral factors (star, gas cell,
later tellurics) are multiplied on the fine ln(lambda) grid, convolved once
with the LSF, averaged over each pixel between the edges given by the
wavelength solution, and multiplied by the continuum.

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
        return (self.wavelength, self.continuum, self.lsf, *self.factors)

    @property
    def pixel_edges(self) -> np.ndarray:
        return np.concatenate([self.pixels - 0.5, self.pixels[-1:] + 0.5])

    def parameter_specs(self) -> list[tuple[str, ParameterSpec]]:
        """Every declared parameter as (component name, spec)."""
        return [(c.name, s) for c in self.components for s in c.parameters()]

    # ------------------------------------------------------------- evaluation
    def fine_spectrum(self, params: ModelParams, ctx: ExposureContext) -> np.ndarray:
        """Product of the spectral factors on the fine grid (before the LSF)."""
        ln = self.grid.lnlam
        out = np.ones_like(ln)
        for f in self.factors:
            out = out * f.evaluate(params.get(f.name, {}), ln, ctx)
        return out

    def evaluate(self, params: ModelParams, ctx: ExposureContext) -> np.ndarray:
        """Model flux per pixel."""
        fine = self.fine_spectrum(params, ctx)
        kernel = self.lsf.evaluate(params[self.lsf.name], self.grid, ctx)
        broadened = convolve(fine, kernel)
        lam_edges = self.wavelength.evaluate(params[self.wavelength.name], self.pixel_edges, ctx)
        binned = pixel_integrate(broadened, self.grid, np.log(lam_edges))
        cont = self.continuum.evaluate(params[self.continuum.name], self.pixels, ctx)
        return cont * binned


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

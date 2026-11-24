"""First implementations of the forward-model components (DESIGN.md table).

Every ``evaluate`` is a pure function of (params, coords, ctx) and the
component's read-only static data. See :mod:`specfast.doppler.components`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from specfast.conventions import C_MPS, ln_shift
from specfast.doppler.components import (
    ExposureContext,
    Frame,
    ParameterSpec,
    Params,
    Scope,
    frozen_array,
    register,
)
from specfast.doppler.grid import LnGrid, cubic_interpolate, gaussian_kernel

PER_TRACE = Scope.EXPOSURE | Scope.CHANNEL | Scope.ORDER


def _horner(coeffs: np.ndarray, t: np.ndarray) -> np.ndarray:
    """sum_k coeffs[k] t^k (plain array ops)."""
    out = np.zeros_like(t) + coeffs[-1]
    for c in coeffs[-2::-1]:
        out = out * t + c
    return out


@dataclass(frozen=True)
class _PixelPolynomial:
    """Polynomial in the scaled pixel ``t = (x - x_center) / x_scale``."""

    degree: int
    x_center: float
    x_scale: float

    def scaled(self, x: np.ndarray) -> np.ndarray:
        return (np.asarray(x, dtype=np.float64) - self.x_center) / self.x_scale

    @classmethod
    def for_pixels(cls, degree: int, npix: int, **kw):
        """Centred and scaled so that t spans [-1, 1] over pixels 0..npix-1."""
        half = 0.5 * (npix - 1)
        return cls(degree=degree, x_center=half, x_scale=half, **kw)


@register("wavelength", "polynomial")
@dataclass(frozen=True)
class PolynomialWavelength(_PixelPolynomial):
    """``lambda(x) = sum_k a_k t^k`` [Angstrom, vacuum], per (exposure,
    channel, order)."""

    kind: ClassVar[str] = "wavelength"
    frame: ClassVar[Frame] = Frame.PIXEL
    name: str = "wavelength"

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return (
            ParameterSpec(
                "coeffs",
                self.degree + 1,
                PER_TRACE,
                "Angstrom",
                "polynomial coefficients in the scaled pixel t",
            ),
        )

    def evaluate(self, params: Params, coords, ctx: ExposureContext) -> np.ndarray:
        return _horner(params["coeffs"], self.scaled(coords))


@register("continuum", "polynomial")
@dataclass(frozen=True)
class PolynomialContinuum(_PixelPolynomial):
    """Multiplicative continuum ``C(x) = sum_k c_k t^k`` (flux units), per
    (exposure, channel, order). A first implementation: DESIGN asks for a
    blaze times a spline able to follow 10-20 A structure."""

    kind: ClassVar[str] = "continuum"
    frame: ClassVar[Frame] = Frame.PIXEL
    name: str = "continuum"

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return (
            ParameterSpec(
                "coeffs",
                self.degree + 1,
                PER_TRACE,
                "flux",
                "polynomial coefficients in the scaled pixel t",
            ),
        )

    def evaluate(self, params: Params, coords, ctx: ExposureContext) -> np.ndarray:
        return _horner(params["coeffs"], self.scaled(coords))


@register("lsf", "gaussian")
@dataclass(frozen=True)
class GaussianLSF:
    """Gaussian line-spread function, constant in velocity [m/s] along the
    order; sigma per (channel, order), frozen from the B-star calibration.

    ``half_width`` (grid samples) is static so kernel shapes do not depend on
    parameters; build it with :meth:`for_grid`.
    """

    kind: ClassVar[str] = "lsf"
    frame: ClassVar[Frame] = Frame.OBSERVED
    half_width: int
    name: str = "lsf"

    @classmethod
    def for_grid(cls, grid: LnGrid, max_sigma_mps: float, nsigma: float = 6.0, **kw):
        return cls(half_width=int(np.ceil(nsigma * max_sigma_mps / grid.step_mps)), **kw)

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return (
            ParameterSpec(
                "sigma",
                1,
                Scope.CHANNEL | Scope.ORDER,
                "m/s",
                "Gaussian sigma in velocity",
                lower=0.0,
                fixed=True,
            ),
        )

    def evaluate(self, params: Params, coords: LnGrid, ctx: ExposureContext) -> np.ndarray:
        return gaussian_kernel(params["sigma"][0], coords.step_mps, self.half_width)


@register("star", "template")
@dataclass(frozen=True, eq=False)
class StarTemplate:
    """A stellar rest-frame template ``S``, Doppler shifted.

    Static data: the template on its own (any increasing) ln(lambda) grid in
    the stellar rest frame, vacuum. Parameter ``v``: the barycentric redshift
    velocity [m/s] (positive = receding), composed relativistically with the
    exposure's barycentric correction ``ctx.z_bary``:
    ``S(lambda_obs * D)``, ``D = 1 / (1 + z_meas)``. Linear interpolation of
    the template: tabulate it finely enough (<= grid step).
    """

    kind: ClassVar[str] = "spectrum"
    frame: ClassVar[Frame] = Frame.STELLAR_REST
    lnlam: np.ndarray
    flux: np.ndarray
    name: str = "star"

    def __post_init__(self) -> None:
        object.__setattr__(self, "lnlam", frozen_array(self.lnlam))
        object.__setattr__(self, "flux", frozen_array(self.flux))
        if self.lnlam.shape != self.flux.shape or np.any(np.diff(self.lnlam) <= 0):
            raise ValueError("template lnlam must be increasing and match flux")

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return (
            ParameterSpec(
                "v",
                1,
                Scope.EXPOSURE | Scope.SEGMENT,
                "m/s",
                "barycentric redshift velocity c*z (positive = receding)",
            ),
        )

    def evaluate(self, params: Params, coords: np.ndarray, ctx: ExposureContext) -> np.ndarray:
        ln_rest = coords - ln_shift(params["v"][0], ctx.z_bary)
        return np.interp(ln_rest, self.lnlam, self.flux)


@register("reference", "iodine")
@dataclass(frozen=True, eq=False)
class IodineCell:
    """Gas-cell transmission ``exp(-k * tau(lambda))`` in the observed frame.

    Static data: the optical depth ``tau`` of the atlas (e.g. the NIST
    2018-08 FTS scan, exact vacuum) on its ln(lambda) grid. ``k`` scales the
    optical depth (the cell strength), per (exposure, channel, order).

    Optional learned correction (``correction``, a node grid in the observed
    frame): ``tau -> tau + dtau(lambda)``, with ``dtau`` a static parameter
    (cubic interpolation between nodes) that the template solver
    (:mod:`specfast.doppler.template`) fits with a prior pulling it to zero.
    It shares the observed frame with the tellurics, so the two separate
    only through their priors and their per-exposure scalings (``k`` here,
    airmass and water for the tellurics); and it separates from the star
    only through the spread of barycentric corrections.
    """

    kind: ClassVar[str] = "spectrum"
    frame: ClassVar[Frame] = Frame.OBSERVED
    lnlam: np.ndarray
    tau: np.ndarray
    name: str = "iodine"
    #: Node grid of the learned optical-depth correction (None: no correction).
    correction: LnGrid | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "lnlam", frozen_array(self.lnlam))
        object.__setattr__(self, "tau", frozen_array(self.tau))
        if self.lnlam.shape != self.tau.shape or np.any(np.diff(self.lnlam) <= 0):
            raise ValueError("atlas lnlam must be increasing and match tau")

    @classmethod
    def from_transmission(cls, lnlam, transmission, floor: float = 1e-6, **kw) -> IodineCell:
        """From an atlas transmission ``T`` (tau = -ln T, T floored)."""
        t = np.clip(np.asarray(transmission, dtype=np.float64), floor, None)
        return cls(lnlam=lnlam, tau=-np.log(t), **kw)

    def parameters(self) -> tuple[ParameterSpec, ...]:
        specs = [ParameterSpec("k", 1, PER_TRACE, "", "optical-depth scale", lower=0.0)]
        if self.correction is not None:
            specs.append(_correction_spec("dtau", self.correction, "iodine optical depth"))
        return tuple(specs)

    def learned_terms(self, params: Params, ctx: ExposureContext) -> tuple:
        """(parameter, node grid, per-exposure scale) of each learned term."""
        if self.correction is None:
            return ()
        return (("dtau", self.correction, float(params["k"][0])),)

    def evaluate(self, params: Params, coords: np.ndarray, ctx: ExposureContext) -> np.ndarray:
        tau = np.interp(coords, self.lnlam, self.tau)
        if self.correction is not None:
            tau = tau + cubic_interpolate(params["dtau"], self.correction, coords)
        return np.exp(-params["k"][0] * tau)


@register("reference", "none")
@dataclass(frozen=True)
class NoGasCell:
    """No absorption cell (G-CLEF): a factor of one. The wavelength
    reference is then a simultaneous calibration channel, applied through
    the wavelength component."""

    kind: ClassVar[str] = "spectrum"
    frame: ClassVar[Frame] = Frame.OBSERVED
    name: str = "reference"

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return ()

    def evaluate(self, params: Params, coords: np.ndarray, ctx: ExposureContext) -> np.ndarray:
        return np.ones_like(coords)


def _correction_spec(name: str, grid: LnGrid, what: str) -> ParameterSpec:
    return ParameterSpec(
        name,
        grid.n,
        Scope.ORDER,
        "",
        f"learned static correction to the {what} (node values; fitted by the "
        "template solver, not by the per-block fit)",
        fixed=True,
    )


@register("star", "gridded")
@dataclass(frozen=True)
class GriddedTemplate:
    """A stellar rest-frame template whose spectrum is itself a parameter.

    The template is the node values ``flux`` on a uniform ln(lambda) grid
    (``grid``, stellar rest frame, vacuum), interpolated with cubic
    convolution (:func:`~specfast.doppler.grid.cubic_weights`). The model is
    linear in ``flux``, which is what lets :mod:`specfast.doppler.template`
    infer it with a sparse linear solve.

    Parameters:

    - ``v`` [m/s], per (exposure, segment): barycentric redshift velocity,
      composed with ``ctx.z_bary`` exactly as in :class:`StarTemplate`;
    - ``zero_point`` [m/s], per (template, order): the template's own
      wavelength zero-point offset, a template property shared by every
      channel (a DSST carries 40-100 m/s of these). It shifts the template
      like a velocity: ``S(ln lambda_rest - ln(1 + zero_point / c))``;
    - ``flux``: the node values.

    ``flux`` and ``zero_point`` are declared ``fixed``: the per-block fit
    leaves them alone and the template solver owns them.
    """

    kind: ClassVar[str] = "spectrum"
    frame: ClassVar[Frame] = Frame.STELLAR_REST
    grid: LnGrid
    name: str = "star"

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return (
            ParameterSpec(
                "v",
                1,
                Scope.EXPOSURE | Scope.SEGMENT,
                "m/s",
                "barycentric redshift velocity c*z (positive = receding)",
            ),
            ParameterSpec(
                "zero_point",
                1,
                Scope.ORDER,
                "m/s",
                "template wavelength zero-point offset (a template property)",
                fixed=True,
            ),
            ParameterSpec(
                "flux",
                self.grid.n,
                Scope.ORDER,
                "",
                "template node values (stellar rest frame)",
                fixed=True,
            ),
        )

    def rest_lnlam(self, params: Params, coords: np.ndarray, ctx: ExposureContext) -> np.ndarray:
        """ln(lambda) in the template's frame of the observed ``coords``."""
        zp = float(params.get("zero_point", np.zeros(1))[0])
        return coords - ln_shift(params["v"][0], ctx.z_bary) - np.log1p(zp / C_MPS)

    def evaluate(self, params: Params, coords: np.ndarray, ctx: ExposureContext) -> np.ndarray:
        return cubic_interpolate(params["flux"], self.grid, self.rest_lnlam(params, coords, ctx))


@register("telluric", "scaled")
@dataclass(frozen=True, eq=False)
class Telluric:
    """Telluric transmission in the observed frame, two absorber groups:

        T = exp(-(airmass * tau_dry + water * tau_water))

    - ``tau_dry`` (O2 and other well-mixed gases) scales with the exposure's
      airmass, a known input (``ctx.airmass``);
    - ``tau_water`` scales with the water column ``water`` (a parameter per
      exposure, in the units ``tau_water`` is normalized to; start it from a
      PWV monitor or a humidity proxy).

    Static data: both optical depths on one ln(lambda) grid (a line-by-line
    model, or an atlas cleaned of its noise floor; zeros for an absent
    group). Optional learned corrections ``dtau_dry`` and ``dtau_water`` on a
    node grid (``correction``) let the solver model shallow (micro-)telluric
    lines the prior gets wrong instead of masking them; each correction is
    scaled per exposure like its group. They share the observed frame with
    the iodine cell and separate from it only through priors and the
    airmass/water scalings, and from the star only through the spread of
    barycentric corrections.
    """

    kind: ClassVar[str] = "spectrum"
    frame: ClassVar[Frame] = Frame.OBSERVED
    lnlam: np.ndarray
    tau_dry: np.ndarray
    tau_water: np.ndarray
    name: str = "telluric"
    correction: LnGrid | None = None

    def __post_init__(self) -> None:
        for f in ("lnlam", "tau_dry", "tau_water"):
            object.__setattr__(self, f, frozen_array(getattr(self, f)))
        if not (self.lnlam.shape == self.tau_dry.shape == self.tau_water.shape) or np.any(
            np.diff(self.lnlam) <= 0
        ):
            raise ValueError("telluric lnlam must be increasing and match the optical depths")

    def parameters(self) -> tuple[ParameterSpec, ...]:
        specs = [
            ParameterSpec(
                "water", 1, Scope.EXPOSURE, "", "water column (tau_water units)", lower=0.0
            )
        ]
        if self.correction is not None:
            specs.append(_correction_spec("dtau_dry", self.correction, "dry optical depth"))
            specs.append(_correction_spec("dtau_water", self.correction, "water optical depth"))
        return tuple(specs)

    def learned_terms(self, params: Params, ctx: ExposureContext) -> tuple:
        if self.correction is None:
            return ()
        return (
            ("dtau_dry", self.correction, float(ctx.airmass)),
            ("dtau_water", self.correction, float(params["water"][0])),
        )

    def optical_depth(self, params: Params, coords: np.ndarray, ctx: ExposureContext):
        dry = np.interp(coords, self.lnlam, self.tau_dry)
        wat = np.interp(coords, self.lnlam, self.tau_water)
        if self.correction is not None:
            dry = dry + cubic_interpolate(params["dtau_dry"], self.correction, coords)
            wat = wat + cubic_interpolate(params["dtau_water"], self.correction, coords)
        return ctx.airmass * dry + params["water"][0] * wat

    def evaluate(self, params: Params, coords: np.ndarray, ctx: ExposureContext) -> np.ndarray:
        return np.exp(-self.optical_depth(params, coords, ctx))


@register("detector", "map")
@dataclass(frozen=True)
class DetectorMap:
    """The detector frame of one trace: errors fixed to the pixels.

    Separate from the spectrograph optics (wavelength solution, distortion,
    LSF), which move with the spectrum when the instrument changes (the
    KiwiSpec along-order distortion followed a ~68 px remount shift). The
    detector map stays with the pixels:

    - ``dx`` [px], one value per pixel *edge* (``npix + 1``): the true edge
      position is ``nominal + dx``. Pixel-position errors, pixel-size
      residuals (a difference of neighbouring edges) and stitching steps
      (a step in ``dx``) all live here;
    - ``response``, one per pixel: the multiplicative sensitivity left after
      flat-fielding (1 = perfect flat). Charge-transfer effects and bad
      pixels are not modelled here: bad pixels are masked (``Mask``).

    Scope: per (channel, order) trace, static (calibration from flats or a
    comb). Both are ``fixed`` by default; :mod:`specfast.doppler.template`
    can fit them with a strong prior.

    Why it matters for templates: the barycentric motion moves the star
    across tens of pixels over a year (+/-25 km/s at ~1 km/s per px) while
    iodine and tellurics stay put, so a static pixel-frame error looks like a
    barycentric-dependent template error. It separates from the template
    only through that motion, and only for template structure narrower than
    the barycentric shift in pixels.
    """

    kind: ClassVar[str] = "detector"
    frame: ClassVar[Frame] = Frame.PIXEL
    npix: int
    name: str = "detector"

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return (
            ParameterSpec(
                "dx",
                self.npix + 1,
                Scope.CHANNEL | Scope.ORDER,
                "px",
                "pixel-edge position offsets (detector frame)",
                fixed=True,
            ),
            ParameterSpec(
                "response",
                self.npix,
                Scope.CHANNEL | Scope.ORDER,
                "",
                "per-pixel sensitivity residual after flat-fielding",
                fixed=True,
            ),
        )

    def edges(self, params: Params, nominal_edges: np.ndarray) -> np.ndarray:
        """True pixel-edge positions [px]."""
        return nominal_edges + params["dx"]

    def evaluate(self, params: Params, coords, ctx: ExposureContext) -> np.ndarray:
        """Multiplicative response per pixel (``coords`` is ignored)."""
        return np.asarray(params["response"], dtype=np.float64)

    @staticmethod
    def identity(npix: int) -> dict[str, np.ndarray]:
        """Parameters of a perfect detector."""
        return {"dx": np.zeros(npix + 1), "response": np.ones(npix)}

"""First implementations of the forward-model components (DESIGN.md table).

Every ``evaluate`` is a pure function of (params, coords, ctx) and the
component's read-only static data. See :mod:`specfast.doppler.components`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from specfast.conventions import ln_shift
from specfast.doppler.components import (
    ExposureContext,
    Frame,
    ParameterSpec,
    Params,
    Scope,
    frozen_array,
    register,
)
from specfast.doppler.grid import LnGrid, gaussian_kernel

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
    """

    kind: ClassVar[str] = "spectrum"
    frame: ClassVar[Frame] = Frame.OBSERVED
    lnlam: np.ndarray
    tau: np.ndarray
    name: str = "iodine"

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
        return (ParameterSpec("k", 1, PER_TRACE, "", "optical-depth scale", lower=0.0),)

    def evaluate(self, params: Params, coords: np.ndarray, ctx: ExposureContext) -> np.ndarray:
        return np.exp(-params["k"][0] * np.interp(coords, self.lnlam, self.tau))


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

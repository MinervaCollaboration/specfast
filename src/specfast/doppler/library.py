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
from specfast.doppler.grid import (
    LnGrid,
    cubic_interpolate,
    gaussian_kernel,
    gh_kernel,
    lagrange_weights,
)

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


@register("wavelength", "optics")
@dataclass(frozen=True, eq=False)
class OpticsWavelength:
    """Optics-frame wavelength solution of one trace (DESIGN, "Wavelength
    component, production form"):

        lambda(p) = L(p') + sum_k a_k t^k,   p' = p + D(p),
        t = (p' - x_center) / x_scale

    - ``L``: the static optical-model curve of the trace (the optics
      guess), a polynomial in ``(p' - base_center) / base_scale``
      (``base`` coefficients, lowest first; empty = no base, so the
      solution is a plain polynomial in p');
    - ``D(p)`` [px]: the static along-order distortion (a per-era
      calibration, common to all orders and fibres; a pixel whose nominal
      centre is p samples p + D(p)), tabulated at the detector columns
      0..len-1 and linearly interpolated (pixel edges); None = no distortion;
    - ``a_k``: the free perturbation, per (exposure, channel, order).

    D lives in the optics frame: it moves with the spectrum when the optics
    change, unlike the detector map (:class:`DetectorMap`), which stays with
    the pixels.
    """

    kind: ClassVar[str] = "wavelength"
    frame: ClassVar[Frame] = Frame.PIXEL
    degree: int
    x_center: float
    x_scale: float
    base: np.ndarray = None
    base_center: float = 0.0
    base_scale: float = 1.0
    distortion: np.ndarray | None = None
    name: str = "wavelength"

    def __post_init__(self) -> None:
        base = np.zeros(0) if self.base is None else self.base
        object.__setattr__(self, "base", frozen_array(base))
        if self.distortion is not None:
            object.__setattr__(self, "distortion", frozen_array(self.distortion))

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return (
            ParameterSpec(
                "coeffs",
                self.degree + 1,
                PER_TRACE,
                "Angstrom",
                "perturbation polynomial in the scaled distorted pixel t",
            ),
        )

    def distorted(self, x: np.ndarray) -> np.ndarray:
        """p + D(p) [px]."""
        x = np.asarray(x, dtype=np.float64)
        if self.distortion is None:
            return x
        cols = np.arange(self.distortion.size, dtype=np.float64)
        return x + np.interp(x, cols, self.distortion)

    def base_curve(self, xd: np.ndarray) -> np.ndarray:
        if self.base.size == 0:
            return np.zeros_like(xd)
        return _horner(self.base, (xd - self.base_center) / self.base_scale)

    def scaled(self, x: np.ndarray) -> np.ndarray:
        return (self.distorted(x) - self.x_center) / self.x_scale

    def evaluate(self, params: Params, coords, ctx: ExposureContext) -> np.ndarray:
        xd = self.distorted(coords)
        return self.base_curve(xd) + _horner(params["coeffs"], (xd - self.x_center) / self.x_scale)


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


@register("lsf", "gauss_hermite")
@dataclass(frozen=True, eq=False)
class GaussHermiteLSF:
    """Gauss-Hermite LSF that varies along the order, from a static map plus
    a per-exposure illumination kernel.

    **Static map** (per channel and order, per era; a calibration from
    B-star frames): along the order, with ``u`` the pixel fraction across
    the block minus 1/2,

        sigma(u) = s0 (1 + g u + q (u^2 - 1/12)),  h3(u) = h3 + h3g u,  h4

    (``map`` = [s0 (m/s), g, q, h3, h3g, h4], fixed). The kernel is evaluated
    exactly at ``nnode`` nodes along the order and the model is blended
    between them with Lagrange weights (:meth:`node_weights`; the forward
    model convolves once per node and blends per pixel).

    **Illumination kernel** (``illum``, per exposure and channel, shared by
    every order): a fibre-illumination change convolves every detector
    position with the same small kernel. Two forms:

    - ``"gh"``: ``illum`` = [dw, dh3], cumulants added at a reference width
      ``sig_ref_mps``: ``sigma^2 = sigma_s^2 + 2 dw sig_ref^2``,
      ``h3 = h3_s + dh3 (sig_ref / sigma_s)^3``;
    - ``"basis"``: ``illum`` = coefficients of empirical zero-sum kernel
      perturbations ``basis`` (nk, L) on a velocity grid of ``basis_step_mps``
      (one unit = one standard deviation of the B-star scatter), added to
      the static kernel and renormalized.

    ``illum`` is declared ``fixed``: the per-block fit leaves it alone and a
    shared-parameter step fits it across the orders of an exposure, under a
    hierarchical (channel, era) prior.
    """

    kind: ClassVar[str] = "lsf"
    frame: ClassVar[Frame] = Frame.OBSERVED
    half_width: int
    step_mps: float
    #: Block pixel range spanned by u = -1/2 .. +1/2 [px].
    pixel_lo: float
    pixel_hi: float
    nnode: int = 5
    illumination: str = "gh"
    sig_ref_mps: float = 1500.0
    basis: np.ndarray | None = None
    basis_step_mps: float | None = None
    name: str = "lsf"

    def __post_init__(self) -> None:
        if self.illumination not in ("gh", "basis", "none"):
            raise ValueError(f"illumination must be gh, basis or none, got {self.illumination!r}")
        if self.illumination == "basis":
            if self.basis is None or self.basis_step_mps is None:
                raise ValueError("basis illumination needs basis and basis_step_mps")
            b = np.atleast_2d(np.asarray(self.basis, dtype=np.float64))
            # resample onto this grid's velocity step (zero outside)
            m = b.shape[1] // 2
            ub = (np.arange(b.shape[1]) - m) * self.basis_step_mps
            ug = np.arange(-self.half_width, self.half_width + 1) * self.step_mps
            rs = np.array([np.interp(ug, ub, row, left=0.0, right=0.0) for row in b])
            rs *= self.basis_step_mps / self.step_mps
            object.__setattr__(self, "basis", frozen_array(rs))

    @classmethod
    def for_grid(cls, grid: LnGrid, max_sigma_mps: float, nsigma: float = 6.0, **kw):
        return cls(
            half_width=int(np.ceil(nsigma * max_sigma_mps / grid.step_mps)),
            step_mps=grid.step_mps,
            **kw,
        )

    @property
    def n_illum(self) -> int:
        if self.illumination == "gh":
            return 2
        if self.illumination == "basis":
            return int(self.basis.shape[0])
        return 0

    def parameters(self) -> tuple[ParameterSpec, ...]:
        specs = [
            ParameterSpec(
                "map",
                6,
                Scope.ERA | Scope.CHANNEL | Scope.ORDER,
                "",
                "static map: s0 [m/s], g, q, h3, h3g, h4",
                fixed=True,
            )
        ]
        if self.n_illum:
            specs.append(
                ParameterSpec(
                    "illum",
                    self.n_illum,
                    Scope.EXPOSURE | Scope.CHANNEL,
                    "",
                    "illumination kernel (shared by all orders of an exposure and channel)",
                    fixed=True,
                )
            )
        return tuple(specs)

    @property
    def nodes(self) -> np.ndarray:
        return np.linspace(-0.5, 0.5, self.nnode) if self.nnode > 1 else np.zeros(1)

    def node_weights(self, pixels: np.ndarray) -> np.ndarray:
        """(nnode, npix) blending weights of the node kernels."""
        u = (np.asarray(pixels, dtype=np.float64) - self.pixel_lo) / (
            self.pixel_hi - self.pixel_lo
        ) - 0.5
        if self.nnode == 1:
            return np.ones((1, u.size))
        return lagrange_weights(u, self.nodes)

    def node_shapes(self, params: Params) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(sigma [m/s], h3, h4) of the static map at the nodes, with the
        illumination cumulants added in the ``gh`` form."""
        s0, g, q, h3, h3g, h4 = (float(v) for v in params["map"])
        u = self.nodes
        sig = s0 * (1.0 + g * u + q * (u * u - 1.0 / 12.0))
        hh3 = h3 + h3g * u
        hh4 = np.full_like(u, h4)
        if self.illumination == "gh":
            dw, dh = (float(v) for v in params["illum"])
            r = self.sig_ref_mps
            s2 = np.clip(sig * sig + 2.0 * dw * r * r, (0.2 * s0) ** 2, None)
            hh3 = hh3 + dh * (r / sig) ** 3
            sig = np.sqrt(s2)
        return sig, hh3, hh4

    def kernels(self, params: Params, coords: LnGrid) -> list[np.ndarray]:
        """The normalized kernel at each node, on the fine grid."""
        sig, h3, h4 = self.node_shapes(params)
        out = []
        for k in range(sig.size):
            ker = gh_kernel(sig[k], h3[k], h4[k], coords.step_mps, self.half_width)
            if self.illumination == "basis":
                ker = ker + np.asarray(params["illum"], dtype=np.float64) @ self.basis
                ker = ker / ker.sum()
            out.append(ker)
        return out

    def evaluate(self, params: Params, coords: LnGrid, ctx: ExposureContext) -> np.ndarray:
        """The kernel at the middle node (a representative single kernel)."""
        ks = self.kernels(params, coords)
        return ks[len(ks) // 2]


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
    #: ``optical_depth``: ``T = exp(-k tau)`` (physical: the column scales);
    #: ``linear``: ``T = 1 + k (exp(-tau) - 1)`` (legacy codes' depth scaling).
    scaling: str = "optical_depth"

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
        if self.scaling == "linear":
            return 1.0 + params["k"][0] * (np.exp(-tau) - 1.0)
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


@register("cti", "serial")
@dataclass(frozen=True)
class SerialCTI:
    """Serial charge-transfer inefficiency of a trace (detector frame).

    The serial register runs along the dispersion with the amplifier at
    column ``amplifier_column`` (KiwiSpec: the blue end of every order), so
    pixel p makes ``|p - amplifier_column| + transfer_offset`` transfers.
    A fraction ``L(p) = n(p) q(S)`` of its charge is captured and re-emitted
    into the pixels read after it (away from the amplifier) with the
    two-species trail ``tau(k) ~ a1 exp(-k / l1) + a2 exp(-k / l2)``,
    normalized to one (charge is conserved):

        F_obs(p) = F(p) (1 - L(p)) + sum_k tau(k) F(p -+ k) L(p -+ k)

    ``q(S) = q_ref (S / s_ref)^alpha`` per transfer, with ``S`` the signal of
    the trace's peak detector pixel [ADU] = ``signal_scale * F`` (flux per
    extracted pixel times the inverse of gain x effective profile rows).

    All parameters are calibration constants (``fixed``; from extended pixel
    edge responses per era). The model applies the operator to the model
    flux with ``L`` evaluated on that flux; :meth:`operator` returns the
    linearized operator (``L`` frozen), which is what the solvers use for
    Jacobian columns and the template's linear operator.
    """

    kind: ClassVar[str] = "cti"
    frame: ClassVar[Frame] = Frame.PIXEL
    amplifier_column: float = 0.0
    transfer_offset: float = 51.0
    trail_length: int = 120
    name: str = "cti"

    def parameters(self) -> tuple[ParameterSpec, ...]:
        return (
            ParameterSpec(
                "trap",
                7,
                Scope.ERA,
                "",
                "q_ref (per transfer), s_ref [ADU], alpha, a1, l1 [px], a2, l2 [px]",
                fixed=True,
            ),
            ParameterSpec("signal_scale", 1, Scope.GLOBAL, "ADU per flux unit", "", fixed=True),
        )

    def trail(self, params: Params) -> np.ndarray:
        _, _, _, a1, l1, a2, l2 = (float(v) for v in params["trap"])
        k = np.arange(1, self.trail_length + 1, dtype=np.float64)
        t = a1 * np.exp(-k / l1) + a2 * np.exp(-k / l2)
        return t / t.sum()

    def loss(self, params: Params, flux: np.ndarray, pixels: np.ndarray) -> np.ndarray:
        q_ref, s_ref, alpha = (float(v) for v in params["trap"][:3])
        sig = np.clip(np.asarray(flux) * float(params["signal_scale"][0]), 1.0, None)
        n = np.abs(np.asarray(pixels, dtype=np.float64) - self.amplifier_column)
        n = n + self.transfer_offset
        return np.clip(n * q_ref * (sig / s_ref) ** alpha, 0.0, 0.5)

    def _redistribute(self, lost: np.ndarray, tau: np.ndarray, pixels) -> np.ndarray:
        """Re-emitted charge per pixel (away from the amplifier)."""
        full = np.convolve(lost, np.concatenate([[0.0], tau]))
        if self.amplifier_column <= float(np.min(pixels)):
            return full[: lost.size]
        # amplifier at the high-column end: trail toward lower columns
        rev = np.convolve(lost[::-1], np.concatenate([[0.0], tau]))[: lost.size]
        return rev[::-1]

    def apply_linear(self, params: Params, loss: np.ndarray, values: np.ndarray, pixels):
        """The linearized operator (``L`` = ``loss`` frozen) applied to ``values``."""
        lost = values * loss
        return values - lost + self._redistribute(lost, self.trail(params), pixels)

    def evaluate(self, params: Params, coords, ctx: ExposureContext, flux=None) -> np.ndarray:
        """Observed flux for the model flux ``flux`` at pixels ``coords``."""
        loss = self.loss(params, flux, coords)
        return self.apply_linear(params, loss, flux, coords)

    @staticmethod
    def kiwispec_default() -> dict[str, np.ndarray]:
        """Trap parameters from the KiwiSpec serial EPER fits (2016-2026, one
        set; era differences are within +-30%): 4e-6 per transfer at 1000 ADU
        falling as S^-0.5; trail 2.5e-4 exp(-k/2.2) + 1.5e-4 exp(-k/20)."""
        return {
            "trap": np.array([4.0e-6, 1000.0, -0.5, 2.5e-4, 2.2, 1.5e-4, 20.0]),
            "signal_scale": np.array([1.0 / (1.265 * 4.6)]),
        }


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

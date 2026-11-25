"""Stellar-template inference: fit the template from the instrument's own spectra.

Why (DESIGN.md "Templates"): external templates (DSSTs) carry per-order
wavelength zero-point errors of 40-100 m/s that are template properties,
common to every telescope. A template inferred from the instrument's own
spectra removes them at the source, and an instrument without a gas cell
(G-CLEF, comb-calibrated) needs such templates anyway, because its comb
calibrates the detector but not the template's wavelength scale.

The model is the existing forward model (:class:`~specfast.doppler.model.
ForwardModel`), with the components grouped by the frame they live in:

==================  =====================================  ===================
frame               components                             moves with
==================  =====================================  ===================
star                :class:`GriddedTemplate` (flux nodes,  RV and barycentric
                    per-order zero point)                  correction
observatory         iodine (fixed prior + optional         nothing (observed
                    learned ``dtau``), tellurics (prior    wavelength)
                    + learned ``dtau_dry``/``dtau_water``,
                    scaled by airmass / water)
spectrograph        wavelength solution (and distortion),  the spectrum, when
optics              LSF                                    the optics move
detector            :class:`DetectorMap`: pixel-edge       the pixels
                    offsets dx(p), per-pixel response
==================  =====================================  ===================

(Sky emission is additive and is not in the multiplicative model yet.)

Template representation
-----------------------
Per order (one template per ``Block.order``), node values on a uniform
ln(lambda) grid in the stellar rest frame, cubic-convolution interpolated
(:func:`template_grid` sets the step from the pixel width and an
oversampling factor). Float64 throughout. The template enters the model
linearly: for each block, ``F = A_b s`` with the sparse operator

    A_b = diag(R C) . P . K . diag(O_b) . W_b(v_b + zero_point, z_bary)

(``W``: cubic interpolation from the nodes to the fine grid at the shifted
rest wavelengths; ``O``: the observatory-frame factors; ``K``: the LSF
convolution; ``P``: pixel integration between the detector-corrected
edges; ``R C``: detector response and continuum).

Regularization pulls the *correction* ``s - p`` toward zero, where ``p`` is
the prior spectrum: an L2 term (``1 / prior_sigma^2`` per node) and a
second-difference smoothness term (``1 / smooth_sigma^2``). Two modes:

- ``modify``: ``p`` is a real spectrum (a DSST, a solar atlas, a synthetic
  spectrum) and the fit is a regularized correction to it. The per-order
  zero points are fitted as template properties (see below);
- ``infer``: ``p`` is flat (or any weak prior) and ``prior_sigma`` is large;
  the template comes from the data. The first step is a template solve from
  the starting velocities.

Solver
------
Alternation (``strategy="alternate"``):

1. velocities and nuisances: every block is fitted on its own with the
   template held fixed (:func:`~specfast.doppler.fit.fit_block`: velocity,
   continuum, and whatever wavelength, iodine-strength and water parameters
   are free). The per-block velocities are then split into one velocity per
   ``Block.key`` (exposure) plus one offset per order,
   ``v_b = v_key + delta_order``, with the weighted mean offset fixed at
   zero. The offsets are added to the template zero points (a template
   property, shared by every channel) and the blocks take ``v_key``;
2. template: given velocities and nuisances the model is linear in the
   nodes; the normal equations are banded, solved by a banded Cholesky
   (scipy), and the diagonal of their inverse (a selected inversion) is the
   template's own variance, exposed as ``OrderTemplate.sigma``;
3. observatory: Gauss-Newton step for the learned observatory-frame
   corrections (iodine, tellurics), all terms of an order jointly
   (scipy.sparse);
4. detector (optional, ``fit_detector``): Gauss-Newton step for each trace's
   detector map under a strong prior.

A joint sparse solve of all blocks is the natural next step; the hook is
``strategy="joint"`` (:meth:`TemplateSolver.joint_step`): template and block
velocities solved together each sweep.

Degeneracies (read before trusting a template)
----------------------------------------------
- **Star vs observatory frame.** The template separates from anything in the
  observed frame (iodine correction, tellurics, sky) *only* through the
  spread of barycentric corrections: template structure on velocity scales
  wider than the spread cannot be told from observatory-frame structure. A
  fixed observatory prior (an iodine atlas) is no escape: its errors alias
  into the template when the spread is small. :func:`check_separability`
  computes the separability ``1 - |<exp(i q v_B)>|^2`` (q ~ 1 / scale) at the
  requested template resolution and the widest separable scale; the solver
  warns (:class:`TemplateDegeneracyWarning`) and flags the result when the
  spread is too small.
- **Iodine vs tellurics.** Both live in the observed frame; they separate only
  through their priors and their per-exposure scalings (iodine strength,
  airmass, water column). The solver reports the cosine between the scaling
  vectors and warns when they are (nearly) proportional.
- **Star vs detector frame.** The barycentric motion moves the star across
  the pixels (+/-25 km/s is tens of KiwiSpec pixels) while the detector map
  stays fixed, so a static pixel-frame error looks like a barycentric-
  dependent template error. They separate only for template structure
  narrower than the barycentric shift in pixels; the check reports the shift
  range in pixels and the separability at the one-pixel scale.
- **Zero points.** The overall template zero point is degenerate with the
  systemic velocity. In ``modify`` mode it is the prior's (weighted mean
  order offset fixed at zero); in ``infer`` mode it is set by the starting
  velocities and only relative velocities mean anything. With a gas cell
  the relative order zero points are on the cell's scale; without one they
  are on the wavelength calibration's scale.
- **Template level vs continuum.** The template's low-order shape is
  degenerate with the continuum; the prior holds it.

The template variance is conditional on the velocities and nuisances (it
does not propagate their uncertainty) and is a diagonal approximation.
"""

from __future__ import annotations

import copy
import warnings
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import scipy.linalg
import scipy.sparse as sp
import scipy.sparse.linalg

from specfast.config import TemplateConfig
from specfast.conventions import C_KMS
from specfast.doppler.components import ExposureContext
from specfast.doppler.fit import fit_block
from specfast.doppler.grid import (
    LnGrid,
    cubic_weights,
    hermite_value,
    kernel_sigma_mps,
    pixel_integrate,
)
from specfast.doppler.library import GriddedTemplate
from specfast.doppler.model import ForwardModel, ParameterLayout

__all__ = [
    "Block",
    "OrderTemplate",
    "SeparabilityReport",
    "TemplateDegeneracyWarning",
    "TemplateResult",
    "TemplateSolver",
    "banded_inverse_diagonal",
    "block_pixel_operator",
    "check_separability",
    "combine_velocities",
    "infer_template",
    "pixel_matrix",
    "prior_on_grid",
    "separability",
    "template_grid",
]


class TemplateDegeneracyWarning(UserWarning):
    """The data cannot separate the template from another frame."""


# ---------------------------------------------------------------------------
# inputs and outputs
# ---------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class Block:
    """One extracted spectrum segment (exposure, channel, order) and its model.

    ``key``: blocks with the same key share one velocity (an exposure, or an
    (exposure, channel) pair when channels have different midpoints).
    ``order``: blocks with the same order share one template, its zero point
    and the learned observatory corrections. ``trace``: blocks with the same
    trace share one detector map (default ``(channel, order)``).
    ``sigma`` is the per-pixel noise; ``inf`` masks a pixel.
    ``exclude`` lists (component, parameter) pairs the per-block fit must
    hold (e.g. a comb-calibrated wavelength solution).
    """

    key: Hashable
    order: Hashable
    model: ForwardModel
    data: np.ndarray
    sigma: np.ndarray
    ctx: ExposureContext
    start: Mapping
    channel: Hashable = None
    exclude: tuple[tuple[str, str], ...] = ()

    @property
    def trace(self) -> tuple:
        return (self.channel, self.order)


@dataclass
class OrderTemplate:
    """The inferred template of one order."""

    grid: LnGrid
    #: Node values (stellar rest frame, before the zero point).
    flux: np.ndarray
    #: 1-sigma of each node (diagonal of the inverse normal matrix).
    sigma: np.ndarray
    prior: np.ndarray
    #: Template wavelength zero point [m/s] (a template property) and its error.
    zero_point: float
    zero_point_sigma: float
    #: Learned observatory-frame corrections {(component, parameter): nodes}.
    observatory: dict = field(default_factory=dict)

    @property
    def lnlam(self) -> np.ndarray:
        return self.grid.lnlam


@dataclass(frozen=True)
class SeparabilityReport:
    """What the barycentric spread can and cannot separate."""

    #: Weighted std and full range of the barycentric velocities [km/s].
    berv_std_kms: float
    berv_range_kms: float
    #: Template resolution element the check uses [km/s].
    resolution_kms: float
    #: Separability (0 = fully degenerate, 1 = fully separable) at that scale.
    separability: float
    #: Widest velocity scale still separable (separability >= threshold) [km/s].
    separable_scale_kms: float
    #: Pixel width [km/s] and the barycentric range in pixels.
    pixel_kms: float
    berv_range_px: float
    #: Separability of template vs detector frame at the one-pixel scale.
    detector_separability: float
    #: Max |cos| between per-exposure scalings of learned observatory terms.
    observatory_scaling_cos: float
    #: Star vs observatory frame unconstrained at the requested resolution.
    degenerate: bool
    #: Star vs detector frame unconstrained.
    detector_degenerate: bool
    #: Observatory terms (iodine, tellurics) mutually unconstrained.
    observatory_degenerate: bool
    messages: tuple[str, ...] = ()


@dataclass
class TemplateResult:
    templates: dict
    #: {key: (velocity [m/s], sigma [m/s])}: barycentric redshift velocities.
    velocities: dict
    #: Per block: the final parameters and the per-block velocity and sigma.
    block_params: list
    block_velocity: np.ndarray
    block_velocity_sigma: np.ndarray
    #: Per-order velocity offsets found at each sweep ({order: m/s}); the
    #: first is the prior's order pattern, the last the residual one.
    order_offsets_history: list
    #: Detector maps per trace (when fitted).
    detector: dict
    separability: SeparabilityReport
    iterations: int
    converged: bool
    mode: str

    def velocity_array(self, keys: Sequence) -> tuple[np.ndarray, np.ndarray]:
        v = np.array([self.velocities[k][0] for k in keys])
        s = np.array([self.velocities[k][1] for k in keys])
        return v, s


# ---------------------------------------------------------------------------
# grids and linear operators
# ---------------------------------------------------------------------------
def template_grid(
    lam_min: float,
    lam_max: float,
    pixel_kms: float,
    oversample: float,
    max_shift_kms: float,
    margin_kms: float = 20.0,
) -> LnGrid:
    """Template node grid for an order covering [lam_min, lam_max] Angstrom
    (observed), with ``oversample`` nodes per pixel of width ``pixel_kms``,
    extended by the largest velocity shift plus ``margin_kms`` (at least the
    LSF kernel's half width)."""
    return LnGrid.covering(
        lam_min, lam_max, step_kms=pixel_kms / oversample, margin_kms=max_shift_kms + margin_kms
    )


def prior_on_grid(lnlam: np.ndarray, flux: np.ndarray, grid: LnGrid) -> np.ndarray:
    """A tabulated prior spectrum resampled (linearly) onto the node grid;
    tabulate it at or below the node step."""
    return np.interp(grid.lnlam, lnlam, flux)


def pixel_matrix(grid: LnGrid, ln_edges: np.ndarray) -> sp.csr_matrix:
    """The pixel-integration operator of :func:`~specfast.doppler.grid.
    pixel_integrate` as a sparse matrix (npix x grid.n), exact to rounding.

    Built by probing the operator with combs of unit samples spaced wider
    than any pixel's support, so it stays consistent with the forward model
    by construction.
    """
    pos = (np.asarray(ln_edges) - grid.ln_start) / grid.step
    i = np.floor(pos).astype(np.int64)
    lo = i[:-1] - 1
    hi = i[1:] + 2
    s = int(np.max(hi - lo)) + 2
    rows, cols, vals = [], [], []
    k = np.arange(lo.size)
    for r in range(s):
        vec = np.zeros(grid.n)
        vec[r::s] = 1.0
        out = pixel_integrate(vec, grid, ln_edges)
        j = lo + np.mod(r - lo, s)
        ok = (j <= hi) & (j >= 0) & (j < grid.n)
        rows.append(k[ok])
        cols.append(j[ok])
        vals.append(out[ok])
    return sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(lo.size, grid.n),
    )


def point_matrix(grid: LnGrid, ln_x: np.ndarray) -> sp.csr_matrix:
    """The point-sampling operator (cubic Hermite value at ``ln_x``,
    :func:`~specfast.doppler.grid.hermite_value`) as a sparse matrix,
    built by probing like :func:`pixel_matrix`."""
    pos = (np.asarray(ln_x) - grid.ln_start) / grid.step
    i = np.floor(pos).astype(np.int64)
    lo, hi = i - 2, i + 3
    s = 8
    rows, cols, vals = [], [], []
    k = np.arange(i.size)
    for r in range(s):
        vec = np.zeros(grid.n)
        vec[r::s] = 1.0
        out = hermite_value(vec, grid, ln_x)
        j = lo + np.mod(r - lo, s)
        ok = (j <= hi) & (j >= 0) & (j < grid.n)
        rows.append(k[ok])
        cols.append(j[ok])
        vals.append(out[ok])
    m = sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(i.size, grid.n),
    )
    m.eliminate_zeros()
    return m


def convolution_matrix(kernel: np.ndarray, n: int) -> sp.csr_matrix:
    """``np.convolve(values, kernel, mode="same")`` as a sparse matrix."""
    hw = kernel.size // 2
    offsets = np.arange(-hw, hw + 1)
    return sp.diags([np.full(n, kernel[hw - d]) for d in offsets], offsets, shape=(n, n)).tocsr()


def block_pixel_operator(
    model: ForwardModel, params: Mapping, ctx: ExposureContext, include_cti: bool = True
):
    """``diag(R C) . P . K`` of one block (npix x fine grid) as a sparse
    matrix; for an LSF varying along the order, ``sum_k diag(R C W_k) P K_k``
    over its nodes (:meth:`~specfast.doppler.model.ForwardModel.node_kernels`)."""
    if model.sampling == "point":
        P = point_matrix(model.grid, model.ln_sample(params, ctx))
    else:
        P = pixel_matrix(model.grid, model.ln_edges(params, ctx)).tocsr()
    pf = model.pixel_factor(params, ctx)
    ks, w = model.node_kernels(params, ctx)
    # P is banded (contiguous columns per row): convolve each row's band with
    # the (reversed) kernels directly instead of multiplying sparse matrices
    npix, n = P.shape
    P.sort_indices()
    starts = np.array(
        [P.indices[P.indptr[i]] if P.indptr[i + 1] > P.indptr[i] else 0 for i in range(npix)]
    )
    ends = np.array(
        [
            P.indices[P.indptr[i + 1] - 1] if P.indptr[i + 1] > P.indptr[i] else 0
            for i in range(npix)
        ]
    )
    width = int(np.max(ends - starts)) + 1
    Pb = np.zeros((npix, width))
    for i in range(npix):
        a, b = P.indptr[i], P.indptr[i + 1]
        Pb[i, P.indices[a:b] - starts[i]] = P.data[a:b]
    L = ks[0].size
    hw = L // 2
    band = np.zeros((npix, width + L - 1))
    weights = [np.ones(npix)] if w is None else list(w)
    for k, ker in enumerate(ks):
        kr = ker[::-1]
        pk = np.zeros_like(band)
        for a in range(width):
            pk[:, a : a + L] += Pb[:, a : a + 1] * kr[None, :]
        band += (pf * weights[k])[:, None] * pk
    cols = starts[:, None] - hw + np.arange(width + L - 1)[None, :]
    band = np.where((cols >= 0) & (cols < n), band, 0.0)
    cols = np.clip(cols, 0, n - 1)
    out = sp.csr_matrix(
        (band.ravel(), cols.ravel(), np.arange(npix + 1) * band.shape[1]), shape=(npix, n)
    )
    out.sum_duplicates()
    if model.cti is not None and include_cti:
        out = cti_matrix(model, params, ctx) @ out
    return out.tocsr()


def cti_offset(model: ForwardModel, params: Mapping, ctx: ExposureContext) -> np.ndarray:
    """``model with CTI - model without CTI`` at ``params`` (zero without
    CTI). The CTI perturbation is ~1e-3 of the flux; the template solver
    subtracts it from the data at the current model instead of carrying the
    CTI operator (a wide band) in its normal equations."""
    if model.cti is None:
        return np.zeros(model.pixels.size)
    flux = model.pixel_factor(params, ctx) * model.broaden_and_bin(
        model.fine_spectrum(params, ctx),
        *model.node_kernels(params, ctx),
        model.ln_edges(params, ctx),
    )
    return model.evaluate(params, ctx) - flux


def cti_matrix(model: ForwardModel, params: Mapping, ctx: ExposureContext) -> sp.csr_matrix:
    """The linearized CTI operator of a block (npix x npix; loss fraction at
    the current model)."""
    cti = model.cti
    cp = params[cti.name]
    loss = model.cti_loss(params, ctx)
    n = loss.size
    tau = cti.trail(cp)
    rows, cols, vals = [np.arange(n)], [np.arange(n)], [1.0 - loss]
    sign = 1 if cti.amplifier_column <= float(np.min(model.pixels)) else -1
    for k in range(1, min(tau.size, n - 1) + 1):
        src = np.arange(n - k) if sign > 0 else np.arange(k, n)
        rows.append(src + sign * k)
        cols.append(src)
        vals.append(tau[k - 1] * loss[src])
    return sp.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)
    )


def interpolation_matrix(grid: LnGrid, ln_x: np.ndarray) -> sp.csr_matrix:
    """Cubic interpolation from ``grid`` nodes to ``ln_x`` (len(ln_x) x grid.n)."""
    idx, w = cubic_weights(grid, ln_x)
    rows = np.repeat(np.arange(ln_x.size), 4)
    return sp.csr_matrix((w.ravel(), (rows, idx.ravel())), shape=(ln_x.size, grid.n))


def second_difference(n: int) -> sp.csr_matrix:
    return sp.diags([np.ones(n - 2), -2 * np.ones(n - 2), np.ones(n - 2)], [0, 1, 2], (n - 2, n))


def _to_banded_upper(N: sp.spmatrix) -> np.ndarray:
    C = N.tocoo()
    b = int(np.max(C.col - C.row)) if C.nnz else 0
    N = N.tocsr()
    ab = np.zeros((b + 1, N.shape[0]))
    for k in range(b + 1):
        ab[b - k, k:] = N.diagonal(k)
    return ab


def banded_inverse_diagonal(cb: np.ndarray) -> np.ndarray:
    """Diagonal of ``A^-1`` from the upper banded Cholesky factor ``cb`` of
    ``A = U^T U`` (scipy ``cholesky_banded`` storage), by the Takahashi
    selected-inversion recursion: O(n b^2), no dense inverse."""
    b = cb.shape[0] - 1
    n = cb.shape[1]
    Zb = np.zeros((b + 1, n))  # Zb[d, i] = Z[i, i + d]
    a = np.arange(b)
    A, Cc = np.meshgrid(a, a, indexing="ij")
    absd = np.abs(A - Cc)
    mind = np.minimum(A, Cc)
    for i in range(n - 1, -1, -1):
        uii = cb[b, i]
        m = min(b, n - 1 - i)
        if m == 0:
            Zb[0, i] = 1.0 / uii**2
            continue
        d = np.arange(1, m + 1)
        u = cb[b - d, i + d]
        W = Zb[absd[:m, :m], i + 1 + mind[:m, :m]]
        z = -(u @ W) / uii
        Zb[1 : m + 1, i] = z
        Zb[0, i] = (1.0 / uii - u @ z) / uii
    return Zb[0]


def solve_banded_spd(
    N: sp.spmatrix,
    rhs: np.ndarray,
    want_diag: bool = True,
    constraint: tuple[np.ndarray, float] | None = None,
):
    """Solve the SPD system ``N x = rhs`` (banded); return (x, diag(N^-1)).

    ``constraint=(g, c)`` imposes ``g . x = c`` exactly (Lagrange multiplier;
    two banded solves) and returns the constrained variance."""
    ab = _to_banded_upper(N)
    cb = scipy.linalg.cholesky_banded(ab, lower=False, check_finite=False)
    x = scipy.linalg.cho_solve_banded((cb, False), rhs, check_finite=False)
    var = banded_inverse_diagonal(cb) if want_diag else None
    if constraint is not None:
        g, c = constraint
        ng = scipy.linalg.cho_solve_banded((cb, False), g, check_finite=False)
        den = float(g @ ng)
        if den > 0:
            x = x - ng * (float(g @ x) - c) / den
            if var is not None:
                var = np.maximum(var - ng**2 / den, 0.0)
    return x, var


# ---------------------------------------------------------------------------
# separability
# ---------------------------------------------------------------------------
def separability(v_kms: np.ndarray, scale_kms: float, weights=None) -> float:
    """How well velocity shifts ``v`` separate rest-frame structure of width
    ``scale`` from fixed structure: ``1 - |<exp(i q v)>|^2`` averaged over
    spatial frequencies ``q`` in [0.5, 1.5] / ``scale`` (0: not at all; ~1:
    fully; ``1 - 1/N`` for N well-spread exposures). The band average keeps
    a chance phase alignment of a few exposures at one frequency from
    reading as a degeneracy."""
    v = np.asarray(v_kms, dtype=np.float64)
    w = np.ones_like(v) if weights is None else np.asarray(weights, dtype=np.float64)
    q = np.linspace(0.5, 1.5, 21) / scale_kms
    m = (np.exp(1j * np.outer(q, v)) @ w) / np.sum(w)
    return float(1.0 - np.mean(np.abs(m) ** 2))


def _separable_scale(v_kms, threshold, weights=None) -> float:
    scales = np.geomspace(1e-4, 1e4, 801)
    ok = [s for s in scales if separability(v_kms, s, weights) >= threshold]
    return float(max(ok)) if ok else 0.0


def check_separability(
    z_bary: np.ndarray,
    resolution_kms: float,
    pixel_kms: float,
    threshold: float = 0.5,
    scalings: Mapping[str, np.ndarray] | None = None,
    cos_threshold: float = 0.999,
    warn: bool = True,
) -> SeparabilityReport:
    """Can the barycentric spread separate the template from the observatory
    and detector frames at the requested ``resolution_kms``?

    ``z_bary``: one barycentric correction per independent exposure.
    ``scalings``: per-exposure scaling of each learned observatory term
    (iodine strength, airmass, water), to check that they are not
    proportional. Warns with :class:`TemplateDegeneracyWarning` when
    ``warn``.
    """
    v = np.asarray(z_bary, dtype=np.float64) * C_KMS
    sep = separability(v, resolution_kms)
    scale = _separable_scale(v, threshold)
    rng = float(np.ptp(v)) if v.size else 0.0
    det_sep = separability(v, pixel_kms)
    cos = 0.0
    names = list(scalings or {})
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a = np.asarray(scalings[names[i]], dtype=np.float64)
            b = np.asarray(scalings[names[j]], dtype=np.float64)
            den = np.linalg.norm(a) * np.linalg.norm(b)
            if den > 0:
                cos = max(cos, float(abs(a @ b) / den))
    degenerate = sep < threshold
    det_degenerate = det_sep < threshold or rng < pixel_kms
    obs_degenerate = cos > cos_threshold
    msgs = []
    if degenerate:
        msgs.append(
            f"barycentric spread {np.std(v):.3g} km/s (range {rng:.3g}) separates the template "
            f"from observatory-frame components only on scales below {scale:.3g} km/s, not at "
            f"the requested resolution {resolution_kms:.3g} km/s (separability {sep:.3f}): "
            "learned iodine/telluric corrections are unconstrained and errors of fixed "
            "observatory priors alias into the template"
        )
    if det_degenerate:
        msgs.append(
            f"barycentric range is {rng / pixel_kms:.3g} px (separability {det_sep:.3f} at one "
            "pixel): the template cannot be separated from detector-frame errors (pixel "
            "positions, response); supply the detector map as a calibration"
        )
    if obs_degenerate:
        msgs.append(
            f"per-exposure scalings of the learned observatory terms {names} are nearly "
            f"proportional (|cos| = {cos:.5f}): they separate only through their priors"
        )
    if warn:
        for msg in msgs:
            warnings.warn(msg, TemplateDegeneracyWarning, stacklevel=3)
    return SeparabilityReport(
        berv_std_kms=float(np.std(v)),
        berv_range_kms=rng,
        resolution_kms=float(resolution_kms),
        separability=sep,
        separable_scale_kms=scale,
        pixel_kms=float(pixel_kms),
        berv_range_px=rng / pixel_kms,
        detector_separability=det_sep,
        observatory_scaling_cos=cos,
        degenerate=degenerate,
        detector_degenerate=det_degenerate,
        observatory_degenerate=obs_degenerate,
        messages=tuple(msgs),
    )


# ---------------------------------------------------------------------------
# velocities
# ---------------------------------------------------------------------------
def combine_velocities(
    v: np.ndarray,
    sigma: np.ndarray,
    keys: Sequence,
    orders: Sequence,
    fit_offsets: bool = True,
    iterations: int = 500,
    tol: float = 1e-9,
):
    """Split per-block velocities into ``v_key + delta_order`` by weighted
    least squares, with the weighted mean of ``delta`` fixed at zero (the
    overall zero point belongs to the template, not to the data).

    Returns ({key: (v, sigma)}, {order: (delta, sigma)})."""
    v = np.asarray(v, dtype=np.float64)
    w = 1.0 / np.asarray(sigma, dtype=np.float64) ** 2
    ukeys = list(dict.fromkeys(keys))
    uord = list(dict.fromkeys(orders))
    kpos = {k: i for i, k in enumerate(ukeys)}
    opos = {o: i for i, o in enumerate(uord)}
    ki = np.array([kpos[k] for k in keys])
    oi = np.array([opos[o] for o in orders])
    wk = np.bincount(ki, w, len(ukeys))
    wo = np.bincount(oi, w, len(uord))
    d = np.zeros(len(uord))
    for _ in range(iterations if fit_offsets else 1):
        vk = np.bincount(ki, w * (v - d[oi]), len(ukeys)) / wk
        if not fit_offsets:
            break
        dn = np.bincount(oi, w * (v - vk[ki]), len(uord)) / wo
        dn -= np.sum(wo * dn) / np.sum(wo)
        done = np.max(np.abs(dn - d)) < tol
        d = dn
        if done:
            vk = np.bincount(ki, w * (v - d[oi]), len(ukeys)) / wk
            break
    vel = {k: (float(vk[i]), float(1 / np.sqrt(wk[i]))) for i, k in enumerate(ukeys)}
    off = {o: (float(d[i]), float(1 / np.sqrt(wo[i]))) for i, o in enumerate(uord)}
    return vel, off


# ---------------------------------------------------------------------------
# the solver
# ---------------------------------------------------------------------------
class TemplateSolver:
    """Alternating solver for the template, velocities and nuisances.

    Use :func:`infer_template`; this class holds the state and exposes the
    individual steps (and the ``joint_step`` hook) for experiments.
    """

    def __init__(
        self,
        blocks: Sequence[Block],
        prior: Mapping,
        config: TemplateConfig,
        star: str = "star",
        detector_prior: Mapping | None = None,
        cache_operators: bool = True,
    ) -> None:
        if not blocks:
            raise ValueError("no blocks")
        #: Keep every block's pixel operator between steps (fast, but a few MB
        #: per block at 1000-pixel blocks on a fine grid: NEID-sized problems
        #: need ``False``, which rebuilds them on demand).
        self.cache_operators = cache_operators
        self.blocks = list(blocks)
        self.config = config
        self.star = star
        self.mode = config.mode
        self.prior_sigma = (
            config.prior_sigma
            if config.prior_sigma is not None
            else (0.05 if self.mode == "modify" else 1.0)
        )
        self.orders = list(dict.fromkeys(b.order for b in self.blocks))
        self.keys = list(dict.fromkeys(b.key for b in self.blocks))
        self.grids: dict = {}
        for b in self.blocks:
            comp = b.model.factor(star)
            if not isinstance(comp, GriddedTemplate):
                raise TypeError(f"block star factor must be a GriddedTemplate, got {type(comp)}")
            g = self.grids.setdefault(b.order, comp.grid)
            if g != comp.grid:
                raise ValueError(f"order {b.order!r}: blocks disagree on the template grid")
        self.prior = {}
        for o in self.orders:
            p = np.asarray(prior[o], dtype=np.float64) if o in prior else None
            if p is None:
                if self.mode == "modify":
                    raise ValueError(f"modify mode needs a prior for order {o!r}")
                p = np.ones(self.grids[o].n)
            if p.shape != (self.grids[o].n,):
                raise ValueError(f"order {o!r}: prior has shape {p.shape}")
            self.prior[o] = p
        self.flux = {o: self.prior[o].copy() for o in self.orders}
        self.flux_sigma = {o: np.full(self.grids[o].n, self.prior_sigma) for o in self.orders}
        self.zero_point = {o: 0.0 for o in self.orders}
        self.zero_point_sigma = {o: np.inf for o in self.orders}
        self.params = [copy.deepcopy({c: dict(d) for c, d in b.start.items()}) for b in self.blocks]
        for p in self.params:
            for c in p:
                p[c] = {k: np.array(v, dtype=np.float64) for k, v in p[c].items()}
        # learned observatory terms: {order: {(comp, param): nodes}}
        self.learned: dict = {o: {} for o in self.orders}
        for b, p in zip(self.blocks, self.params, strict=True):
            for f in b.model.factors:
                if hasattr(f, "learned_terms") and f.name != star:
                    for name, grid, _ in f.learned_terms(p.get(f.name, {}), b.ctx):
                        init = p.get(f.name, {}).get(name, np.zeros(grid.n))
                        self.learned[b.order].setdefault((f.name, name), np.array(init, float))
        # detector maps per trace
        self.detector: dict = {}
        self.detector_prior: dict = {}
        for b, p in zip(self.blocks, self.params, strict=True):
            det = b.model.detector
            if det is None:
                continue
            start = (detector_prior or {}).get(b.trace) or p.get(det.name) or det.identity(det.npix)
            start = {k: np.array(v, dtype=np.float64) for k, v in start.items()}
            self.detector_prior.setdefault(b.trace, start)
            self.detector.setdefault(b.trace, copy.deepcopy(start))
        self.block_v = np.array([float(p[star]["v"][0]) for p in self.params])
        self.block_vsig = np.full(len(self.blocks), np.inf)
        self.velocities: dict = {}
        self.history: list = []
        self._ops: dict = {}
        #: Compute the template's own variance (selected inversion) at every
        #: template step; switch off to save time until the last one.
        self.want_sigma = True
        self._sync()

    # ----------------------------------------------------------- state sync
    def _sync(self) -> None:
        """Push the order-, trace- and key-level state into the block params."""
        for b, p in zip(self.blocks, self.params, strict=True):
            s = p.setdefault(self.star, {})
            s["flux"] = self.flux[b.order]
            s["zero_point"] = np.array([self.zero_point[b.order]])
            for (c, name), nodes in self.learned[b.order].items():
                p.setdefault(c, {})[name] = nodes
            if b.model.detector is not None:
                p[b.model.detector.name] = self.detector[b.trace]

    def _pixel_operator(self, i: int) -> sp.csr_matrix:
        """diag(R C) . P . K for block ``i`` (npix x fine grid), cached until
        the block's instrument parameters change (unless ``cache_operators``
        is False)."""
        if i in self._ops:
            return self._ops[i]
        b, p = self.blocks[i], self.params[i]
        op = block_pixel_operator(b.model, p, b.ctx, include_cti=False)
        if self.cache_operators:
            self._ops[i] = op
        return op

    @staticmethod
    def _weights(b: Block) -> np.ndarray:
        s = np.asarray(b.sigma, dtype=np.float64)
        return np.where(np.isfinite(s) & (s > 0), 1.0 / s**2, 0.0)

    # --------------------------------------------------------------- steps
    def nuisance_step(self, max_nfev: int = 200) -> dict:
        """Fit every block with the template fixed, then split the block
        velocities into per-key velocities and per-order offsets."""
        for i, (b, p) in enumerate(zip(self.blocks, self.params, strict=True)):
            fit = fit_block(
                b.model,
                b.data,
                b.sigma,
                b.ctx,
                p,
                exclude=b.exclude,
                max_nfev=max_nfev,
                solver="gn",
            )
            for c, d in fit.params.items():
                p[c].update({k: v for k, v in d.items() if (c, k) in _free(fit)})
            self.block_v[i] = float(fit.params[self.star]["v"][0])
            self.block_vsig[i] = float(fit.sigma(self.star, "v")[0])
        vel, off = combine_velocities(
            self.block_v,
            self.block_vsig,
            [b.key for b in self.blocks],
            [b.order for b in self.blocks],
            fit_offsets=self.config.fit_zero_points,
        )
        self.velocities = vel
        offsets = {o: d for o, (d, _) in off.items()}
        if self.config.fit_zero_points:
            for o, (d, s) in off.items():
                self.zero_point[o] += d
                self.zero_point_sigma[o] = s
        for b, p in zip(self.blocks, self.params, strict=True):
            p[self.star]["v"] = np.array([vel[b.key][0]])
        self.history.append(offsets)
        self._ops.clear()
        self._sync()
        return offsets

    def template_step(self) -> None:
        """Linear, regularized solve for every order's template nodes."""
        cfg = self.config
        for o in self.orders:
            g = self.grids[o]
            N = sp.csr_matrix((g.n, g.n))
            rhs = np.zeros(g.n)
            for i, (b, p) in enumerate(zip(self.blocks, self.params, strict=True)):
                if b.order != o:
                    continue
                m = b.model
                star = m.factor(self.star)
                M = self._pixel_operator(i)
                obs = m.fine_spectrum(p, b.ctx, skip=(self.star,))
                W = interpolation_matrix(g, star.rest_lnlam(p[self.star], m.grid.lnlam, b.ctx))
                A = M @ sp.diags(obs) @ W
                w = self._weights(b)
                Aw = A.T @ sp.diags(w)
                N = N + Aw @ A
                rhs += Aw @ (np.asarray(b.data, dtype=np.float64) - cti_offset(m, p, b.ctx))
            D = second_difference(g.n)
            R = sp.identity(g.n) / self.prior_sigma**2 + (D.T @ D) / cfg.smooth_sigma**2
            # Gauge: the update must not shift the template (a shift is the
            # zero point's job). The constraint is the shift the data would
            # measure between the new template and the reference (prior; in
            # infer mode the previous template), linearized:
            # (N_data g)' (s - s_ref) = 0 with g the reference's derivative.
            ref = self.prior[o] if self.mode == "modify" else self.flux[o]
            gvec = N @ np.gradient(ref)
            con = (gvec, float(gvec @ ref)) if np.any(gvec) else None
            x, var = solve_banded_spd(
                N + R, rhs + R @ self.prior[o], want_diag=self.want_sigma, constraint=con
            )
            self.flux[o] = x
            if var is not None:
                self.flux_sigma[o] = np.sqrt(var)
        self._sync()

    def observatory_step(self) -> None:
        """One Gauss-Newton step for the learned observatory corrections of
        every order, all terms jointly (they share the observed frame)."""
        cfg = self.config
        for o in self.orders:
            terms = list(self.learned[o])
            if not terms:
                continue
            sizes = []
            grids = {}
            for b, p in zip(self.blocks, self.params, strict=True):
                if b.order == o:
                    for f in b.model.factors:
                        if hasattr(f, "learned_terms") and f.name != self.star:
                            for name, grid, _ in f.learned_terms(p[f.name], b.ctx):
                                grids[(f.name, name)] = grid
            sizes = [grids[t].n for t in terms]
            off = np.concatenate([[0], np.cumsum(sizes)])
            ntot = int(off[-1])
            N = sp.csr_matrix((ntot, ntot))
            rhs = np.zeros(ntot)
            for i, (b, p) in enumerate(zip(self.blocks, self.params, strict=True)):
                if b.order != o:
                    continue
                m = b.model
                M = self._pixel_operator(i)
                fine = m.fine_spectrum(p, b.ctx)
                cols = []
                for t in terms:
                    f = m.factor(t[0])
                    scale = {n: s for n, _, s in f.learned_terms(p[f.name], b.ctx)}[t[1]]
                    Wt = interpolation_matrix(grids[t], m.grid.lnlam)
                    cols.append(-(M @ sp.diags(fine * scale) @ Wt))
                J = sp.hstack(cols).tocsr()
                r = np.asarray(b.data, dtype=np.float64) - m.evaluate(p, b.ctx)
                Jw = J.T @ sp.diags(self._weights(b))
                N = N + Jw @ J
                rhs += Jw @ r
            regs = []
            cur = np.concatenate([self.learned[o][t] for t in terms])
            for t in terms:
                n = grids[t].n
                D = second_difference(n)
                regs.append(
                    sp.identity(n) / cfg.observatory_prior_sigma**2
                    + (D.T @ D) / cfg.observatory_smooth_sigma**2
                )
            R = sp.block_diag(regs).tocsc()
            delta = scipy.sparse.linalg.spsolve((N + R).tocsc(), rhs - R @ cur)
            for t, a, z in zip(terms, off[:-1], off[1:], strict=True):
                self.learned[o][t] = self.learned[o][t] + delta[a:z]
        self._sync()

    def detector_step(self) -> None:
        """One Gauss-Newton step for each trace's detector map (edge offsets
        and response) under the strong prior of the configuration."""
        cfg = self.config
        h = 1e-4
        for trace, det in self.detector.items():
            npix = det["response"].size
            n = 2 * npix + 1
            N = sp.csr_matrix((n, n))
            rhs = np.zeros(n)
            for b, p in zip(self.blocks, self.params, strict=True):
                if b.trace != trace:
                    continue
                m = b.model
                name = m.detector.name
                f0 = m.evaluate(p, b.ctx)
                rows, cols, vals = [], [], []
                k = np.arange(npix)
                for par in (0, 1):
                    dp = copy.copy(p)
                    up = det["dx"].copy()
                    up[par::2] += h
                    dn = det["dx"].copy()
                    dn[par::2] -= h
                    dp[name] = {"dx": up, "response": det["response"]}
                    fu = m.evaluate(dp, b.ctx)
                    dp[name] = {"dx": dn, "response": det["response"]}
                    fd = m.evaluate(dp, b.ctx)
                    e = np.where(k % 2 == par, k, k + 1)
                    rows.append(k)
                    cols.append(e)
                    vals.append((fu - fd) / (2 * h))
                rows.append(k)
                cols.append(npix + 1 + k)
                vals.append(f0 / det["response"])
                J = sp.csr_matrix(
                    (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                    shape=(npix, n),
                )
                r = np.asarray(b.data, dtype=np.float64) - f0
                Jw = J.T @ sp.diags(self._weights(b))
                N = N + Jw @ J
                rhs += Jw @ r
            prior = self.detector_prior[trace]
            lam = np.concatenate(
                [
                    np.full(npix + 1, 1 / cfg.detector_dx_sigma_px**2),
                    np.full(npix, 1 / cfg.detector_response_sigma**2),
                ]
            )
            cur = np.concatenate([det["dx"] - prior["dx"], det["response"] - prior["response"]])
            delta = scipy.sparse.linalg.spsolve((N + sp.diags(lam)).tocsc(), rhs - lam * cur)
            self.detector[trace] = {
                "dx": det["dx"] + delta[: npix + 1],
                "response": det["response"] + delta[npix + 1 :],
            }
        self._ops.clear()
        self._sync()

    def joint_step(self, local: Sequence[tuple[str, str]] | None = None) -> dict:
        """Joint Gauss-Newton step for every order's template nodes AND the
        block velocities (``strategy="joint"``), replacing
        :meth:`template_step`.

        The alternation converges slowly along the template-velocity valley
        (a template change that one set of velocities can absorb). Here, per
        order, the normal equations of (template s, block velocities v) are
        solved together:

            [N + R   B] [s ]   [A' W d + R p]
            [B'      C] [dv] = [J' W d      ]

        with A the block's template operator, J its velocity column with the
        block's other ``local`` parameters (wavelength, iodine strength,
        continuum) profiled out (J - J_o (J_o' W J_o)^-1 J_o' W J), B = A' W J,
        C = J' W J. The banded N is solved for all velocity columns at once
        and the small Schur system for dv is dense (one row per block), so the
        cost stays close to a template step. The template shift gauge of
        :meth:`template_step` applies (as an exact linear constraint). The
        local parameters are refitted by the next nuisance step; the coupling
        of the template to them (not to the velocity) stays alternating.
        Returns per-order velocity-step statistics.
        """
        from specfast.doppler.fastfit import model_and_jacobian

        cfg = self.config
        stats = {}
        for o in self.orders:
            g = self.grids[o]
            N = sp.csr_matrix((g.n, g.n))
            rhs = np.zeros(g.n)
            idx, Bcols, C, rv = [], [], [], []
            for i, (b, p) in enumerate(zip(self.blocks, self.params, strict=True)):
                if b.order != o:
                    continue
                m = b.model
                star = m.factor(self.star)
                M = self._pixel_operator(i)
                obs = m.fine_spectrum(p, b.ctx, skip=(self.star,))
                sp_ = p[self.star]
                W = interpolation_matrix(g, star.rest_lnlam(sp_, m.grid.lnlam, b.ctx))
                A = M @ sp.diags(obs) @ W
                w = self._weights(b)
                d = np.asarray(b.data, dtype=np.float64) - cti_offset(m, p, b.ctx)
                Aw = A.T @ sp.diags(w)
                N = N + Aw @ A
                rhs += Aw @ d
                # velocity column at the current template, other locals profiled
                h = 1.0
                v0 = float(sp_["v"][0])
                fp = star.evaluate({**sp_, "v": np.array([v0 + h])}, m.grid.lnlam, b.ctx)
                fm = star.evaluate({**sp_, "v": np.array([v0 - h])}, m.grid.lnlam, b.ctx)
                jv = M @ (obs * (fp - fm) / (2 * h))
                if local is None:
                    lay = ParameterLayout.free(m, exclude=b.exclude)
                    cand = [(c, n) for c, n, _ in lay.entries]
                else:
                    cand = list(local)
                others = [lp for lp in cand if lp != (self.star, "v") and lp[0] in p]
                if others:
                    _, Jo, _, _ = model_and_jacobian(m, p, b.ctx, others)
                    Jow = Jo * w[:, None]
                    try:
                        coef = np.linalg.solve(Jow.T @ Jo, Jow.T @ jv)
                        jv = jv - Jo @ coef
                    except np.linalg.LinAlgError:
                        pass
                c = float(jv @ (w * jv))
                if not np.isfinite(c) or c <= 0:
                    continue
                idx.append(i)
                Bcols.append(Aw @ jv)
                C.append(c)
                rv.append(float(jv @ (w * d)))
            D = second_difference(g.n)
            R = sp.identity(g.n) / self.prior_sigma**2 + (D.T @ D) / cfg.smooth_sigma**2
            ref = self.prior[o] if self.mode == "modify" else self.flux[o]
            gvec = N @ np.gradient(ref)
            con = (gvec, float(gvec @ ref)) if np.any(gvec) else None
            Ntot = N + R
            rs = rhs + R @ self.prior[o]
            ab = _to_banded_upper(Ntot)
            cb = scipy.linalg.cholesky_banded(ab, lower=False, check_finite=False)

            def ninv(x, homogeneous):
                y = scipy.linalg.cho_solve_banded((cb, False), x, check_finite=False)
                if con is not None:
                    gg, cc = con
                    ng = scipy.linalg.cho_solve_banded((cb, False), gg, check_finite=False)
                    den = float(gg @ ng)
                    target = 0.0 if homogeneous else cc
                    if den > 0:
                        corr = (gg @ y - target) / den
                        y = y - np.outer(ng, corr) if y.ndim == 2 else y - ng * corr
                return y

            s0 = ninv(rs, homogeneous=False)
            if idx:
                B = np.stack(Bcols, axis=1)
                NB = ninv(B, homogeneous=True)
                S = np.diag(C) - B.T @ NB
                dv = np.linalg.solve(S, np.array(rv) - B.T @ s0)
                snew = s0 - NB @ dv
                for j, i in enumerate(idx):
                    p = self.params[i]
                    p[self.star]["v"] = np.array([float(p[self.star]["v"][0]) + dv[j]])
                stats[o] = dict(
                    dv_rms=float(np.sqrt(np.mean(dv**2))),
                    dv_max=float(np.max(np.abs(dv))),
                    nblocks=len(idx),
                )
            else:
                snew = s0
            self.flux[o] = snew
            if self.want_sigma:
                self.flux_sigma[o] = np.sqrt(np.clip(banded_inverse_diagonal(cb), 0, None))
        self._ops.clear()
        self._sync()
        return stats

    # ------------------------------------------------------------ helpers
    def lsf_sigma_kms(self) -> float:
        b, p = self.blocks[0], self.params[0]
        return kernel_sigma_mps(b.model.kernel(p, b.ctx), b.model.grid.step_mps) / 1e3

    def pixel_kms(self) -> float:
        out = []
        for b, p in zip(self.blocks, self.params, strict=True):
            out.append(np.median(np.diff(b.model.ln_edges(p, b.ctx))) * C_KMS)
        return float(np.median(out))

    def separability_report(self, warn: bool = True) -> SeparabilityReport:
        zb = {}
        scal: dict = {}
        for b, p in zip(self.blocks, self.params, strict=True):
            zb.setdefault(b.key, b.ctx.z_bary)
            for f in b.model.factors:
                if hasattr(f, "learned_terms") and f.name != self.star:
                    for name, _, s in f.learned_terms(p[f.name], b.ctx):
                        scal.setdefault(f"{f.name}.{name}", {}).setdefault(b.key, s)
        keys = list(zb)
        scalings = {n: np.array([d.get(k, 0.0) for k in keys]) for n, d in scal.items()}
        res = self.config.resolution_kms or 2.3548 * self.lsf_sigma_kms()
        return check_separability(
            np.array([zb[k] for k in keys]),
            res,
            self.pixel_kms(),
            threshold=self.config.min_separability,
            scalings=scalings,
            warn=warn,
        )

    def result(self, report, iterations, converged) -> TemplateResult:
        temps = {
            o: OrderTemplate(
                grid=self.grids[o],
                flux=self.flux[o].copy(),
                sigma=self.flux_sigma[o].copy(),
                prior=self.prior[o].copy(),
                zero_point=self.zero_point[o],
                zero_point_sigma=self.zero_point_sigma[o],
                observatory={t: v.copy() for t, v in self.learned[o].items()},
            )
            for o in self.orders
        }
        return TemplateResult(
            templates=temps,
            velocities=dict(self.velocities),
            block_params=self.params,
            block_velocity=self.block_v.copy(),
            block_velocity_sigma=self.block_vsig.copy(),
            order_offsets_history=self.history,
            detector=copy.deepcopy(self.detector),
            separability=report,
            iterations=iterations,
            converged=converged,
            mode=self.mode,
        )


def _free(fit) -> set:
    return {(c, p) for c, p, _ in fit.layout.entries}


def infer_template(
    blocks: Sequence[Block],
    prior: Mapping,
    config: TemplateConfig | None = None,
    star: str = "star",
    detector_prior: Mapping | None = None,
    callback: Callable[[TemplateSolver, int], None] | None = None,
    cache_operators: bool = True,
) -> TemplateResult:
    """Infer the stellar template (per order), velocities and nuisances.

    ``blocks``: the spectra with their models (each model's star factor a
    :class:`~specfast.doppler.library.GriddedTemplate` named ``star``; the
    starting parameters in ``Block.start``). ``prior``: {order: node values}
    (``modify`` mode: required; ``infer`` mode: optional, flat otherwise).
    ``detector_prior``: {trace: {"dx", "response"}} calibration maps (else
    the blocks' starting parameters, else a perfect detector).
    ``cache_operators``: see :class:`TemplateSolver` (False for large
    problems: memory instead of speed).

    Checks first whether the barycentric spread can separate the template
    from the observatory and detector frames (:func:`check_separability`)
    and warns if not; the report is in the result.
    """
    cfg = config or TemplateConfig()
    solver = TemplateSolver(
        blocks,
        prior,
        cfg,
        star=star,
        detector_prior=detector_prior,
        cache_operators=cache_operators,
    )
    report = solver.separability_report(warn=True)
    learn_obs = cfg.learn_observatory and any(solver.learned[o] for o in solver.orders)

    def update_rest():
        if cfg.strategy == "joint":
            solver.joint_step()
        else:
            solver.template_step()
        if learn_obs:
            solver.observatory_step()
        if cfg.fit_detector and solver.detector:
            solver.detector_step()

    if cfg.mode == "infer":
        update_rest()
    converged = False
    it = 0
    previous = None
    for it in range(1, cfg.iterations + 1):
        offsets = solver.nuisance_step()
        if callback is not None:
            callback(solver, it)
        v = np.array([solver.velocities[k][0] for k in solver.keys])
        if previous is not None:
            dv = np.max(np.abs(v - previous))
            doff = max((abs(d) for d in offsets.values()), default=0.0)
            if max(dv, doff) < cfg.tol_mps:
                converged = True
                break
        previous = v
        if it < cfg.iterations:
            update_rest()
    return solver.result(report, it, converged)

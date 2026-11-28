"""Emission-line wavelength calibration: a stable model shared by fibres.

DESIGN.md, "Wavelength" (production form): a static solution with a few
low-order perturbation terms shared by all orders and fibres, per exposure,
instead of an independent high-order polynomial solved from scratch every
day. First used for NRES (simultaneous ThAr fibre, two science fibres; see
:mod:`specfast.converters.nres`), but nothing here is NRES-specific.

Pieces
------
1. :func:`fit_lines`: pixel-integrated Gaussian plus linear background,
   fitted to many emission lines at once (vectorised Gauss-Newton) in an
   extracted 1-D spectrum. Returns centroids with formal errors.
2. :func:`identify_lines`: reference wavelengths -> predicted pixels from a
   starting wavelength array (e.g. the upstream pipeline's), keeping lines
   with no other catalogue line nearby.
3. :class:`StableModel` (:func:`fit_stable_model`): for one instrument unit
   and era, every measured line position is modelled as

       x[line, fibre, exposure] = r[line, fibre] + D_e(r, m),

   with ``r`` a static reference position per (line, order, fibre), learned from
   all exposures, and ``D_e`` a low-order 2-D polynomial in (pixel, order)
   per exposure, *shared by every fibre lit in that exposure* (the detector
   image moves as a whole). Lines whose positions scatter across exposures
   more than their errors allow are pruned (a stable-line list). The
   absolute scale is fitted once: ``m * lambda = P(x, m)`` on the
   reference fibre's static positions (a weighted, clipped Legendre fit of
   the grating-equation product), and each other fibre is the reference
   fibre displaced by a smooth static offset ``S_f(x, m)``:

       lambda_f(x, m) = P(x - S_f(x, m) - D_e(x, m), m) / m.

   So the two science fibres share one dispersion law and differ only by a
   measured low-order geometric offset.
4. :func:`fit_drift`: ``D_e`` for any frame from the lines of one fibre
   (e.g. the simultaneous-reference fibre of a science exposure), against
   the static reference positions.

Units: pixels along the dispersion (0-based extracted column), wavelengths
in Angstrom (vacuum, as the line list), orders are physical echelle orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.polynomial import legendre as L
from scipy.special import erf

SQRT2 = np.sqrt(2.0)
SQRT2PI = np.sqrt(2.0 * np.pi)


# ---------------------------------------------------------------------------
# line fitting
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LineFits:
    """Gaussian fits to a batch of lines (one entry per input line)."""

    x0: np.ndarray  #: centroid [px]
    x0_err: np.ndarray  #: formal 1-sigma [px] (scaled by sqrt(chi2r) when > 1)
    sigma: np.ndarray  #: Gaussian sigma [px]
    amp: np.ndarray  #: integrated line flux
    amp_err: np.ndarray
    chi2r: np.ndarray
    ok: np.ndarray  #: bool, converged and sane


def _gauss_pix(x, x0, s):
    """Pixel-integrated unit Gaussian and its derivatives wrt x0, s."""
    up = (x + 0.5 - x0) / s
    um = (x - 0.5 - x0) / s
    g = 0.5 * (erf(up / SQRT2) - erf(um / SQRT2))
    pp = np.exp(-0.5 * up**2) / SQRT2PI
    pm = np.exp(-0.5 * um**2) / SQRT2PI
    dx0 = -(pp - pm) / s
    ds = -(pp * up - pm * um) / s
    return g, dx0, ds


def fit_lines(
    flux: np.ndarray,
    sigma: np.ndarray,
    x_guess: np.ndarray,
    half_width: int = 4,
    sigma_guess: float = 1.2,
    sigma_range: tuple[float, float] = (0.4, 3.5),
    max_shift: float = 1.5,
    n_iter: int = 12,
) -> LineFits:
    """Fit lines in one 1-D spectrum at the guessed pixel positions.

    ``flux``, ``sigma``: the spectrum and its 1-sigma per pixel (``inf`` or
    non-finite = masked). ``x_guess``: guessed centroids. Each line gets a
    window of ``2 half_width + 1`` pixels centred on the nearest pixel.
    Model: ``A * G(x; x0, s) + b0 + b1 (x - xc)``, G a unit Gaussian
    integrated over each pixel.
    """
    flux = np.asarray(flux, float)
    sig = np.asarray(sigma, float)
    xg = np.asarray(x_guess, float)
    n = flux.size
    nl = xg.size
    off = np.arange(-half_width, half_width + 1)
    xc = np.rint(xg).astype(int)
    pix = xc[:, None] + off[None, :]
    inside = (pix >= 0) & (pix < n)
    pixc = np.clip(pix, 0, n - 1)
    y = flux[pixc]
    s = sig[pixc]
    w = np.where(
        inside & np.isfinite(s) & (s > 0) & np.isfinite(y), 1.0 / np.where(s > 0, s, 1) ** 2, 0.0
    )
    y = np.where(w > 0, y, 0.0)
    xr = (pix - xc[:, None]).astype(float)
    # starting values
    edge = np.concatenate([y[:, :2], y[:, -2:]], axis=1)
    b0 = np.median(edge, axis=1)
    b1 = np.zeros(nl)
    x0 = xg - xc
    sg = np.full(nl, sigma_guess)
    amp = np.clip(np.sum(y - b0[:, None], axis=1), 1e-12, None)
    p = np.stack([amp, x0, sg, b0, b1], axis=1)
    ok = np.sum(w > 0, axis=1) >= 2 * half_width - 1
    eye = np.eye(5) * 1e-12
    for _ in range(n_iter):
        g, dg0, dgs = _gauss_pix(xr, p[:, 1:2], p[:, 2:3])
        model = p[:, 0:1] * g + p[:, 3:4] + p[:, 4:5] * xr
        r = y - model
        J = np.stack(
            [g, p[:, 0:1] * dg0, p[:, 0:1] * dgs, np.ones_like(g), xr],
            axis=2,
        )
        JW = J * w[:, :, None]
        N = np.einsum("lki,lkj->lij", JW, J) + eye
        b = np.einsum("lki,lk->li", JW, r)
        try:
            dp = np.linalg.solve(N, b[:, :, None])[:, :, 0]
        except np.linalg.LinAlgError:
            dp = np.zeros_like(p)
            for i in range(nl):
                try:
                    dp[i] = np.linalg.solve(N[i], b[i])
                except np.linalg.LinAlgError:
                    ok[i] = False
        dp[:, 1] = np.clip(dp[:, 1], -0.5, 0.5)
        dp[:, 2] = np.clip(dp[:, 2], -0.3, 0.3)
        p = p + dp
        p[:, 2] = np.clip(p[:, 2], sigma_range[0] * 0.5, sigma_range[1] * 1.5)
    g, dg0, dgs = _gauss_pix(xr, p[:, 1:2], p[:, 2:3])
    model = p[:, 0:1] * g + p[:, 3:4] + p[:, 4:5] * xr
    r = y - model
    J = np.stack([g, p[:, 0:1] * dg0, p[:, 0:1] * dgs, np.ones_like(g), xr], axis=2)
    JW = J * w[:, :, None]
    N = np.einsum("lki,lkj->lij", JW, J) + eye
    dof = np.maximum(np.sum(w > 0, axis=1) - 5, 1)
    chi2r = np.sum(r**2 * w, axis=1) / dof
    cov = np.full((nl, 5, 5), np.nan)
    good_n = np.isfinite(N).all(axis=(1, 2))
    try:
        cov[good_n] = np.linalg.inv(N[good_n])
    except np.linalg.LinAlgError:
        for i in np.where(good_n)[0]:
            try:
                cov[i] = np.linalg.inv(N[i])
            except np.linalg.LinAlgError:
                pass
    scale = np.sqrt(np.maximum(chi2r, 1.0))
    x0_err = np.sqrt(np.abs(cov[:, 1, 1])) * scale
    amp_err = np.sqrt(np.abs(cov[:, 0, 0])) * scale
    x0 = p[:, 1] + xc
    ok &= np.isfinite(x0) & np.isfinite(x0_err) & (x0_err > 0)
    ok &= (p[:, 2] >= sigma_range[0]) & (p[:, 2] <= sigma_range[1])
    ok &= np.abs(x0 - xg) <= max_shift
    ok &= p[:, 0] > 5 * amp_err
    return LineFits(x0, x0_err, p[:, 2], p[:, 0], amp_err, chi2r, ok)


def identify_lines(
    wave: np.ndarray,
    line_wavelengths: np.ndarray,
    min_separation_px: float = 5.0,
    edge_px: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    """Catalogue lines falling in one order, with predicted pixels.

    ``wave``: a starting wavelength per pixel (monotonic over its non-zero,
    finite part). Returns (indices into ``line_wavelengths``, predicted
    pixel). Lines with another catalogue line closer than
    ``min_separation_px`` are dropped (blends).
    """
    wave = np.asarray(wave, float)
    x = np.arange(wave.size, dtype=float)
    good = np.isfinite(wave) & (wave > 0)
    if good.sum() < 10:
        return np.zeros(0, int), np.zeros(0)
    xg, wg = x[good], wave[good]
    if wg[-1] < wg[0]:
        xg, wg = xg[::-1], wg[::-1]
    lines = np.asarray(line_wavelengths, float)
    sel = np.where((lines > wg[0]) & (lines < wg[-1]))[0]
    if sel.size == 0:
        return np.zeros(0, int), np.zeros(0)
    xp = np.interp(lines[sel], wg, xg)
    # isolation in pixel space against all catalogue lines in range
    allin = np.where((lines > wg[0] - 5) & (lines < wg[-1] + 5))[0]
    xall = np.interp(lines[allin], wg, xg, left=-1e9, right=1e9)
    keep = np.ones(sel.size, bool)
    for k, xi in enumerate(xp):
        d = np.abs(xall - xi)
        keep[k] = np.sum(d < min_separation_px) == 1
    keep &= (xp > xg.min() + edge_px) & (xp < xg.max() - edge_px)
    return sel[keep], xp[keep]


# ---------------------------------------------------------------------------
# bases
# ---------------------------------------------------------------------------
#: Named low-order (pixel, order) bases for the per-exposure perturbation.
#: Each term is (degree in scaled pixel, degree in scaled order).
DRIFT_BASES = {
    "shift": ((0, 0),),
    "linear": ((0, 0), (1, 0), (0, 1)),
    "bilinear": ((0, 0), (1, 0), (0, 1), (1, 1)),
    "quadratic": ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2)),
}


@dataclass(frozen=True)
class Scaling:
    """Maps pixel and order to [-1, 1]."""

    x_min: float
    x_max: float
    m_min: float
    m_max: float

    def t(self, x):
        return 2.0 * (np.asarray(x, float) - self.x_min) / (self.x_max - self.x_min) - 1.0

    def u(self, m):
        return 2.0 * (np.asarray(m, float) - self.m_min) / (self.m_max - self.m_min) - 1.0


def basis(terms, t, u) -> np.ndarray:
    """Legendre product basis, shape (len(t), len(terms))."""
    t = np.asarray(t, float)
    u = np.asarray(u, float)
    cols = []
    for i, j in terms:
        ci = np.zeros(i + 1)
        ci[i] = 1
        cj = np.zeros(j + 1)
        cj[j] = 1
        cols.append(L.legval(t, ci) * L.legval(u, cj))
    return np.stack(cols, axis=1) if cols else np.zeros((t.size, 0))


def grid_terms(deg_x: int, deg_m: int) -> tuple[tuple[int, int], ...]:
    return tuple((i, j) for i in range(deg_x + 1) for j in range(deg_m + 1))


# ---------------------------------------------------------------------------
# the stable model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LineMeasurements:
    """Long-format line positions: one row per (line, fibre, exposure)."""

    line: np.ndarray  #: int, index into the catalogue
    fibre: np.ndarray  #: int
    exposure: np.ndarray  #: int, 0..n_exposures-1
    order: np.ndarray  #: physical echelle order
    x: np.ndarray  #: measured centroid [px]
    x_err: np.ndarray  #: 1-sigma [px]

    def subset(self, sel):
        return LineMeasurements(
            *(np.asarray(getattr(self, f))[sel] for f in self.__dataclass_fields__)
        )


@dataclass
class StableModel:
    """Static reference + shared low-order per-exposure perturbations."""

    scaling: Scaling
    drift_terms: tuple
    ref_fibre: int
    #: {(line, order, fibre): (r, r_err)} static reference positions.
    reference: dict
    #: per exposure: drift coefficients (n_exp, n_terms) and their errors.
    drift: np.ndarray
    drift_err: np.ndarray
    #: absolute scale m*lambda = P(x, m): Legendre coefficients on grid_terms.
    disp_terms: tuple
    disp_coeffs: np.ndarray
    #: per fibre (other than ref_fibre): static offset S_f(x, m) [px].
    offset_terms: tuple
    offsets: dict
    #: diagnostics
    rms_px: float = np.nan
    disp_rms_mps: float = np.nan
    n_lines: int = 0
    pruned_lines: int = 0
    per_exposure_rms_px: np.ndarray = field(default_factory=lambda: np.zeros(0))
    lines_used: np.ndarray = field(default_factory=lambda: np.zeros(0, int))
    #: per fibre: {order: static constant [px]} added to S_f (when fitted)
    order_offsets: dict = field(default_factory=dict)

    # -- evaluation ---------------------------------------------------------
    def drift_px(self, coeffs, x, m):
        return basis(self.drift_terms, self.scaling.t(x), self.scaling.u(m)) @ np.asarray(coeffs)

    def offset_px(self, fibre, x, m):
        if fibre == self.ref_fibre or fibre not in self.offsets:
            return np.zeros(np.broadcast(np.asarray(x), np.asarray(m)).shape)
        x, m = np.broadcast_arrays(np.asarray(x, float), np.asarray(m, float))
        s = basis(self.offset_terms, self.scaling.t(x), self.scaling.u(m)) @ self.offsets[fibre]
        po = self.order_offsets.get(fibre)
        if po:
            s = s + np.array([po.get(int(round(mm)), 0.0) for mm in m.ravel()]).reshape(m.shape)
        return s

    def m_lambda(self, x, m):
        return basis(self.disp_terms, self.scaling.t(x), self.scaling.u(m)) @ self.disp_coeffs

    def wavelength(self, fibre, m, x=None, drift_coeffs=None):
        """Vacuum wavelength [A] of extracted pixels ``x`` of (fibre, order m).

        ``drift_coeffs``: the exposure's perturbation (None = the static
        reference, i.e. the mean exposure).
        """
        x = (
            np.arange(int(self.scaling.x_max) + 1, dtype=float)
            if x is None
            else np.asarray(x, float)
        )
        mm = np.full(x.shape, float(m))
        xs = x - self.offset_px(fibre, x, mm)
        if drift_coeffs is not None:
            xs = xs - self.drift_px(drift_coeffs, x, mm)
        return self.m_lambda(xs, mm) / mm


def _wls(A, y, w):
    sw = np.sqrt(w)
    coef, *_ = np.linalg.lstsq(A * sw[:, None], y * sw, rcond=None)
    return coef


def fit_stable_model(
    meas: LineMeasurements,
    line_wavelengths: np.ndarray,
    scaling: Scaling,
    ref_fibre: int = 1,
    drift: str = "bilinear",
    disp_deg: tuple[int, int] = (9, 7),
    offset_deg: tuple[int, int] = (3, 3),
    offset_order_constants: bool = True,
    err_floor_px: float = 0.003,
    min_frac: float = 0.5,
    clip: float = 5.0,
    line_chi2_max: float = 4.0,
    n_iter: int = 8,
) -> StableModel:
    """Fit the static reference, per-exposure drifts and absolute scale.

    ``meas``: line positions from many exposures of one unit and era.
    A (line, order, fibre) is kept if measured in at least ``min_frac`` of the
    exposures where that fibre was lit; measurements beyond ``clip`` robust
    sigma are rejected; then lines whose reduced chi2 about their reference
    exceeds ``line_chi2_max`` are pruned.
    """
    terms = DRIFT_BASES[drift]
    nexp = int(meas.exposure.max()) + 1
    key = (meas.line.astype(np.int64) * 256 + meas.order.astype(np.int64)) * 16 + meas.fibre.astype(
        np.int64
    )
    # coverage cut
    lit = {f: len(np.unique(meas.exposure[meas.fibre == f])) for f in np.unique(meas.fibre)}
    ukey, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    kf = (ukey % 16).astype(int)
    need = np.array([min_frac * lit[f] for f in kf])
    keepk = cnt >= np.maximum(need, 2)
    use = keepk[inv]
    err2 = meas.x_err**2 + err_floor_px**2
    good = use.copy()
    nk = ukey.size
    C = np.zeros((nexp, len(terms)))
    t_meas = scaling.t(meas.x)
    u_meas = scaling.u(meas.order)
    B = basis(terms, t_meas, u_meas)
    r = np.zeros(nk)
    pruned = np.zeros(nk, bool)
    for it in range(n_iter):
        w = np.where(good, 1.0 / err2, 0.0)
        d = np.einsum("ij,ij->i", B, C[meas.exposure])
        num = np.bincount(inv, w * (meas.x - d), minlength=nk)
        den = np.bincount(inv, w, minlength=nk)
        r = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
        # per-exposure drift
        res0 = meas.x - r[inv]
        for e in range(nexp):
            s = (meas.exposure == e) & good & np.isfinite(res0)
            if s.sum() > 3 * len(terms):
                C[e] = _wls(B[s], res0[s], w[s])
            else:
                C[e] = np.nan
        C[~np.isfinite(C).all(axis=1)] = 0.0
        # gauge: mean drift over exposures = 0 (absorbed into r)
        cbar = C.mean(axis=0)
        C -= cbar
        # residuals and clipping
        d = np.einsum("ij,ij->i", B, C[meas.exposure])
        res = meas.x - d - r[inv]
        z = res / np.sqrt(err2)
        zg = z[good & np.isfinite(z)]
        rs = 1.4826 * np.median(np.abs(zg - np.median(zg))) if zg.size else 1.0
        good = use & np.isfinite(z) & (np.abs(z) < clip * max(rs, 1.0)) & ~pruned[inv]
        if it >= 2:
            c2 = np.bincount(inv, np.where(good, z**2, 0), minlength=nk)
            nn = np.bincount(inv, good.astype(float), minlength=nk)
            c2r = np.where(nn > 1, c2 / np.maximum(nn - 1, 1), 0)
            med = np.median(c2r[nn > 1]) if np.any(nn > 1) else 1.0
            pruned |= (c2r > line_chi2_max * max(med, 1.0)) & (nn > 1)
            good &= ~pruned[inv]
    # drift errors
    Cerr = np.zeros_like(C)
    w = np.where(good, 1.0 / err2, 0.0)
    per_rms = np.zeros(nexp)
    d = np.einsum("ij,ij->i", B, C[meas.exposure])
    res = meas.x - d - r[inv]
    for e in range(nexp):
        s = (meas.exposure == e) & good
        if s.sum() > len(terms):
            N = (B[s] * w[s, None]).T @ B[s]
            chi = np.sum(res[s] ** 2 * w[s]) / max(s.sum() - len(terms), 1)
            try:
                Cerr[e] = np.sqrt(np.diag(np.linalg.inv(N)) * max(chi, 1.0))
            except np.linalg.LinAlgError:
                Cerr[e] = np.nan
            per_rms[e] = np.sqrt(np.mean(res[s] ** 2))
    nn = np.bincount(inv, good.astype(float), minlength=nk)
    rerr = np.where(
        nn > 0, 1.0 / np.sqrt(np.maximum(np.bincount(inv, w, minlength=nk), 1e-30)), np.nan
    )
    reference = {}
    for k in range(nk):
        if nn[k] >= 2 and np.isfinite(r[k]):
            lo, f = divmod(int(ukey[k]), 16)
            ln, o = divmod(lo, 256)
            reference[(ln, o, f)] = (float(r[k]), float(rerr[k]))
    model = StableModel(
        scaling=scaling,
        drift_terms=terms,
        ref_fibre=ref_fibre,
        reference=reference,
        drift=C,
        drift_err=Cerr,
        disp_terms=grid_terms(*disp_deg),
        disp_coeffs=np.zeros(len(grid_terms(*disp_deg))),
        offset_terms=grid_terms(*offset_deg),
        offsets={},
        rms_px=float(np.sqrt(np.mean(res[good] ** 2))) if good.any() else np.nan,
        n_lines=int(np.sum(nn >= 2)),
        pruned_lines=int(pruned.sum()),
        per_exposure_rms_px=per_rms,
    )
    _fit_absolute(
        model,
        np.asarray(line_wavelengths, float),
        clip=clip,
        order_constants=offset_order_constants,
    )
    return model


def _fit_absolute(
    model: StableModel,
    line_wavelengths,
    clip=5.0,
    n_iter=6,
    order_constants=True,
    min_lines_per_order=5,
):
    """m*lambda = P(r, m) on the reference fibre; S_f for the other fibres."""
    ref = model.reference
    rows = [(ln, v[0], v[1], o) for (ln, o, f), v in ref.items() if f == model.ref_fibre]
    if len(rows) < 2 * len(model.disp_terms):
        raise ValueError("too few reference-fibre lines for the dispersion fit")
    ln, x, xe, m = (np.array(c) for c in zip(*rows, strict=True))
    ln = ln.astype(int)
    lam = line_wavelengths[ln]
    sc = model.scaling
    A = basis(model.disp_terms, sc.t(x), sc.u(m))
    y = m * lam
    # weight: position error converted to m*lambda via the local dispersion
    good = np.ones(len(y), bool)
    coef = None
    for _ in range(n_iter):
        coef = _wls(A[good], y[good], np.ones(good.sum()))
        if _ == 0:
            # local slope d(m lambda)/dx for weights
            dA = basis(model.disp_terms, sc.t(x + 0.5), sc.u(m)) - basis(
                model.disp_terms, sc.t(x - 0.5), sc.u(m)
            )
            slope = np.abs(dA @ coef)
            w = 1.0 / ((slope * xe) ** 2 + (slope * 0.003) ** 2)
        coef = _wls(A[good], y[good], w[good])
        res_v = (y - A @ coef) / y * 299_792_458.0
        rs = 1.4826 * np.median(np.abs(res_v[good] - np.median(res_v[good])))
        good = np.abs(res_v) < clip * rs
    model.disp_coeffs = coef
    model.disp_rms_mps = float(np.sqrt(np.mean(res_v[good] ** 2)))
    model.lines_used = ln[good]
    # fibre offsets: same line in fibre f and the reference fibre
    rf = model.ref_fibre
    for f in sorted({f for (_, _, f) in ref if f != rf}):
        pairs = [
            (ref[(ln_, o, f)][0], ref[(ln_, o, rf)][0], o, ref[(ln_, o, f)][1])
            for (ln_, o, ff) in ref
            if ff == f and (ln_, o, rf) in ref
        ]
        if len(pairs) < 3 * len(model.offset_terms):
            continue
        xf, x1, mf, ef = (np.array(c) for c in zip(*pairs, strict=True))
        A = basis(model.offset_terms, sc.t(xf), sc.u(mf))
        dy = xf - x1
        g = np.ones(dy.size, bool)
        for _ in range(n_iter):
            c = _wls(A[g], dy[g], 1.0 / (ef[g] ** 2 + 0.003**2))
            rr = dy - A @ c
            rs = 1.4826 * np.median(np.abs(rr[g] - np.median(rr[g])))
            g = np.abs(rr) < clip * max(rs, 1e-4)
        model.offsets[f] = c
        if order_constants:
            po = {}
            for o in np.unique(mf):
                s_ = g & (mf == o)
                if s_.sum() >= min_lines_per_order:
                    w_ = 1.0 / (ef[s_] ** 2 + 0.003**2)
                    po[int(o)] = float(np.sum(w_ * rr[s_]) / np.sum(w_))
            model.order_offsets[f] = po


def fit_drift(
    model: StableModel,
    line: np.ndarray,
    fibre: np.ndarray,
    order: np.ndarray,
    x: np.ndarray,
    x_err: np.ndarray,
    terms: str | None = None,
    err_floor_px: float = 0.003,
    clip: float = 5.0,
    n_iter: int = 5,
):
    """Per-frame perturbation D(x, m) from measured lines vs the reference.

    Returns (coeffs on the model's drift basis, their errors, n lines used,
    rms [px]). ``terms``: a smaller basis name (e.g. ``"linear"`` for a
    faint reference fibre); missing terms are returned as zero.
    """
    use_terms = model.drift_terms if terms is None else DRIFT_BASES[terms]
    rr = []
    for ln, o, f in zip(line, order, fibre, strict=True):
        v = model.reference.get((int(ln), int(o), int(f)))
        rr.append(np.nan if v is None else v[0])
    r = np.array(rr)
    ok = np.isfinite(r) & np.isfinite(x) & np.isfinite(x_err)
    sc = model.scaling
    B = basis(use_terms, sc.t(x), sc.u(order))
    e2 = x_err**2 + err_floor_px**2
    y = x - r
    g = ok.copy()
    c = np.zeros(len(use_terms))
    for _ in range(n_iter):
        if g.sum() <= len(use_terms) + 2:
            return (
                np.full(len(model.drift_terms), np.nan),
                np.full(len(model.drift_terms), np.nan),
                0,
                np.nan,
            )
        c = _wls(B[g], y[g], 1 / e2[g])
        res = y - B @ c
        z = res / np.sqrt(e2)
        rs = 1.4826 * np.median(np.abs(z[g] - np.median(z[g])))
        g = ok & (np.abs(z) < clip * max(rs, 1.0))
    N = (B[g] / e2[g, None]).T @ B[g]
    chi = np.sum(res[g] ** 2 / e2[g]) / max(g.sum() - len(use_terms), 1)
    ce = np.sqrt(np.diag(np.linalg.inv(N)) * max(chi, 1.0))
    full = np.zeros(len(model.drift_terms))
    fe = np.zeros(len(model.drift_terms))
    for k, tm in enumerate(use_terms):
        j = model.drift_terms.index(tm)
        full[j] = c[k]
        fe[j] = ce[k]
    return full, fe, int(g.sum()), float(np.sqrt(np.mean(res[g] ** 2)))

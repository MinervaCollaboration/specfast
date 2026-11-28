"""Line-by-line (LBL) radial velocities against a data-built template.

Method (Bouchy, Pepe & Queloz 2001; Dumusque 2018; Artigau et al. 2022):
for a spectrum D(lambda) that is the template T shifted by a small
velocity dv,

    D(lambda) ~ T(lambda) + dv * g(lambda),   g = dT/dv = -(lambda / c) T'(lambda),

so within the window of one line the least-squares velocity and its error
are

    dv = sum(w r g) / sum(w g^2),   sigma = sum(w g^2)^(-1/2),

with r = D - T and w the inverse variance. Velocities are measured about a
frame velocity v (the template is evaluated at lambda / (1 + v/c)), so a
line's velocity is v + dv.

Everything here works per echelle order on rest-frame wavelengths
(lambda_rest = lambda_obs (1 + z_B) / (1 + v_star/c), barycorrpy's z_B, as
in :mod:`specfast.conventions`), in plain NumPy plus scipy splines:

- :func:`build_template`: robust (median) co-add of continuum-normalised
  spectra on a common rest-frame grid, with each spectrum's slowly varying
  continuum (blaze residual, colour) solved against the template and
  iterated;
- :func:`find_lines`: line windows from the template's minima, bounded by
  the flanking maxima (the windows tile the order without overlap), with
  depth, width, centre and a blend indicator;
- :func:`line_velocities`: per-line velocities of one spectrum.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import maximum_filter1d, median_filter, uniform_filter1d

from specfast.conventions import C_MPS

__all__ = [
    "LineList",
    "build_template",
    "find_lines",
    "line_velocities",
    "smooth_continuum",
    "template_spline",
]


def _fill(x, good):
    """Linear fill of bad samples (for filters that cannot take weights)."""
    if good.all():
        return x
    if not good.any():
        return np.ones_like(x)
    i = np.arange(x.size)
    return np.interp(i, i[good], x[good])


def smooth_continuum(ratio, good, width_px=301):
    """Slowly varying continuum from a data/template ratio.

    Running median over ``width_px`` pixels (robust to residual lines and
    cosmic rays), then a boxcar of the same width; bad pixels are filled
    linearly first.
    """
    r = _fill(np.asarray(ratio, dtype=float), np.asarray(good, dtype=bool))
    # median of 1/8-width bins, running median of those, then interpolate and
    # smooth: ~the same as a running median of full width, much faster
    b = max(1, width_px // 8)
    nb = r.size // b
    if nb >= 9:
        xb = (np.arange(nb) + 0.5) * b - 0.5
        rb = np.median(r[: nb * b].reshape(nb, b), axis=1)
        rb = median_filter(rb, size=9, mode="nearest")
        r = np.interp(np.arange(r.size), xb, rb)
    else:
        r = median_filter(r, size=width_px, mode="nearest")
    return uniform_filter1d(r, size=width_px, mode="nearest")


def template_spline(grid, tmpl):
    """Cubic spline of a template on its grid (NaN-free)."""
    good = np.isfinite(tmpl)
    return CubicSpline(grid[good], tmpl[good], extrapolate=False)


def _interp_frame(wave, flux, good, grid):
    """Cubic-spline a frame onto ``grid``; grid points near bad pixels -> NaN."""
    out = np.full(grid.shape, np.nan)
    if good.sum() < 10:
        return out
    cs = CubicSpline(wave[good], flux[good], extrapolate=False)
    v = cs(grid)
    # validity: the nearest original pixel on each side must be good
    j = np.clip(np.searchsorted(wave, grid), 1, wave.size - 1)
    ok = good[j] & good[j - 1] & (grid >= wave[0]) & (grid <= wave[-1])
    out[ok] = v[ok]
    return out


def build_template(waves, fluxes, variances, grid, n_iter=3, width_px=301, min_frames=3):
    """Median co-add of spectra (one order) on the rest-frame ``grid``.

    ``waves``, ``fluxes``, ``variances``: (n_frames, n_pix) rest-frame
    wavelengths (increasing), blaze-divided flux and its variance (inf or
    non-finite = bad). Returns the template on ``grid`` (NaN where fewer than
    ``min_frames`` frames contribute) and the per-frame continua (n_frames,
    n_pix) that bring each frame onto the template's scale.
    """
    waves = np.asarray(waves, dtype=float)
    fluxes = np.asarray(fluxes, dtype=float)
    good = np.isfinite(fluxes) & np.isfinite(variances) & (np.asarray(variances) > 0)
    good &= np.isfinite(waves)
    n = fluxes.shape[0]
    cont = np.ones_like(fluxes)
    for k in range(n):
        if good[k].any():
            cont[k] = np.median(fluxes[k][good[k]])
    tmpl = None
    for _ in range(n_iter + 1):
        stack = np.array(
            [_interp_frame(waves[k], fluxes[k] / cont[k], good[k], grid) for k in range(n)]
        )
        cnt = np.isfinite(stack).sum(axis=0)
        with np.errstate(all="ignore"):
            tmpl = np.nanmedian(stack, axis=0)
        tmpl[cnt < min_frames] = np.nan
        tmpl /= np.nanmedian(tmpl)
        ts = template_spline(grid, tmpl)
        for k in range(n):
            t = ts(waves[k])
            g = good[k] & np.isfinite(t) & (t > 0)
            if g.sum() < 10:
                continue
            cont[k] = smooth_continuum(
                np.where(g, fluxes[k] / np.where(g, t, 1.0), 1.0), g, width_px
            )
    return tmpl, cont


@dataclass
class LineList:
    """Line windows found in one order's template (rest frame, wavelength units of the grid)."""

    #: line centre (parabola through the minimum and its neighbours)
    center: np.ndarray
    #: window edges (the flanking maxima)
    lo: np.ndarray
    hi: np.ndarray
    #: depth below the local continuum (1 - T_min / envelope)
    depth: np.ndarray
    #: full width at half depth, in m/s
    fwhm: np.ndarray
    #: 1 - (lower flanking maximum / envelope): 0 for an isolated line
    #: whose window reaches the continuum on both sides, large for blends
    blend: np.ndarray
    #: (max - min) / (max + min) of the two flanking maxima
    asym: np.ndarray
    #: total velocity information sum(g^2) in the window at unit noise
    #: (relative to the continuum), for a quality ranking
    q: np.ndarray

    def __len__(self):
        return self.center.size


def find_lines(grid, tmpl, min_depth=0.03, envelope_kms=40.0, edge=20):
    """Line windows from a template's local minima.

    Each window runs from the local maximum left of a minimum to the one on
    its right, so windows tile the order and never overlap. ``envelope_kms``
    sets the running-maximum width used as the local continuum. Lines within
    ``edge`` grid points of the order ends or of NaN gaps are dropped.
    """
    grid = np.asarray(grid, dtype=float)
    t = np.asarray(tmpl, dtype=float)
    ok = np.isfinite(t)
    tf = _fill(t, ok)
    dlnl = np.median(np.diff(np.log(grid)))
    wenv = max(3, int(round(envelope_kms * 1e3 / C_MPS / dlnl)))
    env = uniform_filter1d(
        maximum_filter1d(tf, size=wenv, mode="nearest"), size=wenv, mode="nearest"
    )
    env = np.maximum(env, tf)
    d = np.diff(tf)
    imin = np.where((d[:-1] < 0) & (d[1:] >= 0))[0] + 1
    imax = np.where((d[:-1] > 0) & (d[1:] <= 0))[0] + 1
    # NaN neighbourhood
    bad = ~ok
    near_bad = maximum_filter1d(bad.astype(np.uint8), size=2 * edge + 1).astype(bool)
    out = {k: [] for k in ("center", "lo", "hi", "depth", "fwhm", "blend", "asym", "q")}
    n = t.size
    for i in imin:
        if i < edge or i > n - edge - 1 or near_bad[i]:
            continue
        kl = np.searchsorted(imax, i) - 1
        kr = kl + 1
        if kl < 0 or kr >= imax.size:
            continue
        a, b = imax[kl], imax[kr]
        if near_bad[a] or near_bad[b]:
            continue
        depth = 1.0 - tf[i] / env[i]
        if depth < min_depth:
            continue
        # parabola through the minimum
        y0, y1, y2 = tf[i - 1], tf[i], tf[i + 1]
        den = y0 - 2 * y1 + y2
        off = 0.5 * (y0 - y2) / den if den > 0 else 0.0
        off = float(np.clip(off, -0.5, 0.5))
        lnc = np.log(grid[i]) + off * dlnl
        # half-depth crossings within the window
        half = tf[i] + 0.5 * (env[i] - tf[i])
        seg_l = tf[a : i + 1][::-1]
        seg_r = tf[i : b + 1]
        jl = np.argmax(seg_l >= half) if (seg_l >= half).any() else seg_l.size - 1
        jr = np.argmax(seg_r >= half) if (seg_r >= half).any() else seg_r.size - 1
        fwhm = (jl + jr) * dlnl * C_MPS
        ml, mr = tf[a] / env[a], tf[b] / env[b]
        g = np.gradient(tf[a : b + 1], np.log(grid[a : b + 1])) / env[a : b + 1]
        out["center"].append(np.exp(lnc))
        out["lo"].append(grid[a])
        out["hi"].append(grid[b])
        out["depth"].append(depth)
        out["fwhm"].append(fwhm)
        out["blend"].append(1.0 - min(ml, mr))
        out["asym"].append(abs(ml - mr) / (ml + mr))
        out["q"].append(float(np.sum((g / C_MPS) ** 2)))
    return LineList(**{k: np.asarray(v, dtype=float) for k, v in out.items()})


def _labels(lam, lo, hi):
    """Pixel -> window index (-1 outside); windows sorted and non-overlapping."""
    lab = np.full(lam.size, -1)
    jlo = np.searchsorted(lam, lo)
    jhi = np.searchsorted(lam, hi)
    for k in range(len(lo)):
        lab[jlo[k] : jhi[k]] = k
    return lab


def line_velocities(
    wave_rest,
    flux,
    variance,
    tspline,
    lo,
    hi,
    v_frame=0.0,
    width_px=301,
    continuum=None,
    n_iter=1,
    clip=5.0,
    deriv=None,
):
    """Per-line velocities (m/s) of one spectrum (one order) against a template.

    ``wave_rest``: the frame's rest-frame wavelengths (barycentric correction
    applied, star velocity not); ``tspline``: :func:`template_spline`;
    ``lo``, ``hi``: line windows (rest frame). The frame velocity starts at
    ``v_frame`` and is re-estimated ``n_iter`` times as the clipped weighted
    mean of the lines; the continuum is re-solved against the shifted template
    unless given. Returns (v_line, sigma_line, v_frame, continuum); lines with
    no usable pixels get NaN.
    """
    wave_rest = np.asarray(wave_rest, dtype=float)
    flux = np.asarray(flux, dtype=float)
    var = np.asarray(variance, dtype=float)
    good = np.isfinite(flux) & np.isfinite(var) & (var > 0) & np.isfinite(wave_rest)
    if deriv is None:
        deriv = tspline.derivative()
    nl = len(lo)
    # pixel -> line label (windows do not overlap)
    v = float(v_frame)
    vel = np.full(nl, np.nan)
    sig = np.full(nl, np.nan)
    cont = continuum
    for it in range(n_iter + 1):
        lam = wave_rest / (1.0 + v / C_MPS)
        t = tspline(lam)
        tp = deriv(lam)
        g_ok = good & np.isfinite(t) & np.isfinite(tp) & (t > 0)
        if cont is None:  # solved once: the frame velocity moves by m/s only
            cont = smooth_continuum(
                np.where(g_ok, flux / np.where(g_ok, t, 1.0), 1.0), g_ok, width_px
            )
        dd = flux / cont
        w = np.where(g_ok, cont**2 / np.where(g_ok, var, 1.0), 0.0)
        r = np.where(g_ok, dd - t, 0.0)
        g = np.where(g_ok, -(lam / C_MPS) * tp, 0.0)
        lab = _labels(lam, lo, hi)
        m = lab >= 0
        num = np.bincount(lab[m], weights=(w * r * g)[m], minlength=nl)
        den = np.bincount(lab[m], weights=(w * g * g)[m], minlength=nl)
        with np.errstate(all="ignore"):
            dv = num / den
            s = 1.0 / np.sqrt(den)
        use = den > 0
        vel[:] = np.nan
        sig[:] = np.nan
        vel[use] = v + dv[use]
        sig[use] = s[use]
        if it == n_iter:
            break
        # clipped weighted mean -> new frame velocity
        x, e = vel[use], sig[use]
        keep = np.ones(x.size, dtype=bool)
        for _ in range(3):
            if keep.sum() < 3:
                break
            ww = 1.0 / e[keep] ** 2
            mu = np.sum(ww * x[keep]) / np.sum(ww)
            z = (x - mu) / e
            mad = 1.4826 * np.median(np.abs(z - np.median(z)))
            keep = np.abs(z - np.median(z)) < clip * max(mad, 1.0)
        if keep.sum() >= 3:
            ww = 1.0 / e[keep] ** 2
            v = float(np.sum(ww * x[keep]) / np.sum(ww))
    return vel, sig, v, cont

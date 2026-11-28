"""Statistics for line-by-line velocity time series.

Small, dependency-light helpers used by the line-atlas analysis
(``scripts/neid_lineatlas.py``):

- :func:`excess_ml`: maximum-likelihood extra scatter tau of values with
  known errors about a free mean (x_i ~ N(mu, e_i^2 + tau^2)), the same
  estimator the chain's "ML excess" uses;
- :func:`group_means`: inverse-variance means of values per group (frames
  -> days or nights);
- :func:`combine_lines`: one velocity per frame from many lines, with
  optional extra per-line variance (excess weighting) and a line mask;
- :func:`block_bootstrap`: resample groups (days, nights) for confidence
  intervals of a statistic, paired between methods.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar

__all__ = ["block_bootstrap", "combine_lines", "excess_ml", "group_means", "wrms"]


def _nll(tau, x, e):
    v = e**2 + tau**2
    w = 1.0 / v
    mu = np.sum(w * x) / np.sum(w)
    return 0.5 * np.sum(np.log(v) + (x - mu) ** 2 * w)


def excess_ml(x, e, tau_max=None):
    """ML extra scatter tau >= 0 of ``x`` with errors ``e`` about a free mean.

    Non-finite entries are ignored; returns NaN with fewer than 3 values.
    """
    x = np.asarray(x, dtype=float)
    e = np.asarray(e, dtype=float)
    ok = np.isfinite(x) & np.isfinite(e) & (e > 0)
    x, e = x[ok], e[ok]
    if x.size < 3:
        return np.nan
    span = np.std(x) * 3 + np.max(e)
    hi = tau_max if tau_max is not None else span
    r = minimize_scalar(
        _nll, bounds=(0.0, hi), args=(x, e), method="bounded", options={"xatol": 1e-4 * hi}
    )
    tau = float(r.x)
    # the bounded optimiser never lands exactly on 0: compare with the boundary
    if _nll(0.0, x, e) <= r.fun:
        tau = 0.0
    return tau


def group_means(groups, x, e):
    """Inverse-variance mean and error of ``x`` per group (axis 0 = samples).

    ``x``, ``e``: (n,) or (n, m); NaN entries are skipped. Returns
    (unique_groups, mean (g, ...), error (g, ...)); groups with no data get NaN.
    """
    groups = np.asarray(groups)
    ug, inv = np.unique(groups, return_inverse=True)
    x = np.asarray(x, dtype=float)
    e = np.asarray(e, dtype=float)
    shp = (ug.size,) + x.shape[1:]
    ok = np.isfinite(x) & np.isfinite(e) & (e > 0)
    w = np.where(ok, 1.0 / np.where(ok, e, 1.0) ** 2, 0.0)
    xw = np.where(ok, x, 0.0) * w
    sw = np.zeros(shp)
    sx = np.zeros(shp)
    np.add.at(sw, inv, w)
    np.add.at(sx, inv, xw)
    with np.errstate(all="ignore"):
        m = sx / sw
        err = 1.0 / np.sqrt(sw)
    m[sw == 0] = np.nan
    err[sw == 0] = np.nan
    return ug, m, err


def combine_lines(vel, sig, mask=None, extra=None, clip=None, n_iter=3):
    """Weighted mean over lines (axis 1) per frame.

    ``vel``, ``sig``: (n_frames, n_lines); ``mask``: (n_lines,) bool, lines
    to use; ``extra``: (n_lines,) extra per-line scatter added in quadrature
    to ``sig`` for the weights; ``clip``: if given, lines deviating from the
    frame's mean by more than ``clip`` times their (sig, extra) error, and
    by more than ``clip`` times the frame's robust (MAD) spread of such
    normalised deviations, are dropped for that frame (``n_iter`` passes).
    Returns (v, sigma) per frame, sigma from the weights actually used
    (photon errors propagated through the weights).
    """
    vel = np.asarray(vel, dtype=float)
    sig = np.asarray(sig, dtype=float)
    ok = np.isfinite(vel) & np.isfinite(sig) & (sig > 0)
    if mask is not None:
        ok &= np.asarray(mask, dtype=bool)[None, :]
    s2 = sig**2 + (0.0 if extra is None else np.asarray(extra, dtype=float)[None, :] ** 2)
    vz = np.where(ok, vel, 0.0)

    def mean(okk):
        w = np.where(okk, 1.0 / np.where(okk, s2, 1.0), 0.0)
        sw = w.sum(axis=1)
        with np.errstate(all="ignore"):
            v = (w * vz).sum(axis=1) / sw
            e = np.sqrt((w**2 * np.where(okk, sig, 0.0) ** 2).sum(axis=1)) / sw
        v[sw == 0] = np.nan
        e[sw == 0] = np.nan
        return v, e

    v, e = mean(ok)
    if clip is not None:
        use = ok
        for _ in range(n_iter):
            z = np.where(ok, (vz - v[:, None]) / np.sqrt(s2), np.nan)
            with np.errstate(all="ignore"):
                mad = 1.4826 * np.nanmedian(np.abs(z), axis=1)
            lim = clip * np.maximum(np.nan_to_num(mad, nan=1.0), 1.0)
            use = ok & (np.abs(np.nan_to_num(z, nan=np.inf)) < lim[:, None])
            v, e = mean(use)
    return v, e


def wrms(x, e=None):
    """rms about the (weighted) mean; unweighted if ``e`` is None."""
    x = np.asarray(x, dtype=float)
    ok = np.isfinite(x)
    if e is None:
        return float(np.sqrt(np.mean((x[ok] - x[ok].mean()) ** 2)))
    e = np.asarray(e, dtype=float)
    ok &= np.isfinite(e) & (e > 0)
    w = 1.0 / e[ok] ** 2
    mu = np.sum(w * x[ok]) / np.sum(w)
    return float(np.sqrt(np.sum(w * (x[ok] - mu) ** 2) / np.sum(w)))


def block_bootstrap(stat, n_groups, n_boot=2000, seed=0):
    """Bootstrap over groups: ``stat(idx)`` evaluated on resampled group indices.

    Returns an array (n_boot, ...) of the statistic. Pass the same ``seed``
    to compare methods on identical resamples (paired CIs).
    """
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        out.append(stat(rng.integers(0, n_groups, n_groups)))
    return np.array(out)

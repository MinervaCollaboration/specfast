"""Combination: per-segment (or per-order) velocities -> per-exposure RVs.

DESIGN.md, "Combination": a joint solve of

    v_(e, s) = RV_e + O_(group, era) + noise,
    sigma^2  = beta^2 sigma_i^2 + s^2      (beta < 1 allowed),

with the offsets O solved jointly with the RVs (generalized least squares;
their uncertainty propagated into the RV covariance through the joint
inverse), beta and s by maximum likelihood (REML over the linear
parameters), and iterative clipping of outliers. Groups are e.g. (channel,
order); eras come from the instrument description (instrument-wide eras and
per-channel breaks) or the run configuration, as one label per measurement.

:func:`era_zero_points` then removes a per-era common mode from the exposure
RVs of one star (its weighted mean per era relative to the reference era); a
joint multi-star common-mode fit belongs to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

__all__ = ["CombinedVelocities", "SegmentVelocities", "combine", "era_zero_points"]


@dataclass(frozen=True)
class SegmentVelocities:
    """Every segment velocity of a set of exposures, long format."""

    #: Exposure index per measurement.
    exposure: np.ndarray
    #: Offset-group label per measurement (e.g. "T2/o07/s1").
    group: np.ndarray
    #: Era label per measurement.
    era: np.ndarray
    #: Velocity [m/s] and formal uncertainty [m/s].
    velocity: np.ndarray
    sigma: np.ndarray


@dataclass(frozen=True)
class CombinedVelocities:
    """Per-exposure RVs [m/s] with their full covariance [m^2/s^2]."""

    rv: np.ndarray
    covariance: np.ndarray
    #: Fitted error-model scale and jitter [m/s].
    beta: float
    jitter: float
    #: Exposure labels of ``rv`` (exposures with at least one kept value).
    exposures: np.ndarray | None = None
    #: Per-measurement residual and keep mask (after clipping).
    residual: np.ndarray | None = None
    keep: np.ndarray | None = None


def _solve(exp_i, off_i, n_exp, n_off, y, var):
    """GLS for [RV | offsets]; gauge: sum of RVs = 0 (a constant moves
    between RVs and offsets)."""
    n = n_exp + n_off
    w = 1.0 / var
    A = np.zeros((n, n))
    np.add.at(A, (exp_i, exp_i), w)
    np.add.at(A, (n_exp + off_i, n_exp + off_i), w)
    np.add.at(A, (exp_i, n_exp + off_i), w)
    np.add.at(A, (n_exp + off_i, exp_i), w)
    b = np.zeros(n)
    np.add.at(b, exp_i, w * y)
    np.add.at(b, n_exp + off_i, w * y)
    g = np.zeros(n)
    g[:n_exp] = 1.0
    K = np.zeros((n + 1, n + 1))
    K[:n, :n] = A
    K[:n, n] = g
    K[n, :n] = g
    Kinv = np.linalg.pinv(K)
    theta = (Kinv @ np.r_[b, 0.0])[:n]
    return theta, Kinv[:n, :n], A


def combine(
    segments: SegmentVelocities,
    clip: float = 5.0,
    max_clip_iter: int = 5,
    fit_error_model: bool = True,
) -> CombinedVelocities:
    """Joint offset / error-model solve (see the module docstring)."""
    v = np.asarray(segments.velocity, dtype=np.float64)
    s = np.asarray(segments.sigma, dtype=np.float64)
    ok = np.isfinite(v) & np.isfinite(s) & (s > 0)
    exp_lab = np.asarray(segments.exposure)
    grp = np.array([f"{g}|{e}" for g, e in zip(segments.group, segments.era, strict=True)])
    keep = ok.copy()
    beta, jit = 1.0, 0.0
    resid_all = np.full(v.size, np.nan)
    for _ in range(max_clip_iter):
        ue, ei = np.unique(exp_lab[keep], return_inverse=True)
        ug, gi = np.unique(grp[keep], return_inverse=True)
        y, si = v[keep], s[keep]

        def nll(q, ei=ei, gi=gi, ne=ue.size, ng=ug.size, y=y, si=si):
            bb, jj = np.exp(q)
            var = bb * bb * si * si + jj * jj
            theta, _, A = _solve(ei, gi, ne, ng, y, var)
            r = y - theta[ei] - theta[ne + gi]
            ev = np.linalg.eigvalsh(A)
            logdet = np.sum(np.log(ev[ev > 1e-12 * ev.max()]))
            return 0.5 * (np.sum(r * r / var) + np.sum(np.log(var)) + logdet)

        if fit_error_model:
            res = minimize(
                nll,
                np.log([max(beta, 0.05), max(jit, 0.1)]),
                method="Nelder-Mead",
                options=dict(xatol=1e-3, fatol=1e-3, maxiter=400),
            )
            beta, jit = (float(x) for x in np.exp(res.x))
        var = beta * beta * si * si + jit * jit
        theta, cov, _ = _solve(ei, gi, ue.size, ug.size, y, var)
        epos = {e: k for k, e in enumerate(ue)}
        gpos = {g: k for k, g in enumerate(ug)}
        resid_all = np.full(v.size, np.nan)
        for i in np.where(ok)[0]:
            if exp_lab[i] in epos and grp[i] in gpos:
                resid_all[i] = v[i] - theta[epos[exp_lab[i]]] - theta[ue.size + gpos[grp[i]]]
        z = resid_all / np.sqrt(beta * beta * s * s + jit * jit)
        new = ok & np.isfinite(z) & (np.abs(z) < clip)
        if np.array_equal(new, keep):
            break
        keep = new
    return CombinedVelocities(
        rv=theta[: ue.size],
        covariance=cov[: ue.size, : ue.size],
        beta=beta,
        jitter=jit,
        exposures=ue,
        residual=resid_all,
        keep=keep,
    )


def era_zero_points(
    mjd: np.ndarray, rv: np.ndarray, sigma: np.ndarray, breaks, ref_era: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    """Remove the weighted mean RV of each era (eras start at ``breaks``,
    MJD) relative to the reference era. Returns (corrected RVs, per-era zero
    points)."""
    era = np.searchsorted(np.asarray(breaks, float), np.asarray(mjd, float), side="right")
    w = 1.0 / np.asarray(sigma, float) ** 2
    zp = np.zeros(len(breaks) + 1)
    for e in np.unique(era):
        m = era == e
        zp[e] = np.sum(w[m] * rv[m]) / np.sum(w[m])
    zp = zp - zp[ref_era]
    return rv - zp[era], zp

"""Per-block weighted least squares of the free parameters of one model.

The first, simple fitting engine: one block (exposure, channel, order) at a
time, scipy's bounded trust-region least squares with finite-difference
Jacobians. It lives outside the model (components stay scipy-free); the
template solver (:mod:`specfast.doppler.template`) calls it for its
velocity and nuisance updates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from specfast.doppler.components import ExposureContext
from specfast.doppler.model import ForwardModel, ModelParams, ParameterLayout

#: Default step of one solver unit per (component, parameter) or unit.
DEFAULT_SCALES: dict = {
    ("star", "v"): 10.0,
    ("iodine", "k"): 1e-3,
    ("wavelength", "coeffs"): 1e-3,
    ("continuum", "coeffs"): 1.0,
    ("telluric", "water"): 1e-3,
    "m/s": 10.0,
    "Angstrom": 1e-3,
    "": 1e-3,
}


@dataclass
class BlockFit:
    """Result of :func:`fit_block`."""

    params: dict
    #: Covariance of the free parameters (physical units, layout order).
    cov: np.ndarray
    layout: ParameterLayout
    #: Weighted chi2 at the solution.
    chi2: float
    #: Number of pixels with finite weight.
    ndata: int
    success: bool

    def sigma(self, comp: str, name: str) -> np.ndarray:
        i = 0
        for c, p, n in self.layout.entries:
            if (c, p) == (comp, name):
                return np.sqrt(np.diag(self.cov)[i : i + n])
            i += n
        raise KeyError((comp, name))


def _scales(model: ForwardModel, layout: ParameterLayout, start: ModelParams, scales: Mapping):
    units = {(c, s.name): s.unit for c, s in model.parameter_specs()}
    out = []
    for c, p, n in layout.entries:
        if (c, p) in scales:
            sc = scales[(c, p)]
        elif (c, p) == (model.continuum.name, "coeffs"):
            # continuum coefficients: a fraction of the flux level
            sc = 1e-3 * max(abs(float(np.asarray(start[c][p])[0])), 1e-12)
        else:
            sc = scales.get(units[(c, p)], 1e-3)
        out.append(np.full(n, float(sc)))
    return np.concatenate(out) if out else np.zeros(0)


def fit_block(
    model: ForwardModel,
    data: np.ndarray,
    sigma: np.ndarray,
    ctx: ExposureContext,
    start: ModelParams,
    exclude: Iterable[tuple[str, str]] = (),
    scales: Mapping | None = None,
    jac: str = "3-point",
    tol: float = 1e-14,
    max_nfev: int = 2000,
    profile_continuum: bool = False,
    solver: str = "trf",
) -> BlockFit:
    """Weighted least squares of every free parameter of ``model`` (not
    ``fixed``, not in ``exclude``). Pixels with infinite ``sigma`` carry no
    weight. Parameters are rescaled by ``scales`` (one solver unit) so the
    finite-difference steps are sensible; the covariance comes from a
    central-difference Jacobian at the solution, over all free parameters.

    ``profile_continuum``: the continuum must be linear in its coefficients
    (a polynomial); it is then solved linearly inside every residual
    evaluation (variable projection), which removes it from the nonlinear
    search. The covariance still includes it.

    ``solver``: ``"trf"`` (scipy's trust-region reflective; ``jac``, ``tol``
    and ``max_nfev`` apply) or ``"gn"`` (:func:`gauss_newton`: damped
    Gauss-Newton with central differences, stopping when every step is below
    1e-4 of the parameter's own uncertainty; far fewer evaluations).
    """
    layout = ParameterLayout.free(model, exclude=exclude)
    sc = DEFAULT_SCALES if scales is None else {**DEFAULT_SCALES, **scales}
    w = 1.0 / np.asarray(sigma, dtype=np.float64)
    good = w > 0
    data = np.asarray(data, dtype=np.float64)
    cname = model.continuum.name
    cfree = any((c, p) == (cname, "coeffs") for c, p, _ in layout.entries)
    profile = profile_continuum and cfree
    if profile:
        nl = ParameterLayout(tuple(e for e in layout.entries if e[:2] != (cname, "coeffs")))
        ncoef = np.asarray(start[cname]["coeffs"]).size
        basis = np.stack(
            [
                model.continuum.evaluate({"coeffs": np.eye(ncoef)[k]}, model.pixels, ctx)
                for k in range(ncoef)
            ],
            axis=1,
        )
        unit = {"coeffs": _unit_coeffs(basis)}
    else:
        nl = layout
    p0 = nl.pack(start)
    scale = _scales(model, nl, start, sc)
    work = {c: dict(d) for c, d in start.items()}

    def params_of(theta):
        p = nl.unpack(p0 + theta * scale, work)
        if profile:
            p[cname] = unit
            u = model.evaluate(p, ctx)
            B = u[:, None] * basis
            coef, *_ = np.linalg.lstsq(B[good] * w[good, None], data[good] * w[good], rcond=None)
            p[cname] = {"coeffs": coef}
        return p

    def resid(theta):
        return ((data - model.evaluate(params_of(theta), ctx)) * w)[good]

    if nl.size and solver == "gn":
        x, success = gauss_newton(resid, np.zeros_like(p0), max_iter=max(5, max_nfev // 10))
    elif nl.size:
        res = least_squares(
            resid,
            np.zeros_like(p0),
            method="trf",
            jac=jac,
            diff_step=1e-4,
            x_scale="jac",
            xtol=tol,
            ftol=tol,
            gtol=tol,
            max_nfev=max_nfev,
        )
        x, success = res.x, bool(res.success)
    else:
        x, success = np.zeros(0), True
    best = params_of(x)
    # covariance over every free parameter (continuum included)
    pf = layout.pack(best)
    fscale = _scales(model, layout, best, sc)

    def full_resid(theta):
        return ((data - model.evaluate(layout.unpack(pf + theta * fscale, best), ctx)) * w)[good]

    J = np.empty((int(good.sum()), len(pf)))
    for j in range(len(pf)):
        h = np.zeros_like(pf)
        h[j] = 1e-3
        J[:, j] = (full_resid(h) - full_resid(-h)) / (2e-3 * fscale[j])
    cov = np.linalg.pinv(J.T @ J)
    r = full_resid(np.zeros_like(pf))
    return BlockFit(
        params=best,
        cov=cov,
        layout=layout,
        chi2=float(r @ r),
        ndata=int(good.sum()),
        success=success,
    )


def _central_jacobian(resid, x, r0, h=1e-3):
    J = np.empty((r0.size, x.size))
    for j in range(x.size):
        d = np.zeros_like(x)
        d[j] = h
        J[:, j] = (resid(x + d) - resid(x - d)) / (2 * h)
    return J


def gauss_newton(resid, x0, max_iter: int = 30, rel_step: float = 1e-4):
    """Minimize ``|resid(x)|^2`` by damped Gauss-Newton (Levenberg-Marquardt
    damping) with central-difference Jacobians (step 1e-3 in ``x``, so ``x``
    should be scaled to O(1) per expected change).

    Stops when every accepted step is below ``rel_step`` times that
    parameter's 1-sigma uncertainty. Returns (x, converged).
    """
    x = np.asarray(x0, dtype=np.float64).copy()
    r = resid(x)
    chi2 = r @ r
    lam = 1e-3
    for _ in range(max_iter):
        J = _central_jacobian(resid, x, r)
        A = J.T @ J
        g = J.T @ r
        sig = np.sqrt(np.clip(np.diag(np.linalg.pinv(A)), 0, None))
        accepted = False
        for _ in range(12):
            step = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-300), -g)
            rn = resid(x + step)
            cn = rn @ rn
            if cn <= chi2:
                x, r, chi2 = x + step, rn, cn
                lam = max(lam / 10, 1e-9)
                accepted = True
                break
            lam *= 10
        if not accepted or np.all(np.abs(step) <= rel_step * np.maximum(sig, 1e-300)):
            return x, True
    return x, False


def _unit_coeffs(basis: np.ndarray) -> np.ndarray:
    """Coefficients of the constant-one continuum, for a polynomial basis
    whose first column is constant."""
    if not np.allclose(basis[:, 0], basis[0, 0]):
        raise ValueError("profile_continuum needs a continuum whose first basis term is constant")
    out = np.zeros(basis.shape[1])
    out[0] = 1.0 / basis[0, 0]
    return out

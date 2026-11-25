"""Per-block fitting with semi-analytic Jacobians, shared-parameter (Schur)
contributions and residual projections.

:func:`specfast.doppler.fit.fit_block` differentiates the whole model by
finite differences: every Jacobian column costs a full model evaluation
(fine spectrum, one convolution per LSF node, pixel integration). Most
columns do not need that:

- **continuum** (linear in its coefficients): ``basis_j * U`` with ``U`` the
  binned spectrum;
- **wavelength** coefficients only move the pixel edges: the pixel average
  ``U_i = (A(e_i+1) - A(e_i)) / (e_i+1 - e_i)`` of the broadened spectrum
  ``b`` (``A`` its running integral) has
  ``dU_i = [b(e_i+1) de_i+1 - b(e_i) de_i - U_i (de_i+1 - de_i)] / (e_i+1 - e_i)``,
  so they need no convolution;
- **spectral-factor** parameters (velocity, iodine strength, water, ...):
  a central difference of that factor alone, times the other factors,
  convolved once per LSF node;
- **LSF** parameters: a central difference of the node kernels, convolved
  with the unchanged fine spectrum.

With CTI the linearized CTI operator is applied to every column.
:func:`fit_block_fast` is damped Gauss-Newton on these Jacobians.
:func:`schur_terms` gives the reduced normal equations of parameters
shared between blocks (one water column per exposure, one illumination
kernel per exposure and channel) with the block's own parameters profiled
out, which a shared-parameter step sums over blocks.
:func:`project_block` is the joint linear projection of a block's residual
on segment velocities, the local nuisances and shape terms (instrument-
frame LSF width and skew; star-frame broadening, skew and line depth),
with covariances (DESIGN, "Stellar signals", outputs 1 and 3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from specfast.conventions import C_MPS
from specfast.doppler.components import ExposureContext
from specfast.doppler.grid import convolve, hermite_value
from specfast.doppler.model import ForwardModel

__all__ = [
    "BlockSolution",
    "fit_block_fast",
    "model_and_jacobian",
    "project_block",
    "schur_terms",
]

#: Finite-difference half-steps per (component kind or parameter name).
FD_STEP = {
    "v": 1.0,  # m/s
    "zero_point": 1.0,
    "k": 1e-4,
    "water": 1e-3,
    "illum": 1e-3,
    "map": 1e-3,
    "sigma": 1.0,
}


@dataclass
class _State:
    fine: np.ndarray
    kernels: list
    weights: np.ndarray | None
    ln_edges: np.ndarray
    broadened: list
    binned_nodes: list
    binned: np.ndarray
    pixel_factor: np.ndarray
    loss: np.ndarray | None
    flux: np.ndarray


def _state(model: ForwardModel, params, ctx) -> _State:
    fine = model.fine_spectrum(params, ctx)
    ks, w = model.node_kernels(params, ctx)
    le = model.ln_sample(params, ctx)
    b = [convolve(fine, k) for k in ks]
    u_k = [model.bin(bb, le) for bb in b]
    u = u_k[0] if w is None else sum(w[k] * u_k[k] for k in range(len(ks)))
    pf = model.pixel_factor(params, ctx)
    flux = pf * u
    loss = None
    if model.cti is not None:
        cp = params[model.cti.name]
        loss = model.cti.loss(cp, flux, model.pixels)
        flux = model.cti.apply_linear(cp, loss, flux, model.pixels)
    return _State(fine, ks, w, le, b, u_k, u, pf, loss, flux)


def _blend(model, st: _State, dfine=None, dkernels=None) -> np.ndarray:
    """Binned, blended response to a fine-spectrum change ``dfine`` (with the
    current kernels) or a kernel change ``dkernels`` (current fine spectrum)."""
    out = np.zeros(model.pixels.size)
    for k in range(len(st.kernels)):
        if dfine is not None:
            bb = convolve(dfine, st.kernels[k])
        else:
            bb = convolve(st.fine, dkernels[k])
        uk = model.bin(bb, st.ln_edges)
        out += uk if st.weights is None else st.weights[k] * uk
    return out


def _cti(model, params, st: _State, col: np.ndarray) -> np.ndarray:
    if model.cti is None:
        return col
    return model.cti.apply_linear(params[model.cti.name], st.loss, col, model.pixels)


def _component(model: ForwardModel, name: str):
    for c in model.components:
        if c.name == name:
            return c
    raise KeyError(f"no component {name!r}")


def _with(params, comp, name, value):
    out = {c: dict(d) for c, d in params.items()}
    out.setdefault(comp, {})[name] = value
    return out


def model_and_jacobian(
    model: ForwardModel,
    params: Mapping,
    ctx: ExposureContext,
    free: Sequence[tuple[str, str]],
    extra_fine: Sequence[np.ndarray] = (),
) -> tuple[np.ndarray, np.ndarray, list[tuple[str, str, int]], _State]:
    """Model flux and the Jacobian (npix x n) of the ``free`` (component,
    parameter) pairs, every element of each array parameter a column, in
    order. ``extra_fine``: additional fine-grid perturbations whose binned
    responses are appended as columns (shape terms). Returns (flux, J,
    column labels, state)."""
    st = _state(model, params, ctx)
    cols, labels = [], []
    others_cache: dict = {}
    for cname, pname in free:
        comp = _component(model, cname)
        val = np.atleast_1d(np.asarray(params[cname][pname], dtype=np.float64))
        if comp is model.continuum:
            n = val.size
            for j in range(n):
                e = np.zeros(n)
                e[j] = 1.0
                basis = comp.evaluate({pname: e}, model.pixels, ctx)
                c = basis * st.binned
                if model.detector is not None:
                    c = c * model.detector.evaluate(params[model.detector.name], model.pixels, ctx)
                cols.append(_cti(model, params, st, c))
                labels.append((cname, pname, j))
        elif comp is model.wavelength:
            pos = model.sample_positions(params)
            lam0 = comp.evaluate(params[cname], pos, ctx)
            point = model.sampling == "point"
            if point:
                hstep = 1e-3 * model.grid.step
                bder = [
                    (
                        hermite_value(bb, model.grid, st.ln_edges + hstep)
                        - hermite_value(bb, model.grid, st.ln_edges - hstep)
                    )
                    / (2 * hstep)
                    for bb in st.broadened
                ]
            else:
                d = st.ln_edges[1:] - st.ln_edges[:-1]
                bvals = [hermite_value(bb, model.grid, st.ln_edges) for bb in st.broadened]
            for j in range(val.size):
                pv = val.copy()
                h = max(1e-6, 1e-6 * abs(pv[j]))
                pv[j] += h
                lam1 = comp.evaluate({**params[cname], pname: pv}, pos, ctx)
                de = (lam1 - lam0) / h / lam0
                du = np.zeros(model.pixels.size)
                for k in range(len(st.broadened)):
                    if point:
                        t = bder[k] * de
                    else:
                        bv = bvals[k]
                        t = (
                            bv[1:] * de[1:]
                            - bv[:-1] * de[:-1]
                            - st.binned_nodes[k] * (de[1:] - de[:-1])
                        ) / d
                    du += t if st.weights is None else st.weights[k] * t
                cols.append(_cti(model, params, st, st.pixel_factor * du))
                labels.append((cname, pname, j))
        elif comp is model.lsf:
            h = FD_STEP.get(pname, 1e-3)
            for j in range(val.size):
                vp, vm = val.copy(), val.copy()
                vp[j] += h
                vm[j] -= h
                kp = (
                    comp.kernels({**params[cname], pname: vp}, model.grid)
                    if hasattr(comp, "kernels")
                    else [comp.evaluate({**params[cname], pname: vp}, model.grid, ctx)]
                )
                km = (
                    comp.kernels({**params[cname], pname: vm}, model.grid)
                    if hasattr(comp, "kernels")
                    else [comp.evaluate({**params[cname], pname: vm}, model.grid, ctx)]
                )
                dk = [(a - b) / (2 * h) for a, b in zip(kp, km, strict=True)]
                c = st.pixel_factor * _blend(model, st, dkernels=dk)
                cols.append(_cti(model, params, st, c))
                labels.append((cname, pname, j))
        else:  # a spectral factor
            if cname not in others_cache:
                others_cache[cname] = model.fine_spectrum(params, ctx, skip=(cname,))
            others = others_cache[cname]
            h = FD_STEP.get(pname, 1e-4)
            for j in range(val.size):
                vp, vm = val.copy(), val.copy()
                vp[j] += h
                vm[j] -= h
                fp = comp.evaluate({**params[cname], pname: vp}, model.grid.lnlam, ctx)
                fm = comp.evaluate({**params[cname], pname: vm}, model.grid.lnlam, ctx)
                dfine = others * (fp - fm) / (2 * h)
                c = st.pixel_factor * _blend(model, st, dfine=dfine)
                cols.append(_cti(model, params, st, c))
                labels.append((cname, pname, j))
    for df in extra_fine:
        c = st.pixel_factor * _blend(model, st, dfine=df)
        cols.append(_cti(model, params, st, c))
        labels.append(("shape", "extra", len(labels)))
    J = np.stack(cols, axis=1) if cols else np.zeros((st.flux.size, 0))
    return st.flux, J, labels, st


@dataclass
class BlockSolution:
    """Result of :func:`fit_block_fast`."""

    params: dict
    #: Covariance of the free parameters (column order of ``labels``).
    cov: np.ndarray
    labels: list
    chi2: float
    ndata: int
    niter: int
    converged: bool
    #: Weighted Jacobian and weighted residual at the solution (for Schur
    #: complements and projections).
    jw: np.ndarray
    rw: np.ndarray
    flux: np.ndarray

    def index(self, comp: str, name: str, j: int = 0) -> int:
        return self.labels.index((comp, name, j))

    def value_sigma(self, comp: str, name: str, j: int = 0) -> tuple[float, float]:
        i = self.index(comp, name, j)
        return (
            float(np.atleast_1d(self.params[comp][name])[j]),
            float(np.sqrt(max(self.cov[i, i], 0.0))),
        )


def _apply_step(params, labels, step, bounds):
    out = {
        c: {k: np.array(v, dtype=np.float64, copy=True) for k, v in d.items()}
        for c, d in params.items()
    }
    for (c, p, j), s in zip(labels, step, strict=True):
        a = np.atleast_1d(out[c][p])
        a[j] += s
        lo, hi = bounds.get((c, p), (-np.inf, np.inf))
        a[j] = min(max(a[j], lo), hi)
        out[c][p] = a
    return out


def fit_block_fast(
    model: ForwardModel,
    data: np.ndarray,
    sigma: np.ndarray,
    ctx: ExposureContext,
    start: Mapping,
    free: Sequence[tuple[str, str]],
    max_iter: int = 30,
    rel_tol: float = 1e-3,
    bounds: Mapping | None = None,
) -> BlockSolution:
    """Damped Gauss-Newton on the semi-analytic Jacobian. Stops when every
    step is below ``rel_tol`` of that parameter's 1-sigma uncertainty.
    ``bounds``: {(component, parameter): (lo, hi)} (clipped)."""
    bounds = dict(bounds or {})
    for c, p in free:
        comp = _component(model, c)
        for s in comp.parameters():
            if s.name == p and (c, p) not in bounds:
                bounds[(c, p)] = (s.lower, s.upper)
    s = np.asarray(sigma, dtype=np.float64)
    w = np.where(np.isfinite(s) & (s > 0), 1.0 / np.where(s > 0, s, 1.0), 0.0)
    d = np.asarray(data, dtype=np.float64)
    d = np.where(w > 0, d, 0.0)
    p = {
        c: {k: np.array(v, dtype=np.float64, copy=True) for k, v in dd.items()}
        for c, dd in start.items()
    }
    lam = 1e-4
    converged = False
    it = 0
    flux, J, labels, _ = model_and_jacobian(model, p, ctx, free)
    r = (d - flux) * w
    chi2 = float(r @ r)
    for it in range(1, max_iter + 1):  # noqa: B007 (it is reported)
        Jw = J * w[:, None]
        A = Jw.T @ Jw
        g = Jw.T @ r
        dA = np.diag(A).copy()
        dA[dA <= 0] = 1.0
        accepted = False
        for _ in range(10):
            try:
                step = np.linalg.solve(A + lam * np.diag(dA), g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            pt = _apply_step(p, labels, step, bounds)
            ft = model.evaluate(pt, ctx)
            rt = (d - ft) * w
            ct = float(rt @ rt)
            if np.isfinite(ct) and ct <= chi2 * (1 + 1e-12):
                accepted = True
                break
            lam *= 10
        if not accepted:
            converged = True  # cannot improve: at a minimum (to rounding)
            break
        p, chi2 = pt, ct
        lam = max(lam / 10, 1e-9)
        try:
            sig = np.sqrt(np.clip(np.diag(np.linalg.inv(A)), 0, None))
        except np.linalg.LinAlgError:
            sig = np.sqrt(1.0 / dA)
        flux, J, labels, _ = model_and_jacobian(model, p, ctx, free)
        r = (d - flux) * w
        chi2 = float(r @ r)
        if np.all(np.abs(step) <= rel_tol * np.maximum(sig, 1e-300)):
            converged = True
            break
    Jw = J * w[:, None]
    try:
        cov = np.linalg.inv(Jw.T @ Jw)
    except np.linalg.LinAlgError:
        cov = np.linalg.pinv(Jw.T @ Jw)
    return BlockSolution(
        params=p,
        cov=cov,
        labels=labels,
        chi2=chi2,
        ndata=int((w > 0).sum()),
        niter=it,
        converged=converged,
        jw=Jw,
        rw=r,
        flux=flux,
    )


def schur_terms(
    model: ForwardModel,
    params: Mapping,
    ctx: ExposureContext,
    data: np.ndarray,
    sigma: np.ndarray,
    local: Sequence[tuple[str, str]],
    shared: Sequence[tuple[str, str]],
):
    """Reduced normal equations of the ``shared`` parameters with the block's
    ``local`` ones profiled out, at ``params``: (H, b, labels) with the
    Gauss-Newton update of the shared parameters ``H^-1 b`` (summed over
    blocks first), and chi2."""
    s = np.asarray(sigma, dtype=np.float64)
    w = np.where(np.isfinite(s) & (s > 0), 1.0 / np.where(s > 0, s, 1.0), 0.0)
    d = np.where(w > 0, np.asarray(data, dtype=np.float64), 0.0)
    flux, J, labels, _ = model_and_jacobian(model, params, ctx, list(local) + list(shared))
    nl = sum(1 for lab in labels if (lab[0], lab[1]) in set(map(tuple, local)))
    Jw = J * w[:, None]
    r = (d - flux) * w
    Jl, Js = Jw[:, :nl], Jw[:, nl:]
    A = Jl.T @ Jl
    try:
        AiB = np.linalg.solve(A, Jl.T @ Js)
        Air = np.linalg.solve(A, Jl.T @ r)
    except np.linalg.LinAlgError:
        Ai = np.linalg.pinv(A)
        AiB, Air = Ai @ (Jl.T @ Js), Ai @ (Jl.T @ r)
    H = Js.T @ Js - (Jl.T @ Js).T @ AiB
    b = Js.T @ r - (Jl.T @ Js).T @ Air
    return H, b, labels[nl:], float(r @ r)


# --------------------------------------------------------------- projection
#: Shape terms of :func:`project_block`: name -> (frame, doc).
SHAPE_TERMS = {
    "lsf_width": ("instrument", "fractional LSF width change (all nodes)"),
    "lsf_h3": ("instrument", "LSF h3 change (all nodes)"),
    "star_broad": ("star", "template broadening: d(sigma^2 / 2) [(km/s)^2]"),
    "star_skew": ("star", "template third-derivative term [(km/s)^3]"),
    "star_depth": ("star", "template line-depth scaling (fraction)"),
}


def _lsf_shape_kernels(model, params, term, h):
    lsf = model.lsf
    lp = dict(params[lsf.name])
    if "map" in lp:
        m = np.array(lp["map"], dtype=np.float64)
        mp, mm = m.copy(), m.copy()
        if term == "lsf_width":
            mp[0] *= 1 + h
            mm[0] *= 1 - h
        else:
            mp[3] += h
            mm[3] -= h
        kp = lsf.kernels({**lp, "map": mp}, model.grid)
        km = lsf.kernels({**lp, "map": mm}, model.grid)
    elif "sigma" in lp:
        if term != "lsf_width":
            return None
        sgm = np.array(lp["sigma"], dtype=np.float64)
        kp = [lsf.evaluate({**lp, "sigma": sgm * (1 + h)}, model.grid, None)]
        km = [lsf.evaluate({**lp, "sigma": sgm * (1 - h)}, model.grid, None)]
    else:
        return None
    return [(a - b) / (2 * h) for a, b in zip(kp, km, strict=True)]


def project_block(
    model: ForwardModel,
    params: Mapping,
    ctx: ExposureContext,
    data: np.ndarray,
    sigma: np.ndarray,
    local: Sequence[tuple[str, str]],
    nseg: int = 4,
    star: str = "star",
    shape_terms: Sequence[str] = tuple(SHAPE_TERMS),
) -> dict:
    """Joint weighted projection of the block residual (at ``params``, a
    converged solution) on: ``nseg`` segment velocities (equal pixel
    fractions of the block; the whole-order velocity column split by
    segment), the ``local`` nuisances (velocity excluded) and the shape
    terms. Returns {"vseg": (nseg,), "vseg_cov": (nseg, nseg),
    "shape": {name: value}, "shape_cov": (m, m), "shape_names": [...],
    "chi2": ...}; velocities [m/s] are the block velocity plus the
    projected segment offset."""
    s = np.asarray(sigma, dtype=np.float64)
    w = np.where(np.isfinite(s) & (s > 0), 1.0 / np.where(s > 0, s, 1.0), 0.0)
    d = np.where(w > 0, np.asarray(data, dtype=np.float64), 0.0)
    loc = [lp for lp in local if lp != (star, "v")]
    # star-frame perturbations of the fine spectrum
    comp = model.factor(star)
    ln = model.grid.lnlam
    others = model.fine_spectrum(params, ctx, skip=(star,))
    S = comp.evaluate(params[star], ln, ctx)
    du = model.grid.step_mps / 1e3  # km/s per sample
    extra, names = [], []
    d1 = np.gradient(S, du)
    d2 = np.gradient(d1, du)
    d3 = np.gradient(d2, du)
    for t in shape_terms:
        if t == "star_broad":
            extra.append(others * d2)
        elif t == "star_skew":
            extra.append(others * d3)
        elif t == "star_depth":
            extra.append(others * (S - 1.0))
        else:
            continue
        names.append(t)
    flux, J, labels, st = model_and_jacobian(
        model, params, ctx, [(star, "v"), *loc], extra_fine=extra
    )
    cols = [J[:, 1:]]
    # LSF shape columns
    lsf_names = []
    for t in shape_terms:
        if not t.startswith("lsf_"):
            continue
        dk = _lsf_shape_kernels(model, params, t, 1e-3)
        if dk is None:
            continue
        c = _cti(model, params, st, st.pixel_factor * _blend(model, st, dkernels=dk))
        cols.append(c[:, None])
        lsf_names.append(t)
    vcol = J[:, 0]
    npx = vcol.size
    edges = np.linspace(0, npx, nseg + 1).astype(int)
    seg = np.zeros((npx, nseg))
    for j in range(nseg):
        seg[edges[j] : edges[j + 1], j] = vcol[edges[j] : edges[j + 1]]
    X = np.concatenate([seg, *cols], axis=1) * w[:, None]
    r = (d - flux) * w
    A = X.T @ X
    try:
        C = np.linalg.inv(A)
    except np.linalg.LinAlgError:
        C = np.linalg.pinv(A)
    coef = C @ (X.T @ r)
    v0 = float(np.atleast_1d(params[star]["v"])[0])
    n_loc = J.shape[1] - 1 - len(names)
    i_shape_star = list(range(nseg + n_loc, nseg + n_loc + len(names)))
    i_shape_lsf = list(range(nseg + n_loc + len(names), X.shape[1]))
    idx = i_shape_lsf + i_shape_star
    all_names = lsf_names + names
    return {
        "vseg": v0 + coef[:nseg],
        "vseg_cov": C[:nseg, :nseg],
        "shape_names": all_names,
        "shape": {n: float(coef[i]) for n, i in zip(all_names, idx, strict=True)},
        "shape_cov": C[np.ix_(idx, idx)],
        "shape_v_cov": C[np.ix_(idx, list(range(nseg)))],
        "chi2": float(r @ r - coef @ (X.T @ r)),
    }


def velocity_shift(v_mps: float) -> float:
    """ln(1 + v / c) (helper for tests)."""
    return float(np.log1p(v_mps / C_MPS))

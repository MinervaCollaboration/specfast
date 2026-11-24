"""Injection tests of stellar-template inference (specfast.doppler.template).

1. MINERVA-like: star + iodine through the LSF, barycentric corrections over
   +/-25 km/s, several orders. Modify mode starts from a DSST-like prior with
   per-order zero-point errors of 40-100 m/s and line depths wrong by 10%;
   infer mode starts flat.
2. G-CLEF-like: no iodine, comb-known wavelengths, star + micro-tellurics
   (< 1% deep, plus a few deep lines) scaled by airmass and water. Tellurics
   modelled as a component (prior with the deep lines only, the micro lines
   learned) against a static 0.98 transmission mask.
3. Detector frame: a static pixel-position map (random + stitching step).
   Ignored, it biases the template and gives barycentric-dependent RV
   errors; supplied as a calibration, it does not.
4. Degeneracy: a tiny barycentric spread is flagged.

The default versions are small (CI); the ``slow`` ones are bigger.
"""

import numpy as np
import pytest
from template_synth import (
    GAMMA,
    PIX_KMS,
    ExposureContext,
    build_model,
    make_blocks,
    make_scene,
    observe,
    star_nodes,
    true_params,
)

from specfast.config import TemplateConfig
from specfast.conventions import C_KMS, C_MPS
from specfast.doppler import LnGrid, Telluric
from specfast.doppler.grid import cubic_interpolate
from specfast.doppler.template import TemplateDegeneracyWarning, infer_template


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def effective(T):
    """Template with its zero point applied, on its own node grid."""
    return cubic_interpolate(T.flux, T.grid, T.grid.lnlam - np.log1p(T.zero_point / C_MPS))


def central(T, berv_kms):
    """Nodes seen by every exposure (inside the pixel range at all BERVs;
    the node grid extends ``berv_kms + 25`` km/s beyond the pixels)."""
    n = T.grid.n
    cut = int(np.ceil((2 * berv_kms + 30.0) / (T.grid.step * C_KMS)))
    return slice(cut, n - cut)


def shift_vs_truth(T, truth, sl):
    """Shift [m/s] of the effective template relative to the truth
    (linearized least squares over the nodes in ``sl``)."""
    g = np.gradient(truth, T.grid.step)[sl] / C_MPS
    d = (effective(T) - truth)[sl]
    return float(-np.sum(g * d) / np.sum(g * g))


def aligned_residual(T, truth, sl, shift, smooth_degree=None):
    """Effective template minus the truth after removing ``shift`` and, if
    asked, a smooth multiplicative polynomial (the continuum degeneracy)."""
    eff = cubic_interpolate(
        T.flux, T.grid, T.grid.lnlam - np.log1p(T.zero_point / C_MPS) + shift / C_MPS
    )[sl]
    tr = truth[sl]
    if smooth_degree is not None:
        t = np.linspace(-1, 1, tr.size)
        coef = np.polynomial.polynomial.polyfit(t, eff / tr, smooth_degree)
        eff = eff / np.polynomial.polynomial.polyval(t, coef)
    return eff - tr


def rv_errors(res, scene):
    v, s = res.velocity_array(range(len(scene.v)))
    return v - scene.v, s


def berv_slope(err, sig, zb):
    """Slope of the RV error against BERV [m/s per km/s] and its 1-sigma."""
    x = zb * C_KMS
    w = 1 / sig**2
    A = np.column_stack([np.ones_like(x), x]) * np.sqrt(w)[:, None]
    cov = np.linalg.inv(A.T @ A)
    coef = cov @ A.T @ (err * np.sqrt(w))
    return coef[1], np.sqrt(cov[1, 1])


# ---------------------------------------------------------------------------
# 1. MINERVA-like
# ---------------------------------------------------------------------------
def minerva_case(n_orders, npix, n_exp, iterations, seed=1):
    sc = make_scene(n_orders=n_orders, npix=npix, n_exp=n_exp, seed=seed)
    data, drift = observe(sc, snr=150, seed=seed + 100)
    rng = np.random.default_rng(seed + 7)
    eps = rng.uniform(40, 100, n_orders) * rng.choice([-1, 1], n_orders)
    eps[0] = abs(eps[0])
    eps[1] = -abs(eps[1])  # a real order pattern, not a common shift
    prior = {}
    for j, o in enumerate(sc.orders):
        c, d = o.lines
        prior[j] = star_nodes(o.tgrid, c, d * (1 + 0.1 * rng.normal(size=d.size)), 3.0, eps[j])
    models = [build_model(sc, o) for o in sc.orders]
    blocks = make_blocks(sc, data, models, np.full(n_exp, GAMMA))
    out = {"scene": sc, "eps": eps, "prior": prior}
    for mode in ("modify", "infer"):
        cfg = TemplateConfig(mode=mode, iterations=iterations)
        out[mode] = infer_template(blocks, prior if mode == "modify" else {}, cfg)
    return out


def check_minerva(case, rv_tol=1.5):
    sc, eps, prior = case["scene"], case["eps"], case["prior"]
    berv = np.max(np.abs(sc.zb)) * C_KMS
    lines = []
    for mode in ("modify", "infer"):
        res = case[mode]
        assert not res.separability.degenerate
        shifts, rms_t, rms_p, pulls = [], [], [], []
        for j, o in enumerate(sc.orders):
            T = res.templates[j]
            sl = central(T, berv)
            shifts.append(shift_vs_truth(T, o.truth, sl))
            deg = None if mode == "modify" else 2
            r = aligned_residual(T, o.truth, sl, shifts[-1], smooth_degree=deg)
            rms_t.append(np.std(r))
            rms_p.append(np.std((prior[j] - o.truth)[sl]))
            pulls.append(r / T.sigma[sl])
        shifts = np.array(shifts)
        pull_rms = np.sqrt(np.mean(np.concatenate(pulls) ** 2))
        first = np.array(list(res.order_offsets_history[0].values()))
        last = np.array(list(res.order_offsets_history[-1].values()))
        err, sig = rv_errors(res, sc)
        rel = err - np.average(err, weights=1 / sig**2)
        slope, slope_sig = berv_slope(err, sig, sc.zb)
        lines.append(
            f"{mode}: template rms err {np.mean(rms_t):.4f} (prior {np.mean(rms_p):.4f}), "
            f"pull rms {pull_rms:.2f}; order zero points vs truth (relative) "
            f"{np.round(shifts - shifts.mean(), 1)} m/s (prior {np.round(eps - eps.mean(), 1)}); "
            f"order offsets first sweep rms {np.std(first):.1f}, last {np.std(last):.2f} m/s; "
            f"RV rel rms {np.std(rel):.2f} vs median sigma {np.median(sig):.2f} m/s, "
            f"BERV slope {slope:.3f} +/- {slope_sig:.3f} m/s per km/s, "
            f"sweeps {res.iterations}"
        )
        # template recovered within noise and better than the prior
        assert np.mean(rms_t) < 0.8 * np.mean(rms_p)
        assert pull_rms < 1.5
        # per-order zero points collapse: the template's orders agree to a
        # few m/s although the prior's were 40-100 m/s apart
        assert np.std(shifts) < 0.15 * np.std(eps)
        assert np.std(last) < 3.0
        if mode == "modify":
            assert np.std(first) > 30.0  # the prior's order pattern was seen
        # RVs: unbiased relative velocities, no BERV dependence
        assert np.std(rel) < rv_tol * np.median(sig)
        assert abs(slope) < 3 * slope_sig
    print("\n" + "\n".join(lines))


def test_minerva_like():
    check_minerva(minerva_case(n_orders=2, npix=250, n_exp=10, iterations=3))


@pytest.mark.slow
def test_minerva_like_slow():
    check_minerva(minerva_case(n_orders=4, npix=400, n_exp=24, iterations=8, seed=2))


# ---------------------------------------------------------------------------
# 2. G-CLEF-like: tellurics modelled vs masked
# ---------------------------------------------------------------------------
def gclef_case(n_orders, npix, n_exp, iterations, seed=3):
    sc = make_scene(
        n_orders=n_orders, npix=npix, n_exp=n_exp, gas_cell=False, tellurics=True, seed=seed
    )
    data, drift = observe(sc, snr=None, truth_telluric=True)
    prior = {j: o.truth for j, o in enumerate(sc.orders)}
    hold = [("wavelength", "coeffs")]  # known from the comb
    cfg = TemplateConfig(mode="modify", iterations=iterations)
    start_v = np.full(n_exp, GAMMA)
    # modelled: the prior knows the deep lines only; micro lines are learned
    modelled = []
    for o in sc.orders:
        corr = LnGrid.covering(np.exp(o.grid.lnlam[0]), np.exp(o.grid.lnlam[-1]), PIX_KMS / 4, 0.0)
        deep = o.telluric_deep
        tel = Telluric(deep.lnlam, deep.tau_dry, deep.tau_water, correction=corr)
        modelled.append(build_model(sc, o, telluric=tel))
    res_mod = infer_template(
        make_blocks(sc, data, modelled, start_v, exclude=hold, drift=drift), prior, cfg
    )
    # masked: no telluric component; static mask where the full atlas
    # (airmass 1, unit water) has T < 0.98
    plain = [build_model(sc, o) for o in sc.orders]
    masks = []
    for o, m in zip(sc.orders, plain, strict=True):
        p = true_params(sc, o, 0, m)
        ln = np.log(m.wavelength.evaluate(p["wavelength"], m.pixels, None))
        t = o.telluric_truth.evaluate({"water": np.ones(1)}, ln, ExposureContext(airmass=1.0))
        masks.append(t < 0.98)
    res_mask = infer_template(
        make_blocks(sc, data, plain, start_v, exclude=hold, drift=drift, masks=masks), prior, cfg
    )
    return sc, res_mod, res_mask, plain, masks


def predicted_mask_bias(sc, res, models, masks):
    """First-order RV error the unmodelled tellurics cause, per exposure:
    the velocity a fit would assign to (model with the true tellurics -
    model without), at the masked solution, weighted like the fit."""
    num = np.zeros(len(sc.v))
    den = np.zeros(len(sc.v))
    i = 0
    for j, o in enumerate(sc.orders):
        m = models[j]
        tel_m = build_model(sc, o, telluric=o.telluric_truth)
        for e in range(len(sc.v)):
            p = {c: dict(d) for c, d in res.block_params[i].items()}
            i += 1
            p["star"]["v"] = np.array([sc.v[e]])
            ctx = ExposureContext(z_bary=float(sc.zb[e]), airmass=float(sc.airmass[e]))
            base = m.evaluate(p, ctx)
            pt = dict(p, telluric={"water": np.array([sc.water[e]])})
            r = tel_m.evaluate(pt, ctx) - base
            p2 = dict(p, star=dict(p["star"], v=np.array([sc.v[e] + 1.0])))
            g = m.evaluate(p2, ctx) - base
            w = np.where(masks[j], 0.0, 1.0 / base)
            num[e] += np.sum(g * w * r)
            den[e] += np.sum(g * w * g)
    return num / den


def check_gclef(case):
    sc, res_mod, res_mask, plain, masks = case
    err_mod, sig = rv_errors(res_mod, sc)
    err_mask, _ = rv_errors(res_mask, sc)
    rel_mod = err_mod - err_mod.mean()
    rel_mask = err_mask - err_mask.mean()
    pred = predicted_mask_bias(sc, res_mask, plain, masks)
    pred -= pred.mean()
    corr = np.corrcoef(pred, rel_mask)[0, 1]
    gain = np.polyfit(pred, rel_mask, 1)[0]
    s_mod = np.polyfit(sc.zb * C_KMS, rel_mod, 1)[0]
    s_mask = np.polyfit(sc.zb * C_KMS, rel_mask, 1)[0]
    s_pred = np.polyfit(sc.zb * C_KMS, pred, 1)[0]
    print(
        f"\nG-CLEF-like (noise-free; photon sigma at S/N~140 would be {np.median(sig):.2f} m/s): "
        f"masked {np.mean([m.mean() for m in masks]):.1%} of pixels; "
        f"RV rms modelled {np.std(rel_mod):.3f} m/s, masked {np.std(rel_mask):.3f} m/s; "
        f"masked vs first-order prediction: r = {corr:.3f}, gain {gain:.2f}; "
        f"BERV slopes modelled {s_mod:+.4f}, masked {s_mask:+.4f}, predicted {s_pred:+.4f} "
        f"m/s per km/s"
    )
    # modelled: unbiased at the 10 cm/s design level (rms over exposures)
    assert np.std(rel_mod) < 0.25
    # masked: a measurable bias, many times the modelled residual ...
    assert np.std(rel_mask) > 1.0
    assert np.std(rel_mask) > 10 * np.std(rel_mod)
    # ... with the sign and size the unmodelled micro-tellurics predict
    assert corr > 0.8
    assert 0.5 < gain < 1.5
    assert np.sign(s_mask) == np.sign(s_pred)


def test_gclef_like_tellurics():
    check_gclef(gclef_case(n_orders=2, npix=250, n_exp=12, iterations=3))


@pytest.mark.slow
def test_gclef_like_tellurics_slow():
    check_gclef(gclef_case(n_orders=3, npix=400, n_exp=24, iterations=6, seed=4))


# ---------------------------------------------------------------------------
# 3. Detector frame
# ---------------------------------------------------------------------------
def detector_case(npix, n_pairs, dx_rms, step_px, seed=4):
    """Exposures in pairs at the same BERV (different RVs): an error fixed to
    the pixels then repeats within each pair."""
    sc = make_scene(n_orders=2, npix=npix, n_exp=2 * n_pairs, gas_cell=False, seed=seed)
    sc.zb[1::2] = sc.zb[0::2]
    rng = np.random.default_rng(seed + 11)
    dx = rng.normal(0, dx_rms, npix + 1)
    dx[npix // 2 :] += step_px  # a stitching step mid-order
    det = {"dx": dx, "response": np.ones(npix)}
    data, drift = observe(sc, snr=None, detector=det)
    prior = {j: o.truth for j, o in enumerate(sc.orders)}
    cfg = TemplateConfig(mode="modify", iterations=3)
    hold = [("wavelength", "coeffs")]
    out = {"scene": sc}
    for name, use in (("ignored", False), ("supplied", True)):
        models = [build_model(sc, o, detector=use) for o in sc.orders]
        blocks = make_blocks(
            sc,
            data,
            models,
            np.full(len(sc.v), GAMMA),
            exclude=hold,
            drift=drift,
            detector=det if use else None,
        )
        out[name] = infer_template(blocks, prior, cfg)
    return out


def test_detector_frame():
    case = detector_case(npix=250, n_pairs=6, dx_rms=5e-3, step_px=0.02)
    sc = case["scene"]
    berv = np.max(np.abs(sc.zb)) * C_KMS
    stats = {}
    for name in ("ignored", "supplied"):
        res = case[name]
        err, _ = rv_errors(res, sc)
        rel = err - err.mean()
        pair_r = np.corrcoef(rel[0::2], rel[1::2])[0, 1] if np.std(rel) > 1e-6 else np.nan
        t_err = np.mean(
            [
                np.std((res.templates[j].flux - o.truth)[central(res.templates[j], berv)])
                for j, o in enumerate(sc.orders)
            ]
        )
        stats[name] = (np.std(rel), pair_r, t_err)
    rep = case["ignored"].separability
    print(
        f"\ndetector (dx rms 5e-3 px + 0.02 px step; BERV range {rep.berv_range_px:.1f} px, "
        f"detector separability {rep.detector_separability:.2f}): "
        + "; ".join(
            f"{k}: RV rms {v[0]:.3g} m/s, same-BERV pair r {v[1]:.3f}, template rms err {v[2]:.2g}"
            for k, v in stats.items()
        )
    )
    ign, sup = stats["ignored"], stats["supplied"]
    # ignored: template biased, RV errors that repeat at the same BERV
    assert ign[0] > 0.2 and ign[1] > 0.9 and ign[2] > 1e-4
    # supplied as a calibration: gone
    assert sup[0] < 0.01 * ign[0] and sup[2] < 0.01 * ign[2]
    assert not rep.detector_degenerate


# ---------------------------------------------------------------------------
# 4. Degeneracy
# ---------------------------------------------------------------------------
def test_tiny_berv_spread_is_flagged():
    sc = make_scene(n_orders=1, npix=150, n_exp=6, berv_kms=0.2, seed=9)
    data, drift = observe(sc, snr=None)
    o = sc.orders[0]
    models = [build_model(sc, o, iodine_correction=True)]
    blocks = make_blocks(sc, data, models, np.full(6, GAMMA))
    with pytest.warns(TemplateDegeneracyWarning) as rec:
        res = infer_template(blocks, {0: o.truth}, TemplateConfig(mode="modify", iterations=1))
    rep = res.separability
    msgs = " | ".join(str(r.message) for r in rec)
    print(
        f"\ndegeneracy: BERV range {rep.berv_range_kms:.2f} km/s ({rep.berv_range_px:.2f} px), "
        f"separability {rep.separability:.4f} at {rep.resolution_kms:.2f} km/s, separable "
        f"below {rep.separable_scale_kms:.3f} km/s; detector separability "
        f"{rep.detector_separability:.4f}"
    )
    assert rep.degenerate and rep.detector_degenerate
    assert rep.separability < 0.01
    assert "observatory-frame" in msgs and "detector-frame" in msgs
    # and a wide spread is not flagged
    wide = make_scene(n_orders=1, npix=150, n_exp=6, berv_kms=25.0, seed=9)
    d2, _ = observe(wide, snr=None)
    b2 = make_blocks(wide, d2, [build_model(wide, wide.orders[0])], np.full(6, GAMMA))
    from specfast.doppler.template import TemplateSolver

    ok = TemplateSolver(b2, {0: wide.orders[0].truth}, TemplateConfig()).separability_report(
        warn=False
    )
    assert not (ok.degenerate or ok.detector_degenerate)

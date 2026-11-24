"""Unit tests of the template-inference building blocks: interpolation,
sparse operators, banded selected inversion, the new components, velocity
splitting and the separability check."""

import dataclasses
import warnings

import numpy as np
import pytest
import scipy.sparse as sp
from template_synth import build_model, ctx_of, make_blocks, make_scene, true_params

from specfast.config import ConfigError, TemplateConfig, parse_config
from specfast.conventions import C_KMS, C_MPS
from specfast.doppler import (
    DetectorMap,
    ExposureContext,
    GriddedTemplate,
    LnGrid,
    Telluric,
    lookup,
)
from specfast.doppler.grid import convolve, cubic_interpolate, cubic_weights, pixel_integrate
from specfast.doppler.template import (
    TemplateDegeneracyWarning,
    TemplateSolver,
    banded_inverse_diagonal,
    check_separability,
    combine_velocities,
    convolution_matrix,
    interpolation_matrix,
    pixel_matrix,
    separability,
    solve_banded_spd,
)


@pytest.fixture(scope="module")
def grid():
    return LnGrid.covering(5480.0, 5520.0, step_kms=0.25, margin_kms=30.0)


def test_cubic_weights_reproduce_quadratics(grid):
    rng = np.random.default_rng(0)
    x = rng.uniform(grid.lnlam[3], grid.lnlam[-4], 500)
    idx, w = cubic_weights(grid, x)
    assert np.allclose(w.sum(axis=-1), 1.0, atol=1e-14)
    t = (grid.lnlam - grid.lnlam[0]) / grid.step
    q = 0.3 + 0.2 * t - 1e-4 * t**2
    tx = (x - grid.lnlam[0]) / grid.step
    assert np.allclose(cubic_interpolate(q, grid, x), 0.3 + 0.2 * tx - 1e-4 * tx**2, rtol=1e-12)
    # passes through the nodes
    assert np.allclose(cubic_interpolate(q, grid, grid.lnlam[5:-5]), q[5:-5], rtol=1e-13)


def test_sparse_operators_match_the_model_functions(grid):
    rng = np.random.default_rng(1)
    vals = 1 + 0.1 * rng.normal(size=grid.n)
    kernel = np.exp(-0.5 * (np.arange(-20, 21) / 6.0) ** 2)
    kernel /= kernel.sum()
    assert np.allclose(convolution_matrix(kernel, grid.n) @ vals, convolve(vals, kernel), 1e-14)
    edges = np.linspace(grid.lnlam[200], grid.lnlam[-200], 101) + 1e-7 * rng.normal(size=101)
    P = pixel_matrix(grid, edges)
    assert np.allclose(P @ vals, pixel_integrate(vals, grid, edges), rtol=1e-12, atol=1e-12)
    tg = LnGrid.covering(5490.0, 5510.0, step_kms=0.3, margin_kms=5.0)
    nodes = rng.normal(size=tg.n)
    x = grid.lnlam[(grid.lnlam > tg.lnlam[2]) & (grid.lnlam < tg.lnlam[-3])]
    assert np.allclose(interpolation_matrix(tg, x) @ nodes, cubic_interpolate(nodes, tg, x))


def test_banded_selected_inverse():
    rng = np.random.default_rng(2)
    n, b = 60, 5
    A = np.zeros((n, n))
    for k in range(b + 1):
        d = rng.normal(size=n - k)
        A += np.diag(d, k) + (np.diag(d, -k) if k else 0)
    A = A @ A.T + n * np.eye(n)  # SPD, bandwidth 2b
    x, var = solve_banded_spd(sp.csr_matrix(A), np.ones(n))
    assert np.allclose(var, np.diag(np.linalg.inv(A)), rtol=1e-10)
    assert np.allclose(A @ x, 1.0)
    g = rng.normal(size=n)
    xc, varc = solve_banded_spd(sp.csr_matrix(A), np.ones(n), constraint=(g, 0.5))
    assert g @ xc == pytest.approx(0.5)
    Ai = np.linalg.inv(A)
    assert np.allclose(varc, np.diag(Ai) - (Ai @ g) ** 2 / (g @ Ai @ g), rtol=1e-8)
    assert banded_inverse_diagonal(np.array([[4.0, 2.0]])) == pytest.approx([1 / 16, 1 / 4])


def test_model_is_linear_in_the_template():
    """A_b s from the solver's sparse operator equals the forward model."""
    sc = make_scene(n_orders=1, npix=120, n_exp=2, seed=3)
    o = sc.orders[0]
    model = build_model(sc, o)
    p = true_params(sc, o, 1, model)
    ctx = ctx_of(sc, 1)
    data = {(e, 0): (np.ones(120), np.ones(120)) for e in range(2)}
    blocks = make_blocks(sc, data, [model], sc.v, perturb=False)
    solver = TemplateSolver(blocks, {0: o.truth}, TemplateConfig())
    M = solver._pixel_operator(1)
    star = model.factor("star")
    W = interpolation_matrix(o.tgrid, star.rest_lnlam(p["star"], o.grid.lnlam, ctx))
    A = M @ sp.diags(model.fine_spectrum(p, ctx, skip=("star",))) @ W
    assert np.allclose(A @ o.truth, model.evaluate(p, ctx), rtol=1e-11)


def test_gridded_template_shift_and_zero_point():
    g = LnGrid.covering(5490.0, 5510.0, step_kms=0.25, margin_kms=50.0)
    flux = 1 - 0.5 * np.exp(-0.5 * ((g.lnlam - np.log(5500.0)) / (3 / C_KMS)) ** 2)
    star = GriddedTemplate(grid=g)
    assert lookup("star", "gridded") is GriddedTemplate
    specs = {s.name: s for s in star.parameters()}
    assert specs["flux"].fixed and specs["zero_point"].fixed and not specs["v"].fixed
    x = g.lnlam[400:-400]
    a = star.evaluate({"v": [100.0], "zero_point": [0.0], "flux": flux}, x, ExposureContext())
    b = star.evaluate({"v": [0.0], "zero_point": [100.0], "flux": flux}, x, ExposureContext())
    assert np.allclose(a, b, atol=1e-12)
    # receding star: line moves red
    c = star.evaluate({"v": [3000.0], "zero_point": [0.0], "flux": flux}, x, ExposureContext())
    centre = lambda f: np.sum(x * (1 - f)) / np.sum(1 - f)  # noqa: E731
    assert (centre(c) - centre(a)) * C_MPS == pytest.approx(2900.0, rel=1e-3)


def test_telluric_scalings():
    ln = np.linspace(8.6, 8.61, 2000)
    td = 0.01 * np.abs(np.sin(ln * 3e4))
    tw = 0.02 * np.abs(np.cos(ln * 2e4))
    tel = Telluric(lnlam=ln, tau_dry=td, tau_water=tw)
    t = tel.evaluate({"water": np.array([1.5])}, ln, ExposureContext(airmass=2.0))
    assert np.allclose(t, np.exp(-(2.0 * td + 1.5 * tw)), rtol=1e-14)
    corr = LnGrid(ln_start=8.6, step=1e-5, n=1001)
    tel2 = Telluric(lnlam=ln, tau_dry=td, tau_water=tw, correction=corr)
    p = {"water": np.array([1.5]), "dtau_dry": np.zeros(1001), "dtau_water": np.zeros(1001)}
    assert np.allclose(tel2.evaluate(p, ln, ExposureContext(airmass=2.0)), t)
    terms = tel2.learned_terms(p, ExposureContext(airmass=2.0))
    assert [(n, s) for n, _, s in terms] == [("dtau_dry", 2.0), ("dtau_water", 1.5)]


def test_detector_map_frame():
    """The identity map changes nothing; a uniform edge offset equals a
    wavelength-solution shift (pixel frame), a response multiplies."""
    sc = make_scene(n_orders=1, npix=100, n_exp=1, seed=5)
    o = sc.orders[0]
    m0 = build_model(sc, o)
    m1 = build_model(sc, o, detector=True)
    p0 = true_params(sc, o, 0, m0)
    p1 = true_params(sc, o, 0, m1)
    ctx = ctx_of(sc, 0)
    assert np.allclose(m1.evaluate(p1, ctx), m0.evaluate(p0, ctx), rtol=1e-14)
    p1["detector"] = {"dx": np.full(101, 0.1), "response": np.full(100, 1.01)}
    # the same as a wavelength polynomial whose pixel origin moved by -0.1 px
    wl = m0.wavelength
    m2 = dataclasses.replace(m0, wavelength=dataclasses.replace(wl, x_center=wl.x_center - 0.1))
    assert np.allclose(m1.evaluate(p1, ctx), 1.01 * m2.evaluate(p0, ctx), rtol=1e-13)
    assert DetectorMap(4).parameters()[0].size == 5


def test_combine_velocities_splits_offsets():
    rng = np.random.default_rng(4)
    vk = rng.normal(0, 30, 10)
    off = np.array([50.0, -20.0, 10.0])
    keys = np.repeat(np.arange(10), 3)
    orders = np.tile(np.arange(3), 10)
    sig = np.tile([1.0, 2.0, 1.0], 10)
    vel, offs = combine_velocities(vk[keys] + off[orders], sig, keys, orders)
    w = np.array([10, 2.5, 10])
    expect = off - np.sum(w * off) / w.sum()
    assert np.allclose([offs[o][0] for o in range(3)], expect, atol=1e-6)
    assert np.allclose([vel[k][0] for k in range(10)] - vk, np.sum(w * off) / w.sum(), atol=1e-6)


def test_separability_check():
    rng = np.random.default_rng(6)
    wide = rng.uniform(-25, 25, 30) / C_KMS
    tiny = rng.uniform(-0.1, 0.1, 30) / C_KMS
    assert separability(wide * C_KMS, 3.5) > 0.9
    assert separability(tiny * C_KMS, 3.5) < 0.01
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ok = check_separability(wide, 3.5, 1.3)
    assert not (ok.degenerate or ok.detector_degenerate or ok.observatory_degenerate)
    assert ok.separable_scale_kms > 10 and ok.berv_range_px > 30
    with pytest.warns(TemplateDegeneracyWarning) as rec:
        bad = check_separability(
            tiny,
            3.5,
            1.3,
            scalings={"iodine.dtau": np.ones(30), "telluric.dtau_dry": np.full(30, 1.2)},
        )
    assert bad.degenerate and bad.detector_degenerate and bad.observatory_degenerate
    assert bad.separable_scale_kms < 0.2 and bad.berv_range_px < 1
    assert len(rec) == 3


def test_template_config():
    cfg = parse_config(
        {
            "schema_version": 1,
            "instrument": "kiwispec",
            "paths": {"output": "out"},
            "doppler": {"star": {"mode": "inferred", "inference": {"mode": "infer"}}},
        }
    )
    t = cfg.doppler.star.inference
    assert t.mode == "infer" and t.oversample == 4.0 and t.strategy == "alternate"
    with pytest.raises(ConfigError, match="oversample"):
        parse_config(
            {
                "schema_version": 1,
                "instrument": "kiwispec",
                "paths": {"output": "out"},
                "doppler": {"star": {"inference": {"oversample": 0}}},
            }
        )

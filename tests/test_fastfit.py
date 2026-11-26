"""Optics wavelength, node-varying Gauss-Hermite LSF, serial CTI, and the
semi-analytic block fitter (specfast.doppler.fastfit)."""

import numpy as np
import pytest
from synth import LAM0, LSF_SIGMA_MPS, NPIX, line_spectrum, make_scene

from specfast.conventions import C_KMS
from specfast.doppler import ExposureContext, ForwardModel, Telluric
from specfast.doppler.fastfit import (
    fit_block_fast,
    model_and_jacobian,
    project_block,
    schur_terms,
)
from specfast.doppler.grid import gh_kernel, kernel_sigma_mps
from specfast.doppler.library import GaussHermiteLSF, OpticsWavelength, SerialCTI


def _rich_model(cti=False, illumination="gh", sampling="average"):
    """The synth scene with the optics wavelength, a GH LSF varying along the
    order with an illumination kernel, a telluric component and optional CTI."""
    sc = make_scene(seed=3)
    m0 = sc.model
    grid = m0.grid
    rng = np.random.default_rng(5)
    t_ln = grid.lnlam
    tau_w = line_spectrum(t_ln, rng.uniform(t_ln[0], t_ln[-1], 20), rng.uniform(0, 0.3, 20), 2.0)
    tell = Telluric(lnlam=t_ln, tau_dry=np.zeros_like(t_ln), tau_water=tau_w)
    disp = LAM0 * 1.3 / C_KMS
    half = 0.5 * (NPIX - 1)
    dist = 0.1 * np.sin(np.arange(NPIX) / 120.0)
    wave = OpticsWavelength(
        degree=2,
        x_center=half,
        x_scale=half,
        base=np.array([LAM0, disp * half, -0.3]),
        base_center=half,
        base_scale=half,
        distortion=dist,
    )
    basis = None
    if illumination == "basis":
        u = np.arange(-21, 22) * 250.0
        b1 = np.exp(-0.5 * (u / 1200) ** 2)
        b1 = b1 / b1.sum() - np.exp(-0.5 * (u / 1600) ** 2) / np.exp(-0.5 * (u / 1600) ** 2).sum()
        basis = np.array([b1 * 0.05, np.gradient(b1) * 0.05])
    lsf = GaussHermiteLSF.for_grid(
        grid,
        LSF_SIGMA_MPS * 1.3,
        pixel_lo=0.0,
        pixel_hi=NPIX - 1.0,
        illumination=illumination,
        basis=basis,
        basis_step_mps=250.0 if basis is not None else None,
    )
    model = ForwardModel(
        wavelength=wave,
        continuum=m0.continuum,
        lsf=lsf,
        factors=(*m0.factors, tell),
        grid=grid,
        pixels=m0.pixels,
        cti=SerialCTI() if cti else None,
        sampling=sampling,
    )
    p = sc.params()
    p["wavelength"] = {"coeffs": np.array([0.01, 0.0, 0.0])}
    p["lsf"] = {
        "map": np.array([LSF_SIGMA_MPS, 0.05, 0.02, 0.01, 0.005, -0.02]),
        "illum": np.zeros(lsf.n_illum),
    }
    p["telluric"] = {"water": np.array([1.0])}
    if cti:
        p["cti"] = SerialCTI.kiwispec_default()
        p["cti"]["signal_scale"] = np.array([1.0])
    return model, p


def test_gh_kernel_reduces_to_gaussian_and_red_tail():
    k = gh_kernel(1500.0, 0.0, 0.0, 250.0, 40)
    assert abs(kernel_sigma_mps(k, 250.0) - 1500.0) < 5.0
    kr = gh_kernel(1500.0, 0.05, 0.0, 250.0, 40)
    u = np.arange(-40, 41) * 250.0
    assert np.sum(u * kr) > 0  # positive h3 = red tail


def test_optics_wavelength_plain_quadratic_without_base():
    w = OpticsWavelength(degree=2, x_center=100.0, x_scale=100.0)
    x = np.array([0.0, 100.0, 200.0])
    lam = w.evaluate({"coeffs": np.array([5000.0, 10.0, 1.0])}, x, ExposureContext())
    assert np.allclose(lam, [5000 - 10 + 1, 5000, 5000 + 10 + 1])


def test_optics_wavelength_distortion_moves_pixels():
    d = np.full(300, 0.5)
    w = OpticsWavelength(degree=1, x_center=0.0, x_scale=1.0, distortion=d)
    lam = w.evaluate({"coeffs": np.array([0.0, 1.0])}, np.array([10.0]), ExposureContext())
    assert lam[0] == pytest.approx(10.5)


def test_node_lsf_constant_map_matches_single_kernel():
    model, p = _rich_model()
    p["lsf"]["map"] = np.array([LSF_SIGMA_MPS, 0, 0, 0, 0, 0])
    ks, w = model.node_kernels(p, ExposureContext())
    assert len(ks) == 5 and w.shape == (5, NPIX)
    assert np.allclose(w.sum(axis=0), 1.0)
    for k in ks:
        assert np.allclose(k, ks[0])


@pytest.mark.parametrize("cti", [False, True])
@pytest.mark.parametrize("illumination", ["gh", "basis"])
@pytest.mark.parametrize("sampling", ["average", "point"])
def test_jacobian_matches_finite_differences(cti, illumination, sampling):
    model, p = _rich_model(cti=cti, illumination=illumination, sampling=sampling)
    ctx = ExposureContext(z_bary=1e-5, airmass=1.2)
    free = [
        ("star", "v"),
        ("wavelength", "coeffs"),
        ("iodine", "k"),
        ("continuum", "coeffs"),
        ("telluric", "water"),
        ("lsf", "illum"),
    ]
    f0, J, labels, _ = model_and_jacobian(model, p, ctx, free)
    assert np.allclose(f0, model.evaluate(p, ctx), rtol=1e-12)
    for col, (c, name, j) in enumerate(labels):
        val = np.atleast_1d(p[c][name]).astype(float)
        h = {"v": 2.0, "k": 1e-4, "water": 1e-3, "illum": 1e-3}.get(name, 1e-4)
        if c == "continuum":
            h = 1.0
        vp, vm = val.copy(), val.copy()
        vp[j] += h
        vm[j] -= h
        pp = {**p, c: {**p[c], name: vp}}
        pm = {**p, c: {**p[c], name: vm}}
        fd = (model.evaluate(pp, ctx) - model.evaluate(pm, ctx)) / (2 * h)
        scale = np.max(np.abs(fd)) + 1e-30
        # CTI columns use the linearized operator (loss frozen): ~1e-3 of it
        tol = 2e-3 if cti else (5e-4 if sampling == "point" else 2e-4)
        assert np.max(np.abs(J[:, col] - fd)) / scale < tol, (c, name, j)


def test_fast_fit_recovers_velocity_and_projection():
    model, p = _rich_model()
    ctx = ExposureContext(z_bary=2e-5, airmass=1.1)
    truth = {c: dict(d) for c, d in p.items()}
    truth["star"] = {"v": np.array([123.4])}
    data = model.evaluate(truth, ctx)
    rng = np.random.default_rng(0)
    sigma = np.sqrt(np.abs(data))
    noisy = data + rng.normal(0, 1, data.size) * sigma
    start = {c: dict(d) for c, d in truth.items()}
    start["star"] = {"v": np.array([0.0])}
    start["wavelength"] = {"coeffs": np.array([0.02, 0.0, 0.0])}
    start["iodine"] = {"k": np.array([1.05])}
    start["continuum"] = {"coeffs": truth["continuum"]["coeffs"] * 1.03}
    free = [("star", "v"), ("wavelength", "coeffs"), ("iodine", "k"), ("continuum", "coeffs")]
    sol = fit_block_fast(model, noisy, sigma, ctx, start, free)
    v, sv = sol.value_sigma("star", "v")
    assert sol.converged
    assert abs(v - 123.4) < 4 * sv
    # noise-free: exact
    sol0 = fit_block_fast(model, data, sigma, ctx, start, free)
    assert abs(sol0.value_sigma("star", "v")[0] - 123.4) < 1e-3
    pr = project_block(model, sol0.params, ctx, data, sigma, free, nseg=4)
    assert np.allclose(pr["vseg"], 123.4, atol=1e-2)
    assert set(pr["shape"]) >= {"lsf_width", "lsf_h3", "star_broad", "star_depth"}
    for val in pr["shape"].values():
        assert abs(val) < 1e-4
    # a shared water step from the Schur complement recovers a water error
    off = {c: dict(d) for c, d in sol0.params.items()}
    off["telluric"] = {"water": np.array([1.2])}
    H, b, lab, _ = schur_terms(model, off, ctx, data, sigma, free, [("telluric", "water")])
    dw = np.linalg.solve(H, b)
    assert abs(1.2 + dw[0] - 1.0) < 0.02


@pytest.mark.parametrize("sampling", ["average", "point"])
def test_template_operator_matches_model(sampling):
    from specfast.doppler.template import block_pixel_operator

    model, p = _rich_model(sampling=sampling)
    ctx = ExposureContext()
    op = block_pixel_operator(model, p, ctx, include_cti=False)
    f = model.evaluate(p, ctx)
    assert np.max(np.abs(op @ model.fine_spectrum(p, ctx) - f)) < 1e-10 * np.max(f)


def test_linear_iodine_scaling():
    from specfast.doppler import IodineCell

    ln = np.linspace(8.6, 8.7, 50)
    t = np.linspace(0.3, 1.0, 50)
    a = IodineCell.from_transmission(ln, t, scaling="linear")
    out = a.evaluate({"k": np.array([0.5])}, ln, ExposureContext())
    assert np.allclose(out, 1 + 0.5 * (t - 1))


def test_iodine_transmission_interpolation():
    from specfast.doppler import IodineCell

    ln = np.linspace(8.6, 8.7, 50)
    t = np.linspace(0.3, 1.0, 50)
    a = IodineCell.from_transmission(ln, t)  # default: linear in transmission
    b = IodineCell.from_transmission(ln, t, interp="tau")
    x = 0.5 * (ln[1:] + ln[:-1])
    ka = {"k": np.array([1.0])}
    assert np.allclose(a.evaluate(ka, ln, ExposureContext()), t)
    assert np.allclose(a.evaluate(ka, x, ExposureContext()), 0.5 * (t[1:] + t[:-1]))
    assert not np.allclose(b.evaluate(ka, x, ExposureContext()), 0.5 * (t[1:] + t[:-1]))

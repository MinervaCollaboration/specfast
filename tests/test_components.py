"""Component interface: declarations, purity, registry, Doppler sign."""

import numpy as np
import pytest

from specfast.conventions import C_KMS, C_MPS
from specfast.doppler import (
    REGISTRY,
    ExposureContext,
    ForwardModel,
    Frame,
    GaussianLSF,
    IodineCell,
    LnGrid,
    NoGasCell,
    ParameterLayout,
    PolynomialContinuum,
    PolynomialWavelength,
    Scope,
    StarTemplate,
    lookup,
)
from specfast.doppler.components import Component


def _one_line_model(npix=400, lam0=5500.0, depth=0.8):
    grid = LnGrid.covering(lam0 - 5, lam0 + 5, step_kms=0.25, margin_kms=100.0)
    t_ln = np.arange(grid.lnlam[0] - 0.001, grid.lnlam[-1] + 0.001, 0.02 / C_KMS)
    t_flux = 1 - depth * np.exp(-0.5 * ((t_ln - np.log(lam0)) / (3 / C_KMS)) ** 2)
    disp = lam0 * 1.3 / C_KMS
    half = 0.5 * (npix - 1)
    model = ForwardModel(
        wavelength=PolynomialWavelength.for_pixels(1, npix),
        continuum=PolynomialContinuum.for_pixels(0, npix),
        lsf=GaussianLSF.for_grid(grid, 1500.0),
        factors=(StarTemplate(lnlam=t_ln, flux=t_flux), NoGasCell()),
        grid=grid,
        pixels=np.arange(npix, dtype=float),
    )
    params = {
        "wavelength": {"coeffs": np.array([lam0, disp * half])},
        "continuum": {"coeffs": np.array([1.0])},
        "lsf": {"sigma": np.array([1500.0])},
        "star": {"v": np.array([0.0])},
    }
    return model, params, disp


def _line_centre_angstrom(model, params, ctx, disp):
    f = model.evaluate(params, ctx)
    a = 1 - f
    x = np.sum(model.pixels * a) / a.sum()
    lam0, slope = params["wavelength"]["coeffs"]
    return lam0 + slope * (x - model.wavelength.x_center) / model.wavelength.x_scale


@pytest.mark.parametrize("v", [+10_000.0, -7_000.0])
def test_doppler_sign_in_model(v):
    """A receding star (v > 0) puts its line at a longer wavelength."""
    model, p, disp = _one_line_model()
    ctx = ExposureContext()
    lam_rest = _line_centre_angstrom(model, p, ctx, disp)
    p["star"]["v"] = np.array([v])
    lam_obs = _line_centre_angstrom(model, p, ctx, disp)
    assert np.sign(lam_obs - lam_rest) == np.sign(v)
    assert (lam_obs / lam_rest - 1) * C_MPS == pytest.approx(v, rel=2e-3)


def test_barycentric_correction_sign():
    """z_B > 0 (observer approaching the star) blueshifts the observed line:
    the same barycentric v with larger z_B sits bluer."""
    model, p, disp = _one_line_model()
    zb = 20.0 / C_KMS
    lam_a = _line_centre_angstrom(model, p, ExposureContext(z_bary=0.0), disp)
    lam_b = _line_centre_angstrom(model, p, ExposureContext(z_bary=zb), disp)
    assert (lam_b / lam_a - 1) == pytest.approx(1 / (1 + zb) - 1, rel=2e-3)


def test_registry_and_protocol():
    assert set(REGISTRY) >= {"wavelength", "continuum", "lsf", "star", "reference"}
    assert lookup("reference", "iodine") is IodineCell
    assert lookup("reference", "none") is NoGasCell
    with pytest.raises(KeyError):
        lookup("reference", "thorium")
    model, _, _ = _one_line_model()
    for comp in model.components:
        assert isinstance(comp, Component)
        assert isinstance(comp.frame, Frame)


def test_declared_scopes_and_frames():
    model, _, _ = _one_line_model()
    specs = {(c, s.name): s for c, s in model.parameter_specs()}
    assert specs[("star", "v")].scope == Scope.EXPOSURE | Scope.SEGMENT
    assert specs[("star", "v")].unit == "m/s"
    assert specs[("lsf", "sigma")].fixed
    assert Scope.ORDER in specs[("wavelength", "coeffs")].scope
    assert model.factors[0].frame is Frame.STELLAR_REST
    assert Scope.GLOBAL == Scope(0)


def test_evaluate_is_pure():
    model, p, _ = _one_line_model()
    ctx = ExposureContext(z_bary=1e-5)
    snapshot = {c: {k: v.copy() for k, v in d.items()} for c, d in p.items()}
    a = model.evaluate(p, ctx)
    b = model.evaluate(p, ctx)
    assert np.array_equal(a, b)
    for c, d in p.items():
        for k, v in d.items():
            assert np.array_equal(v, snapshot[c][k])
    star = model.factors[0]
    with pytest.raises(ValueError):
        star.flux[0] = 2.0  # static data is read-only


def test_iodine_optical_depth_scaling():
    ln = np.linspace(8.6, 8.61, 1000)
    tau = np.abs(np.sin(ln * 1e4))
    cell = IodineCell(lnlam=ln, tau=tau)
    ctx = ExposureContext()
    t1 = cell.evaluate({"k": np.array([1.0])}, ln, ctx)
    t2 = cell.evaluate({"k": np.array([2.0])}, ln, ctx)
    assert np.allclose(t2, t1**2, rtol=1e-14)
    assert np.allclose(cell.evaluate({"k": np.array([0.0])}, ln, ctx), 1.0)
    back = IodineCell.from_transmission(ln, t1)
    assert np.allclose(back.tau, tau, atol=1e-12)
    assert np.array_equal(NoGasCell().evaluate({}, ln, ctx), np.ones_like(ln))
    assert NoGasCell().parameters() == ()


def test_layout_round_trip():
    model, p, _ = _one_line_model()
    layout = ParameterLayout.free(model)
    assert ("lsf", "sigma", 1) not in layout.entries  # fixed
    theta = layout.pack(p)
    assert layout.size == theta.size == 2 + 1 + 1
    q = layout.unpack(theta + 1.0, p)
    assert q["star"]["v"][0] == p["star"]["v"][0] + 1.0
    assert q["lsf"] is not p["lsf"] and np.array_equal(q["lsf"]["sigma"], p["lsf"]["sigma"])
    with pytest.raises(ValueError):
        layout.unpack(np.zeros(3), p)


def test_iodine_cell_average_is_grid_phase_invariant():
    # an atlas with lines narrower than the grid step: point sampling at the
    # grid nodes aliases (the result depends on where the nodes fall); the
    # cell average does not, to well below the photon limit of a fit
    from specfast.doppler.library import IodineCell

    rng = np.random.default_rng(3)
    ln = np.arange(np.log(5400.0), np.log(5410.0), 0.01 / C_KMS)
    c = rng.uniform(ln[0], ln[-1], 200)
    tau = np.zeros_like(ln)
    for x in c:
        tau += rng.uniform(0.05, 0.5) * np.exp(-0.5 * ((ln - x) / (0.25 / C_KMS)) ** 2)
    step = 0.25 / C_KMS
    probe = np.arange(np.log(5402.0), np.log(5408.0), 2.0 / C_KMS)  # smooth read-out points

    def smooth_at(cell, phase):
        g = np.arange(np.log(5401.0) + phase * step, np.log(5409.0), step)
        t = cell.evaluate({"k": np.array([1.0])}, g, None)
        # read out through a 1.5 km/s Gaussian (an LSF), the way a fit sees it
        w = np.exp(-0.5 * ((probe[:, None] - g[None, :]) / (1.5 / C_KMS)) ** 2)
        return (w @ t) / w.sum(axis=1)

    point = IodineCell(lnlam=ln, tau=tau)
    cellavg = IodineCell(lnlam=ln, tau=tau, supersample=8)
    d_point = np.max(np.abs(smooth_at(point, 0.0) - smooth_at(point, 0.5)))
    d_cell = np.max(np.abs(smooth_at(cellavg, 0.0) - smooth_at(cellavg, 0.5)))
    assert d_cell < 0.1 * d_point
    with pytest.raises(ValueError):
        IodineCell(lnlam=ln, tau=tau, supersample=0)
    with pytest.raises(ValueError):
        IodineCell(lnlam=ln, tau=tau, interp="sinc")
    # a cubic spline in optical depth: between the samples, closer to the
    # truth than linear interpolation when the atlas is coarsely sampled
    coarse = slice(None, None, 25)  # 0.25 km/s samples of 0.25 km/s lines
    probe_ln = ln[12::25][:-1]
    truth = np.exp(-tau[12::25][:-1])
    errs = {}
    for interp in ("tau", "transmission", "cubic"):
        cell = IodineCell(lnlam=ln[coarse], tau=tau[coarse], interp=interp)
        errs[interp] = np.sqrt(
            np.mean((cell.evaluate({"k": np.ones(1)}, probe_ln, None) - truth) ** 2)
        )
    assert errs["cubic"] < min(errs["tau"], errs["transmission"])

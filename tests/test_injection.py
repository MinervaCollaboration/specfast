"""Acceptance test: injection-recovery on spectra made by the forward model.

Synthetic star and synthetic iodine lines; velocities of a K = 50 m/s orbit
(plus a -1234.5 m/s systemic velocity) are injected with barycentric
corrections up to +/-30 km/s, the wavelength solution, continuum, iodine
strength and velocity are fitted per exposure from a perturbed start, and
the orbit is refitted to the recovered velocities.
"""

import numpy as np
import pytest
from synth import (
    ExposureContext,
    exposures,
    fit_block,
    index_of,
    make_scene,
    noise_free_run,
    perturbed_start,
    recover_K,
)

K = 50.0


@pytest.fixture(scope="module")
def scene():
    return make_scene()


def _report(v_true, v_fit, phase):
    gamma, ks, kc = recover_K(v_fit, phase)
    return np.hypot(ks, kc), gamma, np.max(np.abs(v_fit - v_true))


def test_noise_free_recovery(scene):
    v_true, v_fit, phase = noise_free_run(scene, n=8, K=K)
    k_fit, gamma, worst = _report(v_true, v_fit, phase)
    print(f"noise-free: K_fit/K - 1 = {k_fit / K - 1:.2e}, max |dv| = {worst:.2e} m/s")
    assert abs(k_fit / K - 1) <= 1e-3
    assert worst <= 1e-3 * K
    assert gamma == pytest.approx(-1234.5, abs=1e-3 * K)


def test_noise_free_recovery_finer_truth(scene):
    """Truth generated on a 5x finer grid than the fit uses: the model's
    own discretization must not leak a barycentric-dependent error."""
    truth = make_scene(step_kms=0.05)
    v_true, zb, phase = exposures(8, seed=11, K=K)
    v_fit = []
    for v, z in zip(v_true, zb, strict=True):
        ctx = ExposureContext(z_bary=z)
        data = truth.model.evaluate(truth.params(v=v), ctx)
        best, *_ = fit_block(scene.model, data, np.ones_like(data), ctx, perturbed_start(scene))
        v_fit.append(best["star"]["v"][0])
    k_fit, gamma, worst = _report(v_true, np.array(v_fit), phase)
    print(f"finer truth: K_fit/K - 1 = {k_fit / K - 1:.2e}, max |dv| = {worst:.2e} m/s")
    assert abs(k_fit / K - 1) <= 1e-3
    assert worst <= 1e-3 * K


def test_noisy_pulls(scene):
    """Photon + read noise at S/N ~ 100 per pixel: velocity pulls have unit
    variance and zero mean, and chi2 per degree of freedom is ~1.

    Seeds are fixed; the bounds are 4 sigma of the sampling scatter for n
    draws (750 draws over five seeds gave pull mean 0.02 +/- 0.04, std 0.99).
    """
    n = 100
    rng = np.random.default_rng(2026)
    v_true, zb, phase = exposures(n, seed=7, K=K)
    pulls, chi2, sig_v = [], [], []
    for v, z in zip(v_true, zb, strict=True):
        ctx = ExposureContext(z_bary=z)
        clean = scene.model.evaluate(scene.params(v=v), ctx)
        sigma = np.sqrt(clean + 5.0**2)
        data = clean + rng.normal(0.0, sigma)
        best, cov, layout, res = fit_block(scene.model, data, sigma, ctx, perturbed_start(scene))
        i = index_of(layout, "star", "v")
        s = np.sqrt(cov[i, i])
        sig_v.append(s)
        pulls.append((best["star"]["v"][0] - v) / s)
        chi2.append(2 * res.cost / (data.size - layout.size))
    pulls = np.array(pulls)
    print(f"noisy: sigma_v ~ {np.median(sig_v):.2f} m/s, pull mean {pulls.mean():.2f}, "
          f"pull std {pulls.std(ddof=1):.2f}, chi2_r {np.mean(chi2):.3f}")
    assert abs(pulls.mean()) < 4 / np.sqrt(n)
    assert abs(pulls.std(ddof=1) - 1) < 4 / np.sqrt(2 * (n - 1))
    dof = scene.model.pixels.size - 9
    assert abs(np.mean(chi2) - 1) < 4 * np.sqrt(2 / (n * dof))


def test_no_gas_cell_with_known_wavelength():
    """Without a gas cell the velocity is degenerate with the wavelength zero
    point, so the wavelength comes from elsewhere (a simultaneous reference)
    and is held fixed; the velocity is then recovered."""
    sc = make_scene(gas_cell=False)
    v_true, zb, _ = exposures(4, seed=5, K=K)
    for v, z in zip(v_true, zb, strict=True):
        ctx = ExposureContext(z_bary=z)
        data = sc.model.evaluate(sc.params(v=v), ctx)
        start = sc.params(v=0.0)
        start["continuum"]["coeffs"] = start["continuum"]["coeffs"] * 1.02
        best, *_ = fit_block(sc.model, data, np.ones_like(data), ctx, start,
                             exclude=[("wavelength", "coeffs")])
        assert best["star"]["v"][0] == pytest.approx(v, abs=1e-3 * K)

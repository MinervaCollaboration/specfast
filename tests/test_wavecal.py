"""specfast.wavecal: line fits and the stable shared-fibre wavelength model.

Synthetic arcs only: a known dispersion law m*lambda = P(x, m), two fibres
displaced by a smooth offset, per-exposure low-order drifts; the fit must
recover drifts, offsets and wavelengths.
"""

import numpy as np
import pytest
from scipy.special import erf

from specfast.wavecal import (
    LineMeasurements,
    Scaling,
    basis,
    fit_drift,
    fit_lines,
    fit_stable_model,
    identify_lines,
)

SC = Scaling(0.0, 4095.0, 60.0, 80.0)
ORDERS = np.arange(60, 81)
C = 299792458.0


def true_mlam(x, m):
    t = SC.t(x)
    u = SC.u(m)
    return 4.66e5 + 2.0e3 * t + 40.0 * t**2 + 3.0 * t**3 + 25.0 * u * t + 8.0 * u


def true_offset(fibre, x, m):
    """Fibre f position minus fibre 1 position, same wavelength [px]."""
    s = {0: 6.0, 2: -6.5}[fibre]
    return s * (1 + 0.3 * SC.t(x) + 0.2 * SC.u(m))


def x_of_lambda_ref(lam, m):
    """Invert the true law for the reference fibre by bisection."""
    lo = np.full(np.shape(lam), -200.0)
    hi = np.full(np.shape(lam), 4300.0)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f = true_mlam(mid, m) / m - lam
        lo = np.where(f < 0, mid, lo)
        hi = np.where(f < 0, hi, mid)
    return 0.5 * (lo + hi)


def make_catalogue(rng, n_per_order=40):
    lam = []
    for m in ORDERS:
        x = np.sort(rng.uniform(100, 4000, n_per_order))
        lam.append(true_mlam(x, m) / m)
    return np.sort(np.concatenate(lam))


def synth_measurements(rng, cat, drifts, lit, noise=0.01):
    rows = []
    for e, (d, fibres) in enumerate(zip(drifts, lit, strict=True)):
        for m in ORDERS:
            lam_lo = true_mlam(0.0, m) / m
            lam_hi = true_mlam(4095.0, m) / m
            idx = np.where((cat > lam_lo) & (cat < lam_hi))[0]
            x1 = x_of_lambda_ref(cat[idx], m)
            for f in fibres:
                x = x1 + (true_offset(f, x1, m) if f != 1 else 0.0)
                x = x + basis(((0, 0), (1, 0), (0, 1), (1, 1)), SC.t(x), SC.u(m)) @ d
                ok = (x > 20) & (x < 4075)
                xe = np.full(ok.sum(), noise)
                rows.append(
                    (
                        idx[ok],
                        np.full(ok.sum(), f),
                        np.full(ok.sum(), e),
                        np.full(ok.sum(), m),
                        x[ok] + rng.normal(0, noise, ok.sum()),
                        xe,
                    )
                )
    cols = [np.concatenate([r[k] for r in rows]) for k in range(6)]
    return LineMeasurements(*cols)


def pixel_gaussian(x, x0, s, amp):
    return (
        amp
        * 0.5
        * (erf((x + 0.5 - x0) / (s * np.sqrt(2))) - erf((x - 0.5 - x0) / (s * np.sqrt(2))))
    )


def test_fit_lines_recovers_centroids_with_unit_pulls():
    rng = np.random.default_rng(1)
    n = 4096
    x = np.arange(n, dtype=float)
    true = np.arange(50, 4050, 37.3) + rng.uniform(-0.5, 0.5, 108)
    pulls = []
    for _ in range(20):
        f = np.full(n, 100.0)
        for x0 in true:
            f += pixel_gaussian(x, x0, 1.5, 5000.0)
        sig = np.sqrt(f + 25.0)
        data = f + rng.normal(0, 1, n) * sig
        lf = fit_lines(
            data, sig, true + rng.uniform(-0.6, 0.6, true.size), half_width=5, sigma_guess=1.3
        )
        assert lf.ok.all()
        pulls.append((lf.x0 - true) / lf.x0_err)
        assert abs(np.median(lf.sigma) - 1.5) < 0.02
        assert np.allclose(lf.sigma, 1.5, atol=0.2)
    p = np.concatenate(pulls)
    assert abs(np.mean(p)) < 0.1
    assert 0.85 < np.std(p) < 1.15


def test_fit_lines_flags_masked_and_empty_windows():
    n = 200
    x = np.arange(n, dtype=float)
    f = 10.0 + pixel_gaussian(x, 100.2, 1.5, 3000.0)
    sig = np.sqrt(f)
    sig[40:60] = np.inf
    lf = fit_lines(f, sig, np.array([100.0, 50.0, 150.0]), half_width=5)
    assert lf.ok[0] and abs(lf.x0[0] - 100.2) < 1e-3
    assert not lf.ok[1]  # masked window
    assert not lf.ok[2]  # no line there


def test_identify_lines_drops_blends_and_edges():
    wave = np.linspace(5000.0, 5100.0, 4096)
    disp = wave[1] - wave[0]
    cat = np.array([4990.0, 5000.05, 5020.0, 5020.0 + 3 * disp, 5050.0, 5099.99, 5200.0])
    idx, xp = identify_lines(wave, cat, min_separation_px=5.0, edge_px=8)
    assert list(idx) == [4]
    assert abs(xp[0] - (5050.0 - 5000.0) / disp) < 1e-6


@pytest.fixture(scope="module")
def synthetic():
    rng = np.random.default_rng(7)
    cat = make_catalogue(rng)
    nexp = 8
    drifts = rng.normal(0, [0.3, 0.05, 0.05, 0.02], size=(nexp, 4))
    lit = [(0, 1)] * 4 + [(1, 2)] * 4  # two arc configurations, like NRES
    meas = synth_measurements(rng, cat, drifts, lit)
    model = fit_stable_model(
        meas,
        cat,
        SC,
        ref_fibre=1,
        drift="bilinear",
        disp_deg=(4, 2),
        offset_deg=(1, 1),
        offset_order_constants=False,
    )
    return cat, drifts, model


def test_stable_model_recovers_relative_drifts(synthetic):
    _, drifts, model = synthetic
    d_true = drifts - drifts.mean(axis=0)
    assert np.allclose(model.drift, d_true, atol=2e-3)
    assert model.rms_px < 0.012


def test_stable_model_shares_one_dispersion_law_across_fibres(synthetic):
    _, drifts, model = synthetic
    mean_d = drifts.mean(axis=0)
    for f in (0, 1, 2):
        for m in (62, 70, 78):
            x = np.linspace(200, 3900, 7)
            # truth: the fibre-f pixel that sees lambda, at the mean drift
            lam_model = model.wavelength(f, m, x)
            x_b = x - basis(model.drift_terms, SC.t(x), SC.u(m)) @ mean_d
            x1 = x_b.copy()
            if f != 1:
                for _ in range(20):  # x_b = x1 + offset(x1)
                    x1 = x_b - true_offset(f, x1, m)
            lam_true = true_mlam(x1, m) / m
            assert np.max(np.abs(lam_model / lam_true - 1)) * C < 3.0  # m/s
    assert set(model.offsets) == {0, 2}


def test_fit_drift_recovers_a_frame_shift(synthetic):
    cat, drifts, model = synthetic
    rng = np.random.default_rng(3)
    d = drifts.mean(axis=0) + np.array([0.12, 0.0, 0.0, 0.0])
    meas = synth_measurements(rng, cat, [d], [(1,)], noise=0.05)
    c, ce, n, rms = fit_drift(
        model, meas.line, meas.fibre, meas.order, meas.x, meas.x_err, terms="shift"
    )
    assert n > 500
    assert abs(c[0] - 0.12) < 4 * ce[0] + 2e-3
    assert np.all(c[1:] == 0)


def test_too_few_lines_raises():
    meas = LineMeasurements(*(np.zeros(3) for _ in range(6)))
    with pytest.raises((ValueError, IndexError)):
        fit_stable_model(meas, np.array([5000.0]), SC)

import numpy as np
import pytest

from specfast import conventions as cv


def test_receding_is_redshift():
    # positive velocity -> z > 0 -> longer wavelengths
    assert cv.velocity_to_redshift(1000.0) > 0
    assert cv.relativistic_doppler_factor(1000.0) > 1.0
    assert cv.doppler_factor(1000.0) < 1.0  # S evaluated at lambda_obs * D


def test_relativistic_factor_matches_exact_form():
    v = 0.1 * cv.C_MPS
    assert cv.relativistic_doppler_factor(v) == pytest.approx(np.sqrt(1.1 / 0.9), rel=1e-15)
    # first order: 1 + v/c
    assert cv.relativistic_doppler_factor(30.0) == pytest.approx(1 + 30 / cv.C_MPS, rel=1e-14)


def test_composition_is_multiplicative():
    z1, z2 = 1e-4, -3e-5
    assert cv.compose_redshifts(z1, z2) == pytest.approx((1 + z1) * (1 + z2) - 1, rel=1e-14)
    # not additive at second order
    assert abs(cv.compose_redshifts(z1, z2) - (z1 + z2)) > 1e-10


def test_barycentric_round_trip():
    v_bary, z_b = -1234.5, 25e3 / cv.C_MPS
    z_meas = cv.measured_redshift(v_bary, z_b)
    # float64 (1 + z) resolves c * 2.2e-16 = 7e-8 m/s
    assert cv.barycentric_velocity(z_meas, z_b) == pytest.approx(v_bary, abs=2e-7)
    # an observer moving toward the star (z_B > 0 corrects a blueshift)
    assert z_meas < v_bary / cv.C_MPS


def test_ln_shift_consistent_with_factor():
    v, z_b = 5000.0, -1e-4
    assert cv.ln_shift(v, z_b) == pytest.approx(-np.log(cv.doppler_factor(v, z_b)), abs=1e-16)

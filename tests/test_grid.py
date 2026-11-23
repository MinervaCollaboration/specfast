"""Unit tests of the fine-grid operators: convolution and pixel integration."""

import math

import numpy as np
import pytest

from specfast.conventions import C_KMS, C_MPS
from specfast.doppler.grid import LnGrid, convolve, gaussian_kernel, integral_at, pixel_integrate


@pytest.fixture
def grid():
    return LnGrid.covering(5480.0, 5520.0, step_kms=0.25, margin_kms=100.0)


def _gauss(grid, centre, sigma_kms, depth=1.0):
    s = sigma_kms / C_KMS
    return depth * np.exp(-0.5 * ((grid.lnlam - centre) / s) ** 2)


def test_grid_covers_range(grid):
    ln = grid.lnlam
    assert ln[0] <= np.log(5480.0) - 100 / C_KMS + 1e-15
    assert ln[-1] >= np.log(5520.0) + 100 / C_KMS - 1e-15
    assert grid.step_mps == pytest.approx(250.0, rel=1e-12)


def test_convolution_conserves_flux(grid):
    mid = grid.lnlam[grid.n // 2]
    line = _gauss(grid, mid, 0.5) + _gauss(grid, mid + 20 / C_KMS, 0.2, 0.3)
    k = gaussian_kernel(1500.0, grid.step_mps, 40)
    assert k.sum() == pytest.approx(1.0, abs=1e-15)
    assert convolve(line, k).sum() == pytest.approx(line.sum(), rel=1e-13)


@pytest.mark.parametrize("sigma_mps", [800.0, 1500.0, 3000.0])
def test_convolution_width(grid, sigma_mps):
    """A delta function becomes a Gaussian of the requested width in velocity,
    whatever the wavelength (constant in km/s)."""
    for i in (grid.n // 4, grid.n // 2):
        delta = np.zeros(grid.n)
        delta[i] = 1.0
        out = convolve(delta, gaussian_kernel(sigma_mps, grid.step_mps, 300))
        v = (grid.lnlam - grid.lnlam[i]) * C_MPS
        mean = np.sum(v * out) / out.sum()
        width = np.sqrt(np.sum((v - mean) ** 2 * out) / out.sum())
        assert mean == pytest.approx(0.0, abs=1e-6)
        assert width == pytest.approx(sigma_mps, rel=1e-6)
    # widths add in quadrature for a broadened line
    s1 = 2.0
    line = _gauss(grid, grid.lnlam[grid.n // 2], s1)
    out = convolve(line, gaussian_kernel(1500.0, grid.step_mps, 300))
    v = (grid.lnlam - grid.lnlam[grid.n // 2]) * C_KMS
    w = np.sqrt(np.sum(v**2 * out) / out.sum())
    assert w == pytest.approx(np.hypot(s1, 1.5), rel=1e-6)


def test_pixel_integration_conserves_flux(grid):
    mid = grid.lnlam[grid.n // 2]
    s = 1.0 / C_KMS
    f = _gauss(grid, mid, 1.0)
    edges = np.log(5494.0) + np.arange(0, 400) * (1.3 / C_KMS) * (1 + 1e-3 * np.arange(400) / 400)
    pix = pixel_integrate(f, grid, edges)
    total = np.sum(pix * np.diff(edges))
    # exactly the interpolant's integral between the outer edges ...
    a = integral_at(f, grid, edges[[0, -1]])
    assert total == pytest.approx(a[1] - a[0], rel=1e-12)
    # ... which is the analytic integral of the line
    assert total == pytest.approx(s * math.sqrt(2 * math.pi), rel=1e-9)


def test_pixel_integration_is_not_point_sampling():
    """A line narrower than a pixel: each pixel holds its mean, not the
    value at its centre (analytic means via erf). The grid resolves the line
    (as the LSF-broadened spectrum always is) for an accurate comparison."""
    grid = LnGrid.covering(5490.0, 5510.0, step_kms=0.1, margin_kms=50.0)
    mid = grid.lnlam[grid.n // 2] + 0.37 * grid.step
    sig = 0.6 / C_KMS
    f = np.exp(-0.5 * ((grid.lnlam - mid) / sig) ** 2)
    pw = 1.3 / C_KMS
    edges = mid - 3.3 * pw + pw * np.arange(8)
    pix = pixel_integrate(f, grid, edges)

    def cdf(x):
        return 0.5 * (1 + math.erf((x - mid) / (sig * math.sqrt(2))))

    exact = np.array(
        [
            (cdf(b) - cdf(a)) * sig * math.sqrt(2 * math.pi) / (b - a)
            for a, b in zip(edges[:-1], edges[1:], strict=True)
        ]
    )
    assert np.allclose(pix, exact, rtol=2e-4, atol=1e-6)
    centres = 0.5 * (edges[1:] + edges[:-1])
    point = np.exp(-0.5 * ((centres - mid) / sig) ** 2)
    assert np.max(np.abs(point - exact)) > 0.05  # point sampling would be wrong

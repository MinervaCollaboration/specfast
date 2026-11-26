"""The fine ln(lambda) grid and the two operators applied on it.

The model is evaluated on a uniform grid in ln(lambda), convolved with the
LSF, then integrated over each detector pixel (DESIGN.md, "The forward
model"). On a uniform ln(lambda) grid a kernel of constant width in
velocity has a constant width in grid samples, so the convolution is a
plain discrete convolution.

All functions are plain NumPy array operations (no scipy) with shapes fixed
by static inputs, so they port to JAX.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from specfast.conventions import C_KMS, C_MPS


@dataclass(frozen=True)
class LnGrid:
    """Uniform grid ``ln(lambda / Angstrom) = ln_start + step * arange(n)``."""

    ln_start: float
    #: Step in ln(lambda) (dimensionless; ``step * c`` is the step in velocity).
    step: float
    n: int

    @classmethod
    def covering(cls, lam_min: float, lam_max: float, step_kms: float, margin_kms: float) -> LnGrid:
        """Grid covering [lam_min, lam_max] Angstrom plus ``margin_kms`` each side."""
        step = step_kms / C_KMS
        lo = np.log(lam_min) - margin_kms / C_KMS
        hi = np.log(lam_max) + margin_kms / C_KMS
        n = int(np.ceil((hi - lo) / step)) + 1
        return cls(ln_start=float(lo), step=float(step), n=n)

    @property
    def lnlam(self) -> np.ndarray:
        return self.ln_start + self.step * np.arange(self.n)

    @property
    def step_mps(self) -> float:
        """Grid step in velocity [m/s]."""
        return self.step * C_MPS


def gaussian_kernel(sigma_mps: float, step_mps: float, half_width: int) -> np.ndarray:
    """Sampled Gaussian of width ``sigma_mps`` on a grid of ``step_mps``,
    ``2 * half_width + 1`` taps, normalized to unit sum (so convolution
    conserves flux exactly)."""
    u = np.arange(-half_width, half_width + 1) * (step_mps / sigma_mps)
    k = np.exp(-0.5 * u * u)
    return k / k.sum()


def convolve(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Convolve ``values`` on the grid with an odd-length ``kernel``.

    Output has the input's length; the first and last ``len(kernel) // 2``
    samples see zero padding and must lie in the grid margin.
    """
    if kernel.size <= 1000:
        return np.convolve(values, kernel, mode="same")
    # long kernels (fine grids): FFT convolution, same result to rounding
    n = values.size + kernel.size - 1
    nfft = 1 << int(np.ceil(np.log2(n)))
    full = np.fft.irfft(np.fft.rfft(values, nfft) * np.fft.rfft(kernel, nfft), nfft)[:n]
    h = kernel.size // 2
    return full[h : h + values.size]


def _slopes(values: np.ndarray, step: float) -> np.ndarray:
    """Finite-difference derivative (central inside, one-sided at the ends)."""
    return np.gradient(values, step)


def cumulative_integral(values: np.ndarray, step: float) -> np.ndarray:
    """Running integral of the cubic Hermite interpolant of ``values`` (node
    slopes from finite differences) over the grid: 0 at the first sample.

    Per cell this is the trapezoid plus the end correction
    ``h^2 (f'_i - f'_(i+1)) / 12``, i.e. fourth-order accurate.
    """
    m = _slopes(values, step)
    cell = 0.5 * step * (values[:-1] + values[1:]) + step * step * (m[:-1] - m[1:]) / 12.0
    return np.concatenate([np.zeros(1), np.cumsum(cell)])


def integral_at(values: np.ndarray, grid: LnGrid, ln_x: np.ndarray) -> np.ndarray:
    """Integral of the cubic Hermite interpolant of ``values`` from the grid
    start to each ``ln_x`` (consistent with :func:`cumulative_integral`)."""
    h = grid.step
    m = _slopes(values, h)
    cum = cumulative_integral(values, h)
    pos = (ln_x - grid.ln_start) / h
    i = np.clip(np.floor(pos).astype(np.int64), 0, grid.n - 2)
    s = pos - i
    s2 = s * s
    s3 = s2 * s
    s4 = s3 * s
    # integrals from 0 to s of the Hermite basis functions (unit cell)
    h00 = s - s3 + 0.5 * s4
    h10 = 0.5 * s2 - 2.0 * s3 / 3.0 + 0.25 * s4
    h01 = s3 - 0.5 * s4
    h11 = -s3 / 3.0 + 0.25 * s4
    part = values[i] * h00 + m[i] * h * h10 + values[i + 1] * h01 + m[i + 1] * h * h11
    return cum[i] + h * part


def pixel_integrate(values: np.ndarray, grid: LnGrid, ln_edges: np.ndarray) -> np.ndarray:
    """Mean of ``values`` over each pixel, pixels bounded by ``ln_edges``.

    ``ln_edges`` (length npix + 1, increasing, inside the grid) are
    ln(lambda) at the pixel edges. Returns, per pixel, the integral of the
    cubic Hermite interpolant over [edge_i, edge_i+1] divided by the pixel
    width in ln(lambda): the average over the pixel, not a point sample at
    its centre. Summing ``result * diff(ln_edges)`` over pixels gives the
    interpolant's integral between the outer edges exactly (flux
    conservation).

    Two choices worth knowing:

    - Cubic, not linear: with a piecewise-linear interpolant the
      discretization error moves with the star across the grid and biased an
      injected K by -0.3% at a 0.25 km/s grid in the injection tests; the
      Hermite form brings that to ~1e-5 at the same cost.
    - The average is taken in ln(lambda), not in pixel x. They differ only
      through the change of dln(lambda)/dx across one pixel (~1e-4 of the
      pixel for an echelle order), identically in every evaluation.
    """
    a = integral_at(values, grid, ln_edges)
    return np.diff(a) / np.diff(ln_edges)


def cubic_weights(grid: LnGrid, ln_x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cubic-convolution (Keys, a = -1/2) interpolation weights from the
    nodes of ``grid`` to the points ``ln_x``.

    Returns ``(idx, w)``, both shaped ``ln_x.shape + (4,)``: the value at
    ``ln_x`` is ``sum(w * values[idx], axis=-1)``. The interpolant passes
    through the node values, is C1 and third-order accurate, and is linear
    in the node values, so the same weights give both the forward model and
    the sparse operator a template solver needs. Indices are clipped to the
    grid (points beyond the ends see the end nodes; the weights still sum to
    one).
    """
    pos = (np.asarray(ln_x, dtype=np.float64) - grid.ln_start) / grid.step
    i = np.floor(pos)
    t = pos - i
    t2 = t * t
    t3 = t2 * t
    w = np.stack(
        [
            0.5 * (-t3 + 2.0 * t2 - t),
            0.5 * (3.0 * t3 - 5.0 * t2 + 2.0),
            0.5 * (-3.0 * t3 + 4.0 * t2 + t),
            0.5 * (t3 - t2),
        ],
        axis=-1,
    )
    idx = i.astype(np.int64)[..., None] + np.arange(-1, 3)
    return np.clip(idx, 0, grid.n - 1), w


def cubic_interpolate(values: np.ndarray, grid: LnGrid, ln_x: np.ndarray) -> np.ndarray:
    """Node ``values`` on ``grid`` interpolated to ``ln_x``; the same
    interpolant as :func:`cubic_weights`, written out for speed."""
    v = np.asarray(values, dtype=np.float64)
    pos = (np.asarray(ln_x, dtype=np.float64) - grid.ln_start) / grid.step
    i = np.floor(pos)
    t = pos - i
    i = i.astype(np.int64)
    last = grid.n - 1
    a = v[np.clip(i - 1, 0, last)]
    b = v[np.clip(i, 0, last)]
    c = v[np.clip(i + 1, 0, last)]
    d = v[np.clip(i + 2, 0, last)]
    # Keys (a = -1/2) in Horner form: b + t (c - a)/2 + t^2 (...) + t^3 (...)
    return b + 0.5 * t * (
        (c - a) + t * ((2.0 * a - 5.0 * b + 4.0 * c - d) + t * (3.0 * (b - c) + d - a))
    )


def kernel_sigma_mps(kernel: np.ndarray, step_mps: float) -> float:
    """RMS width [m/s] of a sampled kernel (its second moment)."""
    k = np.asarray(kernel, dtype=np.float64)
    u = (np.arange(k.size) - 0.5 * (k.size - 1)) * step_mps
    mu = np.sum(u * k) / np.sum(k)
    return float(np.sqrt(np.sum((u - mu) ** 2 * k) / np.sum(k)))


#: Normalizations of the Hermite polynomials H3, H4 of the Gauss-Hermite
#: series (van der Marel & Franx 1993).
_SQ3 = np.sqrt(3.0)
_SQ24 = np.sqrt(24.0)


def gh_kernel(
    sigma_mps: float, h3: float, h4: float, step_mps: float, half_width: int
) -> np.ndarray:
    """Sampled Gauss-Hermite profile ``G(y) [1 + h3 H3(y) + h4 H4(y)]``,
    ``y = u / sigma`` with ``u`` the velocity offset (positive = red), so a
    positive ``h3`` is a red tail. ``H3 = (2 y^3 - 3 y) / sqrt 3``,
    ``H4 = (4 y^4 - 12 y^2 + 3) / sqrt 24``. Clipped at zero, normalized to
    unit sum, ``2 * half_width + 1`` taps (index increasing = redward, as
    :func:`convolve` expects)."""
    y = np.arange(-half_width, half_width + 1) * (step_mps / max(float(sigma_mps), 1e-6))
    y2 = y * y
    k = np.exp(-0.5 * y2) * (
        1.0 + h3 * (2.0 * y2 * y - 3.0 * y) / _SQ3 + h4 * (4.0 * y2 * y2 - 12.0 * y2 + 3.0) / _SQ24
    )
    k = np.clip(k, 0.0, None)
    return k / k.sum()


def lagrange_weights(u: np.ndarray, nodes: np.ndarray) -> np.ndarray:
    """Lagrange interpolation weights (len(nodes), len(u)) from ``nodes`` to
    ``u``: a quantity known at the nodes is ``weights.T @ values``."""
    u = np.asarray(u, dtype=np.float64)
    nodes = np.asarray(nodes, dtype=np.float64)
    w = np.ones((nodes.size, u.size))
    for k in range(nodes.size):
        for j in range(nodes.size):
            if j != k:
                w[k] *= (u - nodes[j]) / (nodes[k] - nodes[j])
    return w


def hermite_value(values: np.ndarray, grid: LnGrid, ln_x: np.ndarray) -> np.ndarray:
    """The cubic Hermite interpolant of :func:`integral_at` (node slopes from
    finite differences) evaluated at ``ln_x``: the derivative of that running
    integral, consistent with :func:`pixel_integrate`."""
    h = grid.step
    m = _slopes(values, h)
    pos = (np.asarray(ln_x, dtype=np.float64) - grid.ln_start) / h
    i = np.clip(np.floor(pos).astype(np.int64), 0, grid.n - 2)
    s = pos - i
    s2 = s * s
    s3 = s2 * s
    return (
        values[i] * (2 * s3 - 3 * s2 + 1)
        + m[i] * h * (s3 - 2 * s2 + s)
        + values[i + 1] * (-2 * s3 + 3 * s2)
        + m[i + 1] * h * (s3 - s2)
    )

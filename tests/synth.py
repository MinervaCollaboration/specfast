"""Synthetic spectra made by the forward model itself, and a small fitter.

Not part of the package. The fitter is the package's per-block
least squares (:mod:`specfast.doppler.fit`).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from specfast.conventions import C_KMS
from specfast.doppler import (
    ExposureContext,
    ForwardModel,
    GaussianLSF,
    IodineCell,
    LnGrid,
    NoGasCell,
    PolynomialContinuum,
    PolynomialWavelength,
    StarTemplate,
)
from specfast.doppler.fit import fit_block as _fit_block

LAM0 = 5500.0  # Angstrom
NPIX = 1024
PIX_KMS = 1.3  # pixel width in velocity (KiwiSpec-like sampling)
LSF_SIGMA_MPS = 1500.0


def line_spectrum(lnlam, centres, depths, sigma_kms):
    """1 - sum of Gaussian lines (centres in ln lambda, widths in km/s);
    returns the optical depth-like sum (caller exponentiates or subtracts)."""
    s = sigma_kms / C_KMS
    out = np.zeros_like(lnlam)
    for c, d in zip(centres, depths, strict=True):
        m = np.abs(lnlam - c) < 8 * s
        out[m] += d * np.exp(-0.5 * ((lnlam[m] - c) / s) ** 2)
    return out


@dataclass
class Scene:
    """Truth for a synthetic block: components, true parameters, grid."""

    model: ForwardModel
    truth: dict

    def params(self, v=None, **override):
        p = {c: dict(d) for c, d in self.truth.items()}
        if v is not None:
            p["star"]["v"] = np.array([float(v)])
        for key, val in override.items():
            comp, name = key.split("__")
            p[comp][name] = np.asarray(val, dtype=float)
        return p


def make_scene(
    seed=1,
    step_kms=0.25,
    gas_cell=True,
    template_step_kms=0.05,
    npix=NPIX,
    iodine_sigma_kms=0.8,
    star_sigma_kms=3.0,
):
    """A KiwiSpec-like order: synthetic star + synthetic iodine lines."""
    rng = np.random.default_rng(seed)
    disp = LAM0 * PIX_KMS / C_KMS  # Angstrom / px at the centre
    half = 0.5 * (npix - 1)
    wave_true = np.array([LAM0, disp * half, -0.3, 0.02])  # a_k in scaled pixel t
    lam_lo = LAM0 - disp * half - 0.5
    lam_hi = LAM0 + disp * half + 0.5
    grid = LnGrid.covering(lam_lo, lam_hi, step_kms=step_kms, margin_kms=100.0)

    # star: rest-frame template, wide enough for |z_B| <= 35 km/s plus margin
    span = (np.log(lam_lo) - 150 / C_KMS, np.log(lam_hi) + 150 / C_KMS)
    t_step = template_step_kms / C_KMS
    t_ln = np.arange(span[0], span[1], t_step)
    nstar = int(1.6 * (lam_hi - lam_lo))  # ~1.6 lines per Angstrom
    s_c = rng.uniform(span[0], span[1], nstar)
    s_d = rng.uniform(0.05, 0.7, nstar)
    s_w = star_sigma_kms
    t_flux = 1.0 - line_spectrum(t_ln, s_c, s_d, s_w)
    t_flux = np.clip(t_flux, 0.05, None)
    star = StarTemplate(lnlam=t_ln, flux=t_flux)

    if gas_cell:
        i_ln = t_ln  # atlas nodes independent of the model grid
        ni = int(8 * (lam_hi - lam_lo))  # dense iodine forest
        i_c = rng.uniform(i_ln[0], i_ln[-1], ni)
        i_d = rng.uniform(0.02, 0.6, ni)
        tau = line_spectrum(i_ln, i_c, i_d, iodine_sigma_kms)
        ref = IodineCell(lnlam=i_ln, tau=tau)
    else:
        ref = NoGasCell()

    model = ForwardModel(
        wavelength=PolynomialWavelength.for_pixels(3, npix),
        continuum=PolynomialContinuum.for_pixels(2, npix),
        lsf=GaussianLSF.for_grid(grid, max_sigma_mps=LSF_SIGMA_MPS),
        factors=(star, ref),
        grid=grid,
        pixels=np.arange(npix, dtype=float),
    )
    truth = {
        "wavelength": {"coeffs": wave_true},
        "continuum": {"coeffs": np.array([1.0e4, 600.0, -900.0])},
        "lsf": {"sigma": np.array([LSF_SIGMA_MPS])},
        "star": {"v": np.array([0.0])},
    }
    if gas_cell:
        truth["iodine"] = {"k": np.array([1.0])}
    return Scene(model=model, truth=truth)


#: Parameter scales for the solver (one unit of theta).
SCALES = {
    ("star", "v"): 10.0,
    ("iodine", "k"): 1e-3,
    ("wavelength", "coeffs"): 1e-3,
    ("continuum", "coeffs"): 1.0,
}


def fit_block(model, data, sigma, ctx, start, exclude=()):
    """Weighted least squares of the free parameters; returns
    (params, covariance of theta in physical units, layout, result with
    ``cost`` = chi2 / 2). A thin wrapper of the package's fit_block."""
    fit = _fit_block(model, data, sigma, ctx, start, exclude=exclude, scales=SCALES)
    return fit.params, fit.cov, fit.layout, SimpleNamespace(cost=0.5 * fit.chi2)


def index_of(layout, comp, name):
    i = 0
    for c, p, n in layout.entries:
        if (c, p) == (comp, name):
            return i
        i += n
    raise KeyError((comp, name))


def perturbed_start(scene, rng=None):
    """A start away from the truth: v = 0 (truth up to ~1.3 km/s away),
    iodine strength +10%, wavelength zero point +0.2 px, continuum +2%."""
    p = scene.params(v=0.0)
    disp = scene.truth["wavelength"]["coeffs"][1] / (0.5 * (len(scene.model.pixels) - 1))
    p["wavelength"]["coeffs"] = p["wavelength"]["coeffs"] + np.array([0.2 * disp, 0, 0, 0])
    p["continuum"]["coeffs"] = p["continuum"]["coeffs"] * 1.02
    if "iodine" in p:
        p["iodine"]["k"] = np.array([1.1])
    return p


def exposures(n, seed, K=50.0, gamma=-1234.5, zb_kms=30.0):
    """(v_true [m/s], z_bary) for n exposures of a K-amplitude orbit."""
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, 1, n)
    v = gamma + K * np.sin(2 * np.pi * phase)
    zb = rng.uniform(-zb_kms, zb_kms, n) / C_KMS
    return v, zb, phase


def recover_K(v_fit, phase):
    """Least-squares (gamma, K sin, K cos) fit to recovered velocities."""
    A = np.column_stack([np.ones_like(phase), np.sin(2 * np.pi * phase), np.cos(2 * np.pi * phase)])
    coef, *_ = np.linalg.lstsq(A, v_fit, rcond=None)
    return coef


def noise_free_run(scene, n=8, seed=11, K=50.0):
    v_true, zb, phase = exposures(n, seed, K=K)
    v_fit = []
    for v, z in zip(v_true, zb, strict=True):
        ctx = ExposureContext(z_bary=z)
        data = scene.model.evaluate(scene.params(v=v), ctx)
        best, *_ = fit_block(scene.model, data, np.ones_like(data), ctx, perturbed_start(scene))
        v_fit.append(best["star"]["v"][0])
    return v_true, np.array(v_fit), phase

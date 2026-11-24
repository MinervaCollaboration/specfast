"""Synthetic multi-order, multi-exposure scenes for the template-inference tests.

Every spectrum is made by the forward model itself with a
:class:`GriddedTemplate` star, so the truth is exactly representable; the
tests probe the solver, the priors and the degeneracies, not the
representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from synth import line_spectrum

from specfast.conventions import C_KMS
from specfast.doppler import (
    DetectorMap,
    ExposureContext,
    ForwardModel,
    GaussianLSF,
    GriddedTemplate,
    IodineCell,
    LnGrid,
    NoGasCell,
    PolynomialContinuum,
    PolynomialWavelength,
    Telluric,
)
from specfast.doppler.template import Block, template_grid

PIX_KMS = 1.3
LSF_SIGMA_MPS = 1500.0
GAMMA = -1234.5


@dataclass
class Order:
    lam0: float
    grid: LnGrid  # fine model grid
    tgrid: LnGrid  # template node grid
    truth: np.ndarray  # true template nodes
    lines: tuple  # (centres, depths) of the star
    wave: np.ndarray  # nominal wavelength coefficients
    iodine: IodineCell | None = None
    telluric: Telluric | None = None
    telluric_truth: Telluric | None = None
    #: The deep telluric lines only (what a mask-oriented atlas resolves).
    telluric_deep: Telluric | None = None


@dataclass
class Scene:
    orders: list
    npix: int
    v: np.ndarray
    zb: np.ndarray
    airmass: np.ndarray
    water: np.ndarray
    phase: np.ndarray
    K: float
    gas_cell: bool
    extra: dict = field(default_factory=dict)


def star_nodes(tgrid, centres, depths, width_kms, shift_mps=0.0):
    ln = tgrid.lnlam
    c = centres + shift_mps / 1e3 / C_KMS
    return np.clip(1.0 - line_spectrum(ln, c, depths, width_kms), 0.05, None)


def make_scene(
    n_orders=3,
    npix=300,
    n_exp=16,
    berv_kms=25.0,
    K=50.0,
    gas_cell=True,
    tellurics=False,
    seed=1,
    oversample=4.0,
    lam_start=5200.0,
):
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, 1, n_exp)
    v = GAMMA + K * np.sin(2 * np.pi * phase)
    zb = rng.uniform(-berv_kms, berv_kms, n_exp) / C_KMS
    airmass = rng.uniform(1.0, 2.0, n_exp)
    water = rng.uniform(0.3, 2.0, n_exp)
    max_shift = berv_kms + 5.0
    orders = []
    for j in range(n_orders):
        lam0 = lam_start + 60.0 * j
        disp = lam0 * PIX_KMS / C_KMS
        half = 0.5 * (npix - 1)
        lo, hi = lam0 - disp * half - 0.5, lam0 + disp * half + 0.5
        grid = LnGrid.covering(lo, hi, step_kms=0.25, margin_kms=15.0)
        tgrid = template_grid(lo, hi, PIX_KMS, oversample, max_shift)
        span = (tgrid.lnlam[0], tgrid.lnlam[-1])
        n_lines = int(1.6 * (np.exp(span[1]) - np.exp(span[0])))
        centres = rng.uniform(*span, n_lines)
        depths = rng.uniform(0.05, 0.7, n_lines)
        truth = star_nodes(tgrid, centres, depths, 3.0)
        order = Order(
            lam0=lam0,
            grid=grid,
            tgrid=tgrid,
            truth=truth,
            lines=(centres, depths),
            wave=np.array([lam0, disp * half, -0.3, 0.02]),
        )
        a_ln = np.arange(grid.lnlam[0] - 1e-4, grid.lnlam[-1] + 1e-4, 0.05 / C_KMS)
        if gas_cell:
            ni = int(8 * (hi - lo))
            tau = line_spectrum(
                a_ln, rng.uniform(a_ln[0], a_ln[-1], ni), rng.uniform(0.02, 0.6, ni), 0.8
            )
            order.iodine = IodineCell(lnlam=a_ln, tau=tau)
        if tellurics:
            # micro-tellurics (< 1% deep) plus a few deep lines, two groups
            def group(n_micro, n_deep, a_ln=a_ln):
                c = rng.uniform(a_ln[0], a_ln[-1], n_micro + n_deep)
                d = np.concatenate(
                    [rng.uniform(0.001, 0.01, n_micro), rng.uniform(0.03, 0.3, n_deep)]
                )
                micro = line_spectrum(a_ln, c[:n_micro], d[:n_micro], 1.0)
                deep = line_spectrum(a_ln, c[n_micro:], d[n_micro:], 1.0)
                return micro, deep

            n_ang = hi - lo
            dry_micro, dry_deep = group(int(0.4 * n_ang), 2)
            wat_micro, wat_deep = group(int(0.6 * n_ang), 3)
            order.telluric_truth = Telluric(
                lnlam=a_ln, tau_dry=dry_micro + dry_deep, tau_water=wat_micro + wat_deep
            )
            order.telluric_deep = Telluric(lnlam=a_ln, tau_dry=dry_deep, tau_water=wat_deep)
        orders.append(order)
    return Scene(
        orders=orders,
        npix=npix,
        v=v,
        zb=zb,
        airmass=airmass,
        water=water,
        phase=phase,
        K=K,
        gas_cell=gas_cell,
    )


def build_model(scene, order, telluric=None, detector=False, iodine_correction=False):
    """The forward model of one order. ``telluric``: a Telluric component or
    None. ``iodine_correction``: give the iodine a learned-correction grid."""
    factors = [GriddedTemplate(grid=order.tgrid)]
    if scene.gas_cell:
        io = order.iodine
        if iodine_correction:
            corr = LnGrid.covering(
                np.exp(order.grid.lnlam[0]),
                np.exp(order.grid.lnlam[-1]),
                step_kms=PIX_KMS / 4,
                margin_kms=0.0,
            )
            io = IodineCell(lnlam=io.lnlam, tau=io.tau, correction=corr)
        factors.append(io)
    else:
        factors.append(NoGasCell())
    if telluric is not None:
        factors.append(telluric)
    return ForwardModel(
        wavelength=PolynomialWavelength.for_pixels(3, scene.npix),
        continuum=PolynomialContinuum.for_pixels(2, scene.npix),
        lsf=GaussianLSF.for_grid(order.grid, max_sigma_mps=LSF_SIGMA_MPS),
        factors=tuple(factors),
        grid=order.grid,
        pixels=np.arange(scene.npix, dtype=float),
        detector=DetectorMap(scene.npix) if detector else None,
    )


def true_params(scene, order, e, model, wave_drift_px=0.0, detector=None):
    disp = order.wave[1] / (0.5 * (scene.npix - 1))
    p = {
        "wavelength": {"coeffs": order.wave + np.array([wave_drift_px * disp, 0, 0, 0])},
        "continuum": {"coeffs": np.array([2.0e4, 1000.0, -1500.0])},
        "lsf": {"sigma": np.array([LSF_SIGMA_MPS])},
        "star": {
            "v": np.array([scene.v[e]]),
            "zero_point": np.zeros(1),
            "flux": order.truth,
        },
    }
    if scene.gas_cell:
        p["iodine"] = {"k": np.array([1.0])}
        io = model.factor("iodine")
        if io.correction is not None:
            p["iodine"]["dtau"] = np.zeros(io.correction.n)
    for f in model.factors:
        if isinstance(f, Telluric):
            p[f.name] = {"water": np.array([scene.water[e]])}
            if f.correction is not None:
                p[f.name]["dtau_dry"] = np.zeros(f.correction.n)
                p[f.name]["dtau_water"] = np.zeros(f.correction.n)
    if model.detector is not None:
        p["detector"] = detector if detector is not None else DetectorMap.identity(scene.npix)
    return p


def ctx_of(scene, e):
    return ExposureContext(z_bary=float(scene.zb[e]), airmass=float(scene.airmass[e]))


def observe(scene, snr=None, seed=99, truth_telluric=False, detector=None, wave_drift=True):
    """Data per (exposure, order) from the truth (with the true tellurics and
    detector map if given). Returns {(e, j): (data, sigma)} and the drifts."""
    rng = np.random.default_rng(seed)
    drift = rng.normal(0, 0.1, len(scene.v)) if wave_drift else np.zeros(len(scene.v))
    out = {}
    for j, order in enumerate(scene.orders):
        tel = order.telluric_truth if truth_telluric else None
        model = build_model(scene, order, telluric=tel, detector=detector is not None)
        for e in range(len(scene.v)):
            p = true_params(scene, order, e, model, drift[e], detector=detector)
            clean = model.evaluate(p, ctx_of(scene, e))
            if snr is None:
                out[(e, j)] = (clean, np.sqrt(clean))
            else:
                sigma = np.sqrt(clean)
                out[(e, j)] = (clean + rng.normal(0, sigma), sigma)
    return out, drift


def make_blocks(
    scene,
    data,
    models,
    start_v,
    exclude=(),
    masks=None,
    drift=None,
    perturb=True,
    detector=None,
    water_start=None,
):
    """Blocks with starts away from the truth (wavelength zero point +0.05 px
    unless held, continuum +2%, iodine strength +5%)."""
    blocks = []
    for j, order in enumerate(scene.orders):
        model = models[j]
        for e in range(len(scene.v)):
            d, s = data[(e, j)]
            p = true_params(
                scene, order, e, model, 0.0 if drift is None else drift[e], detector=detector
            )
            p["star"]["v"] = np.array([start_v[e]])
            p["star"]["flux"] = np.ones(order.tgrid.n)
            if perturb:
                if ("wavelength", "coeffs") not in exclude:
                    disp = order.wave[1] / (0.5 * (scene.npix - 1))
                    p["wavelength"]["coeffs"] = p["wavelength"]["coeffs"] + [0.05 * disp, 0, 0, 0]
                p["continuum"]["coeffs"] = p["continuum"]["coeffs"] * 1.02
                if "iodine" in p:
                    p["iodine"]["k"] = np.array([1.05])
            if water_start is not None and "telluric" in p:
                p["telluric"]["water"] = np.array([water_start[e]])
            if masks is not None:
                s = np.where(masks[j], np.inf, s)
            blocks.append(
                Block(
                    key=e,
                    order=j,
                    model=model,
                    data=d,
                    sigma=s,
                    ctx=ctx_of(scene, e),
                    start=p,
                    channel=0,
                    exclude=tuple(exclude),
                )
            )
    return blocks

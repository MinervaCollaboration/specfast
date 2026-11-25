"""End-to-end Doppler engine on synthetic extracted products.

Synthetic ``.proc.fits`` files (two channels, one order) are made with the
forward model itself, read back by the reader, fitted by the engine (worker
processes, sweeps, shared parameters, template) and the injected
velocities recovered.
"""

import datetime

import numpy as np
import pytest
import yaml
from astropy.io import fits
from astropy.table import Table
from synth import LAM0, line_spectrum

from specfast.conventions import C_KMS, C_MPS, measured_redshift
from specfast.doppler import ExposureContext, ForwardModel, LnGrid
from specfast.doppler.engine import provisional_z_bary, run
from specfast.doppler.library import (
    GaussHermiteLSF,
    IodineCell,
    OpticsWavelength,
    PolynomialContinuum,
    StarTemplate,
)
from specfast.doppler.runconfig import parse_run_config
from specfast.instrument import load_instrument

NPIX = 700
GAIN = 1.0

INSTRUMENT = (
    """
name: synth
description: synthetic two-channel test instrument
status: provisional
gas_cell: iodine
site: {name: test, latitude_deg: 31.68, longitude_deg: -110.88, height_m: 2316.0}
channels:
  - {name: A, role: science, telescope: A}
  - {name: B, role: science, telescope: B}
arms:
  - name: main
    channels: [A, B]
    orders: [0]
    rv_orders: [0]
    detector: {name: d, npix_dispersion: NPIXVAL, gain_e_per_adu: 1.0}
header:
  date_obs: [DATE-OBS]
  exptime: [EXPTIME]
  gas_cell_state: [I2POSAS]
  gas_cell_in_value: in
"""
).replace("NPIXVAL", str(NPIX))

STAR = dict(name="S", ra_deg=26.0, dec_deg=-15.9, rv_kms=-10.0)


def _world(tmp_path, n_exp=8, seed=4):
    rng = np.random.default_rng(seed)
    disp = LAM0 * 1.2 / C_KMS
    half = 0.5 * (NPIX - 1)
    base = np.array([LAM0, disp * half, -0.2])
    lam_lo, lam_hi = LAM0 - disp * half - 2, LAM0 + disp * half + 2
    ln = np.arange(np.log(lam_lo) - 200 / C_KMS, np.log(lam_hi) + 200 / C_KMS, 0.05 / C_KMS)
    nst = int(2.0 * (lam_hi - lam_lo))
    star = 1 - line_spectrum(ln, rng.uniform(ln[0], ln[-1], nst), rng.uniform(0.05, 0.6, nst), 3.0)
    star = np.clip(star, 0.05, None)
    ni = int(8 * (lam_hi - lam_lo))
    tau = line_spectrum(ln, rng.uniform(ln[0], ln[-1], ni), rng.uniform(0.02, 0.5, ni), 0.8)
    cal = tmp_path / "cal"
    cal.mkdir()
    np.savez(cal / "iodine.npz", wave_vac=np.exp(ln), transmission=np.exp(-tau))
    np.savez(cal / "template.npz", wave_vac=np.exp(ln), flux=star)
    np.savez(
        cal / "sigma.npz",
        channel=np.array(["A", "B"]),
        order=np.array([0, 0]),
        sigma_kms=np.array([1.5, 1.6]),
    )
    np.savez(
        cal / "lsfmap.npz",
        era_starts=np.array([0.0]),
        era=np.array([0, 0]),
        channel=np.array(["A", "B"]),
        order=np.array([0, 0]),
        s0_kms=np.array([1.5, 1.6]),
        g=np.array([0.03, 0.0]),
        q=np.zeros(2),
        h3=np.array([0.01, 0.0]),
        h3g=np.zeros(2),
        h4=np.zeros(2),
    )
    np.savez(
        cal / "optics.npz",
        era_starts=np.array([0.0]),
        era=np.array([0, 0]),
        channel=np.array(["A", "B"]),
        order=np.array([0, 0]),
        coeffs=np.array([base, base]),
        x_center=np.array([half]),
        x_scale=np.array([half]),
    )
    ins_path = tmp_path / "synth.yaml"
    ins_path.write_text(INSTRUMENT)
    ins = load_instrument(ins_path)
    # exposures over a year (BERV spread), injected orbit
    d0 = datetime.datetime(2019, 1, 1, 6, 0, 0)
    dates = [d0 + datetime.timedelta(days=float(x)) for x in np.linspace(0, 330, n_exp)]
    mjd = np.array([(d - datetime.datetime(1858, 11, 17)).total_seconds() / 86400 for d in dates])
    from specfast.doppler.runconfig import StarConfig

    sc = StarConfig(**STAR)
    zb = provisional_z_bary(mjd + 150.0 / 86400, sc, ins.site)
    v_true = STAR["rv_kms"] * 1e3 + 30.0 * np.sin(2 * np.pi * np.arange(n_exp) / 3.7)
    grid = LnGrid.covering(lam_lo - 1, lam_hi + 1, 0.25, 60.0)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pix = np.arange(NPIX, dtype=float)
    for e, d in enumerate(dates):
        flux = np.zeros((2, 1, NPIX))
        ivar = np.zeros((2, 1, NPIX))
        wave = np.zeros((2, 1, NPIX))
        for c, s0 in enumerate((1500.0, 1600.0)):
            lsf = GaussHermiteLSF.for_grid(
                grid, 2500.0, pixel_lo=0.0, pixel_hi=NPIX - 1.0, illumination="none"
            )
            m = ForwardModel(
                wavelength=OpticsWavelength(degree=2, x_center=half, x_scale=half),
                continuum=PolynomialContinuum.for_pixels(2, NPIX),
                lsf=lsf,
                factors=(StarTemplate(lnlam=ln, flux=star), IodineCell(lnlam=ln, tau=tau)),
                grid=grid,
                pixels=pix,
            )
            drift = rng.normal(0, 0.003)
            p = {
                "wavelength": {"coeffs": base + np.array([drift, 0, 0])},
                "continuum": {"coeffs": np.array([2e5, 1e4, -3e4])},
                "lsf": {
                    "map": np.array([s0, 0.03 if c == 0 else 0, 0, 0.01 if c == 0 else 0, 0, 0])
                },
                "star": {"v": np.array([v_true[e]])},
                "iodine": {"k": np.array([1.0])},
            }
            f = m.evaluate(p, ExposureContext(z_bary=zb[e]))
            f = f + rng.normal(0, 1, NPIX) * np.sqrt(f)
            flux[c, 0], ivar[c, 0] = f / GAIN, GAIN**2 / f
            wave[c, 0] = np.polynomial.polynomial.polyval((pix - half) / half, base)
        h = fits.PrimaryHDU(flux.astype(np.float32))
        h.header["DATE-OBS"] = d.isoformat(timespec="milliseconds")
        h.header["EXPTIME"] = 300.0
        h.header["I2POSAS"] = "in"
        h.header["OBJECT1"] = "S"
        fits.HDUList(
            [
                h,
                fits.ImageHDU(ivar.astype(np.float32)),
                fits.ImageHDU(wave),
                fits.ImageHDU(np.ones_like(flux, dtype=np.float32)),
            ]
        ).writeto(data_dir / f"n{d:%Y%m%d}.S.{e:04d}.proc.fits")
    cfg = dict(
        schema_version=1,
        instrument=str(ins_path),
        output=str(tmp_path / "out"),
        star=STAR,
        inputs=dict(directory=str(data_dir), suffix=".proc.fits"),
        calibrations=dict(
            template=str(cal / "template.npz"),
            iodine_atlas=str(cal / "iodine.npz"),
            lsf_sigma=str(cal / "sigma.npz"),
            lsf_map=str(cal / "lsfmap.npz"),
            optics=str(cal / "optics.npz"),
        ),
        model=dict(
            buffer_angstrom=1.0,
            wavelength=dict(distortion=False, search_px=5.0),
            lsf=dict(model="gauss_hermite", illumination="gh", tau_init=[0.02, 0.01]),
            iodine=dict(learned_correction=False),
            telluric=dict(model="none"),
            star=dict(mode="modify"),
        ),
        solver=dict(sweeps=3, processes=2),
        outputs=dict(segments=2),
    )
    return cfg, v_true, zb


@pytest.mark.parametrize("variant", ["joint", "fixed_gaussian_pipeline", "detector_cti"])
def test_engine_recovers_injected_velocities(tmp_path, variant):
    cfg, v_true, zb = _world(tmp_path)
    if variant != "joint":
        cfg["model"].update(
            lsf=dict(model="gaussian", illumination="none"), star=dict(mode="fixed")
        )
        cfg["model"]["wavelength"]["base"] = "pipeline"
        cfg["solver"]["sweeps"] = 1
    if variant == "detector_cti":
        # hooks on (identity map; CTI of the synthetic data is zero, so a
        # small CTI only perturbs the fit slightly)
        cfg["model"]["detector_map"] = True
        cfg["model"]["cti"] = dict(enabled=True)
    with open(tmp_path / "run.yaml", "w") as fh:
        yaml.safe_dump(cfg, fh)
    out = run(parse_run_config(cfg))
    t = Table.read(out / "blocks.fits")
    assert len(t) == 2 * len(v_true)
    for ch in ("A", "B"):
        s = t[t["channel"] == ch]
        s.sort("file")
        v = np.asarray(s["v"], float)
        err = np.asarray(s["v_err"], float)
        resid = v - v_true - np.mean(v - v_true)
        # photon-limited recovery (8 exposures, S/N ~ 450 per pixel)
        assert np.std(resid) < 2.0 * np.median(err), (ch, resid, np.median(err))
        # raw redshift is the total measured redshift
        cz = C_MPS * measured_redshift(v, np.asarray(s["z_bary_prov"], float))
        assert np.allclose(cz, s["cz"])
    assert (out / "convergence.json").exists() and (out / "provenance.json").exists()
    assert np.all(np.isfinite(np.asarray(t["vseg"], float)))


def test_static_positions_loader(tmp_path):
    from specfast.doppler.calib import StaticPositions

    S = np.zeros((2, 10))
    S[1, 3] = np.nan
    S[1, 4] = 0.02
    np.savez(
        tmp_path / "s.npz",
        era_starts=np.array([0.0, 100.0]),
        era=np.array([0, 1]),
        channel=np.array(["A", "A"]),
        order=np.array([0, 0]),
        S=S,
    )
    sp = StaticPositions(tmp_path / "s.npz")
    assert np.all(sp.get(50.0, "A", 0) == 0)
    row = sp.get(150.0, "A", 0)
    assert row[3] == 0.0 and row[4] == 0.02
    assert sp.get(150.0, "B", 0) is None


def test_engine_warm_start_with_new_frames(tmp_path):
    cfg, v_true, zb = _world(tmp_path)
    first = dict(cfg, output=str(tmp_path / "first"))
    first["inputs"] = dict(cfg["inputs"], limit=5)
    run(parse_run_config(first))
    second = dict(cfg, output=str(tmp_path / "second"))
    second["solver"] = dict(cfg["solver"], warm_start=str(tmp_path / "first" / "state.pkl"))
    out = run(parse_run_config(second))
    t = Table.read(out / "blocks.fits")
    assert len(t) == 2 * len(v_true)
    log = (out / "progress.log").read_text()
    assert "warm start: 6 blocks without saved state" in log
    for ch in ("A", "B"):
        s = t[t["channel"] == ch]
        s.sort("file")
        resid = np.asarray(s["v"], float) - v_true
        resid -= resid.mean()
        assert np.std(resid) < 2.0 * np.median(np.asarray(s["v_err"], float))

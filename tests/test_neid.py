"""NEID: the instrument description and the L1/L2 -> ExtractedSpectrum converter.

The fixture is a synthetic file with the NEID L1/L2 layout (extension names,
122 orders, the per-order header keywords) and a few pixels per order; no
real NEID data are committed.
"""

import numpy as np
import pytest
from astropy.io import fits

from specfast.converters.neid import N_ORDERS, echelle_order, read_neid
from specfast.instrument import load_instrument
from specfast.products import ExtractedSpectrum, Mask

NPIX = 16


def make_neid_file(path, level=1, instrument="NEID"):
    rng = np.random.default_rng(5)
    prim = fits.PrimaryHDU()
    h = prim.header
    h["INSTRUME"] = instrument
    h["DATALVL"] = level
    h["FILENAME"] = path.name
    h["OBJECT"] = "HD 10700"
    h["DATE-OBS"] = "2023-10-15T05:06:07.890"
    h["EXPTIME"] = 90.0
    h["OBS-MODE"] = "HR"
    h["SCI-OBJ"] = "HD 10700"
    h["CAL-OBJ"] = "Etalon"
    h["SKY-OBJ"] = "Sky"
    h["QRA"] = "01:44:02.2"
    h["QDEC"] = "-15:56:02"
    h["PMKSTOP"] = 3.0e-5
    h["CCDTEMP"] = -100.0
    h["E_VER"] = "v1.5.3"
    h["WAVECAL"] = "LFCplusThAr"
    h["DRIFTFUN"] = "dailymodel0"
    h["MDSPFILE"] = "master.fits"
    h["DRIFTREF"] = "drift.npy"
    for k, v in (("DRIFTRV0", 0.25), ("DRIFTRV1", 0.0), ("DRIFTRV2", 0.0)):
        h[k] = v
    for i in range(N_ORDERS):
        m = int(echelle_order(i))
        h[f"SSBZ{m:03d}"] = 1.0e-5 + 1e-12 * i
        h[f"SSBJD{m:03d}"] = 2460232.71 + 1e-7 * i
    hdus = [prim]
    for ext in ("SCI", "SKY", "CAL"):
        flux = rng.normal(1e4, 100, (N_ORDERS, NPIX))
        var = np.full((N_ORDERS, NPIX), 1e4)
        lam0 = 6.13e6 / echelle_order(np.arange(N_ORDERS))[:, None]
        wave = lam0 * (1 + 2e-6 * np.arange(NPIX))[None, :]
        if ext == "SCI":
            flux[5, 3] = np.nan
            var[6, 4] = 0.0
            wave[0, :] = 0.0
        hdus += [
            fits.ImageHDU(flux, name=f"{ext}FLUX"),
            fits.ImageHDU(var.astype(np.float32), name=f"{ext}VAR"),
            fits.ImageHDU(wave, name=f"{ext}WAVE"),
        ]
    hdus[3].header["ZPTDRIFT"] = -103.0  # SCIWAVE
    if level == 2:
        c = fits.ImageHDU(np.zeros((N_ORDERS, 8)), name="CCFS")
        for i in range(N_ORDERS):
            m = int(echelle_order(i))
            c.header[f"CCFRV{m:03d}"] = 0.0 if i < 10 else -16.6 + 1e-4 * i
            c.header[f"CCFWT{m:03d}"] = 1.0
        c.header["CCFRVMOD"] = -16.6024
        c.header["DVRMSMOD"] = 0.0003
        c.header["CCFJDMOD"] = 2460232.7123
        c.header["CCFRVSUM"] = -16.6030
        t = fits.ImageHDU(np.ones((N_ORDERS, NPIX, 2)), name="TELLURIC")
        t.header["WVAPOR"] = 4.5
        t.header["ZENITH"] = 48.0
        hdus += [t, c]
    fits.HDUList(hdus).writeto(path)
    return path


def test_instrument_description():
    n = load_instrument("neid")
    assert n.gas_cell == "none" and n.status == "provisional"
    assert [m.name for m in n.modes] == ["HR", "HE"] and n.mode().name == "HR"
    (arm,) = n.arms
    assert len(arm.orders) == N_ORDERS and arm.detector.npix_dispersion == 9216
    assert arm.echelle_orders == tuple(173 - o for o in arm.orders)
    assert set(arm.rv_orders) <= set(arm.orders)
    # grating equation: m * lambda is the same in every order (~61.3 um at
    # the order centre); each order spans ~1.9% in lambda, 1.0 (m = 52) to
    # 3.3 (m = 173) free spectral ranges lambda / m, so blue orders overlap
    for m, (lo, hi) in zip(arm.echelle_orders, arm.order_wavelength_ranges_nm, strict=True):
        assert m * 0.5 * (lo + hi) / 1e3 == pytest.approx(61.3, rel=0.01)
        assert 0.017 < (hi - lo) / (0.5 * (lo + hi)) < 0.021
    assert {c.name for c in n.channels} == {"SCI", "SKY", "CAL"}
    assert {"comb", "etalon", "thar"} <= set(n.channel("CAL").sources)
    assert len(n.traces("main")) == 3 * N_ORDERS


def test_convert_l1(tmp_path):
    f = make_neid_file(tmp_path / "neidL1_20231015T050607.fits")
    sp, audit = read_neid(f)
    arm = sp.arm("main")
    assert arm.channels == ("SCI", "SKY", "CAL") and arm.flux.shape == (3, N_ORDERS, NPIX)
    assert arm.flux.dtype == np.float64 and arm.variance.dtype == np.float64
    # bad pixels: flagged, zero flux, infinite variance; never a usable zero
    for o, p in ((5, 3), (6, 4)):
        assert arm.mask[0, o, p] & Mask.NO_DATA
        assert arm.flux[0, o, p] == 0.0 and np.isinf(arm.variance[0, o, p])
    assert (arm.mask[1:] & Mask.NO_DATA).sum() == 0
    # uncalibrated order: NaN wavelength, flagged
    assert np.all(np.isnan(arm.wavelength[0, 0])) and np.all(arm.mask[0, 0] & Mask.NO_WAVELENGTH)
    assert np.all(np.isfinite(arm.wavelength[1:, 0]))
    assert "LFCplusThAr" in arm.wavelength_source and "v1.5.3" in arm.wavelength_source
    h = sp.header
    assert h.instrument == "neid" and h.exptime_s == 90.0
    assert h.target_ra_deg == pytest.approx(26.00917, abs=1e-4)
    assert h.target_dec_deg == pytest.approx(-15.93389, abs=1e-4)
    assert h.environment["spectrograph_pressure"] == pytest.approx(4.0e-5, rel=1e-3)
    # no CCF in L1: the BJD is the per-order midpoint of the order nearest 550 nm
    i111 = int(np.where(audit.echelle_orders == 111)[0][0])
    assert h.bjd_tdb_mid == audit.bjd_tdb[i111]
    assert audit.ccf_rv is None and audit.data_level == 1
    assert audit.z_bary[0] == pytest.approx(1e-5) and audit.drift_terms == (0.25, 0.0, 0.0)
    assert audit.wave_zero_point_drift == -103.0
    # audit-only barycentric velocity: c[(1 + z)(1 + z_B) - 1]
    v = audit.barycentric_velocity(np.zeros(N_ORDERS))
    assert v[0] == pytest.approx(299792458.0 * 1e-5)
    # the product round-trips through its FITS format
    out = tmp_path / "es.fits"
    sp.write(out)
    back = ExtractedSpectrum.read(out)
    b = back.arm("main")
    assert back.header == sp.header and b.wavelength_source == arm.wavelength_source
    np.testing.assert_array_equal(b.mask, arm.mask)
    np.testing.assert_array_equal(b.flux, arm.flux)


def test_convert_l2_audit(tmp_path):
    f = make_neid_file(tmp_path / "neidL2_20231015T050607.fits", level=2)
    sp, audit = read_neid(f, channels=("SCI",), hash_input=False)
    assert sp.arm("main").channels == ("SCI",) and sp.provenance.inputs == ()
    # header CCFRV of 0 means "not measured"; km/s -> m/s
    assert np.all(np.isnan(audit.ccf_rv[:10])) and np.all(np.isfinite(audit.ccf_rv[10:]))
    assert audit.ccf_rv[10] == pytest.approx(-16599.0)
    assert audit.ccf_rv_mod == pytest.approx(-16602.4) and audit.ccf_rv_mod_err == pytest.approx(
        0.3
    )
    assert sp.header.bjd_tdb_mid == 2460232.7123
    assert audit.pwv_mm == 4.5 and audit.telluric_zenith_deg == 48.0


def test_rejects(tmp_path):
    f = make_neid_file(tmp_path / "other.fits", instrument="HARPN")
    with pytest.raises(ValueError, match="INSTRUME"):
        read_neid(f)
    g = make_neid_file(tmp_path / "neid.fits")
    with pytest.raises(ValueError, match="channels"):
        read_neid(g, channels=("SCI", "COMB"))


def test_rejects_missing_wavelength(tmp_path):
    # some public files carry flux but no wavelength (empty SCIWAVE, blank WAVECAL)
    f = make_neid_file(tmp_path / "neid.fits")
    with fits.open(f) as hl:
        hl["SCIWAVE"].data = None
        hl[0].header["WAVECAL"] = ""
        hl.writeto(tmp_path / "nowave.fits")
    with pytest.raises(ValueError, match="SCIWAVE is empty"):
        read_neid(tmp_path / "nowave.fits")
    # the other fibres still convert
    sp, _ = read_neid(tmp_path / "nowave.fits", channels=("SKY", "CAL"), hash_input=False)
    assert sp.arm("main").channels == ("SKY", "CAL")

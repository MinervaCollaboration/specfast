"""NRES: instrument description, BANZAI-NRES e92-1d converter and master-arc extraction.

Fixtures are synthetic files with the BANZAI-NRES layout (extension and
column names, 4096 columns per trace); no real NRES data are committed.
"""

import numpy as np
import pytest
from astropy.io import fits

from specfast.converters.nres import (
    CHANNELS,
    NPIX,
    ORDERS,
    extract_master_arc,
    parse_basename,
    read_banzai_1d,
    read_banzai_blaze,
)
from specfast.instrument import load_instrument
from specfast.products import ExtractedSpectrum, Mask


def make_e92(path, sci_fibre=2):
    rng = np.random.default_rng(3)
    rows = []
    tid = 1
    for m in ORDERS[10:14]:
        for f in (1, sci_fibre):
            w = np.linspace(5000.0, 5100.0, NPIX) * (100.0 / m)
            w[:10] = 0.0  # unextracted columns
            flux = rng.uniform(100, 200, NPIX)
            unc = np.sqrt(flux)
            mask = np.zeros(NPIX, np.uint8)
            mask[20] = 1
            rows.append((tid, m, f, w, flux, unc, np.full(NPIX, 0.5), mask))
            tid += 1
    cols = [
        fits.Column("id", "K", array=[r[0] for r in rows]),
        fits.Column("order", "K", array=[r[1] for r in rows]),
        fits.Column("fiber", "K", array=[r[2] for r in rows]),
        fits.Column("wavelength", f"{NPIX}D", array=np.array([r[3] for r in rows])),
        fits.Column("flux", f"{NPIX}D", array=np.array([r[4] for r in rows])),
        fits.Column("uncertainty", f"{NPIX}D", array=np.array([r[5] for r in rows])),
        fits.Column("blaze", f"{NPIX}D", array=np.array([r[6] for r in rows])),
        fits.Column("blaze_error", f"{NPIX}D", array=np.array([r[6] for r in rows])),
        fits.Column("mask", f"{NPIX}B", array=np.array([r[7] for r in rows])),
    ]
    prim = fits.PrimaryHDU()
    h = prim.header
    h["OBJECT"] = "HD 10700"
    h["OBJECTS"] = "none&thar&HD 10700" if sci_fibre == 2 else "HD 10700&thar&none"
    h["SCIFIBER"] = sci_fibre
    h["DATE-OBS"] = "2022-06-14T08:38:59.000"
    h["EXPTIME"] = 143.0
    h["RV"] = -16250.0
    h["RVERR"] = 32.6
    h["BARYCORR"] = 24603.4
    h["TCORR"] = 2459744.86
    h["SNR"] = 139.0
    h["TEFF"] = 5800.0
    h["LOGG"] = 5.5
    h["NRESPRES"] = 12.2
    h["NRESTEMP"] = 21.5
    h["L1IDARC"] = "lscnrs01-fa09-20220614-double-bin1x1-011.fits.fz"
    h["L1IDFLAT"] = "lscnrs01-fa09-20220614-lampflat-bin1x1-011.fits.fz"
    h["PIPEVER"] = "1.1.3"
    hl = fits.HDUList([prim, fits.BinTableHDU.from_columns(cols, name="SPECTRUM")])
    hl.writeto(path)
    return rows


def test_instrument_description():
    inst = load_instrument("nres")
    assert [c.name for c in inst.channels] == list(CHANNELS.values())
    assert inst.channel("fibre1").role == "reference_thar"
    assert {c.name for c in inst.science_channels()} == {"fibre0", "fibre2"}
    arm = inst.arm("main")
    assert arm.echelle_orders == ORDERS
    assert len(arm.order_wavelength_ranges_nm) == len(ORDERS)
    # m * lambda is nearly constant along the orders (grating equation)
    mid = np.array([np.mean(r) for r in arm.order_wavelength_ranges_nm]) * np.array(ORDERS)
    assert np.ptp(mid) / np.mean(mid) < 0.05
    assert inst.gas_cell == "none"


def test_parse_basename():
    d = parse_basename("lscnrs01-fa09-20220614-0041-e92-1d.fits.fz")
    assert d == {
        "site": "lsc",
        "unit": "nres01",
        "camera": "fa09",
        "day": "20220614",
        "frame": "0041",
    }
    assert parse_basename("tlvnrs04-fa18-20210506-double-bin1x1-011.fits.fz")["frame"] == "double"
    with pytest.raises(ValueError):
        parse_basename("not-a-frame.fits")


@pytest.mark.parametrize("sci", [0, 2])
def test_read_banzai_1d(tmp_path, sci):
    p = tmp_path / "lscnrs01-fa09-20220614-0041-e92-1d.fits"
    rows = make_e92(p, sci_fibre=sci)
    spec, audit = read_banzai_1d(p)
    assert isinstance(spec, ExtractedSpectrum)
    arm = spec.arm("main")
    assert arm.channels == ("fibre0", "fibre1", "fibre2")
    assert arm.flux.shape == (3, len(ORDERS), NPIX)
    assert audit.science_fibre == sci and audit.unit == "nres01" and audit.site == "lsc"
    assert audit.rv == -16250.0 and audit.template_teff == 5800.0
    assert spec.header.target_name == "HD 10700"
    assert abs(spec.header.environment["spectrograph_pressure"] - 12.2 * 68.947572932) < 1e-6
    tid, m, f, w, flux, unc, _, mask = rows[1]
    j = ORDERS.index(m)
    np.testing.assert_allclose(arm.flux[f, j, 30:], flux[30:])
    np.testing.assert_allclose(arm.variance[f, j, 30:], unc[30:] ** 2)
    assert arm.mask[f, j, 20] & Mask.NO_DATA and np.isinf(arm.variance[f, j, 20])
    assert arm.mask[f, j, 5] & Mask.NO_WAVELENGTH and np.isnan(arm.wavelength[f, j, 5])
    # the unlit science fibre and absent orders are NO_DATA, never usable zeros
    other = 2 - sci
    assert np.all(arm.mask[other] & Mask.NO_DATA) and np.all(np.isinf(arm.variance[other]))
    assert np.all(arm.mask[1, 0] & Mask.NO_DATA)
    assert "banzai-nres" in arm.wavelength_source
    blaze = read_banzai_blaze(p)
    assert np.allclose(blaze[f, j], 0.5) and np.isnan(blaze[f, 0]).all()


def test_read_banzai_1d_replacement_wavelength_round_trip(tmp_path):
    p = tmp_path / "x-e92-1d.fits"
    make_e92(p)
    w = np.full((3, len(ORDERS), NPIX), 5000.0)
    with pytest.raises(ValueError):
        read_banzai_1d(p, wavelength=w)  # needs a source
    spec, _ = read_banzai_1d(p, wavelength=w, wavelength_source="specfast.wavecal test")
    out = tmp_path / "es.fits"
    spec.write(out)
    back = ExtractedSpectrum.read(out)
    a = back.arm("main")
    assert a.wavelength_source == "specfast.wavecal test"
    assert np.all(a.wavelength == 5000.0)
    assert not np.any(a.mask & Mask.NO_WAVELENGTH)


def test_extract_master_arc_matches_profile_weighted_sum(tmp_path):
    ny = 12
    traces = np.zeros((ny, NPIX), np.uint8)
    traces[1:5] = 1  # fibre 1, order 70
    traces[6:10] = 2  # fibre 2, order 70
    prof_col = np.array([0.1, 0.4, 0.4, 0.1])
    profile = np.zeros((ny, NPIX))
    profile[1:5] = prof_col[:, None]
    profile[6:10] = prof_col[:, None]
    x = np.arange(NPIX)
    s1 = 1000.0 + 500.0 * np.exp(-0.5 * ((x - 2000.3) / 1.5) ** 2)
    s2 = 300.0 + 0 * x
    data = np.zeros((ny, NPIX))
    data[1:5] = prof_col[:, None] * s1
    data[6:10] = prof_col[:, None] * s2
    err = np.sqrt(np.abs(data) + 49.0)
    wimg = np.zeros((ny, NPIX))
    wimg[1:5] = 5000.0 + 0.02 * x
    wimg[6:10] = 5001.0 + 0.02 * x
    fits.HDUList(
        [
            fits.PrimaryHDU(),
            fits.ImageHDU(traces, name="TRACES"),
            fits.ImageHDU(profile, name="PROFILE"),
        ]
    ).writeto(tmp_path / "flat.fits")
    hdr = fits.Header()
    hdr["OBJECTS"] = "none&thar&thar"
    hdr["MJD-OBS"] = 59744.75
    fits.HDUList(
        [
            fits.PrimaryHDU(),
            fits.ImageHDU(data.astype(np.float32), header=hdr, name="SPECTRUM"),
            fits.ImageHDU(np.zeros((ny, NPIX), np.uint8), name="BPM"),
            fits.ImageHDU(err.astype(np.float32), name="ERR"),
            fits.ImageHDU(wimg, name="WAVELENGTH"),
        ]
    ).writeto(tmp_path / "arc.fits")
    ma = extract_master_arc(tmp_path / "arc.fits", tmp_path / "flat.fits", [(1, 70, 1), (2, 70, 2)])
    assert ma.lit_fibres == (1, 2)
    assert list(ma.fibre) == [1, 2] and list(ma.order) == [70, 70]
    np.testing.assert_allclose(ma.flux[0], s1, rtol=1e-5)
    np.testing.assert_allclose(ma.flux[1], s2, rtol=1e-5)
    np.testing.assert_allclose(ma.wavelength[1], 5001.0 + 0.02 * x)
    assert np.all(np.isfinite(ma.variance)) and ma.mjd == 59744.75

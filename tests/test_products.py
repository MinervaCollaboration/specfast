import numpy as np
import pytest
from astropy.io import fits

from specfast.products import (
    FORMAT_VERSION,
    ArmSpectrum,
    ExtractedSpectrum,
    Mask,
    NormalizedHeader,
    TraceDiagnostics,
)
from specfast.provenance import Provenance


def _arm(name, channels, orders, npix, rng, wave):
    shape = (len(channels), len(orders), npix)
    diag = TraceDiagnostics(
        width_px=rng.normal(2, 0.1, shape[:2]),
        centroid_px=rng.normal(0, 0.1, shape[:2]),
        profile_chi2=rng.uniform(1, 2, shape[:2]),
        halo_fraction=np.full(shape[:2], np.nan),
    )
    mask = rng.integers(0, 2**32, shape, dtype=np.uint64).astype(np.uint32)
    mask[0, 0, 0] = np.uint32(0xFFFFFFFF)
    return ArmSpectrum(
        arm=name,
        channels=channels,
        orders=orders,
        flux=rng.normal(1e4, 100, shape),
        variance=rng.uniform(1e4, 2e4, shape),
        mask=mask,
        diagnostics=diag,
        wavelength=rng.uniform(5000, 6000, shape) if wave else None,
        wavelength_source="test" if wave else None,
    )


def _spectrum():
    rng = np.random.default_rng(3)
    header = NormalizedHeader(
        instrument="kiwispec",
        raw_file="n20170101.HD122064.0001.fits",
        date_obs_utc="2017-01-01T03:04:05.678",
        exptime_s=1200.0,
        bjd_tdb_mid=2457754.6301234567,
        target_name="HD 122064",
        target_ra_deg=209.6098,
        target_dec_deg=61.4957,
        gas_cell_in=True,
        environment={"spectrograph_pressure": 1.2e-3, "gas_cell_temperature": 50.0},
    )
    prov = Provenance.create("extract", config_sha256="ab" * 32)
    arms = (
        _arm("main", ("T1", "T2", "T3", "T4"), tuple(range(5)), 64, rng, wave=True),
        _arm("red", ("S0", "COMB"), (10, 11, 12), 32, rng, wave=False),
    )
    return ExtractedSpectrum(header=header, arms=arms, provenance=prov)


def test_exact_round_trip(tmp_path):
    sp = _spectrum()
    path = tmp_path / "x.fits"
    sp.write(path)
    back = ExtractedSpectrum.read(path)
    assert back.header == sp.header
    assert back.provenance == sp.provenance
    assert len(back.arms) == len(sp.arms)
    for a, b in zip(sp.arms, back.arms, strict=True):
        assert (a.arm, a.channels, a.orders) == (b.arm, b.channels, b.orders)
        for name in ("flux", "variance", "mask", "wavelength"):
            x, y = getattr(a, name), getattr(b, name)
            if x is None:
                assert y is None
                continue
            assert x.dtype == y.dtype and x.shape == y.shape
            assert np.array_equal(x, y)
        assert a.wavelength_source == b.wavelength_source
        for f in ("width_px", "centroid_px", "profile_chi2", "halo_fraction"):
            assert np.array_equal(getattr(a.diagnostics, f), getattr(b.diagnostics, f),
                                  equal_nan=True)


def test_format_version_checked(tmp_path):
    path = tmp_path / "x.fits"
    _spectrum().write(path)
    assert fits.getheader(path)["SFFORMAT"] == FORMAT_VERSION
    with fits.open(path, mode="update") as h:
        h[0].header["SFFORMAT"] = FORMAT_VERSION + 1
    with pytest.raises(ValueError, match="format version"):
        ExtractedSpectrum.read(path)


def test_mask_bits_distinct():
    bits = [int(m) for m in Mask]
    assert len(set(bits)) == len(bits) and all(b & (b - 1) == 0 for b in bits)
    assert max(bits) < 2**32


def test_shape_validation():
    rng = np.random.default_rng(0)
    a = _arm("main", ("T1",), (0,), 8, rng, wave=False)
    with pytest.raises(ValueError, match="uint32"):
        ArmSpectrum(a.arm, a.channels, a.orders, a.flux, a.variance,
                    a.mask.astype(np.int32), a.diagnostics)
    with pytest.raises(ValueError, match="wavelength_source"):
        ArmSpectrum(a.arm, a.channels, a.orders, a.flux, a.variance, a.mask,
                    a.diagnostics, wavelength=a.flux.copy())

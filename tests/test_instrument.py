import datetime as dt

import pytest

from specfast.config import ConfigError
from specfast.instrument import load_instrument, shipped_instruments


def test_shipped():
    assert {"kiwispec", "gclef_magellan", "gclef_gmt"} <= set(shipped_instruments())


def test_kiwispec_layout():
    k = load_instrument("kiwispec")
    assert k.gas_cell == "iodine"
    assert [c.name for c in k.science_channels()] == ["T1", "T2", "T3", "T4"]
    (arm,) = k.arms
    assert len(arm.orders) == 29 and arm.detector.npix_dispersion == 2048
    assert arm.rv_orders == tuple(range(1, 24))
    assert arm.echelle_orders == tuple(122 - o for o in arm.orders)
    traces = k.traces(arm.name)
    assert len(traces) == 4 * 29 - 2  # T3 (off the chip) and T4 (dummy) of the last order
    live = {(t.channel, t.order) for t in traces}
    assert ("T4", 28) not in live and ("T3", 28) not in live and ("T1", 28) in live
    d = arm.detector
    assert d.raw_shape == (2052, 2090) and d.saturation_adu < 65535


def test_kiwispec_eras():
    k = load_instrument("kiwispec")
    assert k.era_of(dt.date(2015, 12, 1)) is None
    assert k.era_of(dt.date(2017, 10, 2)).start == dt.date(2017, 10, 2)
    assert k.era_of(dt.date(2018, 6, 1)).start == dt.date(2017, 10, 2)
    assert k.is_excluded(dt.date(2017, 6, 1)) and not k.is_excluded(dt.date(2017, 10, 2))
    assert k.channel_epoch("T3", dt.date(2018, 8, 1)) == 0
    assert k.channel_epoch("T3", dt.date(2018, 12, 17)) == 1
    assert k.channel_epoch("T2", dt.date(2018, 12, 16)) == 0
    assert k.channel_epoch("T1", dt.date(2019, 12, 1)) == 0
    # per-telescope exclusion: T2's 2019 guiding episode only
    d = dt.date(2019, 6, 1)
    assert k.is_excluded(d, "T2") and not k.is_excluded(d, "T1") and not k.is_excluded(d)


@pytest.mark.parametrize("name, nslices", [("gclef_magellan", 1), ("gclef_gmt", 7)])
def test_gclef(name, nslices):
    g = load_instrument(name)
    assert g.status == "provisional" and g.gas_cell == "none"
    assert len(g.science_channels()) == nslices
    cal = [c for c in g.channels if c.role == "calibration"]
    assert len(cal) == 2 and all({"comb", "etalon", "thar"} <= set(c.sources) for c in cal)
    blue, red = g.arms
    assert (blue.name, red.name) == ("blue", "red")
    # the overlap order 114 is on both arms; blue holds the higher orders
    assert blue.echelle_orders[0] > blue.echelle_orders[-1] == 114 == red.echelle_orders[0]
    assert blue.wavelength_range_nm[1] < 545 < red.wavelength_range_nm[1]
    for a in g.arms:
        assert a.detector.pixel_size_um == 9.0 and a.detector.npix_dispersion == 10560
        assert len(a.order_wavelength_ranges_nm) == len(a.orders) == len(a.echelle_orders)
        # orders span about their free spectral range (lambda / m) or more
        for m, (lo, hi) in zip(a.echelle_orders, a.order_wavelength_ranges_nm, strict=True):
            assert hi - lo > 0.9 * 0.5 * (lo + hi) / m
        assert set(a.channels) == {c.name for c in g.channels}
        # unknowns stay unknown
        assert a.detector.gain_e_per_adu is None and a.detector.read_noise_e is None
    assert g.site is None


def test_gclef_sites_differ_only_in_feed():
    m, g = load_instrument("gclef_magellan"), load_instrument("gclef_gmt")
    for am, ag in zip(m.arms, g.arms, strict=True):
        assert am.echelle_orders == ag.echelle_orders
        assert am.order_wavelength_ranges_nm == ag.order_wavelength_ranges_nm
        assert am.detector == ag.detector


def test_arm_layout_validation(tmp_path):
    f = tmp_path / "x.yaml"
    base = (
        "name: x\ndescription: d\nstatus: provisional\n"
        "channels: [{name: A, role: calibration, sources: [comb]}]\n"
    )
    f.write_text(
        base + "arms: [{name: m, channels: [A], orders: [0, 1], detector: {name: d},"
        " order_wavelength_ranges_nm: [[500, 510]]}]\n"
    )
    with pytest.raises(ConfigError, match="order_wavelength_ranges_nm/orders length"):
        load_instrument(f)
    f.write_text(
        base + "arms: [{name: m, channels: [A], orders: [0], detector: {name: d},"
        " order_wavelength_ranges_nm: [[510, 500]]}]\n"
    )
    with pytest.raises(ConfigError, match=r"\[min, max\]"):
        load_instrument(f)
    f.write_text(
        base.replace("[comb]", "[laser]")
        + "arms: [{name: m, channels: [A], orders: [0], detector: {name: d}}]\n"
    )
    with pytest.raises(ConfigError, match="not one of"):
        load_instrument(f)


def test_excluded_channel_validation(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text(
        "name: x\ndescription: d\nstatus: provisional\n"
        "channels: [{name: A, role: science}]\n"
        "arms: [{name: m, channels: [A], orders: [0], detector: {name: d}}]\n"
        "excluded: [{start: 2020-01-01, end: 2020-01-02, channels: [B]}]\n"
    )
    with pytest.raises(ConfigError, match="excluded window"):
        load_instrument(f)


def test_validation(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        "name: x\ndescription: d\nstatus: provisional\n"
        "channels: [{name: A, role: science}]\n"
        "arms: [{name: m, channels: [A, B], orders: [0], detector: {name: d}}]\n"
    )
    with pytest.raises(ConfigError, match="unknown channels"):
        load_instrument(f)
    f.write_text(
        "name: x\ndescription: d\nstatus: provisional\nwhatever: 1\nchannels: []\narms: []\n"
    )
    with pytest.raises(ConfigError, match="unknown key"):
        load_instrument(f)

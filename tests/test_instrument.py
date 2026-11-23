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
    traces = k.traces(arm.name)
    assert len(traces) == 4 * 29 - 1  # T4 of the last order is absent
    assert ("T4", 28) not in {(t.channel, t.order) for t in traces}


def test_kiwispec_eras():
    k = load_instrument("kiwispec")
    assert k.era_of(dt.date(2015, 12, 1)) is None
    assert k.era_of(dt.date(2017, 10, 2)).start == dt.date(2017, 10, 2)
    assert k.era_of(dt.date(2018, 6, 1)).start == dt.date(2017, 10, 2)
    assert k.is_excluded(dt.date(2017, 6, 1)) and not k.is_excluded(dt.date(2017, 10, 2))
    assert k.channel_epoch("T3", dt.date(2018, 8, 1)) == 1
    assert k.channel_epoch("T1", dt.date(2018, 8, 1)) == 0
    assert k.channel_epoch("T1", dt.date(2018, 12, 22)) == 1


@pytest.mark.parametrize("name, nslices", [("gclef_magellan", 1), ("gclef_gmt", 7)])
def test_gclef_placeholders(name, nslices):
    g = load_instrument(name)
    assert g.status == "placeholder" and g.gas_cell == "none"
    assert len(g.science_channels()) == nslices
    roles = {c.role for c in g.channels}
    assert {"reference_comb", "reference_etalon", "reference_thar"} <= roles
    assert [a.name for a in g.arms] == ["blue", "red"]
    assert g.wavelength_range_nm == (350.0, 1100.0)
    # unknowns stay unknown
    assert all(a.detector.gain_e_per_adu is None for a in g.arms)


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
        "name: x\ndescription: d\nstatus: provisional\nwhatever: 1\n"
        "channels: []\narms: []\n"
    )
    with pytest.raises(ConfigError, match="unknown key"):
        load_instrument(f)

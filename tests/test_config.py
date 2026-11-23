import dataclasses

import pytest
import yaml

from specfast.config import ConfigError, load_config, parse_config

GOOD = {
    "schema_version": 1,
    "instrument": "kiwispec",
    "paths": {"output": "out", "raw": "raw"},
    "doppler": {"wavelength": {"degree": 4}, "reference": {"model": "none"},
                "orders": [1, 2, 3]},
}


def test_load_resolves_relative_paths(tmp_path):
    f = tmp_path / "run.yaml"
    f.write_text(yaml.safe_dump(GOOD))
    cfg = load_config(f)
    assert cfg.paths.output == str((tmp_path / "out").resolve())
    assert cfg.doppler.wavelength.degree == 4
    assert cfg.doppler.orders == (1, 2, 3)
    assert cfg.doppler.reference.model == "none"
    assert cfg.doppler.grid.step_kms == 0.25  # default
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.instrument = "x"


@pytest.mark.parametrize(
    "mutate, msg",
    [
        (lambda d: d.update(bogus=1), "unknown key"),
        (lambda d: d["doppler"].update(segmnets_per_order=2), "unknown key"),
        (lambda d: d.pop("paths"), "required key missing"),
        (lambda d: d["doppler"]["reference"].update(model="thorium"), "not one of"),
        (lambda d: d["doppler"]["wavelength"].update(degree="3"), "expected an integer"),
        (lambda d: d["doppler"]["wavelength"].update(degree=0), "must be >= 1"),
        (lambda d: d.update(schema_version=2), "schema_version"),
    ],
)
def test_rejects_bad_config(mutate, msg):
    d = yaml.safe_load(yaml.safe_dump(GOOD))
    mutate(d)
    with pytest.raises(ConfigError, match=msg):
        parse_config(d)


def test_no_environment_expansion(monkeypatch):
    monkeypatch.setenv("SPECFAST_DATA", "/somewhere")
    d = yaml.safe_load(yaml.safe_dump(GOOD))
    d["paths"]["output"] = "$SPECFAST_DATA/out"
    assert parse_config(d).paths.output == "$SPECFAST_DATA/out"


def test_hash_tracks_content_not_formatting():
    a = parse_config(GOOD)
    b = parse_config(yaml.safe_load(yaml.safe_dump(GOOD, sort_keys=True)))
    assert a.sha256() == b.sha256()
    d = yaml.safe_load(yaml.safe_dump(GOOD))
    d["doppler"]["segments_per_order"] = 3
    assert parse_config(d).sha256() != a.sha256()

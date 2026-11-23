"""Optics tools on a synthetic design (tests/optics_synth.py): ZAR/LZW,
the .zmx parser, the tracer, the echellogram and the YAML emitter."""

from __future__ import annotations

import numpy as np
import pytest
import yaml
from optics_synth import (
    DX,
    HALF,
    ORDERS,
    T1,
    T2,
    expected_xy,
    lzw_compress,
    zar_bytes,
    zmx_text,
)

from specfast.instrument import load_instrument
from specfast.optics import cli
from specfast.optics.echellogram import InputPoint, build
from specfast.optics.glass import GlassLibrary, parse_agf
from specfast.optics.trace import StandIn, System, TraceError
from specfast.optics.zar import decode_text, lzw_decompress, read_zar
from specfast.optics.zmx import parse_zmx

# A Sellmeier-1 glass (n_d = 1.5168).
AGF = (
    "CC test\nNM TESTBK 2 517642 1.5168 64.17 0 0\n"
    "CD 1.03961212 6.00069867e-3 0.231792344 2.00179144e-2 1.01046945 103.560653\n"
)


def system(config=1, **kw):
    lens = parse_zmx(zmx_text())
    surfs, _ = lens.configured(config)
    return System(surfs, GlassLibrary(), echelle=2, **kw)


@pytest.mark.parametrize("n", [0, 1, 300, 70000])
def test_lzw_roundtrip(n):
    rng = np.random.default_rng(n)
    data = bytes(rng.choice(list(b"SURF 0123456789 abc\n"), size=n))
    assert lzw_decompress(lzw_compress(data)) == data


def test_zar_roundtrip(tmp_path):
    text = zmx_text().replace("\n", "\r\n").encode("utf-16")
    p = tmp_path / "d.zar"
    p.write_bytes(zar_bytes({"d.zmx": text, "g.agf": AGF.encode()}))
    files = read_zar(p)
    assert set(files) == {"d.zmx", "g.agf"}
    assert decode_text(files["d.zmx"]) == zmx_text()


def test_parse_and_configs():
    lens = parse_zmx(zmx_text())
    assert len(lens.surfaces) == 8 and lens.stop_index == 2
    assert lens.nconf == 2 and lens.config_labels[0] == "ORDER 20"
    assert [f.y for f in lens.fields] == [0.0, 0.2, -0.2] and lens.fields[1].comment == "upper"
    for c, m in enumerate(ORDERS, 1):
        surfs, waves = lens.configured(c)
        assert surfs[2].parm[2] == m and waves == [0.5]
    assert lens.surfaces[2].parm[2] == ORDERS[0]  # the stored lens is unchanged


def test_glass_sellmeier():
    g = GlassLibrary([parse_agf(AGF)])
    assert g["testbk"].index(0.5875618) == pytest.approx(1.5168, abs=2e-5)


@pytest.mark.parametrize("config", [1, 2])
def test_trace_matches_grating_equation(config):
    s = system(config)
    m = ORDERS[config - 1]
    lam = np.array([0.47, 0.48, 0.49])
    for x0, y0 in [(0.0, 0.0), (0.0, 0.2), (0.1, -0.2)]:
        got = s.image_xy(np.full(3, x0), np.full(3, y0), lam)
        want = np.array([expected_xy(x0, y0, la, m) for la in lam])
        np.testing.assert_allclose(got, want, atol=1e-7)
    # the order override reproduces the other configuration
    got = s.image_xy([0.0], [0.0], [0.48], order=31)
    np.testing.assert_allclose(got[0], expected_xy(0.0, 0.0, 0.48, 31), atol=1e-7)


def test_blackbox_needs_standin():
    lens = parse_zmx(zmx_text())
    surfs, _ = lens.configured(1)
    surfs[4].type = "BLACKBOX"
    with pytest.raises(TraceError, match="black box"):
        System(surfs, GlassLibrary(), echelle=2)
    st = {4: StandIn("grating", lines_per_um=T2, order=1.0)}
    s = System(surfs, GlassLibrary(), st, echelle=2)
    np.testing.assert_allclose(
        s.image_xy([0.0], [0.0], [0.48])[0], expected_xy(0, 0, 0.48, ORDERS[0]), atol=1e-7
    )


def _edge_wavelength(m, side):
    """Wavelength where the axis trace crosses x = side * HALF[0] (bisection
    on the analytic answer)."""
    lc = (DX / 200.0) / T1 / m
    lo, hi = lc, lc * (1 + side * 3.0 / m)
    target = side * HALF[0]
    f = lambda la: expected_xy(0, 0, la, m)[0] - target  # noqa: E731
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if np.sign(f(mid)) == np.sign(f(lo)):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def test_echellogram_orders_and_ranges():
    s = system(1)
    pts = [InputPoint("axis", 0.0, 0.0), InputPoint("up", 0.0, 0.2)]
    m_lam = (DX / 200.0) / T1  # blaze centred on the detector centre
    eg = build(s, pts, m_lam, HALF, core_mm=0.05)
    assert eg.disp_axis == 0
    ms = [o.m for o in eg.orders]
    assert ms == sorted(ms, reverse=True) and len(ms) >= 3
    n_x_limited = 0
    for o in eg.orders:
        want = sorted([_edge_wavelength(o.m, -1), _edge_wavelength(o.m, 1)])
        if all(abs(expected_xy(0, 0, la, o.m)[1]) <= HALF[1] for la in want):
            # the order leaves the chip through its dispersion-direction edges
            assert o.lam_lo == pytest.approx(want[0], abs=1e-7)
            assert o.lam_hi == pytest.approx(want[1], abs=1e-7)
            n_x_limited += 1
        else:
            # it leaves through a cross-dispersion edge: the ends lie on the boundary
            for la in (o.lam_lo, o.lam_hi):
                x, y = expected_xy(0, 0, la, o.m)
                assert min(abs(abs(x) - HALF[0]), abs(abs(y) - HALF[1])) < 1e-5
                assert abs(x) <= HALF[0] + 1e-6 and abs(y) <= HALF[1] + 1e-6
        x, y = expected_xy(0, 0, o.lam_centre, o.m)
        assert abs(x) < 1e-6 and o.cross_mm[0] == pytest.approx(y, abs=1e-6)
        assert o.resolving_power > 0
    assert n_x_limited >= 3
    # the analytic order list: every order whose centre is on the chip
    centre_y = {m: expected_xy(0, 0, m_lam / m, m)[1] for m in range(5, 60)}
    assert set(ms) <= {m for m, y in centre_y.items() if abs(y) < HALF[1] + 0.5}


def test_cli_writes_loadable_yaml(tmp_path):
    zar = tmp_path / "d.zar"
    zar.write_bytes(zar_bytes({"d.zmx": zmx_text().encode(), "g.agf": AGF.encode()}))
    params = {
        "echelle_surface": 2,
        "points": [
            {"name": "a", "x_mm": 0.1, "y_mm": 0.0},
            {"name": "b", "x_mm": -0.1, "y_mm": 0.0},
            {"name": "axis", "x_mm": 0.0, "y_mm": 0.0},
        ],
        "reference_point": "axis",
        "core_mm": 0.05,
        "modes": [
            {"name": "wide", "point": "a", "core_mm": 0.1},
            {
                "name": "pair",
                "point": "axis",
                "slit_pitch": {"from": "a", "to": "b", "positions": 2},
            },
        ],
        "arms": [
            {
                "name": "main",
                "config": 1,
                "m_lambda_um": (DX / 200.0) / T1,
                "slit_pitch": {"from": "a", "to": "b", "positions": 2},
            }
        ],
    }
    overrides = {
        "_header": ["synthetic"],
        "name": "synth",
        "description": "made-up echelle",
        "status": "provisional",
        "channels": [
            {"name": "A", "role": "science"},
            {"name": "B", "role": "calibration", "sources": ["comb"]},
        ],
        "arms": [
            {
                "name": "main",
                "channels": ["A", "B"],
                "detector": {"name": "ccd", "pixel_size_um": 10.0, "gain_e_per_adu": None},
            }
        ],
        "modes": [
            {"name": "wide", "channels": ["A"], "fibre_core_um": 100.0},
            {"name": "pair", "channels": ["A", "B"]},
        ],
        "default_mode": "pair",
    }
    (tmp_path / "p.yaml").write_text(yaml.safe_dump(params))
    (tmp_path / "o.yaml").write_text(yaml.safe_dump(overrides))
    out = tmp_path / "synth.yaml"
    rc = cli.main(
        [
            str(zar),
            "--params",
            str(tmp_path / "p.yaml"),
            "--overrides",
            str(tmp_path / "o.yaml"),
            "--out",
            str(out),
            "--provenance",
            "derived (test)",
            "--echellogram",
            str(tmp_path / "e.npz"),
        ]
    )
    assert rc == 0
    text = out.read_text()
    assert text.startswith("# synthetic\n") and "# derived (test)" in text
    inst = load_instrument(out)
    (arm,) = inst.arms
    assert arm.detector.npix_dispersion == round(2 * HALF[0] / 0.01)
    assert arm.detector.npix_cross_dispersion == round(2 * HALF[1] / 0.01)
    assert arm.detector.gain_e_per_adu is None
    assert inst.channel("B").sources == ("comb",)
    assert len(arm.echelle_orders) == len(arm.orders) == len(arm.order_wavelength_ranges_nm)
    i = len(arm.orders) // 2  # an order cut by the dispersion-direction edges
    m0 = arm.echelle_orders[i]
    lo = _edge_wavelength(m0, -1) * 1000
    hi = _edge_wavelength(m0, 1) * 1000
    assert arm.order_wavelength_ranges_nm[i] == pytest.approx(sorted([lo, hi]), abs=1e-3)
    # slit x maps onto the cross-dispersion axis at magnification F_CAM / F_COLL = 2,
    # times 1/cos of the echelle's ~0.1 rad deflection (exact: the trace tests above)
    assert arm.slit_pitch_px == pytest.approx(0.1 * 2 / 0.01 / np.sqrt(1 - 0.1**2), rel=2e-3)
    assert arm.resolving_power > 0
    assert np.load(tmp_path / "e.npz")["main_xy_mm"].shape[1] == 3
    wide, pair = inst.modes
    assert inst.mode() is pair and inst.mode("wide").fibre_core_um == 100.0
    (wa,) = wide.arms
    # twice the core of the arm's reference fibre: half the resolving power
    assert wa.resolving_power == pytest.approx(arm.resolving_power / 2, rel=0.02)
    # point "a" is offset across the slit only: no offset along the dispersion
    assert abs(wa.dispersion_offset_px) < 0.5
    assert pair.arms[0].resolving_power is None
    assert pair.arms[0].slit_pitch_px == arm.slit_pitch_px
    assert {t.channel for t in inst.traces("main", "wide")} == {"A"}
    assert {t.channel for t in inst.traces("main")} == {"A", "B"}

"""``specfast-zemax2instrument``: a Zemax design to an instrument YAML.

Usage::

    specfast-zemax2instrument DESIGN.zar --params P.yaml --overrides O.yaml \\
        --out instrument.yaml [--echellogram E.npz] [--summary S.txt]

``DESIGN`` is a ``.zar`` archive (its ``.zmx`` and ``.agf`` files are used)
or a ``.zmx`` file (give catalogues with ``--glass``). All inputs come from
the command line; nothing is read from fixed paths or the environment.

The parameters file (YAML) says how to trace the design. Every key is
optional unless marked:

``echelle_surface``  surface whose diffraction order is scanned (default: the
                     stop, if it is a grating)
``start_surface``    surface the rays start from (default 0, the object)
``image_surface``    last surface traced (default: the last surface)
``standins``         ``{surface: {kind: ..., ...}}`` replacements for black
                     boxes (see :class:`specfast.optics.trace.StandIn`); an
                     encrypted black box without one is an error
``points``           ``[{name, x_mm, y_mm}]`` start-surface points to trace
                     (default: the design's fields)
``reference_point``  name of the point used for ranges and resolution
                     (default: the first)
``core_mm``          fibre core / slit width at the start surface, for the
                     resolving power
``half_size_mm``     detector half-sizes [x, y] (default: the image
                     surface's rectangular aperture)
``wavelengths``      ``design`` (default: write the design's wavelengths) or
                     ``air_to_vacuum`` (multiply by the index of air at the
                     design's temperature and pressure)
``arms``             ``[{name, config, m_range: [lo, hi], m_lambda_um,
                     slit_pitch: {from, to, positions}, complete_only}]``
                     (default: one arm per ``--config``)
``modes``            ``[{name, point, core_mm, slit_pitch: {from, to,
                     positions}}]``: observing modes whose fibres the design
                     models; per arm, the tool derives each mode's
                     resolving power (fibre of ``core_mm`` at ``point``),
                     its row's offset along the dispersion and its slit
                     pitch. The overrides must give each mode's channels.

The overrides file (YAML) is merged on top of the generated description:
names, channels and roles, gain, read noise, site and so on. Each arm's
``detector.pixel_size_um`` must be given there (or with ``--pixel-um``):
lens files hold the detector's size, not its pixel pitch. A top-level
``_header`` list becomes the file's leading comment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

from specfast.instrument import load_instrument
from specfast.optics import emit
from specfast.optics.echellogram import Echellogram, InputPoint, build
from specfast.optics.glass import GlassLibrary, parse_agf
from specfast.optics.trace import StandIn, System
from specfast.optics.zar import decode_text, find, read_zar
from specfast.optics.zmx import Lens, parse_zmx


def load_design(path: Path, extra_glass: list[Path]) -> tuple[Lens, GlassLibrary, list[str]]:
    """Lens, glass library and the names of black-box files in an archive
    (which are listed, never read)."""
    glasses = GlassLibrary()
    blackboxes: list[str] = []
    if path.suffix.lower() == ".zar":
        files = read_zar(path)
        zmx = find(files, ".zmx")
        if len(zmx) != 1:
            raise SystemExit(f"{path}: expected one .zmx in the archive, found {zmx}")
        lens = parse_zmx(files[zmx[0]])
        for name in find(files, ".agf"):
            glasses.add(parse_agf(decode_text(files[name])))
        blackboxes = find(files, ".zbb")
    else:
        lens = parse_zmx(path)
    for g in extra_glass:
        glasses.add(parse_agf(decode_text(g.read_bytes())))
    return lens, glasses, blackboxes


def air_index(lam_um: float, t_c: float, p_atm: float) -> float:
    """Index of dry air (Edlen 1966, scaled to t, p)."""
    s2 = 1.0 / lam_um**2
    ns = 1 + 1e-8 * (8342.13 + 2406030 / (130 - s2) + 15997 / (38.9 - s2))
    return 1 + (ns - 1) * p_atm * (1 + 0.003661 * 15.0) / (1 + 0.003661 * t_c)


def trace_arms(lens: Lens, glasses: GlassLibrary, params: dict, configs: list[int]):
    """Echellogram per arm: list of (arm spec, Echellogram, System)."""
    arms = params.get("arms") or [{"name": f"arm{c}", "config": c} for c in configs]
    standins = {int(k): StandIn(**v) for k, v in (params.get("standins") or {}).items()}
    if params.get("points"):
        points = [
            InputPoint(p["name"], float(p["x_mm"]), float(p["y_mm"])) for p in params["points"]
        ]
    else:
        points = [
            InputPoint(f.comment or f"field{i + 1}", f.x, f.y) for i, f in enumerate(lens.fields)
        ] or [InputPoint("axis", 0.0, 0.0)]
    names = [p.name for p in points]
    ref = names.index(params["reference_point"]) if "reference_point" in params else 0
    out = []
    for spec in arms:
        surfs, waves = lens.configured(int(spec["config"]))
        start = int(params.get("start_surface", 0))
        image = params.get("image_surface")
        image = int(image) if image is not None else len(surfs) - 1
        ech = params.get("echelle_surface")
        if ech is None:
            stop = lens.stop_index
            if surfs[stop].type != "DGRATING":
                raise SystemExit("give echelle_surface: the stop is not a grating")
            ech = stop
        ech = int(ech)
        system = System(surfs, glasses, standins, start=start, image=image, echelle=ech)
        half = params.get("half_size_mm") or surfs[image].rect_aperture
        if half is None:
            raise SystemExit("give half_size_mm: the image surface has no rectangular aperture")
        if "m_lambda_um" in spec:
            m_lam = float(spec["m_lambda_um"])
        else:
            primary = waves[lens.primary_wave - 1]
            m_lam = abs(surfs[ech].parm.get(2, 0.0)) * primary
        mr = tuple(spec["m_range"]) if spec.get("m_range") else None
        eg = build(
            system,
            points,
            m_lam,
            (float(half[0]), float(half[1])),
            ref=ref,
            core_mm=params.get("core_mm"),
            m_range=mr,
        )
        out.append((spec, eg, system))
    return out, points


def save_echellogram(path: Path, results: list[tuple[dict, Echellogram, System]], points) -> None:
    """All traced positions (private product: derived from the design)."""
    data = {"point_names": np.array([p.name for p in points])}
    for spec, eg, _ in results:
        a = spec["name"]
        data[f"{a}_m"] = np.array([o.m for o in eg.orders])
        data[f"{a}_lam_um"] = np.array([o.lam for o in eg.orders])
        data[f"{a}_xy_mm"] = np.array([o.xy for o in eg.orders])
        data[f"{a}_range_um"] = np.array([[o.lam_lo, o.lam_hi] for o in eg.orders])
        data[f"{a}_centre_um"] = np.array([o.lam_centre for o in eg.orders])
        data[f"{a}_dlam_dmm"] = np.array([o.dlam_dmm for o in eg.orders])
        data[f"{a}_cross_mm"] = np.array([o.cross_mm for o in eg.orders])
        data[f"{a}_complete"] = np.array([o.complete for o in eg.orders])
        data[f"{a}_R"] = np.array([o.resolving_power or np.nan for o in eg.orders])
        data[f"{a}_disp_axis"] = np.array(eg.disp_axis)
    np.savez(path, **data)


def summary(results, pixel_um: dict[str, float]) -> str:
    lines = []
    for spec, eg, _ in results:
        a = spec["name"]
        pix = pixel_um.get(a)
        lines.append(
            f"arm {a} (config {spec['config']}), dispersion along detector "
            f"{'xy'[eg.disp_axis]}; partial orders {eg.partial_orders}"
        )
        lines.append("   m   lo_nm    hi_nm   centre   fsr_nm  nm/px     R     cross_mm  complete")
        for o in eg.orders:
            npx = o.dlam_dmm * 1000 * (pix or float("nan")) / 1000
            lines.append(
                f"{o.m:4d} {o.lam_lo * 1e3:8.3f} {o.lam_hi * 1e3:8.3f} {o.lam_centre * 1e3:8.3f} "
                f"{o.fsr * 1e3:7.3f} {npx:8.5f} {o.resolving_power or 0:7.0f} "
                f"{o.cross_mm[eg.ref]:8.3f} {o.complete}"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="specfast-zemax2instrument",
        description="Generate a specfast instrument YAML from a Zemax design.",
    )
    ap.add_argument("design", type=Path, help=".zar archive or .zmx lens file")
    ap.add_argument("--out", type=Path, required=True, help="instrument YAML to write")
    ap.add_argument(
        "--params",
        "--blackbox-params",
        type=Path,
        dest="params",
        help="tracing parameters and black-box stand-ins (YAML)",
    )
    ap.add_argument("--overrides", type=Path, help="facts the design lacks (YAML), merged on top")
    ap.add_argument("--glass", type=Path, action="append", default=[], help="extra .agf catalogue")
    ap.add_argument(
        "--config",
        type=int,
        action="append",
        default=[],
        help="configuration(s) to trace when the parameters name no arms",
    )
    ap.add_argument("--pixel-um", type=float, help="pixel size for arms the overrides do not set")
    ap.add_argument(
        "--provenance",
        default="derived from the optical design",
        help="comment written after every generated value",
    )
    ap.add_argument("--echellogram", type=Path, help="also save all traced positions (.npz)")
    ap.add_argument("--summary", type=Path, help="also write a per-order text summary")
    args = ap.parse_args(argv)

    params = yaml.safe_load(args.params.read_text()) if args.params else {}
    overrides = yaml.safe_load(args.overrides.read_text()) if args.overrides else {}
    params = params or {}
    overrides = overrides or {}
    lens, glasses, blackboxes = load_design(args.design, args.glass)
    if blackboxes:
        print(f"black boxes in the archive (not read): {blackboxes}", file=sys.stderr)
    results, points = trace_arms(lens, glasses, params, args.config or [1])

    ov_arms = {a["name"]: a for a in overrides.get("arms", []) if isinstance(a, dict)}
    pixel_um = {}
    for spec, _, _ in results:
        p = (ov_arms.get(spec["name"], {}).get("detector") or {}).get(
            "pixel_size_um", args.pixel_um
        )
        if p is None:
            raise SystemExit(f"arm {spec['name']}: give detector.pixel_size_um in the overrides")
        pixel_um[spec["name"]] = float(p)
    scale = 1.0
    if params.get("wavelengths", "design") == "air_to_vacuum":
        scale = air_index(0.55, lens.temperature_c, lens.pressure_atm)
    names = [p.name for p in points]
    gen_arms = []
    for spec, eg, _ in results:
        sp = spec.get("slit_pitch")
        pitch = (
            (names.index(sp["from"]), names.index(sp["to"]), float(sp["positions"])) if sp else None
        )
        facts = emit.arm_facts(
            eg, pixel_um[spec["name"]], pitch, spec.get("complete_only", True), scale
        )
        gen_arms.append({"name": spec["name"], **facts})
    generated = {"arms": gen_arms}
    gen_modes = []
    for mspec in params.get("modes") or []:
        mp = mspec.get("slit_pitch")
        mpitch = (
            (names.index(mp["from"]), names.index(mp["to"]), float(mp["positions"])) if mp else None
        )
        if mspec["point"] not in names:
            raise SystemExit(f"mode {mspec['name']}: no point {mspec['point']!r}")
        marms = []
        for spec, eg, system in results:
            f = emit.mode_arm_facts(
                system,
                eg,
                pixel_um[spec["name"]],
                names.index(mspec["point"]),
                mspec.get("core_mm"),
                mpitch,
                spec.get("complete_only", True),
            )
            marms.append({"name": spec["name"], **f})
        gen_modes.append({"name": mspec["name"], "arms": marms})
    if gen_modes:
        generated["modes"] = gen_modes
    lo = min(a["wavelength_range_nm"][0] for a in gen_arms)
    hi = max(a["wavelength_range_nm"][1] for a in gen_arms)
    generated["wavelength_range_nm"] = [lo, hi]
    derived = emit.derived_paths(generated)
    header = overrides.pop(emit.HEADER_KEY, None)
    touched: set = set()
    doc = emit.merge(generated, overrides, (), touched)
    doc["__derived__"] = derived - touched
    text = emit.to_yaml(doc, args.provenance, header)
    args.out.write_text(text)
    load_instrument(args.out)  # the output must load
    if args.echellogram:
        save_echellogram(args.echellogram, results, points)
    if args.summary:
        args.summary.write_text(summary(results, pixel_um))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

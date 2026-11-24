"""Turn echellograms into an instrument description (YAML).

The generated part holds only derived physical facts: per arm, the echelle
orders on the detector and their wavelength ranges, the detector format, the
resolving power, the order spacing and the slit pitch. Everything the design
does not give (names, channel roles, gain, read noise, site, ...) comes from
an overrides mapping merged on top. Nothing is invented: a key that neither
source sets is left out (the loader's default, usually null).

Every generated value is written with a trailing provenance comment.
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from specfast.optics.echellogram import Echellogram, point_facts
from specfast.optics.trace import System

#: Overrides keys that are not part of the instrument schema.
HEADER_KEY = "_header"


def arm_facts(
    eg: Echellogram,
    pixel_size_um: float,
    slit_pitch: tuple[int, int, float] | None = None,
    complete_only: bool = True,
    wavelength_scale: float = 1.0,
) -> dict[str, Any]:
    """Derived facts of one arm.

    slit_pitch: (point i, point j, number of slit positions between them):
        the cross-dispersion distance between adjacent slit positions is the
        median over orders of |cross(i) - cross(j)| / n.
    wavelength_scale: factor applied to the design wavelengths (1, or the
        index of air to convert air to vacuum wavelengths).
    """
    pix_mm = pixel_size_um / 1000.0
    orders = [o for o in eg.orders if o.complete or not complete_only]
    orders.sort(key=lambda o: -o.m)  # index 0 = bluest
    if not orders:
        raise ValueError("no complete order on the detector")
    nm = 1000.0 * wavelength_scale
    ranges = [[_r(o.lam_lo * nm, 3), _r(o.lam_hi * nm, 3)] for o in orders]
    hx, hy = eg.half_size
    nd = round(2 * (hx, hy)[eg.disp_axis] / pix_mm)
    nc = round(2 * (hy, hx)[eg.disp_axis] / pix_mm)
    cross = np.array([o.cross_mm[eg.ref] for o in orders])
    spacing = np.abs(np.diff(cross)) / pix_mm
    out: dict[str, Any] = {
        "orders": list(range(len(orders))),
        "echelle_orders": [o.m for o in orders],
        "wavelength_range_nm": [
            _r(min(r[0] for r in ranges), 1),
            _r(max(r[1] for r in ranges), 1),
        ],
        "order_wavelength_ranges_nm": ranges,
        "order_spacing_px": [_r(spacing.min(), 1), _r(spacing.max(), 1)] if len(spacing) else None,
        "detector": {
            "npix_dispersion": int(nd),
            "npix_cross_dispersion": int(nc),
        },
    }
    rs = [o.resolving_power for o in orders if o.resolving_power]
    if rs:
        out["resolving_power"] = float(round(float(np.median(rs)), -2))
    if slit_pitch is not None:
        i, j, n = slit_pitch
        p = np.median([abs(o.cross_mm[i] - o.cross_mm[j]) for o in orders]) / n / pix_mm
        out["slit_pitch_px"] = _r(p, 2)
    return out


def mode_arm_facts(
    sys: System,
    eg: Echellogram,
    pixel_size_um: float,
    point: int,
    core_mm: float | None = None,
    slit_pitch: tuple[int, int, float] | None = None,
    complete_only: bool = True,
) -> dict[str, Any]:
    """Derived facts of one observing mode on one arm: the resolving power of
    the mode's fibre (core ``core_mm`` at start-surface point ``point``), the
    offset of its row along the dispersion from the arm's reference trace,
    and its slit pitch (as in :func:`arm_facts`). Medians over orders."""
    pix_mm = pixel_size_um / 1000.0
    keep = [o.complete or not complete_only for o in eg.orders]
    allf = point_facts(sys, eg, point, core_mm)
    facts = [f for f, k in zip(allf, keep, strict=True) if k]
    out: dict[str, Any] = {
        "dispersion_offset_px": _r(np.median([f[1] for f in facts]) / pix_mm, 1),
    }
    rs = [f[0] for f in facts if f[0]]
    if rs:
        out["resolving_power"] = float(round(float(np.median(rs)), -2))
    if slit_pitch is not None:
        i, j, n = slit_pitch
        orders = [o for o, k in zip(eg.orders, keep, strict=True) if k]
        p = np.median([abs(o.cross_mm[i] - o.cross_mm[j]) for o in orders]) / n / pix_mm
        out["slit_pitch_px"] = _r(p, 2)
    return out


def _r(x: float, nd: int) -> float:
    return float(round(float(x), nd))


# ------------------------------------------------------------------ merging
def merge(base: Any, over: Any, path: tuple = (), touched: set | None = None) -> Any:
    """Deep-merge ``over`` onto ``base``. Mappings merge key by key; lists of
    mappings that all have a ``name`` merge item by item by name (items only
    in ``over`` are appended); anything else in ``over`` replaces ``base``.
    Paths set from ``over`` are added to ``touched``."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = (
                merge(base[k], v, path + (k,), touched)
                if k in base
                else _mark(v, path + (k,), touched)
            )
        return out
    if _named_list(base) and _named_list(over):
        out = list(base)
        names = [b["name"] for b in base]
        for item in over:
            if item["name"] in names:
                i = names.index(item["name"])
                out[i] = merge(base[i], item, path + (i,), touched)
            else:
                out.append(_mark(item, path + (len(out),), touched))
        return out
    return _mark(over, path, touched)


def _named_list(x: Any) -> bool:
    return isinstance(x, list) and all(isinstance(i, dict) and "name" in i for i in x)


def _mark(v, path, touched):
    if touched is not None:
        touched.add(path)
    return v


def derived_paths(obj: Any, path: tuple = ()) -> set:
    """Every leaf path of a generated mapping (``name`` keys, which only
    identify list items, excluded)."""
    if isinstance(obj, dict):
        out = set()
        for k, v in obj.items():
            if k != "name":
                out |= derived_paths(v, path + (k,))
        return out
    if _named_list(obj):
        out = set()
        for i, v in enumerate(obj):
            out |= derived_paths(v, path + (i,))
        return out
    return {path}


# ------------------------------------------------------------------ writing
_ORDER = [
    "name",
    "description",
    "status",
    "gas_cell",
    "wavelength_range_nm",
    "site",
    "header",
    "channels",
    "arms",
    "eras",
    "excluded",
    "channel_breaks",
    "default_mode",
    "modes",
    "notes",
]


def to_yaml(doc: dict, provenance: str, header: list[str] | None = None) -> str:
    """Write ``doc`` as YAML. Leaves whose path is in ``doc["__derived__"]``
    (removed before writing) get the trailing comment ``# <provenance>``."""
    derived = set(doc.pop("__derived__", set()))
    lines = [f"# {h}" if h else "#" for h in (header or [])]
    keys = [k for k in _ORDER if k in doc] + [k for k in doc if k not in _ORDER]
    for k in keys:
        lines += _emit(k, doc[k], 0, (k,), derived, provenance)
    return "\n".join(lines) + "\n"


def _emit(key, val, ind, path, derived, prov) -> list[str]:
    pad = " " * ind
    head = f"{pad}{key}:" if key is not None else ""
    if isinstance(val, dict) and val and not _short(val):
        out = [head]
        for k, v in _ordered(val):
            out += _emit(k, v, ind + 2, path + (k,), derived, prov)
        return out
    if isinstance(val, list) and val and all(isinstance(v, dict) for v in val):
        out = [head]
        for i, item in enumerate(val):
            sub = _emit_item(item, ind + 2, path + (i,), derived, prov)
            out += sub
        return out
    if isinstance(val, list) and val and all(isinstance(v, str) for v in val):
        if any(len(v) > 60 for v in val):
            out = [head]
            for v in val:
                if len(v) > 70:
                    out += [f"{pad}  - >-", *_fold(v, ind + 4)]
                else:
                    out.append(f"{pad}  - {_flow(v)}")
            return out
    if isinstance(val, str) and len(val) > 70:
        return [f"{head} >-", *_fold(val, ind + 2)]
    text = _flow(val)
    comment = f"  # {prov}" if path in derived else ""
    line = f"{head} {text}"
    if len(line) + len(comment) > 99 and isinstance(val, list):
        return _wrap(head, val, ind, comment)
    return [line + comment]


def _emit_item(item: dict, ind: int, path, derived, prov) -> list[str]:
    pad = " " * ind
    if _short(item) and not any(path + (k,) in derived for k in item):
        return [f"{pad}- {_flow(item)}"]
    out = []
    first = True
    for k, v in _ordered(item):
        sub = _emit(k, v, ind + 2, path + (k,), derived, prov)
        if first:
            sub[0] = f"{pad}- " + sub[0].lstrip()
            first = False
        out += sub
    return out


#: Keys written first, in this order, wherever they occur (dicts keep their
#: own order otherwise; ``detector``, a mode's ``arms`` and ``notes`` go last).
_FIRST = ["name", "role", "channels", "orders", "rv_orders", "echelle_orders"]
_LAST = ["detector", "absent_traces", "arms", "notes"]


def _ordered(d: dict):
    keys = [k for k in _FIRST if k in d]
    keys += [k for k in d if k not in _FIRST and k not in _LAST]
    keys += [k for k in _LAST if k in d]
    return [(k, d[k]) for k in keys]


def _short(d: dict) -> bool:
    return all(not isinstance(v, dict | list) or not v for v in d.values()) and len(_flow(d)) < 90


def _wrap(head: str, val: list, ind: int, comment: str) -> list[str]:
    items = [_flow(v) for v in val]
    out = [f"{head}{comment}"]
    pad = " " * (ind + 2)
    line = pad + "["
    for i, it in enumerate(items):
        piece = it + ("," if i < len(items) - 1 else "]")
        if len(line) + len(piece) + 1 > 99 and line.strip() != "[":
            out.append(line.rstrip())
            line = pad + " "
        line += piece + " "
    out.append(line.rstrip())
    return out


def _flow(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return ".nan"
        return repr(v)
    if isinstance(v, str):
        if v and all(c.isalnum() or c in "_-./ ()" for c in v) and not v[0].isdigit():
            if v not in ("null", "true", "false", "yes", "no", "on", "off") and v.strip() == v:
                return v
        return json.dumps(v)
    if isinstance(v, list | tuple):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_flow(x)}" for k, x in v.items()) + "}"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    raise TypeError(f"cannot write {type(v).__name__}")


def _fold(text: str, ind: int) -> list[str]:
    words = text.split()
    out, line = [], " " * ind
    for w in words:
        if len(line) + len(w) + 1 > 80 and line.strip():
            out.append(line.rstrip())
            line = " " * ind
        line += w + " "
    out.append(line.rstrip())
    return out

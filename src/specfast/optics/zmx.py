"""Parse a sequential Zemax lens file (``.zmx``).

What is read: surfaces (type, comment, curvature, conic, thickness, glass,
parameters, extra data, stop, semi-diameter, rectangular aperture), the
pickup solves that tie surfaces together (curvature, thickness, parameter and
glass pickups), fields (object x/y and their comments), wavelengths, the
multi-configuration editor (``PRAM``, ``THIC``, ``GLSS``, ``IGNR``,
``IGNM``, ``WAVE``, ``CRVT``, ``CONN`` and config labels) and a few header
keys. Other keys are ignored. Units are as in the file (lens units are
assumed to be mm; :func:`parse_zmx` checks).

:meth:`Lens.configured` returns the surfaces of one configuration with its
operands applied and the pickups re-evaluated, as Zemax does.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

from specfast.optics.zar import decode_text


class ZmxError(ValueError):
    """A lens file this parser cannot interpret."""


@dataclass
class Surface:
    index: int
    type: str = "STANDARD"
    comment: str = ""
    curv: float = 0.0
    conic: float = 0.0
    thick: float = 0.0
    #: Glass name, "MIRROR", or None (the medium of the previous surface is
    #: kept only after a mirror; otherwise None means air).
    glass: str | None = None
    parm: dict[int, float] = field(default_factory=dict)
    xdat: dict[int, float] = field(default_factory=dict)
    stop: bool = False
    ignored: bool = False
    semi_diameter: float | None = None
    #: Rectangular aperture half-widths (x, y), if any.
    rect_aperture: tuple[float, float] | None = None
    #: Pickups: ("curv", src, scale, offset), ("thick", src, scale, offset),
    #: ("parm", p, src, scale, offset, col), ("glass", src).
    pickups: list[tuple] = field(default_factory=list)


@dataclass
class Field:
    x: float
    y: float
    weight: float = 1.0
    comment: str = ""


@dataclass
class Lens:
    name: str = ""
    notes: list[str] = field(default_factory=list)
    surfaces: list[Surface] = field(default_factory=list)
    fields: list[Field] = field(default_factory=list)
    #: Wavelengths [um] of the current (stored) configuration.
    wavelengths: list[float] = field(default_factory=list)
    #: 1-based index of the primary wavelength.
    primary_wave: int = 1
    #: Object-space numerical aperture, if the aperture type is object NA.
    object_na: float | None = None
    #: Environment: temperature [C], pressure [atm].
    temperature_c: float = 20.0
    pressure_atm: float = 1.0
    glass_catalogs: list[str] = field(default_factory=list)
    nconf: int = 1
    #: Multi-configuration rows: (operand, surface/index, param, values per config).
    mce: list[tuple[str, int, int, list]] = field(default_factory=list)
    #: Labels of each configuration (first labelled MOFF row), or "".
    config_labels: list[str] = field(default_factory=list)

    @property
    def stop_index(self) -> int:
        for s in self.surfaces:
            if s.stop:
                return s.index
        raise ZmxError("no stop surface")

    def configured(self, config: int) -> tuple[list[Surface], list[float]]:
        """Surfaces and wavelengths [um] of configuration ``config`` (1-based),
        with its operands applied and pickups re-evaluated."""
        if not 1 <= config <= self.nconf:
            raise ZmxError(f"config {config} not in 1..{self.nconf}")
        surfs = copy.deepcopy(self.surfaces)
        waves = list(self.wavelengths)
        for op, s, p, vals in self.mce:
            v = vals[config - 1]
            if v is None:
                continue
            if op == "PRAM":
                surfs[s].parm[p] = float(v)
            elif op == "XDAT":
                surfs[s].xdat[p] = float(v)
            elif op == "THIC":
                surfs[s].thick = float(v)
            elif op == "CRVT":
                surfs[s].curv = float(v)
            elif op == "CONN":
                surfs[s].conic = float(v)
            elif op == "GLSS":
                surfs[s].glass = None if v == "" else str(v)
            elif op == "IGNR":
                surfs[s].ignored = bool(round(float(v)))
            elif op == "IGNM":
                for k in range(s, p + 1):
                    surfs[k].ignored = bool(round(float(v)))
            elif op == "WAVE":
                while len(waves) < s:
                    waves.append(float("nan"))
                waves[s - 1] = float(v)
        apply_pickups(surfs)
        return surfs, waves


def apply_pickups(surfs: list[Surface]) -> None:
    """Re-evaluate pickup solves in surface order (in place)."""
    for s in surfs:
        for pk in s.pickups:
            kind = pk[0]
            if kind == "curv":
                _, src, scale, offset = pk
                s.curv = scale * surfs[src].curv + offset
            elif kind == "thick":
                _, src, scale, offset = pk
                s.thick = scale * surfs[src].thick + offset
            elif kind == "parm":
                _, p, src, scale, offset, col = pk
                s.parm[p] = scale * surfs[src].parm.get(col or p, 0.0) + offset
            elif kind == "glass":
                s.glass = surfs[pk[1]].glass


_MCE_OPS = {"PRAM", "XDAT", "THIC", "CRVT", "CONN", "GLSS", "IGNR", "IGNM", "WAVE"}


def _int(t: str) -> int:
    return int(float(t))


def _floats(tokens: list[str]) -> list[float]:
    return [float(t) for t in tokens]


def parse_zmx(source: str | Path | bytes) -> Lens:
    """Parse a lens file given as a path, raw bytes, or text."""
    if isinstance(source, bytes):
        text = decode_text(source)
    elif isinstance(source, Path) or (isinstance(source, str) and "\n" not in source):
        text = decode_text(Path(source).read_bytes())
    else:
        text = source
    lens = Lens()
    cur: Surface | None = None
    xfln: list[float] = []
    yfln: list[float] = []
    fwgn: list[float] = []
    fcom: dict[int, str] = {}
    waves: dict[int, float] = {}
    rows: dict[tuple[str, int, int], dict[int, object]] = {}
    labels: dict[int, str] = {}
    for line in text.split("\n"):
        if not line.strip():
            continue
        tok = line.split()
        key = tok[0]
        if line.startswith(" ") and cur is not None:
            _surface_key(cur, key, tok, line)
            continue
        cur = None
        if key == "SURF":
            cur = Surface(_int(tok[1]))
            if cur.index != len(lens.surfaces):
                raise ZmxError(f"surface {cur.index} out of sequence")
            lens.surfaces.append(cur)
        elif key == "NAME":
            lens.name = line[4:].strip()
        elif key == "NOTE":
            note = line[4:].strip()
            if note[:2] == "0 ":
                lens.notes.append(note[2:].strip())
        elif key == "UNIT":
            if tok[1] != "MM":
                raise ZmxError(f"lens units {tok[1]!r}: only MM is supported")
        elif key == "OBNA":
            lens.object_na = float(tok[1])
        elif key == "ENVD":
            lens.temperature_c, lens.pressure_atm = float(tok[1]), float(tok[2])
        elif key == "GCAT":
            lens.glass_catalogs = tok[1:]
        elif key == "XFLN":
            xfln = _floats(tok[1:])
        elif key == "YFLN":
            yfln = _floats(tok[1:])
        elif key == "FWGN":
            fwgn = _floats(tok[1:])
        elif key == "FCOM":
            fcom[_int(tok[1])] = line.split(None, 2)[2].strip() if len(tok) > 2 else ""
        elif key == "WAVM":
            waves[_int(tok[1])] = float(tok[2])
        elif key == "PWAV":
            lens.primary_wave = _int(tok[1])
        elif key == "MNUM":
            lens.nconf = _int(tok[1])
        elif key == "MOFF":
            c = _int(tok[2])
            q = line.split('"')
            if len(q) > 1 and q[1] and c not in labels:
                labels[c] = q[1]
        elif key in _MCE_OPS:
            s, c = _int(tok[1]), _int(tok[2])
            if key == "GLSS":
                q = line.split('"')
                val: object = q[1] if len(q) > 1 else tok[3]
                p = 0
            else:
                val = float(tok[3])
                p = _int(tok[5]) if key in ("PRAM", "XDAT", "IGNM") else 0
            rows.setdefault((key, s, p), {})[c] = val
    nf = max(len(xfln), len(yfln))
    for i in range(nf):
        lens.fields.append(
            Field(
                x=xfln[i] if i < len(xfln) else 0.0,
                y=yfln[i] if i < len(yfln) else 0.0,
                weight=fwgn[i] if i < len(fwgn) else 1.0,
                comment=fcom.get(i + 1, ""),
            )
        )
    lens.wavelengths = [waves[k] for k in sorted(waves)]
    for (key, s, p), d in rows.items():
        lens.mce.append((key, s, p, [d.get(c) for c in range(1, lens.nconf + 1)]))
    lens.config_labels = [labels.get(c, "") for c in range(1, lens.nconf + 1)]
    return lens


def _surface_key(s: Surface, key: str, tok: list[str], line: str) -> None:
    if key == "COMM":
        s.comment = line.strip()[5:].strip()
    elif key == "TYPE":
        s.type = tok[1]
    elif key == "CURV":
        s.curv = float(tok[1])
        if len(tok) > 4 and tok[2] == "4":
            s.pickups.append(("curv", _int(tok[3]), float(tok[4]), 0.0))
    elif key == "CONI":
        s.conic = float(tok[1])
    elif key == "DISZ":
        s.thick = float(tok[1]) if tok[1] != "INFINITY" else float("inf")
    elif key == "GLAS":
        s.glass = tok[1]
        if len(tok) > 3 and tok[2] == "2":
            s.pickups.append(("glass", _int(tok[3])))
    elif key == "PARM":
        s.parm[_int(tok[1])] = float(tok[2])
    elif key == "XDAT":
        s.xdat[_int(tok[1])] = float(tok[2])
    elif key == "STOP":
        s.stop = True
    elif key == "IGNR":
        s.ignored = len(tok) < 2 or tok[1] != "0"
    elif key == "DIAM":
        s.semi_diameter = float(tok[1])
    elif key == "SQAP":
        s.rect_aperture = (float(tok[1]), float(tok[2]))
    elif key == "PZUP":
        s.pickups.append(("thick", _int(tok[1]), float(tok[2]), float(tok[3])))
    elif key == "PPAR":
        col = _int(tok[5]) if len(tok) > 5 else 0
        s.pickups.append(("parm", _int(tok[1]), _int(tok[2]), float(tok[3]), float(tok[4]), col))

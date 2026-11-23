"""The instrument description, as data (DESIGN.md, "Two stages, one repository").

An :class:`Instrument` has arms (one detector each, with an order range),
channels (a telescope fibre, a pupil slice, or a reference/calibration
fibre) and traces (channel x order on an arm), plus era breaks, both
instrument-wide and per channel. Descriptions are YAML files: the shipped
ones live in ``specfast/instruments/`` and are loaded by name; any other
file can be loaded by path.

Unknown numbers are ``null`` in the YAML (``None`` here), never invented.
Optical-model parameters derived from private design files are calibration
products and never part of this public description.

Order indices are the indices of the extracted product (``0..n-1`` in the
order the extraction writes them), not physical echelle order numbers;
those go in ``Arm.echelle_orders`` when known.
"""

from __future__ import annotations

import bisect
import datetime
from dataclasses import dataclass, field
from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml

from specfast.config import ConfigError, build_dataclass

Role = Literal[
    "science",
    "reference_comb",
    "reference_etalon",
    "reference_thar",
    "sky",
    "calibration",
]

#: Light sources that can feed a reference or calibration channel.
Source = Literal["comb", "etalon", "thar", "flat", "sky"]


@dataclass(frozen=True)
class Detector:
    """Detector geometry and noise. Any unknown value is None."""

    name: str
    #: Extracted pixels along the dispersion direction.
    npix_dispersion: int | None = None
    #: Pixels across the dispersion direction (the light-sensitive area).
    npix_cross_dispersion: int | None = None
    #: Pixel pitch [um].
    pixel_size_um: float | None = None
    #: Raw-frame rows x columns, including overscan, as stored.
    raw_shape: tuple[int, ...] | None = None
    #: Gain [e-/ADU].
    gain_e_per_adu: float | None = None
    #: Read noise [e-] (nominal; the extraction measures it per frame).
    read_noise_e: float | None = None
    #: Saturation / non-linearity limit [ADU].
    saturation_adu: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class Channel:
    """One light path into the spectrograph."""

    name: str
    role: Role
    #: Feeding telescope (science channels), e.g. "T1".
    telescope: str | None = None
    #: Pupil-slice index (G-CLEF), 0-based.
    slice_index: int | None = None
    #: Position of this channel's trace within an order on the slit
    #: (0 = first), when known.
    slit_position: int | None = None
    #: Sources that can feed this channel (reference / calibration channels
    #: whose source is selectable); empty = fixed by ``role``.
    sources: tuple[Source, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class TraceRef:
    """A (channel, order) pair."""

    channel: str
    order: int


@dataclass(frozen=True)
class Arm:
    """One detector and the orders and channels it records."""

    name: str
    detector: Detector
    #: Channel names recorded on this arm.
    channels: tuple[str, ...]
    #: Order indices of the extracted product, in storage order.
    orders: tuple[int, ...] = ()
    #: Orders used for velocities (None = not decided).
    rv_orders: tuple[int, ...] | None = None
    #: Physical echelle order numbers aligned with ``orders`` (None = unknown).
    echelle_orders: tuple[int, ...] | None = None
    #: Approximate vacuum wavelength range [nm] (None = unknown).
    wavelength_range_nm: tuple[float, ...] | None = None
    #: Per order (aligned with ``orders``): the [min, max] wavelength [nm]
    #: recorded on the detector (None = unknown).
    order_wavelength_ranges_nm: tuple[tuple[float, ...], ...] | None = None
    #: Approximate resolving power lambda / delta-lambda (None = unknown).
    resolving_power: float | None = None
    #: [min, max] centre-to-centre spacing of adjacent orders across the
    #: dispersion [pixels] (None = unknown).
    order_spacing_px: tuple[float, ...] | None = None
    #: Distance across the dispersion between adjacent slit positions
    #: (``Channel.slit_position``) [pixels] (None = unknown).
    slit_pitch_px: float | None = None
    #: (channel, order) slots that exist in the product but carry no light.
    absent_traces: tuple[TraceRef, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class Trace:
    """One extracted spectrum: a channel in an order on an arm."""

    arm: str
    channel: str
    order: int


@dataclass(frozen=True)
class Era:
    """An instrument-wide era, starting on ``start`` (inclusive)."""

    name: str
    start: datetime.date
    notes: str = ""


@dataclass(frozen=True)
class ExcludedWindow:
    """Dates (inclusive) whose data are excluded by default."""

    start: datetime.date
    end: datetime.date
    notes: str = ""


@dataclass(frozen=True)
class ChannelBreak:
    """A break affecting only some channels (per-telescope LSF, offsets,
    throughput), on ``date`` (inclusive)."""

    date: datetime.date
    channels: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class Site:
    name: str
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    height_m: float | None = None


@dataclass(frozen=True)
class HeaderKeywords:
    """Raw-header keywords for each normalized field, in order of preference.

    ``{t}`` in a keyword is replaced by the telescope number (1-based) of a
    channel. An empty tuple means the keyword is not known.
    """

    #: Shutter-open time, UTC ISO string.
    date_obs: tuple[str, ...] = ()
    #: Exposure time [s].
    exptime: tuple[str, ...] = ()
    gas_cell_state: tuple[str, ...] = ()
    #: Value of ``gas_cell_state`` meaning "cell in the beam" (case-insensitive).
    gas_cell_in_value: str | None = None
    #: Target RA / Dec [deg, J2000], per telescope.
    target_ra: tuple[str, ...] = ()
    target_dec: tuple[str, ...] = ()
    spectrograph_pressure: tuple[str, ...] = ()
    gas_cell_temperature: tuple[str, ...] = ()
    detector_temperature: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class Instrument:
    name: str
    description: str
    #: "provisional" (filled from known facts, being checked) or
    #: "placeholder" (only public headline facts; most numbers unknown).
    status: Literal["provisional", "placeholder"]
    channels: tuple[Channel, ...]
    arms: tuple[Arm, ...]
    #: Gas cell in the science beam, if any.
    gas_cell: Literal["iodine", "none"] | None = None
    wavelength_range_nm: tuple[float, ...] | None = None
    site: Site | None = None
    header: HeaderKeywords = field(default_factory=HeaderKeywords)
    eras: tuple[Era, ...] = ()
    excluded: tuple[ExcludedWindow, ...] = ()
    channel_breaks: tuple[ChannelBreak, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self._validate()

    # ------------------------------------------------------------------ lookup
    def channel(self, name: str) -> Channel:
        for c in self.channels:
            if c.name == name:
                return c
        raise KeyError(f"{self.name}: no channel {name!r}")

    def arm(self, name: str) -> Arm:
        for a in self.arms:
            if a.name == name:
                return a
        raise KeyError(f"{self.name}: no arm {name!r}")

    def science_channels(self) -> tuple[Channel, ...]:
        return tuple(c for c in self.channels if c.role == "science")

    def traces(self, arm: str) -> tuple[Trace, ...]:
        """Every live trace on an arm, order-major, channels in arm order."""
        a = self.arm(arm)
        absent = set(a.absent_traces)
        return tuple(
            Trace(a.name, ch, o)
            for o in a.orders
            for ch in a.channels
            if TraceRef(ch, o) not in absent
        )

    # ------------------------------------------------------------------ eras
    @cached_property
    def _era_starts(self) -> list[datetime.date]:
        return [e.start for e in self.eras]

    def era_of(self, date: datetime.date) -> Era | None:
        """The instrument-wide era containing ``date`` (None before the first)."""
        i = bisect.bisect_right(self._era_starts, date) - 1
        return self.eras[i] if i >= 0 else None

    def is_excluded(self, date: datetime.date) -> bool:
        return any(w.start <= date <= w.end for w in self.excluded)

    def channel_epoch(self, channel: str, date: datetime.date) -> int:
        """Number of per-channel breaks of ``channel`` on or before ``date``:
        0 before the first. Combine with :meth:`era_of` for per-channel eras."""
        self.channel(channel)
        return sum(1 for b in self.channel_breaks if channel in b.channels and b.date <= date)

    # ------------------------------------------------------------------ checks
    def _validate(self) -> None:
        where = f"instrument {self.name!r}"
        names = [c.name for c in self.channels]
        if len(set(names)) != len(names):
            raise ConfigError(f"{where}: duplicate channel names {names}")
        known = set(names)
        if len({a.name for a in self.arms}) != len(self.arms):
            raise ConfigError(f"{where}: duplicate arm names")
        if not self.arms:
            raise ConfigError(f"{where}: needs at least one arm")
        for a in self.arms:
            bad = set(a.channels) - known
            if bad:
                raise ConfigError(f"{where}: arm {a.name!r} has unknown channels {sorted(bad)}")
            if len(set(a.orders)) != len(a.orders):
                raise ConfigError(f"{where}: arm {a.name!r} repeats an order")
            if not a.orders and self.status != "placeholder":
                raise ConfigError(f"{where}: arm {a.name!r} has no orders")
            if a.rv_orders is not None and not set(a.rv_orders) <= set(a.orders):
                raise ConfigError(f"{where}: arm {a.name!r} rv_orders not in orders")
            if a.echelle_orders is not None and len(a.echelle_orders) != len(a.orders):
                raise ConfigError(f"{where}: arm {a.name!r} echelle_orders/orders length")
            r = a.order_wavelength_ranges_nm
            if r is not None:
                if len(r) != len(a.orders):
                    raise ConfigError(
                        f"{where}: arm {a.name!r} order_wavelength_ranges_nm/orders length"
                    )
                if any(len(x) != 2 or not x[0] < x[1] for x in r):
                    raise ConfigError(
                        f"{where}: arm {a.name!r} order_wavelength_ranges_nm entries "
                        "must be [min, max]"
                    )
            for k in ("wavelength_range_nm", "order_spacing_px"):
                v = getattr(a, k)
                if v is not None and (len(v) != 2 or v[0] > v[1]):
                    raise ConfigError(f"{where}: arm {a.name!r} {k} must be [min, max]")
            for t in a.absent_traces:
                if t.channel not in a.channels or t.order not in a.orders:
                    raise ConfigError(f"{where}: arm {a.name!r} absent trace {t} unknown")
        starts = [e.start for e in self.eras]
        if starts != sorted(starts) or len(set(starts)) != len(starts):
            raise ConfigError(f"{where}: eras must be strictly increasing in start date")
        for w in self.excluded:
            if w.end < w.start:
                raise ConfigError(f"{where}: excluded window ends before it starts: {w}")
        for b in self.channel_breaks:
            bad = set(b.channels) - known
            if bad:
                raise ConfigError(f"{where}: channel break {b.date} names {sorted(bad)}")


def load_instrument(name_or_path: str | Path) -> Instrument:
    """Load a shipped instrument by name (e.g. ``"kiwispec"``) or a YAML path."""
    p = Path(name_or_path)
    if p.suffix in (".yaml", ".yml") or p.exists():
        text = p.read_text()
        where = str(p)
    else:
        res = resources.files("specfast.instruments").joinpath(f"{name_or_path}.yaml")
        if not res.is_file():
            raise FileNotFoundError(
                f"no shipped instrument {name_or_path!r}; see {shipped_instruments()}"
            )
        text = res.read_text()
        where = f"{name_or_path}.yaml"
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: top level must be a mapping")
    return build_dataclass(Instrument, data, where)


def shipped_instruments() -> list[str]:
    """Names of the instrument descriptions shipped with the package."""
    files = resources.files("specfast.instruments").iterdir()
    return sorted(f.name[:-5] for f in files if f.name.endswith(".yaml"))

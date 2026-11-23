"""The instrument description, as data (DESIGN.md, "Two stages, one repository").

An :class:`Instrument` has arms (one detector each, with an order range),
channels (a telescope fibre, a pupil slice, or a reference/calibration
fibre) and traces (channel x order on an arm), plus era breaks, both
instrument-wide and per channel. An instrument with several observing
modes (fibre sets of different core size, resolving power or slicing)
lists them as :class:`Mode`; a run selects one, and only that mode's
channels carry light. Descriptions are YAML files: the shipped
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


FibreShape = Literal["round", "hexagonal", "octagonal", "square", "rectangular"]


@dataclass(frozen=True)
class ModeArm:
    """What one observing mode looks like on one arm (derived from an
    optical design, or None when unknown)."""

    #: Arm name.
    name: str
    #: Resolving power of this mode's fibre on this arm, by the same
    #: definition as ``Arm.resolving_power`` (None = unknown).
    resolving_power: float | None = None
    #: Distance across the dispersion between adjacent slit positions of
    #: this mode [pixels] (None = unknown).
    slit_pitch_px: float | None = None
    #: Offset along the dispersion of this mode's fibre row from the arm's
    #: reference trace, at the same wavelength [pixels] (None = unknown).
    dispersion_offset_px: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class Mode:
    """An observing mode: which channels carry light, and through what
    fibres. Channels are logical (the first science fibre is ``S0`` in
    every mode); the fibres behind them differ from mode to mode."""

    name: str
    #: Channels that carry light in this mode (a subset of the instrument's).
    channels: tuple[str, ...]
    #: Telescope interface feeding this mode (e.g. "natural seeing", "MagAO-X").
    interface: str | None = None
    #: Fibre core diameter (flat to flat for polygons) [um] (None = unknown).
    fibre_core_um: float | None = None
    fibre_shape: FibreShape | None = None
    #: Sky field of each science fibre [arcsec] (None = unknown).
    field_of_view_arcsec: float | None = None
    #: Resolving power as published for the mode (None = unknown). Design
    #: values per arm, by this package's definition, are in ``arms``.
    resolving_power_quoted: float | None = None
    arms: tuple[ModeArm, ...] = ()
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
    #: Observing modes; empty = one implicit mode using every channel.
    modes: tuple[Mode, ...] = ()
    #: Mode used when a run names none (None = a run must name one, if
    #: there are modes).
    default_mode: str | None = None
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

    def mode(self, name: str | None = None) -> Mode | None:
        """The named mode, or the default when ``name`` is None. None for an
        instrument without modes (every channel carries light)."""
        if not self.modes:
            if name is not None:
                raise KeyError(f"{self.name}: has no modes (asked for {name!r})")
            return None
        name = name if name is not None else self.default_mode
        if name is None:
            raise ConfigError(
                f"{self.name}: no default mode; choose one of {[m.name for m in self.modes]}"
            )
        for m in self.modes:
            if m.name == name:
                return m
        raise KeyError(f"{self.name}: no mode {name!r}")

    def traces(self, arm: str, mode: str | None = None) -> tuple[Trace, ...]:
        """Every live trace on an arm, order-major, channels in arm order.
        With modes, only the selected mode's channels (``mode`` None = the
        default mode)."""
        a = self.arm(arm)
        absent = set(a.absent_traces)
        md = self.mode(mode)
        lit = set(md.channels) if md is not None else set(a.channels)
        return tuple(
            Trace(a.name, ch, o)
            for o in a.orders
            for ch in a.channels
            if ch in lit and TraceRef(ch, o) not in absent
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
        mnames = [m.name for m in self.modes]
        if len(set(mnames)) != len(mnames):
            raise ConfigError(f"{where}: duplicate mode names {mnames}")
        if self.default_mode is not None and self.default_mode not in mnames:
            raise ConfigError(f"{where}: default_mode {self.default_mode!r} is not a mode")
        on_arms = {c for a in self.arms for c in a.channels}
        arm_names = {a.name for a in self.arms}
        for m in self.modes:
            if not m.channels:
                raise ConfigError(f"{where}: mode {m.name!r} has no channels")
            bad = set(m.channels) - known
            if bad:
                raise ConfigError(f"{where}: mode {m.name!r} has unknown channels {sorted(bad)}")
            off = set(m.channels) - on_arms
            if off:
                raise ConfigError(f"{where}: mode {m.name!r} channels {sorted(off)} on no arm")
            for ma in m.arms:
                if ma.name not in arm_names:
                    raise ConfigError(f"{where}: mode {m.name!r} names unknown arm {ma.name!r}")
            if len({ma.name for ma in m.arms}) != len(m.arms):
                raise ConfigError(f"{where}: mode {m.name!r} repeats an arm")


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

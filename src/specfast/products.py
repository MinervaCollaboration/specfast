"""``ExtractedSpectrum``: the contract between extraction and Doppler stages.

DESIGN.md, "Two stages, one repository". One exposure, one multi-extension
FITS file. Per arm, arrays over (channel, order, pixel):

- ``flux`` [e-] and ``variance`` [e-^2] (float64);
- ``mask``, a uint32 bitmask (:class:`Mask`); a set bit *describes* the pixel,
  it does not by itself exclude it: the Doppler stage decides what to drop;
- per-trace diagnostics (:class:`TraceDiagnostics`);
- optionally the wavelength [Angstrom, vacuum] with its source.

Plus a normalized header (:class:`NormalizedHeader`) and the provenance
record. The layout is versioned by :data:`FORMAT_VERSION`.

FITS layout (extension names; ``<ARM>`` is the arm name, upper-cased)::

    PRIMARY          no data; SFPRODUC, SFFORMAT, INSTRUME, DATE-OBS, EXPTIME
    HEADER           1-row table, column JSON: the NormalizedHeader
    RAWHEADER        optional 1-row table, column JSON: the source frame's
                     own header cards {keyword: value} (kept verbatim)
    PROVENANCE       1-row table, column JSON: the Provenance record
    FLUX_<ARM>       float64 (channel, order, pixel), header ARM
    VAR_<ARM>        float64
    MASK_<ARM>       uint32
    WAVE_<ARM>       float64, optional; header WAVESRC
    TRACES_<ARM>     table, one row per (channel, order), channel-major:
                     CHANNEL, ORDER and the diagnostics columns
"""

from __future__ import annotations

import enum
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import numpy as np
from astropy.io import fits

from specfast.provenance import Provenance

#: Version of the on-disk layout written by this code.
FORMAT_VERSION = 1
PRODUCT_NAME = "ExtractedSpectrum"


class Mask(enum.IntFlag):
    """Bits of the per-pixel uint32 mask."""

    #: Known detector defect (bad column, hot pixel).
    BAD_PIXEL = 1 << 0
    #: At least one contributing raw pixel at or above the saturation limit.
    SATURATED = 1 << 1
    #: A cosmic ray was rejected in this column (flux from the remaining pixels).
    COSMIC_RAY = 1 << 2
    #: No data: outside the detector, an absent trace or a dummy slot.
    NO_DATA = 1 << 3
    #: The whole trace is dark (below a diagnostic flux level). Extracted
    #: and kept with honest errors: never zeroed, never dropped.
    DARK_TRACE = 1 << 4
    #: Profile fit poor in this column (large chi2).
    PROFILE_OUTLIER = 1 << 5
    #: Scattered-light model unreliable here.
    BACKGROUND_SUSPECT = 1 << 6
    #: No wavelength for this pixel (when a wavelength array is present).
    NO_WAVELENGTH = 1 << 7


@dataclass(frozen=True)
class TraceDiagnostics:
    """Per-trace illumination diagnostics, each shaped (channel, order).

    NaN where not measured.
    """

    #: Cross-dispersion profile width (rms) [px].
    width_px: np.ndarray
    #: Cross-dispersion centroid offset from the reference trace [px].
    centroid_px: np.ndarray
    #: Reduced chi2 of the profile fit.
    profile_chi2: np.ndarray
    #: Scattered-light (halo) flux as a fraction of the trace flux.
    halo_fraction: np.ndarray

    @classmethod
    def empty(cls, shape: tuple[int, int]) -> TraceDiagnostics:
        return cls(**{f.name: np.full(shape, np.nan) for f in fields(cls)})


@dataclass(frozen=True)
class ArmSpectrum:
    """The extracted arrays of one arm."""

    arm: str
    channels: tuple[str, ...]
    orders: tuple[int, ...]
    flux: np.ndarray
    variance: np.ndarray
    mask: np.ndarray
    diagnostics: TraceDiagnostics
    wavelength: np.ndarray | None = None
    #: Where ``wavelength`` came from (e.g. "legacy-pipeline", "iodine-fit",
    #: "lamp+drift"); required when ``wavelength`` is given.
    wavelength_source: str | None = None

    def __post_init__(self) -> None:
        shape = (len(self.channels), len(self.orders))
        if self.flux.ndim != 3 or self.flux.shape[:2] != shape:
            raise ValueError(
                f"arm {self.arm}: flux shape {self.flux.shape}, expected {shape} + (npix,)"
            )
        for name in ("flux", "variance"):
            a = getattr(self, name)
            if a.dtype != np.float64:
                raise ValueError(f"arm {self.arm}: {name} must be float64, got {a.dtype}")
        if self.variance.shape != self.flux.shape:
            raise ValueError(f"arm {self.arm}: variance shape {self.variance.shape}")
        if self.mask.dtype != np.uint32 or self.mask.shape != self.flux.shape:
            raise ValueError(f"arm {self.arm}: mask must be uint32 shaped like flux")
        for f in fields(TraceDiagnostics):
            if getattr(self.diagnostics, f.name).shape != shape:
                raise ValueError(f"arm {self.arm}: diagnostics.{f.name} shape != {shape}")
        if self.wavelength is not None:
            if self.wavelength.shape != self.flux.shape or self.wavelength.dtype != np.float64:
                raise ValueError(f"arm {self.arm}: wavelength must be float64 shaped like flux")
            if not self.wavelength_source:
                raise ValueError(f"arm {self.arm}: wavelength given without wavelength_source")
        elif self.wavelength_source is not None:
            raise ValueError(f"arm {self.arm}: wavelength_source without wavelength")

    @property
    def npix(self) -> int:
        return self.flux.shape[2]

    def index(self, channel: str, order: int) -> tuple[int, int]:
        """Array indices of a (channel, order) trace."""
        return self.channels.index(channel), self.orders.index(order)


@dataclass(frozen=True)
class NormalizedHeader:
    """One schema for every era's raw-header keywords (DESIGN.md, "Data model
    and provenance"). Unknown values are None."""

    instrument: str
    #: Raw frame file name (no directory).
    raw_file: str
    #: Shutter-open time, UTC, ISO 8601.
    date_obs_utc: str
    #: Exposure time [s].
    exptime_s: float
    #: Flux-weighted midpoint, BJD_TDB [d], if known.
    bjd_tdb_mid: float | None = None
    target_name: str | None = None
    #: Target catalogue position [deg, J2000] (barycentric-correction input).
    target_ra_deg: float | None = None
    target_dec_deg: float | None = None
    #: Gas cell in the beam (None = unknown or no cell).
    gas_cell_in: bool | None = None
    #: Environment: name -> value (pressures [mbar], temperatures [C], ...).
    environment: dict[str, float] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> NormalizedHeader:
        return cls(**json.loads(text))


@dataclass(frozen=True)
class ExtractedSpectrum:
    """One extracted exposure (the extraction -> Doppler contract)."""

    header: NormalizedHeader
    arms: tuple[ArmSpectrum, ...]
    provenance: Provenance
    #: The source frame's own header cards {keyword: value}, kept verbatim
    #: (None = not kept). Optional extension RAWHEADER.
    raw_header: dict | None = None

    def arm(self, name: str) -> ArmSpectrum:
        for a in self.arms:
            if a.arm == name:
                return a
        raise KeyError(f"no arm {name!r}")

    # ------------------------------------------------------------------ FITS
    def write(self, path: str | Path, overwrite: bool = False) -> None:
        """Write the multi-extension FITS file."""
        hdr = self.header
        prim = fits.PrimaryHDU()
        prim.header["SFPRODUC"] = (PRODUCT_NAME, "specfast product type")
        prim.header["SFFORMAT"] = (FORMAT_VERSION, "specfast product format version")
        prim.header["INSTRUME"] = hdr.instrument
        prim.header["DATE-OBS"] = (hdr.date_obs_utc, "shutter open, UTC")
        prim.header["EXPTIME"] = (hdr.exptime_s, "[s]")
        prim.header["SFVERSN"] = (self.provenance.package_version, "specfast version")
        hdus = [
            prim,
            _json_hdu("HEADER", hdr.to_json()),
            _json_hdu("PROVENANCE", self.provenance.to_json()),
        ]
        if self.raw_header is not None:
            hdus.append(_json_hdu("RAWHEADER", json.dumps(self.raw_header, sort_keys=True)))
        for a in self.arms:
            tag = a.arm.upper()
            for ext, data in (("FLUX", a.flux), ("VAR", a.variance), ("MASK", a.mask)):
                h = fits.ImageHDU(data=data, name=f"{ext}_{tag}")
                h.header["ARM"] = a.arm
                hdus.append(h)
            if a.wavelength is not None:
                h = fits.ImageHDU(data=a.wavelength, name=f"WAVE_{tag}")
                h.header["ARM"] = a.arm
                h.header["WAVESRC"] = a.wavelength_source
                h.header["BUNIT"] = "Angstrom (vacuum)"
                hdus.append(h)
            hdus.append(_traces_hdu(a))
        fits.HDUList(hdus).writeto(path, overwrite=overwrite)

    @classmethod
    def read(cls, path: str | Path) -> ExtractedSpectrum:
        """Read a file written by :meth:`write` (any supported format version)."""
        with fits.open(path) as hl:
            prim = hl[0].header
            if prim.get("SFPRODUC") != PRODUCT_NAME:
                raise ValueError(f"{path}: not a specfast {PRODUCT_NAME}")
            version = prim.get("SFFORMAT")
            if version != FORMAT_VERSION:
                raise ValueError(
                    f"{path}: format version {version}, this code reads {FORMAT_VERSION}"
                )
            header = NormalizedHeader.from_json(_read_json(hl["HEADER"]))
            prov = Provenance.from_json(_read_json(hl["PROVENANCE"]))
            raw = json.loads(_read_json(hl["RAWHEADER"])) if "RAWHEADER" in hl else None
            arms = []
            for h in hl:
                if not h.name.startswith("TRACES_"):
                    continue
                tag = h.name[len("TRACES_") :]
                arms.append(_read_arm(hl, tag, h))
        return cls(header=header, arms=tuple(arms), provenance=prov, raw_header=raw)


def _json_hdu(name: str, text: str) -> fits.BinTableHDU:
    col = fits.Column(name="JSON", format=f"{max(len(text), 1)}A", array=np.array([text]))
    return fits.BinTableHDU.from_columns([col], name=name)


def _read_json(hdu: fits.BinTableHDU) -> str:
    return str(hdu.data["JSON"][0])


_DIAG_COLUMNS = [f.name for f in fields(TraceDiagnostics)]


def _traces_hdu(a: ArmSpectrum) -> fits.BinTableHDU:
    nc, no = len(a.channels), len(a.orders)
    chan = np.repeat(np.array(a.channels), no)
    order = np.tile(np.array(a.orders, dtype=np.int64), nc)
    width = max(len(c) for c in a.channels)
    cols = [
        fits.Column(name="CHANNEL", format=f"{width}A", array=chan),
        fits.Column(name="ORDER", format="K", array=order),
    ]
    for name in _DIAG_COLUMNS:
        cols.append(
            fits.Column(
                name=name.upper(), format="D", array=getattr(a.diagnostics, name).reshape(-1)
            )
        )
    h = fits.BinTableHDU.from_columns(cols, name=f"TRACES_{a.arm.upper()}")
    h.header["ARM"] = a.arm
    return h


def _read_arm(hl: fits.HDUList, tag: str, traces: fits.BinTableHDU) -> ArmSpectrum:
    arm = traces.header["ARM"]
    chan = [str(c) for c in traces.data["CHANNEL"]]
    order = [int(o) for o in traces.data["ORDER"]]
    channels = tuple(dict.fromkeys(chan))
    orders = tuple(dict.fromkeys(order))
    shape = (len(channels), len(orders))
    diag = TraceDiagnostics(
        **{
            n: np.asarray(traces.data[n.upper()], dtype=np.float64).reshape(shape)
            for n in _DIAG_COLUMNS
        }
    )
    wave, src = None, None
    if f"WAVE_{tag}" in hl:
        wave = np.asarray(hl[f"WAVE_{tag}"].data, dtype=np.float64)
        src = hl[f"WAVE_{tag}"].header["WAVESRC"]
    return ArmSpectrum(
        arm=arm,
        channels=channels,
        orders=orders,
        flux=np.asarray(hl[f"FLUX_{tag}"].data, dtype=np.float64),
        variance=np.asarray(hl[f"VAR_{tag}"].data, dtype=np.float64),
        mask=np.asarray(hl[f"MASK_{tag}"].data, dtype=np.uint32),
        diagnostics=diag,
        wavelength=wave,
        wavelength_source=src,
    )

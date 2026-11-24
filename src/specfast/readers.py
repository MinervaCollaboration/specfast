"""Readers that convert other pipelines' extractions to :class:`ExtractedSpectrum`.

DESIGN.md, "Two stages, one repository": the Doppler stage can run on
another pipeline's extraction once it is converted to the product. Readers
do the conversion in memory (nothing is written unless the caller writes
the product).

``read_proc``: the KiwiSpec ``.proc.fits`` layout written by the legacy
reduction (pipeline v1.0.0) and by the extract2 pilot (``*.x2.proc.fits``):

    HDU0  flux [ADU], (channel, order, pixel)  + the raw frame's header
    HDU1  inverse variance [ADU^-2]
    HDU2  wavelength [Angstrom, vacuum] (the legacy pipeline's solution)
    HDU3  mask (extract2: 1 = good, 0 = bad; legacy: all ones)

and optionally an extract2 diagnostics file (``*.x2.diag.fits``, table
``TRACES`` with per-trace width, centroid, profile chi2, background and a
``dark`` flag). Flux and variance are converted to electrons with the
detector gain (the frame's ``X2GAIN`` if present, else the instrument's).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np
from astropy.io import fits

from specfast.instrument import Instrument
from specfast.products import (
    ArmSpectrum,
    ExtractedSpectrum,
    Mask,
    NormalizedHeader,
    TraceDiagnostics,
)
from specfast.provenance import Provenance

__all__ = ["read_proc", "header_value", "parse_angle"]

#: Raw-header keywords copied into ``NormalizedHeader.environment`` when
#: numeric (per-channel ones carry the 1-based channel number).
_ENV_KEYS = (
    "SPECPRES",
    "CCD-TEMP",
    "I2TEMPA",
    "TEMPA1",
    "TEMPB1",
    "TEMPC1",
    "TEMPD1",
    "TEMPE02",
    "OUTTEMP",
    "DEWPOINT",
    "PRESSURE",
)
_ENV_KEYS_PER_CHANNEL = ("AIRMASS", "HOURANG", "ALT", "DEFOCUS")


def header_value(header, keys, default=None):
    """First present, non-empty, non-UNKNOWN value of ``keys``."""
    for k in keys:
        v = header.get(k)
        if v is None:
            continue
        if isinstance(v, str) and v.strip().upper() in ("", "UNKNOWN", "NONE"):
            continue
        return v
    return default


def parse_angle(value, hours: bool) -> float | None:
    """Degrees from a number (degrees) or a sexagesimal string (hours for RA)."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        pass
    parts = s.replace(":", " ").split()
    if len(parts) != 3:
        return None
    sign = -1.0 if parts[0].startswith("-") else 1.0
    a, b, c = abs(float(parts[0])), float(parts[1]), float(parts[2])
    deg = sign * (a + b / 60.0 + c / 3600.0)
    return deg * 15.0 if hours else deg


def _float(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _normalized_header(hdr, instrument: Instrument, raw_file: str, nchan: int) -> NormalizedHeader:
    hk = instrument.header
    date_obs = str(header_value(hdr, hk.date_obs or ("DATE-OBS",), "")).strip()
    exptime = _float(header_value(hdr, hk.exptime or ("EXPTIME",), 0.0)) or 0.0
    gas = header_value(hdr, hk.gas_cell_state)
    gas_in = None
    if gas is not None and hk.gas_cell_in_value is not None:
        gas_in = str(gas).strip().lower() == hk.gas_cell_in_value.lower()
    ra = dec = None
    target = None
    for t in range(1, nchan + 1):
        r = parse_angle(header_value(hdr, [k.format(t=t) for k in hk.target_ra]), hours=True)
        d = parse_angle(header_value(hdr, [k.format(t=t) for k in hk.target_dec]), hours=False)
        if r is not None and d is not None:
            ra, dec = r, d
            # legacy headers give RA in hours when sexagesimal; decimal RA is
            # in degrees only if > 24 cannot be told apart: keep sexagesimal
            break
    for t in range(1, nchan + 1):
        o = header_value(hdr, (f"OBJECT{t}", "OBJECT"))
        if o is not None:
            target = str(o).strip()
            break
    env: dict[str, float] = {}
    for k in _ENV_KEYS:
        f = _float(hdr.get(k))
        if f is not None:
            env[k] = f
    for k in _ENV_KEYS_PER_CHANNEL:
        for t in range(1, nchan + 1):
            f = _float(hdr.get(f"{k}{t}"))
            if f is not None:
                env[f"{k}{t}"] = f
    return NormalizedHeader(
        instrument=instrument.name,
        raw_file=raw_file,
        date_obs_utc=date_obs,
        exptime_s=exptime,
        target_name=target,
        target_ra_deg=ra,
        target_dec_deg=dec,
        gas_cell_in=gas_in,
        environment=env,
    )


def _raw_header_dict(hdr) -> dict:
    out = {}
    for card in hdr.cards:
        k = card.keyword
        if not k or k in ("COMMENT", "HISTORY", "SIMPLE", "BITPIX", "EXTEND") or k.startswith(
            "NAXIS"
        ):
            continue
        v = card.value
        if isinstance(v, bool | int | float | str):
            out[k] = v
    return out


def _diagnostics(diag_path, nchan: int, norder: int):
    """(TraceDiagnostics, dark (channel, order) bool) from an extract2 diag file."""
    diag = TraceDiagnostics.empty((nchan, norder))
    dark = np.zeros((nchan, norder), bool)
    if diag_path is None or not Path(diag_path).exists():
        return diag, dark, False
    with fits.open(diag_path) as h:
        t = h["TRACES"].data
        tel = np.asarray(t["tel"], int)
        o = np.asarray(t["ordi"], int)
        ok = (tel >= 0) & (tel < nchan) & (o >= 0) & (o < norder)
        arrs = {n: np.array(getattr(diag, n)) for n in ("width_px", "centroid_px")}
        arrs["profile_chi2"] = np.array(diag.profile_chi2)
        arrs["halo_fraction"] = np.array(diag.halo_fraction)
        flux = np.asarray(t["flux_med"], float)
        with np.errstate(divide="ignore", invalid="ignore"):
            halo = np.asarray(t["bg_med"], float) / flux
        cols = {
            "width_px": np.asarray(t["width"], float),
            "centroid_px": np.asarray(t["dcen0"], float),
            "profile_chi2": np.asarray(t["chi2r"], float),
            "halo_fraction": halo,
        }
        for n, v in cols.items():
            arrs[n][tel[ok], o[ok]] = v[ok]
        dark[tel[ok], o[ok]] = np.asarray(t["dark"], bool)[ok]
    return TraceDiagnostics(**arrs), dark, True


def read_proc(
    path: str | Path,
    instrument: Instrument,
    diag_path: str | Path | None = None,
    arm: str | None = None,
    gain: float | None = None,
) -> ExtractedSpectrum:
    """Read a KiwiSpec ``.proc.fits`` (legacy or extract2) as an
    :class:`ExtractedSpectrum`, keeping the raw header (``raw_header``).

    Pixels with zero inverse variance, or a zero mask value where the mask
    is not all ones, get ``Mask.BAD_PIXEL`` (and infinite variance); traces
    the diagnostics flag as dark get ``Mask.DARK_TRACE``.
    """
    path = Path(path)
    a = instrument.arm(arm) if arm else instrument.arms[0]
    with fits.open(path) as h:
        hdr = h[0].header
        flux = np.asarray(h[0].data, dtype=np.float64)
        ivar = np.asarray(h[1].data, dtype=np.float64)
        wave = np.asarray(h[2].data, dtype=np.float64) if len(h) > 2 else None
        msrc = np.asarray(h[3].data, dtype=np.float64) if len(h) > 3 else None
        raw = _raw_header_dict(hdr)
    nchan, norder, npix = flux.shape
    if nchan != len(a.channels):
        raise ValueError(f"{path.name}: {nchan} channels, instrument arm has {len(a.channels)}")
    g = gain or _float(hdr.get("X2GAIN")) or a.detector.gain_e_per_adu
    if g is None:
        raise ValueError(f"{path.name}: no gain (frame or instrument)")
    good = np.isfinite(flux) & np.isfinite(ivar) & (ivar > 0)
    if msrc is not None and not np.all(msrc == 1):
        good &= msrc > 0
    mask = np.where(good, 0, int(Mask.BAD_PIXEL)).astype(np.uint32)
    with np.errstate(divide="ignore"):
        var = np.where(good, (g * g) / np.where(good, ivar, 1.0), np.inf)
    flux_e = np.where(np.isfinite(flux), flux * g, 0.0)
    diag, dark, have_diag = _diagnostics(diag_path, nchan, norder)
    mask[dark] |= np.uint32(Mask.DARK_TRACE)
    orders = tuple(range(norder)) if len(a.orders) != norder else tuple(a.orders)
    src = None
    if wave is not None:
        src = str(hdr.get("X2WAVE") or "legacy-pipeline").strip() or "legacy-pipeline"
        bad = ~np.isfinite(wave) | (wave <= 0)
        mask[bad] |= np.uint32(Mask.NO_WAVELENGTH)
        wave = np.where(bad, 0.0, wave)
    arm_spec = ArmSpectrum(
        arm=a.name,
        channels=tuple(a.channels),
        orders=orders,
        flux=flux_e,
        variance=var,
        mask=mask,
        diagnostics=diag,
        wavelength=wave,
        wavelength_source=src,
    )
    header = _normalized_header(hdr, instrument, path.name, nchan)
    inputs = {"proc": path}
    if have_diag:
        inputs["diag"] = Path(diag_path)
    prov = Provenance.create("read_proc", inputs=inputs)
    return ExtractedSpectrum(header=header, arms=(arm_spec,), provenance=prov, raw_header=raw)


def date_of(spec: ExtractedSpectrum) -> datetime.date:
    """UTC date of shutter open."""
    return datetime.date.fromisoformat(spec.header.date_obs_utc[:10])

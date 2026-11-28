"""LCO NRES: BANZAI-NRES products -> specfast.

NRES (``instruments/nres.yaml``) is specfast's third instrument: four
identical fibre-fed echelles on the Las Cumbres Observatory (LCO) network,
each with two telescope fibres (0 and 2) and a simultaneous ThAr fibre (1)
between them. LCO's current pipeline, BANZAI-NRES (McCully et al. 2022,
SPIE 12189, arXiv:2212.11381; https://github.com/LCOGT/banzai-nres), writes
for each science exposure an ``e92-1d`` file: a 1-row-per-trace table
(``SPECTRUM``: id, order, fiber, wavelength, flux, uncertainty, blaze, mask,
4096 columns each) and the per-order CCF. Master calibrations are stacked
2-D images: the lamp flat (``TRACES``, ``PROFILE``, ``BLAZE``...) and the
ThAr arc "DOUBLE" (``SPECTRUM``, ``ERR``, ``BPM``, ``WAVELENGTH``,
``FEATURES``, ``FIBERS``).

What this module provides
-------------------------
- :func:`read_banzai_1d`: one ``e92-1d`` file -> :class:`~specfast.products.
  ExtractedSpectrum` (arm ``main``, channels ``fibre0``, ``fibre1``,
  ``fibre2``; order index i is echelle order ``ORDERS[i] = 52 + i``) plus a
  :class:`BanzaiAudit` with the pipeline's own RV, barycentric correction,
  template and calibration bookkeeping (audit only). The extracted pixel
  index is the detector column, so wavelength models in pixel space apply
  directly. A wavelength array may be passed to replace BANZAI's.
- :func:`extract_master_arc`: optimal extraction of a master arc with the
  lamp flat's profile (BANZAI's own weights, Horne 1986), for line
  measurement in exactly the same 1-D column space as the science traces.
- :func:`parse_basename`, :data:`UNITS`: filename bookkeeping.

What it does not do: re-extract raw frames (``e00``); the IDL-era ``e91``
products are not read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.io import fits

from specfast.products import (
    ArmSpectrum,
    ExtractedSpectrum,
    Mask,
    NormalizedHeader,
    TraceDiagnostics,
)
from specfast.provenance import Provenance

__all__ = [
    "CHANNELS",
    "NPIX",
    "ORDERS",
    "UNITS",
    "BanzaiAudit",
    "MasterArc",
    "extract_master_arc",
    "parse_basename",
    "read_banzai_1d",
]

#: BANZAI fibre number -> specfast channel name.
CHANNELS = {0: "fibre0", 1: "fibre1", 2: "fibre2"}
#: Extracted pixels per trace (detector columns).
NPIX = 4096
#: Physical echelle orders that BANZAI-NRES can write (52..119); the
#: product stores every one of them (order index i <-> m = ORDERS[i] = 52 + i),
#: NO_DATA where a trace is missing.
ORDERS = tuple(range(52, 120))
#: Site code -> spectrograph unit (filename prefix ``{site}nrs{NN}``).
UNITS = {"lsc": "nres01", "elp": "nres02", "cpt": "nres03", "tlv": "nres04"}
PSI_TO_MBAR = 68.947572932

_BASENAME = re.compile(
    r"(?P<site>[a-z]{3})nrs(?P<unit>\d\d)-(?P<camera>f[a-z]\d\d)-(?P<day>\d{8})-"
    r"(?P<frame>\d{4}|double|lampflat)"
)


def parse_basename(name: str) -> dict:
    """``lscnrs01-fa09-20220614-0041-e92-1d.fits.fz`` -> site, unit, camera,
    day (YYYYMMDD), frame (number or calibration type)."""
    m = _BASENAME.search(Path(name).name)
    if m is None:
        raise ValueError(f"not an NRES basename: {name!r}")
    d = m.groupdict()
    d["unit"] = "nres" + d["unit"]
    return d


@dataclass(frozen=True)
class BanzaiAudit:
    """BANZAI-NRES values that must not enter specfast's measurement.

    ``rv``/``rv_err`` [m/s] are BANZAI's barycentric-corrected CCF velocity;
    ``barycorr`` [m/s] its barycentric correction (astropy, geometric
    mid-exposure); ``bjd_tdb`` its time stamp (TCORR).
    """

    rv: float | None
    rv_err: float | None
    barycorr: float | None
    bjd_tdb: float | None
    snr: float | None
    template_teff: float | None
    template_logg: float | None
    science_fibre: int | None
    objects: str | None
    arc: str | None
    flat: str | None
    pipeline_version: str | None
    site: str | None
    unit: str | None


def _num(h, key):
    v = h.get(key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _audit(prim: fits.Header, path: Path) -> BanzaiAudit:
    sf = prim.get("SCIFIBER")
    try:
        info = parse_basename(path.name)
    except ValueError:
        info = {"site": prim.get("SITEID"), "unit": prim.get("TELESCOP")}
    return BanzaiAudit(
        rv=_num(prim, "RV"),
        rv_err=_num(prim, "RVERR"),
        barycorr=_num(prim, "BARYCORR"),
        bjd_tdb=_num(prim, "TCORR"),
        snr=_num(prim, "SNR"),
        template_teff=_num(prim, "TEFF"),
        template_logg=_num(prim, "LOGG"),
        science_fibre=int(sf) if sf is not None and str(sf).strip() != "" else None,
        objects=prim.get("OBJECTS"),
        arc=prim.get("L1IDARC"),
        flat=prim.get("L1IDFLAT"),
        pipeline_version=prim.get("PIPEVER"),
        site=info.get("site"),
        unit=info.get("unit"),
    )


def _header(path: Path, prim: fits.Header) -> NormalizedHeader:
    env = {}
    for key, name, scale in (
        ("NRESPRES", "spectrograph_pressure", PSI_TO_MBAR),
        ("NRESTEMP", "spectrograph_temperature", 1.0),
        ("IGLATEMP", "enclosure_temperature", 1.0),
    ):
        v = _num(prim, key)
        if v is not None and abs(v) < 1e4:
            env[name] = v * scale
    objs = str(prim.get("OBJECTS", "")).split("&")
    sf = prim.get("SCIFIBER")
    target = prim.get("OBJECT")
    if sf in (0, 2) and len(objs) == 3:
        target = objs[int(sf)]

    def deg(key, unit):
        v = prim.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            from astropy.coordinates import Angle

            try:
                return float(Angle(str(v), unit=unit).deg)
            except Exception:
                return None

    return NormalizedHeader(
        instrument="nres",
        raw_file=str(prim.get("ORIGNAME") or path.name),
        date_obs_utc=str(prim.get("DATE-OBS")),
        exptime_s=float(prim.get("EXPTIME", np.nan)),
        bjd_tdb_mid=None,
        target_name=target,
        target_ra_deg=deg("RA", "hourangle"),
        target_dec_deg=deg("DEC", "deg"),
        gas_cell_in=None,
        environment=env,
    )


def read_banzai_1d(
    path: str | Path,
    wavelength: np.ndarray | None = None,
    wavelength_source: str | None = None,
    hash_input: bool = False,
) -> tuple[ExtractedSpectrum, BanzaiAudit]:
    """Convert one BANZAI-NRES ``e92-1d`` file.

    Flux and variance are BANZAI's optimally extracted electrons (not blaze
    corrected); the blaze from the lamp flat is not part of the contract
    and is returned separately by :func:`read_banzai_blaze`. ``wavelength``:
    optional replacement array shaped (3, len(ORDERS), NPIX) [A, vacuum],
    with ``wavelength_source`` naming it; default BANZAI's (the master
    arc's 2-D solution, median across each trace).
    """
    path = Path(path)
    with fits.open(path, memmap=False) as hl:
        prim = hl[0].header
        t = hl["SPECTRUM"].data
        fib = np.asarray(t["fiber"]).astype(int)
        order = np.asarray(t["order"]).astype(int)
        flux_t = np.asarray(t["flux"], dtype=np.float64)
        unc_t = np.asarray(t["uncertainty"], dtype=np.float64)
        wave_t = np.asarray(t["wavelength"], dtype=np.float64)
        mask_t = np.asarray(t["mask"])
        audit = _audit(prim, path)
        header = _header(path, prim)
    shape = (len(CHANNELS), len(ORDERS), NPIX)
    flux = np.zeros(shape)
    var = np.full(shape, np.inf)
    wave = np.full(shape, np.nan)
    mask = np.full(shape, np.uint32(Mask.NO_DATA), dtype=np.uint32)
    oidx = {m: i for i, m in enumerate(ORDERS)}
    for k in range(len(fib)):
        if fib[k] not in CHANNELS or order[k] not in oidx:
            continue
        c, j = fib[k], oidx[order[k]]
        f, u, w = flux_t[k], unc_t[k], wave_t[k]
        bad = (mask_t[k] != 0) | ~np.isfinite(f) | ~np.isfinite(u) | (u <= 0)
        flux[c, j] = np.where(bad, 0.0, f)
        var[c, j] = np.where(bad, np.inf, u**2)
        m = np.where(bad, np.uint32(Mask.NO_DATA), np.uint32(0)).astype(np.uint32)
        nowave = ~np.isfinite(w) | (w <= 0)
        m[nowave] |= np.uint32(Mask.NO_WAVELENGTH)
        mask[c, j] = m
        wave[c, j] = np.where(nowave, np.nan, w)
    source = f"banzai-nres {audit.pipeline_version}: master arc {audit.arc} (no drift correction)"
    if wavelength is not None:
        wavelength = np.asarray(wavelength, dtype=np.float64)
        if wavelength.shape != shape:
            raise ValueError(f"wavelength shape {wavelength.shape}, expected {shape}")
        if not wavelength_source:
            raise ValueError("a replacement wavelength needs wavelength_source")
        wave = wavelength.copy()
        nowave = ~np.isfinite(wave) | (wave <= 0)
        mask = np.where(
            nowave, mask | np.uint32(Mask.NO_WAVELENGTH), mask & ~np.uint32(Mask.NO_WAVELENGTH)
        )
        mask = mask.astype(np.uint32)
        wave[nowave] = np.nan
        source = wavelength_source
    arm = ArmSpectrum(
        arm="main",
        channels=tuple(CHANNELS.values()),
        orders=tuple(range(len(ORDERS))),
        flux=flux,
        variance=var,
        mask=mask,
        diagnostics=TraceDiagnostics.empty((len(CHANNELS), len(ORDERS))),
        wavelength=wave,
        wavelength_source=source,
    )
    prov = Provenance.create("convert-nres", inputs={"banzai_1d": path} if hash_input else None)
    return ExtractedSpectrum(header=header, arms=(arm,), provenance=prov), audit


def read_banzai_blaze(path: str | Path) -> np.ndarray:
    """The lamp-flat blaze per (channel, order, pixel) of an ``e92-1d``
    file (NaN where missing)."""
    out = np.full((len(CHANNELS), len(ORDERS), NPIX), np.nan)
    oidx = {m: i for i, m in enumerate(ORDERS)}
    with fits.open(path, memmap=False) as hl:
        t = hl["SPECTRUM"].data
        for f, o, b in zip(t["fiber"], t["order"], t["blaze"], strict=True):
            if int(f) in CHANNELS and int(o) in oidx:
                out[int(f), oidx[int(o)]] = b
    return out


@dataclass(frozen=True)
class MasterArc:
    """An optimally extracted master arc, one row per trace."""

    fibre: np.ndarray  #: (n,) BANZAI fibre number
    order: np.ndarray  #: (n,) physical echelle order
    flux: np.ndarray  #: (n, NPIX)
    variance: np.ndarray  #: (n, NPIX), inf where unusable
    wavelength: np.ndarray  #: (n, NPIX) BANZAI's solution, median across the trace
    mjd: float
    lit_fibres: tuple[int, ...]


def extract_master_arc(arc_path, flat_path, trace_table) -> MasterArc:
    """Extract a BANZAI master arc with a master lamp flat's traces and profile.

    ``trace_table``: (trace_id, order, fibre) rows that label the flat's
    ``TRACES`` image, e.g. the ``SPECTRUM`` table's ``id``/``order``/
    ``fiber`` columns of a science ``e92-1d`` reduced with that flat. The
    weights are BANZAI's (Horne 1986 eq. 8 with the flat's profile and the
    arc's own variance), so arc and science traces live in the same 1-D
    column space.
    """
    with fits.open(flat_path, memmap=False) as fl:
        traces = np.asarray(fl["TRACES"].data)
        profile = np.asarray(fl["PROFILE"].data, dtype=np.float64)
    with fits.open(arc_path, memmap=False) as hl:
        data = np.asarray(hl["SPECTRUM"].data, dtype=np.float64)
        err = np.asarray(hl["ERR"].data, dtype=np.float64)
        bpm = np.asarray(hl["BPM"].data)
        wimg = np.asarray(hl["WAVELENGTH"].data, dtype=np.float64)
        hdr = hl["SPECTRUM"].header
        objs = str(hdr.get("OBJECTS", "")).split("&")
        mjd = float(hdr.get("MJD-OBS", np.nan))
    lit = tuple(i for i, o in enumerate(objs) if o.strip().lower() == "thar")
    ids = np.asarray([r[0] for r in trace_table], dtype=int)
    orders = np.asarray([r[1] for r in trace_table], dtype=int)
    fibres = np.asarray([r[2] for r in trace_table], dtype=int)
    sel = traces > 0
    tid = traces[sel].astype(np.int64)
    ys, xs = np.nonzero(sel)
    var = err[sel] ** 2
    good = (bpm[sel] == 0) & np.isfinite(var) & (var > 0) & np.isfinite(data[sel])
    p = profile[sel]
    d = data[sel]
    wv = wimg[sel]
    w_num = np.where(good, p / np.where(good, var, 1.0), 0.0)
    nmax = int(tid.max()) + 1
    key = tid * NPIX + xs
    num = np.bincount(key, w_num * d, minlength=nmax * NPIX).reshape(nmax, NPIX)
    den = np.bincount(key, w_num * p, minlength=nmax * NPIX).reshape(nmax, NPIX)
    # wavelength: profile-weighted mean of the 2-D solution across the trace
    pw = np.bincount(key, p * np.where(np.isfinite(wv), wv, 0), minlength=nmax * NPIX)
    ps = np.bincount(key, p * np.isfinite(wv), minlength=nmax * NPIX)
    wave = np.where(ps > 0, pw / np.where(ps > 0, ps, 1), np.nan).reshape(nmax, NPIX)
    with np.errstate(invalid="ignore", divide="ignore"):
        flux = np.where(den > 0, num / den, 0.0)
        variance = np.where(den > 0, 1.0 / den, np.inf)
    keep = (ids > 0) & (ids < nmax)
    return MasterArc(
        fibre=fibres[keep],
        order=orders[keep],
        flux=flux[ids[keep]],
        variance=variance[ids[keep]],
        wavelength=np.where(wave[ids[keep]] > 0, wave[ids[keep]], np.nan),
        mjd=mjd,
        lit_fibres=lit,
    )

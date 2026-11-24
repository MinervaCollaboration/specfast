"""NEID L1 (or L2) file -> :class:`~specfast.products.ExtractedSpectrum`.

NEID (``instruments/neid.yaml``) is specfast's second test bed: a stabilised
spectrograph calibrated by a laser comb, ThAr and a simultaneous etalon or
comb, with no gas cell. Its public Data Reduction Pipeline (DRP) products
are documented at https://neid.ipac.caltech.edu/.

What is converted
-----------------
One arm (``main``), channels ``SCI``, ``SKY`` and ``CAL`` (the L1 extensions
``SCIFLUX``/``SCIVAR``/``SCIWAVE`` and so on), 122 orders (index ``i``,
echelle order ``m = 173 - i``) of 9216 pixels.

- **Flux and variance**: as the DRP wrote them (float64). They are electrons
  from a flat-relative optimal extraction multiplied by a smooth lamp SED,
  not raw electrons; the variance matches the flux. Non-finite flux or a
  non-positive / non-finite variance becomes flux 0, variance ``inf`` and
  :attr:`Mask.NO_DATA`: never a silently usable zero.
- **Wavelength**: the DRP's vacuum wavelengths (``SCIWAVE``...), which the
  DRP builds from a comb+ThAr master solution moved by the drift it
  measured in the simultaneous reference. ``wavelength_source`` records the
  algorithm, drift model, master files and DRP version from the header.
  Pixels with wavelength 0 (orders the DRP leaves uncalibrated) become NaN
  with :attr:`Mask.NO_WAVELENGTH`.
- **Header**: shutter-open UTC, exposure time, target, queue position, and
  the environment (spectrograph pressure converted from Torr to mbar, CCD
  temperature in C). ``bjd_tdb_mid`` is the DRP's flux-weighted midpoint of
  the CCF-weighted orders (``CCFJDMOD``) where present (L2), else the
  per-order ``SSBJD`` of the order nearest 550 nm.

What is kept apart (:class:`NeidAudit`)
---------------------------------------
specfast releases raw redshifts (DESIGN.md, "Raw redshifts"): no
barycentric term enters ``z_meas``. NEID's per-order barycentric
corrections (``SSBZnnn``, weighted by its chromatic exposure meter), its
BJDs, its wavelength-drift terms and, in L2 files, its CCF velocities are
therefore returned separately, for comparison and audit only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.coordinates import Angle
from astropy.io import fits

from specfast.conventions import C_MPS
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
    "N_ORDERS",
    "NeidAudit",
    "echelle_order",
    "read_neid",
]

#: Logical channel -> L1 extension prefix.
CHANNELS = {"SCI": "SCI", "SKY": "SKY", "CAL": "CAL"}
#: Orders in the L1 product; echelle order m = M_FIRST - index.
N_ORDERS = 122
M_FIRST = 173
TORR_TO_MBAR = 1.333223684


def echelle_order(index):
    """Echelle order number ``m`` of L1 order index ``index``."""
    return M_FIRST - np.asarray(index)


@dataclass(frozen=True)
class NeidAudit:
    """NEID DRP values that must not enter specfast's raw redshift.

    Arrays are per L1 order index (122 entries); NaN where the header has no
    value. Velocities in m/s.
    """

    echelle_orders: np.ndarray
    #: Barycentric correction z_B per order (SSBZnnn), barycorrpy convention.
    z_bary: np.ndarray
    #: BJD_TDB of the flux-weighted midpoint per order (SSBJDnnn).
    bjd_tdb: np.ndarray
    #: DRP wavelength-drift terms DRIFTRV0..2, as written in the header.
    drift_terms: tuple[float, ...]
    #: Zero-point drift of SCIWAVE from the master solution (ZPTDRIFT), as written.
    wave_zero_point_drift: float | None
    obs_mode: str | None
    sci_object: str | None
    cal_object: str | None
    sky_object: str | None
    drp_version: str | None
    data_level: int | None
    #: L2 only (None for L1): barycentric-corrected CCF velocity per order
    #: (CCFRVnnn; 0 in the header means "not measured" and becomes NaN) and
    #: its order weight (CCFWTnnn).
    ccf_rv: np.ndarray | None = None
    ccf_weight: np.ndarray | None = None
    #: L2 only: CCF velocity of the weighted orders (CCFRVMOD), its error
    #: (DVRMSMOD) and BJD (CCFJDMOD); the unweighted sum (CCFRVSUM).
    ccf_rv_mod: float | None = None
    ccf_rv_mod_err: float | None = None
    ccf_bjd_mod: float | None = None
    ccf_rv_sum: float | None = None
    #: L2 only: the DRP telluric model's water vapour [mm] and zenith angle [deg].
    pwv_mm: float | None = None
    telluric_zenith_deg: float | None = None

    def barycentric_velocity(self, z_meas: np.ndarray) -> np.ndarray:
        """Audit only: c[(1 + z_meas)(1 + z_B) - 1] per order [m/s], NEID's
        correction applied to specfast's measured redshifts."""
        return C_MPS * ((1.0 + np.asarray(z_meas)) * (1.0 + self.z_bary) - 1.0)


def _get(h: fits.Header, key: str, default=None):
    v = h.get(key, default)
    if isinstance(v, str):
        v = v.strip()
        if v == "":
            return default
    return v


def _float(h: fits.Header, key: str) -> float | None:
    v = _get(h, key)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _per_order(h: fits.Header, prefix: str, zero_is_missing: bool = False) -> np.ndarray:
    out = np.full(N_ORDERS, np.nan)
    for i in range(N_ORDERS):
        v = _float(h, f"{prefix}{int(echelle_order(i)):03d}")
        if v is None or (zero_is_missing and v == 0.0):
            continue
        out[i] = v
    return out


def _sexagesimal(value, unit: str) -> float | None:
    """Degrees from a queue RA (hours) or Dec (degrees) string; None if absent."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "0", "-999999"):
        return None
    try:
        return float(Angle(s, unit=unit).deg)
    except (ValueError, TypeError):
        return None


def _wavelength_source(prim: fits.Header, wave_hdr: fits.Header) -> str:
    parts = [
        f"NEID DRP {_get(prim, 'E_VER', '?')} L1 SCIWAVE/SKYWAVE/CALWAVE",
        f"WAVECAL={_get(wave_hdr, 'WAVECAL', _get(prim, 'WAVECAL', '?'))}",
        f"DRIFTFUN={_get(prim, 'DRIFTFUN', '?')}",
        f"MDSPFILE={_get(prim, 'MDSPFILE', '?')}",
        f"DRIFTREF={_get(prim, 'DRIFTREF', '?')}",
    ]
    return "; ".join(parts)


def _audit(hl: fits.HDUList) -> NeidAudit:
    prim = hl[0].header
    wave_hdr = hl["SCIWAVE"].header
    ccf = hl["CCFS"].header if "CCFS" in hl else None
    tel = hl["TELLURIC"].header if "TELLURIC" in hl else None
    drift = tuple(
        float(v) for k in ("DRIFTRV0", "DRIFTRV1", "DRIFTRV2") if (v := _float(prim, k)) is not None
    )
    kw = {}
    if ccf is not None:
        kw = dict(
            ccf_rv=1e3 * _per_order(ccf, "CCFRV", zero_is_missing=True),
            ccf_weight=_per_order(ccf, "CCFWT"),
            ccf_rv_mod=_scale(_float(ccf, "CCFRVMOD"), 1e3),
            ccf_rv_mod_err=_scale(_float(ccf, "DVRMSMOD"), 1e3),
            ccf_bjd_mod=_float(ccf, "CCFJDMOD"),
            ccf_rv_sum=_scale(_float(ccf, "CCFRVSUM"), 1e3),
        )
    if tel is not None:
        kw.update(pwv_mm=_float(tel, "WVAPOR"), telluric_zenith_deg=_float(tel, "ZENITH"))
    level = _get(prim, "DATALVL")
    return NeidAudit(
        echelle_orders=echelle_order(np.arange(N_ORDERS)),
        z_bary=_per_order(prim, "SSBZ"),
        bjd_tdb=_per_order(prim, "SSBJD"),
        drift_terms=drift,
        wave_zero_point_drift=_float(wave_hdr, "ZPTDRIFT"),
        obs_mode=_get(prim, "OBS-MODE"),
        sci_object=_get(prim, "SCI-OBJ"),
        cal_object=_get(prim, "CAL-OBJ"),
        sky_object=_get(prim, "SKY-OBJ"),
        drp_version=_get(prim, "E_VER"),
        data_level=None if level is None else int(level),
        **kw,
    )


def _scale(v: float | None, s: float) -> float | None:
    return None if v is None else v * s


def _header(path: Path, prim: fits.Header, audit: NeidAudit) -> NormalizedHeader:
    if audit.ccf_bjd_mod is not None:
        bjd = audit.ccf_bjd_mod
    else:
        bjd = None
        ok = np.isfinite(audit.bjd_tdb)
        if ok.any():
            # order nearest 550 nm: m * lambda ~ 6130 A * 100 -> m ~ 111
            idx = np.where(ok)[0]
            bjd = float(audit.bjd_tdb[idx[np.argmin(np.abs(audit.echelle_orders[idx] - 111))]])
    env = {}
    p = _float(prim, "PMKSTOP")
    if p is not None:
        env["spectrograph_pressure"] = p * TORR_TO_MBAR
    t = _float(prim, "CCDTEMP")
    if t is not None:
        env["detector_temperature"] = t
    return NormalizedHeader(
        instrument="neid",
        raw_file=str(_get(prim, "FILENAME", path.name)),
        date_obs_utc=str(_get(prim, "DATE-OBS")),
        exptime_s=float(_get(prim, "EXPTIME")),
        bjd_tdb_mid=bjd,
        target_name=_get(prim, "OBJECT"),
        target_ra_deg=_sexagesimal(_get(prim, "QRA"), "hourangle"),
        target_dec_deg=_sexagesimal(_get(prim, "QDEC"), "deg"),
        gas_cell_in=None,
        environment=env,
    )


def read_neid(
    path: str | Path,
    channels: tuple[str, ...] = ("SCI", "SKY", "CAL"),
    hash_input: bool = True,
) -> tuple[ExtractedSpectrum, NeidAudit]:
    """Convert one NEID L1 (or L2) file.

    ``channels``: which of SCI, SKY, CAL to convert. ``hash_input``: record
    the input file's sha256 in the provenance (reads the whole file).
    Returns the :class:`ExtractedSpectrum` and the audit-only
    :class:`NeidAudit`.
    """
    path = Path(path)
    unknown = set(channels) - set(CHANNELS)
    if unknown or not channels:
        raise ValueError(f"channels must be a non-empty subset of {tuple(CHANNELS)}")
    with fits.open(path, memmap=False) as hl:
        prim = hl[0].header
        if str(_get(prim, "INSTRUME", "")).upper() != "NEID":
            raise ValueError(f"{path}: INSTRUME is not NEID")
        flux, var, wave = [], [], []
        for ch in channels:
            ext = CHANNELS[ch]
            # Some public files (e.g. solar 2021-09-15, DRP v1.5.3) have no
            # wavelength (empty *WAVE, blank WAVECAL) or no data for a fibre.
            for kind in ("FLUX", "VAR", "WAVE"):
                if hl[f"{ext}{kind}"].data is None:
                    raise ValueError(
                        f"{path}: {ext}{kind} is empty (WAVECAL="
                        f"{_get(prim, 'WAVECAL', '')!r}); the DRP did not produce it"
                    )
            f = np.asarray(hl[f"{ext}FLUX"].data, dtype=np.float64)
            v = np.asarray(hl[f"{ext}VAR"].data, dtype=np.float64)
            w = np.asarray(hl[f"{ext}WAVE"].data, dtype=np.float64)
            if f.shape[0] != N_ORDERS or f.shape != v.shape or f.shape != w.shape:
                raise ValueError(
                    f"{path}: {ext} arrays have shapes {f.shape}, {v.shape}, {w.shape}"
                )
            flux.append(f)
            var.append(v)
            wave.append(w)
        flux = np.stack(flux)
        var = np.stack(var)
        wave = np.stack(wave)
        audit = _audit(hl)
        source = _wavelength_source(prim, hl["SCIWAVE"].header)
        header = _header(path, prim, audit)
    mask = np.zeros(flux.shape, dtype=np.uint32)
    bad = ~np.isfinite(flux) | ~np.isfinite(var) | (var <= 0)
    mask[bad] |= np.uint32(Mask.NO_DATA)
    flux = np.where(bad, 0.0, flux)
    var = np.where(bad, np.inf, var)
    nowave = ~np.isfinite(wave) | (wave <= 0)
    mask[nowave] |= np.uint32(Mask.NO_WAVELENGTH)
    wave = np.where(nowave, np.nan, wave)
    arm = ArmSpectrum(
        arm="main",
        channels=tuple(channels),
        orders=tuple(range(N_ORDERS)),
        flux=flux,
        variance=var,
        mask=mask,
        diagnostics=TraceDiagnostics.empty((len(channels), N_ORDERS)),
        wavelength=wave,
        wavelength_source=source,
    )
    prov = Provenance.create("convert-neid", inputs={"neid": path} if hash_input else None)
    return ExtractedSpectrum(header=header, arms=(arm,), provenance=prov), audit

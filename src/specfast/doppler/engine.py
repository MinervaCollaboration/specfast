"""The Doppler engine for real extracted spectra (``specfast-doppler``).

One fit block per (exposure, channel, order), with the forward model
assembled from the run configuration (:mod:`specfast.doppler.runconfig`):

- wavelength: optics curve + D(p) + per-block polynomial
  (:class:`~specfast.doppler.library.OpticsWavelength`), or a polynomial
  started from the product's stored wavelengths;
- LSF: the per-era Gauss-Hermite map varying along the order plus the
  per-(exposure, channel) illumination kernel under a hierarchical
  (channel, era) prior (:class:`~specfast.doppler.library.GaussHermiteLSF`),
  or a frozen Gaussian;
- iodine: atlas plus an optional learned observed-frame correction;
- tellurics: per-exposure water column times the cleaned atlas, or a mask;
- star: the tabulated template (``fixed``) or the template module in
  ``modify`` / ``infer`` mode with per-(template, order) zero points;
- detector frame: optional serial CTI and detector map.

Solver: alternating sweeps, each

1. every block fitted with its own parameters free (velocity, wavelength,
   iodine strength, continuum; :func:`~specfast.doppler.fastfit.
   fit_block_fast`), shared parameters held;
2. shared parameters (water per exposure; illumination kernel per exposure
   and channel) take one Gauss-Newton step on the Schur-reduced normal
   equations summed over their blocks (block parameters profiled out),
   with the hierarchical prior updated from the population;
3. block velocities combined into one per (exposure, channel) plus
   per-order offsets (template zero points), with an optional smooth
   per-order function of the barycentric velocity;
4. template (and learned observatory corrections) solved with the block
   velocities set to the combined ones (``modify`` / ``infer``).

Work is split by order across worker processes that keep their blocks in
memory; the master exchanges only velocities, shared parameters and
reduced normal equations. Convergence is logged per sweep.

Outputs (``output`` directory): ``blocks.fits`` (one row per block: raw
redshift ``cz``, velocity and errors, segment velocities with covariance,
shape-term projection with covariance, nuisances, corrections),
``exposures.fits`` (per exposure and channel), ``templates.npz``,
``convergence.json``, ``log.tsv`` (every skipped frame or trace and why),
``state.pkl`` (warm start), ``provenance.json``.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import multiprocessing as mp
import pickle
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from specfast.config import TemplateConfig
from specfast.conventions import C_KMS, C_MPS, measured_redshift
from specfast.converters.kiwispec_proc import read_proc
from specfast.doppler import calib as CB
from specfast.doppler.components import ExposureContext
from specfast.doppler.fastfit import fit_block_fast, project_block, schur_terms
from specfast.doppler.grid import LnGrid, convolve
from specfast.doppler.library import (
    DetectorMap,
    GaussHermiteLSF,
    GaussianLSF,
    GriddedTemplate,
    IodineCell,
    OpticsWavelength,
    PolynomialContinuum,
    SerialCTI,
    StarTemplate,
    Telluric,
)
from specfast.doppler.model import ForwardModel
from specfast.doppler.runconfig import DopplerRunConfig, TargetConfig
from specfast.doppler.template import (
    Block,
    TemplateSolver,
    combine_velocities,
    pooled_observatory_step,
    prior_on_grid,
    template_grid,
)
from specfast.instrument import Instrument, load_instrument
from specfast.products import Mask
from specfast.provenance import Provenance

__all__ = ["FrameInfo", "list_frames", "provisional_z_bary", "run"]

#: Normalization of the polynomial basis of the optics curves (KiwiSpec
#: optical-model tables: (p - 1023.5) / 1024); overridden by the file.
LOCAL_FREE = (("star", "v"), ("wavelength", "coeffs"), ("iodine", "k"), ("continuum", "coeffs"))


# ------------------------------------------------------------------ frames
@dataclass
class FrameInfo:
    name: str
    path: str
    diag: str | None
    date: datetime.date
    mjd_start: float
    exptime: float
    mjd_mid: float
    z_bary: float = 0.0
    airmass: tuple = (1.0, 1.0, 1.0, 1.0)
    #: Index of the frame's target (``targets_of(cfg)``).
    target: int = 0


def targets_of(cfg: DopplerRunConfig) -> list[TargetConfig]:
    """The run's targets: ``cfg.targets``, or the single star of a one-star
    run built from ``star``, ``inputs`` and ``calibrations.template``."""
    if cfg.targets:
        return list(cfg.targets)
    return [
        TargetConfig(
            star=cfg.star,
            name_contains=cfg.inputs.name_contains or "",
            template=cfg.calibrations.template,
            mode=cfg.model.star.mode,
            frame_list=cfg.inputs.frame_list,
        )
    ]


def _frame_names(cfg: DopplerRunConfig, log: list, target: TargetConfig):
    inp = cfg.inputs
    contains = target.name_contains
    out = []
    if inp.manifest is not None:
        m = inp.manifest
        seen = {}
        for line in Path(m.path).read_text().splitlines():
            f = line.split("\t")
            if len(f) <= max(m.name_column, m.status_column, m.path_column):
                continue
            name = f[m.name_column].strip()
            if contains and contains not in name:
                continue
            seen[name] = (f[m.status_column].strip(), f[m.path_column].strip())
        for name, (status, rel) in seen.items():
            if status != m.ok_status:
                log.append((name, "", "", "manifest_status", status))
                continue
            p = Path(m.root) / rel
            if not p.exists():
                log.append((name, "", "", "missing_file", str(rel)))
                continue
            out.append((name, str(p)))
    else:
        for p in sorted(Path(inp.directory).rglob("*" + inp.suffix)):
            name = p.name[: -len(inp.suffix)]
            if contains and contains not in name:
                continue
            out.append((name, str(p)))
    if target.frame_list:
        keep = {ln.strip() for ln in Path(target.frame_list).read_text().splitlines() if ln.strip()}
        out = [x for x in out if CB.stem(x[0]) in keep]
    return sorted(out, key=lambda x: x[0])


def provisional_z_bary(mjd_utc: np.ndarray, star, site) -> np.ndarray:
    """Provisional barycentric correction (code convention: ``z_bary`` with
    ``1 + z_meas = (1 + v / c) / (1 + z_bary)``) from catalogue astrometry,
    for placing exposures in the star frame only."""
    import astropy.units as u
    from astropy.coordinates import EarthLocation, SkyCoord
    from astropy.time import Time

    loc = EarthLocation.from_geodetic(
        site.longitude_deg * u.deg, site.latitude_deg * u.deg, site.height_m * u.m
    )
    t = Time(np.atleast_1d(mjd_utc), format="mjd", scale="utc")
    dist = (1000.0 / star.parallax_mas) * u.pc if star.parallax_mas > 0 else 1e5 * u.pc
    c = SkyCoord(
        ra=star.ra_deg * u.deg,
        dec=star.dec_deg * u.deg,
        pm_ra_cosdec=star.pmra_masyr * u.mas / u.yr,
        pm_dec=star.pmdec_masyr * u.mas / u.yr,
        distance=dist,
        radial_velocity=star.rv_kms * u.km / u.s,
        obstime=Time(star.epoch_jyear, format="jyear", scale="tdb"),
    )
    c2 = c.apply_space_motion(new_obstime=t)
    pos = SkyCoord(ra=c2.ra, dec=c2.dec)
    vcorr = pos.radial_velocity_correction(kind="barycentric", obstime=t, location=loc)
    vc = np.asarray(vcorr.to(u.m / u.s).value, dtype=np.float64)
    # astropy: v_bary = v_meas + v_corr (to first order; exactly
    # 1 + v_bary / c = (1 + z_meas)(1 + v_corr / c)), so z_bary = v_corr / c
    return vc / C_MPS


def list_frames(cfg: DopplerRunConfig, instrument: Instrument, log: list) -> list[FrameInfo]:
    """Frames of the run: manifest / directory, name filter, dates,
    instrument-wide exclusions, gas cell in; with the provisional
    barycentric correction at the geometric mid-exposure."""
    from astropy.io import fits
    from astropy.time import Time

    from specfast.converters.kiwispec_proc import header_value

    targets = targets_of(cfg)
    names, owner, seen = [], [], set()
    for ti, tg in enumerate(targets):
        for name, path in _frame_names(cfg, log, tg):
            if name in seen:
                log.append((name, "", "", "second_target", tg.star.name))
                continue
            seen.add(name)
            names.append((name, path))
            owner.append(ti)
    inp = cfg.inputs
    frames = []
    d0 = datetime.date.fromisoformat(inp.first_date) if inp.first_date else None
    d1 = datetime.date.fromisoformat(inp.last_date) if inp.last_date else None
    hk = instrument.header
    for (name, path), ti in zip(names, owner, strict=True):
        try:
            h = fits.getheader(path)
        except Exception as exc:  # noqa: BLE001 (logged, never silent)
            log.append((name, "", "", "unreadable", repr(exc)))
            continue
        dobs = str(header_value(h, hk.date_obs or ("DATE-OBS",), "")).strip()
        try:
            t0 = Time(dobs, format="isot", scale="utc")
        except ValueError:
            log.append((name, "", "", "bad_date", dobs))
            continue
        date = datetime.date.fromisoformat(dobs[:10])
        if (d0 and date < d0) or (d1 and date > d1):
            continue
        if instrument.is_excluded(date):
            log.append((name, "", "", "excluded_window", str(date)))
            continue
        gas = header_value(h, hk.gas_cell_state)
        if hk.gas_cell_in_value and str(gas).strip().lower() != hk.gas_cell_in_value.lower():
            log.append((name, "", "", "gas_cell_out", str(gas)))
            continue
        try:
            exptime = float(header_value(h, hk.exptime or ("EXPTIME",), 0.0))
        except (TypeError, ValueError):
            exptime = 0.0
        am = []
        for t in range(1, 5):
            try:
                am.append(float(h.get(f"AIRMASS{t}", 1.0)))
            except (TypeError, ValueError):
                am.append(1.0)
        diag = None
        if inp.diag_suffix:
            dp = path[: -len(inp.suffix)] + inp.diag_suffix if path.endswith(inp.suffix) else None
            diag = dp if dp and Path(dp).exists() else None
        frames.append(
            FrameInfo(
                name=CB.stem(name),
                path=path,
                diag=diag,
                date=date,
                mjd_start=float(t0.mjd),
                exptime=exptime,
                mjd_mid=float(t0.mjd) + 0.5 * exptime / 86400.0,
                airmass=tuple(am),
                target=ti,
            )
        )
    if inp.limit:
        # at most ``limit`` frames per target
        keep, n = [], {}
        for f in frames:
            n[f.target] = n.get(f.target, 0) + 1
            if n[f.target] <= inp.limit:
                keep.append(f)
        frames = keep
    for ti, tg in enumerate(targets):
        fs = [f for f in frames if f.target == ti]
        if fs:
            zb = provisional_z_bary(np.array([f.mjd_mid for f in fs]), tg.star, instrument.site)
            for f, z in zip(fs, zb, strict=True):
                f.z_bary = float(z)
    return frames


# ------------------------------------------------------------ calibrations
@dataclass
class Calibrations:
    iodine: CB.Atlas | None
    telluric: CB.Atlas | None
    template: tuple
    lsf_map: CB.LsfMap | None
    lsf_sigma: CB.LsfSigma | None
    lsf_basis: CB.LsfBasis | None
    optics: CB.OpticsCurves | None
    distortion: CB.Distortion | None
    static: CB.StaticPositions | None = None
    #: Per target: (ln lambda, flux) of its template, or None (featureless).
    templates: tuple = ()

    @staticmethod
    def _template(path):
        tz = np.load(path)
        w = np.asarray(tz["wave_vac"], float)
        o = np.argsort(w)
        return np.log(w[o]), np.asarray(tz["flux"], float)[o]

    @classmethod
    def load(cls, cfg: DopplerRunConfig) -> Calibrations:
        c = cfg.calibrations
        temps = tuple(cls._template(t.template) if t.template else None for t in targets_of(cfg))
        return cls(
            templates=temps,
            iodine=CB.load_atlas(c.iodine_atlas) if c.iodine_atlas else None,
            telluric=CB.load_atlas(c.telluric_atlas) if c.telluric_atlas else None,
            template=temps[0] if temps[0] is not None else cls._template(c.template),
            lsf_map=CB.LsfMap(c.lsf_map) if c.lsf_map else None,
            lsf_sigma=CB.LsfSigma(c.lsf_sigma) if c.lsf_sigma else None,
            lsf_basis=CB.LsfBasis(c.lsf_basis) if c.lsf_basis else None,
            optics=CB.OpticsCurves(c.optics) if c.optics else None,
            distortion=CB.Distortion(c.distortion) if c.distortion else None,
            static=CB.StaticPositions(c.wavelength_static) if c.wavelength_static else None,
        )


def _cut(lnlam, values, lo, hi, fill):
    i0 = max(int(np.searchsorted(lnlam, lo)) - 2, 0)
    i1 = min(int(np.searchsorted(lnlam, hi)) + 2, lnlam.size)
    if i1 - i0 < 4:
        return np.array([lo, hi]), np.array([fill, fill])
    return lnlam[i0:i1], values[i0:i1]


# ------------------------------------------------------------------ worker
class OrderWorker:
    """Owns the blocks of some orders (one process)."""

    def __init__(self, cfg, instrument, frames, orders, log):
        self.cfg = cfg
        self.ins = instrument
        self.arm = instrument.arms[0]
        self.channels = tuple(cfg.model.channels or self.arm.channels)
        self.frames = frames
        self.orders = list(orders)
        self.log = log
        self.cal = Calibrations.load(cfg)
        self.blocks: dict = {}  # order -> list of Block
        self.meta: dict = {}  # order -> list of dict (frame, channel, ...)
        self.params: dict = {}  # order -> list of params (fixed mode)
        self.solvers: dict = {}  # (order, target) -> TemplateSolver
        self.sol_index: dict = {}  # (order, target) -> indices into blocks[order]
        self.ntargets = len(targets_of(cfg))
        self.order_static: dict = {}

    def group(self, o, t):
        """Zero-point group of (order, target): the order for one star."""
        return o if self.ntargets == 1 else 100 * o + t

    # ---------------------------------------------------------------- build
    def _initial_wavelength(self, fr, ch, order, wave_row, npix):
        """(base coeffs, base centre, base scale, D, start lambda(p))."""
        m = self.cfg.model.wavelength
        D = self.cal.distortion.get(fr.mjd_mid) if (m.distortion and self.cal.distortion) else None
        if m.static_table:
            if self.cal.static is None:
                raise ValueError("wavelength.static_table needs calibrations.wavelength_static")
            S = self.cal.static.get(fr.mjd_mid, ch, order)
            if S is None:
                self.log.append((fr.name, ch, order, "no_static_table_row", "S = 0"))
            else:
                D = S.copy() if D is None else D + S
        cols = np.arange(npix, dtype=float)
        pd = cols if D is None else cols + np.interp(cols, np.arange(D.size), D)
        if m.base == "optics":
            if self.cal.optics is None:
                raise ValueError("wavelength.base = optics needs calibrations.optics")
            row = self.cal.optics.get(fr.mjd_mid, ch, order)
            if row is None:
                return None
            coeffs, xc, xs = row
            lam = np.polynomial.polynomial.polyval((pd - xc) / xs, coeffs)
            return coeffs, xc, xs, D, lam
        if wave_row is None or not np.all(wave_row > 0):
            return None
        return None, 0.0, 1.0, D, np.asarray(wave_row, float)

    def build(self):
        cfg = self.cfg
        mcfg = cfg.model
        npix = self.arm.detector.npix_dispersion or 2048
        buff = mcfg.buffer_angstrom
        rows = {o: [] for o in self.orders}
        for fr in self.frames:
            try:
                spec = read_proc(fr.path, self.ins, fr.diag)
            except Exception as exc:  # noqa: BLE001
                self.log.append((fr.name, "", "", "read_error", repr(exc)))
                continue
            a = spec.arms[0]
            for o in self.orders:
                io = a.orders.index(o)
                for ch in self.channels:
                    cidx = a.channels.index(ch)
                    if self.ins.is_excluded(fr.date, ch) or _extra_excluded(cfg, fr.date, ch):
                        self.log.append((fr.name, ch, o, "channel_excluded", ""))
                        continue
                    mask = a.mask[cidx, io]
                    if np.any(mask & Mask.DARK_TRACE):
                        self.log.append((fr.name, ch, o, "dark_trace", ""))
                        continue
                    wave_row = a.wavelength[cidx, io] if a.wavelength is not None else None
                    init = self._initial_wavelength(fr, ch, o, wave_row, npix)
                    if init is None:
                        self.log.append((fr.name, ch, o, "no_wavelength_start", ""))
                        continue
                    flux = a.flux[cidx, io]
                    var = a.variance[cidx, io]
                    ok = (mask & (Mask.BAD_PIXEL | Mask.SATURATED | Mask.NO_DATA)) == 0
                    sig = np.where(ok & np.isfinite(var) & (var > 0), np.sqrt(var), np.inf)
                    if np.sum(np.isfinite(sig)) < 200 or np.nanmedian(flux[ok]) <= 0:
                        self.log.append((fr.name, ch, o, "no_signal", ""))
                        continue
                    rows[o].append(
                        dict(
                            fr=fr, ch=ch, ci=self.channels.index(ch), flux=flux, sig=sig, init=init
                        )
                    )
        for o in self.orders:
            self._build_order(o, rows[o], npix, buff)

    def _build_order(self, o, rows, npix, buff):
        cfg = self.cfg
        mcfg = cfg.model
        if not rows:
            self.blocks[o], self.meta[o], self.params[o] = [], [], []
            return
        lam_lo = min(r["init"][4][0] for r in rows)
        lam_hi = max(r["init"][4][-1] for r in rows)
        pix_kms = float(
            np.median(
                [C_KMS * np.median(np.diff(r["init"][4])) / r["init"][4][npix // 2] for r in rows]
            )
        )
        search_kms = mcfg.wavelength.search_px * pix_kms
        grid = LnGrid.covering(lam_lo, lam_hi, mcfg.grid_step_kms, margin_kms=search_kms + 60.0)
        if mcfg.grid_phase:
            # grid-phase check: the same grid shifted by a fraction of a step
            grid = dataclasses.replace(grid, ln_start=grid.ln_start + mcfg.grid_phase * grid.step)
        lo, hi = grid.lnlam[0], grid.lnlam[-1]
        # star factor per target; observed-frame factors shared by the order
        targets = targets_of(cfg)
        stars, tgrids, priors = [], [], []
        for ti, tg in enumerate(targets):
            vmax = abs(tg.star.rv_kms) + 40.0
            if tg.mode == "fixed":
                tl, tf = self.cal.templates[ti]
                tln, tfl = _cut(tl, tf, lo - (vmax + 20) / C_KMS, hi + (vmax + 20) / C_KMS, 1.0)
                stars.append(StarTemplate(lnlam=tln, flux=tfl, name="star"))
                tgrids.append(None)
                priors.append(None)
                continue
            tgrid = template_grid(np.exp(lo), np.exp(hi), pix_kms, mcfg.star.oversample, vmax, 20.0)
            stars.append(GriddedTemplate(grid=tgrid, name="star"))
            tgrids.append(tgrid)
            if tg.mode == "modify":
                tl, tf = self.cal.templates[ti]
                priors.append(prior_on_grid(tl, tf, tgrid))
            else:
                priors.append(np.ones(tgrid.n))
        learn = any(tg.mode != "fixed" for tg in targets)
        factors = []
        if self.cal.iodine is not None:
            iln, itr = _cut(self.cal.iodine.lnlam, self.cal.iodine.transmission, lo, hi, 1.0)
            corr = None
            if mcfg.iodine.learned_correction and learn:
                corr = LnGrid.covering(np.exp(lo), np.exp(hi), mcfg.iodine.node_kms, 0.0)
            factors.append(
                IodineCell.from_transmission(
                    iln, itr, name="iodine", correction=corr, scaling=mcfg.iodine.scaling
                )
            )
        tel_mask_fn = None
        if self.cal.telluric is not None and mcfg.telluric.model != "none":
            tln_, ttr = _cut(self.cal.telluric.lnlam, self.cal.telluric.transmission, lo, hi, 1.0)
            if mcfg.telluric.model == "modelled":
                clean = np.where(ttr > mcfg.telluric.clean_threshold, 1.0, ttr)
                tau_w = -np.log(np.clip(clean, 1e-4, None))
                tau_d = np.zeros_like(tau_w)
                if self.cal.telluric.transmission_dry is not None:
                    _, tdry = _cut(
                        self.cal.telluric.lnlam, self.cal.telluric.transmission_dry, lo, hi, 1.0
                    )
                    tau_d = -np.log(
                        np.clip(
                            np.where(tdry > mcfg.telluric.clean_threshold, 1.0, tdry), 1e-4, None
                        )
                    )
                factors.append(
                    Telluric(lnlam=tln_, tau_dry=tau_d, tau_water=tau_w, name="telluric")
                )
            else:
                thr = mcfg.telluric.mask_threshold

                def tel_mask_fn(lam, tln_=tln_, ttr=ttr, thr=thr):
                    return np.interp(np.log(lam), tln_, ttr) < thr

        cti = None
        if mcfg.cti.enabled:
            cti = SerialCTI(
                amplifier_column=mcfg.cti.amplifier_column,
                transfer_offset=mcfg.cti.transfer_offset,
                name="cti",
            )
        down = float(mcfg.telluric.downweight.get(o, mcfg.telluric.downweight.get(str(o), 1.0)))
        iod = factors[0] if factors and factors[0].name == "iodine" else None
        blocks, meta, params = [], [], []
        for r in rows:
            fr, ch = r["fr"], r["ch"]
            coeffs, bxc, bxs, D, lam = r["init"]
            win = np.where((lam >= lam[0] + buff) & (lam <= lam[-1] - buff))[0]
            if win.size < 200:
                continue
            p0, p1 = int(win[0]), int(win[-1])
            pixels = np.arange(p0, p1 + 1, dtype=float)
            half = 0.5 * (p1 - p0)
            xc = p0 + half
            wave = OpticsWavelength(
                degree=mcfg.wavelength.degree,
                x_center=xc,
                x_scale=half,
                base=coeffs if coeffs is not None else None,
                base_center=bxc,
                base_scale=bxs,
                distortion=D,
            )
            # perturbation start reproducing the start lambda (pipeline:
            # the full polynomial; optics: zero)
            if coeffs is None:
                t = wave.scaled(pixels)
                a0 = np.polynomial.polynomial.polyfit(t, lam[p0 : p1 + 1], mcfg.wavelength.degree)
            else:
                a0 = np.zeros(mcfg.wavelength.degree + 1)
            cont = PolynomialContinuum(
                degree=mcfg.continuum_degree, x_center=xc, x_scale=half, name="continuum"
            )
            pixel_mps = C_MPS * float(np.median(np.diff(lam[p0 : p1 + 1]) / lam[p0:p1]))
            lsf, lsfp = self._lsf(fr, ch, o, grid, p0, p1, pixel_mps)
            if lsf is None:
                self.log.append((fr.name, ch, o, "no_lsf_calibration", ""))
                continue
            det, detp = None, None
            if mcfg.detector_map:
                det = DetectorMap(npix=pixels.size, name="detector")
                detp = self._detector_map(ch, o, p0, p1)
            model = ForwardModel(
                wavelength=wave,
                continuum=cont,
                lsf=lsf,
                factors=(stars[fr.target], *factors),
                grid=grid,
                pixels=pixels,
                cti=cti,
                detector=det,
                sampling=mcfg.sampling,
            )
            data = r["flux"][p0 : p1 + 1].astype(float)
            sig = r["sig"][p0 : p1 + 1].astype(float) * down
            if tel_mask_fn is not None:
                sig = np.where(tel_mask_fn(lam[p0 : p1 + 1]), np.inf, sig)
            p = {
                "wavelength": {"coeffs": a0},
                "continuum": {
                    "coeffs": np.r_[
                        np.nanpercentile(data[np.isfinite(sig)], 90),
                        np.zeros(mcfg.continuum_degree),
                    ]
                },
                "lsf": lsfp,
                "star": {"v": np.array([targets[fr.target].star.rv_kms * 1e3])},
            }
            if iod is not None:
                p["iodine"] = {"k": np.array([1.0])}
                if iod.correction is not None:
                    p["iodine"]["dtau"] = np.zeros(iod.correction.n)
            if any(f.name == "telluric" for f in factors):
                p["telluric"] = {"water": np.array([1.0])}
            if cti is not None:
                cp = SerialCTI.kiwispec_default()
                if mcfg.cti.trap is not None:
                    cp["trap"] = np.array(mcfg.cti.trap, float)
                if mcfg.cti.signal_scale is not None:
                    cp["signal_scale"] = np.array([mcfg.cti.signal_scale])
                p["cti"] = cp
            if det is not None:
                p["detector"] = detp
            ctx = ExposureContext(
                z_bary=fr.z_bary, airmass=float(fr.airmass[self.ins.arms[0].channels.index(ch)])
            )
            key = (fr.name, ch)
            b = Block(
                key=key, order=o, model=model, data=data, sigma=sig, ctx=ctx, start=p, channel=ch
            )
            blocks.append(b)
            meta.append(
                dict(
                    frame=fr.name,
                    ch=ch,
                    order=o,
                    mjd=fr.mjd_mid,
                    z_bary=fr.z_bary,
                    p0=p0,
                    p1=p1,
                    era_lsf=(self.cal.lsf_map.era(fr.mjd_mid) if self.cal.lsf_map else 0),
                    target=fr.target,
                    group=self.group(o, fr.target),
                    flat=targets[fr.target].mode == "flat",
                )
            )
            params.append(p)
        self.blocks[o], self.meta[o] = blocks, meta
        self.params[o] = [
            {c: {k: np.array(v, float) for k, v in d.items()} for c, d in p.items()} for p in params
        ]
        for ti, tg in enumerate(targets):
            idx = [i for i, m in enumerate(meta) if m["target"] == ti]
            if tg.mode == "fixed" or not idx:
                continue
            tc = TemplateConfig(
                mode="modify" if tg.mode == "flat" else tg.mode,
                oversample=mcfg.star.oversample,
                prior_sigma=mcfg.star.prior_sigma,
                smooth_sigma=mcfg.star.smooth_sigma,
                fit_zero_points=mcfg.star.fit_zero_points,
                learn_observatory=mcfg.iodine.learned_correction and mcfg.iodine.learn,
                observatory_prior_sigma=mcfg.iodine.prior_sigma,
                observatory_smooth_sigma=mcfg.iodine.smooth_sigma,
                observatory_gauge=mcfg.iodine.gauge,
                observatory_gauge_kms=mcfg.iodine.gauge_kms,
            )
            sol = TemplateSolver(
                [blocks[i] for i in idx], {o: priors[ti]}, tc, star="star", cache_operators=False
            )
            if mcfg.iodine.correction_file and iod is not None and iod.correction is not None:
                self._load_correction(o, sol, iod.correction)
            self.solvers[(o, ti)] = sol
            self.sol_index[(o, ti)] = idx
            for j, i in enumerate(idx):
                self.params[o][i] = sol.params[j]

    def _load_correction(self, o, sol, grid):
        """Start the learned iodine correction of order ``o`` from an earlier
        run's ``templates.npz`` (interpolated in ln wavelength onto this grid;
        zero outside the source range)."""
        path = self.cfg.model.iodine.correction_file
        with np.load(path) as z:
            kv, kg = f"o{o}_obs_iodine.dtau", f"o{o}_obsgrid_iodine.dtau"
            if kv not in z.files or kg not in z.files:
                self.log.append(("", "", o, "no_learned_correction", "start at zero"))
                return
            v = np.asarray(z[kv], float)
            g0, gs, gn = z[kg]
        src = g0 + gs * np.arange(int(gn))
        sol.learned[o][("iodine", "dtau")] = np.interp(grid.lnlam, src, v, left=0.0, right=0.0)
        sol._sync()

    def _detector_map(self, ch, o, p0, p1):
        """The detector-frame map of a trace sliced to the block (a
        calibration product, ``calibrations.detector_map``); without one, a
        perfect detector (logged: no measured map exists yet)."""
        npx = p1 - p0 + 1
        path = self.cfg.calibrations.detector_map
        if path:
            if not hasattr(self, "_dmap"):
                z = np.load(path)
                self._dmap = {
                    (str(c), int(oo)): (np.asarray(dx, float), np.asarray(r, float))
                    for c, oo, dx, r in zip(
                        z["channel"], z["order"], z["dx"], z["response"], strict=True
                    )
                }
            row = self._dmap.get((ch, o))
            if row is not None:
                return {"dx": row[0][p0 : p1 + 2].copy(), "response": row[1][p0 : p1 + 1].copy()}
        self.log.append(("", ch, o, "detector_map_identity", "no measured map"))
        return DetectorMap.identity(npx)

    def _lsf(self, fr, ch, o, grid, p0, p1, pixel_mps=0.0):
        """LSF component and parameters of a block. ``lsf.point_sampled_
        calibration``: the calibration widths were measured with a model that
        point-samples the broadened spectrum at pixel centres; specfast
        averages over each pixel, which adds the pixel box (variance w^2 / 12,
        w the pixel width), so that variance is removed from the calibrated
        width."""
        m = self.cfg.model.lsf
        box = pixel_mps**2 / 12.0 if m.point_sampled_calibration else 0.0
        if m.model == "gaussian":
            s = self.cal.lsf_sigma.get(ch, o) if self.cal.lsf_sigma else None
            if s is None:
                return None, None
            s = float(np.sqrt(max(s * s - box, (0.5 * s) ** 2)))
            return GaussianLSF.for_grid(grid, 1.5 * s, nsigma=m.nsigma, name="lsf"), {
                "sigma": np.array([s])
            }
        row = self.cal.lsf_map.get(fr.mjd_mid, ch, o) if self.cal.lsf_map else None
        if row is None:
            return None, None
        basis, bstep = None, None
        illum = m.illumination
        if illum == "basis":
            if self.cal.lsf_basis is None:
                raise ValueError("lsf.illumination = basis needs calibrations.lsf_basis")
            basis, bstep = self.cal.lsf_basis.for_order(o), self.cal.lsf_basis.step_mps
        lsf = GaussHermiteLSF.for_grid(
            grid,
            1.4 * row[0],
            nsigma=m.nsigma,
            pixel_lo=float(p0),
            pixel_hi=float(p1),
            nnode=m.nnode,
            illumination=illum,
            basis=basis,
            basis_step_mps=bstep,
            name="lsf",
        )
        row = row.copy()
        row[0] = float(np.sqrt(max(row[0] ** 2 - box, (0.5 * row[0]) ** 2)))
        p = {"map": row}
        if lsf.n_illum:
            p["illum"] = np.zeros(lsf.n_illum)
        return lsf, p

    # --------------------------------------------------------------- search
    def search(self, shifts=None, half_range=None, step=1.0, only_cold=False):
        """Coarse pixel shift per block (grid search, continuum profiled):
        around 0 over +-``half_range`` px, or around the given per-(frame,
        channel) shifts. Returns {(frame, ch): [(order, shift, dchi2)]}."""
        out = {}
        hr = self.cfg.model.wavelength.search_px if half_range is None else half_range
        for o in self.orders:
            for b, p in zip(self.blocks[o], self.params[o], strict=True):
                if only_cold and id(b) not in getattr(self, "cold", set()):
                    continue
                c0 = 0.0 if shifts is None else shifts.get(b.key, 0.0)
                s, gain = _shift_search(b, p, np.arange(c0 - hr, c0 + hr + 1e-9, step))
                if shifts is not None:
                    s, gain = _shift_search(b, p, np.arange(s - 1.0, s + 1.0 + 1e-9, 0.05))
                    _apply_shift(b, p, s)
                out.setdefault(b.key, []).append((o, float(s), float(gain)))
        if shifts is not None:
            for sol in self.solvers.values():
                sol._sync()
        return out

    # ------------------------------------------------------------------ fit
    def _shared_free(self, b):
        sh = []
        if "telluric" in [f.name for f in b.model.factors]:
            # only blocks that see water lines constrain the column
            tel = b.model.factor("telluric")
            lo, hi = b.model.grid.lnlam[0], b.model.grid.lnlam[-1]
            sel = (tel.lnlam >= lo) & (tel.lnlam <= hi)
            if np.any(sel) and float(np.max(tel.tau_water[sel])) > 1e-3:
                sh.append(("telluric", "water"))
        if isinstance(b.model.lsf, GaussHermiteLSF) and b.model.lsf.n_illum:
            sh.append(("lsf", "illum"))
        return sh

    def fit(self, shared, cold=False, want_schur=True):
        water = shared.get("water", {})
        illum = shared.get("illum", {})
        rows, schur = [], {}
        for o in self.orders:
            for i, (b, p) in enumerate(zip(self.blocks[o], self.params[o], strict=True)):
                fname, ch = b.key
                if "telluric" in p and fname in water:
                    p["telluric"]["water"] = np.array([water[fname]])
                if "illum" in p.get("lsf", {}) and b.key in illum:
                    p["lsf"]["illum"] = np.array(illum[b.key], float)
                free = [lf for lf in LOCAL_FREE if lf[0] in p]
                flat = self.meta[o][i].get("flat", False)
                if flat:
                    free = [f for f in free if f != ("star", "v")]
                try:
                    if cold or id(b) in getattr(self, "cold", set()):
                        s1 = fit_block_fast(
                            b.model,
                            b.data,
                            b.sigma,
                            b.ctx,
                            p,
                            [f for f in free if f != ("star", "v")],
                            max_iter=self.cfg.solver.max_iter_block,
                        )
                        p.update(s1.params)
                    sol = fit_block_fast(
                        b.model,
                        b.data,
                        b.sigma,
                        b.ctx,
                        p,
                        free,
                        max_iter=self.cfg.solver.max_iter_block,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.log.append((fname, ch, o, "fit_error", repr(exc)))
                    rows.append((o, i, np.nan, np.inf, np.nan, 0, False, 0, np.nan, np.nan))
                    continue
                for c, d in sol.params.items():
                    p[c] = d
                v, sv = (np.nan, np.inf) if flat else sol.value_sigma("star", "v")
                self.meta[o][i]["chi2r"] = float(sol.chi2 / max(sol.ndata, 1))
                m = sol.flux
                good = sol.rw != 0
                with np.errstate(divide="ignore", invalid="ignore"):
                    frac = float(np.sqrt(np.mean(((b.data - m) / m)[good] ** 2)))
                k = float(p["iodine"]["k"][0]) if "iodine" in p else np.nan
                rows.append((o, i, v, sv, sol.chi2, sol.ndata, sol.converged, sol.niter, frac, k))
                if want_schur:
                    for name, sh in (("water", ("telluric", "water")), ("illum", ("lsf", "illum"))):
                        if sh not in self._shared_free(b):
                            continue
                        try:
                            H, g, _, _ = schur_terms(b.model, p, b.ctx, b.data, b.sigma, free, [sh])
                        except Exception as exc:  # noqa: BLE001
                            self.log.append((fname, ch, o, f"schur_{name}_error", repr(exc)))
                            continue
                        gk = fname if name == "water" else b.key
                        acc = schur.setdefault(name, {}).setdefault(gk, [0.0, 0.0])
                        acc[0] = acc[0] + H
                        acc[1] = acc[1] + g
        for sol in self.solvers.values():
            sol._sync()
        self.cold = set()
        return rows, schur

    def keys(self):
        return {
            o: [
                (b.key, m["z_bary"], m["group"])
                for b, m in zip(self.blocks[o], self.meta[o], strict=True)
            ]
            for o in self.orders
        }

    # ------------------------------------------------------------- template
    def template(self, block_v, zp_increment, omega=1.0, exclude=()):
        """Template (and learned observatory) step per order and target, with
        the block velocities and zero-point increments (per group) from the
        master. ``omega`` > 1 over-relaxes the template update (successive
        over-relaxation of the alternation: old + omega * (new - old)). The
        learned observed-frame corrections of an order are solved once from
        all its targets' normal equations."""
        stats = {}
        ex = set(map(tuple, exclude))
        targets = targets_of(self.cfg)
        for (o, t), sol in self.solvers.items():
            idx = self.sol_index[(o, t)]
            sol.excluded = {id(self.blocks[o][i]) for i in idx if (o, i) in ex}
            for j, i in enumerate(idx):
                v = block_v.get((o, i))
                if v is not None and np.isfinite(v):
                    sol.params[j]["star"]["v"] = np.array([v])
            g = self.group(o, t)
            if g in zp_increment:
                sol.zero_point[o] += zp_increment[g][0]
                sol.zero_point_sigma[o] = zp_increment[g][1]
            sol._sync()
            old = sol.flux[o].copy()
            if targets[t].mode != "flat":
                sol.template_step()
                if omega != 1.0:
                    sol.flux[o] = old + omega * (sol.flux[o] - old)
                    sol._sync()
            stats[g] = dict(
                dflux_rms=float(np.sqrt(np.mean((sol.flux[o] - old) ** 2))),
                dobs_rms=0.0,
                zero_point=float(sol.zero_point[o]),
            )
        mi = self.cfg.model.iodine
        for o in self.orders:
            ts = [t for (oo, t) in self.solvers if oo == o]
            sols = [self.solvers[(o, t)] for t in ts]
            if not sols or not sols[0].config.learn_observatory or not any(sols[0].learned[o]):
                continue
            w = []
            for t, sol in zip(ts, sols, strict=True):
                c2 = [
                    self.meta[o][i].get("chi2r", np.nan)
                    for i in self.sol_index[(o, t)]
                    if id(self.blocks[o][i]) not in sol.excluded
                ]
                c2 = np.asarray(c2, float)
                c2 = c2[np.isfinite(c2) & (c2 > 0)]
                if mi.target_weighting == "chi2r" and targets[t].mode != "flat" and c2.size:
                    w.append(1.0 / float(np.median(c2)))
                else:
                    w.append(1.0)
            res = pooled_observatory_step(sols, o, w)
            for t, sh, wt in zip(ts, res["share"], w, strict=True):
                g = self.group(o, t)
                stats[g]["dobs_rms"] = res["rms_step"]
                stats[g]["obs_share"] = sh
                stats[g]["obs_weight"] = wt
        return stats

    # ------------------------------------------------------------ project
    def project(self, nseg, projection):
        rows = []
        for o in self.orders:
            for i, (b, p, m) in enumerate(
                zip(self.blocks[o], self.params[o], self.meta[o], strict=True)
            ):
                free = [lf for lf in LOCAL_FREE if lf[0] in p]
                out = dict(order=o, index=i)
                lam = b.model.wavelength.evaluate(p["wavelength"], b.model.pixels[[0, -1]], b.ctx)
                out["l1"], out["l2"] = float(lam[0]), float(lam[1])
                try:
                    sol = fit_block_fast(b.model, b.data, b.sigma, b.ctx, p, free, max_iter=3)
                    out["cov_local"] = sol.cov
                    out["labels"] = sol.labels
                    if projection:
                        out["proj"] = project_block(
                            b.model, p, b.ctx, b.data, b.sigma, free, nseg=nseg
                        )
                except Exception as exc:  # noqa: BLE001
                    self.log.append((m["frame"], m["ch"], o, "project_error", repr(exc)))
                out["params"] = {
                    c: {
                        k: np.asarray(v).tolist()
                        for k, v in d.items()
                        if k not in ("flux", "dtau", "dtau_dry", "dtau_water")
                    }
                    for c, d in p.items()
                }
                rows.append(out)
        return rows

    def templates(self):
        out = {}
        for (o, t), sol in self.solvers.items():
            out[self.group(o, t)] = dict(
                grid=(sol.grids[o].ln_start, sol.grids[o].step, sol.grids[o].n),
                flux=sol.flux[o],
                sigma=sol.flux_sigma[o],
                prior=sol.prior[o],
                zero_point=sol.zero_point[o],
                zero_point_sigma=sol.zero_point_sigma[o],
                observatory={f"{a}.{b}": v for (a, b), v in sol.learned[o].items()},
                observatory_grid={
                    f"{a}.{b}": self._learned_grid(sol, o, (a, b)) for (a, b) in sol.learned[o]
                },
            )
        return out

    @staticmethod
    def _learned_grid(sol, o, term):
        for b, p in zip(sol.blocks, sol.params, strict=True):
            if b.order == o:
                f = b.model.factor(term[0])
                for name, grid, _ in f.learned_terms(p[f.name], b.ctx):
                    if name == term[1]:
                        return np.array([grid.ln_start, grid.step, grid.n], float)
        return np.zeros(3)

    def state(self):
        st = {}
        for o in self.orders:
            st[o] = dict(
                keys=[b.key for b in self.blocks[o]],
                params=[
                    {
                        c: {k: np.asarray(v) for k, v in d.items() if k != "flux"}
                        for c, d in p.items()
                    }
                    for p in self.params[o]
                ],
            )
            st[o]["solvers"] = {
                t: dict(
                    flux=sol.flux[o],
                    zp=sol.zero_point[o],
                    learned={k: v for k, v in sol.learned[o].items()},
                )
                for (oo, t), sol in self.solvers.items()
                if oo == o
            }
        return st

    def load_state(self, st):
        """Warm start from a saved state; blocks without a saved state stay
        cold (``self.cold``) and get the wavelength search and the two-stage
        fit. Returns the number of cold blocks."""
        self.cold = set()
        for o in self.orders:
            idx = {k: i for i, k in enumerate(st[o]["keys"])} if o in st else {}
            for b, p in zip(self.blocks[o], self.params[o], strict=True):
                j = idx.get(b.key)
                if j is None:
                    self.cold.add(id(b))
                    continue
                for c, d in st[o]["params"][j].items():
                    if c in p:
                        for k, v in d.items():
                            if k in p[c] and np.shape(p[c][k]) == np.shape(v):
                                p[c][k] = np.array(v, float)
            if o not in st:
                continue
            saved = st[o].get("solvers")
            if saved is None and "flux" in st[o]:  # one-star state of earlier versions
                saved = {
                    0: dict(flux=st[o]["flux"], zp=st[o]["zp"], learned=st[o].get("learned", {}))
                }
            for t, d in (saved or {}).items():
                sol = self.solvers.get((o, t))
                if sol is None:
                    continue
                if sol.flux[o].shape == d["flux"].shape:
                    sol.flux[o] = np.array(d["flux"])
                    sol.zero_point[o] = float(d["zp"])
                for k, v in d.get("learned", {}).items():
                    if k in sol.learned[o] and sol.learned[o][k].shape == v.shape:
                        sol.learned[o][k] = np.array(v)
                sol._sync()
        return len(self.cold)


def _extra_excluded(cfg, date, ch):
    for w in cfg.extra_excluded:
        a = datetime.date.fromisoformat(str(w["start"]))
        b = datetime.date.fromisoformat(str(w["end"]))
        if a <= date <= b and (not w.get("channels") or ch in w["channels"]):
            return True
    return False


def _shift_search(b: Block, p, shifts):
    """Best pixel shift of the block's wavelength solution on a grid of
    shifts (continuum profiled by linear least squares)."""
    m = b.model
    fine = m.fine_spectrum(p, b.ctx)
    ks, _ = m.node_kernels(p, b.ctx)
    bb = convolve(fine, ks[len(ks) // 2])
    w = np.where(np.isfinite(b.sigma), 1.0 / b.sigma, 0.0)
    good = w > 0
    t = (m.pixels - m.continuum.x_center) / m.continuum.x_scale
    basis = np.stack([t**j for j in range(m.continuum.degree + 1)], axis=1)
    edges = m.sample_positions(p)
    best, bchi, chis = 0.0, np.inf, []
    lo, hi = m.grid.lnlam[1], m.grid.lnlam[-2]
    for s in shifts:
        le = np.log(m.wavelength.evaluate(p["wavelength"], edges + s, b.ctx))
        if le[0] < lo or le[-1] > hi:
            chis.append(np.inf)
            continue
        u = m.bin(bb, le)
        X = basis * u[:, None]
        coef, *_ = np.linalg.lstsq(X[good] * w[good, None], b.data[good] * w[good], rcond=None)
        r = (b.data - X @ coef) * w
        c = float(r[good] @ r[good])
        chis.append(c)
        if c < bchi:
            best, bchi = float(s), c
    chis = np.array(chis)
    fin = chis[np.isfinite(chis)]
    gain = float(np.median(fin) - bchi) if fin.size else 0.0
    return best, gain


def _apply_shift(b: Block, p, s):
    """Move the block's wavelength perturbation so lambda(p) -> lambda(p + s)
    (and reset the continuum level)."""
    m = b.model
    w = m.wavelength
    lam_s = w.evaluate(p["wavelength"], m.pixels + s, b.ctx)
    t = w.scaled(m.pixels)
    target = lam_s - w.base_curve(w.distorted(m.pixels))
    p["wavelength"]["coeffs"] = np.polynomial.polynomial.polyfit(t, target, w.degree)


# --------------------------------------------------------------- processes
def _worker_main(conn, cfg, ins, frames, orders):
    log: list = []
    try:
        w = OrderWorker(cfg, ins, frames, orders, log)
        w.build()
        conn.send(("ok", sum(len(v) for v in w.blocks.values())))
    except Exception:  # noqa: BLE001
        conn.send(("error", traceback.format_exc()))
        return
    while True:
        cmd, payload = conn.recv()
        if cmd == "stop":
            conn.send(("ok", log))
            return
        try:
            fn = getattr(w, cmd)
            res = fn(**payload)
            conn.send(("ok", res))
        except Exception:  # noqa: BLE001
            conn.send(("error", traceback.format_exc()))


class _Pool:
    def __init__(self, cfg, ins, frames, order_sets):
        ctx = mp.get_context("fork")
        self.procs, self.conns = [], []
        for orders in order_sets:
            a, b = ctx.Pipe()
            pr = ctx.Process(target=_worker_main, args=(b, cfg, ins, frames, orders), daemon=True)
            pr.start()
            self.procs.append(pr)
            self.conns.append(a)
        self.nblocks = 0
        for c in self.conns:
            st, res = c.recv()
            if st != "ok":
                self.close()
                raise RuntimeError(f"worker failed to build:\n{res}")
            self.nblocks += res

    def call(self, cmd, **payload):
        for c in self.conns:
            c.send((cmd, payload))
        out = []
        for c in self.conns:
            st, res = c.recv()
            if st != "ok":
                raise RuntimeError(f"worker {cmd} failed:\n{res}")
            out.append(res)
        return out

    def close(self):
        logs = []
        for c in self.conns:
            try:
                c.send(("stop", {}))
                st, res = c.recv()
                if st == "ok":
                    logs.extend(res)
            except (EOFError, OSError, BrokenPipeError):
                pass
        for p in self.procs:
            p.join(timeout=30)
            if p.is_alive():
                p.terminate()
        return logs


# ---------------------------------------------------------- shared steps
def _shared_update(cfg, shared, schur, frames_era, hyper):
    """One Gauss-Newton step of each shared parameter group with its prior;
    updates the hierarchical illumination prior. Returns change summary."""
    out = {}
    if "water" in schur:
        dmax = 0.0
        nclip = 0
        for fname, (H, g) in schur["water"].items():
            H = np.atleast_2d(H)
            if H[0, 0] <= 0:
                continue
            # weak prior N(1, water_prior_sigma) in atlas units
            w0 = shared["water"].get(fname, 1.0)
            pw = 1.0 / cfg.model.telluric.water_prior_sigma**2
            d = float((np.atleast_1d(g)[0] - pw * (w0 - 1.0)) / (H[0, 0] + pw))
            lim = max(0.5, w0)  # at most a doubling per sweep
            d = float(np.clip(d, -lim, lim))
            shared["water"][fname] = max(shared["water"].get(fname, 1.0) + d, 0.0)
            dmax = max(dmax, abs(d))
            nclip += int(abs(d) >= lim)
        out["water_max_step"] = dmax
        out["water_clipped"] = nclip
    if "illum" in schur:
        lsf = cfg.model.lsf
        steps = []
        for key, (H, g) in schur["illum"].items():
            H = np.atleast_2d(H)
            n = H.shape[0]
            phi = np.asarray(shared["illum"].get(key, np.zeros(n)), float)
            grp = (key[1], frames_era.get(key[0], 0))
            mu, tau = hyper.get(grp, (np.zeros(n), np.resize(np.array(lsf.tau_init, float), n)))
            P = (
                np.diag(1.0 / np.maximum(tau, lsf.tau_floor) ** 2)
                if lsf.hierarchical
                else np.zeros((n, n))
            )
            try:
                d = np.linalg.solve(H + P, np.atleast_1d(g) - P @ (phi - mu))
            except np.linalg.LinAlgError:
                continue
            d = np.clip(d, -3.0, 3.0) if lsf.illumination == "basis" else np.clip(d, -0.05, 0.05)
            shared["illum"][key] = phi + d
            try:
                shared.setdefault("illum_var", {})[key] = np.diag(np.linalg.inv(H + P))
            except np.linalg.LinAlgError:
                pass
            steps.append(np.max(np.abs(d)))
        out["illum_max_step"] = float(max(steps)) if steps else 0.0
        if not lsf.exposure_common:
            # per-channel kernels only: remove each exposure's channel mean
            byexp: dict = {}
            for key in shared["illum"]:
                byexp.setdefault(key[0], []).append(key)
            for keys in byexp.values():
                m = np.mean([shared["illum"][k] for k in keys], axis=0)
                for k in keys:
                    shared["illum"][k] = shared["illum"][k] - m
        if lsf.hierarchical:
            groups = {}
            for key, phi in shared["illum"].items():
                grp = (key[1], frames_era.get(key[0], 0))
                groups.setdefault(grp, []).append((phi, shared.get("illum_var", {}).get(key)))
            for grp, items in groups.items():
                P_ = np.array([x[0] for x in items])
                V_ = np.array([x[1] if x[1] is not None else np.zeros(P_.shape[1]) for x in items])
                if len(items) < 3:
                    continue
                # EM update of the hierarchical normal prior: mean and
                # variance of the posterior means plus their posterior
                # variances (never collapses below what the data support)
                mu = P_.mean(axis=0)
                var = np.maximum(((P_ - mu) ** 2 + V_).mean(axis=0), lsf.tau_floor**2)
                hyper[grp] = (mu, np.sqrt(var))
            out["illum_hyper"] = {
                f"{g[0]}/era{g[1]}": [np.round(h[0], 4).tolist(), np.round(h[1], 4).tolist()]
                for g, h in hyper.items()
            }
    return out


def _legendre(x, deg):
    return np.stack(
        [np.polynomial.legendre.legval(x, np.eye(deg + 1)[k]) for k in range(1, deg + 1)], axis=1
    )


def _berv_pattern(cfg, bl, vel, off):
    """Per-order smooth function of BERV on block residuals (per-(channel,
    order) constants profiled), with its mean over orders at each exposure
    removed. Returns f per block row index (m/s) and coefficients."""
    bp = cfg.model.berv_pattern
    f = np.zeros(len(bl["v"]))
    coefs = {}
    ok = np.isfinite(bl["v"]) & np.isfinite(bl["sv"]) & (bl["sv"] > 0)
    vk = np.array([vel[k][0] if k in vel else np.nan for k in bl["key"]])
    dlt = np.array([off.get(o, (0.0, 0.0))[0] for o in bl["order"]])
    r = bl["v"] - vk - dlt
    x = np.clip(bl["berv_kms"] / bp.scale_kms, -1.5, 1.5)
    for o in np.unique(bl["order"]):
        s = ok & (bl["order"] == o) & np.isfinite(r)
        if s.sum() < 20:
            continue
        chs = sorted(set(bl["ch"][s]))
        X = np.concatenate(
            [
                np.stack([(bl["ch"][s] == c).astype(float) for c in chs], 1),
                _legendre(x[s], bp.degree),
            ],
            axis=1,
        )
        w = 1.0 / bl["sv"][s] ** 2
        A = X.T @ (X * w[:, None])
        c = np.linalg.solve(A + 1e-9 * np.eye(A.shape[0]), X.T @ (w * r[s]))
        cb = c[len(chs) :]
        coefs[int(o)] = cb.tolist()
        so = bl["order"] == o
        f[so] = _legendre(x[so], bp.degree) @ cb
    # remove the per-exposure weighted mean over orders (belongs to v_key)
    w = np.where(ok, 1.0 / np.where(ok, bl["sv"], 1.0) ** 2, 0.0)
    keys = {k: i for i, k in enumerate(dict.fromkeys(bl["key"]))}
    ki = np.array([keys[k] for k in bl["key"]])
    num = np.bincount(ki, w * f, len(keys))
    den = np.bincount(ki, w, len(keys))
    f = f - (num / np.where(den > 0, den, 1.0))[ki]
    return f, coefs


# -------------------------------------------------------------------- run
def run(cfg: DopplerRunConfig, config_path: str | None = None) -> Path:
    t_start = time.time()
    out = Path(cfg.output)
    out.mkdir(parents=True, exist_ok=True)
    ins = load_instrument(cfg.instrument)
    log: list = []
    frames = list_frames(cfg, ins, log)
    if not frames:
        raise RuntimeError("no frames to fit")
    orders = list(cfg.model.orders or ins.arms[0].rv_orders)
    nproc = max(1, min(cfg.solver.processes, len(orders)))
    sets = [orders[i::nproc] for i in range(nproc)]
    conv = dict(sweeps=[], started=datetime.datetime.now(datetime.UTC).isoformat())
    _progress(out, f"{len(frames)} frames, orders {orders}, {nproc} processes")
    pool = _Pool(cfg, ins, frames, sets)
    _progress(out, f"built {pool.nblocks} blocks ({time.time() - t_start:.0f} s)")
    cal = Calibrations.load(cfg)
    frames_era = {f.name: (cal.lsf_map.era(f.mjd_mid) if cal.lsf_map else 0) for f in frames}
    zb = {f.name: f.z_bary for f in frames}
    shared = {"water": {f.name: 1.0 for f in frames}, "illum": {}}
    hyper: dict = {}
    warm = None
    if cfg.solver.warm_start:
        with open(cfg.solver.warm_start, "rb") as fh:
            warm = pickle.load(fh)
    try:
        if warm is None:
            # coarse wavelength search: per block, then per-(frame, channel)
            # median, then a local search around it
            res = pool.call("search")
            per = {}
            for r in res:
                for k, lst in r.items():
                    per.setdefault(k, []).extend(lst)
            med = {
                k: float(np.median([s for _, s, g in lst if g > 0] or [s for _, s, _ in lst]))
                for k, lst in per.items()
            }
            pool.call("search", shifts=med, half_range=3.0, step=0.25)
            _progress(
                out,
                f"wavelength search done ({time.time() - t_start:.0f} s); "
                f"median |shift| {np.median(np.abs(list(med.values()))):.2f} px",
            )
        else:
            ncold = sum(pool.call("load_state", st=warm["workers"]))
            shared = warm["shared"]
            for f in frames:
                shared.setdefault("water", {}).setdefault(f.name, 1.0)
            hyper = warm.get("hyper", {})
            if ncold:
                res = pool.call("search", only_cold=True)
                per = {}
                for r in res:
                    for k, lst in r.items():
                        per.setdefault(k, []).extend(lst)
                med = {
                    k: float(np.median([s for _, s, g in lst if g > 0] or [s for _, s, _ in lst]))
                    for k, lst in per.items()
                }
                pool.call("search", shifts=med, half_range=3.0, step=0.25, only_cold=True)
            _progress(out, f"warm start: {ncold} blocks without saved state (searched, cold fit)")
        prev = None
        templ = any(t.mode != "fixed" for t in targets_of(cfg))
        f_berv = None
        for sweep in range(1, cfg.solver.sweeps + 1):
            t0 = time.time()
            res = pool.call("fit", shared=shared, cold=(sweep == 1 and warm is None))
            rows = [r for rr, _ in res for r in rr]
            schur: dict = {}
            for _, s in res:
                for name, d in s.items():
                    for k, (H, g) in d.items():
                        acc = schur.setdefault(name, {}).setdefault(k, [0.0, 0.0])
                        acc[0] = acc[0] + H
                        acc[1] = acc[1] + g
            keys = {}
            for kk in pool.call("keys"):
                keys.update(kk)
            bl = _block_table(rows, keys, zb)
            ok = np.isfinite(bl["v"]) & np.isfinite(bl["sv"]) & (bl["sv"] > 0) & (bl["sv"] < 1e3)
            ok &= bl["conv"] & (bl["frac"] <= cfg.solver.template_max_frac_rms)
            # outlying blocks (failed fits, wrong minima): more than the
            # tolerance from their order's median velocity
            for o in np.unique(bl["group"]):
                so = ok & (bl["group"] == o)
                if so.any():
                    med = np.median(bl["v"][so])
                    ok &= ~(
                        (bl["group"] == o)
                        & (np.abs(bl["v"] - med) > cfg.solver.template_max_dev_mps)
                    )
            vel, off = combine_velocities(
                bl["v"][ok],
                bl["sv"][ok],
                [bl["key"][i] for i in np.where(ok)[0]],
                bl["group"][ok],
                fit_offsets=True,
            )
            if cfg.model.berv_pattern.enabled:
                f_berv, bcoef = _berv_pattern(cfg, bl, vel, off)
                bl["v_berv_corr"] = bl["v"] - f_berv
                vel, off = combine_velocities(
                    bl["v_berv_corr"][ok],
                    bl["sv"][ok],
                    [bl["key"][i] for i in np.where(ok)[0]],
                    bl["group"][ok],
                    fit_offsets=True,
                )
            rec = dict(
                sweep=sweep,
                seconds=time.time() - t0,
                nblocks=int(len(bl["v"])),
                nfit=int(ok.sum()),
                chi2=float(np.nansum(bl["chi2"])),
                ndata=int(np.nansum(bl["ndata"])),
                converged_blocks=float(np.mean(bl["conv"])),
                order_offsets_rms=float(np.std([d for d, _ in off.values()])),
            )
            rec["blocks_in_template"] = int(ok.sum())
            if prev is not None:
                # well-measured (exposure, channel) velocities only (formal
                # error < 20 m/s)
                common = sorted(k for k in set(prev) & set(vel) if vel[k][1] < 20.0)
                dv = np.array([vel[k][0] - prev[k][0] for k in common])
                dv = dv - np.median(dv)
                rec["dv_max"] = float(np.max(np.abs(dv)))
                rec["dv_p95"] = float(np.percentile(np.abs(dv), 95))
                rec["dv_med"] = float(np.median(np.abs(dv)))
                rec["dv_rms"] = float(np.sqrt(np.mean(dv**2)))
                rec["n_dv"] = len(common)
                if conv["sweeps"] and "dv_rms" in conv["sweeps"][-1]:
                    rec["dv_ratio"] = rec["dv_rms"] / max(conv["sweeps"][-1]["dv_rms"], 1e-12)
            upd = _shared_update(cfg, shared, schur, frames_era, hyper)
            rec.update({k: v for k, v in upd.items() if k != "illum_hyper"})
            rec["illum_hyper"] = upd.get("illum_hyper")
            conv["sweeps"].append(rec)
            summary = {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in rec.items()
                if k != "illum_hyper"
            }
            _progress(out, f"sweep {sweep}: {json.dumps(summary)}")
            with open(out / "convergence.json", "w") as fh:
                json.dump(conv, fh, indent=1, default=float)
            converged = prev is not None and rec.get("dv_p95", np.inf) < cfg.solver.tol_mps
            prev = vel
            _save_state(out, pool, shared, hyper)
            if sweep == cfg.solver.sweeps or converged:
                break
            if templ:
                block_v, zpinc = {}, {}
                for j in range(len(bl["v"])):
                    k = bl["key"][j]
                    if k in vel:
                        fb = 0.0 if f_berv is None else f_berv[j]
                        block_v[(int(bl["order"][j]), int(bl["index"][j]))] = vel[k][0] + fb
                if cfg.model.star.fit_zero_points:
                    zpinc = {int(o): (d, s) for o, (d, s) in off.items()}
                excl = [
                    (int(bl["order"][j]), int(bl["index"][j]))
                    for j in range(len(bl["v"]))
                    if not ok[j] or bl["key"][j] not in vel
                ]
                st = pool.call(
                    "template",
                    block_v=block_v,
                    zp_increment=zpinc,
                    omega=cfg.solver.relaxation,
                    exclude=excl,
                )
                rec["template"] = {int(o): v for s in st for o, v in s.items()}
        # final projection and outputs
        _progress(out, "projection")
        proj = [
            r
            for rr in pool.call(
                "project", nseg=cfg.outputs.segments, projection=cfg.outputs.projection
            )
            for r in rr
        ]
        temps = {}
        for t in pool.call("templates"):
            temps.update(t)
        _write_outputs(
            cfg, ins, out, frames, bl, proj, vel, off, shared, temps, f_berv, config_path
        )
    finally:
        log.extend(pool.close())
    with open(out / "log.tsv", "w") as fh:
        fh.write("frame\tchannel\torder\treason\tdetail\n")
        for row in log:
            fh.write("\t".join(str(x).replace("\t", " ").replace("\n", " | ") for x in row) + "\n")
    conv["finished"] = datetime.datetime.now(datetime.UTC).isoformat()
    conv["seconds"] = time.time() - t_start
    with open(out / "convergence.json", "w") as fh:
        json.dump(conv, fh, indent=1, default=float)
    _progress(out, f"done ({time.time() - t_start:.0f} s)")
    return out


def run_config_hash(cfg) -> str:
    """sha256 of the run configuration's canonical JSON (dates as ISO)."""
    text = json.dumps(dataclasses.asdict(cfg), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def _progress(out: Path, msg: str):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(out / "progress.log", "a") as fh:
        fh.write(line + "\n")


def _save_state(out, pool, shared, hyper):
    st = {}
    for s in pool.call("state"):
        st.update(s)
    tmp = out / "state.pkl.tmp"
    with open(tmp, "wb") as fh:
        pickle.dump(dict(workers=st, shared=shared, hyper=hyper), fh)
    tmp.replace(out / "state.pkl")


def _block_table(rows, keys, zb):
    n = len(rows)
    bl = dict(
        order=np.zeros(n, int),
        group=np.zeros(n, int),
        index=np.zeros(n, int),
        v=np.full(n, np.nan),
        sv=np.full(n, np.nan),
        chi2=np.full(n, np.nan),
        ndata=np.zeros(n, int),
        conv=np.zeros(n, bool),
        niter=np.zeros(n, int),
        frac=np.full(n, np.nan),
        k=np.full(n, np.nan),
        key=[None] * n,
        ch=np.empty(n, object),
        berv_kms=np.zeros(n),
    )
    for j, (o, i, v, sv, chi2, nd, cv, nit, frac, k) in enumerate(rows):
        bl["order"][j], bl["index"][j] = o, i
        bl["v"][j], bl["sv"][j], bl["chi2"][j] = v, sv, chi2
        bl["ndata"][j], bl["conv"][j], bl["niter"][j] = nd, cv, nit
        bl["frac"][j], bl["k"][j] = frac, k
        key, z, g = keys[o][i]
        bl["key"][j] = key
        bl["group"][j] = g
        bl["ch"][j] = key[1]
        bl["berv_kms"][j] = -z * C_KMS
    return bl


def _write_outputs(cfg, ins, out, frames, bl, proj, vel, off, shared, temps, f_berv, config_path):
    from astropy.table import Table

    from specfast.doppler.runconfig import CorrectionConfig  # noqa: F401

    fr = {f.name: f for f in frames}
    tnames = [t.star.name for t in targets_of(cfg)]
    chans = tuple(ins.arms[0].channels)
    corrs = {c.name: CB.Corrections(c.path, c.column, chans) for c in cfg.calibrations.corrections}
    pj = {(r["order"], r["index"]): r for r in proj}
    nseg = cfg.outputs.segments
    rows = []
    for j in range(len(bl["v"])):
        o, i = int(bl["order"][j]), int(bl["index"][j])
        fname, ch = bl["key"][j]
        f = fr[fname]
        v = bl["v"][j]
        r = dict(
            file=fname,
            target=tnames[f.target],
            channel=ch,
            tel=chans.index(ch),
            order=o,
            mjd_mid_utc=f.mjd_mid,
            exptime=f.exptime,
            z_bary_prov=f.z_bary,
            v=v,
            v_err=bl["sv"][j],
            cz=float(C_MPS * measured_redshift(v, f.z_bary)) if np.isfinite(v) else np.nan,
            chi2=bl["chi2"][j],
            ndata=int(bl["ndata"][j]),
            frac_rms=bl["frac"][j],
            iodine_k=bl["k"][j],
            converged=bool(bl["conv"][j]),
            niter=int(bl["niter"][j]),
            berv_pattern=float(f_berv[j]) if f_berv is not None else 0.0,
            water=float(shared["water"].get(fname, np.nan)),
        )
        il = shared["illum"].get((fname, ch))
        r["illum"] = np.asarray(il if il is not None else [], float)
        for name, c in corrs.items():
            r[f"corr_{name}"] = c.get(fname, chans.index(ch))
        p = pj.get((o, i), {})
        prm = p.get("params", {})
        r["wave_coeffs"] = np.asarray(prm.get("wavelength", {}).get("coeffs", []), float)
        r["l1"], r["l2"] = p.get("l1", np.nan), p.get("l2", np.nan)
        pr = p.get("proj")
        if pr is not None:
            r["vseg"] = np.asarray(pr["vseg"], float)
            r["vseg_cov"] = np.asarray(pr["vseg_cov"], float).ravel()
            r["shape"] = np.array([pr["shape"].get(n, np.nan) for n in SHAPE_ORDER])
            idx = [
                pr["shape_names"].index(n) if n in pr["shape_names"] else -1 for n in SHAPE_ORDER
            ]
            cov = np.full((len(SHAPE_ORDER), len(SHAPE_ORDER)), np.nan)
            sc = pr["shape_cov"]
            for a, ia in enumerate(idx):
                for b, ib in enumerate(idx):
                    if ia >= 0 and ib >= 0:
                        cov[a, b] = sc[ia, ib]
            r["shape_cov"] = cov.ravel()
        else:
            r["vseg"] = np.full(nseg, np.nan)
            r["vseg_cov"] = np.full(nseg * nseg, np.nan)
            r["shape"] = np.full(len(SHAPE_ORDER), np.nan)
            r["shape_cov"] = np.full(len(SHAPE_ORDER) ** 2, np.nan)
        lab = p.get("labels")
        if lab is not None:
            r["cov_local"] = np.asarray(p["cov_local"], float).ravel()
        rows.append(r)
    # uniform vector lengths
    for col in ("illum", "wave_coeffs", "cov_local"):
        n = max((len(r.get(col, [])) for r in rows), default=0)
        for r in rows:
            a = np.asarray(r.get(col, []), float)
            r[col] = np.r_[a, np.full(n - a.size, np.nan)]
    t = Table(rows=rows)
    t.meta["SHAPES"] = ",".join(SHAPE_ORDER)
    t.meta["NSEG"] = nseg
    t.meta["VUNIT"] = "m/s"
    t.meta["CZ"] = "c * z_meas, raw measured redshift (no barycentric correction)"
    t.meta["VDEF"] = "barycentric velocity with the provisional z_bary (audit only)"
    t.write(out / "blocks.fits", overwrite=True)
    erows = []
    for (fname, ch), (v, s) in sorted(vel.items()):
        f = fr[fname]
        e = dict(
            file=fname,
            channel=ch,
            tel=chans.index(ch),
            mjd_mid_utc=f.mjd_mid,
            z_bary_prov=f.z_bary,
            v=v,
            v_err=s,
            cz=float(C_MPS * measured_redshift(v, f.z_bary)),
        )
        for name, c in corrs.items():
            e[f"corr_{name}"] = c.get(fname, chans.index(ch))
        erows.append(e)
    Table(rows=erows).write(out / "exposures.fits", overwrite=True)
    if temps:
        arr = {}
        for o, d in temps.items():
            arr[f"o{o}_grid"] = np.array(d["grid"], float)
            arr[f"o{o}_flux"] = d["flux"]
            arr[f"o{o}_sigma"] = d["sigma"]
            arr[f"o{o}_prior"] = d["prior"]
            arr[f"o{o}_zero_point"] = np.array([d["zero_point"], d["zero_point_sigma"]])
            for k, v in d["observatory"].items():
                arr[f"o{o}_obs_{k}"] = v
            for k, v in d.get("observatory_grid", {}).items():
                arr[f"o{o}_obsgrid_{k}"] = v
        np.savez(out / "templates.npz", **arr)
    inputs = {}
    c = cfg.calibrations
    for role in (
        "iodine_atlas",
        "telluric_atlas",
        "template",
        "lsf_map",
        "lsf_sigma",
        "lsf_basis",
        "optics",
        "distortion",
        "wavelength_static",
        "detector_map",
    ):
        if getattr(c, role):
            inputs[role] = getattr(c, role)
    for cc in c.corrections:
        inputs[f"correction_{cc.name}"] = cc.path
    for t in cfg.targets:
        if t.template:
            inputs[f"template_{t.star.name}"] = t.template
    if cfg.model.iodine.correction_file:
        inputs["iodine_correction"] = cfg.model.iodine.correction_file
    prov = Provenance.create("doppler", config_sha256=run_config_hash(cfg), inputs=inputs)
    with open(out / "provenance.json", "w") as fh:
        json.dump(
            dict(
                provenance=json.loads(prov.to_json()),
                config=dataclasses.asdict(cfg),
                config_path=config_path,
                order_offsets={int(o): list(v) for o, v in off.items()},
                nframes=len(frames),
            ),
            fh,
            indent=1,
            default=str,
        )


SHAPE_ORDER = ("lsf_width", "lsf_h3", "star_broad", "star_skew", "star_depth")

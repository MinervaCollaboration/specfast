"""Stable-line atlas from NEID solar line-by-line velocities, and its payoff tests.

    python neid_lineatlas.py --solar E1.npz:pre E2.npz:post ... --lines lines.npz
        [--tau lbl_tau.npz] [--sunspots SN_d_tot_V2.0.csv] [--flares-rank FLARES_ranking.csv
        --flares-metrics LBL_metrics.csv] [--minerva-orders kiwispec] [--minerva-chunks excess.csv]
        --out-dir DIR [--n-boot 2000]

Inputs: ``neid_lbl.py measure`` outputs (one per template era; ``:pre`` or
``:post`` says which side of NEID's 2022 fire it is), the line list, and
optional public references (SILSO daily sunspot number; the FLARES
line ranking and per-line metrics of Pandey et al. 2026, Zenodo
10.5281/zenodo.20937741, CC BY 4.0).

Steps (all statistics on daily means; m/s):

1. Per line and zero-point era: weighted zero point, 6-sigma clipping.
   Zero-point eras = template eras, with an extra break at 2024-03-01
   (found in NEID tau Ceti data inside one DRP version).
2. "Clean" lines (the baseline "all lines"): NEID telluric model absorbs
   < 1% anywhere in the window in every frame, and the line is measured in
   >= 90% of frames.
3. Per line: day-to-day excess variance beyond photon noise (unbiased
   mean(D^2 - E^2) of daily means D about the zero point) in four day
   subsets: pre-fire, post-fire, low and high activity (median daily
   sunspot number); within-day excess; slope against the common daily RV
   (beta) and against the sunspot number.
4. Cross-fit payoff: days split into halves A/B (alternating within each
   era); lines chosen or weighted on one half, evaluated on the other, both
   ways. Daily-mean RV rms of: all clean lines; the "universal" stable
   subset (excess variance below the clean-line median in all four
   subsets); the 50% of lines with the lowest pooled excess; the 50% with
   the lowest |beta - mean| (activity-insensitive); inverse-variance weights
   with the excess added in quadrature. Paired day-bootstrap CIs.
5. Published lists (FLARES top 24 and top 10%), evaluated on all days.
6. tau Ceti (optional): night-to-night rms with solar-selected subsets and
   solar excess weights (selected on all solar days; no tau data used),
   paired night-bootstrap CIs.
7. Atlas CSV (one row per line window and order) and MINERVA order mapping.
"""

from __future__ import annotations

import argparse
import csv
import json
import os

import numpy as np

from specfast.conventions import C_MPS
from specfast.linestats import combine_lines, excess_ml, group_means, wrms

FIRE_BREAK = "2022-07-01"
ZP_BREAK = "2024-03-01"
TELL_MAX = 0.01
METER_CV_MAX = 0.27
CCF_SD_MAX = 3.0  # m/s
MIN_FWHM = 4000.0  # m/s
MAX_SIG = 100.0  # m/s, median per-frame line error
CLIP = 5.0  # robust per-frame combination of lines (see linestats.combine_lines)
# KiwiSpec product orders (index, vacuum nm span over the 2048 columns), from
# specfast/instruments/kiwispec.yaml; MINERVA's RV chunks are orders 1-23 with
# 2 A trimmed at each end.
KIWISPEC = [
    (0, 498.9, 503.1),
    (1, 503.1, 507.2),
    (2, 507.2, 511.5),
    (3, 511.5, 515.8),
    (4, 515.8, 520.1),
    (5, 520.3, 524.6),
    (6, 524.7, 529.1),
    (7, 529.3, 533.7),
    (8, 533.9, 538.4),
    (9, 538.7, 543.1),
    (10, 543.5, 548.0),
    (11, 548.4, 552.9),
    (12, 553.4, 557.9),
    (13, 558.4, 563.1),
    (14, 563.6, 568.3),
    (15, 568.9, 573.6),
    (16, 574.2, 579.0),
    (17, 579.7, 584.5),
    (18, 585.3, 590.1),
    (19, 591.0, 595.8),
    (20, 596.8, 601.7),
    (21, 602.7, 607.6),
    (22, 608.7, 613.7),
    (23, 614.8, 619.9),
    (24, 621.1, 626.2),
    (25, 627.5, 632.7),
    (26, 634.1, 639.3),
    (27, 640.7, 646.0),
]
TAU_SHIFT_MS = -15955.0  # tau Cet frame relative to the solar template frame (NEID CCFs)


# ----------------------------------------------------------------------------- loading
def load_lbl(spec, tag_key="era"):
    path, side = spec.rsplit(":", 1)
    d = np.load(path)
    n = d["vel"].shape[0]
    dates = np.array([str(x)[:10] for x in d["meta_date_obs"]])
    zp_era = np.array([f"{os.path.basename(path)}|{'b' if x >= ZP_BREAK else 'a'}" for x in dates])
    return {
        "vel": d["vel"].astype(float),
        "sig": d["sig"].astype(float),
        "date": dates,
        "zp_era": zp_era,
        "side": np.array([side] * n),
        "tell_max": d["tell_max"],
        "act": d["meta_act"],
        "ccf": d["meta_ccf_mod"],
        "fname": d["meta_fname"],
        "bjd": d["meta_bjd"][:, 60] if d["meta_bjd"].ndim == 2 else d["meta_bjd"],
        "snr": d["meta_extsnr"],
        "meter_cv": d["meta_meter_cv"],
    }


def quality(sol, day_qc="ccf", log=None):
    """Frame and day cuts for the solar feed; returns a boolean frame mask.

    Frames (RV-blind): exposure-meter flux variability <= METER_CV_MAX (the
    clear-sky value is 0.245-0.255; clouds raise it) and S/N >= 0.8 x the
    day's best. Days: >= 4 good frames and, with ``day_qc="ccf"``, NEID's
    own CCF velocities (an external pipeline, independent of any line
    selection here) consistent within the day (robust sd <= CCF_SD_MAX m/s);
    this catches instrument or feed glitches (e.g. 2021-10-24) that the
    frame cuts miss.
    """
    day = sol["date"]
    keep = np.isfinite(sol["meter_cv"]) & (sol["meter_cv"] <= METER_CV_MAX)
    for d in np.unique(day):
        s = day == d
        keep[s] &= sol["snr"][s] >= 0.8 * np.nanmax(sol["snr"][s])
    bad_days = []
    for d in np.unique(day):
        s = (day == d) & keep
        ok = s.sum() >= 4
        if ok and day_qc == "ccf":
            c = sol["ccf"][s]
            sd = 1.4826 * np.median(np.abs(c - np.median(c)))
            ok = sd <= CCF_SD_MAX
        if not ok:
            keep[day == d] = False
            bad_days.append(d)
    if log is not None:
        log["qc_frames_kept"] = int(keep.sum())
        log["qc_frames_total"] = int(keep.size)
        log["qc_days_dropped"] = bad_days
    return keep


def subset(sol, keep):
    return {k: (v if k == "tell_max" else v[keep]) for k, v in sol.items()}


def concat(parts):
    out = {}
    for k in parts[0]:
        if k == "tell_max":
            out[k] = np.max([p[k] for p in parts], axis=0)
        else:
            out[k] = np.concatenate([p[k] for p in parts])
    return out


def sunspots(path):
    sn = {}
    if not path:
        return sn
    with open(path) as fh:
        for row in fh:
            f = row.split(";")
            if len(f) > 4 and float(f[4]) >= 0:
                sn[f"{int(f[0]):04d}-{int(f[1]):02d}-{int(f[2]):02d}"] = float(f[4])
    return sn


# ----------------------------------------------------------------------------- per line
def zero_and_clip(vel, sig, zp_era, nsig=6.0):
    r = np.full_like(vel, np.nan)
    for e in np.unique(zp_era):
        s = zp_era == e
        v, sg = vel[s], sig[s]
        ok = np.isfinite(v) & np.isfinite(sg) & (sg > 0)
        w = np.where(ok, 1 / np.where(ok, sg, 1) ** 2, 0)
        mu = np.nansum(np.where(ok, v, 0) * w, axis=0) / np.maximum(w.sum(axis=0), 1e-30)
        for _ in range(2):
            z = (v - mu) / sg
            mad = 1.4826 * np.nanmedian(np.abs(z), axis=0)
            okk = ok & (np.abs(z) < nsig * np.maximum(mad, 1.0))
            w = np.where(okk, 1 / np.where(okk, sg, 1) ** 2, 0)
            mu = np.nansum(np.where(okk, v, 0) * w, axis=0) / np.maximum(w.sum(axis=0), 1e-30)
        rr = v - mu
        rr[~okk] = np.nan
        r[s] = rr
    return r


def daily(r, sig, day):
    return group_means(day, r, sig)


def common_daily(r, sig, day, mask):
    v, e = combine_lines(r, sig, mask=mask, clip=CLIP)
    return group_means(day, v, e)


# ----------------------------------------------------------------------------- RV series
def daily_rv(r, sig, day, mask=None, extra=None):
    v, e = combine_lines(r, sig, mask=mask, extra=extra, clip=CLIP)
    ud, Dv, Ev = group_means(day, v, e)
    return ud, Dv, Ev


def era_centered(ud, Dv, era_of_day):
    out = Dv.copy()
    for e in np.unique(era_of_day):
        s = era_of_day == e
        out[s] -= np.nanmean(Dv[s])
    return out


def rms_ci(series_fn, groups, n_boot, seed=1):
    """rms of a centred series and its bootstrap over groups (dict of method -> series)."""
    rng = np.random.default_rng(seed)
    keys = list(series_fn)
    ng = len(groups)
    boots = {k: [] for k in keys}
    for _ in range(n_boot):
        idx = np.concatenate([groups[i] for i in rng.integers(0, ng, ng)])
        for k in keys:
            x = series_fn[k][idx]
            boots[k].append(np.sqrt(np.nanmean((x - np.nanmean(x)) ** 2)))
    return {k: np.array(v) for k, v in boots.items()}


# ----------------------------------------------------------------------------- main analysis
def analyse(a):
    os.makedirs(a.out_dir, exist_ok=True)
    ll = np.load(a.lines)
    sol = concat([load_lbl(s) for s in a.solar])
    qclog = {}
    sol = subset(sol, quality(sol, a.day_qc, qclog))
    nl = ll["center"].size
    sn = sunspots(a.sunspots)
    r = zero_and_clip(sol["vel"], sol["sig"], sol["zp_era"])
    sig = sol["sig"]
    day = sol["date"]
    frac = np.isfinite(r).mean(axis=0)
    sig_line = np.nanmedian(sig, axis=0)
    # RV-blind line quality: telluric-free, measured in >= 90% of frames, resolved
    # (FWHM >= 4 km/s; narrower minima are template noise) and informative
    # (median per-frame error <= 100 m/s)
    clean = (
        (sol["tell_max"] < TELL_MAX)
        & (frac >= 0.9)
        & (ll["fwhm"] >= MIN_FWHM)
        & (sig_line <= MAX_SIG)
    )
    res = {
        "n_frames": int(r.shape[0]),
        "n_days": int(np.unique(day).size),
        "n_lines": int(nl),
        "n_clean": int(clean.sum()),
        **qclog,
    }
    print(json.dumps(res), flush=True)

    # per-day attributes
    ud, D, E = daily(r, sig, day)
    nd = ud.size
    side_of_day = np.array([sol["side"][day == d][0] for d in ud])
    zp_of_day = np.array([sol["zp_era"][day == d][0] for d in ud])
    sn_day = np.array([sn.get(d, np.nan) for d in ud])
    hk = sol["act"][:, 0]
    _, hk_day, _ = group_means(day, hk, np.ones_like(hk))
    # CaHK centred per zero-point era (instrument-dependent index); fill missing SN from HK
    hk_c = era_centered(ud, hk_day, zp_of_day)
    ok = np.isfinite(sn_day) & np.isfinite(hk_c)
    if ok.sum() > 10:
        p = np.polyfit(hk_c[ok], sn_day[ok], 1)
        act_day = np.where(np.isfinite(sn_day), sn_day, np.polyval(p, hk_c))
    else:
        act_day = sn_day
    low = act_day <= np.nanmedian(act_day)
    subsets = {"pre": side_of_day == "pre", "post": side_of_day == "post", "low": low, "high": ~low}
    res["days_per_subset"] = {k: int(v.sum()) for k, v in subsets.items()}

    # common daily RV (clean lines) and line statistics on all days
    _, Dc, Ec = common_daily(r, sig, day, clean)
    Dc_c = era_centered(ud, Dc, zp_of_day)
    res["sun_daily_rms_all_clean"] = wrms(Dc_c)
    _, ccf_day, _ = group_means(day, sol["ccf"], np.ones(day.size))
    ccf_c = era_centered(ud, ccf_day, zp_of_day)
    okc = np.isfinite(ccf_c) & np.isfinite(Dc_c)
    res["neid_ccf_daily_rms"] = wrms(ccf_c[okc])
    res["lbl_vs_ccf_daily"] = dict(
        r=float(np.corrcoef(ccf_c[okc], Dc_c[okc])[0, 1]), rms_diff=wrms(ccf_c[okc] - Dc_c[okc])
    )
    stats = line_stats(r, sig, day, ud, D, E, subsets, Dc, act_day, np.ones(nd, bool), zp_of_day)

    # cross-fit
    halves = split_days(ud, zp_of_day)
    xfit, half_stats = crossfit(
        r, sig, day, ud, D, E, subsets, Dc_c, act_day, halves, clean, zp_of_day, a.n_boot
    )
    res["crossfit"] = xfit
    res["reliability"] = reliability(stats, half_stats, clean)
    extra_cols = flares_metrics(a, ll)
    res["correlates"] = correlates(stats, clean, ll, sol["tell_max"], extra_cols)

    # published lists
    pub = published(a, ll, clean)
    if pub:
        res["published"] = evaluate_masks(r, sig, day, ud, zp_of_day, clean, pub, a.n_boot)

    # universal stable flag on all days (for the atlas and tau)
    stable_all = universal(stats, clean)
    res["stable_fraction_all_days"] = float(stable_all.sum() / clean.sum())
    res["stable_fraction_by_half"] = [float(x) for x in xfit["stable_fraction"]]

    # tau Ceti
    if a.tau:
        res["tau"] = tau_test(a.tau, ll, clean, stable_all, stats, a.n_boot, pub)

    # MINERVA mapping
    morder = minerva_order(ll["center"])
    if a.minerva_chunks:
        res["minerva"] = minerva_chunks(a.minerva_chunks, morder, stable_all, clean, ll)
    write_atlas(a, ll, sol, stats, clean, stable_all, morder, pub, frac, extra_cols)
    with open(os.path.join(a.out_dir, "results.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    np.savez(
        os.path.join(a.out_dir, "line_stats.npz"),
        clean=clean,
        stable=stable_all,
        days=ud,
        act_day=act_day,
        common=Dc_c,
        **{k: v for k, v in stats.items()},
    )
    print(json.dumps(res, indent=1, default=float))


def center_rows(D, E, rows, zp_of_day):
    """Per-line daily means centred per zero-point era using only ``rows`` days.

    Returns (Dc, Ee): centred means (NaN outside ``rows``) and the noise
    standard deviation of each centred mean, E sqrt(1 - w/W).
    """
    Dc = np.full_like(D, np.nan)
    Ee = np.full_like(E, np.nan)
    ok = np.isfinite(D) & np.isfinite(E)
    w = np.where(ok, 1 / np.where(ok, E, 1) ** 2, 0)
    for e in np.unique(zp_of_day):
        s = rows & (zp_of_day == e)
        if s.sum() < 2:
            continue
        W = w[s].sum(0)
        with np.errstate(all="ignore"):
            mu = (w[s] * np.where(ok[s], D[s], 0)).sum(0) / W
            Dc[s] = D[s] - mu
            Ee[s] = E[s] * np.sqrt(np.clip(1 - w[s] / W, 0, 1))
    Dc[~ok] = np.nan
    return Dc, Ee


def center_series(x, rows, zp_of_day, e=None):
    out = np.full(x.shape, np.nan)
    for z in np.unique(zp_of_day):
        s = rows & (zp_of_day == z) & np.isfinite(x)
        if s.sum() < 2:
            continue
        if e is None:
            out[s] = x[s] - np.mean(x[s])
        else:
            ww = 1 / e[s] ** 2
            out[s] = x[s] - np.sum(ww * x[s]) / np.sum(ww)
    return out


def exvar_c(Dc, Ee, nmin=5):
    with np.errstate(all="ignore"):
        x = Dc**2 - Ee**2
        n = np.isfinite(x).sum(axis=0)
        v = np.nanmean(x, axis=0)
        se = np.nanstd(x, axis=0) / np.sqrt(np.maximum(n, 1))
    v[n < nmin] = np.nan
    se[n < nmin] = np.nan
    return v, se


def slope_c(Dc, Ee, xc):
    """Weighted slope of centred daily means against a centred regressor (no intercept)."""
    ok = np.isfinite(Dc) & np.isfinite(Ee) & (Ee > 0) & np.isfinite(xc)[:, None]
    w = np.where(ok, 1 / np.where(ok, Ee, 1) ** 2, 0)
    X = np.where(ok, xc[:, None], 0)
    with np.errstate(all="ignore"):
        sxx = (w * X**2).sum(0)
        b = (w * X * np.where(ok, Dc, 0)).sum(0) / sxx
        eb = 1 / np.sqrt(sxx)
    b[sxx == 0] = np.nan
    eb[sxx == 0] = np.nan
    return b, eb


def line_stats(r, sig, day, ud, D, E, subsets, common, act_day, rows, zp_of_day):
    """Per-line statistics using only the days in ``rows`` (zero points per era
    re-estimated on those days, so disjoint day sets give independent numbers)."""
    st = {}
    for k, s in subsets.items():
        st[f"exvar_{k}"], st[f"exvar_se_{k}"] = exvar_c(*center_rows(D, E, s & rows, zp_of_day))
    Dc, Ee = center_rows(D, E, rows, zp_of_day)
    st["exvar_all"], st["exvar_se_all"] = exvar_c(Dc, Ee)
    cc = center_series(common, rows, zp_of_day)
    st["exvar_rel"], _ = exvar_c(Dc - cc[:, None], Ee)
    st["beta"], st["beta_err"] = slope_c(Dc, Ee, cc)
    ac = center_series(act_day / 100.0, rows, zp_of_day)
    st["act_slope"], st["act_slope_err"] = slope_c(Dc, Ee, ac)
    # within-day excess: frame residuals about the daily mean, frames of ``rows`` days
    inv = np.searchsorted(ud, day)
    fr = rows[inv]
    x = (r - D[inv])[fr]
    with np.errstate(all="ignore"):
        w = 1 / sig**2
        W = np.zeros_like(D)
        np.add.at(W, inv, np.where(np.isfinite(r), w, 0))
        e_eff = (sig * np.sqrt(np.clip(1 - w / W[inv], 1e-3, 1)))[fr]
        st["exvar_within"] = np.nanmean(x**2 - e_eff**2, axis=0)
    st["sig_med"] = np.nanmedian(sig, axis=0)
    st["E_med"] = np.nanmedian(np.where(rows[:, None], E, np.nan), axis=0)
    return st


def _spear(x, y):
    from scipy.stats import spearmanr

    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return [np.nan, np.nan, int(ok.sum())]
    rho, p = spearmanr(x[ok], y[ok])
    return [float(rho), float(p), int(ok.sum())]


def reliability(st, half_stats, clean):
    """Are per-line statistics repeatable? Spearman between disjoint day sets."""
    A, B = half_stats
    c = clean
    return {
        "exvar_halfA_vs_halfB": _spear(A["exvar_all"][c], B["exvar_all"][c]),
        "exvar_pre_vs_post": _spear(st["exvar_pre"][c], st["exvar_post"][c]),
        "exvar_low_vs_high": _spear(st["exvar_low"][c], st["exvar_high"][c]),
        "exvar_rel_halfA_vs_halfB": _spear(A["exvar_rel"][c], B["exvar_rel"][c]),
        "beta_halfA_vs_halfB": _spear(A["beta"][c], B["beta"][c]),
        "act_slope_halfA_vs_halfB": _spear(A["act_slope"][c], B["act_slope"][c]),
        "exvar_within_halfA_vs_halfB": _spear(A["exvar_within"][c], B["exvar_within"][c]),
        # signal-to-noise of the per-line excess: median |exvar| / se
        "median_exvar_over_se": float(
            np.nanmedian(np.abs(st["exvar_all"][c]) / st["exvar_se_all"][c])
        ),
    }


def flares_metrics(a, ll, tol_kms=1.0):
    """Atomic data (VALD via FLARES LBL_metrics.csv) matched by wavelength."""
    out = {k: np.full(ll["center"].size, np.nan) for k in ("exc_eV", "loggf", "lande_g")}
    if not a.flares_metrics:
        return out
    lam, cols = [], []
    with open(a.flares_metrics) as fh:
        for row in csv.DictReader(fh):
            lam.append(float(row["lambda"]))
            cols.append(
                [
                    float(row[k]) if row[k] not in ("", "NaN") else np.nan
                    for k in ("excitation_energy", "oscillator_strength", "lande_factor")
                ]
            )
    lam, cols = np.array(lam), np.array(cols)
    o = np.argsort(lam)
    lam, cols = lam[o], cols[o]
    c = ll["center"]
    j = np.clip(np.searchsorted(lam, c), 1, lam.size - 1)
    jj = np.where(np.abs(lam[j] - c) < np.abs(lam[j - 1] - c), j, j - 1)
    ok = np.abs(lam[jj] / c - 1) * C_MPS / 1e3 < tol_kms
    for i, k in enumerate(("exc_eV", "loggf", "lande_g")):
        out[k][ok] = cols[jj[ok], i]
    return out


def correlates(st, clean, ll, tell_max, extra):
    """Binned mean excess variance, beta and within-day excess against line properties."""
    props = {
        "depth": (ll["depth"], [0.03, 0.1, 0.2, 0.4, 0.6, 1.0]),
        "fwhm_kms": (ll["fwhm"] / 1e3, [0, 5, 7, 9, 12, 100]),
        "blend": (ll["blend"], [0, 0.02, 0.05, 0.15, 0.4, 1.0]),
        "tell_max": (tell_max, [0, 1e-4, 1e-3, 3e-3, 0.01]),
        "wave_A": (ll["center"], [3900, 4500, 5000, 5500, 6000, 6500, 7900]),
        "exc_eV": (extra["exc_eV"], [0, 1, 2, 3, 4, 5, 10]),
        "lande_g": (extra["lande_g"], [-1, 0.75, 1.0, 1.25, 1.5, 4]),
    }
    out = {}
    for name, (x, edges) in props.items():
        rows = []
        for lo, hi in zip(edges[:-1], edges[1:], strict=True):
            s = clean & np.isfinite(x) & (x >= lo) & (x < hi)
            n = int(s.sum())
            if n < 5:
                rows.append([lo, hi, n] + [np.nan] * 6)
                continue
            v = st["exvar_all"][s]
            # weights from photon noise only (var of D^2 - E^2 ~ E^4), not from the scatter
            wv = 1 / st["E_med"][s] ** 4
            okv = np.isfinite(v) & np.isfinite(wv)
            b = st["beta"][s]
            wb = 1 / st["beta_err"][s] ** 2
            okb = np.isfinite(b) & np.isfinite(wb)
            vm = float(np.sum(wv[okv] * v[okv]) / np.sum(wv[okv]))
            # error from the scatter of the per-line values about the weighted mean
            vse = float(np.sqrt(np.sum(wv[okv] ** 2 * (v[okv] - vm) ** 2)) / np.sum(wv[okv]))
            rows.append(
                [
                    lo,
                    hi,
                    n,
                    vm,
                    vse,
                    float(np.sum(wb[okb] * b[okb]) / np.sum(wb[okb])),
                    float(1 / np.sqrt(np.sum(wb[okb]))),
                    float(np.nanmedian(st["exvar_within"][s])),
                    float(np.nanmedian(st["sig_med"][s])),
                ]
            )
        out[name] = {
            "columns": [
                "lo",
                "hi",
                "n",
                "wmean_exvar",
                "se",
                "wmean_beta",
                "se_beta",
                "median_exvar_within",
                "median_sig_frame",
            ],
            "rows": rows,
            "spearman_exvar": _spear(x[clean], st["exvar_all"][clean]),
            "spearman_beta": _spear(x[clean], st["beta"][clean]),
        }
    return out


def universal(st, clean, q=0.5):
    ok = clean.copy()
    for k in ("pre", "post", "low", "high"):
        v = st[f"exvar_{k}"]
        if not np.isfinite(v[clean]).any():
            continue  # subset with too few days
        thr = np.nanquantile(v[clean], q)
        ok &= np.isfinite(v) & (v <= thr)
    return ok


def split_days(ud, zp_of_day):
    h = np.zeros(ud.size, dtype=int)
    for e in np.unique(zp_of_day):
        idx = np.where(zp_of_day == e)[0]
        h[idx[1::2]] = 1
    return h


def method_masks(st, clean):
    """Masks / extra-variance weights from statistics of the selection half."""
    v = st["exvar_all"]
    thr = np.nanquantile(v[clean], 0.5)
    b = st["beta"]
    bm = np.nanmedian(b[clean])
    db = np.abs(b - bm)
    bthr = np.nanquantile(db[clean], 0.5)
    extra = np.sqrt(np.clip(np.nan_to_num(v, nan=1e6), 0, None))
    return {
        "all": (clean, None),
        "universal": (universal(st, clean), None),
        "low_excess_50": (clean & (v <= thr), None),
        "low_beta_50": (clean & (db <= bthr), None),
        "excess_weighted": (clean, extra),
    }


def crossfit(r, sig, day, ud, D, E, subsets, Dc_c, act_day, halves, clean, zp_of_day, n_boot):
    out = {"methods": {}, "stable_fraction": []}
    series = {}
    half_stats = []
    for sel in (0, 1):
        rows_sel = halves == sel
        st = line_stats(r, sig, day, ud, D, E, subsets, Dc_c, act_day, rows_sel, zp_of_day)
        half_stats.append(st)
        masks = method_masks(st, clean)
        if sel == 1:
            uA, uB = method_masks(half_stats[0], clean)["universal"][0], masks["universal"][0]
            out["universal_overlap"] = dict(
                n_A=int(uA.sum()),
                n_B=int(uB.sum()),
                n_both=int((uA & uB).sum()),
                expected_if_random=float(uA.sum() * uB.sum() / clean.sum()),
            )
        out["stable_fraction"].append(masks["universal"][0].sum() / clean.sum())
        ev_days = ud[halves != sel]
        fr = np.isin(day, ev_days)
        for name, (m, extra) in masks.items():
            udd, Dv, _ = daily_rv(r[fr], sig[fr], day[fr], mask=m, extra=extra)
            zp = np.array([zp_of_day[np.searchsorted(ud, x)] for x in udd])
            c = era_centered(udd, Dv, zp)
            series.setdefault(name, {})[sel] = (udd, c)
            out["methods"].setdefault(name, {})[f"n_lines_sel{sel}"] = int(m.sum())
    # pooled evaluation series (each day evaluated once, by the other half's selection)
    names = list(series)
    days_all = np.concatenate([series["all"][s][0] for s in (0, 1)])
    order = np.argsort(days_all)
    pooled = {n: np.concatenate([series[n][s][1] for s in (0, 1)])[order] for n in names}
    groups = [np.array([i]) for i in range(days_all.size)]
    boots = rms_ci(pooled, groups, n_boot)
    for n in names:
        x = pooled[n]
        out["methods"][n].update(
            rms=float(np.sqrt(np.nanmean(x**2))),
            rms_ci=[float(q) for q in np.percentile(boots[n], [2.5, 97.5])],
            diff_vs_all=float(np.sqrt(np.nanmean(x**2)) - np.sqrt(np.nanmean(pooled["all"] ** 2))),
            diff_ci=[float(q) for q in np.percentile(boots[n] - boots["all"], [2.5, 97.5])],
        )
    out["n_eval_days"] = int(days_all.size)
    return out, half_stats


def evaluate_masks(r, sig, day, ud, zp_of_day, clean, masks, n_boot):
    series = {}
    base = dict(all=clean)
    base.update(masks)
    for name, m in base.items():
        udd, Dv, _ = daily_rv(r, sig, day, mask=m & np.isfinite(r).any(axis=0))
        series[name] = era_centered(udd, Dv, zp_of_day)
    groups = [np.array([i]) for i in range(ud.size)]
    boots = rms_ci(series, groups, n_boot, seed=2)
    out = {}
    for n, x in series.items():
        out[n] = dict(
            n_lines=int(base[n].sum()),
            rms=float(np.sqrt(np.nanmean(x**2))),
            rms_ci=[float(q) for q in np.percentile(boots[n], [2.5, 97.5])],
            diff_ci=[float(q) for q in np.percentile(boots[n] - boots["all"], [2.5, 97.5])],
        )
    return out


def published(a, ll, clean):
    if not (a.flares_rank and a.flares_metrics):
        return {}
    met = {}
    with open(a.flares_metrics) as fh:
        for row in csv.DictReader(fh):
            met[row["name"]] = float(row["lambda"])
    rank = []
    with open(a.flares_rank) as fh:
        for row in csv.DictReader(fh):
            rank.append((int(row["rank"]), met.get(row["name"], np.nan)))
    rank.sort()
    lam = np.array([x[1] for x in rank])
    c = ll["center"]

    def match(lams, tol_kms=1.0):
        m = np.zeros(c.size, dtype=bool)
        for x in lams:
            if not np.isfinite(x):
                continue
            d = np.abs(c / x - 1) * C_MPS / 1e3
            m |= d < tol_kms
        return m

    n10 = len(lam) // 10
    return {"flares_top24": match(lam[:24]) & clean, "flares_top10pct": match(lam[:n10]) & clean}


def tau_test(path, ll, clean, stable, st, n_boot, pub):
    d = np.load(path)
    vel, sig = d["vel"].astype(float), d["sig"].astype(float)
    night = np.array([str(x)[:10] for x in d["meta_date_obs"]])
    era = np.array([str(x) for x in d["meta_driftref"]])
    r = zero_and_clip(vel, sig, era)
    tclean = clean & (d["tell_max"] < TELL_MAX) & (np.isfinite(r).mean(0) >= 0.9)
    masks = method_masks(st, tclean)
    masks["universal_solar"] = (tclean & stable, None)
    for k, m in pub.items():
        masks[k] = (m & tclean, None)
    un = np.unique(night)
    era_n = np.array([era[night == x][0] for x in un])
    series, out = {}, {}
    for name, (m, extra) in masks.items():
        v, e = combine_lines(r, sig, mask=m, extra=extra, clip=CLIP)
        u, Dv, Ev = group_means(night, v, e)
        c = era_centered(u, Dv, era_n)
        series[name] = c
        within = v - Dv[np.searchsorted(u, night)]
        out[name] = dict(
            n_lines=int(m.sum()),
            formal_nightly=float(np.nanmedian(Ev)),
            excess_ml=float(excess_ml(c, Ev)),
            within_rms=float(np.nanstd(within)),
        )
    groups = [np.array([i]) for i in range(un.size)]
    boots = rms_ci(series, groups, n_boot, seed=3)
    for n in series:
        out[n].update(
            rms=float(np.sqrt(np.nanmean(series[n] ** 2))),
            rms_ci=[float(q) for q in np.percentile(boots[n], [2.5, 97.5])],
            diff_vs_all=float(
                np.sqrt(np.nanmean(series[n] ** 2)) - np.sqrt(np.nanmean(series["all"] ** 2))
            ),
            diff_ci=[float(q) for q in np.percentile(boots[n] - boots["all"], [2.5, 97.5])],
        )
    # NEID CCF for reference
    u, Dv, _ = group_means(night, d["meta_ccf_mod"], np.ones(night.size))
    out["neid_ccf"] = dict(rms=float(np.sqrt(np.nanmean(era_centered(u, Dv, era_n) ** 2))))
    out["n_nights"] = int(un.size)
    out["n_frames"] = int(night.size)
    return out


def minerva_order(center_A, shift_ms=TAU_SHIFT_MS):
    lam_nm = center_A * (1 + shift_ms / C_MPS) / 10.0
    out = np.full(center_A.size, -1)
    for i, lo, hi in KIWISPEC:
        if 1 <= i <= 23:
            s = (lam_nm >= lo + 0.2) & (lam_nm <= hi - 0.2)
            out[s] = i
    return out


def minerva_chunks(path, morder, stable, clean, ll):
    tau = {}
    with open(path) as fh:
        for row in csv.DictReader(fh):
            if row["star"] != "HD10700":
                continue
            tau.setdefault(int(row["ordi"]), []).append(float(row["v_mom"]))
    rows = []
    for o in sorted(tau):
        s = (morder == o) & clean
        q = ll["q"]
        rows.append(
            (
                o,
                float(np.mean(tau[o])),
                int(s.sum()),
                int((s & stable).sum()),
                float(np.sum(q[s & stable]) / max(np.sum(q[s]), 1e-30)),
            )
        )
    rows = np.array(rows)
    from scipy.stats import spearmanr

    rho, p = spearmanr(rows[:, 4], rows[:, 1])
    rho2, p2 = spearmanr(rows[:, 3] / np.maximum(rows[:, 2], 1), rows[:, 1])
    return {
        "per_order": rows.tolist(),
        "columns": [
            "ordi",
            "tauCet_chunk_excess_var_mean",
            "n_clean",
            "n_stable",
            "stable_q_share",
        ],
        "spearman_qshare_vs_excess": [float(rho), float(p)],
        "spearman_nfrac_vs_excess": [float(rho2), float(p2)],
    }


def write_atlas(a, ll, sol, st, clean, stable, morder, pub, frac, extra):
    path = os.path.join(a.out_dir, "neid_solar_line_atlas.csv")
    flr = pub.get("flares_top24", np.zeros(clean.size, bool))
    cols = [
        "order_m",
        "wave_vac_A",
        "lo_A",
        "hi_A",
        "depth",
        "fwhm_kms",
        "blend",
        "tell_max",
        "clean",
        "sig_frame_ms",
        "exvar_pre",
        "exvar_post",
        "exvar_low",
        "exvar_high",
        "exvar_all",
        "exvar_se_all",
        "exvar_within",
        "beta",
        "beta_err",
        "act_slope",
        "act_slope_err",
        "exc_eV",
        "loggf",
        "lande_g",
        "minerva_order",
        "stable",
        "flares_top24",
    ]

    def f(x, nd=2):
        return "" if not np.isfinite(x) else f"{x:.{nd}f}"

    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i in range(ll["center"].size):
            if frac[i] < 0.5:
                continue
            w.writerow(
                [
                    int(ll["order_m"][i]),
                    f"{ll['center'][i]:.4f}",
                    f"{ll['lo'][i]:.4f}",
                    f"{ll['hi'][i]:.4f}",
                    f(ll["depth"][i], 3),
                    f(ll["fwhm"][i] / 1e3, 2),
                    f(ll["blend"][i], 3),
                    f(sol["tell_max"][i], 4),
                    int(clean[i]),
                    f(st["sig_med"][i], 1),
                    f(st["exvar_pre"][i], 1),
                    f(st["exvar_post"][i], 1),
                    f(st["exvar_low"][i], 1),
                    f(st["exvar_high"][i], 1),
                    f(st["exvar_all"][i], 1),
                    f(st["exvar_se_all"][i], 1),
                    f(st["exvar_within"][i], 1),
                    f(st["beta"][i], 2),
                    f(st["beta_err"][i], 2),
                    f(st["act_slope"][i], 2),
                    f(st["act_slope_err"][i], 2),
                    f(extra["exc_eV"][i], 3),
                    f(extra["loggf"][i], 3),
                    f(extra["lande_g"][i], 2),
                    int(morder[i]),
                    int(stable[i]),
                    int(flr[i]),
                ]
            )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--solar", nargs="+", required=True, help="lbl.npz:pre|post")
    p.add_argument("--lines", required=True)
    p.add_argument("--tau")
    p.add_argument("--sunspots")
    p.add_argument("--flares-rank")
    p.add_argument("--flares-metrics")
    p.add_argument("--minerva-chunks")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--n-boot", type=int, default=2000)
    p.add_argument("--day-qc", choices=("ccf", "none"), default="ccf")
    analyse(p.parse_args(argv))


if __name__ == "__main__":
    main()

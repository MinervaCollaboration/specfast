"""Line-by-line velocities of NEID L2 spectra (solar feed or stars), in three steps.

    python neid_lbl.py template --caches C1.npz [C2.npz ...] --out tmpl.npz
                                [--max-frames 160] [--vstar 0] [--workers 6]
    python neid_lbl.py lines    --template tmpl.npz --out lines.npz [--min-depth 0.03]
    python neid_lbl.py measure  --caches ... --template tmpl.npz --lines lines.npz --out lbl.npz
                                [--vstar 0] [--workers 6]

Inputs are compact per-day caches written by ``neid_lbl_cache.py`` (orders
m = 154..79 of NEID L2: blaze-divided here, wavelengths = reference SCIWAVE x
(1 + per-frame factor), per-order barycentric z_B from the header). Rest-frame
wavelengths are lambda_obs (1 + z_B) / (1 + vstar / c).

- ``template``: per order, a median co-add (specfast.doppler.lbl.build_template)
  of up to ``--max-frames`` frames spread over the days given, on the first
  frame's rest-frame wavelength grid.
- ``lines``: line windows from the template minima (specfast.doppler.lbl.find_lines).
  The windows are in rest-frame wavelength, so one line list can be applied to
  any template (another era, another star) of a similar spectrum.
- ``measure``: per frame and order, per-line velocities against the template
  (specfast.doppler.lbl.line_velocities), plus each line's NEID telluric-model
  absorption (max over the frames) and the frame metadata.
"""

from __future__ import annotations

import argparse
import os
from multiprocessing import Pool

import numpy as np

from specfast.conventions import C_MPS
from specfast.doppler.lbl import build_template, find_lines, line_velocities, template_spline

G = {}  # data shared with forked workers


def frame_ok(d):
    """RV-blind frame cut: S/N, exposure-meter flux variability, and a comb-based
    wavelength calibration (DRP WAVECAL "LFCplusThAr..."; "ThAronly" days sit
    ~30 m/s off in NEID's own CCF velocities as well)."""
    snr = d["extsnr"]
    cv = d["meter_cv"]
    lfc = np.array([str(x).startswith("LFCplusThAr") for x in d["wavecal"]])
    return np.isfinite(snr) & (snr >= 150) & ~(cv > 0.6) & lfc


def load(caches, vstar, need_tell=False):
    frames = []
    for c in caches:
        z = np.load(c)
        keys = [
            "flux",
            "var",
            "blaze",
            "wref",
            "wfull",
            "wfull_idx",
            "wscale",
            "zb",
            "orders_m",
            "bjd",
            "date_obs",
            "fname",
            "extsnr",
            "pwv",
            "airmass",
            "zen",
            "ccf_mod",
            "ccf_mod_err",
            "drp",
            "driftref",
            "act",
            "meter_cv",
            "drift0",
            "wavecal",
        ]
        if need_tell:
            keys.append("tell")
        d = {k: z[k] for k in keys}  # decompress each array once
        ok = frame_ok(d)
        wfi = list(d["wfull_idx"])
        for j in np.where(ok)[0]:
            fr = {
                "cache": os.path.basename(c),
                "flux": d["flux"][j],
                "var": d["var"][j],
                "blaze": d["blaze"],
                "wref": d["wref"],
                "wfull": d["wfull"][wfi.index(j)] if j in wfi else None,
                "s": float(d["wscale"][j]),
                "zb": d["zb"][j][173 - d["orders_m"]],
                "meta": {
                    k: d[k][j]
                    for k in (
                        "bjd",
                        "date_obs",
                        "fname",
                        "extsnr",
                        "pwv",
                        "airmass",
                        "zen",
                        "ccf_mod",
                        "ccf_mod_err",
                        "drp",
                        "driftref",
                        "act",
                        "meter_cv",
                        "drift0",
                        "wavecal",
                    )
                },
            }
            if need_tell:
                fr["tell"] = d["tell"][j]
            frames.append(fr)
    G["frames"] = frames
    G["orders_m"] = np.load(caches[0])["orders_m"]
    G["vstar"] = vstar


def order_arrays(oi, frames):
    w, f, v = [], [], []
    vstar = G["vstar"]
    for fr in frames:
        lam = fr["wfull"][oi] if fr["wfull"] is not None else fr["wref"][oi] * (1 + fr["s"])
        lam = lam * (1 + fr["zb"][oi]) / (1 + vstar / C_MPS)
        b = fr["blaze"][oi].astype(float)
        good = (b > 0) & np.isfinite(b) & np.isfinite(lam) & (lam > 0)
        bb = np.where(good, b, 1.0)
        f.append(np.where(good, fr["flux"][oi] / bb, np.nan))
        v.append(np.where(good, fr["var"][oi] / bb**2, np.inf))
        w.append(np.where(np.isfinite(lam), lam, np.nan))
    return np.array(w), np.array(f), np.array(v)


def _template_order(oi):
    frames = G["tframes"]
    w, f, v = order_arrays(oi, frames)
    # common grid: the first frame's wavelengths (fill NaN ends linearly)
    grid = w[0].copy()
    bad = ~np.isfinite(grid)
    if bad.any():
        i = np.arange(grid.size)
        grid = np.interp(i, i[~bad], grid[~bad])
    # trim 100 px at each end (blaze edges)
    tmpl, _ = build_template(w, f, v, grid)
    tmpl[:100] = np.nan
    tmpl[-100:] = np.nan
    return grid, tmpl


def cmd_template(a):
    load(a.caches, a.vstar)
    fr = G["frames"]
    # spread over caches (days)
    by = {}
    for k, x in enumerate(fr):
        by.setdefault(x["cache"], []).append(k)
    per = max(1, a.max_frames // max(1, len(by)))
    pick = []
    for ks in by.values():
        idx = np.linspace(0, len(ks) - 1, min(per, len(ks))).round().astype(int)
        pick += [ks[i] for i in sorted(set(idx))]
    G["tframes"] = [fr[k] for k in pick[: a.max_frames]]
    print(f"template from {len(G['tframes'])} frames of {len(by)} caches", flush=True)
    no = len(G["orders_m"])
    with Pool(a.workers) as p:
        res = p.map(_template_order, range(no))
    np.savez(
        a.out,
        grid=np.array([r[0] for r in res]),
        tmpl=np.array([r[1] for r in res]),
        orders_m=G["orders_m"],
        vstar=a.vstar,
        n_frames=len(G["tframes"]),
        frames=np.array([x["meta"]["fname"] for x in G["tframes"]]),
    )


def cmd_lines(a):
    t = np.load(a.template)
    rows = {k: [] for k in ("order_m", "center", "lo", "hi", "depth", "fwhm", "blend", "asym", "q")}
    for oi, m in enumerate(t["orders_m"]):
        ll = find_lines(t["grid"][oi], t["tmpl"][oi], min_depth=a.min_depth)
        rows["order_m"] += [int(m)] * len(ll)
        for k in ("center", "lo", "hi", "depth", "fwhm", "blend", "asym", "q"):
            rows[k] += list(getattr(ll, k))
    out = {k: np.array(v) for k, v in rows.items()}
    np.savez(a.out, **out)
    print(f"{out['center'].size} line windows in {len(t['orders_m'])} orders")


def _measure_order(oi):
    frames = G["frames"]
    w, f, v = order_arrays(oi, frames)
    ts = template_spline(G["grid"][oi], G["tmpl"][oi])
    dts = ts.derivative()
    sel = np.where(G["lorder"] == G["orders_m"][oi])[0]
    lo, hi = G["llo"][sel], G["lhi"][sel]
    n = len(frames)
    vel = np.full((n, sel.size), np.nan, dtype=np.float32)
    sig = np.full((n, sel.size), np.nan, dtype=np.float32)
    vord = np.full(n, np.nan)
    tmax = np.zeros(sel.size)
    tmed = []
    for k in range(n):
        if sel.size == 0:
            break
        a, b, vf, _ = line_velocities(w[k], f[k], v[k], ts, lo, hi, deriv=dts)
        vel[k], sig[k], vord[k] = a, b, vf
        if "tell" in frames[k]:
            dep = frames[k]["tell"][oi] / 65535.0
            j0 = np.searchsorted(w[k], lo)
            j1 = np.searchsorted(w[k], hi)
            tt = np.array([dep[x:y].max() if y > x else 0.0 for x, y in zip(j0, j1, strict=True)])
            tmax = np.maximum(tmax, tt)
            tmed.append(tt)
    tmed = np.median(np.array(tmed), axis=0) if tmed else np.zeros(sel.size)
    return sel, vel, sig, vord, tmax, tmed


def cmd_measure(a):
    load(a.caches, a.vstar, need_tell=True)
    t = np.load(a.template)
    ll = np.load(a.lines)
    G.update(grid=t["grid"], tmpl=t["tmpl"], lorder=ll["order_m"], llo=ll["lo"], lhi=ll["hi"])
    n, nl = len(G["frames"]), ll["center"].size
    print(f"measuring {n} frames x {nl} lines", flush=True)
    vel = np.full((n, nl), np.nan, dtype=np.float32)
    sig = np.full((n, nl), np.nan, dtype=np.float32)
    vord = np.full((n, len(G["orders_m"])), np.nan)
    tmax = np.zeros(nl)
    tmed = np.zeros(nl)
    with Pool(a.workers) as p:
        for oi, (sel, v_, s_, vo, tx, tm) in enumerate(
            p.imap(_measure_order, range(len(G["orders_m"])))
        ):
            vel[:, sel], sig[:, sel], vord[:, oi] = v_, s_, vo
            tmax[sel], tmed[sel] = tx, tm
    meta = {}
    for k in G["frames"][0]["meta"]:
        meta["meta_" + k] = np.array([fr["meta"][k] for fr in G["frames"]])
    meta["meta_zb"] = np.array([fr["zb"] for fr in G["frames"]])
    np.savez(
        a.out,
        vel=vel,
        sig=sig,
        v_order=vord,
        tell_max=tmax,
        tell_med=tmed,
        cache=np.array([fr["cache"] for fr in G["frames"]]),
        vstar=a.vstar,
        **meta,
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("template")
    s.add_argument("--caches", nargs="+", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--max-frames", type=int, default=160)
    s.add_argument("--vstar", type=float, default=0.0)
    s.add_argument("--workers", type=int, default=6)
    s = sub.add_parser("lines")
    s.add_argument("--template", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--min-depth", type=float, default=0.03)
    s = sub.add_parser("measure")
    s.add_argument("--caches", nargs="+", required=True)
    s.add_argument("--template", required=True)
    s.add_argument("--lines", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--vstar", type=float, default=0.0)
    s.add_argument("--workers", type=int, default=6)
    a = p.parse_args(argv)
    {"template": cmd_template, "lines": cmd_lines, "measure": cmd_measure}[a.cmd](a)


if __name__ == "__main__":
    main()

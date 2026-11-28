"""Compact cache of NEID L2 frames for the line atlas.

usage: python -I neid_lbl_cache.py OUT.npz FILE [FILE ...]   (one night or day per output)

Per frame, orders m = 154..79 (index 19..94): flux, variance (float32;
non-finite or non-positive variance -> 0 flux, inf variance), the wavelength
as a single multiplicative factor of a reference frame's SCIWAVE (NEID's L1
wavelengths are master x (1 + drift); the factor is verified to < 1 cm/s
per frame, else the frame's wavelengths are stored in full), NEID's telluric
model (plane 0) as uint16 absorption depth x 65535, SCIBLAZE of the
reference frame, and header quantities (per-order SSBZ/SSBJD, CCF RVs,
EXTSNR, PWV, zenith, drift, DQ bits, activity indices, exposure meter).
"""

import os
import sys
import warnings

os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np  # noqa: E402
from astropy.io import fits  # noqa: E402

warnings.filterwarnings("ignore")
M_HI, M_LO = 154, 79
IDX = np.arange(173 - M_HI, 173 - M_LO + 1)
C = 299792458.0
ACT = ("CaIIHK", "HeI_1", "NaI", "Ha06_1", "Ha16_1", "CaI_1", "CaIRT1", "CaIRT2", "CaIRT3")


def hget(h, k, default=np.nan):
    v = h.get(k, default)
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    return v


def per_order(h, pre):
    return np.array([float(hget(h, f"{pre}{173 - i:03d}")) for i in range(122)])


def main(out, files):
    rec = {
        k: []
        for k in (
            "flux",
            "var",
            "wscale",
            "tell",
            "zb",
            "bjd",
            "ccf_rv",
            "ccf_mod",
            "ccf_mod_err",
            "ccf_bjd",
            "pwv",
            "zen",
            "airmass",
            "exptime",
            "date_obs",
            "fname",
            "drp",
            "driftref",
            "wavecal",
            "drift0",
            "zptdrift",
            "extsnr",
            "dq1",
            "dq2",
            "meter_cv",
            "meter_n",
            "act",
            "act_err",
        )
    }
    wref = blaze = None
    wfull = {}
    for f in files:
        try:
            hl = fits.open(f, memmap=False)
        except Exception as e:  # noqa: BLE001
            print("SKIP", os.path.basename(f), e, flush=True)
            continue
        with hl:
            p = hl[0].header
            if hl["SCIWAVE"].data is None or hl["SCIFLUX"].data is None:
                print("SKIP nowave", os.path.basename(f), flush=True)
                continue
            w = np.asarray(hl["SCIWAVE"].data[IDX], dtype=np.float64)
            fl = np.asarray(hl["SCIFLUX"].data[IDX], dtype=np.float64)
            va = np.asarray(hl["SCIVAR"].data[IDX], dtype=np.float64)
            bad = ~np.isfinite(fl) | ~np.isfinite(va) | (va <= 0) | ~(w > 0)
            fl[bad] = 0.0
            va[bad] = np.inf
            if wref is None:
                wref = w.copy()
                blaze = np.asarray(hl["SCIBLAZE"].data[IDX], dtype=np.float32)
            ok = (w > 0) & (wref > 0)
            r = w[ok] / wref[ok] - 1.0
            s = float(np.median(r))
            n = len(rec["flux"])
            if np.max(np.abs(r - s)) * C > 0.01:
                wfull[n] = w
            rec["wscale"].append(s)
            rec["flux"].append(fl.astype(np.float32))
            rec["var"].append(va.astype(np.float32))
            if "TELLURIC" in hl and hl["TELLURIC"].data is not None:
                t = np.asarray(hl["TELLURIC"].data[IDX, :, 0], dtype=np.float64)
                th = hl["TELLURIC"].header
                rec["pwv"].append(float(hget(th, "WVAPOR")))
                rec["zen"].append(float(hget(th, "ZENITH")))
            else:
                t = np.ones_like(w)
                rec["pwv"].append(np.nan)
                rec["zen"].append(np.nan)
            t = np.where(np.isfinite(t), t, 1.0)
            rec["tell"].append(np.round(np.clip(1.0 - t, 0, 1) * 65535).astype(np.uint16))
            rec["zb"].append(per_order(p, "SSBZ"))
            rec["bjd"].append(per_order(p, "SSBJD"))
            if "CCFS" in hl:
                ch = hl["CCFS"].header
                rec["ccf_rv"].append(1e3 * per_order(ch, "CCFRV"))
                rec["ccf_mod"].append(1e3 * float(hget(ch, "CCFRVMOD")))
                rec["ccf_mod_err"].append(1e3 * float(hget(ch, "DVRMSMOD")))
                rec["ccf_bjd"].append(float(hget(ch, "CCFJDMOD")))
            else:
                rec["ccf_rv"].append(np.full(122, np.nan))
                rec["ccf_mod"].append(np.nan)
                rec["ccf_mod_err"].append(np.nan)
                rec["ccf_bjd"].append(np.nan)
            rec["airmass"].append(float(hget(p, "AIRMASS")))
            rec["exptime"].append(float(hget(p, "EXPTIME")))
            rec["date_obs"].append(str(hget(p, "DATE-OBS", "")))
            rec["fname"].append(os.path.basename(f))
            rec["drp"].append(str(hget(p, "E_VER", "")))
            rec["driftref"].append(str(hget(p, "DRIFTREF", "")))
            rec["wavecal"].append(str(hget(p, "WAVECAL", "")))
            rec["drift0"].append(float(hget(p, "DRIFTRV0")))
            rec["zptdrift"].append(float(hget(hl["SCIWAVE"].header, "ZPTDRIFT")))
            rec["extsnr"].append(float(hget(p, "EXTSNR")))
            rec["dq1"].append(str(hget(p, "DQLEVEL1", "")))
            rec["dq2"].append(str(hget(p, "DQLEVEL2", "")))
            em = hl["EXPMETER"].data if "EXPMETER" in hl else None
            if em is not None:
                sci = np.nansum(em[4], axis=0)
                ok = sci > 0
                rec["meter_cv"].append(
                    float(np.std(sci[ok]) / np.mean(sci[ok])) if ok.sum() > 2 else np.nan
                )
                rec["meter_n"].append(int(ok.sum()))
            else:
                rec["meter_cv"].append(np.nan)
                rec["meter_n"].append(0)
            av = np.full(len(ACT), np.nan)
            ae = np.full(len(ACT), np.nan)
            if "ACTIVITY" in hl and hl["ACTIVITY"].data is not None:
                d = hl["ACTIVITY"].data
                names = [str(x).strip() for x in d["INDEX"]]
                for j, a in enumerate(ACT):
                    if a in names:
                        k = names.index(a)
                        av[j] = d["VALUE"][k]
                        ae[j] = d["UNCERTAINTY"][k]
            rec["act"].append(av)
            rec["act_err"].append(ae)
        print(os.path.basename(f), flush=True)
    if not rec["flux"]:
        print("NOTHING", out)
        return 1
    arrs = {k: np.array(v) for k, v in rec.items()}
    arrs["wref"] = wref
    arrs["blaze"] = blaze
    arrs["orders_m"] = 173 - IDX
    arrs["act_names"] = np.array(ACT)
    arrs["wfull_idx"] = np.array(sorted(wfull), dtype=int)
    arrs["wfull"] = (
        np.array([wfull[k] for k in sorted(wfull)]) if wfull else np.zeros((0,) + wref.shape)
    )
    tmp = out + ".tmp.npz"
    np.savez_compressed(tmp, **arrs)
    os.replace(tmp, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sorted(sys.argv[2:])))

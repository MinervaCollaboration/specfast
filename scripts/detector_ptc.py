"""Detector constants from raw frames: overscan geometry, read noise, gain
(photon-transfer curve) and the saturation level.

Generic: every input is a path argument; nothing here knows where data live.

    python scripts/detector_ptc.py --bias B1.fits B2.fits [--flat F1.fits F2.fits]

Raw layout assumed: the imaging area is the first ``--ncols`` columns and the
first ``--nrows`` rows; whatever lies beyond on either axis is overscan
(serial overscan in columns, or overclocked rows when the controller's
serial/parallel lengths were set the other way round). Frames written by
Spectral Instruments' native software (``BITPIX = -16``, "U16" big-endian
byte pairs, ``SIMPLE = F``) are decoded as well as standard 16-bit FITS.

Method:

- overscan profile: mean of each overscan column minus the settled level (the
  last half of the overscan); with a flat, also the overscan next to the
  brightest rows, which shows how many columns carry deferred charge;
- read noise: sigma-clipped standard deviation of the difference of two bias
  frames / sqrt(2), in the imaging area and in the overscan. (A MAD estimate
  is quantised for integer ADU: 1.4826 * 3 / sqrt(2) = 3.145 for every frame);
- gain: photon-transfer curve from a pair of identical flats. Both are
  bias-subtracted (bias level + mean bias structure); the clipped variance of
  their difference / 2 against the mean level, in level bins. Pixel-response
  non-uniformity cancels in the difference. g = slope^-1 of var(mean) fitted
  between ``--fit-min`` and ``--fit-max`` ADU;
- saturation: the distribution of the highest raw values (a clipped plateau
  shows as a pile-up), and the level where the PTC variance collapses.
"""

from __future__ import annotations

import argparse

import numpy as np
from astropy.io import fits


def read_raw(path: str) -> tuple[np.ndarray, fits.Header]:
    """Raw frame as float64 ADU (rows x columns as stored) and its header."""
    with fits.open(path, uint=True, ignore_missing_end=True) as h:
        hdr = h[0].header.copy()
        d = np.asarray(h[0].data)
    ny, nx = int(hdr["NAXIS2"]), int(hdr["NAXIS1"])
    if d.ndim == 1 or d.shape[0] != ny:  # SI native U16: big-endian byte pairs
        b = np.asarray(d, np.uint8).reshape(-1)[: ny * nx * 2].reshape(ny, nx, 2)
        d = b[:, :, 0].astype(np.int64) * 256 + b[:, :, 1]
    return d.astype(float).reshape(ny, nx), hdr


def split(d: np.ndarray, ncols: int, nrows: int) -> tuple[np.ndarray, np.ndarray, str]:
    """(image, overscan with the overscan axis last, where)."""
    ny, nx = d.shape
    if nx > ncols:
        return d[:nrows, :ncols], d[:nrows, ncols:], f"{nx - ncols} columns"
    if ny > nrows:
        return d[:nrows, :ncols], d[nrows:, :ncols].T, f"{ny - nrows} rows"
    return d, np.empty((d.shape[0], 0)), "none"


def csig(x: np.ndarray, k: float = 5.0) -> float:
    """Iteratively k-sigma-clipped standard deviation."""
    x = x[np.isfinite(x)].ravel()
    for _ in range(10):
        m, s = x.mean(), x.std()
        keep = np.abs(x - m) < k * s
        if keep.all():
            break
        x = x[keep]
    return float(x.std())


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bias", nargs=2, required=True, metavar="FITS")
    ap.add_argument("--flat", nargs=2, metavar="FITS", help="two identical flats")
    ap.add_argument("--ncols", type=int, default=2048, help="imaging columns")
    ap.add_argument("--nrows", type=int, default=2052, help="imaging rows")
    ap.add_argument("--skip-overscan", type=int, default=6, help="overscan columns to skip")
    ap.add_argument("--fit-min", type=float, default=500.0, help="PTC fit lower level [ADU]")
    ap.add_argument("--fit-max", type=float, default=30000.0, help="PTC fit upper level [ADU]")
    ap.add_argument("--edge", type=int, default=20, help="image border to ignore [px]")
    a = ap.parse_args(argv)
    sk, e = a.skip_overscan, a.edge

    bias = []
    for p in a.bias:
        d, h = read_raw(p)
        im, ov, where = split(d, a.ncols, a.nrows)
        if ov.size:
            lev = float(np.median(ov[:, sk:]))
            ovs = csig(ov[:, sk:] - np.median(ov[:, sk:], axis=1, keepdims=True))
            prof = ov.mean(axis=0) - np.median(ov[:, ov.shape[1] // 2 :])
            print(f"{p}: raw {d.shape}, overscan {where}, level {lev:.1f} ADU, sigma {ovs:.2f} ADU")
            print(f"  overscan means - settled level, first 8: {np.round(prof[:8], 2)}")
            print(f"  image - overscan level: {np.median(im[e:-e, e:-e]) - lev:.2f} ADU")
        else:
            lev = float(np.median(im))
            print(f"{p}: raw {d.shape}, no overscan, image median {lev:.1f} ADU")
        bias.append((im - lev, ov[:, sk:] if ov.size else None, lev))
    rn = csig((bias[0][0] - bias[1][0])[e:-e, e:-e]) / np.sqrt(2)
    print(f"read noise (bias difference, image) {rn:.3f} ADU")
    if bias[0][1] is not None:
        print(
            f"read noise (bias difference, overscan) "
            f"{csig(bias[0][1] - bias[1][1]) / np.sqrt(2):.3f} ADU"
        )
    bstruct = 0.5 * (bias[0][0] + bias[1][0])
    blev = 0.5 * (bias[0][2] + bias[1][2])

    if not a.flat:
        return
    fl, top = [], []
    for p in a.flat:
        d, h = read_raw(p)
        im, ov, _ = split(d, a.ncols, a.nrows)
        lev = float(np.median(ov[:, sk:])) if ov.size else blev
        note = ""
        if abs(lev - blev) > 20:  # overscan polluted (saturated rows spill into it)
            note = f" (overscan polluted: {lev:.0f}; bias level {blev:.1f} used)"
            lev = blev
        print(f"{p}: EXPTIME {h.get('EXPTIME')}, max raw {im.max():.0f} ADU{note}")
        if ov.size:
            hot = np.argsort(im[:, -8:].mean(axis=1))[-50:]
            print(
                f"  50 brightest rows: last image cols - level "
                f"{np.round(im[hot, -3:].mean(axis=0) - lev, 1)}, overscan cols 0-7 - level "
                f"{np.round(ov[hot, :8].mean(axis=0) - lev, 1)}"
            )
        top.append(np.sort(im.ravel())[-20000:])
        fl.append(im - lev - bstruct)
    t = np.concatenate(top)
    q = np.percentile(t, [50, 90, 99, 99.9, 100])
    vals, cnt = np.unique(t, return_counts=True)
    print(f"highest 20000 raw values per flat: percentiles 50/90/99/99.9/100 = {np.round(q)}")
    print(
        f"  most frequent of them: {vals[np.argsort(cnt)[-5:]].astype(int)} "
        f"(counts {np.sort(cnt)[-5:]})"
    )

    f1, f2 = (f[e:-e, e:-e] for f in fl)
    m = 0.5 * (f1 + f2)
    bright = (m > a.fit_min) & (m < a.fit_max)
    r = float(np.median(f1[bright] / f2[bright])) if bright.sum() > 1000 else 1.0
    diff = f1 - r * f2
    edges = np.unique(np.concatenate([np.geomspace(50, 1000, 8), np.arange(1000, 66000, 1000)]))
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        s = (m >= lo) & (m < hi)
        if s.sum() >= 400:
            rows.append((float(np.mean(m[s])), csig(diff[s]) ** 2 / (1 + r**2), int(s.sum())))
    if len(rows) < 3:
        print("flat pair too faint for a PTC")
        return
    ptc = np.array(rows)
    print(f"flat ratio f1/f2 = {r:.4f}; PTC (mean ADU, var ADU^2, n, mean/(var-rn^2)):")
    for mu, var, n in ptc:
        print(f"  {mu:9.1f} {var:10.1f} {int(n):8d}  {mu / max(var - rn**2, 1e-9):.3f}")
    sel = (ptc[:, 0] > a.fit_min) & (ptc[:, 0] < a.fit_max)
    if sel.sum() < 3:
        return
    w = np.sqrt(ptc[sel, 2])
    A = np.vstack([ptc[sel, 0], np.ones(sel.sum())]).T
    coef = np.linalg.lstsq(A * w[:, None], ptc[sel, 1] * w, rcond=None)[0]
    g = 1 / coef[0]
    print(
        f"PTC fit {a.fit_min:.0f}-{a.fit_max:.0f} ADU: var = {coef[0]:.4f} mean + {coef[1]:.1f}"
        f" -> gain {g:.3f} e-/ADU; read noise {rn:.3f} ADU = {rn * g:.2f} e-"
    )
    pred = coef[0] * ptc[:, 0] + coef[1]
    low = np.nonzero((ptc[:, 0] > a.fit_max) & (ptc[:, 1] < 0.5 * pred))[0]
    if low.size:
        print(
            f"PTC collapse (var < half the linear trend) from mean ~{ptc[low[0], 0]:.0f} ADU"
            f" above bias ({ptc[low[0], 0] + blev:.0f} raw)"
        )


if __name__ == "__main__":
    main()

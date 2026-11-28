"""Line-by-line velocities: injection tests on synthetic spectra."""

import numpy as np

from specfast.conventions import C_MPS
from specfast.doppler.lbl import build_template, find_lines, line_velocities, template_spline

RNG = np.random.default_rng(7)
NPIX = 3000
LAM0 = 5500.0
DLNL = 1.0 / 400_000  # ~0.75 km/s per pixel
LINES = np.sort(RNG.uniform(LAM0 * 1.002, LAM0 * np.exp(NPIX * DLNL) / 1.002, 60))
DEPTHS = RNG.uniform(0.1, 0.7, LINES.size)
SIG_KMS = 3.0


def spectrum(lam, v=0.0, shift_line=None, dv_line=0.0):
    """Gaussian absorption lines (rest LINES) seen at velocity v."""
    f = np.ones_like(lam)
    for k, (c, d) in enumerate(zip(LINES, DEPTHS, strict=True)):
        vk = v + (dv_line if k == shift_line else 0.0)
        cc = c * (1 + vk / C_MPS)
        s = cc * SIG_KMS * 1e3 / C_MPS
        f *= 1 - d * np.exp(-0.5 * ((lam - cc) / s) ** 2)
    return f


def frames(vels, snr=300.0, shift_line=None, dv_line=0.0):
    lam_pix = LAM0 * np.exp(np.arange(NPIX) * DLNL)
    out_w, out_f, out_v = [], [], []
    for k, v in enumerate(vels):
        # each frame's pixels sit at a slightly different rest wavelength (barycentric shift)
        zb = RNG.uniform(-3e-6, 3e-6)
        lam_rest = lam_pix * (1 + zb)
        cont = 1000.0 * (1 + 0.2 * np.sin(np.arange(NPIX) / 900.0 + k))
        f = cont * spectrum(lam_rest, v, shift_line if k % 2 else None, dv_line)
        var = (cont / snr) ** 2 * np.ones(NPIX)
        out_w.append(lam_rest)
        out_f.append(f + RNG.normal(0, np.sqrt(var)))
        out_v.append(var)
    return np.array(out_w), np.array(out_f), np.array(out_v)


def setup(vels, **kw):
    w, f, var = frames(vels, **kw)
    grid = w[0].copy()
    tmpl, _ = build_template(w, f, var, grid)
    ll = find_lines(grid, tmpl, min_depth=0.05)
    ts = template_spline(grid, tmpl)
    return w, f, var, ll, ts


def test_template_and_lines():
    w, f, var, ll, ts = setup(np.zeros(12))
    # every isolated injected line (no neighbour within 5 sigma) is found within 300 m/s
    # (parabola centre; blends pull it)
    sep = np.abs(LINES[:, None] / LINES[None, :] - 1) * C_MPS
    np.fill_diagonal(sep, np.inf)
    iso = LINES[sep.min(axis=1) > 5 * SIG_KMS * 1e3]
    assert iso.size >= 5
    for c in iso:
        assert np.min(np.abs(ll.center / c - 1)) * C_MPS < 300
    assert np.all(ll.hi > ll.lo)
    assert np.all(ll.lo[1:] >= ll.hi[:-1] - 1e-9)  # no overlap


def test_frame_velocities_recovered():
    vels = RNG.uniform(-50, 50, 16)
    w, f, var, ll, ts = setup(vels, snr=500.0)
    est = []
    for k in range(len(vels)):
        vl, sl, vf, _ = line_velocities(w[k], f[k], var[k], ts, ll.lo, ll.hi)
        est.append(vf)
    est = np.array(est)
    d = (est - est.mean()) - (vels - vels.mean())
    assert np.std(d) < 1.0  # m/s, at S/N 500 over ~60 lines


def test_line_errors_calibrated_and_single_line_shift():
    vels = np.zeros(20)
    k_shift = int(np.argmax(DEPTHS))
    w, f, var, ll, ts = setup(vels, snr=400.0, shift_line=k_shift, dv_line=40.0)
    vl = []
    sl = []
    for k in range(len(vels)):
        a, b, _, _ = line_velocities(w[k], f[k], var[k], ts, ll.lo, ll.hi)
        vl.append(a)
        sl.append(b)
    vl, sl = np.array(vl), np.array(sl)
    j = int(np.argmin(np.abs(ll.center - LINES[k_shift])))
    odd = np.arange(len(vels)) % 2 == 1
    # the shifted line moves by ~40 m/s between odd and even frames
    diff = np.nanmean(vl[odd, j]) - np.nanmean(vl[~odd, j])
    assert 25 < diff < 55
    # other lines: residuals about their mean are consistent with the errors
    others = np.ones(len(ll), dtype=bool)
    others[j] = False
    z = (vl[:, others] - np.nanmean(vl[:, others], axis=0)) / sl[:, others]
    rz = np.nanstd(z)
    assert 0.7 < rz < 1.4

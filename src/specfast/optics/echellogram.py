"""Echellogram of one spectrograph arm: which orders land on the detector,
their wavelength ranges, trace positions per channel, dispersion, resolving
power and spacings.

Everything here is chief-ray geometry from :class:`specfast.optics.trace.System`.
Positions are in mm on the image surface (local x, y, origin at its vertex)
and in pixels once a pixel size is given.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from specfast.optics.trace import System


@dataclass(frozen=True)
class InputPoint:
    """A point on the start surface (a fibre or slice centre) [mm]."""

    name: str
    x_mm: float
    y_mm: float


@dataclass
class OrderTrace:
    """One echelle order on the detector."""

    m: int
    #: Wavelength range [um] of the reference point's trace on the detector.
    lam_lo: float
    lam_hi: float
    #: Wavelength at the detector centre line (dispersion coordinate 0) [um].
    lam_centre: float
    #: Sample wavelengths [um] (n,) and positions [mm] per point (npts, n, 2).
    lam: np.ndarray
    xy: np.ndarray
    #: Dispersion at the centre [um per mm along the dispersion axis].
    dlam_dmm: float
    #: Resolving power at the centre for the reference point (None without
    #: a core diameter).
    resolving_power: float | None = None
    #: Cross-dispersion position [mm] of every point at the order centre.
    cross_mm: np.ndarray = field(default_factory=lambda: np.zeros(0))
    #: True when every point's trace is on the detector at the order centre.
    complete: bool = True

    @property
    def fsr(self) -> float:
        """Free spectral range lambda/m at the centre [um]."""
        return self.lam_centre / self.m


@dataclass
class Echellogram:
    points: list[InputPoint]
    #: Index of the reference point (used for ranges and resolution).
    ref: int
    #: Detector half-sizes [mm] (x, y).
    half_size: tuple[float, float]
    #: 0 if the echelle disperses along detector x, 1 along y.
    disp_axis: int
    orders: list[OrderTrace]
    #: Orders of which only a corner reaches the detector (not in ``orders``).
    partial_orders: list[int] = field(default_factory=list)

    def order_spacing_mm(self) -> np.ndarray:
        """Centre-to-centre cross-dispersion spacing of adjacent orders [mm]
        (reference point, at each order's centre); length n_orders - 1."""
        c = np.array([o.cross_mm[self.ref] for o in self.orders])
        return np.abs(np.diff(c))

    def point_spacing_mm(self, i: int, j: int) -> np.ndarray:
        """Cross-dispersion distance between points i and j per order [mm]."""
        return np.array([abs(o.cross_mm[i] - o.cross_mm[j]) for o in self.orders])


def _positions(sys: System, pts: list[InputPoint], lam: np.ndarray, m: int) -> np.ndarray:
    """(npts, nlam, 2) chief-ray image positions."""
    npt, nl = len(pts), len(lam)
    x = np.repeat([p.x_mm for p in pts], nl)
    y = np.repeat([p.y_mm for p in pts], nl)
    lamv = np.tile(lam, npt)
    xy = sys.image_xy(x, y, lamv, order=m)
    return xy.reshape(npt, nl, 2)


def _monotonic_run(xy, i0):
    """Mask of the contiguous run of samples around index i0 along which the
    trace moves monotonically along its main direction (rejects spurious
    far-off-blaze solutions)."""
    n = len(xy)
    good = np.zeros(n, bool)
    d = np.diff(xy, axis=0)
    ax = int(np.argmax(np.nanmedian(np.abs(d), axis=0)))
    sgn = np.sign(np.nanmedian(d[:, ax]))
    step_ok = np.isfinite(d).all(axis=1) & (np.sign(d[:, ax]) == sgn)
    if not np.isfinite(xy[i0]).all():
        return good
    good[i0] = True
    i = i0
    while i > 0 and step_ok[i - 1]:
        i -= 1
        good[i] = True
    i = i0
    while i < n - 1 and step_ok[i]:
        i += 1
        good[i] = True
    return good


def _inside(xy, half):
    return (np.abs(xy[..., 0]) <= half[0]) & (np.abs(xy[..., 1]) <= half[1])


def build(
    sys: System,
    points: list[InputPoint],
    m_lam: float,
    half_size: tuple[float, float],
    ref: int = 0,
    core_mm: float | None = None,
    m_range: tuple[int, int] | None = None,
    n_samples: int = 25,
) -> Echellogram:
    """Trace an arm.

    m_lam: the echelle's m * lambda at the blaze [um] (e.g. from a design
        configuration: its order times its primary wavelength), used to
        guess each order's wavelengths.
    half_size: detector half-sizes [mm].
    ref: index of the reference point in ``points``.
    core_mm: fibre core (slit width) at the start surface, for the
        resolving power (geometric: lambda / (dispersion * projected width)).
    m_range: orders to try (inclusive); default: search outwards from the
        order whose blaze wavelength lands nearest the detector centre.
    """
    pref = [points[ref]]

    def scan(m):
        """Samples of the reference trace over +-w free spectral ranges,
        widened until the part on the detector ends inside the scan."""
        lam_c = m_lam / m
        w = 1.6
        while True:
            lam = lam_c * (1 + np.linspace(-w, w, 65) / m)
            xy = _positions(sys, pref, lam, m)[0]
            ok = _inside(xy, half_size) & np.all(np.isfinite(xy), axis=-1)
            ok &= _monotonic_run(xy, len(lam) // 2)
            if not (ok[0] or ok[-1]) or w >= 8.0:
                return lam, xy, ok
            w *= 1.5

    if m_range is None:
        found = []
        m0 = None
        # coarse search for one order on the chip
        for m in range(10, 1000):
            lam_c = m_lam / m
            if lam_c < 0.1:
                break
            xy = _positions(sys, pref, np.array([lam_c]), m)[0]
            if np.all(np.isfinite(xy)) and _inside(xy, half_size).all():
                m0 = m
                break
        if m0 is None:
            raise ValueError("no order lands on the detector")
        for step in (1, -1):
            m = m0 if step == 1 else m0 - 1
            misses = 0
            while m > 0 and misses < 2:
                if scan(m)[2].any():
                    found.append(m)
                    misses = 0
                else:
                    misses += 1
                m += step
        ms = sorted(found, reverse=True)
    else:
        ms = list(range(m_range[1], m_range[0] - 1, -1))

    # dispersion axis from the first order
    lam, xy, ok = scan(ms[len(ms) // 2])
    g = np.nanmedian(np.abs(np.diff(xy[ok], axis=0)), axis=0)
    disp_axis = int(np.argmax(g))
    cross_axis = 1 - disp_axis

    orders = []
    partial = []
    for m in ms:
        lam, xy, ok = scan(m)
        if not ok.any():
            continue
        d = xy[ok, disp_axis]
        if not (d.min() <= 0.0 <= d.max()):
            # only a corner of the order reaches the detector
            partial.append(m)
            continue
        lo, hi = _edges(sys, pref[0], m, lam, ok, half_size)
        lam_s = np.linspace(lo, hi, n_samples)
        xys = _positions(sys, points, lam_s, m)
        # centre: dispersion coordinate 0 on the reference trace
        d = xys[ref, :, disp_axis]
        lam_c = float(
            np.interp(0.0, d, lam_s) if d[0] < d[-1] else np.interp(0.0, d[::-1], lam_s[::-1])
        )
        lam_c = min(max(lam_c, lo), hi)
        h = 1e-5 * lam_c
        trio = _positions(sys, points, np.array([lam_c - h, lam_c, lam_c + h]), m)
        dxy = (trio[ref, 2] - trio[ref, 0]) / (2 * h)
        disp = float(np.hypot(*dxy))
        R = None
        if core_mm:
            R = _resolving_power(sys, points[ref], m, lam_c, dxy, core_mm)
        orders.append(
            OrderTrace(
                m=m,
                lam_lo=float(lo),
                lam_hi=float(hi),
                lam_centre=lam_c,
                lam=lam_s,
                xy=xys,
                dlam_dmm=1.0 / disp,
                resolving_power=R,
                cross_mm=trio[:, 1, cross_axis].copy(),
                complete=bool(_inside(trio[:, 1], half_size).all()),
            )
        )
    return Echellogram(points, ref, half_size, disp_axis, orders, partial)


def _edges(sys, p, m, lam, ok, half):
    """Wavelengths where the reference trace leaves the detector: regula
    falsi on the violated coordinate, between the coarse samples."""
    idx = np.flatnonzero(ok)
    i0, i1 = idx[0], idx[-1]

    def pos(lv):
        return _positions(sys, [p], np.array([lv]), m)[0, 0]

    def refine(a_in, b_out):
        xb = pos(b_out)
        if not np.all(np.isfinite(xb)):
            return a_in
        k = int(np.argmax(np.abs(xb) / np.asarray(half)))
        edge = np.sign(xb[k]) * half[k]

        def f(lv):
            return pos(lv)[k] - edge

        fa, fb = f(a_in), f(b_out)
        for _ in range(8):
            c = b_out - fb * (b_out - a_in) / (fb - fa)
            fc = f(c)
            if abs(fc) < 1e-6:
                return c
            if np.sign(fc) == np.sign(fa):
                a_in, fa = c, fc
            else:
                b_out, fb = c, fc
        return c

    lo = refine(lam[i0], lam[i0 - 1]) if i0 > 0 else lam[0]
    hi = refine(lam[i1], lam[i1 + 1]) if i1 < len(lam) - 1 else lam[-1]
    return (lo, hi) if lo < hi else (hi, lo)


def _resolving_power(sys, p, m, lam_c, dxy_dlam, core_mm):
    """lambda / (delta-lambda of a fibre of diameter ``core_mm``): the
    fibre's image extent along the dispersion direction, from the Jacobian
    of image position with respect to start-surface position."""
    e = dxy_dlam / np.hypot(*dxy_dlam)
    h = 1e-3
    pts = [
        InputPoint("", p.x_mm + h, p.y_mm),
        InputPoint("", p.x_mm - h, p.y_mm),
        InputPoint("", p.x_mm, p.y_mm + h),
        InputPoint("", p.x_mm, p.y_mm - h),
    ]
    xy = _positions(sys, pts, np.array([lam_c]), m)[:, 0, :]
    J = np.stack([(xy[0] - xy[1]) / (2 * h), (xy[2] - xy[3]) / (2 * h)], axis=1)
    width = core_mm * float(np.linalg.norm(J.T @ e))
    return float(lam_c * np.hypot(*dxy_dlam) / width)

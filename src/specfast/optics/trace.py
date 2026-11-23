"""A 3-D sequential ray tracer with Zemax rules.

Conventions (all checked against Zemax designs):

- Every surface has a global frame (origin, rotation whose columns are the
  local x, y, z axes). A coordinate break (``COORDBRK``) decenters by
  (PARM 1, PARM 2) and tilts about local x, y, z by PARM 3, 4, 5 [deg], in
  that order (intrinsic rotations), or in the reverse order when PARM 6 is
  non-zero; its thickness is then applied along the new local z. Mirrors do
  not flip frames: thicknesses change sign instead.
- Ignored surfaces are skipped, and so are their thicknesses and coordinate
  breaks (Zemax drops an ignored surface from the prescription).
- Indices are relative to air at the design's environment (air = 1), and
  wavelengths are the design's (air) wavelengths [um], as Zemax uses them.
- A grating (``DGRATING``, or a grating stand-in) has its lines along local
  x; it adds ``order * lambda * lines_per_um`` to the tangential wave-vector
  along local y (the Zemax sign). Reflective if its glass is ``MIRROR``.
- Encrypted black boxes are never read. Each ``BLACKBOX`` surface needs a
  stand-in, given by the user (:class:`StandIn`).

Surfaces supported: STANDARD (conic), EVENASPH, TOROIDAL (y-z profile with
conic and even terms, rotated about an axis parallel to y), DGRATING,
PARAXIAL (ideal lens), COORDBRK.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from specfast.optics.glass import GlassLibrary
from specfast.optics.zmx import Surface


class TraceError(ValueError):
    """A system the tracer cannot handle (unknown surface type, missing
    stand-in, ...)."""


@dataclass(frozen=True)
class StandIn:
    """A user-supplied replacement for an encrypted black-box surface (or
    any surface).

    kind:
      ``plane``      a dummy plane (no effect);
      ``grating``    a plane grating, lines along local x (``lines_per_um``,
                     ``order``), followed by ``glass`` (None = air,
                     "MIRROR" = reflective);
      ``ideal_lens`` a paraxial lens of focal length ``focal_mm``;
      ``camera``     an ideal camera of focal length ``focal_mm``, with radial
                     distortion ``k1``, ``k2`` in the direction tangents; the
                     trace stops here and the image coordinates are
                     ``f * (u, v) * (1 + k1 r^2 + k2 r^4)`` (u, v = dx/dz,
                     dy/dz in this surface's frame).
    """

    kind: str
    lines_per_um: float = 0.0
    order: float = 1.0
    glass: str | None = None
    focal_mm: float = 0.0
    k1: float = 0.0
    k2: float = 0.0


def _rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def build_frames(surfs: list[Surface]) -> list[tuple[np.ndarray, np.ndarray]]:
    """Global (origin, rotation) of every surface (see module docstring)."""
    org = np.zeros(3)
    R = np.eye(3)
    frames = []
    for s in surfs:
        if s.ignored:
            frames.append((org.copy(), R.copy()))
            continue
        if s.type == "COORDBRK":
            dx, dy = s.parm.get(1, 0.0), s.parm.get(2, 0.0)
            ax, ay, az = (np.radians(s.parm.get(k, 0.0)) for k in (3, 4, 5))
            if s.parm.get(6, 0.0) == 0:
                org = org + R @ np.array([dx, dy, 0.0])
                R = R @ _rx(ax) @ _ry(ay) @ _rz(az)
            else:
                R = R @ _rz(az) @ _ry(ay) @ _rx(ax)
                org = org + R @ np.array([dx, dy, 0.0])
        frames.append((org.copy(), R.copy()))
        if np.isfinite(s.thick):
            org = org + R @ np.array([0.0, 0.0, s.thick])
    return frames


# --------------------------------------------------------------- surfaces
def _sag_conic(c, k, r2):
    arg = np.maximum(1.0 - (1.0 + k) * c * c * r2, 0.0)
    return c * r2 / (1.0 + np.sqrt(arg))


def _even_terms(s: Surface, r2):
    out = np.zeros_like(r2)
    for p in range(1, 9):
        a = s.parm.get(p, 0.0)
        if a:
            out = out + a * r2**p
    return out


def _sag(s: Surface, x, y):
    """Surface sag z(x, y) in the local frame."""
    if s.type == "EVENASPH":
        r2 = x * x + y * y
        return _sag_conic(s.curv, s.conic, r2) + _even_terms(s, r2)
    if s.type == "TOROIDAL":
        y2 = y * y
        zy = _sag_conic(s.curv, s.conic, y2)
        for p in range(2, 9):  # PARM 2.. = y^2, y^4, ... coefficients
            a = s.parm.get(p, 0.0)
            if a:
                zy = zy + a * y2 ** (p - 1)
        R = s.parm.get(1, 0.0)
        if R == 0.0:
            return zy
        a = R - zy
        return R - np.where(a >= 0, 1.0, -1.0) * np.sqrt(np.maximum(a * a - x * x, 0.0))
    r2 = x * x + y * y
    return _sag_conic(s.curv, s.conic, r2)


def _quadric(p, d, c, k):
    """Exact intersection with a conic of curvature c, conic k (virtual
    intersections allowed, as in Zemax sequential mode)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        tpl = -p[:, 2] / d[:, 2]
    if c == 0.0:
        t = tpl
    else:
        kk = 1.0 + k
        A = c * (d[:, 0] ** 2 + d[:, 1] ** 2 + kk * d[:, 2] ** 2)
        B = 2 * c * (p[:, 0] * d[:, 0] + p[:, 1] * d[:, 1] + kk * p[:, 2] * d[:, 2]) - 2 * d[:, 2]
        C = c * (p[:, 0] ** 2 + p[:, 1] ** 2 + kk * p[:, 2] ** 2) - 2 * p[:, 2]
        disc = np.sqrt(np.maximum(B * B - 4 * A * C, 0.0))
        with np.errstate(divide="ignore", invalid="ignore"):
            q = -0.5 * (B + np.where(B >= 0, 1.0, -1.0) * disc)
            t1 = q / A
            t2 = C / q
        t = np.where(np.abs(t1 - tpl) < np.abs(t2 - tpl), t1, t2)
        t = np.where(np.abs(A) < 1e-14, -C / B, t)
    return t


def intersect(s: Surface, p, d):
    """Intersection points and unit normals (pointing towards -z at the
    vertex) of local rays p + t d with surface ``s``."""
    if s.type in ("STANDARD", "DGRATING", "COORDBRK", "PARAXIAL", "BLACKBOX"):
        c = s.curv if s.type in ("STANDARD", "DGRATING") else 0.0
        k = s.conic if s.type == "STANDARD" else 0.0
        t = _quadric(p, d, c, k)
        q = p + t[:, None] * d
        if c == 0.0:
            n = np.tile([0.0, 0.0, -1.0], (len(p), 1))
        else:
            n = np.stack([c * q[:, 0], c * q[:, 1], c * (1 + k) * q[:, 2] - 1.0], axis=1)
            n /= np.linalg.norm(n, axis=1)[:, None]
        return q, n
    if s.type not in ("EVENASPH", "TOROIDAL"):
        raise TraceError(f"surface {s.index}: type {s.type} is not supported")
    # start from the base conic, then Newton on f(t) = sag(x, y) - z
    t = _quadric(p, d, s.curv, s.conic if s.type == "EVENASPH" else 0.0)
    t = np.where(np.isfinite(t), t, -p[:, 2] / d[:, 2])
    h = 1e-6
    for _ in range(30):
        q = p + t[:, None] * d
        f = _sag(s, q[:, 0], q[:, 1]) - q[:, 2]
        gx = (_sag(s, q[:, 0] + h, q[:, 1]) - _sag(s, q[:, 0] - h, q[:, 1])) / (2 * h)
        gy = (_sag(s, q[:, 0], q[:, 1] + h) - _sag(s, q[:, 0], q[:, 1] - h)) / (2 * h)
        df = gx * d[:, 0] + gy * d[:, 1] - d[:, 2]
        step = f / df
        t = t - step
        if not (np.abs(step) >= 1e-10).any():
            break
    q = p + t[:, None] * d
    gx = (_sag(s, q[:, 0] + h, q[:, 1]) - _sag(s, q[:, 0] - h, q[:, 1])) / (2 * h)
    gy = (_sag(s, q[:, 0], q[:, 1] + h) - _sag(s, q[:, 0], q[:, 1] - h)) / (2 * h)
    n = np.stack([gx, gy, -np.ones_like(gx)], axis=1)
    n /= np.linalg.norm(n, axis=1)[:, None]
    return q, n


def refract(d, n_hat, n1, n2):
    cosi = np.sum(d * n_hat, axis=1)
    nh = n_hat * np.where(cosi >= 0, 1.0, -1.0)[:, None]
    cosi = np.abs(cosi)
    mu = n1 / n2
    k = 1 - mu**2 * (1 - cosi**2)
    with np.errstate(invalid="ignore"):
        return mu[:, None] * d + (np.sqrt(np.where(k >= 0, k, np.nan)) - mu * cosi)[:, None] * nh


def reflect(d, n_hat):
    return d - 2 * np.sum(d * n_hat, axis=1)[:, None] * n_hat


def diffract(d, n1, n2, order, lam_um, lines_per_um, reflective):
    """Plane grating in the local z = 0 plane, lines along local x."""
    kx = n1 * d[:, 0]
    ky = n1 * d[:, 1] + order * lam_um * lines_per_um
    kz2 = n2**2 - kx**2 - ky**2
    with np.errstate(invalid="ignore"):
        kz = np.sqrt(np.where(kz2 > 0, kz2, np.nan))
    sgn = np.where(d[:, 2] >= 0, 1.0, -1.0)
    kz = -sgn * kz if reflective else sgn * kz
    out = np.stack([kx, ky, kz], axis=1)
    return out / np.linalg.norm(out, axis=1)[:, None]


# --------------------------------------------------------------- system
@dataclass
class System:
    """One configuration of a sequential design, ready to trace."""

    surfaces: list[Surface]
    glasses: GlassLibrary
    standins: dict[int, StandIn] = field(default_factory=dict)
    #: Surface the rays start from (the object, or a stand-in object plane).
    start: int = 0
    #: Surface the rays are aimed at (default: the stop).
    aim_surface: int | None = None
    #: Last surface traced (default: the last surface).
    image: int | None = None
    #: The echelle: the DGRATING whose order ``trace(order=...)`` sets.
    echelle: int | None = None

    def __post_init__(self) -> None:
        self.frames = build_frames(self.surfaces)
        if self.aim_surface is None:
            self.aim_surface = next(s.index for s in self.surfaces if s.stop)
        if self.image is None:
            self.image = len(self.surfaces) - 1
        for s in self.surfaces[self.start + 1 : self.image + 1]:
            if s.ignored or s.type == "COORDBRK":
                continue
            if s.type == "BLACKBOX" and s.index not in self.standins:
                raise TraceError(
                    f"surface {s.index} is an encrypted black box: give a stand-in "
                    "(it is never decrypted)"
                )

    # -- media
    def index(self, glass: str | None, lam_um: np.ndarray) -> np.ndarray:
        if glass is None or glass.upper() in ("", "AIR", "MIRROR"):
            return np.ones_like(lam_um)
        return np.asarray(self.glasses[glass].index(lam_um), dtype=float)

    def _start_medium(self) -> str | None:
        g = self.surfaces[self.start].glass
        return None if g in (None, "MIRROR") else g

    # -- tracing
    def trace(self, P, D, lam_um, order=None, stop_at=None):
        """Trace global rays P, D (N x 3) leaving surface ``self.start`` to
        surface ``stop_at`` (default: the image). ``order``, when given,
        replaces the diffraction order of the echelle surface (keeping the
        design's sign).

        Returns (P, D) in the local frame of ``stop_at``, or, at a ``camera``
        stand-in, (image xy [mm] as an N x 2 array, None).
        """
        stop_at = self.image if stop_at is None else stop_at
        n_ray = len(P)
        lam = np.broadcast_to(np.asarray(lam_um, float), (n_ray,)).copy()
        medium = self._start_medium()
        n_cur = self.index(medium, lam)
        p_loc = d_loc = None
        for i in range(self.start + 1, stop_at + 1):
            s = self.surfaces[i]
            if s.ignored or s.type == "COORDBRK":
                continue
            org, R = self.frames[i]
            p, d = (P - org) @ R, D @ R
            st = self.standins.get(i)
            if st is not None:
                q, nh = intersect(_PLANE, p, d)
                if st.kind == "camera":
                    u, v = d[:, 0] / d[:, 2], d[:, 1] / d[:, 2]
                    r2 = u * u + v * v
                    fac = st.focal_mm * (1 + st.k1 * r2 + st.k2 * r2 * r2)
                    return np.stack([u * fac, v * fac], axis=1), None
                if st.kind == "grating":
                    refl = st.glass == "MIRROR"
                    new = medium if refl else st.glass
                    n_new = n_cur if refl else self.index(new, lam)
                    d = diffract(d, n_cur, n_new, st.order, lam, st.lines_per_um, refl)
                    n_cur, medium = n_new, new
                elif st.kind == "ideal_lens":
                    d = _paraxial(q, d, st.focal_mm, n_cur)
                elif st.kind != "plane":
                    raise TraceError(f"stand-in kind {st.kind!r} unknown")
            else:
                q, nh = intersect(s, p, d)
                if s.type == "DGRATING":
                    refl = s.glass == "MIRROR"
                    new = medium if refl else s.glass
                    n_new = n_cur if refl else self.index(new, lam)
                    m = s.parm.get(2, 0.0)
                    if order is not None and i == self.echelle:
                        m = (-1.0 if m < 0 else 1.0) * np.asarray(order, float)
                    d = diffract(d, n_cur, n_new, m, lam, s.parm.get(1, 0.0), refl)
                    n_cur, medium = n_new, new
                elif s.type == "PARAXIAL":
                    d = _paraxial(q, d, s.parm.get(1, 0.0), n_cur)
                elif s.glass == "MIRROR":
                    d = reflect(d, nh)
                else:
                    new = s.glass
                    n_new = self.index(new, lam)
                    if not np.array_equal(n_new, n_cur):
                        d = refract(d, nh, n_cur, n_new)
                    n_cur, medium = n_new, new
            p_loc, d_loc = q, d
            P, D = q @ R.T + org, d @ R.T
        return p_loc, d_loc

    def launch(self, x_mm, y_mm):
        """Global points on the start surface at local (x, y)."""
        org, R = self.frames[self.start]
        x = np.atleast_1d(np.asarray(x_mm, float))
        y = np.broadcast_to(np.asarray(y_mm, float), x.shape)
        loc = np.stack([x, y, np.zeros_like(x)], axis=1)
        return loc @ R.T + org

    def aim(self, P0, lam_um, order=None, target=(0.0, 0.0), tol=1e-7):
        """Directions from start points P0 so each ray (with its own
        wavelength) hits the aim surface at local (x, y) = target. Newton
        iteration on the direction tangents, vectorised over rays."""
        org, R = self.frames[self.start]
        n = len(P0)
        lam = np.broadcast_to(np.asarray(lam_um, float), (n,))
        uv = np.zeros((n, 2))
        tgt = np.asarray(target, float)

        def dirs(uv):
            loc = np.stack([uv[:, 0], uv[:, 1], np.ones(n)], axis=1)
            loc /= np.linalg.norm(loc, axis=1)[:, None]
            return loc @ R.T

        def hit(uv):
            p, _ = self.trace(P0, dirs(uv), lam, order, stop_at=self.aim_surface)
            return p[:, :2]

        for _ in range(25):
            h0 = hit(uv)
            err = h0 - tgt
            if not (np.abs(err) >= tol).any():
                break
            eps = 1e-6
            J = np.empty((n, 2, 2))
            for j in range(2):
                du = uv.copy()
                du[:, j] += eps
                J[:, :, j] = (hit(du) - h0) / eps
            with np.errstate(invalid="ignore"):
                bad = ~np.isfinite(J).all(axis=(1, 2)) | (
                    np.abs(np.linalg.det(np.nan_to_num(J))) < 1e-300
                )
            J[bad] = np.eye(2)
            uv = uv - np.linalg.solve(J, np.nan_to_num(err)[:, :, None])[:, :, 0]
            uv[bad] = np.nan
        # rays that did not converge (vignetted, evanescent, ...) are NaN
        err = hit(uv) - tgt
        failed = ~(np.abs(err) < 1e3 * tol).all(axis=1)
        out = dirs(uv)
        out[failed] = np.nan
        return out

    def image_xy(self, x_mm, y_mm, lam_um, order=None):
        """Chief-ray image positions [mm] (N x 2) on the image surface (or
        the camera stand-in) for start-surface points (x, y) at ``lam_um``."""
        x = np.atleast_1d(np.asarray(x_mm, float))
        lam = np.atleast_1d(np.asarray(lam_um, float))
        n = max(len(x), len(lam))
        x = np.broadcast_to(x, (n,))
        y = np.broadcast_to(np.asarray(y_mm, float), (n,))
        lam = np.broadcast_to(lam, (n,))
        if order is not None:
            order = np.broadcast_to(np.asarray(order, float), (n,))
        P0 = self.launch(x, y)
        D0 = self.aim(P0, lam, order)
        p, _ = self.trace(P0, D0, lam, order)
        return p[:, :2]


_PLANE = Surface(-1)


def _paraxial(q, d, f, n):
    """Ideal lens at the local z = 0 plane: direction tangents change by
    -(x, y) / f."""
    u = d[:, 0] / d[:, 2] - q[:, 0] / f
    v = d[:, 1] / d[:, 2] - q[:, 1] / f
    out = np.stack([u, v, np.ones_like(u)], axis=1) * np.where(d[:, 2] >= 0, 1.0, -1.0)[:, None]
    return out / np.linalg.norm(out, axis=1)[:, None]

"""Calibration inputs of a Doppler run, in plain documented formats.

All are ``.npz`` files (NumPy archives) except the correction tables (CSV).
Wavelengths are vacuum Angstrom; MJD are UTC; channel names are the
instrument's (e.g. ``T1``); order indices are the product's.

=====================  ======================================================
file                   arrays
=====================  ======================================================
iodine atlas           ``wave_vac``, ``transmission``
telluric atlas         ``wave_vac``, ``transmission`` (treated as water), and
                       optionally ``transmission_dry`` (scaled by airmass)
stellar template       ``wave_vac`` (stellar rest frame), ``flux`` (normalized)
LSF map (GH, per era)  ``era_starts`` (MJD; era i from era_starts[i]),
                       ``era``, ``channel``, ``order``, ``s0_kms``, ``g``,
                       ``q``, ``h3``, ``h3g``, ``h4`` (one row per era,
                       channel, order)
LSF sigma (Gaussian)   ``channel``, ``order``, ``sigma_kms``
LSF change basis       ``x_kms`` (kernel velocity grid), ``group_last_order``
                       (last order index of each order group), ``P<g>``
                       (nk, len(x_kms)) zero-sum kernel perturbations per
                       group (one unit = one standard deviation)
optics curves          ``era_starts``, ``era``, ``channel``, ``order``,
                       ``coeffs`` (n, ncoef; polynomial in
                       (p - x_center) / x_scale, lowest first),
                       ``x_center``, ``x_scale``
distortion D(p)        ``era_starts``, ``D`` (n_era, n_columns) [px]
detector map           ``channel``, ``order``, ``dx`` (n, npix + 1),
                       ``response`` (n, npix)
=====================  ======================================================

An era index is the last ``era_starts`` entry at or before the MJD (0
before the first).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

__all__ = [
    "Atlas",
    "Corrections",
    "Distortion",
    "LsfBasis",
    "LsfMap",
    "LsfSigma",
    "OpticsCurves",
    "era_index",
    "load_atlas",
]


def era_index(starts: np.ndarray, mjd: float) -> int:
    return max(int(np.searchsorted(np.asarray(starts, float), mjd, side="right")) - 1, 0)


def _str(a) -> np.ndarray:
    return np.asarray(a).astype(str)


@dataclass(frozen=True)
class Atlas:
    lnlam: np.ndarray
    transmission: np.ndarray
    transmission_dry: np.ndarray | None = None


def load_atlas(path: str | Path) -> Atlas:
    z = np.load(path)
    w = np.asarray(z["wave_vac"], float)
    t = np.asarray(z["transmission"], float)
    o = np.argsort(w)
    dry = np.asarray(z["transmission_dry"], float)[o] if "transmission_dry" in z.files else None
    return Atlas(lnlam=np.log(w[o]), transmission=t[o], transmission_dry=dry)


class LsfMap:
    def __init__(self, path):
        z = np.load(path)
        self.starts = np.asarray(z["era_starts"], float)
        self.rows = {}
        for i in range(len(z["era"])):
            key = (int(z["era"][i]), str(_str(z["channel"])[i]), int(z["order"][i]))
            self.rows[key] = np.array(
                [
                    float(z["s0_kms"][i]) * 1e3,
                    float(z["g"][i]),
                    float(z["q"][i]),
                    float(z["h3"][i]),
                    float(z["h3g"][i]),
                    float(z["h4"][i]),
                ]
            )

    def era(self, mjd: float) -> int:
        return era_index(self.starts, mjd)

    def get(self, mjd: float, channel: str, order: int) -> np.ndarray | None:
        return self.rows.get((self.era(mjd), channel, order))


class LsfSigma:
    def __init__(self, path):
        z = np.load(path)
        self.rows = {
            (str(c), int(o)): float(s) * 1e3
            for c, o, s in zip(_str(z["channel"]), z["order"], z["sigma_kms"], strict=True)
        }

    def get(self, channel: str, order: int) -> float | None:
        return self.rows.get((channel, order))


class LsfBasis:
    def __init__(self, path):
        z = np.load(path)
        self.x_kms = np.asarray(z["x_kms"], float)
        self.last = np.asarray(z["group_last_order"], int)
        self.P = [np.asarray(z[f"P{g}"], float) for g in range(len(self.last))]

    @property
    def step_mps(self) -> float:
        return float(self.x_kms[1] - self.x_kms[0]) * 1e3

    @property
    def nk(self) -> int:
        return int(self.P[0].shape[0])

    def for_order(self, order: int) -> np.ndarray:
        g = int(np.searchsorted(self.last, order, side="left"))
        return self.P[min(g, len(self.P) - 1)]


class OpticsCurves:
    def __init__(self, path):
        z = np.load(path)
        self.starts = np.asarray(z["era_starts"], float)
        self.rows = {}
        for i in range(len(z["era"])):
            key = (int(z["era"][i]), str(_str(z["channel"])[i]), int(z["order"][i]))
            self.rows[key] = (
                np.asarray(z["coeffs"][i], float),
                float(
                    np.asarray(z["x_center"]).reshape(-1)[i if np.size(z["x_center"]) > 1 else 0]
                ),
                float(np.asarray(z["x_scale"]).reshape(-1)[i if np.size(z["x_scale"]) > 1 else 0]),
            )

    def era(self, mjd: float) -> int:
        return era_index(self.starts, mjd)

    def get(self, mjd: float, channel: str, order: int):
        return self.rows.get((self.era(mjd), channel, order))


class Distortion:
    def __init__(self, path):
        z = np.load(path)
        self.starts = np.asarray(z["era_starts"], float)
        self.D = np.asarray(z["D"], float)

    def get(self, mjd: float) -> np.ndarray:
        return self.D[min(era_index(self.starts, mjd), len(self.D) - 1)]


class Corrections:
    """{(frame name stem, channel index): value} from a CSV correction table."""

    def __init__(self, path, column: str, channels: tuple[str, ...]):
        self.values = {}
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                if "tel" in row and row["tel"] != "":
                    ch = int(float(row["tel"]))
                else:
                    ch = channels.index(row["channel"])
                try:
                    v = float(row[column])
                except (TypeError, ValueError):
                    continue
                if np.isfinite(v):
                    self.values[(stem(row["file"]), ch)] = v

    def get(self, name: str, ch: int) -> float:
        return self.values.get((stem(name), ch), 0.0)


def stem(name: str) -> str:
    """Frame stem: the raw frame name without product suffixes."""
    n = Path(str(name).strip()).name
    for suf in (".x2.proc.fits", ".proc.fits", ".fits", ".x2"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n

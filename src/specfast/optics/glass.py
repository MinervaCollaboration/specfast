"""Glass catalogues in Zemax ``.agf`` format.

Each glass is an ``NM name formula ...`` line followed by ``CD`` (dispersion
coefficients) and other lines. Indices are relative to air at the catalogue's
reference conditions, with the wavelength in um; the tracer works in that
relative system (air = 1), as Zemax does at standard conditions. Thermal
(``TD``) terms are not applied.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Formula numbers as written in .agf files.
FORMULAS = {
    1: "Schott",
    2: "Sellmeier 1",
    3: "Herzberger",
    5: "Conrady",
    6: "Sellmeier 3",
    7: "Handbook 1",
    8: "Handbook 2",
    9: "Sellmeier 4",
    10: "Extended",
    11: "Sellmeier 5",
    12: "Extended 2",
}


class GlassError(KeyError):
    """An unknown glass or unsupported dispersion formula."""


@dataclass(frozen=True)
class Glass:
    name: str
    formula: int
    coeffs: tuple[float, ...]

    def index(self, lam_um):
        """Refractive index (relative to air) at wavelength(s) ``lam_um``."""
        lam = np.asarray(lam_um, dtype=float)
        c = list(self.coeffs) + [0.0] * (12 - len(self.coeffs))
        L2 = lam * lam
        f = self.formula
        if f == 1:
            n2 = c[0] + c[1] * L2 + c[2] / L2 + c[3] / L2**2 + c[4] / L2**3 + c[5] / L2**4
        elif f in (2, 6, 11):
            nterm = {2: 3, 6: 4, 11: 5}[f]
            n2 = 1.0 + sum(c[2 * k] * L2 / (L2 - c[2 * k + 1]) for k in range(nterm))
        elif f == 3:
            L = 1.0 / (L2 - 0.028)
            return c[0] + c[1] * L + c[2] * L * L + c[3] * L2 + c[4] * L2**2 + c[5] * L2**3
        elif f == 5:
            return c[0] + c[1] / lam + c[2] / lam**3.5
        elif f == 7:
            n2 = c[0] + c[1] / (L2 - c[2]) - c[3] * L2
        elif f == 8:
            n2 = c[0] + c[1] * L2 / (L2 - c[2]) - c[3] * L2
        elif f == 9:
            n2 = c[0] + c[1] * L2 / (L2 - c[2]) + c[3] * L2 / (L2 - c[4])
        elif f == 10:
            n2 = c[0] + c[1] * L2 + sum(c[k] / L2 ** (k - 1) for k in range(2, 8))
        elif f == 12:
            n2 = (
                c[0]
                + c[1] * L2
                + sum(c[k] / L2 ** (k - 1) for k in range(2, 6))
                + c[6] * L2**2
                + c[7] * L2**3
            )
        else:
            raise GlassError(f"{self.name}: dispersion formula {f} is not supported")
        return np.sqrt(n2)


def parse_agf(text: str) -> dict[str, Glass]:
    """Glasses in one ``.agf`` catalogue, keyed by upper-case name."""
    out: dict[str, Glass] = {}
    name = None
    formula = 0
    for line in text.splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "NM" and len(tok) > 2:
            name, formula = tok[1], int(float(tok[2]))
        elif tok[0] == "CD" and name is not None:
            out[name.upper()] = Glass(name, formula, tuple(float(t) for t in tok[1:]))
            name = None
    return out


class GlassLibrary:
    """Several catalogues; first match wins."""

    def __init__(self, catalogs: list[dict[str, Glass]] | None = None):
        self._cats = list(catalogs or [])

    def add(self, catalog: dict[str, Glass]) -> None:
        self._cats.append(catalog)

    def __contains__(self, name: str) -> bool:
        return any(name.upper() in c for c in self._cats)

    def __getitem__(self, name: str) -> Glass:
        for c in self._cats:
            g = c.get(name.upper())
            if g is not None:
                return g
        raise GlassError(f"glass {name!r} is not in any loaded catalogue")

"""Stage 2, Doppler: the forward model and its components (DESIGN.md).

- :mod:`~specfast.doppler.components`: the component interface (scopes,
  frames, parameter specs) and the registry;
- :mod:`~specfast.doppler.grid`: the fine ln(lambda) grid, LSF convolution
  and pixel integration;
- :mod:`~specfast.doppler.library`: first component implementations;
- :mod:`~specfast.doppler.model`: one fit block's forward model and the
  flat parameter-vector layout for an external solver.

Not here yet: the fitting engine (problem assembly across blocks, per-segment
velocities, block-sparse Jacobian), tellurics, templates other than a
tabulated one.
"""

from specfast.doppler import library  # noqa: F401  (registers the components)
from specfast.doppler.components import (
    REGISTRY,
    Component,
    ExposureContext,
    Frame,
    ParameterSpec,
    Scope,
    lookup,
    register,
)
from specfast.doppler.grid import LnGrid
from specfast.doppler.library import (
    GaussianLSF,
    IodineCell,
    NoGasCell,
    PolynomialContinuum,
    PolynomialWavelength,
    StarTemplate,
)
from specfast.doppler.model import ForwardModel, ParameterLayout

__all__ = [
    "REGISTRY",
    "Component",
    "ExposureContext",
    "ForwardModel",
    "Frame",
    "GaussianLSF",
    "IodineCell",
    "LnGrid",
    "NoGasCell",
    "ParameterLayout",
    "ParameterSpec",
    "PolynomialContinuum",
    "PolynomialWavelength",
    "Scope",
    "StarTemplate",
    "lookup",
    "register",
]

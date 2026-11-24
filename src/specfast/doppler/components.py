"""The component interface (DESIGN.md, "Components").

A component is one factor of the forward model. It

- declares its parameters (:class:`ParameterSpec`), each with a **scope**
  (:class:`Scope`: global, era, night, exposure, channel, order, segment, or
  a product such as ``CHANNEL | ORDER``) saying how the parameter is shared
  across fit blocks;
- declares the **frame** (:class:`Frame`) it lives in;
- evaluates as a **pure function** ``evaluate(params, coords, ctx)`` of its
  parameter arrays, the coordinates it is asked for, the exposure context
  and its own immutable static data (atlases, templates). No I/O, no
  mutable state, plain NumPy array operations only (no scipy, no
  ``interp1d``), so the same code can later run under JAX or PyTensor.

What ``coords`` means depends on the component's ``kind``:

=============  ======================  =====================================
kind           coords                  returns
=============  ======================  =====================================
wavelength     pixel positions [px]    vacuum wavelength [Angstrom]
continuum      pixel positions [px]    multiplicative continuum
spectrum       fine ln(lambda) grid    multiplicative factor on the grid
lsf            the fine grid           a normalized convolution kernel
detector       pixel positions [px]    per-pixel response (and edge offsets)
=============  ======================  =====================================

Spectrum components with a learned static correction (iodine, tellurics)
also implement ``learned_terms(params, ctx)``: a tuple of
``(parameter name, node LnGrid, scale)``, each term adding
``scale * interp(nodes)`` to the component's optical depth. The template
solver uses it to fit those corrections.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable

import numpy as np


class Scope(enum.Flag):
    """How a parameter is shared. Combine with ``|`` (e.g. one value per
    channel and order: ``Scope.CHANNEL | Scope.ORDER``)."""

    GLOBAL = 0
    ERA = enum.auto()
    NIGHT = enum.auto()
    EXPOSURE = enum.auto()
    CHANNEL = enum.auto()
    ORDER = enum.auto()
    SEGMENT = enum.auto()


class Frame(enum.Enum):
    """The frame a component is defined in."""

    PIXEL = "pixel"
    OBSERVED = "observed"
    BARYCENTRIC = "barycentric"
    STELLAR_REST = "stellar_rest"


@dataclass(frozen=True)
class ParameterSpec:
    """One declared parameter (an array of ``size`` values)."""

    name: str
    size: int
    scope: Scope
    unit: str
    doc: str = ""
    lower: float = -np.inf
    upper: float = np.inf
    #: Frozen calibration (e.g. the B-star LSF width): never fitted by default.
    fixed: bool = False


@dataclass(frozen=True)
class ExposureContext:
    """Per-exposure static inputs (known, not fitted)."""

    #: Barycentric correction z_B of the exposure (conventions module).
    z_bary: float = 0.0
    #: Airmass of the exposure (scales the dry telluric optical depth).
    airmass: float = 1.0


Params = Mapping[str, np.ndarray]


@runtime_checkable
class Component(Protocol):
    """The interface every component implements."""

    kind: ClassVar[str]
    frame: ClassVar[Frame]
    #: Instance name: the parameter namespace in a model.
    name: str

    def parameters(self) -> tuple[ParameterSpec, ...]: ...

    def evaluate(self, params: Params, coords: Any, ctx: ExposureContext) -> np.ndarray: ...


# ---------------------------------------------------------------------------
# registry: kind -> implementation name -> class (used to build models from
# a run config, e.g. doppler.reference.model: iodine)
# ---------------------------------------------------------------------------
REGISTRY: dict[str, dict[str, type]] = {}


def register(kind: str, name: str) -> Callable[[type], type]:
    """Class decorator: register an implementation under (kind, name)."""

    def deco(cls: type) -> type:
        impls = REGISTRY.setdefault(kind, {})
        if name in impls:
            raise ValueError(f"component {kind}/{name} registered twice")
        impls[name] = cls
        return cls

    return deco


def lookup(kind: str, name: str) -> type:
    """The registered class for (kind, name)."""
    try:
        return REGISTRY[kind][name]
    except KeyError:
        known = {k: sorted(v) for k, v in REGISTRY.items()}
        raise KeyError(f"no component {kind}/{name}; registered: {known}") from None


def frozen_array(a: Any, dtype: Any = np.float64) -> np.ndarray:
    """A read-only copy, for a component's static data."""
    out = np.array(a, dtype=dtype, copy=True)
    out.setflags(write=False)
    return out

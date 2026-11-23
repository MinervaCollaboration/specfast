"""Stage 1, extraction: raw frame + calibration products -> ExtractedSpectrum.

Interface only. The recipe is fixed by DESIGN.md, "Stage 1: extraction"
(settled by the extract2 pilot, FINDINGS.md 2026-11-22):

- fit all traces of a column simultaneously, with an empirical profile per
  trace (fibre flats where they exist, else stacked bright frames; pick the
  source per era by held-out chi2);
- a 2D scattered-light model;
- per-exposure trace re-centring (global shift + tilt, then per trace);
- variance from the model, never zero a low-flux window, no count floor:
  dark traces are flagged (``Mask.DARK_TRACE``) and kept;
- calibrations: a long-term stacked bias (or overscan only), no darks, no
  nightly slit flats, optionally a multi-night stacked pixel flat;
- reference channels (comb, etalon, ThAr) are extracted like any other.

Arrays here are in detector orientation (row = cross-dispersion,
column = dispersion) after the instrument's raw-frame flip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from specfast.config import RunConfig
from specfast.instrument import Instrument
from specfast.products import ExtractedSpectrum
from specfast.provenance import Provenance

_TODO = "not implemented yet: see DESIGN.md, 'Stage 1: extraction'"


@dataclass(frozen=True)
class StackedBias:
    """Long-term stacked bias structure of one arm's detector."""

    arm: str
    #: Bias structure after subtracting each frame's overscan level [ADU].
    structure: np.ndarray
    #: Read noise from frame differences [e-].
    read_noise_e: float
    n_frames: int
    provenance: Provenance


@dataclass(frozen=True)
class TraceSet:
    """Reference trace centres and widths for one arm."""

    arm: str
    #: (channel, order) labels of each trace, in cross-dispersion order.
    labels: tuple[tuple[str, int], ...]
    #: Trace centre row per (trace, column) [px].
    centre: np.ndarray
    #: Reference cross-dispersion width per (trace, column) [px].
    width: np.ndarray
    provenance: Provenance


@dataclass(frozen=True)
class ProfileSet:
    """Empirical cross-dispersion profiles per trace."""

    arm: str
    #: "fibre_flat", "stacked_frames" or "gaussian".
    source: str
    #: Offset grid u [px] the profiles are tabulated on.
    u_grid: np.ndarray
    #: Column nodes the profiles are tabulated at [px].
    column_nodes: np.ndarray
    #: Unit-integral profiles, shaped (trace, node, u).
    table: np.ndarray
    provenance: Provenance


@dataclass(frozen=True)
class ScatteredLightModel:
    """Settings of the smooth 2D background fitted per exposure."""

    #: Spline knot spacing (rows, columns) [px].
    knot_spacing: tuple[float, float] = (128.0, 128.0)


@dataclass(frozen=True)
class PixelFlat:
    """Optional multi-night stacked pixel-to-pixel flat."""

    arm: str
    #: Pixel response (1 = nominal).
    response: np.ndarray
    #: Fractional per-pixel error of the response.
    error: np.ndarray
    provenance: Provenance


@dataclass(frozen=True)
class ExtractionCalibrations:
    """Every calibration product the extraction of one arm needs."""

    bias: StackedBias
    traces: TraceSet
    profiles: ProfileSet
    scattered_light: ScatteredLightModel = field(default_factory=ScatteredLightModel)
    pixel_flat: PixelFlat | None = None


def stack_bias(paths: list[Path], instrument: Instrument, arm: str) -> StackedBias:
    """Long-term stacked bias from many bias frames."""
    raise NotImplementedError(_TODO)


def find_traces(frames: list[Path], instrument: Instrument, arm: str) -> TraceSet:
    """Locate every trace (channel x order) on bright or flat frames."""
    raise NotImplementedError(_TODO)


def build_profiles(
    frames: list[Path], calib_bias: StackedBias, traces: TraceSet, source: str
) -> ProfileSet:
    """Empirical per-trace profiles from fibre flats or stacked bright frames."""
    raise NotImplementedError(_TODO)


def extract_frame(
    raw: Path,
    instrument: Instrument,
    calibrations: dict[str, ExtractionCalibrations],
    config: RunConfig,
) -> ExtractedSpectrum:
    """Extract one raw frame; ``calibrations`` maps arm name -> products."""
    raise NotImplementedError(_TODO)

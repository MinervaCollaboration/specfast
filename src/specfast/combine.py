"""Combination: per-segment velocities -> per-exposure RVs (interface only).

DESIGN.md, "Combination": a joint solve of

    v_(e, s) = RV_e + O_(group, era) + noise,
    sigma^2  = beta^2 sigma_i^2 + s^2      (beta < 1 allowed),

with the offsets O marginalized (REML) and their uncertainty propagated
into the RV covariance; a known signal (an orbit) can be solved jointly.
Groups are e.g. (channel, order, segment); eras come from the instrument
description (instrument-wide and per channel) or the run config.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_TODO = "not implemented yet: see DESIGN.md, 'Combination'"


@dataclass(frozen=True)
class SegmentVelocities:
    """Every segment velocity of a set of exposures, long format."""

    #: Exposure index per measurement.
    exposure: np.ndarray
    #: Offset-group label per measurement (e.g. "T2/o07/s1").
    group: np.ndarray
    #: Era label per measurement.
    era: np.ndarray
    #: Velocity [m/s] and formal uncertainty [m/s].
    velocity: np.ndarray
    sigma: np.ndarray


@dataclass(frozen=True)
class CombinedVelocities:
    """Per-exposure RVs [m/s] with their full covariance [m^2/s^2]."""

    rv: np.ndarray
    covariance: np.ndarray
    #: Fitted error-model scale and jitter [m/s].
    beta: float
    jitter: float


def combine(segments: SegmentVelocities) -> CombinedVelocities:
    """Joint offset / error-model solve."""
    raise NotImplementedError(_TODO)

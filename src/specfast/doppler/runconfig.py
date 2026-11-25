"""Configuration of a Doppler run on extracted spectra (``specfast-doppler``).

One YAML file, validated strictly like :mod:`specfast.config` (unknown keys,
missing required keys and wrong types are errors; nothing comes from the
environment). Data locations are written out in the file, which belongs to
the user, not to this repository.

Calibration inputs are plain files in documented formats
(:mod:`specfast.doppler.calib`); every one is hashed into the provenance.
Every model component has a switch, so a run can be the full joint model
or any ablation of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from specfast.config import ConfigError, build_dataclass

RUN_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ManifestConfig:
    """A tab-separated manifest of extracted frames (no header line)."""

    path: str
    #: Directory the manifest's relative product paths are under.
    root: str
    #: 0-based columns of the frame name, status and product path.
    name_column: int = 0
    status_column: int = 5
    path_column: int = 8
    ok_status: str = "ok"


@dataclass(frozen=True)
class InputsConfig:
    #: Product reader: ``proc`` (KiwiSpec legacy / extract2 ``.proc.fits``).
    reader: Literal["proc"] = "proc"
    manifest: ManifestConfig | None = None
    #: Alternatively, a directory searched for ``*<suffix>`` files.
    directory: str | None = None
    suffix: str = ".proc.fits"
    #: Diagnostics file next to each product (suffix replacing ``suffix``);
    #: None = none.
    diag_suffix: str | None = None
    #: Keep frames whose name contains this string (e.g. the target name).
    name_contains: str | None = None
    #: Process at most this many frames (testing); None = all.
    limit: int | None = None
    #: Only frames whose UTC date is within [first_date, last_date].
    first_date: str | None = None
    last_date: str | None = None
    #: Explicit frame-name list file (one name per line) restricting the run.
    frame_list: str | None = None


@dataclass(frozen=True)
class StarConfig:
    """Catalogue astrometry: only for the provisional barycentric correction
    (placing exposures in the star frame) and the starting velocity. Never
    enters the released raw redshift."""

    name: str
    ra_deg: float
    dec_deg: float
    pmra_masyr: float = 0.0
    pmdec_masyr: float = 0.0
    parallax_mas: float = 0.0
    #: Systemic velocity [km/s] relative to the template (start value).
    rv_kms: float = 0.0
    #: Catalogue epoch of the position (Julian year).
    epoch_jyear: float = 2000.0


@dataclass(frozen=True)
class CorrectionConfig:
    """A per-(frame, channel) velocity correction table (CSV with columns
    ``file``, ``tel`` (0-based channel index) or ``channel``, and the value
    column), recorded with the outputs and applied to the corrected column,
    never to the raw redshift."""

    name: str
    path: str
    column: str


@dataclass(frozen=True)
class CalibrationsConfig:
    #: Stellar template (prior in modify mode).
    template: str
    iodine_atlas: str | None = None
    telluric_atlas: str | None = None
    #: Gauss-Hermite per-era map; Gaussian frozen-sigma table (fallback).
    lsf_map: str | None = None
    lsf_sigma: str | None = None
    lsf_basis: str | None = None
    optics: str | None = None
    distortion: str | None = None
    #: Static per-(era, channel, order) pixel-position table S(p) on top of
    #: D(p) (doppler.calib.StaticPositions).
    wavelength_static: str | None = None
    detector_map: str | None = None
    corrections: tuple[CorrectionConfig, ...] = ()


@dataclass(frozen=True)
class WavelengthModel:
    #: ``optics``: static optical-model curve + perturbation; ``pipeline``:
    #: polynomial started from the product's stored wavelengths.
    base: Literal["optics", "pipeline"] = "optics"
    distortion: bool = True
    #: Apply the static position table S(p) (needs
    #: calibrations.wavelength_static).
    static_table: bool = False
    degree: int = 2
    #: Coarse pixel-shift search half-range [px] per (exposure, channel).
    search_px: float = 80.0


@dataclass(frozen=True)
class LsfModel:
    model: Literal["gaussian", "gauss_hermite"] = "gauss_hermite"
    nnode: int = 5
    illumination: Literal["none", "gh", "basis"] = "none"
    #: Hierarchical (channel, era) prior on the illumination kernel.
    hierarchical: bool = True
    #: False: the illumination kernel is per channel relative to the others
    #: (its mean over the channels of each exposure held at zero), so no
    #: exposure-common LSF change is fitted.
    exposure_common: bool = True
    #: Initial prior widths (gh: [dw, dh3]; basis: per coefficient).
    tau_init: tuple[float, ...] = (2.0, 2.0, 2.0)
    tau_floor: float = 1e-3
    #: The calibration (map or sigma table) was measured with a model that
    #: point-samples at pixel centres: remove the pixel-box variance.
    point_sampled_calibration: bool = False
    nsigma: float = 6.0


@dataclass(frozen=True)
class IodineModel:
    learned_correction: bool = True
    #: ``optical_depth`` (exp(-k tau)) or ``linear`` (1 + k (T - 1)).
    scaling: Literal["optical_depth", "linear"] = "optical_depth"
    node_kms: float = 0.6
    prior_sigma: float = 0.01
    smooth_sigma: float = 0.01


@dataclass(frozen=True)
class TelluricModel:
    #: ``modelled``: per-exposure water column times the cleaned atlas;
    #: ``mask``: static mask where the atlas is below ``mask_threshold``;
    #: ``none``.
    model: Literal["modelled", "mask", "none"] = "modelled"
    mask_threshold: float = 0.98
    #: Atlas cleaned to 1 where it is above this (its noise floor).
    clean_threshold: float = 0.99
    #: Prior width of the per-exposure water column around 1 (atlas units).
    water_prior_sigma: float = 1.0
    #: Noise inflation per order index (e.g. water orders), {order: factor}.
    downweight: dict = field(default_factory=dict)


@dataclass(frozen=True)
class StarModel:
    #: ``fixed``: the tabulated template; ``modify``: regularized correction
    #: of it with per-order zero points; ``infer``: flat start.
    mode: Literal["fixed", "modify", "infer"] = "modify"
    oversample: float = 4.0
    prior_sigma: float | None = None
    smooth_sigma: float = 0.01
    fit_zero_points: bool = True


@dataclass(frozen=True)
class CtiModel:
    enabled: bool = False
    #: q_ref, s_ref [ADU], alpha, a1, l1, a2, l2 (None = KiwiSpec default).
    trap: tuple[float, ...] | None = None
    #: Peak-pixel ADU per extracted flux unit (None = default).
    signal_scale: float | None = None
    amplifier_column: float = 0.0
    transfer_offset: float = 51.0


@dataclass(frozen=True)
class BervPatternModel:
    """Smooth per-order function of the barycentric velocity, shared by all
    channels, as a velocity nuisance (Legendre degree 1..degree in
    BERV / scale)."""

    enabled: bool = False
    degree: int = 3
    scale_kms: float = 30.0


@dataclass(frozen=True)
class ModelConfig:
    grid_step_kms: float = 0.25
    #: Pixel sampling of the model: ``average`` (physical) or ``point``.
    sampling: Literal["average", "point"] = "average"
    #: Order indices; None = the arm's rv_orders.
    orders: tuple[int, ...] | None = None
    channels: tuple[str, ...] | None = None
    #: Wavelength margin dropped at each order end [Angstrom].
    buffer_angstrom: float = 2.0
    continuum_degree: int = 2
    wavelength: WavelengthModel = field(default_factory=WavelengthModel)
    lsf: LsfModel = field(default_factory=LsfModel)
    iodine: IodineModel = field(default_factory=IodineModel)
    telluric: TelluricModel = field(default_factory=TelluricModel)
    star: StarModel = field(default_factory=StarModel)
    cti: CtiModel = field(default_factory=CtiModel)
    detector_map: bool = False
    berv_pattern: BervPatternModel = field(default_factory=BervPatternModel)


@dataclass(frozen=True)
class SolverConfig:
    sweeps: int = 10
    #: Stop when the largest change of an (exposure, channel) velocity
    #: between sweeps is below this [m/s].
    tol_mps: float = 0.05
    processes: int = 4
    #: A previous run's state file to start from (warm start).
    warm_start: str | None = None
    max_iter_block: int = 30
    #: Blocks enter the template step only if converged, frac_rms below
    #: this, and their combined velocity within ``template_max_dev_mps`` of
    #: the median.
    template_max_frac_rms: float = 0.15
    template_max_dev_mps: float = 1000.0
    #: Over-relaxation factor of the template update (1 = plain alternation;
    #: ~1.2-1.4 speeds up a slowly converging alternation).
    relaxation: float = 1.0


@dataclass(frozen=True)
class OutputConfig:
    segments: int = 4
    projection: bool = True


@dataclass(frozen=True)
class DopplerRunConfig:
    schema_version: int
    instrument: str
    output: str
    star: StarConfig
    calibrations: CalibrationsConfig
    inputs: InputsConfig = field(default_factory=InputsConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    solver: SolverConfig = field(default_factory=SolverConfig)
    outputs: OutputConfig = field(default_factory=OutputConfig)
    #: Extra per-channel breaks (beyond the instrument's), for the
    #: combination: [{date: YYYY-MM-DD, channels: [..]}].
    extra_channel_breaks: tuple[dict, ...] = ()
    #: Extra per-channel exclusion windows: [{start, end, channels}].
    extra_excluded: tuple[dict, ...] = ()


def load_run_config(path: str | Path) -> DopplerRunConfig:
    data = yaml.safe_load(Path(path).read_text())
    return parse_run_config(data)


def parse_run_config(data: dict) -> DopplerRunConfig:
    if not isinstance(data, dict):
        raise ConfigError("run config: top level must be a mapping")
    cfg = build_dataclass(DopplerRunConfig, data)
    if cfg.schema_version != RUN_SCHEMA_VERSION:
        raise ConfigError(
            f"schema_version: this code reads {RUN_SCHEMA_VERSION}, got {cfg.schema_version}"
        )
    m = cfg.model
    if m.grid_step_kms <= 0:
        raise ConfigError("model.grid_step_kms must be > 0")
    if m.lsf.model == "gaussian" and m.lsf.illumination != "none":
        raise ConfigError("model.lsf: a Gaussian LSF has no illumination kernel")
    if m.star.mode != "fixed" and m.berv_pattern.enabled and m.berv_pattern.degree < 1:
        raise ConfigError("model.berv_pattern.degree must be >= 1")
    if cfg.inputs.manifest is None and cfg.inputs.directory is None:
        raise ConfigError("inputs: give a manifest or a directory")
    return cfg

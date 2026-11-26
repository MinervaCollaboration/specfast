"""Explicit per-run configuration (DESIGN.md, "Data model and provenance").

A run is described by one YAML file, loaded into frozen dataclasses and
validated: unknown keys, missing required keys and wrong types are errors.
Nothing is read from environment variables, and ``$VARS`` or ``~`` in paths
are *not* expanded: data locations are written out in the user's config.

Relative paths in ``paths`` are resolved against the config file's directory
when loaded with :func:`load_config`.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

#: Version of the run-config schema this code reads.
CONFIG_SCHEMA_VERSION = 1


class ConfigError(ValueError):
    """An invalid run configuration (the message names the offending key)."""


@dataclass(frozen=True)
class PathsConfig:
    """Data locations. ``output`` is required; the others are optional."""

    output: str
    raw: str | None = None
    calibrations: str | None = None
    templates: str | None = None


@dataclass(frozen=True)
class GridConfig:
    """Fine model grid, uniform in ln(lambda)."""

    #: Grid step [km/s] (0.25 km/s is R ~ 1.2e6).
    step_kms: float = 0.25
    #: Margin beyond the order's wavelength range on each side [km/s].
    margin_kms: float = 100.0


@dataclass(frozen=True)
class WavelengthConfig:
    model: Literal["polynomial"] = "polynomial"
    #: Polynomial degree in pixel (DESIGN: default > 2).
    degree: int = 3


@dataclass(frozen=True)
class ContinuumConfig:
    model: Literal["polynomial"] = "polynomial"
    degree: int = 2


@dataclass(frozen=True)
class LsfConfig:
    model: Literal["gaussian"] = "gaussian"
    #: Kernel half-width in units of sigma.
    nsigma: float = 6.0


@dataclass(frozen=True)
class ReferenceConfig:
    """Wavelength reference: an absorption cell in the beam, or none."""

    model: Literal["iodine", "none"] = "iodine"
    #: Iodine atlas file (relative to ``paths.calibrations`` if not absolute).
    atlas: str | None = None


@dataclass(frozen=True)
class TemplateConfig:
    """Template inference (:mod:`specfast.doppler.template`)."""

    #: ``modify``: regularized correction to a prior spectrum (DSST, solar
    #: atlas, synthetic); ``infer``: flat or weak prior.
    mode: Literal["modify", "infer"] = "modify"
    #: Template nodes per detector pixel (sets the node step).
    oversample: float = 4.0
    #: L2 prior width per node on the correction (template - prior);
    #: None = 0.05 (modify) or 1.0 (infer).
    prior_sigma: float | None = None
    #: Prior width of the correction's second difference per node.
    smooth_sigma: float = 0.01
    #: Fit per-order template zero points (a template property).
    fit_zero_points: bool = True
    #: Maximum alternation sweeps, and the convergence tolerance [m/s] on
    #: the velocities and order offsets between sweeps.
    iterations: int = 8
    tol_mps: float = 0.01
    #: Fit the learned observatory-frame corrections the components declare.
    learn_observatory: bool = True
    observatory_prior_sigma: float = 0.01
    observatory_smooth_sigma: float = 0.01
    #: Gauge of the learned observatory corrections against the template:
    #: ``template`` constrains each correction to have no component along the
    #: template's mean observed-frame imprint (high-passed log flux) or its
    #: derivative, the directions in which an observed-frame correction and the
    #: star-frame template trade off when the barycentric range is small.
    observatory_gauge: Literal["none", "template"] = "none"
    #: High-pass width [km/s] of the imprint used by the template gauge.
    observatory_gauge_kms: float = 30.0
    #: Fit the detector maps (default: fixed calibration), with these priors.
    fit_detector: bool = False
    detector_dx_sigma_px: float = 0.002
    detector_response_sigma: float = 0.001
    #: Separability threshold (0-1) for the degeneracy check, and the template
    #: resolution it is checked at [km/s] (None = the LSF FWHM).
    min_separability: float = 0.5
    resolution_kms: float | None = None
    #: ``alternate`` (template / velocities+nuisances); ``joint`` is a hook.
    strategy: Literal["alternate", "joint"] = "alternate"


@dataclass(frozen=True)
class StarConfig:
    mode: Literal["dsst", "inferred", "synthetic"] = "dsst"
    #: Template file (relative to ``paths.templates`` if not absolute).
    template: str | None = None
    #: Settings of the inferred mode.
    inference: TemplateConfig = field(default_factory=TemplateConfig)


@dataclass(frozen=True)
class DopplerConfig:
    grid: GridConfig = field(default_factory=GridConfig)
    wavelength: WavelengthConfig = field(default_factory=WavelengthConfig)
    continuum: ContinuumConfig = field(default_factory=ContinuumConfig)
    lsf: LsfConfig = field(default_factory=LsfConfig)
    reference: ReferenceConfig = field(default_factory=ReferenceConfig)
    star: StarConfig = field(default_factory=StarConfig)
    #: Velocity segments per order (DESIGN, "Velocity granularity").
    segments_per_order: int = 4
    #: Order indices to fit; ``None`` = the arm's ``rv_orders``.
    orders: tuple[int, ...] | None = None
    #: Channel names to fit; ``None`` = all science channels.
    channels: tuple[str, ...] | None = None


@dataclass(frozen=True)
class RunConfig:
    """The whole run configuration."""

    schema_version: int
    #: Shipped instrument name (e.g. ``kiwispec``) or a path to a YAML file.
    instrument: str
    paths: PathsConfig
    #: Observing mode (instruments with modes); None = the instrument's default.
    mode: str | None = None
    doppler: DopplerConfig = field(default_factory=DopplerConfig)

    def sha256(self) -> str:
        """Hash of the canonical JSON form (key order and formatting do not
        matter; any value change does)."""
        return config_hash(self)


def config_hash(cfg: Any) -> str:
    """sha256 hex digest of a config dataclass's canonical JSON."""
    text = json.dumps(dataclasses.asdict(cfg), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _is_dataclass_type(tp: Any) -> bool:
    return isinstance(tp, type) and dataclasses.is_dataclass(tp)


def _build(tp: Any, value: Any, where: str) -> Any:
    """Convert ``value`` (plain YAML data) to type ``tp``, strictly."""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) != 1:
            raise ConfigError(f"{where}: unsupported union type {tp}")
        return _build(non_none[0], value, where)
    if origin is Literal:
        if value not in args:
            raise ConfigError(f"{where}: {value!r} is not one of {list(args)}")
        return value
    if origin is tuple:
        if not isinstance(value, list | tuple):
            raise ConfigError(f"{where}: expected a list, got {type(value).__name__}")
        return tuple(_build(args[0], v, f"{where}[{i}]") for i, v in enumerate(value))
    if _is_dataclass_type(tp):
        if not isinstance(value, dict):
            raise ConfigError(f"{where}: expected a mapping, got {type(value).__name__}")
        return build_dataclass(tp, value, where)
    if tp is dict or origin is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"{where}: expected a mapping, got {type(value).__name__}")
        return dict(value)
    if tp is datetime.date:
        if isinstance(value, datetime.datetime):
            raise ConfigError(f"{where}: expected a date, got a datetime {value!r}")
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value)
            except ValueError as exc:
                raise ConfigError(f"{where}: {exc}") from None
        raise ConfigError(f"{where}: expected a YYYY-MM-DD date, got {value!r}")
    if tp is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{where}: expected true/false, got {value!r}")
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where}: expected an integer, got {value!r}")
        return value
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{where}: expected a number, got {value!r}")
        return float(value)
    if tp is str:
        if not isinstance(value, str):
            raise ConfigError(f"{where}: expected a string, got {value!r}")
        return value
    raise ConfigError(f"{where}: unsupported field type {tp}")


def build_dataclass(cls: type, data: dict, where: str = "") -> Any:
    """Build frozen dataclass ``cls`` from a mapping, rejecting unknown keys
    and reporting missing required ones. Used for configs and instruments."""
    hints = typing.get_type_hints(cls)
    fields = {f.name: f for f in dataclasses.fields(cls) if f.init}
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise ConfigError(f"{where or cls.__name__}: unknown key(s) {unknown}")
    kwargs = {}
    for name, f in fields.items():
        sub = f"{where}.{name}" if where else name
        if name in data:
            kwargs[name] = _build(hints[name], data[name], sub)
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            raise ConfigError(f"{sub}: required key missing")
    return cls(**kwargs)


def _resolve(path: str | None, base: Path) -> str | None:
    if path is None:
        return None
    p = Path(path)
    return str(p if p.is_absolute() else (base / p).resolve())


def parse_config(data: dict, base_dir: str | Path | None = None) -> RunConfig:
    """Validate a config mapping. Relative paths resolve against ``base_dir``
    (left as written when ``base_dir`` is None)."""
    if not isinstance(data, dict):
        raise ConfigError("config: top level must be a mapping")
    cfg = build_dataclass(RunConfig, data)
    if cfg.schema_version != CONFIG_SCHEMA_VERSION:
        raise ConfigError(
            f"schema_version: this code reads version {CONFIG_SCHEMA_VERSION}, "
            f"got {cfg.schema_version}"
        )
    d = cfg.doppler
    if d.wavelength.degree < 1:
        raise ConfigError("doppler.wavelength.degree: must be >= 1")
    if d.continuum.degree < 0:
        raise ConfigError("doppler.continuum.degree: must be >= 0")
    if d.segments_per_order < 1:
        raise ConfigError("doppler.segments_per_order: must be >= 1")
    if d.grid.step_kms <= 0 or d.grid.margin_kms < 0:
        raise ConfigError("doppler.grid: step_kms must be > 0 and margin_kms >= 0")
    if d.lsf.nsigma <= 0:
        raise ConfigError("doppler.lsf.nsigma: must be > 0")
    t = d.star.inference
    positive = {
        "oversample": t.oversample,
        "smooth_sigma": t.smooth_sigma,
        "observatory_prior_sigma": t.observatory_prior_sigma,
        "observatory_smooth_sigma": t.observatory_smooth_sigma,
        "detector_dx_sigma_px": t.detector_dx_sigma_px,
        "detector_response_sigma": t.detector_response_sigma,
        "prior_sigma": 1.0 if t.prior_sigma is None else t.prior_sigma,
        "resolution_kms": 1.0 if t.resolution_kms is None else t.resolution_kms,
    }
    for key, val in positive.items():
        if val <= 0:
            raise ConfigError(f"doppler.star.inference.{key}: must be > 0")
    if t.iterations < 1 or not 0 < t.min_separability < 1:
        raise ConfigError(
            "doppler.star.inference: iterations must be >= 1 and min_separability in (0, 1)"
        )
    if base_dir is not None:
        base = Path(base_dir)
        p = cfg.paths
        paths = PathsConfig(
            output=_resolve(p.output, base),
            raw=_resolve(p.raw, base),
            calibrations=_resolve(p.calibrations, base),
            templates=_resolve(p.templates, base),
        )
        cfg = dataclasses.replace(cfg, paths=paths)
    return cfg


def load_config(path: str | Path) -> RunConfig:
    """Load and validate a run config YAML file."""
    path = Path(path)
    with open(path) as fh:
        data = yaml.safe_load(fh)
    return parse_config(data, base_dir=path.parent)

"""Provenance: what code, configuration and inputs made a product.

Every product carries a :class:`Provenance` record (DESIGN.md, "Data model
and provenance"): the package version and ``git describe`` of the code, the
config hash, and the sha256 of every input and calibration file. Records are
plain data and round-trip through JSON exactly.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from specfast import __version__

_CHUNK = 1 << 20


def sha256_file(path: str | Path) -> str:
    """sha256 hex digest of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def git_describe(path: str | Path | None = None) -> str | None:
    """``git describe --always --dirty --tags`` of the checkout holding
    ``path`` (default: this package), or None outside a git checkout."""
    where = Path(path) if path is not None else Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "describe", "--always", "--dirty", "--tags"],
            cwd=where,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


@dataclass(frozen=True)
class FileHash:
    """One input file: a role label, the path as given, and its sha256."""

    role: str
    path: str
    sha256: str

    @classmethod
    def of(cls, role: str, path: str | Path) -> FileHash:
        return cls(role=role, path=str(path), sha256=sha256_file(path))


@dataclass(frozen=True)
class Provenance:
    """The provenance record attached to every product."""

    package_version: str
    git_describe: str | None
    python_version: str
    created_utc: str
    config_sha256: str | None = None
    inputs: tuple[FileHash, ...] = field(default_factory=tuple)
    #: Name of the stage that made the product (e.g. "extract", "doppler").
    stage: str = ""

    @classmethod
    def create(
        cls,
        stage: str,
        config_sha256: str | None = None,
        inputs: dict[str, str | Path] | None = None,
    ) -> Provenance:
        """A record for the running code; ``inputs`` maps role -> file path."""
        files = tuple(FileHash.of(r, p) for r, p in sorted((inputs or {}).items()))
        return cls(
            package_version=__version__,
            git_describe=git_describe(),
            python_version=platform.python_version(),
            created_utc=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
            config_sha256=config_sha256,
            inputs=files,
            stage=stage,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Provenance:
        d = json.loads(text)
        d["inputs"] = tuple(FileHash(**f) for f in d.get("inputs", ()))
        return cls(**d)

"""``specfast-doppler RUN.yaml``: fit a set of extracted spectra
(:mod:`specfast.doppler.engine`)."""

from __future__ import annotations

import argparse

from specfast.doppler.engine import run
from specfast.doppler.runconfig import load_run_config


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="specfast-doppler", description=__doc__)
    ap.add_argument("config", help="run configuration (YAML)")
    a = ap.parse_args(argv)
    cfg = load_run_config(a.config)
    out = run(cfg, config_path=a.config)
    print(f"outputs in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

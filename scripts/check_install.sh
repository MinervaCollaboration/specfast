#!/usr/bin/env bash
# Check that specfast installs as a package: `pip install .` into a fresh
# venv, then import it and load a shipped instrument description (package
# data) from outside the checkout. CI runs this (job `install`); locally:
#
#   PYTHON=python3.12 scripts/check_install.sh /path/to/scratch-venv
set -euo pipefail
venv=${1:?usage: check_install.sh VENV_DIR}
repo=$(cd "$(dirname "$0")/.." && pwd)
rm -rf "$venv"
"${PYTHON:-python3}" -m venv "$venv"
"$venv/bin/python" -m pip install --quiet --upgrade pip
"$venv/bin/python" -m pip install --quiet "$repo"
cd "$venv"
"$venv/bin/python" - "$repo" <<'PY'
import sys
import specfast
from specfast.instrument import load_instrument
if specfast.__file__.startswith(sys.argv[1] + "/"):
    sys.exit("specfast imported from the checkout")
for name in ("kiwispec", "gclef_magellan", "gclef_gmt"):
    load_instrument(name)
print(specfast.__file__)
PY
echo "install OK"

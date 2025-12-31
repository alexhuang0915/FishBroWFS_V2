#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."  # repo root

if [ ! -x ".venv/bin/python" ]; then
  echo "ERROR: .venv not found. Create venv first." >&2
  exit 1
fi

.venv/bin/python -m pip install -U pip
# Use the repo's canonical requirements file here (pick the right one)
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python -m playwright --version
.venv/bin/python -m playwright install chromium
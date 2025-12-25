#!/bin/bash
# Launch B5-C Mission Control (NiceGUI + FastAPI)

set -e

# Set PYTHONPATH
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"

# Change to repo root
cd "$(dirname "$0")/.."

# Start NiceGUI app (which includes FastAPI)
python -m FishBroWFS_V2.control.app_nicegui


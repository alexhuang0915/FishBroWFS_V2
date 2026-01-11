#!/bin/bash
# Pyright/Pylance Zero-Red CI Gate
# Runs pyright with strict mode matching Pylance behavior
# Exits non-zero if ANY error exists

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Use project venv python if present
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

# Check if pyright is available
if ! command -v pyright >/dev/null 2>&1 && ! $PYTHON -m pyright --help >/dev/null 2>&1; then
    echo "ERROR: pyright not found. Install with: pip install pyright"
    exit 1
fi

# Use custom config if present
CONFIG_FILE="scripts/_dev/pyrightconfig.json"
if [ -f "$CONFIG_FILE" ]; then
    CONFIG_ARG="-p $CONFIG_FILE"
else
    CONFIG_ARG=""
fi

echo "==> Running pyright zero-red gate..."
echo "    Python: $PYTHON"
echo "    Config: ${CONFIG_ARG:-default}"
echo "    Root: $REPO_ROOT"
echo

# Run pyright
if command -v pyright >/dev/null 2>&1; then
    # pyright available as standalone command
    pyright $CONFIG_ARG --outputjson .
else
    # pyright available as module
    $PYTHON -m pyright $CONFIG_ARG --outputjson .
fi

EXIT_CODE=$?

echo
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Pyright: 0 errors (ZERO-RED ACHIEVED)"
else
    echo "❌ Pyright: errors found (see above)"
    echo "   To reproduce locally:"
    echo "   cd $REPO_ROOT"
    if [ -n "$CONFIG_ARG" ]; then
        echo "   pyright $CONFIG_ARG ."
    else
        echo "   pyright ."
    fi
fi

exit $EXIT_CODE
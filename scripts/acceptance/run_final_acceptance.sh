#!/usr/bin/env zsh
# FishBroWFS_V2 Final Acceptance Harness
# One-click end-to-end acceptance test producing auditable evidence bundle.
# Exit codes: 0=PASS, 2=FAIL

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
readonly EVID_ROOT="$ROOT_DIR/outputs/_dp_evidence/final_acceptance"

# Timestamp (UTC)
readonly TS=$(python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
PY
)

readonly EVID="$EVID_ROOT/$TS"
readonly SUPERVISOR_HOST="127.0.0.1"
readonly SUPERVISOR_PORT="8000"
readonly SUPERVISOR_URL="http://$SUPERVISOR_HOST:$SUPERVISOR_PORT"

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
log() {
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"
}

fail() {
    log "FAIL: $*"
    echo "FAIL: $*" >&2
    exit 2
}

ensure_dir() {
    mkdir -p "$1"
}

write_evidence() {
    local filename="$1"
    local content="$2"
    echo "$content" > "$EVID/$filename"
    log "Wrote evidence: $filename"
}

# -----------------------------------------------------------------------------
# Initialization
# -----------------------------------------------------------------------------
log "Starting Final Acceptance Harness"
log "Root directory: $ROOT_DIR"
log "Evidence directory: $EVID"

ensure_dir "$EVID"

# -----------------------------------------------------------------------------
# 00 Environment Capture
# -----------------------------------------------------------------------------
log "Capturing environment..."
{
    echo "=== System ==="
    uname -a
    echo ""
    echo "=== Python ==="
    python3 --version 2>&1 || echo "python3 not found"
    echo ""
    echo "=== Pip freeze ==="
    pip freeze 2>/dev/null || echo "pip not available"
    echo ""
    echo "=== Git ==="
    git rev-parse HEAD 2>/dev/null || echo "git not available"
    echo ""
    echo "=== Date (UTC) ==="
    date -u
} > "$EVID/00_env.txt"

# -----------------------------------------------------------------------------
# 01 Git Status
# -----------------------------------------------------------------------------
log "Capturing git status..."
git status --porcelain=v1 > "$EVID/01_git_status.txt" 2>/dev/null || true

# -----------------------------------------------------------------------------
# 02 Root Listing
# -----------------------------------------------------------------------------
log "Capturing root directory listing..."
ls -la "$ROOT_DIR" > "$EVID/02_root_ls.txt"

# -----------------------------------------------------------------------------
# 03 Engineering Gate: make check
# -----------------------------------------------------------------------------
log "Running make check..."
cd "$ROOT_DIR"
if make check > "$EVID/03_make_check.txt" 2>&1; then
    log "make check passed"
else
    log "make check failed"
    # Check if there are any failures
    if grep -q "FAILED\|ERROR" "$EVID/03_make_check.txt"; then
        fail "make check had test failures"
    fi
    # If make check exits non-zero but no FAILED/ERROR lines, still treat as failure
    fail "make check exited with error"
fi

# -----------------------------------------------------------------------------
# 04 Supervisor Gate
# -----------------------------------------------------------------------------
log "Checking Supervisor on $SUPERVISOR_URL..."

# Function to check if /health responds
health_check() {
    curl -s -f --max-time 5 "$SUPERVISOR_URL/health" >/dev/null 2>&1
}

# Function to start supervisor in background
start_supervisor() {
    log "Starting supervisor..."
    nohup python3 scripts/run_supervisor.py --host "$SUPERVISOR_HOST" --port "$SUPERVISOR_PORT" \
        > "$EVID/supervisor_stdout.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$EVID/supervisor_pid.txt"
    log "Supervisor started with PID $pid"
    
    # Wait for health to become available
    local max_wait=20
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if health_check; then
            log "Supervisor health check passed after ${waited}s"
            return 0
        fi
        sleep 0.5
        waited=$((waited + 1))
    done
    
    log "Supervisor failed to become healthy after ${max_wait}s"
    # Try to kill it
    kill "$pid" 2>/dev/null || true
    return 1
}

SUPERVISOR_STARTED=false
if health_check; then
    log "Supervisor already running and healthy"
    write_evidence "04_supervisor_status.txt" "using existing supervisor"
else
    # Check if port is occupied by something else
    if nc -z "$SUPERVISOR_HOST" "$SUPERVISOR_PORT" 2>/dev/null; then
        fail "Port $SUPERVISOR_PORT is occupied but /health is not responding"
    fi
    
    # Start supervisor
    if start_supervisor; then
        SUPERVISOR_STARTED=true
        write_evidence "04_supervisor_status.txt" "started new supervisor"
    else
        fail "Failed to start supervisor"
    fi
fi

# -----------------------------------------------------------------------------
# 05-14 Python Probe
# -----------------------------------------------------------------------------
log "Running Python acceptance probe..."
cd "$ROOT_DIR"
if python3 scripts/acceptance/final_acceptance_probe.py \
    --base-url "$SUPERVISOR_URL" \
    --evidence-dir "$EVID"; then
    log "Python probe completed successfully"
else
    probe_exit=$?
    log "Python probe failed with exit code $probe_exit"
    # If probe failed, we still want to clean up supervisor if we started it
    if [ "$SUPERVISOR_STARTED" = true ]; then
        kill "$(cat "$EVID/supervisor_pid.txt")" 2>/dev/null || true
    fi
    exit 2
fi

# -----------------------------------------------------------------------------
# 15 Cleanup (if we started supervisor)
# -----------------------------------------------------------------------------
if [ "$SUPERVISOR_STARTED" = true ]; then
    log "Stopping supervisor we started..."
    pid=$(cat "$EVID/supervisor_pid.txt" 2>/dev/null || echo "")
    if [ -n "$pid" ]; then
        kill -TERM "$pid" 2>/dev/null || true
        # Wait up to 5 seconds
        local wait_count=0
        while kill -0 "$pid" 2>/dev/null && [ $wait_count -lt 10 ]; do
            sleep 0.5
            wait_count=$((wait_count + 1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null || true
            log "Supervisor required SIGKILL"
        else
            log "Supervisor stopped gracefully"
        fi
    fi
fi

# -----------------------------------------------------------------------------
# 16 Final Summary
# -----------------------------------------------------------------------------
log "Generating final summary..."
{
    echo "# Final Acceptance Summary"
    echo ""
    echo "## Execution Details"
    echo "- Timestamp: $TS"
    echo "- Evidence directory: $EVID"
    echo "- Supervisor: $(if [ "$SUPERVISOR_STARTED" = true ]; then echo "started and stopped"; else echo "using existing"; fi)"
    echo "- Base URL: $SUPERVISOR_URL"
    echo ""
    echo "## Gates Status"
    echo "- ✅ Environment captured"
    echo "- ✅ Git status captured"
    echo "- ✅ Root listing captured"
    echo "- ✅ make check passed"
    echo "- ✅ Supervisor health check passed"
    echo "- ✅ Python probe completed"
    echo ""
    echo "## Evidence Files"
    for f in "$EVID"/*; do
        if [ -f "$f" ]; then
            echo "- $(basename "$f")"
        fi
    done
    echo ""
    echo "## Result: PASS"
} > "$EVID/99_final_summary.md"

# -----------------------------------------------------------------------------
# 17 Output
# -----------------------------------------------------------------------------
log ""
log "========================================"
log "FINAL ACCEPTANCE: PASS"
log "Evidence directory: $EVID"
log "========================================"
exit 0
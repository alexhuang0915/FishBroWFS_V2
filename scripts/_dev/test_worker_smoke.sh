#!/bin/bash
set -e

echo "=== Starting worker smoke test ==="
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8001  # Different port to avoid conflict
DB_PATH="outputs/jobs.db"

# Clean up any existing pidfile
rm -f outputs/worker.pid outputs/worker.heartbeat 2>/dev/null || true

# Start backend in background
echo "Starting backend on $BACKEND_HOST:$BACKEND_PORT..."
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m uvicorn control.api:app --host $BACKEND_HOST --port $BACKEND_PORT --reload &
BACKEND_PID=$!

# Give backend time to start
sleep 3

# Start worker in background
echo "Starting worker daemon..."
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m control.worker_main "$DB_PATH" &
WORKER_PID=$!

# Give worker time to start and write pidfile
sleep 2

# Probe /worker/status - should be alive:true
echo "Probing /worker/status endpoint..."
MAX_RETRIES=10
RETRY=0
WORKER_ALIVE=false

while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -s http://$BACKEND_HOST:$BACKEND_PORT/worker/status 2>/dev/null | grep -q '"alive":true'; then
        WORKER_ALIVE=true
        break
    fi
    echo "  Retry $((RETRY+1))/$MAX_RETRIES: worker not alive yet..."
    sleep 1
    RETRY=$((RETRY+1))
done

if [ "$WORKER_ALIVE" = true ]; then
    echo "✓ Worker status reports alive:true"
else
    echo "✗ Worker failed to become alive after $MAX_RETRIES retries"
    # Capture worker logs if any
    if [ -f outputs/worker_process.log ]; then
        echo "=== Worker logs (tail) ==="
        tail -20 outputs/worker_process.log || true
    fi
    kill $BACKEND_PID $WORKER_PID 2>/dev/null || true
    exit 1
fi

# Clean up
echo "Stopping worker (PID: $WORKER_PID)..."
kill $WORKER_PID 2>/dev/null || true
wait $WORKER_PID 2>/dev/null || true

echo "Stopping backend (PID: $BACKEND_PID)..."
kill $BACKEND_PID 2>/dev/null || true
wait $BACKEND_PID 2>/dev/null || true

# Clean up pidfiles
rm -f outputs/worker.pid outputs/worker.heartbeat 2>/dev/null || true

echo "=== Worker smoke test PASSED ==="

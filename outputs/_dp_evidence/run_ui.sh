#!/bin/bash
set -e
cd /home/fishbro/FishBroWFS_V2
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -B scripts/desktop_launcher.py 2>&1 &
PID=$!
echo "Desktop UI started with PID $PID"
sleep 5
if kill -0 $PID 2>/dev/null; then
    echo "UI still running after 5 seconds, killing."
    kill $PID
    sleep 1
    kill -9 $PID 2>/dev/null || true
fi
wait $PID 2>/dev/null || true
echo "UI process terminated."
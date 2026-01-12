"""Worker main entry point (for subprocess execution)."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically (write temp then replace)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_pidfile(db_path: Path) -> Path:
    """Write PID file atomically."""
    pidfile = db_path.parent / "worker.pid"
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(pidfile, str(os.getpid()))
    return pidfile


def write_initial_heartbeat(db_path: Path) -> Path:
    """Write initial heartbeat file atomically."""
    heartbeat_file = db_path.parent / "worker.heartbeat"
    heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(heartbeat_file, str(time.time()))
    return heartbeat_file


def worker_loop(db_path: Path) -> None:
    """Headless worker loop that processes jobs from the database.
    
    This is a simplified implementation that periodically checks for
    jobs and processes them. In a real implementation, this would
    integrate with the supervisor job system.
    """
    print(f"Worker loop started for database: {db_path}")
    
    # Simple heartbeat mechanism
    heartbeat_interval = 5.0  # seconds
    last_heartbeat = time.time()
    
    try:
        while True:
            current_time = time.time()
            
            # Update heartbeat file periodically
            if current_time - last_heartbeat >= heartbeat_interval:
                heartbeat_file = db_path.parent / "worker.heartbeat"
                atomic_write_text(heartbeat_file, str(current_time))
                last_heartbeat = current_time
            
            # Check for jobs (simplified - would query database)
            # For now, just sleep and continue
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("Worker loop interrupted")
        raise


def cleanup_files(db_path: Path) -> None:
    """Clean up pidfile and heartbeat file (best-effort)."""
    pidfile = db_path.parent / "worker.pid"
    heartbeat_file = db_path.parent / "worker.heartbeat"
    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        heartbeat_file.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m control.worker_main <db_path>")
        sys.exit(1)
    
    db_path = Path(sys.argv[1])
    
    # Setup signal handlers for clean shutdown
    def signal_handler(signum, frame):
        cleanup_files(db_path)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Create pidfile immediately
        write_pidfile(db_path)
        
        # Create initial heartbeat
        write_initial_heartbeat(db_path)
        
        # Start worker loop (heartbeat updates are handled inside worker_loop)
        worker_loop(db_path)
        
    except KeyboardInterrupt:
        # Clean shutdown on Ctrl+C
        pass
    except Exception as e:
        print(f"Worker main error: {e}")
        raise
    finally:
        # Clean up pidfile and heartbeat
        cleanup_files(db_path)

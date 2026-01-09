#!/usr/bin/env python3
"""
Worker process bootstrap.
Reads job spec from DB, validates handler exists, runs execute, heartbeats in background.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import signal
import threading
from pathlib import Path
from typing import Optional

from .db import SupervisorDB, get_default_db_path
from .job_handler import get_handler, execute_job, validate_job_spec
from .models import JobSpec, now_iso


def heartbeat_worker(db: SupervisorDB, job_id: str, interval: float = 2.0):
    """Background thread to send heartbeats."""
    try:
        while True:
            time.sleep(interval)
            try:
                db.update_heartbeat(job_id)
            except Exception:
                # If job is no longer RUNNING, exit
                break
    except KeyboardInterrupt:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervisor worker bootstrap")
    parser.add_argument("--db", type=Path, required=True, help="Path to jobs_v2.db")
    parser.add_argument("--job-id", type=str, required=True, help="Job ID to execute")
    parser.add_argument("--artifacts-root", type=Path, default=None,
                       help="Root directory for artifacts (default: outputs/_dp_evidence/supervisor_artifacts)")
    args = parser.parse_args()
    
    # Default artifacts directory: canonical job artifact root
    if args.artifacts_root is None:
        args.artifacts_root = Path("outputs")
    
    # Create canonical artifact directory for this job
    from .models import get_job_artifact_dir
    artifacts_dir = get_job_artifact_dir(args.artifacts_root, args.job_id)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    db = SupervisorDB(args.db)
    
    # Get job spec
    job_row = db.get_job_row(args.job_id)
    if job_row is None:
        print(f"ERROR: Job {args.job_id} not found", file=sys.stderr)
        return 1
    
    if job_row.state != "RUNNING":
        print(f"ERROR: Job {args.job_id} is not RUNNING (state={job_row.state})", file=sys.stderr)
        return 1
    
    # Parse spec
    try:
        spec_dict = json.loads(job_row.spec_json)
        spec = JobSpec(**spec_dict)
    except Exception as e:
        db.mark_failed(args.job_id, f"invalid_spec_json: {e}")
        return 1
    
    # Check handler exists
    handler = get_handler(spec.job_type)
    if handler is None:
        error_msg = f"unknown_job_type: {spec.job_type}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        db.mark_failed(args.job_id, error_msg)
        return 1
    
    # Validate params
    try:
        handler.validate_params(spec.params)
    except Exception as e:
        error_msg = f"validation_error: {e}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        db.mark_failed(args.job_id, error_msg)
        return 1
    
    # Register this worker
    worker_id = f"worker_{os.getpid()}_{int(time.time())}"
    db.register_worker(worker_id, os.getpid())
    db.mark_running(args.job_id, worker_id, os.getpid())
    
    # Start heartbeat thread
    heartbeat_thread = threading.Thread(
        target=heartbeat_worker,
        args=(db, args.job_id),
        daemon=True
    )
    heartbeat_thread.start()
    
    # Execute job
    try:
        result = execute_job(args.job_id, spec, db, str(artifacts_dir))
        # Check if result indicates abort
        if isinstance(result, dict) and result.get("aborted") is True:
            db.mark_aborted(args.job_id, "user_abort")
        else:
            db.mark_succeeded(args.job_id, result)
        return 0
    except KeyboardInterrupt:
        db.mark_aborted(args.job_id, "worker_interrupted")
        return 130  # SIGINT exit code
    except Exception as e:
        db.mark_failed(args.job_id, f"execution_error: {e}")
        return 1
    finally:
        db.mark_worker_exited(worker_id)


if __name__ == "__main__":
    sys.exit(main())
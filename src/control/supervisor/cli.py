#!/usr/bin/env python3
"""
Supervisor CLI for submitting, listing, and aborting jobs.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List

from .db import SupervisorDB, get_default_db_path
from .models import JobSpec, JobRow, JobState
from .job_handler import validate_job_spec


def submit_job(db_path: Path, job_type: str, params_json: str, metadata_json: Optional[str] = None) -> str:
    """Submit a new job."""
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid params JSON: {e}")
    
    metadata = {}
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid metadata JSON: {e}")
    
    spec = JobSpec(job_type=job_type, params=params, metadata=metadata)
    validate_job_spec(spec)
    
    db = SupervisorDB(db_path)
    job_id = db.submit_job(spec)
    return job_id


def list_jobs(db_path: Path, state: Optional[str] = None) -> List[JobRow]:
    """List jobs, optionally filtered by state."""
    db = SupervisorDB(db_path)
    
    with db._connect() as conn:
        if state:
            cursor = conn.execute("""
                SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC
            """, (state,))
        else:
            cursor = conn.execute("""
                SELECT * FROM jobs ORDER BY created_at DESC
            """)
        
        rows = cursor.fetchall()
        return [JobRow(**dict(row)) for row in rows]


def abort_job(db_path: Path, job_id: str) -> bool:
    """Request abort for a job."""
    db = SupervisorDB(db_path)
    
    # Check if job exists
    job = db.get_job_row(job_id)
    if job is None:
        return False
    
    if job.state not in ("QUEUED", "RUNNING"):
        return False
    
    db.request_abort(job_id)
    return True


def format_job_row(job: JobRow) -> str:
    """Format job row for display."""
    lines = [
        f"Job ID:    {job.job_id}",
        f"Type:      {job.job_type}",
        f"State:     {job.state}",
        f"Created:   {job.created_at}",
        f"Updated:   {job.updated_at}",
    ]
    if job.state_reason:
        lines.append(f"Reason:    {job.state_reason}")
    if job.worker_pid:
        lines.append(f"Worker:    {job.worker_pid}")
    if job.last_heartbeat:
        lines.append(f"Heartbeat: {job.last_heartbeat}")
    if job.progress is not None:
        lines.append(f"Progress:  {job.progress:.1%}")
    if job.phase:
        lines.append(f"Phase:     {job.phase}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervisor CLI")
    parser.add_argument("--db", type=Path, default=None,
                       help="Path to jobs_v2.db (default: outputs/jobs_v2.db)")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # submit command
    submit_parser = subparsers.add_parser("submit", help="Submit a new job")
    submit_parser.add_argument("--job-type", type=str, required=True, help="Job type")
    submit_parser.add_argument("--params-json", type=str, required=True, help="JSON parameters")
    submit_parser.add_argument("--metadata-json", type=str, help="JSON metadata")
    
    # list command
    list_parser = subparsers.add_parser("list", help="List jobs")
    list_parser.add_argument("--state", type=str, choices=["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "ABORTED", "ORPHANED", "REJECTED"],
                            help="Filter by state")
    
    # abort command
    abort_parser = subparsers.add_parser("abort", help="Abort a job")
    abort_parser.add_argument("--job-id", type=str, required=True, help="Job ID to abort")
    
    args = parser.parse_args()
    
    # Determine DB path
    db_path = args.db or get_default_db_path()
    
    try:
        if args.command == "submit":
            job_id = submit_job(db_path, args.job_type, args.params_json, args.metadata_json)
            print(f"Submitted job: {job_id}")
            return 0
        
        elif args.command == "list":
            jobs = list_jobs(db_path, args.state)
            if not jobs:
                print("No jobs found.")
                return 0
            
            for i, job in enumerate(jobs):
                if i > 0:
                    print("\n" + "-" * 40)
                print(format_job_row(job))
            return 0
        
        elif args.command == "abort":
            success = abort_job(db_path, args.job_id)
            if success:
                print(f"Abort requested for job {args.job_id}")
                return 0
            else:
                print(f"Job {args.job_id} not found or not abortable", file=sys.stderr)
                return 1
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
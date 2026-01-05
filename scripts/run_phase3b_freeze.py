#!/usr/bin/env python3
"""
Phase 3B Season Freeze – DEPRECATED WRAPPER.

This script is now a thin client that submits a Supervisor v2 job.
It does NOT execute core logic directly.

PHASE B HARDENING: This wrapper is now DISABLED by default.
To enable legacy compatibility, set environment variable:
    FISHBRO_ALLOW_LEGACY_WRAPPERS=1

Usage:
    python scripts/run_phase3b_freeze.py [--season SEASON] [--force]
    [--engine-version VERSION] [--notes NOTES] [--api-url URL] [--timeout SECONDS]
    [--no-wait]
"""

import sys
import os
import argparse
import time
import json

# PHASE B HARDENING: Check if legacy wrappers are allowed
if os.environ.get("FISHBRO_ALLOW_LEGACY_WRAPPERS") != "1":
    print("=" * 80)
    print("ERROR: Legacy wrapper execution is DISABLED by default.")
    print()
    print("This script (run_phase3b_freeze.py) is a legacy wrapper that has been")
    print("disabled as part of Phase B 'root-cut' hardening.")
    print()
    print("To enable legacy compatibility (temporary opt-in), set:")
    print("    export FISHBRO_ALLOW_LEGACY_WRAPPERS=1")
    print()
    print("PREFERRED ALTERNATIVES:")
    print("1. Use Qt Desktop UI (src/gui/desktop/)")
    print("2. Submit Supervisor job directly via API:")
    print("   - Job type: RUN_FREEZE_V2")
    print("   - Use SupervisorClient or HTTP POST to /jobs")
    print("=" * 80)
    sys.exit(2)

# Check for requests dependency
try:
    import requests
except ImportError:
    print("ERROR: 'requests' library is required for Supervisor API client.")
    print("Install it via: pip install requests")
    print("Or ensure it's in your project dependencies (pyproject.toml / requirements.txt)")
    sys.exit(1)

# Deprecation warning (only shown if wrapper is enabled)
print("=" * 70)
print("DEPRECATED: This script is now a wrapper for Supervisor v2.")
print("It will submit a RUN_FREEZE_V2 job via HTTP API and poll for completion.")
print("Direct execution of freeze logic has been migrated to Supervisor.")
print("=" * 70)
print()


def submit_freeze_job(api_url: str, season: str, force: bool = False, 
                      engine_version: str = None, notes: str = None) -> str:
    """Submit RUN_FREEZE_V2 job to Supervisor API and return job_id."""
    payload = {
        "season": season,
        "force": force,
    }
    if engine_version is not None:
        payload["engine_version"] = engine_version
    if notes is not None:
        payload["notes"] = notes
    
    # Supervisor expects job spec format
    job_spec = {
        "job_type": "RUN_FREEZE_V2",
        "params": payload,
        "metadata": {
            "submitted_by": "legacy_wrapper",
            "wrapper_version": "1.0"
        }
    }
    
    url = f"{api_url.rstrip('/')}/jobs"
    try:
        response = requests.post(url, json=job_spec, timeout=30)
        response.raise_for_status()
        result = response.json()
        job_id = result.get("job_id")
        if not job_id:
            raise ValueError(f"API response missing job_id: {result}")
        return job_id
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to Supervisor API at {url}")
        print("Make sure the Supervisor service is running (e.g., 'make backend' or 'make legacy-backend').")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: API request failed with status {e.response.status_code}: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to submit job: {e}")
        sys.exit(1)


def poll_job_status(api_url: str, job_id: str, timeout_sec: int = 3600, poll_interval: int = 2) -> bool:
    """Poll job status until completion or timeout. Returns True if succeeded."""
    start_time = time.time()
    url = f"{api_url.rstrip('/')}/jobs/{job_id}"
    
    print(f"Job {job_id} submitted. Polling for completion (timeout: {timeout_sec}s)...")
    
    last_state = None
    while time.time() - start_time < timeout_sec:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            job = response.json()
            state = job.get("status", "UNKNOWN")
            
            if state != last_state:
                print(f"  Job state: {state}")
                last_state = state
            
            if state == "SUCCEEDED":
                print("Job completed successfully.")
                return True
            elif state in ("FAILED", "CANCELLED", "ABORTED"):
                print(f"Job terminated with state: {state}")
                # Try to get error details
                try:
                    error = job.get("error")
                    if error:
                        print(f"Error details: {error}")
                except:
                    pass
                return False
            elif state == "RUNNING":
                # Show progress if available
                progress = job.get("progress", 0)
                if progress > 0:
                    print(f"  Progress: {progress:.1%}", end='\r')
            
            time.sleep(poll_interval)
        except requests.exceptions.RequestException as e:
            print(f"Warning: Failed to poll job status: {e}")
            time.sleep(poll_interval * 2)
    
    print(f"ERROR: Polling timeout after {timeout_sec} seconds.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit season freeze job to Supervisor")
    parser.add_argument("--season", default="2026Q1", help="Season identifier (default: 2026Q1)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing frozen season")
    parser.add_argument("--engine-version", help="Engine version to freeze with")
    parser.add_argument("--notes", help="Freeze notes")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Supervisor API base URL")
    parser.add_argument("--timeout", type=int, default=3600, help="Polling timeout in seconds")
    parser.add_argument("--no-wait", action="store_true", help="Submit job and exit immediately")
    args = parser.parse_args()
    
    print(f"Submitting freeze job for season: {args.season}")
    if args.force:
        print("Force flag enabled (will overwrite existing frozen season).")
    
    # Submit job
    job_id = submit_freeze_job(
        api_url=args.api_url,
        season=args.season,
        force=args.force,
        engine_version=args.engine_version,
        notes=args.notes
    )
    
    print(f"Submitted RUN_FREEZE_V2 job: {job_id}")
    
    if args.no_wait:
        print("Exiting immediately (--no-wait). Job will continue running.")
        sys.exit(0)
    
    # Poll for completion
    success = poll_job_status(args.api_url, job_id, timeout_sec=args.timeout)
    
    if success:
        print("\nSeason freeze completed successfully via Supervisor.")
        sys.exit(0)
    else:
        print("\nSeason freeze failed or timed out.")
        sys.exit(1)


if __name__ == "__main__":
    main()
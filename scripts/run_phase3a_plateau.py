#!/usr/bin/env python3
"""
Phase 3A Plateau Identification – DEPRECATED WRAPPER.

This script is now a thin client that submits a Supervisor v2 job.
It does NOT execute core logic directly.

PHASE B HARDENING: This wrapper is now DISABLED by default.
To enable legacy compatibility, set environment variable:
    FISHBRO_ALLOW_LEGACY_WRAPPERS=1

Usage:
    python scripts/run_phase3a_plateau.py <path/to/winners.json>
    python scripts/run_phase3a_plateau.py   (default: use test fixture)

Optional arguments:
    --k-neighbors <int>          Number of neighbors for plateau detection (default: 5)
    --score-threshold-rel <float> Relative score threshold (default: 0.1)
    --api-url <url>              Supervisor API base URL (default: http://localhost:8000)
    --timeout <seconds>          Polling timeout in seconds (default: 3600)
    --no-wait                    Submit job and exit immediately (returns job ID)
"""

import sys
import os
import argparse
import time
import json
from pathlib import Path

# PHASE B HARDENING: Check if legacy wrappers are allowed
if os.environ.get("FISHBRO_ALLOW_LEGACY_WRAPPERS") != "1":
    print("=" * 80)
    print("ERROR: Legacy wrapper execution is DISABLED by default.")
    print()
    print("This script (run_phase3a_plateau.py) is a legacy wrapper that has been")
    print("disabled as part of Phase B 'root-cut' hardening.")
    print()
    print("To enable legacy compatibility (temporary opt-in), set:")
    print("    export FISHBRO_ALLOW_LEGACY_WRAPPERS=1")
    print()
    print("PREFERRED ALTERNATIVES:")
    print("1. Use Qt Desktop UI (src/gui/desktop/)")
    print("2. Submit Supervisor job directly via API:")
    print("   - Job type: RUN_PLATEAU_V2")
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
print("It will submit a RUN_PLATEAU_V2 job via HTTP API and poll for completion.")
print("Direct execution of plateau logic has been migrated to Supervisor.")
print("=" * 70)
print()


def infer_research_run_id(winners_path: Path) -> str:
    """
    Infer research_run_id from winners.json path.
    
    Expected path pattern: outputs/seasons/current/{research_run_id}/winners.json
    or outputs/seasons/current/{research_run_id}/research/winners.json
    """
    # Normalize path
    winners_path = winners_path.resolve()
    
    # Try to match pattern
    parts = winners_path.parts
    try:
        # Find index of "seasons" in path
        seasons_idx = parts.index("seasons")
        # Expect "current" after seasons
        if seasons_idx + 2 < len(parts) and parts[seasons_idx + 1] == "current":
            research_run_id = parts[seasons_idx + 2]
            return research_run_id
    except ValueError:
        pass
    
    # Fallback: use parent directory name
    parent = winners_path.parent
    if parent.name == "research":
        parent = parent.parent
    return parent.name


def submit_plateau_job(api_url: str, research_run_id: str, k_neighbors: int = None, score_threshold_rel: float = None) -> str:
    """Submit RUN_PLATEAU_V2 job to Supervisor API and return job_id."""
    payload = {
        "research_run_id": research_run_id,
    }
    if k_neighbors is not None:
        payload["k_neighbors"] = k_neighbors
    if score_threshold_rel is not None:
        payload["score_threshold_rel"] = score_threshold_rel
    
    # Supervisor expects job spec format
    job_spec = {
        "job_type": "RUN_PLATEAU_V2",
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
    parser = argparse.ArgumentParser(description="Submit plateau identification job to Supervisor")
    parser.add_argument("winners_path", nargs="?", help="Path to winners.json file")
    parser.add_argument("--k-neighbors", type=int, help="Number of neighbors for plateau detection")
    parser.add_argument("--score-threshold-rel", type=float, help="Relative score threshold")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Supervisor API base URL")
    parser.add_argument("--timeout", type=int, default=3600, help="Polling timeout in seconds")
    parser.add_argument("--no-wait", action="store_true", help="Submit job and exit immediately")
    args = parser.parse_args()
    
    # Determine winners path
    if args.winners_path:
        winners_path = Path(args.winners_path)
    else:
        # Fallback to test fixture (for development)
        winners_path = Path("tests/fixtures/artifacts/winners_v2_valid.json")
        print(f"No path provided, using test fixture: {winners_path}")
    
    if not winners_path.exists():
        print(f"ERROR: File not found: {winners_path}")
        print("Please provide a valid winners.json path.")
        sys.exit(1)
    
    # Infer research_run_id from path
    research_run_id = infer_research_run_id(winners_path)
    print(f"Inferred research_run_id: {research_run_id}")
    print(f"Winners path: {winners_path}")
    
    # Submit job
    job_id = submit_plateau_job(
        api_url=args.api_url,
        research_run_id=research_run_id,
        k_neighbors=args.k_neighbors,
        score_threshold_rel=args.score_threshold_rel
    )
    
    print(f"Submitted RUN_PLATEAU_V2 job: {job_id}")
    
    if args.no_wait:
        print("Exiting immediately (--no-wait). Job will continue running.")
        sys.exit(0)
    
    # Poll for completion
    success = poll_job_status(args.api_url, job_id, timeout_sec=args.timeout)
    
    if success:
        print("\nPlateau identification completed successfully via Supervisor.")
        sys.exit(0)
    else:
        print("\nPlateau identification failed or timed out.")
        sys.exit(1)


if __name__ == "__main__":
    main()
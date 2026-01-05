#!/usr/bin/env python3
"""
Research v3 – DEPRECATED Transitional Wrapper.

This script is deprecated and MUST NOT execute research logic directly.
Instead, it submits a RUN_RESEARCH_V2 job to Supervisor v2.

PHASE B HARDENING: This wrapper is now DISABLED by default.
To enable legacy compatibility, set environment variable:
    FISHBRO_ALLOW_LEGACY_WRAPPERS=1
"""

import sys
import os
import logging
import json
import time
from pathlib import Path
from typing import Optional

# PHASE B HARDENING: Check if legacy wrappers are allowed
if os.environ.get("FISHBRO_ALLOW_LEGACY_WRAPPERS") != "1":
    print("=" * 80)
    print("ERROR: Legacy wrapper execution is DISABLED by default.")
    print()
    print("This script (run_research_v3.py) is a legacy wrapper that has been")
    print("disabled as part of Phase B 'root-cut' hardening.")
    print()
    print("To enable legacy compatibility (temporary opt-in), set:")
    print("    export FISHBRO_ALLOW_LEGACY_WRAPPERS=1")
    print()
    print("PREFERRED ALTERNATIVES:")
    print("1. Use Qt Desktop UI (src/gui/desktop/)")
    print("2. Submit Supervisor job directly via API:")
    print("   - Job type: RUN_RESEARCH_V2")
    print("   - Use SupervisorClient or HTTP POST to /jobs")
    print("=" * 80)
    sys.exit(2)

# Ensure the package root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def submit_run_research_v2_job() -> str:
    """Submit a RUN_RESEARCH_V2 job to Supervisor."""
    try:
        from src.control.supervisor import submit
        
        # Default parameters - these should come from command line or config
        # For now, use reasonable defaults
        payload = {
            "strategy_id": "S1",
            "profile_name": "CME_MNQ_v2",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "params_override": {}
        }
        
        job_id = submit("RUN_RESEARCH_V2", payload)
        logger.info(f"Submitted RUN_RESEARCH_V2 job with ID: {job_id}")
        return job_id
        
    except ImportError as e:
        logger.error(f"Failed to import supervisor module: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        raise


def wait_for_job_completion(job_id: str, timeout_seconds: int = 3600) -> bool:
    """Wait for job completion, polling status."""
    try:
        from src.control.supervisor import get_job
        
        start_time = time.time()
        poll_interval = 2.0  # seconds
        
        while time.time() - start_time < timeout_seconds:
            job = get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return False
            
            logger.info(f"Job {job_id} state: {job.state}")
            
            if job.state == "SUCCEEDED":
                logger.info(f"Job {job_id} succeeded")
                return True
            elif job.state == "FAILED":
                logger.error(f"Job {job_id} failed: {job.state_reason}")
                return False
            elif job.state == "ABORTED":
                logger.warning(f"Job {job_id} was aborted")
                return False
            elif job.state == "ORPHANED":
                logger.error(f"Job {job_id} was orphaned")
                return False
            
            # Job is still running or queued
            time.sleep(poll_interval)
        
        logger.error(f"Timeout waiting for job {job_id}")
        return False
        
    except Exception as e:
        logger.error(f"Error while waiting for job: {e}")
        return False


def main() -> int:
    """Main entry point - submits job to Supervisor and waits for completion."""
    logger.warning("=" * 80)
    logger.warning("DEPRECATED: run_research_v3.py is deprecated.")
    logger.warning("This script no longer executes research logic directly.")
    logger.warning("Instead, it submits a RUN_RESEARCH_V2 job to Supervisor v2.")
    logger.warning("=" * 80)
    
    try:
        # Submit job to Supervisor
        job_id = submit_run_research_v2_job()
        
        # Wait for job completion
        success = wait_for_job_completion(job_id)
        
        if success:
            logger.info("Research job completed successfully via Supervisor v2")
            return 0
        else:
            logger.error("Research job failed via Supervisor v2")
            return 1
            
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
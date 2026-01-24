
import time
import sys
import json
import logging
from pathlib import Path

# Setup paths
src_path = str(Path.cwd() / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from control.supervisor.db import get_default_db_path, SupervisorDB
from control.supervisor.models import JobSpec, JobStatus

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def wait_for_job(db: SupervisorDB, job_id: str, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        job = db.get_job_row(job_id)
        if not job:
            logger.error(f"Job {job_id} disappeared!")
            return None
        
        logger.info(f"Job {job_id} State: {job.state} Progress: {job.progress}")
        
        if job.state == JobStatus.SUCCEEDED:
            logger.info(f"Job {job_id} SUCCEEDED!")
            return job
        elif job.state in [JobStatus.FAILED, JobStatus.ABORTED, JobStatus.ORPHANED, JobStatus.REJECTED]:
            logger.error(f"Job {job_id} terminated with {job.state}")
            return job
            
        time.sleep(2)
    
    logger.error(f"Job {job_id} timed out")
    return None

def main():
    db_path = get_default_db_path()
    db = SupervisorDB(db_path)
    
    # 1. RUN_RESEARCH_WFS
    logger.info("Submitting RUN_RESEARCH_WFS...")
    # Using specific params from verifying data existence
    wfs_params = {
        "strategy_id": "s1_v1",
        "instrument": "CME.MNQ",
        "timeframe": "15m",
        "start_season": "2026Q1",
        "end_season": "2026Q1",
        "season": "2026Q1",
        "dataset_id": "CME.MNQ",
        "workers": 1
    }
    
    wfs_spec = JobSpec(
        job_type="RUN_RESEARCH_WFS",
        params=wfs_params
    )
    
    wfs_job_id = db.submit_job(wfs_spec)
    logger.info(f"Submitted WFS Job: {wfs_job_id}")
    
    # Monitor WFS
    wfs_result = wait_for_job(db, wfs_job_id, timeout=600)
    if not wfs_result or wfs_result.state != JobStatus.SUCCEEDED:
        logger.error("WFS Failed. Aborting loop.")
        sys.exit(1)
        
    # 2. BUILD_PORTFOLIO_V2
    logger.info("Submitting BUILD_PORTFOLIO_V2...")
    port_params = {
        "season": "2026Q1",
        "candidate_run_ids": [wfs_job_id],
        "timeframe": "15m",
        "allowlist": []
    }
    
    port_spec = JobSpec(
        job_type="BUILD_PORTFOLIO_V2",
        params=port_params
    )
    
    port_job_id = db.submit_job(port_spec)
    logger.info(f"Submitted Portfolio Job: {port_job_id}")
    
    # Monitor Portfolio
    port_result = wait_for_job(db, port_job_id, timeout=120)
    if not port_result or port_result.state != JobStatus.SUCCEEDED:
        logger.error("Portfolio Build Failed.")
        sys.exit(1)
        
    logger.info("FULL LOOP COMPLETED SUCCESSFULLY")

if __name__ == "__main__":
    main()

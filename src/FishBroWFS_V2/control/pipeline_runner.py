"""Pipeline Runner for M1 Wizard.

Stub implementation for job pipeline execution.
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional
from pathlib import Path

from FishBroWFS_V2.control.jobs_db import (
    get_job, mark_running, mark_done, mark_failed, append_log
)
from FishBroWFS_V2.control.job_api import calculate_units
from FishBroWFS_V2.control.artifacts_api import write_research_index


class PipelineRunner:
    """Simple pipeline runner for M1 demonstration."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize pipeline runner.
        
        Args:
            db_path: Path to SQLite database. If None, uses default.
        """
        self.db_path = db_path or Path("outputs/jobs.db")
    
    def run_job(self, job_id: str) -> bool:
        """Run a job (stub implementation for M1).
        
        This is a simplified runner that simulates job execution
        for demonstration purposes.
        
        Args:
            job_id: Job ID to run
            
        Returns:
            True if job completed successfully, False otherwise
        """
        try:
            # Get job record
            job = get_job(self.db_path, job_id)
            
            # Mark as running
            mark_running(self.db_path, job_id, pid=12345)
            self._log(job_id, f"Job {job_id} started")
            
            # Simulate work based on units
            units = 0
            if hasattr(job.spec, 'config_snapshot'):
                config = job.spec.config_snapshot
                if isinstance(config, dict) and 'units' in config:
                    units = config.get('units', 10)
            
            # Default to 10 units if not specified
            if units <= 0:
                units = 10
            
            self._log(job_id, f"Processing {units} units")
            
            # Simulate unit processing
            for i in range(units):
                time.sleep(0.1)  # Simulate work
                progress = (i + 1) / units
                if i % max(1, units // 10) == 0:  # Log every ~10%
                    self._log(job_id, f"Unit {i+1}/{units} completed ({progress:.0%})")
            
            # Mark as done
            mark_done(self.db_path, job_id, run_id=f"run_{job_id}", report_link=f"/reports/{job_id}")
            
            # Write research index (M2)
            try:
                season = job.spec.season if hasattr(job.spec, 'season') else "default"
                # Generate dummy units based on config snapshot
                units = []
                if hasattr(job.spec, 'config_snapshot'):
                    config = job.spec.config_snapshot
                    if isinstance(config, dict):
                        # Extract possible symbols, timeframes, etc.
                        data1 = config.get('data1', {})
                        symbols = data1.get('symbols', ['MNQ'])
                        timeframes = data1.get('timeframes', ['60m'])
                        strategy = config.get('strategy_id', 'vPB_Z')
                        data2_filters = config.get('data2', {}).get('filters', ['VX'])
                        # Create one unit per combination (simplified)
                        for sym in symbols[:1]:  # limit
                            for tf in timeframes[:1]:
                                for filt in data2_filters[:1]:
                                    units.append({
                                        'data1_symbol': sym,
                                        'data1_timeframe': tf,
                                        'strategy': strategy,
                                        'data2_filter': filt,
                                        'status': 'DONE',
                                        'artifacts': {
                                            'canonical_results': f'outputs/seasons/{season}/research/{job_id}/{sym}/{tf}/{strategy}/{filt}/canonical_results.json',
                                            'metrics': f'outputs/seasons/{season}/research/{job_id}/{sym}/{tf}/{strategy}/{filt}/metrics.json',
                                            'trades': f'outputs/seasons/{season}/research/{job_id}/{sym}/{tf}/{strategy}/{filt}/trades.parquet',
                                        }
                                    })
                if not units:
                    # Fallback dummy unit
                    units.append({
                        'data1_symbol': 'MNQ',
                        'data1_timeframe': '60m',
                        'strategy': 'vPB_Z',
                        'data2_filter': 'VX',
                        'status': 'DONE',
                        'artifacts': {
                            'canonical_results': f'outputs/seasons/{season}/research/{job_id}/MNQ/60m/vPB_Z/VX/canonical_results.json',
                            'metrics': f'outputs/seasons/{season}/research/{job_id}/MNQ/60m/vPB_Z/VX/metrics.json',
                            'trades': f'outputs/seasons/{season}/research/{job_id}/MNQ/60m/vPB_Z/VX/trades.parquet',
                        }
                    })
                write_research_index(season, job_id, units)
                self._log(job_id, f"Research index written for {len(units)} units")
            except Exception as e:
                self._log(job_id, f"Failed to write research index: {e}")
            
            self._log(job_id, f"Job {job_id} completed successfully")
            
            return True
            
        except Exception as e:
            # Mark as failed
            error_msg = f"Job failed: {str(e)}"
            try:
                mark_failed(self.db_path, job_id, error=error_msg)
                self._log(job_id, error_msg)
            except Exception:
                pass  # Ignore errors during failure marking
            
            return False
    
    def _log(self, job_id: str, message: str) -> None:
        """Add log entry for job."""
        try:
            append_log(self.db_path, job_id, message)
        except Exception:
            pass  # Ignore log errors
    
    def get_job_progress(self, job_id: str) -> Dict[str, Any]:
        """Get job progress information.
        
        Args:
            job_id: Job ID
            
        Returns:
            Dictionary with progress information
        """
        try:
            job = get_job(self.db_path, job_id)
            
            # Calculate progress based on status
            units_total = 0
            units_done = 0
            
            if hasattr(job.spec, 'config_snapshot'):
                config = job.spec.config_snapshot
                if isinstance(config, dict) and 'units' in config:
                    units_total = config.get('units', 0)
            
            if job.status.value == "DONE":
                units_done = units_total
            elif job.status.value == "RUNNING":
                # For stub, estimate 50% progress
                units_done = units_total // 2 if units_total > 0 else 0
            
            progress = units_done / units_total if units_total > 0 else 0
            
            return {
                "job_id": job_id,
                "status": job.status.value,
                "units_done": units_done,
                "units_total": units_total,
                "progress": progress,
                "is_running": job.status.value == "RUNNING",
                "is_done": job.status.value == "DONE",
                "is_failed": job.status.value == "FAILED"
            }
        except Exception as e:
            return {
                "job_id": job_id,
                "status": "UNKNOWN",
                "units_done": 0,
                "units_total": 0,
                "progress": 0,
                "is_running": False,
                "is_done": False,
                "is_failed": True,
                "error": str(e)
            }


# Singleton instance
_runner_instance: Optional[PipelineRunner] = None

def get_pipeline_runner() -> PipelineRunner:
    """Get singleton pipeline runner instance."""
    global _runner_instance
    if _runner_instance is None:
        _runner_instance = PipelineRunner()
    return _runner_instance


def start_job_async(job_id: str) -> None:
    """Start job execution asynchronously (stub).
    
    In a real implementation, this would spawn a worker process.
    For M1, we'll just simulate immediate execution.
    
    Args:
        job_id: Job ID to start
    """
    # In a real implementation, this would use a task queue or worker pool
    # For M1 demo, we'll run synchronously
    runner = get_pipeline_runner()
    runner.run_job(job_id)


def check_job_status(job_id: str) -> Dict[str, Any]:
    """Check job status (convenience wrapper).
    
    Args:
        job_id: Job ID
        
    Returns:
        Dictionary with job status and progress
    """
    runner = get_pipeline_runner()
    return runner.get_job_progress(job_id)
"""
Data Prepare Service for explicit, governed data preparation workflow.

Implements Route 4: Data Prepare as First-Class Citizen.
- Prepare is explicit (never implicit)
- Prepare is separate from Run
- Prepare completion is required before Run unlocks
- Explain Hub tells users why data is stale/missing and what will be built

Service Responsibilities:
- Accept a DerivedDataset (from DatasetResolver)
- Execute a bounded prepare command (CLI or callable already in repo)
- Emit progress + completion signals
- Write a small prepare result artifact (for UI state restoration)
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Literal

from PySide6.QtCore import QObject, Signal, QTimer

from gui.services.supervisor_client import (
    SupervisorClientError,
    submit_job,
    get_job,
    abort_job
)
from gui.services.dataset_resolver import DerivedDatasets, DatasetStatus

logger = logging.getLogger(__name__)


class PrepareStatus(str, Enum):
    """Status of a dataset preparation."""
    READY = "READY"
    MISSING = "MISSING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    PREPARING = "PREPARING"  # new, transient
    FAILED = "FAILED"        # new, terminal until retried


@dataclass(frozen=True)
class PrepareResult:
    """Result of a dataset preparation."""
    dataset_key: str  # "DATA1" or "DATA2"
    dataset_id: Optional[str]
    success: bool
    status: PrepareStatus
    message: str
    job_id: Optional[str] = None
    artifact_path: Optional[str] = None
    timestamp: Optional[str] = None


class DataPrepareService(QObject):
    """
    Service for explicit data preparation with progress reporting.
    
    Signals:
    - progress: Emitted during preparation (dataset_key, percent)
    - finished: Emitted when preparation completes (dataset_key, success, message)
    - status_changed: Emitted when dataset status changes (dataset_key, new_status)
    """
    
    # Signals
    progress = Signal(str, int)   # dataset_key, percent
    finished = Signal(str, bool, str)  # dataset_key, success, message
    status_changed = Signal(str, str)  # dataset_key, new_status
    
    def __init__(self, outputs_root: Optional[Path] = None):
        super().__init__()
        self.outputs_root = outputs_root or Path("outputs")
        self.prepare_artifacts_dir = self.outputs_root / "_runtime" / "data_prepare"
        self.prepare_artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Active preparations tracking
        self._active_preparations: Dict[str, str] = {}  # dataset_key -> job_id
        self._prepare_results: Dict[str, PrepareResult] = {}
        
        # Timer for polling job status
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_active_preparations)
        self._poll_timer.start(2000)  # Poll every 2 seconds
    
    def prepare(self, dataset_key: str, derived: DerivedDatasets) -> None:
        """
        Prepare a dataset (DATA1 or DATA2).
        
        Args:
            dataset_key: "DATA1" or "DATA2"
            derived: DerivedDatasets from DatasetResolver
        """
        # Determine which dataset to prepare
        if dataset_key == "DATA1":
            dataset_id = derived.data1_id
            current_status = derived.data1_status
        elif dataset_key == "DATA2":
            dataset_id = derived.data2_id
            current_status = derived.data2_status
        else:
            logger.error(f"Invalid dataset_key: {dataset_key}")
            self.finished.emit(dataset_key, False, f"Invalid dataset key: {dataset_key}")
            return
        
        # Validate dataset_id
        if not dataset_id:
            logger.error(f"Cannot prepare {dataset_key}: dataset_id is None")
            self.finished.emit(dataset_key, False, f"No dataset ID for {dataset_key}")
            return
        
        # Check if already preparing
        if dataset_key in self._active_preparations:
            logger.warning(f"{dataset_key} is already being prepared")
            self.finished.emit(dataset_key, False, f"{dataset_key} is already being prepared")
            return
        
        # Determine prepare action based on current status
        if current_status == DatasetStatus.READY:
            logger.info(f"{dataset_key} ({dataset_id}) is already READY, no preparation needed")
            self.finished.emit(dataset_key, True, f"{dataset_key} is already READY")
            return
        
        # Emit status change
        self.status_changed.emit(dataset_key, PrepareStatus.PREPARING.value)
        
        # Submit BUILD_DATA job via supervisor
        try:
            job_payload = self._build_job_payload(dataset_id, current_status)
            logger.info(f"Submitting BUILD_DATA job for {dataset_key} ({dataset_id})")
            
            # Submit job
            response = submit_job(job_payload)
            job_id = response.get("job_id")
            
            if not job_id:
                raise SupervisorClientError(f"No job_id in response: {response}")
            
            # Track active preparation
            self._active_preparations[dataset_key] = job_id
            
            # Store initial result
            self._prepare_results[dataset_key] = PrepareResult(
                dataset_key=dataset_key,
                dataset_id=dataset_id,
                success=False,
                status=PrepareStatus.PREPARING,
                message=f"Preparation started for {dataset_id}",
                job_id=job_id,
                timestamp=datetime.now().isoformat()
            )
            
            # Write initial artifact
            self._write_prepare_artifact(dataset_key)
            
            logger.info(f"Started preparation for {dataset_key} ({dataset_id}), job_id={job_id}")
            self.progress.emit(dataset_key, 10)  # Initial progress
            
        except Exception as e:
            logger.error(f"Failed to start preparation for {dataset_key}: {e}")
            self.status_changed.emit(dataset_key, PrepareStatus.FAILED.value)
            self.finished.emit(dataset_key, False, f"Failed to start preparation: {e}")
    
    def _build_job_payload(self, dataset_id: str, current_status: DatasetStatus) -> Dict[str, Any]:
        """
        Build BUILD_DATA job payload based on dataset status.
        
        Rules:
        - MISSING/UNKNOWN -> Build Cache (full build)
        - STALE -> Rebuild Cache (force rebuild)
        - READY -> No action needed (should not be called)
        """
        payload = {
            "job_type": "BUILD_DATA",
            "dataset_id": dataset_id,
            "timeframe_min": 60,  # Default timeframe
            "mode": "FULL"
        }
        
        if current_status in [DatasetStatus.MISSING, DatasetStatus.UNKNOWN]:
            # Build cache
            payload["force_rebuild"] = False
        elif current_status == DatasetStatus.STALE:
            # Rebuild cache
            payload["force_rebuild"] = True
        else:
            # Should not happen for PREPARING
            payload["force_rebuild"] = False
        
        return payload
    
    def _poll_active_preparations(self):
        """Poll status of active preparations."""
        if not self._active_preparations:
            return
        
        for dataset_key, job_id in list(self._active_preparations.items()):
            try:
                # Get job details
                job = get_job(job_id)
                state = job.get("state")
                
                if state == "COMPLETED":
                    # Job completed successfully
                    self._handle_job_completion(dataset_key, job_id, success=True)
                    
                elif state == "FAILED":
                    # Job failed
                    self._handle_job_completion(dataset_key, job_id, success=False)
                    
                elif state in ["RUNNING", "QUEUED"]:
                    # Still running, update progress
                    progress = job.get("progress", 0)
                    self.progress.emit(dataset_key, progress)
                    
                else:
                    # Unknown status
                    logger.warning(f"Unknown job state for {dataset_key}: {state}")
                    
            except Exception as e:
                logger.error(f"Failed to poll job status for {dataset_key}: {e}")
    
    def _handle_job_completion(self, dataset_key: str, job_id: str, success: bool):
        """Handle job completion (success or failure)."""
        # Remove from active preparations
        if dataset_key in self._active_preparations:
            del self._active_preparations[dataset_key]
        
        # Get result from storage
        result = self._prepare_results.get(dataset_key)
        
        if success:
            new_status = PrepareStatus.READY
            message = f"Preparation completed successfully for {result.dataset_id if result else dataset_key}"
            logger.info(f"Preparation succeeded for {dataset_key}")
        else:
            new_status = PrepareStatus.FAILED
            message = f"Preparation failed for {result.dataset_id if result else dataset_key}"
            logger.error(f"Preparation failed for {dataset_key}")
        
        # Update result
        if result:
            updated_result = PrepareResult(
                dataset_key=dataset_key,
                dataset_id=result.dataset_id,
                success=success,
                status=new_status,
                message=message,
                job_id=job_id,
                artifact_path=str(self._get_artifact_path(dataset_key)),
                timestamp=datetime.now().isoformat()
            )
            self._prepare_results[dataset_key] = updated_result
        else:
            # Create new result if not found
            self._prepare_results[dataset_key] = PrepareResult(
                dataset_key=dataset_key,
                dataset_id=None,
                success=success,
                status=new_status,
                message=message,
                job_id=job_id,
                artifact_path=str(self._get_artifact_path(dataset_key)),
                timestamp=datetime.now().isoformat()
            )
        
        # Write artifact
        self._write_prepare_artifact(dataset_key)
        
        # Emit signals
        self.status_changed.emit(dataset_key, new_status.value)
        self.finished.emit(dataset_key, success, message)
        self.progress.emit(dataset_key, 100 if success else 0)
    
    def _write_prepare_artifact(self, dataset_key: str):
        """Write prepare result artifact to disk."""
        result = self._prepare_results.get(dataset_key)
        if not result:
            return
        
        artifact_path = self._get_artifact_path(dataset_key)
        try:
            # Convert result to dict
            result_dict = {
                "dataset_key": result.dataset_key,
                "dataset_id": result.dataset_id,
                "success": result.success,
                "status": result.status.value,
                "message": result.message,
                "job_id": result.job_id,
                "artifact_path": result.artifact_path,
                "timestamp": result.timestamp or datetime.now().isoformat()
            }
            
            with open(artifact_path, "w") as f:
                json.dump(result_dict, f, indent=2, sort_keys=True)
                
            logger.debug(f"Wrote prepare artifact for {dataset_key} to {artifact_path}")
            
        except Exception as e:
            logger.error(f"Failed to write prepare artifact for {dataset_key}: {e}")
    
    def _get_artifact_path(self, dataset_key: str) -> Path:
        """Get path for prepare artifact."""
        return self.prepare_artifacts_dir / f"{dataset_key.lower()}_prepare_result.json"
    
    def get_prepare_status(self, dataset_key: str) -> Optional[PrepareStatus]:
        """Get current prepare status for a dataset."""
        result = self._prepare_results.get(dataset_key)
        if result:
            return result.status
        
        # Check if there's a stored artifact
        artifact_path = self._get_artifact_path(dataset_key)
        if artifact_path.exists():
            try:
                with open(artifact_path, "r") as f:
                    artifact = json.load(f)
                return PrepareStatus(artifact.get("status", PrepareStatus.UNKNOWN.value))
            except Exception as e:
                logger.error(f"Failed to read prepare artifact for {dataset_key}: {e}")
        
        return None
    
    def get_prepare_result(self, dataset_key: str) -> Optional[PrepareResult]:
        """Get prepare result for a dataset."""
        result = self._prepare_results.get(dataset_key)
        if result:
            return result
        
        # Try to load from artifact
        artifact_path = self._get_artifact_path(dataset_key)
        if artifact_path.exists():
            try:
                with open(artifact_path, "r") as f:
                    artifact = json.load(f)
                
                return PrepareResult(
                    dataset_key=artifact.get("dataset_key", dataset_key),
                    dataset_id=artifact.get("dataset_id"),
                    success=artifact.get("success", False),
                    status=PrepareStatus(artifact.get("status", PrepareStatus.UNKNOWN.value)),
                    message=artifact.get("message", ""),
                    job_id=artifact.get("job_id"),
                    artifact_path=artifact.get("artifact_path"),
                    timestamp=artifact.get("timestamp")
                )
            except Exception as e:
                logger.error(f"Failed to load prepare result for {dataset_key}: {e}")
        
        return None
    
    def cancel_preparation(self, dataset_key: str) -> bool:
        """Cancel an active preparation."""
        if dataset_key not in self._active_preparations:
            return False
        
        job_id = self._active_preparations[dataset_key]
        logger.info(f"Cancelling preparation for {dataset_key}, job_id={job_id}")
        
        try:
            # Call abort_job to request supervisor to abort the job
            abort_job(job_id)
            logger.info(f"Abort request sent for job {job_id}")
        except Exception as e:
            logger.warning(f"Failed to send abort request for job {job_id}: {e}")
            # Continue with local cancellation even if abort request fails
        
        # Remove from tracking
        del self._active_preparations[dataset_key]
        
        # Update result
        result = self._prepare_results.get(dataset_key)
        if result:
            self._prepare_results[dataset_key] = PrepareResult(
                dataset_key=dataset_key,
                dataset_id=result.dataset_id,
                success=False,
                status=PrepareStatus.FAILED,
                message=f"Preparation cancelled by user",
                job_id=job_id,
                timestamp=datetime.now().isoformat()
            )
        
        # Emit signals
        self.status_changed.emit(dataset_key, PrepareStatus.FAILED.value)
        self.finished.emit(dataset_key, False, "Preparation cancelled")
        
        return True
    
    def clear_result(self, dataset_key: str) -> bool:
        """Clear prepare result for a dataset (allow retry)."""
        if dataset_key in self._prepare_results:
            del self._prepare_results[dataset_key]
        
        # Delete artifact
        artifact_path = self._get_artifact_path(dataset_key)
        if artifact_path.exists():
            try:
                artifact_path.unlink()
                return True
            except Exception as e:
                logger.error(f"Failed to delete artifact for {dataset_key}: {e}")
                return False
        
        return True


# Singleton instance for convenience
_data_prepare_service = None


def get_data_prepare_service() -> DataPrepareService:
    """Return the singleton data prepare service instance."""
    global _data_prepare_service
    if _data_prepare_service is None:
        _data_prepare_service = DataPrepareService()
    return _data_prepare_service
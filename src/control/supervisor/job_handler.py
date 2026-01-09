from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import json
from pathlib import Path
from .models import JobSpec, JobStatus
from .artifact_writer import CanonicalArtifactWriter


HANDLER_REGISTRY: dict[str, "BaseJobHandler"] = {}


class JobContext:
    """
    Runtime context for handler execution.
    IMPORTANT: Handlers MUST NOT mutate job state directly.
    They may only:
      - write heartbeat via ctx.heartbeat()
      - check abort via ctx.is_abort_requested()
      - write artifacts only under ctx.artifacts_dir
    """
    def __init__(self, job_id: str, db: Any, artifacts_dir: str, writer: Optional[CanonicalArtifactWriter] = None):
        self.job_id = job_id
        self._db = db
        self.artifacts_dir = artifacts_dir
        self._writer = writer

    def heartbeat(self, progress: float | None = None, phase: str | None = None) -> None:
        self._db.update_heartbeat(self.job_id, progress=progress, phase=phase)
        # Also write state.json snapshot
        if self._writer is not None:
            self._writer.write_state(JobStatus.RUNNING, progress=progress, phase=phase)

    def is_abort_requested(self) -> bool:
        return self._db.is_abort_requested(self.job_id)


class BaseJobHandler(ABC):
    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate job parameters before execution."""
        pass

    @abstractmethod
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute the job and return result dict."""
        pass


def register_handler(job_type: str, handler: BaseJobHandler) -> None:
    if not job_type or not isinstance(job_type, str):
        raise ValueError("job_type must be non-empty str")
    HANDLER_REGISTRY[job_type] = handler


def get_handler(job_type: str) -> Optional[BaseJobHandler]:
    return HANDLER_REGISTRY.get(job_type)


def validate_job_spec(spec: JobSpec) -> None:
    """Validate job spec before submission."""
    if not spec.job_type:
        raise ValueError("job_type is required")
    if not isinstance(spec.params, dict):
        raise ValueError("params must be a dict")
    # Check if handler exists
    handler = get_handler(spec.job_type)
    if handler is None:
        raise ValueError(f"Unknown job_type: {spec.job_type}")
    # Validate params with handler
    handler.validate_params(spec.params)


def execute_job(job_id: str, spec: JobSpec, db: Any, artifacts_dir: str) -> Dict[str, Any]:
    """Execute a job using its handler."""
    handler = get_handler(spec.job_type)
    if handler is None:
        raise ValueError(f"No handler registered for job_type: {spec.job_type}")
    
    # Convert artifacts_dir to Path
    artifacts_path = Path(artifacts_dir)
    
    # Create artifact writer and write spec.json, state.json (RUNNING)
    writer = CanonicalArtifactWriter(job_id, spec, artifacts_path)
    writer.write_spec()
    writer.write_state(JobStatus.RUNNING, progress=0.0, phase="start")
    
    # Execute with captured stdout/stderr
    context = JobContext(job_id, db, artifacts_dir, writer=writer)
    try:
        with writer:
            result = handler.execute(spec.params, context)
    except Exception as e:
        # Write state with FAILED
        writer.write_state(JobStatus.FAILED, error=str(e))
        raise
    
    # Write state with SUCCEEDED and result
    writer.write_state(JobStatus.SUCCEEDED, progress=100.0, phase="complete")
    writer.write_result(result)
    return result
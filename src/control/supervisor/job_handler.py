from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import json
from .models import JobSpec


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
    def __init__(self, job_id: str, db: Any, artifacts_dir: str):
        self.job_id = job_id
        self._db = db
        self.artifacts_dir = artifacts_dir

    def heartbeat(self, progress: float | None = None, phase: str | None = None) -> None:
        self._db.update_heartbeat(self.job_id, progress=progress, phase=phase)

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
    
    context = JobContext(job_id, db, artifacts_dir)
    return handler.execute(spec.params, context)
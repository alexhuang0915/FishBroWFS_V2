"""
Job SSOT Store - Single source of truth for job lifecycle and UI state.
Matches GO AI Execution Spec Phase 2.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Literal
from PySide6.QtCore import QObject, Signal

JobStatus = Literal["queued", "running", "done", "failed", "canceled"]

@dataclass
class JobRecord:
    job_id: str
    job_type: str
    created_at: datetime
    status: JobStatus
    progress_stage: str = ""
    summary: str = ""
    artifact_dir: Optional[str] = None
    error_digest: Optional[str] = None

class JobStore(QObject):
    """
    In-memory store for UI Job records. 
    Enforces Job SSOT across all 5 target tabs.
    """
    jobs_changed = Signal()
    selected_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._jobs: Dict[str, JobRecord] = {}
        self._selected_id: Optional[str] = None

    def upsert(self, job: JobRecord) -> None:
        """Add or update a job record. Emits jobs_changed."""
        self._jobs[job.job_id] = job
        self.jobs_changed.emit()

    def set_selected(self, job_id: str) -> None:
        """Update the focused job. Emits selected_changed."""
        if job_id in self._jobs:
            self._selected_id = job_id
            self.selected_changed.emit(job_id)

    def get_selected(self) -> Optional[JobRecord]:
        """Return the currently focused JobRecord."""
        if self._selected_id is None:
            return None
        return self._jobs.get(self._selected_id)

    def list_jobs(self) -> List[JobRecord]:
        """Return all jobs sorted by creation time (newest first)."""
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

# Global singleton instance
job_store = JobStore()

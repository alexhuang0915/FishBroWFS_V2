"""
Job Lifecycle Service - UI‑owned management of job archive/restore/purge.

Implements Hybrid BC v1.1 job lifecycle semantics:
- ACTIVE: job directory exists under outputs/jobs/<job_id>/
- ARCHIVED: job directory moved to outputs/jobs/_trash/<job_id>/
- PURGED: job directory deleted from filesystem (requires ENABLE_PURGE_ACTION=1)
- Tombstone: after purge, a tombstone JSON file stored at outputs/_runtime/job_lifecycle/tombstones/<job_id>.json
- Lifecycle index: outputs/_runtime/job_lifecycle/index.json tracks job_id -> status (ACTIVE/ARCHIVED/PURGED) + timestamps

All operations are local filesystem moves/deletes; no backend API changes.
"""

import json
import os
import shutil
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, TypedDict, Literal, Any

logger = logging.getLogger(__name__)


class JobLifecycleState(str, Enum):
    """Job lifecycle states."""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    PURGED = "PURGED"


class TombstoneRecord(TypedDict):
    """Tombstone record for a purged job."""
    job_id: str
    purged_at: str  # ISO timestamp
    purged_by: str  # "ui" or "system"
    reason: str
    original_path: str  # path before purge (relative to outputs/jobs/)


class LifecycleEntry(TypedDict):
    """Entry in the lifecycle index."""
    job_id: str
    state: JobLifecycleState
    created_at: str  # ISO timestamp of job creation (approximate)
    archived_at: Optional[str]
    purged_at: Optional[str]
    last_updated: str


class JobLifecycleService:
    """Service for managing job lifecycle (archive/restore/purge)."""
    
    def __init__(self, outputs_root: Optional[Path] = None):
        from core.paths import get_artifacts_root, get_runtime_root, get_jobs_dir
        
        self.outputs_root = outputs_root or Path("outputs") # Kept for reference but we use specific roots
        
        # New structure:
        # jobs -> outputs/artifacts/jobs
        # trash -> outputs/artifacts/jobs/_trash (co-located with jobs for atomic moves)
        # runtime -> outputs/runtime/job_lifecycle
        
        self.jobs_root = get_jobs_dir()
        self.trash_root = self.jobs_root / "_trash"
        self.runtime_root = get_runtime_root() / "job_lifecycle"
        self.tombstones_dir = self.runtime_root / "tombstones"
        self.index_path = self.runtime_root / "index.json"
        
        # Ensure directories exist
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.trash_root.mkdir(parents=True, exist_ok=True)
        self.tombstones_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        
        # Load or create index
        self._index: Dict[str, LifecycleEntry] = self._load_index()
    
    def _load_index(self) -> Dict[str, LifecycleEntry]:
        """Load lifecycle index from disk."""
        if not self.index_path.exists():
            return {}
        try:
            with open(self.index_path, "r") as f:
                data = json.load(f)
            # Validate structure
            index = {}
            for job_id, entry in data.items():
                # Ensure state is valid
                state = JobLifecycleState(entry.get("state", JobLifecycleState.ACTIVE))
                index[job_id] = {
                    "job_id": job_id,
                    "state": state,
                    "created_at": entry.get("created_at", ""),
                    "archived_at": entry.get("archived_at"),
                    "purged_at": entry.get("purged_at"),
                    "last_updated": entry.get("last_updated", ""),
                }
            return index
        except Exception as e:
            logger.error(f"Failed to load lifecycle index: {e}")
            return {}
    
    def _save_index(self) -> None:
        """Save lifecycle index to disk."""
        try:
            with open(self.index_path, "w") as f:
                json.dump(self._index, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.error(f"Failed to save lifecycle index: {e}")
    
    def _update_index_entry(
        self,
        job_id: str,
        state: JobLifecycleState,
        archived_at: Optional[str] = None,
        purged_at: Optional[str] = None,
    ) -> None:
        """Update or create an index entry."""
        now = datetime.now().isoformat()
        if job_id in self._index:
            entry = self._index[job_id]
            entry["state"] = state
            entry["last_updated"] = now
            if archived_at:
                entry["archived_at"] = archived_at
            if purged_at:
                entry["purged_at"] = purged_at
        else:
            # Guess creation time from directory mtime
            created_at = now
            job_dir = self.jobs_root / job_id
            if job_dir.exists():
                created_at = datetime.fromtimestamp(job_dir.stat().st_mtime).isoformat()
            elif (self.trash_root / job_id).exists():
                created_at = datetime.fromtimestamp((self.trash_root / job_id).stat().st_mtime).isoformat()
            
            self._index[job_id] = {
                "job_id": job_id,
                "state": state,
                "created_at": created_at,
                "archived_at": archived_at,
                "purged_at": purged_at,
                "last_updated": now,
            }
        self._save_index()
    
    def _write_tombstone(self, job_id: str, original_path: Path, reason: str = "user") -> None:
        """Write a tombstone record for a purged job."""
        tombstone: TombstoneRecord = {
            "job_id": job_id,
            "purged_at": datetime.now().isoformat(),
            "purged_by": "ui",
            "reason": reason,
            "original_path": str(original_path.relative_to(self.outputs_root)),
        }
        tombstone_path = self.tombstones_dir / f"{job_id}.json"
        try:
            with open(tombstone_path, "w") as f:
                json.dump(tombstone, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.error(f"Failed to write tombstone for {job_id}: {e}")
    
    def get_job_state(self, job_id: str) -> JobLifecycleState:
        """Get current lifecycle state of a job."""
        if job_id in self._index:
            return self._index[job_id]["state"]
        # Infer from filesystem
        if (self.jobs_root / job_id).exists():
            return JobLifecycleState.ACTIVE
        if (self.trash_root / job_id).exists():
            return JobLifecycleState.ARCHIVED
        # Not found anywhere
        return JobLifecycleState.PURGED  # assume purged if not present
    
    def archive_job(self, job_id: str) -> bool:
        """
        Archive a job (move to _trash).
        
        Returns True on success, False on failure.
        """
        source = self.jobs_root / job_id
        dest = self.trash_root / job_id
        
        if not source.exists():
            logger.warning(f"Cannot archive job {job_id}: source directory does not exist")
            return False
        
        if dest.exists():
            logger.warning(f"Cannot archive job {job_id}: already exists in trash")
            return False
        
        try:
            shutil.move(str(source), str(dest))
            logger.info(f"Archived job {job_id} to {dest}")
            self._update_index_entry(
                job_id,
                JobLifecycleState.ARCHIVED,
                archived_at=datetime.now().isoformat(),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to archive job {job_id}: {e}")
            return False
    
    def restore_job(self, job_id: str) -> bool:
        """
        Restore an archived job (move back to active).
        
        Returns True on success, False on failure.
        """
        source = self.trash_root / job_id
        dest = self.jobs_root / job_id
        
        if not source.exists():
            logger.warning(f"Cannot restore job {job_id}: not found in trash")
            return False
        
        if dest.exists():
            logger.warning(f"Cannot restore job {job_id}: active directory already exists")
            return False
        
        try:
            shutil.move(str(source), str(dest))
            logger.info(f"Restored job {job_id} to {dest}")
            self._update_index_entry(job_id, JobLifecycleState.ACTIVE)
            return True
        except Exception as e:
            logger.error(f"Failed to restore job {job_id}: {e}")
            return False
    
    def purge_job(self, job_id: str, reason: str = "user") -> bool:
        """
        Permanently delete an archived job.
        
        Requires environment variable ENABLE_PURGE_ACTION=1.
        Returns True on success, False on failure.
        """
        if os.environ.get("ENABLE_PURGE_ACTION") != "1":
            logger.warning("Purge action disabled (ENABLE_PURGE_ACTION != 1)")
            return False
        
        source = self.trash_root / job_id
        if not source.exists():
            logger.warning(f"Cannot purge job {job_id}: not found in trash")
            return False
        
        # Write tombstone before deletion
        self._write_tombstone(job_id, source, reason)
        
        try:
            shutil.rmtree(source)
            logger.info(f"Purged job {job_id} from {source}")
            self._update_index_entry(
                job_id,
                JobLifecycleState.PURGED,
                purged_at=datetime.now().isoformat(),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to purge job {job_id}: {e}")
            return False
    
    def list_active_jobs(self) -> List[str]:
        """List job IDs that are currently active (excluding underscore-prefixed directories)."""
        if not self.jobs_root.exists():
            return list()
        jobs = list()
        for entry in self.jobs_root.iterdir():
            if not entry.is_dir():
                continue
            # Red Team constraint: skip folders starting with '_'
            if entry.name.startswith("_"):
                continue
            # Also skip hidden directories (starting with '.')
            if entry.name.startswith("."):
                continue
            jobs.append(entry.name)
        return jobs
    
    def list_archived_jobs(self) -> List[str]:
        """List job IDs that are archived."""
        if not self.trash_root.exists():
            return list()
        jobs = list()
        for entry in self.trash_root.iterdir():
            if entry.is_dir():
                jobs.append(entry.name)
        return jobs
    
    def get_index_entry(self, job_id: str) -> Optional[LifecycleEntry]:
        """Get lifecycle index entry for a job."""
        return self._index.get(job_id)
    
    def get_all_index_entries(self) -> Dict[str, LifecycleEntry]:
        """Get all lifecycle index entries."""
        return self._index.copy()
    
    def get_job_ids_by_state(self, state: JobLifecycleState) -> List[str]:
        """Get all job IDs with the given lifecycle state."""
        return [job_id for job_id, entry in self._index.items() if entry["state"] == state]
    
    def sync_index_with_filesystem(self) -> None:
        """
        Synchronize index with actual filesystem state.
        
        This ensures that if a job directory was moved/deleted outside the UI,
        the index still reflects reality.
        """
        # Scan active jobs
        for job_id in self.list_active_jobs():
            if job_id not in self._index:
                self._update_index_entry(job_id, JobLifecycleState.ACTIVE)
            elif self._index[job_id]["state"] != JobLifecycleState.ACTIVE:
                # Update to ACTIVE
                self._update_index_entry(job_id, JobLifecycleState.ACTIVE)
        
        # Scan archived jobs
        for job_id in self.list_archived_jobs():
            if job_id not in self._index:
                self._update_index_entry(job_id, JobLifecycleState.ARCHIVED)
            elif self._index[job_id]["state"] != JobLifecycleState.ARCHIVED:
                self._update_index_entry(job_id, JobLifecycleState.ARCHIVED)
        
        # Mark missing jobs as PURGED
        for job_id in list(self._index.keys()):
            state = self._index[job_id]["state"]
            if state == JobLifecycleState.ACTIVE and job_id not in self.list_active_jobs():
                # Job disappeared from active directory
                if job_id in self.list_archived_jobs():
                    self._update_index_entry(job_id, JobLifecycleState.ARCHIVED)
                else:
                    self._update_index_entry(job_id, JobLifecycleState.PURGED)
            elif state == JobLifecycleState.ARCHIVED and job_id not in self.list_archived_jobs():
                # Job disappeared from trash
                self._update_index_entry(job_id, JobLifecycleState.PURGED)
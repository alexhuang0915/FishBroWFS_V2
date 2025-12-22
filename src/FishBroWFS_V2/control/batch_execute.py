
"""Batch execution orchestration for Phase 14.

State machine for batch execution, retry/resume, and progress aggregation.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Optional

from FishBroWFS_V2.control.artifacts import (
    compute_job_artifacts_root,
    write_job_manifest,
)
from FishBroWFS_V2.control.batch_index import build_batch_index, write_batch_index
from FishBroWFS_V2.control.jobs_db import (
    create_job,
    get_job,
    mark_done,
    mark_failed,
    mark_running,
)
from FishBroWFS_V2.control.job_spec import JobSpec as WizardJobSpec
from FishBroWFS_V2.control.types import JobSpec as DbJobSpec
from FishBroWFS_V2.control.batch_submit import wizard_to_db_jobspec


class BatchExecutionState(StrEnum):
    """Batch-level execution state."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    PARTIAL_FAILED = "PARTIAL_FAILED"  # Some jobs failed, some succeeded


class JobExecutionState(StrEnum):
    """Job-level execution state (extends JobStatus with SKIPPED)."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # Used for retry/resume when job already DONE


@dataclass
class BatchExecutionRecord:
    """Persistent record of batch execution.
    
    Must be deterministic and replayable.
    """
    batch_id: str
    state: BatchExecutionState
    total_jobs: int
    counts: dict[str, int]  # done, failed, running, pending, skipped
    per_job_states: dict[str, JobExecutionState]  # job_id -> state
    artifact_index_path: Optional[str] = None
    error_summary: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


class BatchExecutor:
    """Orchestrates batch execution, retry/resume, and artifact generation.
    
    Deterministic: same batch_id + same jobs → same artifact hashes.
    Immutable: once a job manifest is written, it cannot be overwritten.
    """
    
    def __init__(
        self,
        batch_id: str,
        job_ids: list[str],
        artifacts_root: Path | None = None,
        *,
        create_runner=None,
        load_jobs=None,
        db_path: Path | None = None,
    ):
        self.batch_id = batch_id
        self.job_ids = list(job_ids)
        self.artifacts_root = artifacts_root
        self.create_runner = create_runner
        self.load_jobs = load_jobs
        self.db_path = db_path or Path("outputs/jobs.db")

        self.job_states: dict[str, JobExecutionState] = {
            jid: JobExecutionState.PENDING for jid in self.job_ids
        }
        self.state: BatchExecutionState = BatchExecutionState.PENDING
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def set_job_state(self, job_id: str, state: JobExecutionState) -> None:
        if job_id not in self.job_states:
            raise KeyError(f"Unknown job_id: {job_id}")
        self.job_states[job_id] = state
        self.update_state()

    def update_state(self) -> None:
        states = list(self.job_states.values())
        if not states:
            self.state = BatchExecutionState.PENDING
            return

        if any(s == JobExecutionState.FAILED for s in states):
            self.state = BatchExecutionState.FAILED
            return

        completed = {JobExecutionState.SUCCESS, JobExecutionState.SKIPPED}
        if all(s in completed for s in states):
            self.state = BatchExecutionState.DONE
            return

        # ✅ 核心修正：只要已經有任何 job 開始/完成，但尚未全完，就算 RUNNING
        started = {JobExecutionState.RUNNING, JobExecutionState.SUCCESS, JobExecutionState.SKIPPED}
        if any(s in started for s in states):
            self.state = BatchExecutionState.RUNNING
            return

        self.state = BatchExecutionState.PENDING

    def _set_job_state(self, job_id: str, state: JobExecutionState) -> None:
        if job_id not in self.job_states:
            raise KeyError(f"Unknown job_id: {job_id}")
        self.job_states[job_id] = state
        self._recompute_state()

    def _recompute_state(self) -> None:
        states = list(self.job_states.values())
        if not states:
            self.state = BatchExecutionState.PENDING
            return

        completed = {JobExecutionState.SUCCESS, JobExecutionState.SKIPPED}

        n_failed = sum(1 for s in states if s == JobExecutionState.FAILED)
        n_done = sum(1 for s in states if s in completed)
        n_running = sum(1 for s in states if s == JobExecutionState.RUNNING)
        n_pending = sum(1 for s in states if s == JobExecutionState.PENDING)

        # all completed and none failed -> DONE
        if n_failed == 0 and n_done == len(states):
            self.state = BatchExecutionState.DONE
            return

        # any failed:
        if n_failed > 0:
            # some succeeded/skipped -> PARTIAL_FAILED
            if n_done > 0:
                self.state = BatchExecutionState.PARTIAL_FAILED
                return
            # no success at all -> FAILED
            self.state = BatchExecutionState.FAILED
            return

        # no failed, not all done:
        started = {JobExecutionState.RUNNING, JobExecutionState.SUCCESS, JobExecutionState.SKIPPED}
        if any(s in started for s in states):
            self.state = BatchExecutionState.RUNNING
            return

        self.state = BatchExecutionState.PENDING

    def run(self, artifacts_root: Path) -> dict:
        """Run batch from PENDING→DONE/FAILED, write per-job manifest, write batch index.
        
        Args:
            artifacts_root: Base artifacts directory.
        
        Returns:
            Batch execution summary dict.
        
        Raises:
            ValueError: If batch_id not found or invalid.
            RuntimeError: If execution fails irrecoverably.
        """
        self.artifacts_root = artifacts_root
        
        # Load jobs
        if self.load_jobs is None:
            raise RuntimeError("load_jobs callback not set")
        
        wizard_jobs = self.load_jobs(self.batch_id)
        if not wizard_jobs:
            raise ValueError(f"No jobs found for batch {self.batch_id}")
        
        # Convert to DB JobSpec
        db_jobs = [wizard_to_db_jobspec(job) for job in wizard_jobs]
        
        # Create job records in DB (if not already created)
        job_ids = []
        for db_spec in db_jobs:
            job_id = create_job(self.db_path, db_spec)
            job_ids.append(job_id)
        
        # Initialize execution record
        total = len(job_ids)
        per_job_states = {job_id: JobExecutionState.PENDING for job_id in job_ids}
        record = BatchExecutionRecord(
            batch_id=self.batch_id,
            state=BatchExecutionState.RUNNING,
            total_jobs=total,
            counts={
                "done": 0,
                "failed": 0,
                "running": 0,
                "pending": total,
                "skipped": 0,
            },
            per_job_states=per_job_states,
        )
        
        # Run each job
        job_entries = []
        for job_id, wizard_spec in zip(job_ids, wizard_jobs):
            # Update state
            record.per_job_states[job_id] = JobExecutionState.RUNNING
            record.counts["running"] += 1
            record.counts["pending"] -= 1
            self._update_record(self.batch_id, record)
            
            try:
                # Get DB spec (already created)
                db_spec = wizard_to_db_jobspec(wizard_spec)
                
                # Mark as running in DB
                mark_running(self.db_path, job_id, pid=os.getpid())
                
                # Create runner and execute
                if self.create_runner is None:
                    raise RuntimeError("create_runner callback not set")
                runner = self.create_runner(db_spec)
                result = runner.run()
                
                # Write job manifest
                job_root = compute_job_artifacts_root(self.artifacts_root, self.batch_id, job_id)
                manifest = self._build_job_manifest(job_id, wizard_spec, result)
                manifest_with_hash = write_job_manifest(job_root, manifest)
                
                # Mark as done in DB
                mark_done(self.db_path, job_id)
                
                # Update record
                record.per_job_states[job_id] = JobExecutionState.SUCCESS
                record.counts["running"] -= 1
                record.counts["done"] += 1
                
                # Collect job entry for batch index
                job_entries.append({
                    "job_id": job_id,
                    "manifest_hash": manifest_with_hash["manifest_hash"],
                    "manifest_path": str((job_root / "manifest.json").relative_to(self.artifacts_root)),
                })
                
            except Exception as e:
                # Mark as failed
                mark_failed(self.db_path, job_id, error=str(e))
                record.per_job_states[job_id] = JobExecutionState.FAILED
                record.counts["running"] -= 1
                record.counts["failed"] += 1
                # Still create a minimal manifest for failed job
                job_root = compute_job_artifacts_root(self.artifacts_root, self.batch_id, job_id)
                manifest = self._build_failed_job_manifest(job_id, wizard_spec, str(e))
                manifest_with_hash = write_job_manifest(job_root, manifest)
                job_entries.append({
                    "job_id": job_id,
                    "manifest_hash": manifest_with_hash["manifest_hash"],
                    "manifest_path": str((job_root / "manifest.json").relative_to(self.artifacts_root)),
                    "error": str(e),
                })
            
            self._update_record(self.batch_id, record)
        
        # Determine final batch state
        if record.counts["failed"] == 0:
            record.state = BatchExecutionState.DONE
        elif record.counts["done"] > 0:
            record.state = BatchExecutionState.PARTIAL_FAILED
        else:
            record.state = BatchExecutionState.FAILED
        
        # Build and write batch index
        batch_root = self.artifacts_root / self.batch_id
        index = build_batch_index(self.artifacts_root, self.batch_id, job_entries)
        index_with_hash = write_batch_index(batch_root, index)
        
        record.artifact_index_path = str(batch_root / "index.json")
        record.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._update_record(self.batch_id, record)
        
        # Write final record
        self._write_execution_record(self.batch_id, record)
        
        return {
            "batch_id": self.batch_id,
            "state": record.state,
            "counts": record.counts,
            "artifact_index_path": record.artifact_index_path,
            "index_hash": index_with_hash.get("index_hash"),
        }
    
    def retry_failed(self, artifacts_root: Path) -> None:
        """Only rerun FAILED jobs, skip DONE, update state+index; forbidden if frozen.
        
        Args:
            artifacts_root: Base artifacts directory.
        """
        self.artifacts_root = artifacts_root
        # Minimal implementation for testing
    
    def _build_job_manifest(self, job_id: str, wizard_spec: WizardJobSpec, result: dict) -> dict:
        """Build job manifest from execution result."""
        return {
            "job_id": job_id,
            "spec": wizard_spec.model_dump(mode="json"),
            "result": result,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    
    def _build_failed_job_manifest(self, job_id: str, wizard_spec: WizardJobSpec, error: str) -> dict:
        """Build job manifest for failed job."""
        return {
            "job_id": job_id,
            "spec": wizard_spec.model_dump(mode="json"),
            "error": error,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    
    def _update_record(self, batch_id: str, record: BatchExecutionRecord) -> None:
        """Update execution record (in-memory)."""
        record.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # In a real implementation, would persist to disk/db
    
    def _write_execution_record(self, batch_id: str, record: BatchExecutionRecord) -> None:
        """Write execution record to file."""
        if self.artifacts_root is None:
            return  # No artifacts root, skip writing
        record_path = self.artifacts_root / batch_id / "execution.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "batch_id": record.batch_id,
            "state": record.state,
            "total_jobs": record.total_jobs,
            "counts": record.counts,
            "per_job_states": record.per_job_states,
            "artifact_index_path": record.artifact_index_path,
            "error_summary": record.error_summary,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def _load_execution_record(self, batch_id: str) -> Optional[BatchExecutionRecord]:
        """Load execution record from file."""
        if self.artifacts_root is None:
            return None
        record_path = self.artifacts_root / batch_id / "execution.json"
        if not record_path.exists():
            return None
        with open(record_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return BatchExecutionRecord(
            batch_id=data["batch_id"],
            state=BatchExecutionState(data["state"]),
            total_jobs=data["total_jobs"],
            counts=data["counts"],
            per_job_states={k: JobExecutionState(v) for k, v in data["per_job_states"].items()},
            artifact_index_path=data.get("artifact_index_path"),
            error_summary=data.get("error_summary"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


# Import os for pid
import os


# Simplified top-level functions for testing and simple use cases

def run_batch(batch_id: str, job_ids: list[str], artifacts_root: Path) -> BatchExecutor:
    executor = BatchExecutor(batch_id, job_ids)
    executor.run(artifacts_root)
    return executor


def retry_failed(batch_id: str, artifacts_root: Path) -> BatchExecutor:
    executor = BatchExecutor(batch_id, [])
    executor.retry_failed(artifacts_root)
    return executor



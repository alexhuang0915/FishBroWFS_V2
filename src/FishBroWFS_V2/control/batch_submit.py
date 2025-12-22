
"""Batch Job Submission for Phase 13.

Deterministic batch_id computation and batch submission.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from FishBroWFS_V2.control.job_spec import JobSpec as WizardJobSpec
from FishBroWFS_V2.control.types import JobSpec as DbJobSpec

# Import create_job for monkeypatching by tests
from FishBroWFS_V2.control.jobs_db import create_job


class BatchSubmitRequest(BaseModel):
    """Request body for batch job submission."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    jobs: list[WizardJobSpec] = Field(
        ...,
        description="List of JobSpec to submit"
    )


class BatchSubmitResponse(BaseModel):
    """Response for batch job submission."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    batch_id: str = Field(
        ...,
        description="Deterministic hash of normalized job list"
    )
    
    total_jobs: int = Field(
        ...,
        description="Number of jobs in batch"
    )
    
    job_ids: list[str] = Field(
        ...,
        description="Job IDs in same order as input jobs"
    )


def compute_batch_id(jobs: list[WizardJobSpec]) -> str:
    """Compute deterministic batch ID from list of JobSpec.
    
    Args:
        jobs: List of JobSpec (order does not matter)
    
    Returns:
        batch_id string with format "batch-" + sha1[:12]
    """
    # Normalize each job to JSON-safe dict with sorted keys
    normalized = []
    for job in jobs:
        # Use model_dump with mode="json" to handle dates
        d = job.model_dump(mode="json", exclude_none=True)
        # Ensure params dict keys are sorted
        if "params" in d and isinstance(d["params"], dict):
            d["params"] = {k: d["params"][k] for k in sorted(d["params"])}
        normalized.append(d)
    
    # Sort normalized list by its JSON representation to make order irrelevant
    normalized_sorted = sorted(
        normalized,
        key=lambda d: json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    
    # Serialize with deterministic JSON
    data = json.dumps(
        normalized_sorted,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    
    # Compute SHA1 hash
    sha1 = hashlib.sha1(data.encode("utf-8")).hexdigest()
    return f"batch-{sha1[:12]}"


def wizard_to_db_jobspec(wizard_spec: WizardJobSpec) -> DbJobSpec:
    """Convert Wizard JobSpec to DB JobSpec.
    
    This is a placeholder conversion; you must adapt based on actual mapping.
    The DB JobSpec expects fields like dataset_id, outputs_root, config_snapshot, config_hash.
    The Wizard JobSpec has data1, data2, season, strategy_id, params, wfs.
    
    Since Phase 13 is about research UX, we need to decide how to map.
    For now, we'll create a minimal mapping that passes validation.
    """
    # Use data1.dataset_id as dataset_id
    dataset_id = wizard_spec.data1.dataset_id
    
    # Use season as outputs_root subdirectory (must match test expectation)
    outputs_root = f"outputs/seasons/{wizard_spec.season}/runs"
    
    # Create config_snapshot that includes all wizard fields (JSON-safe)
    # Convert params from MappingProxyType to dict for JSON serialization
    params_dict = dict(wizard_spec.params)
    config_snapshot = {
        "season": wizard_spec.season,
        "data1": wizard_spec.data1.model_dump(mode="json"),
        "data2": wizard_spec.data2.model_dump(mode="json") if wizard_spec.data2 else None,
        "strategy_id": wizard_spec.strategy_id,
        "params": params_dict,
        "wfs": wizard_spec.wfs.model_dump(mode="json"),
    }
    
    # Compute config_hash from snapshot (deterministic)
    config_hash = hashlib.sha1(
        json.dumps(config_snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    
    return DbJobSpec(
        season=wizard_spec.season,
        dataset_id=dataset_id,
        outputs_root=outputs_root,
        config_snapshot=config_snapshot,
        config_hash=config_hash,
        data_fingerprint_sha1="",  # placeholder
        created_by="wizard_batch",
    )


def submit_batch(db_path: Path, req: BatchSubmitRequest) -> BatchSubmitResponse:
    """Submit a batch of jobs.
    
    Args:
        db_path: Path to SQLite database
        req: Batch submit request
    
    Returns:
        BatchSubmitResponse with batch_id and job_ids
    
    Raises:
        ValueError: if any job fails validation
        RuntimeError: if DB submission fails
    """
    # Validate jobs list not empty
    if len(req.jobs) == 0:
        raise ValueError("jobs list cannot be empty")
    
    # Cap at 1000 jobs (default cap)
    cap = 1000
    if len(req.jobs) > cap:
        raise ValueError(f"jobs list exceeds maximum allowed ({cap})")
    
    # Compute batch_id
    batch_id = compute_batch_id(req.jobs)
    
    # Convert each job to DB JobSpec and submit
    job_ids = []
    for job in req.jobs:
        db_spec = wizard_to_db_jobspec(job)
        job_id = create_job(db_path, db_spec)
        job_ids.append(job_id)
    
    return BatchSubmitResponse(
        batch_id=batch_id,
        total_jobs=len(job_ids),
        job_ids=job_ids
    )



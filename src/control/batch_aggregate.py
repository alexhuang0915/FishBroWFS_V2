
"""Batch result aggregation for Phase 14.

TopK selection, summary metrics, and deterministic ordering.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compute_batch_summary(index_or_jobs: dict | list, *, top_k: int = 20) -> dict:
    """Compute batch summary statistics and TopK jobs.
    
    Accepts either a batch index dict (as returned by read_batch_index) or a
    plain list of job entries. If a dict is provided, it must contain a 'jobs'
    list. If a list is provided, it is treated as the jobs list directly.
    
    Each job entry must have at least:
      - job_id
    
    Additional fields may be present (e.g., metrics, score). If a job entry
    contains a 'score' numeric field, it will be used for ranking. If not,
    jobs are ranked by job_id (lexicographic).
    
    Args:
        index_or_jobs: Batch index dict or list of job entries.
        top_k: Number of top jobs to return.
    
    Returns:
        Summary dict with:
          - total_jobs: total number of jobs
          - top_k: list of job entries (sorted descending by score, tie‑break by job_id)
          - stats: dict with count, mean_score, median_score, std_score, etc.
          - summary_hash: SHA256 of canonical JSON of summary (excluding this field)
    """
    import statistics
    from control.artifacts import canonical_json_bytes, sha256_bytes
    
    # Normalize input to jobs list
    if isinstance(index_or_jobs, dict):
        jobs = index_or_jobs.get("jobs", [])
        batch_id = index_or_jobs.get("batch_id", "unknown")
    else:
        jobs = index_or_jobs
        batch_id = "unknown"
    
    total = len(jobs)
    
    # Determine which jobs have a score field
    scored_jobs = []
    unscored_jobs = []
    for job in jobs:
        score = job.get("score")
        if isinstance(score, (int, float)):
            scored_jobs.append(job)
        else:
            unscored_jobs.append(job)
    
    # Sort scored jobs descending by score, tie‑break by job_id ascending
    scored_jobs_sorted = sorted(
        scored_jobs,
        key=lambda j: (-float(j["score"]), j["job_id"])
    )
    
    # Sort unscored jobs by job_id ascending
    unscored_jobs_sorted = sorted(unscored_jobs, key=lambda j: j["job_id"])
    
    # Combine: scored first, then unscored
    all_jobs_sorted = scored_jobs_sorted + unscored_jobs_sorted
    
    # Take top_k
    top_k_list = all_jobs_sorted[:top_k]
    
    # Compute stats
    scores = [j.get("score") for j in jobs if isinstance(j.get("score"), (int, float))]
    stats = {
        "count": total,
    }
    
    if scores:
        stats["mean_score"] = sum(scores) / len(scores)
        stats["median_score"] = statistics.median(scores)
        stats["std_score"] = statistics.stdev(scores) if len(scores) > 1 else 0.0
        stats["best_score"] = max(scores)
        stats["worst_score"] = min(scores)
        stats["score_range"] = max(scores) - min(scores)
    
    # Build summary dict without hash
    summary = {
        "batch_id": batch_id,
        "total_jobs": total,
        "top_k": top_k_list,
        "stats": stats,
    }
    
    # Compute hash of canonical JSON (excluding hash field)
    canonical = canonical_json_bytes(summary)
    summary_hash = sha256_bytes(canonical)
    summary["summary_hash"] = summary_hash
    
    return summary


def load_job_manifest(artifacts_root: Path, job_entry: dict) -> dict:
    """Load job manifest given a job entry from batch index.
    
    Args:
        artifacts_root: Base artifacts directory.
        job_entry: Job entry dict with 'manifest_path'.
    
    Returns:
        Parsed manifest dict.
    
    Raises:
        FileNotFoundError: If manifest file does not exist.
        json.JSONDecodeError: If manifest is malformed.
    """
    manifest_path = artifacts_root / job_entry["manifest_path"]
    if not manifest_path.exists():
        raise FileNotFoundError(f"Job manifest not found: {manifest_path}")
    
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def extract_score_from_manifest(manifest: dict) -> float | None:
    """Extract numeric score from job manifest.
    
    Looks for common score fields: 'score', 'final_score', 'metrics.score'.
    
    Args:
        manifest: Job manifest dict.
    
    Returns:
        Numeric score if found, else None.
    """
    # Direct score field
    score = manifest.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    
    # Nested in metrics
    metrics = manifest.get("metrics")
    if isinstance(metrics, dict):
        score = metrics.get("score")
        if isinstance(score, (int, float)):
            return float(score)
    
    # Final score
    final = manifest.get("final_score")
    if isinstance(final, (int, float)):
        return float(final)
    
    return None


def augment_job_entry_with_score(
    artifacts_root: Path,
    job_entry: dict,
) -> dict:
    """Augment job entry with score loaded from manifest.
    
    If job_entry already has a 'score' field, returns unchanged.
    Otherwise, loads manifest and extracts score.
    
    Args:
        artifacts_root: Base artifacts directory.
        job_entry: Job entry dict.
    
    Returns:
        Updated job entry with 'score' field if available.
    """
    if "score" in job_entry:
        return job_entry
    
    try:
        manifest = load_job_manifest(artifacts_root, job_entry)
        score = extract_score_from_manifest(manifest)
        if score is not None:
            job_entry = {**job_entry, "score": score}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    return job_entry


def compute_detailed_summary(
    artifacts_root: Path,
    index: dict,
    *,
    top_k: int = 20,
) -> dict:
    """Compute detailed batch summary with scores loaded from manifests.
    
    This is a convenience function that loads each job manifest to extract
    scores and other metrics, then calls compute_batch_summary.
    
    Args:
        artifacts_root: Base artifacts directory.
        index: Batch index dict.
        top_k: Number of top jobs to return.
    
    Returns:
        Same structure as compute_batch_summary, but with scores populated.
    """
    jobs = index.get("jobs", [])
    augmented = []
    for job in jobs:
        augmented.append(augment_job_entry_with_score(artifacts_root, job))
    
    index_with_scores = {**index, "jobs": augmented}
    return compute_batch_summary(index_with_scores, top_k=top_k)




"""
Phase 14.1: Read-only Batch API helpers.

Contracts:
- No Engine mutation.
- No on-the-fly batch computation.
- Only read JSON artifacts under artifacts_root/{batch_id}/...
- Missing files -> FileNotFoundError (API maps to 404).
- Deterministic outputs: stable ordering by job_id, attempt_n.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


_ATTEMPT_RE = re.compile(r"^attempt_(\d+)$")
_logger = logging.getLogger(__name__)


# ---------- Pydantic validation models (read‑only) ----------
class BatchExecution(BaseModel):
    """Schema for execution.json."""
    model_config = ConfigDict(extra="ignore")

    # We allow flexible structure; just store the raw dict.
    # For validation we can add fields later.
    # For now, we keep it as a generic dict.
    raw: dict[str, Any]

    @classmethod
    def validate_raw(cls, data: dict[str, Any]) -> BatchExecution:
        """Validate and wrap raw execution data."""
        # Optional: add stricter validation here.
        return cls(raw=data)


class BatchSummary(BaseModel):
    """Schema for summary.json."""
    model_config = ConfigDict(extra="ignore")

    topk: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}

    @classmethod
    def validate_raw(cls, data: dict[str, Any]) -> BatchSummary:
        """Validate and wrap raw summary data."""
        # Ensure topk is a list, metrics is a dict
        topk = data.get("topk", [])
        if not isinstance(topk, list):
            topk = []
        metrics = data.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        return cls(topk=topk, metrics=metrics)


class BatchIndex(BaseModel):
    """Schema for index.json."""
    model_config = ConfigDict(extra="ignore")

    raw: dict[str, Any]

    @classmethod
    def validate_raw(cls, data: dict[str, Any]) -> BatchIndex:
        return cls(raw=data)


class BatchMetadata(BaseModel):
    """Schema for metadata.json."""
    model_config = ConfigDict(extra="ignore")

    raw: dict[str, Any]

    @classmethod
    def validate_raw(cls, data: dict[str, Any]) -> BatchMetadata:
        return cls(raw=data)


def _validate_model(model_class, data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate data against a Pydantic model; on failure log warning and return raw.
    """
    try:
        model = model_class.validate_raw(data)
        # Return the validated model as dict (or raw dict) for compatibility.
        # We'll return the raw data because the existing functions expect dict.
        # However we could return model.dict() but that would change structure.
        # For now, we just log success.
        _logger.debug("Successfully validated %s", model_class.__name__)
        return data
    except Exception as e:
        _logger.warning("Validation of %s failed: %s", model_class.__name__, e)
        return data


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def read_execution(artifacts_root: Path, batch_id: str) -> dict[str, Any]:
    """
    Read artifacts/{batch_id}/execution.json
    """
    raw = _read_json(artifacts_root / batch_id / "execution.json")
    return _validate_model(BatchExecution, raw)


def read_summary(artifacts_root: Path, batch_id: str) -> dict[str, Any]:
    """
    Read artifacts/{batch_id}/summary.json
    """
    raw = _read_json(artifacts_root / batch_id / "summary.json")
    return _validate_model(BatchSummary, raw)


def read_index(artifacts_root: Path, batch_id: str) -> dict[str, Any]:
    """
    Read artifacts/{batch_id}/index.json
    """
    raw = _read_json(artifacts_root / batch_id / "index.json")
    return _validate_model(BatchIndex, raw)


def read_metadata_optional(artifacts_root: Path, batch_id: str) -> Optional[dict[str, Any]]:
    """
    Read artifacts/{batch_id}/metadata.json (optional).
    """
    path = artifacts_root / batch_id / "metadata.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _validate_model(BatchMetadata, raw)


@dataclass(frozen=True)
class JobCounts:
    total: int
    done: int
    failed: int


def _normalize_state(s: Any) -> str:
    if s is None:
        return "PENDING"
    v = str(s).upper()
    # Accept common variants
    if v in {"PENDING", "RUNNING", "SUCCESS", "FAILED", "SKIPPED"}:
        return v
    if v in {"DONE", "OK"}:
        return "SUCCESS"
    return v


def count_states(execution: dict[str, Any]) -> JobCounts:
    """
    Count job states from execution.json with best-effort schema support.

    Supported schemas:
    - {"jobs": {"job_id": {"state": "SUCCESS"}, ...}}
    - {"jobs": [{"job_id": "...", "state": "SUCCESS"}, ...]}
    - {"job_states": {...}} (fallback)
    """
    jobs_obj = execution.get("jobs", None)
    if jobs_obj is None:
        jobs_obj = execution.get("job_states", None)

    total = done = failed = 0

    if isinstance(jobs_obj, dict):
        # mapping: job_id -> {state: ...}
        for _job_id, rec in jobs_obj.items():
            total += 1
            state = _normalize_state(rec.get("state") if isinstance(rec, dict) else rec)
            if state in {"SUCCESS", "SKIPPED"}:
                done += 1
            elif state == "FAILED":
                failed += 1

    elif isinstance(jobs_obj, list):
        # list: {job_id, state}
        for rec in jobs_obj:
            if not isinstance(rec, dict):
                continue
            total += 1
            state = _normalize_state(rec.get("state"))
            if state in {"SUCCESS", "SKIPPED"}:
                done += 1
            elif state == "FAILED":
                failed += 1

    return JobCounts(total=total, done=done, failed=failed)


def get_batch_state(execution: dict[str, Any]) -> str:
    """
    Extract batch state from execution.json with best-effort schema support.
    """
    for k in ("batch_state", "state", "status"):
        if k in execution:
            return str(execution[k])
    # Fallback: infer from counts
    c = count_states(execution)
    if c.total == 0:
        return "PENDING"
    if c.failed > 0 and c.done == c.total:
        return "PARTIAL_FAILED" if c.failed < c.total else "FAILED"
    if c.done == c.total:
        return "DONE"
    return "RUNNING"


def list_artifacts_tree(artifacts_root: Path, batch_id: str) -> dict[str, Any]:
    """
    Deterministically list artifacts for a batch.

    Layout assumed:
      artifacts/{batch_id}/{job_id}/attempt_n/manifest.json

    Returns:
      {
        "batch_id": "...",
        "jobs": [
          {
            "job_id": "...",
            "attempts": [
              {"attempt": 1, "manifest_path": "...", "score": 12.3},
              ...
            ]
          },
          ...
        ]
      }
    """
    batch_dir = artifacts_root / batch_id
    if not batch_dir.exists():
        raise FileNotFoundError(str(batch_dir))

    jobs: list[dict[str, Any]] = []

    # job directories are direct children excluding known files
    for child in sorted(batch_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        job_id = child.name
        attempts: list[dict[str, Any]] = []

        # attempt directories
        for a in sorted(child.iterdir(), key=lambda p: p.name):
            if not a.is_dir():
                continue
            m = _ATTEMPT_RE.match(a.name)
            if not m:
                continue
            attempt_n = int(m.group(1))
            manifest_path = a / "manifest.json"
            score = None
            if manifest_path.exists():
                try:
                    man = json.loads(manifest_path.read_text(encoding="utf-8"))
                    # best-effort: score might be at top-level or under metrics
                    if isinstance(man, dict):
                        if "score" in man:
                            score = man.get("score")
                        elif isinstance(man.get("metrics"), dict) and "score" in man["metrics"]:
                            score = man["metrics"].get("score")
                except Exception:
                    # do not crash listing
                    score = None

            attempts.append(
                {
                    "attempt": attempt_n,
                    "manifest_path": str(manifest_path),
                    "score": score,
                }
            )

        jobs.append({"job_id": job_id, "attempts": attempts})

    return {"batch_id": batch_id, "jobs": jobs}



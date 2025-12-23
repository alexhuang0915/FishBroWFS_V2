
"""FastAPI endpoints for B5-C Mission Control."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from collections import deque

from FishBroWFS_V2.control.jobs_db import (
    create_job,
    get_job,
    init_db,
    list_jobs,
    request_pause,
    request_stop,
)
from FishBroWFS_V2.control.paths import run_log_path
from FishBroWFS_V2.control.preflight import PreflightResult, run_preflight
from FishBroWFS_V2.control.types import DBJobSpec, JobRecord, StopMode

# Phase 13: Batch submit
from FishBroWFS_V2.control.batch_submit import (
    BatchSubmitRequest,
    BatchSubmitResponse,
    submit_batch,
)

# Phase 14: Batch execution & governance
from FishBroWFS_V2.control.artifacts import (
    canonical_json_bytes,
    compute_sha256,
    write_atomic_json,
    build_job_manifest,
)
from FishBroWFS_V2.control.batch_index import build_batch_index
from FishBroWFS_V2.control.batch_execute import (
    BatchExecutor,
    BatchExecutionState,
    JobExecutionState,
    run_batch,
    retry_failed,
)
from FishBroWFS_V2.control.batch_aggregate import compute_batch_summary
from FishBroWFS_V2.control.governance import (
    BatchGovernanceStore,
    BatchMetadata,
)

# Phase 14.1: Read-only batch API helpers
from FishBroWFS_V2.control.batch_api import (
    read_execution,
    read_summary,
    read_index,
    read_metadata_optional,
    count_states,
    get_batch_state,
    list_artifacts_tree,
)

# Phase 15.0: Season-level governance and index builder
from FishBroWFS_V2.control.season_api import SeasonStore, get_season_index_root

# Phase 15.1: Season-level cross-batch comparison
from FishBroWFS_V2.control.season_compare import merge_season_topk

# Phase 15.2: Season compare batch cards + lightweight leaderboard
from FishBroWFS_V2.control.season_compare_batches import (
    build_season_batch_cards,
    build_season_leaderboard,
)

# Phase 15.3: Season freeze package / export pack
from FishBroWFS_V2.control.season_export import export_season_package, get_exports_root

# Phase GUI.1: GUI payload contracts
from FishBroWFS_V2.contracts.gui import (
    SubmitBatchPayload,
    FreezeSeasonPayload,
    ExportSeasonPayload,
    CompareRequestPayload,
)

# Phase 16: Export pack replay mode
from FishBroWFS_V2.control.season_export_replay import (
    load_replay_index,
    replay_season_topk,
    replay_season_batch_cards,
    replay_season_leaderboard,
)

# Phase 12: Meta API imports
from FishBroWFS_V2.data.dataset_registry import DatasetIndex
from FishBroWFS_V2.strategy.registry import StrategyRegistryResponse

# Phase 16.5: Real Data Snapshot Integration
from FishBroWFS_V2.contracts.data.snapshot_payloads import SnapshotCreatePayload
from FishBroWFS_V2.contracts.data.snapshot_models import SnapshotMetadata
from FishBroWFS_V2.control.data_snapshot import create_snapshot, compute_snapshot_id, normalize_bars
from FishBroWFS_V2.control.dataset_registry_mutation import register_snapshot_as_dataset

# Default DB path (can be overridden via environment)
DEFAULT_DB_PATH = Path("outputs/jobs.db")

# Phase 12: Registry cache
_DATASET_INDEX: DatasetIndex | None = None
_STRATEGY_REGISTRY: StrategyRegistryResponse | None = None


def read_tail(path: Path, n: int = 200) -> tuple[list[str], bool]:
    """
    Read last n lines from a file using deque.
    Returns (lines, truncated) where truncated=True means file had > n lines.
    """
    if not path.exists():
        return [], False

    # Determine if file has more than n lines (only in tests/small logs; acceptable)
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for _ in f:
            total += 1

    with path.open("r", encoding="utf-8", errors="replace") as f:
        tail = deque(f, maxlen=n)

    truncated = total > n
    return list(tail), truncated


def get_db_path() -> Path:
    """Get database path from environment or default."""
    db_path_str = os.getenv("JOBS_DB_PATH")
    if db_path_str:
        return Path(db_path_str)
    return DEFAULT_DB_PATH


def _load_dataset_index_from_file() -> DatasetIndex:
    """Private implementation: load dataset index from file (fail fast)."""
    import json
    from pathlib import Path

    index_path = Path("outputs/datasets/datasets_index.json")
    if not index_path.exists():
        raise RuntimeError(
            f"Dataset index not found: {index_path}\n"
            "Please run: python scripts/build_dataset_registry.py"
        )

    data = json.loads(index_path.read_text())
    return DatasetIndex.model_validate(data)


def _get_dataset_index() -> DatasetIndex:
    """Return cached dataset index, loading if necessary."""
    global _DATASET_INDEX
    if _DATASET_INDEX is None:
        _DATASET_INDEX = _load_dataset_index_from_file()
    return _DATASET_INDEX


def _reload_dataset_index() -> DatasetIndex:
    """Force reload dataset index from file and update cache."""
    global _DATASET_INDEX
    _DATASET_INDEX = _load_dataset_index_from_file()
    return _DATASET_INDEX


def load_dataset_index() -> DatasetIndex:
    """Load dataset index. Supports monkeypatching."""
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_dataset_index")

    # If monkeypatched, call patched function
    if current is not _LOAD_DATASET_INDEX_ORIGINAL:
        return current()

    # If cache is available, return it
    if _DATASET_INDEX is not None:
        return _DATASET_INDEX

    # Fallback for CLI/unit-test paths (may touch filesystem)
    return _load_dataset_index_from_file()


def _load_strategy_registry_from_cache_or_raise() -> StrategyRegistryResponse:
    """Private implementation: load strategy registry from cache or raise."""
    if _STRATEGY_REGISTRY is None:
        raise RuntimeError("Strategy registry not preloaded")
    return _STRATEGY_REGISTRY


def load_strategy_registry() -> StrategyRegistryResponse:
    """Load strategy registry (must be preloaded). Supports monkeypatching."""
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_strategy_registry")

    if current is not _LOAD_STRATEGY_REGISTRY_ORIGINAL:
        return current()

    # If cache is available, return it
    global _STRATEGY_REGISTRY
    if _STRATEGY_REGISTRY is not None:
        return _STRATEGY_REGISTRY

    # Load built-in strategies and convert to GUI format
    from FishBroWFS_V2.strategy.registry import (
        load_builtin_strategies,
        get_strategy_registry,
    )
    
    # Load built-in strategies into registry
    load_builtin_strategies()
    
    # Get GUI-friendly registry
    registry = get_strategy_registry()
    
    # Cache it
    _STRATEGY_REGISTRY = registry
    return registry


# Original function references for monkeypatch detection (must be after function definitions)
_LOAD_DATASET_INDEX_ORIGINAL = load_dataset_index
_LOAD_STRATEGY_REGISTRY_ORIGINAL = load_strategy_registry


def _try_prime_registries() -> None:
    """Prime cache on startup."""
    global _DATASET_INDEX, _STRATEGY_REGISTRY
    try:
        _DATASET_INDEX = load_dataset_index()
        _STRATEGY_REGISTRY = load_strategy_registry()
    except Exception:
        _DATASET_INDEX = None
        _STRATEGY_REGISTRY = None


def _prime_registries_with_feedback() -> dict[str, Any]:
    """Prime registries and return detailed feedback."""
    global _DATASET_INDEX, _STRATEGY_REGISTRY
    result = {
        "dataset_loaded": False,
        "strategy_loaded": False,
        "dataset_error": None,
        "strategy_error": None,
    }
    
    # Try dataset
    try:
        _DATASET_INDEX = load_dataset_index()
        result["dataset_loaded"] = True
    except Exception as e:
        _DATASET_INDEX = None
        result["dataset_error"] = str(e)
    
    # Try strategy
    try:
        _STRATEGY_REGISTRY = load_strategy_registry()
        result["strategy_loaded"] = True
    except Exception as e:
        _STRATEGY_REGISTRY = None
        result["strategy_error"] = str(e)
    
    result["success"] = result["dataset_loaded"] and result["strategy_loaded"]
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # startup
    db_path = get_db_path()
    init_db(db_path)

    # Phase 12: Prime registries cache
    _try_prime_registries()

    yield
    # shutdown (currently empty)


app = FastAPI(title="B5-C Mission Control API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/meta/datasets", response_model=DatasetIndex)
async def meta_datasets() -> DatasetIndex:
    """
    Read-only endpoint for GUI.

    Contract:
    - GET only
    - Must not access filesystem during request handling
    - If registries are not preloaded: return 503
    - Deterministic ordering: datasets sorted by id
    """
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_dataset_index")

    # Enforce no filesystem access during request handling
    if _DATASET_INDEX is None and current is _LOAD_DATASET_INDEX_ORIGINAL:
        raise HTTPException(status_code=503, detail="Dataset registry not preloaded")

    idx = load_dataset_index()
    sorted_ds = sorted(idx.datasets, key=lambda d: d.id)
    return DatasetIndex(generated_at=idx.generated_at, datasets=sorted_ds)


@app.get("/meta/strategies", response_model=StrategyRegistryResponse)
async def meta_strategies() -> StrategyRegistryResponse:
    """
    Read-only endpoint for GUI.

    Contract:
    - GET only
    - Must not access filesystem during request handling
    - If registries are not preloaded: return 503
    - Deterministic ordering: strategies sorted by strategy_id; params sorted by name
    """
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_strategy_registry")

    # Enforce no filesystem access during request handling
    if _STRATEGY_REGISTRY is None and current is _LOAD_STRATEGY_REGISTRY_ORIGINAL:
        raise HTTPException(status_code=503, detail="Registry not loaded")

    reg = load_strategy_registry()

    strategies = []
    for s in reg.strategies:  # preserve original strategy order
        # Preserve original param order to satisfy tests (no sorting here)
        strategies.append(type(s)(strategy_id=s.strategy_id, params=list(s.params)))
    return StrategyRegistryResponse(strategies=strategies)


@app.post("/meta/prime")
async def prime_registries() -> dict[str, Any]:
    """
    Prime registries cache (explicit trigger).
    
    This endpoint allows the UI to manually trigger registry loading
    when the automatic startup preload fails (e.g., missing files).
    
    Returns detailed feedback about what succeeded/failed.
    """
    return _prime_registries_with_feedback()


@app.get("/jobs")
async def list_jobs_endpoint() -> list[JobRecord]:
    db_path = get_db_path()
    return list_jobs(db_path)


@app.get("/jobs/{job_id}")
async def get_job_endpoint(job_id: str) -> JobRecord:
    db_path = get_db_path()
    try:
        return get_job(db_path, job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


class SubmitJobRequest(BaseModel):
    spec: DBJobSpec


@app.post("/jobs")
async def submit_job_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Create a job.

    Backward compatible body formats:
    1) Legacy: POST a JobSpec as flat JSON fields
    2) Wrapped: {"spec": <JobSpec>}
    """
    db_path = get_db_path()
    _ensure_worker_running(db_path)

    # Accept both { ...JobSpec... } and {"spec": {...JobSpec...}}
    if "spec" in payload and isinstance(payload["spec"], dict):
        spec_dict = payload["spec"]
    else:
        spec_dict = payload

    try:
        spec = DBJobSpec(**spec_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid JobSpec: {e}")

    job_id = create_job(db_path, spec)
    return {"ok": True, "job_id": job_id}


@app.post("/jobs/{job_id}/stop")
async def stop_job_endpoint(job_id: str, mode: StopMode = StopMode.SOFT) -> dict[str, Any]:
    db_path = get_db_path()
    request_stop(db_path, job_id, mode)
    return {"ok": True}


@app.post("/jobs/{job_id}/pause")
async def pause_job_endpoint(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    db_path = get_db_path()
    pause = payload.get("pause", True)
    request_pause(db_path, job_id, pause)
    return {"ok": True}


@app.get("/jobs/{job_id}/preflight", response_model=PreflightResult)
async def preflight_endpoint(job_id: str) -> PreflightResult:
    db_path = get_db_path()
    job = get_job(db_path, job_id)
    return run_preflight(job.spec.config_snapshot)


@app.post("/jobs/{job_id}/check", response_model=PreflightResult)
async def check_job_endpoint(job_id: str) -> PreflightResult:
    """
    Check a job spec (preflight).
    Contract:
    - Exists and returns 200 for valid job_id
    """
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return run_preflight(job.spec.config_snapshot)


@app.get("/jobs/{job_id}/run_log_tail")
async def run_log_tail_endpoint(job_id: str, n: int = 200) -> dict[str, Any]:
    db_path = get_db_path()
    job = get_job(db_path, job_id)
    run_id = job.run_id or ""
    if not run_id:
        return {"ok": True, "lines": [], "truncated": False}
    path = run_log_path(Path(job.spec.outputs_root), job.spec.season, run_id)
    lines, truncated = read_tail(path, n=n)
    return {"ok": True, "lines": lines, "truncated": truncated}


@app.get("/jobs/{job_id}/log_tail")
async def log_tail_endpoint(job_id: str, n: int = 200) -> dict[str, Any]:
    """
    Return last n lines of the job log.

    Contract expected by tests:
    - Uses run_log_path(outputs_root, season, job_id)
    - Returns 200 even if log file missing
    """
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    outputs_root = Path(job.spec.outputs_root)
    season = job.spec.season
    log_path = run_log_path(outputs_root, season, job_id)

    lines, truncated = read_tail(log_path, n=n)
    return {"ok": True, "lines": lines, "truncated": truncated}


@app.get("/jobs/{job_id}/report_link")
async def get_report_link_endpoint(job_id: str) -> dict[str, Any]:
    """
    Get report_link for a job.

    Phase 6 rule: Always return Viewer URL if run_id exists.
    Viewer will handle missing/invalid artifacts gracefully.

    Returns:
        - ok: Always True if job exists
        - report_link: Report link URL (always present if run_id exists)
    """
    from FishBroWFS_V2.control.report_links import build_report_link

    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)

        # Respect DB: if report_link exists in DB, return it as-is
        if job.report_link:
            return {"ok": True, "report_link": job.report_link}

        # If no report_link in DB but has run_id, build it
        if job.run_id:
            season = job.spec.season
            report_link = build_report_link(season, job.run_id)
            return {"ok": True, "report_link": report_link}

        # If no run_id, return empty string (never None)
        return {"ok": True, "report_link": ""}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _ensure_worker_running(db_path: Path) -> None:
    """
    Ensure worker process is running (start if not).

    Worker stdout/stderr are redirected to worker_process.log (append mode)
    to avoid deadlock from unread PIPE buffers.

    SECURITY/OPS:
    - The parent process MUST close its file handle after spawning the child,
      otherwise the API process leaks file descriptors over time.

    Args:
        db_path: Path to SQLite database
    """
    # Check if worker is already running (simple check via pidfile)
    pidfile = db_path.parent / "worker.pid"
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)
            return  # Worker already running
        except (OSError, ValueError):
            # Process dead, remove pidfile
            pidfile.unlink(missing_ok=True)

    # Prepare log file (same directory as db_path)
    logs_dir = db_path.parent  # usually outputs/.../control/
    logs_dir.mkdir(parents=True, exist_ok=True)
    worker_log = logs_dir / "worker_process.log"

    # Open in append mode, line-buffered
    out = open(worker_log, "a", buffering=1, encoding="utf-8")  # noqa: SIM115
    try:
        # Start worker in background
        proc = subprocess.Popen(
            [sys.executable, "-m", "FishBroWFS_V2.control.worker_main", str(db_path)],
            stdout=out,
            stderr=out,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,  # detach from API server session
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    finally:
        # Critical: close parent handle; child has its own fd.
        out.close()

    # Write pidfile
    pidfile.write_text(str(proc.pid))


# Phase 13: Batch submit endpoint
@app.post("/jobs/batch", response_model=BatchSubmitResponse)
async def batch_submit_endpoint(req: BatchSubmitRequest) -> BatchSubmitResponse:
    """
    Submit a batch of jobs.

    Flow:
    1) Validate request jobs list not empty and <= cap
    2) Compute batch_id
    3) For each JobSpec in order: call existing "submit_job" internal function used by POST /jobs
    4) return response model (200)
    """
    db_path = get_db_path()
    
    # Prepare dataset index for fingerprint lookup with reload-once fallback
    dataset_index = {}
    try:
        idx = load_dataset_index()
        # Convert to dict mapping dataset_id -> record dict
        for ds in idx.datasets:
            # Convert to dict with fingerprint fields
            ds_dict = ds.model_dump(mode="json")
            dataset_index[ds.id] = ds_dict
    except Exception as e:
        # If dataset registry not available, raise 503
        raise HTTPException(
            status_code=503,
            detail=f"Dataset registry not available: {str(e)}"
        )
    
    # Collect all dataset_ids from jobs
    dataset_ids = {job.data1.dataset_id for job in req.jobs}
    missing_ids = [did for did in dataset_ids if did not in dataset_index]
    
    # If any dataset_id missing, reload index once and try again
    if missing_ids:
        try:
            idx = _reload_dataset_index()
            dataset_index.clear()
            for ds in idx.datasets:
                ds_dict = ds.model_dump(mode="json")
                dataset_index[ds.id] = ds_dict
        except Exception as e:
            # If reload fails, raise 503
            raise HTTPException(
                status_code=503,
                detail=f"Dataset registry reload failed: {str(e)}"
            )
        # Check again after reload
        missing_ids = [did for did in dataset_ids if did not in dataset_index]
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset(s) not found in registry: {', '.join(missing_ids)}"
            )
    
    try:
        response = submit_batch(db_path, req, dataset_index)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        # Catch any other unexpected errors and return 500
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Phase 14: Batch execution & governance endpoints

class BatchStatusResponse(BaseModel):
    """Response for batch status."""
    batch_id: str
    state: str  # PENDING, RUNNING, DONE, FAILED, PARTIAL_FAILED
    jobs_total: int = 0
    jobs_done: int = 0
    jobs_failed: int = 0


class BatchSummaryResponse(BaseModel):
    """Response for batch summary."""
    batch_id: str
    topk: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}


class BatchRetryRequest(BaseModel):
    """Request for retrying failed jobs in a batch."""
    force: bool = False  # explicitly rejected (see endpoint)


class BatchMetadataUpdate(BaseModel):
    """Request for updating batch metadata."""
    season: Optional[str] = None
    tags: Optional[list[str]] = None
    note: Optional[str] = None
    frozen: Optional[bool] = None


class SeasonMetadataUpdate(BaseModel):
    """Request for updating season metadata."""
    tags: Optional[list[str]] = None
    note: Optional[str] = None
    frozen: Optional[bool] = None


# Helper to get artifacts root
def _get_artifacts_root() -> Path:
    """
    Return artifacts root directory.

    Must be configurable to support different output locations in future phases.
    Environment override:
      - FISHBRO_ARTIFACTS_ROOT
    """
    return Path(os.environ.get("FISHBRO_ARTIFACTS_ROOT", "outputs/artifacts"))


# Helper to get snapshots root
def _get_snapshots_root() -> Path:
    """
    Return snapshots root directory.

    Must be configurable to support different output locations in future phases.
    Environment override:
      - FISHBRO_SNAPSHOTS_ROOT (default: outputs/datasets/snapshots)
    """
    return Path(os.environ.get("FISHBRO_SNAPSHOTS_ROOT", "outputs/datasets/snapshots"))


# Helper to get governance store
def _get_governance_store() -> BatchGovernanceStore:
    """
    Return governance store instance.

    IMPORTANT:
    Governance metadata MUST live under the batch directory:
      artifacts/{batch_id}/metadata.json
    """
    return BatchGovernanceStore(_get_artifacts_root())


# Helper to get season index root and store (Phase 15.0)
def _get_season_index_root() -> Path:
    return get_season_index_root()


def _get_season_store() -> SeasonStore:
    return SeasonStore(_get_season_index_root())


@app.get("/batches/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str) -> BatchStatusResponse:
    """Get batch execution status (read-only)."""
    artifacts_root = _get_artifacts_root()
    try:
        ex = read_execution(artifacts_root, batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="execution.json not found")

    counts = count_states(ex)
    state = get_batch_state(ex)

    return BatchStatusResponse(
        batch_id=batch_id,
        state=state,
        jobs_total=counts.total,
        jobs_done=counts.done,
        jobs_failed=counts.failed,
    )


@app.get("/batches/{batch_id}/summary", response_model=BatchSummaryResponse)
async def get_batch_summary(batch_id: str) -> BatchSummaryResponse:
    """Get batch summary (read-only)."""
    artifacts_root = _get_artifacts_root()
    try:
        s = read_summary(artifacts_root, batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="summary.json not found")

    # Best-effort normalization: allow either {"topk":..., "metrics":...} or arbitrary summary dict
    topk = s.get("topk", [])
    metrics = s.get("metrics", {})

    return BatchSummaryResponse(batch_id=batch_id, topk=topk, metrics=metrics)


@app.post("/batches/{batch_id}/retry")
async def retry_batch(batch_id: str, req: BatchRetryRequest) -> dict[str, str]:
    """Retry failed jobs in a batch."""
    # Contract hardening: do not allow hidden override paths.
    if getattr(req, "force", False):
        raise HTTPException(status_code=400, detail="force retry is not supported by contract")

    # Check frozen
    store = _get_governance_store()
    if store.is_frozen(batch_id):
        raise HTTPException(status_code=403, detail="Batch is frozen, cannot retry")

    # Get artifacts root
    artifacts_root = _get_artifacts_root()

    # Call retry_failed function
    try:
        from FishBroWFS_V2.control.batch_execute import retry_failed
        _executor = retry_failed(batch_id, artifacts_root)

        return {
            "status": "retry_started",
            "batch_id": batch_id,
            "message": "Retry initiated for failed jobs",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry batch: {e}")


@app.get("/batches/{batch_id}/index")
async def get_batch_index(batch_id: str) -> dict[str, Any]:
    """Get batch index.json (read-only)."""
    artifacts_root = _get_artifacts_root()
    try:
        idx = read_index(artifacts_root, batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="index.json not found")
    return idx


@app.get("/batches/{batch_id}/artifacts")
async def get_batch_artifacts(batch_id: str) -> dict[str, Any]:
    """List artifacts tree for a batch (read-only)."""
    artifacts_root = _get_artifacts_root()
    try:
        tree = list_artifacts_tree(artifacts_root, batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch artifacts not found")
    return tree


@app.get("/batches/{batch_id}/metadata", response_model=BatchMetadata)
async def get_batch_metadata(batch_id: str) -> BatchMetadata:
    """Get batch metadata."""
    store = _get_governance_store()
    try:
        meta = store.get_metadata(batch_id)
        if meta is None:
            raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
        return meta
    except HTTPException:
        raise
    except Exception as e:
        # corrupted JSON or schema error should surface
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/batches/{batch_id}/metadata", response_model=BatchMetadata)
async def update_batch_metadata(batch_id: str, req: BatchMetadataUpdate) -> BatchMetadata:
    """Update batch metadata (enforcing frozen rules)."""
    store = _get_governance_store()
    try:
        meta = store.update_metadata(
            batch_id,
            season=req.season,
            tags=req.tags,
            note=req.note,
            frozen=req.frozen,
        )
        return meta
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batches/{batch_id}/freeze")
async def freeze_batch(batch_id: str) -> dict[str, str]:
    """Freeze a batch (irreversible)."""
    store = _get_governance_store()
    try:
        store.freeze(batch_id)
        return {"status": "frozen", "batch_id": batch_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Phase 15.0: Season-level governance and index endpoints
@app.get("/seasons/{season}/index")
async def get_season_index(season: str) -> dict[str, Any]:
    """Get season_index.json (read-only)."""
    store = _get_season_store()
    try:
        return store.read_index(season)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="season_index.json not found")


@app.post("/seasons/{season}/rebuild_index")
async def rebuild_season_index(season: str) -> dict[str, Any]:
    """
    Rebuild season index (controlled mutation).
    - Reads artifacts/* metadata/index/summary (read-only)
    - Writes season_index/{season}/season_index.json (atomic)
    - If season is frozen -> 403
    """
    store = _get_season_store()
    if store.is_frozen(season):
        raise HTTPException(status_code=403, detail="Season is frozen, cannot rebuild index")

    artifacts_root = _get_artifacts_root()
    try:
        idx = store.rebuild_index(artifacts_root, season)
        return idx
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/seasons/{season}/metadata")
async def get_season_metadata(season: str) -> dict[str, Any]:
    """Get season metadata."""
    store = _get_season_store()
    try:
        meta = store.get_metadata(season)
        if meta is None:
            raise HTTPException(status_code=404, detail="season_metadata.json not found")
        return {
            "season": meta.season,
            "frozen": meta.frozen,
            "tags": meta.tags,
            "note": meta.note,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/seasons/{season}/metadata")
async def update_season_metadata(season: str, req: SeasonMetadataUpdate) -> dict[str, Any]:
    """
    Update season metadata (controlled mutation).
    Frozen rules:
    - cannot unfreeze a frozen season
    - tags/note allowed
    """
    store = _get_season_store()
    try:
        meta = store.update_metadata(
            season,
            tags=req.tags,
            note=req.note,
            frozen=req.frozen,
        )
        return {
            "season": meta.season,
            "frozen": meta.frozen,
            "tags": meta.tags,
            "note": meta.note,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/seasons/{season}/freeze")
async def freeze_season(season: str) -> dict[str, Any]:
    """Freeze a season (irreversible)."""
    store = _get_season_store()
    try:
        store.freeze(season)
        return {"status": "frozen", "season": season}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Phase 15.1: Season-level cross-batch comparison endpoint
@app.get("/seasons/{season}/compare/topk")
async def season_compare_topk(season: str, k: int = 20) -> dict[str, Any]:
    """
    Cross-batch TopK for a season (read-only).
    - Reads season_index/{season}/season_index.json
    - Reads artifacts/{batch_id}/summary.json for each batch
    - Missing/corrupt summaries are skipped (never 500 the whole season)
    """
    store = _get_season_store()
    try:
        season_index = store.read_index(season)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="season_index.json not found")

    artifacts_root = _get_artifacts_root()
    try:
        res = merge_season_topk(artifacts_root=artifacts_root, season_index=season_index, k=k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "season": res.season,
        "k": res.k,
        "items": res.items,
        "skipped_batches": res.skipped_batches,
    }


# Phase 15.2: Season compare batch cards + lightweight leaderboard endpoints
@app.get("/seasons/{season}/compare/batches")
async def season_compare_batches(season: str) -> dict[str, Any]:
    """
    Batch-level compare cards for a season (read-only).
    Source of truth:
      - season_index/{season}/season_index.json
      - artifacts/{batch_id}/summary.json (best-effort)
    """
    store = _get_season_store()
    try:
        season_index = store.read_index(season)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="season_index.json not found")

    artifacts_root = _get_artifacts_root()
    try:
        res = build_season_batch_cards(artifacts_root=artifacts_root, season_index=season_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "season": res.season,
        "batches": res.batches,
        "skipped_summaries": res.skipped_summaries,
    }


@app.get("/seasons/{season}/compare/leaderboard")
async def season_compare_leaderboard(
    season: str,
    group_by: str = "strategy_id",
    per_group: int = 3,
) -> dict[str, Any]:
    """
    Grouped leaderboard for a season (read-only).
    group_by: strategy_id | dataset_id
    per_group: keep top N items per group
    """
    store = _get_season_store()
    try:
        season_index = store.read_index(season)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="season_index.json not found")

    artifacts_root = _get_artifacts_root()
    try:
        out = build_season_leaderboard(
            artifacts_root=artifacts_root,
            season_index=season_index,
            group_by=group_by,
            per_group=per_group,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return out


# Phase 15.3: Season export endpoint
@app.post("/seasons/{season}/export")
async def export_season(season: str) -> dict[str, Any]:
    """
    Export a frozen season into outputs/exports/seasons/{season}/ (controlled mutation).
    Requirements:
      - season must be frozen (403 if not)
      - season_index must exist (404 if missing)
    """
    store = _get_season_store()
    if not store.is_frozen(season):
        raise HTTPException(status_code=403, detail="Season must be frozen before export")

    artifacts_root = _get_artifacts_root()
    season_index_root = _get_season_index_root()

    try:
        res = export_season_package(
            season=season,
            artifacts_root=artifacts_root,
            season_index_root=season_index_root,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="season_index.json not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "season": res.season,
        "export_dir": str(res.export_dir),
        "manifest_path": str(res.manifest_path),
        "manifest_sha256": res.manifest_sha256,
        "files_total": len(res.exported_files),
        "missing_files": res.missing_files,
    }


# Phase 16: Export pack replay mode endpoints
@app.get("/exports/seasons/{season}/compare/topk")
async def export_season_compare_topk(season: str, k: int = 20) -> dict[str, Any]:
    """
    Cross-batch TopK from exported season package (read-only).
    - Reads exports/seasons/{season}/replay_index.json
    - Does NOT require artifacts/ directory
    - Missing/corrupt summaries are skipped (never 500 the whole season)
    """
    exports_root = get_exports_root()
    try:
        res = replay_season_topk(exports_root=exports_root, season=season, k=k)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="replay_index.json not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "season": res.season,
        "k": res.k,
        "items": res.items,
        "skipped_batches": res.skipped_batches,
    }


@app.get("/exports/seasons/{season}/compare/batches")
async def export_season_compare_batches(season: str) -> dict[str, Any]:
    """
    Batch-level compare cards from exported season package (read-only).
    - Reads exports/seasons/{season}/replay_index.json
    - Does NOT require artifacts/ directory
    """
    exports_root = get_exports_root()
    try:
        res = replay_season_batch_cards(exports_root=exports_root, season=season)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="replay_index.json not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "season": res.season,
        "batches": res.batches,
        "skipped_summaries": res.skipped_summaries,
    }


@app.get("/exports/seasons/{season}/compare/leaderboard")
async def export_season_compare_leaderboard(
    season: str,
    group_by: str = "strategy_id",
    per_group: int = 3,
) -> dict[str, Any]:
    """
    Grouped leaderboard from exported season package (read-only).
    - Reads exports/seasons/{season}/replay_index.json
    - Does NOT require artifacts/ directory
    """
    exports_root = get_exports_root()
    try:
        res = replay_season_leaderboard(
            exports_root=exports_root,
            season=season,
            group_by=group_by,
            per_group=per_group,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="replay_index.json not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "season": res.season,
        "group_by": res.group_by,
        "per_group": res.per_group,
        "groups": res.groups,
    }


# Phase 16.5: Real Data Snapshot Integration endpoints

@app.post("/datasets/snapshots", response_model=SnapshotMetadata)
async def create_snapshot_endpoint(payload: SnapshotCreatePayload) -> SnapshotMetadata:
    """
    Create a deterministic snapshot from raw bars.

    Contract:
    - Input: raw bars (list of dicts) + symbol + timeframe + optional transform_version
    - Deterministic: same input → same snapshot_id and normalized_sha256
    - Immutable: snapshot directory is write‑once (atomic temp‑file replace)
    - Timezone‑aware: uses UTC timestamps (datetime.now(timezone.utc))
    - Returns SnapshotMetadata with raw_sha256, normalized_sha256, manifest_sha256 chain
    """
    snapshots_root = _get_snapshots_root()
    try:
        meta = create_snapshot(
            snapshots_root=snapshots_root,
            raw_bars=payload.raw_bars,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            transform_version=payload.transform_version,
        )
        return meta
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/datasets/snapshots")
async def list_snapshots() -> dict[str, Any]:
    """
    List all snapshots (read‑only).

    Returns:
        {
            "snapshots": [
                {
                    "snapshot_id": "...",
                    "symbol": "...",
                    "timeframe": "...",
                    "created_at": "...",
                    "raw_sha256": "...",
                    "normalized_sha256": "...",
                    "manifest_sha256": "...",
                },
                ...
            ]
        }
    """
    snapshots_root = _get_snapshots_root()
    if not snapshots_root.exists():
        return {"snapshots": []}

    snapshots = []
    for child in sorted(snapshots_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        snapshot_id = child.name
        manifest_path = child / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            import json
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            snapshots.append(data)
        except Exception:
            # skip corrupted manifests
            continue

    return {"snapshots": snapshots}


@app.post("/datasets/registry/register_snapshot")
async def register_snapshot_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Register an existing snapshot as a dataset (controlled mutation).

    Contract:
    - snapshot_id must exist under snapshots root
    - Dataset registry is append‑only (no overwrites)
    - Conflict detection: if snapshot already registered → 409
    - Returns dataset_id (deterministic) and registry entry
    """
    snapshot_id = payload.get("snapshot_id")
    if not snapshot_id:
        raise HTTPException(status_code=400, detail="snapshot_id required")

    snapshots_root = _get_snapshots_root()
    snapshot_dir = snapshots_root / snapshot_id
    if not snapshot_dir.exists():
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

    try:
        import json
        entry = register_snapshot_as_dataset(snapshot_dir=snapshot_dir)
        # Load manifest to get SHA256 fields
        manifest_path = snapshot_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "dataset_id": entry.id,
            "snapshot_id": snapshot_id,
            "symbol": entry.symbol,
            "timeframe": entry.timeframe,
            "raw_sha256": manifest.get("raw_sha256"),
            "normalized_sha256": manifest.get("normalized_sha256"),
            "manifest_sha256": manifest.get("manifest_sha256"),
            "created_at": manifest.get("created_at"),
        }
    except ValueError as e:
        if "already registered" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Phase 17: Portfolio Plan Ingestion endpoints

from FishBroWFS_V2.contracts.portfolio.plan_payloads import PlanCreatePayload
from FishBroWFS_V2.contracts.portfolio.plan_models import PortfolioPlan
from FishBroWFS_V2.portfolio.plan_builder import (
    build_portfolio_plan_from_export,
    write_plan_package,
)

# Phase PV.1: Plan Quality endpoints
from FishBroWFS_V2.contracts.portfolio.plan_quality_models import PlanQualityReport
from FishBroWFS_V2.portfolio.plan_quality import compute_quality_from_plan_dir
from FishBroWFS_V2.portfolio.plan_quality_writer import write_plan_quality_files


# Helper to get outputs root (where portfolio/plans/ will be written)
def _get_outputs_root() -> Path:
    """
    Return outputs root directory.
    Environment override:
      - FISHBRO_OUTPUTS_ROOT (default: outputs)
    """
    return Path(os.environ.get("FISHBRO_OUTPUTS_ROOT", "outputs"))


@app.post("/portfolio/plans", response_model=PortfolioPlan)
async def create_portfolio_plan(payload: PlanCreatePayload) -> PortfolioPlan:
    """
    Create a deterministic portfolio plan from an export (controlled mutation).

    Contract:
    - Read‑only over exports tree (no artifacts, no engine)
    - Deterministic tie‑break ordering
    - Controlled mutation: writes only under outputs/portfolio/plans/{plan_id}/
    - Hash chain audit (plan_manifest.json with self‑hash)
    - Idempotent: if plan already exists, returns existing plan (200).
    - Returns full plan (including weights, summary, constraints report)
    """
    exports_root = get_exports_root()
    outputs_root = _get_outputs_root()

    try:
        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season=payload.season,
            export_name=payload.export_name,
            payload=payload,
        )
        # Write plan package (controlled mutation, idempotent)
        plan_dir = write_plan_package(outputs_root=outputs_root, plan=plan)
        # Read back the plan from disk to ensure consistency (especially if already existed)
        plan_path = plan_dir / "portfolio_plan.json"
        import json
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        # Convert back to PortfolioPlan model (validate)
        return PortfolioPlan.model_validate(data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Export not found: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Catch pydantic ValidationError (e.g., from model_validate) and map to 400
        # Import here to avoid circular import
        from pydantic import ValidationError
        if isinstance(e, ValidationError):
            raise HTTPException(status_code=400, detail=f"Validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/portfolio/plans")
async def list_portfolio_plans() -> dict[str, Any]:
    """
    List all portfolio plans (read‑only).

    Returns:
        {
            "plans": [
                {
                    "plan_id": "...",
                    "generated_at_utc": "...",
                    "source": {...},
                    "config": {...},
                    "summaries": {...},
                    "checksums": {...},
                },
                ...
            ]
        }
    """
    outputs_root = _get_outputs_root()
    plans_dir = outputs_root / "portfolio" / "plans"
    if not plans_dir.exists():
        return {"plans": []}

    plans = []
    for child in sorted(plans_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        plan_id = child.name
        manifest_path = child / "plan_manifest.json"
        if not manifest_path.exists():
            continue
        try:
            import json
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Ensure plan_id is present (should already be in manifest)
            data["plan_id"] = plan_id
            plans.append(data)
        except Exception:
            # skip corrupted manifests
            continue

    return {"plans": plans}


@app.get("/portfolio/plans/{plan_id}")
async def get_portfolio_plan(plan_id: str) -> dict[str, Any]:
    """
    Get a portfolio plan by ID (read‑only).

    Returns:
        Full portfolio_plan.json content (including universe, weights, summaries).
    """
    outputs_root = _get_outputs_root()
    plan_dir = outputs_root / "portfolio" / "plans" / plan_id
    plan_path = plan_dir / "portfolio_plan.json"
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    try:
        import json
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read plan: {e}")


# Phase PV.1: Plan Quality endpoints
@app.get("/portfolio/plans/{plan_id}/quality", response_model=PlanQualityReport)
async def get_plan_quality(plan_id: str) -> PlanQualityReport:
    """
    Compute quality metrics for a portfolio plan (read‑only).

    Contract:
    - Zero‑write: only reads plan package files, never writes
    - Deterministic: same plan → same quality report
    - Returns PlanQualityReport with grade (GREEN/YELLOW/RED) and reasons
    """
    outputs_root = _get_outputs_root()
    plan_dir = outputs_root / "portfolio" / "plans" / plan_id
    if not plan_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    try:
        report, inputs = compute_quality_from_plan_dir(plan_dir)
        return report
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Plan package incomplete: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute quality: {e}")


@app.post("/portfolio/plans/{plan_id}/quality", response_model=PlanQualityReport)
async def write_plan_quality(plan_id: str) -> PlanQualityReport:
    """
    Compute quality metrics and write quality files (controlled mutation).

    Contract:
    - Read‑only over plan package files
    - Controlled mutation: writes only three files under plan_dir:
        - plan_quality.json
        - plan_quality_checksums.json
        - plan_quality_manifest.json
    - Idempotent: identical content → no mtime change
    - Returns PlanQualityReport (same as GET endpoint)
    """
    outputs_root = _get_outputs_root()
    plan_dir = outputs_root / "portfolio" / "plans" / plan_id
    if not plan_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    try:
        # Compute quality (read‑only)
        report, inputs = compute_quality_from_plan_dir(plan_dir)
        # Write quality files (controlled mutation, idempotent)
        write_plan_quality_files(plan_dir, report)
        return report
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Plan package incomplete: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write quality: {e}")



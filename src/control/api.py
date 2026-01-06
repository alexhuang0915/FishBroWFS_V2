
"""FastAPI endpoints for B5-C Mission Control."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import mimetypes
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel

from collections import deque

from control.jobs_db import (
    create_job,
    get_job,
    init_db,
    list_jobs,
    request_pause,
    request_stop,
)
from control.paths import run_log_path
from control.preflight import PreflightResult, run_preflight
from control.control_types import DBJobSpec, JobRecord, StopMode, JobStatus

# Phase 13: Batch submit
from control.batch_submit import (
    BatchSubmitRequest,
    BatchSubmitResponse,
    submit_batch,
)

# Phase 14: Batch execution & governance
from control.artifacts import (
    canonical_json_bytes,
    compute_sha256,
    write_atomic_json,
    build_job_manifest,
)
from control.batch_index import build_batch_index
from control.batch_execute import (
    BatchExecutor,
    BatchExecutionState,
    JobExecutionState,
    run_batch,
    retry_failed,
)
from control.batch_aggregate import compute_batch_summary
from control.governance import (
    BatchGovernanceStore,
    BatchMetadata,
)

# Phase 14: Governance Observability via HTTP Pull (Heartbeat Pattern)
from control.run_status import read_status

# Phase 14.1: Read-only batch API helpers
from control.batch_api import (
    read_execution,
    read_summary,
    read_index,
    read_metadata_optional,
    count_states,
    get_batch_state,
    list_artifacts_tree,
)

# Phase 15.0: Season-level governance and index builder
from control.season_api import SeasonStore, get_season_index_root

# Phase 15.1: Season-level cross-batch comparison
from control.season_compare import merge_season_topk

# Phase 15.2: Season compare batch cards + lightweight leaderboard
from control.season_compare_batches import (
    build_season_batch_cards,
    build_season_leaderboard,
)

# Phase 15.3: Season freeze package / export pack
from control.season_export import export_season_package, get_exports_root

# Phase GUI.1: GUI payload contracts
from contracts.gui import (
    SubmitBatchPayload,
    FreezeSeasonPayload,
    ExportSeasonPayload,
    CompareRequestPayload,
)

# Phase 16: Export pack replay mode
from control.season_export_replay import (
    load_replay_index,
    replay_season_topk,
    replay_season_batch_cards,
    replay_season_leaderboard,
)

# Phase 12: Meta API imports
from data.dataset_registry import DatasetIndex
from strategy.registry import StrategyRegistryResponse

# Phase A: Service Identity
from core.service_identity import get_service_identity

# Phase B: Worker Spawn Governance
from control.worker_spawn_policy import can_spawn_worker, validate_pidfile

# Phase 16.5: Real Data Snapshot Integration
from contracts.data.snapshot_payloads import SnapshotCreatePayload
from contracts.data.snapshot_models import SnapshotMetadata
from control.data_snapshot import create_snapshot, compute_snapshot_id, normalize_bars
from control.dataset_registry_mutation import register_snapshot_as_dataset

# Phase A: Registry endpoints
from portfolio.instruments import load_instruments_config

# Phase A: Data readiness helpers
from control.bars_store import bars_dir, resampled_bars_path
from control.features_store import features_dir, features_path

# Phase B: Reporting endpoints
from core.reporting.models import StrategyReportV1, PortfolioReportV1
from control.reporting.io import (
    read_job_artifact,
    read_portfolio_admission_artifact,
    job_report_exists,
    portfolio_report_exists,
    read_job_report,
    read_portfolio_report,
)

# Phase D: Portfolio Build API
from control.portfolio.api_v1 import router as portfolio_router

# Phase E.4: Outputs summary endpoint
from control.supervisor import list_jobs

# Default DB path (can be overridden via environment)
DEFAULT_DB_PATH = Path("outputs/jobs.db")

# Phase 12: Registry cache
_DATASET_INDEX: DatasetIndex | None = None
_STRATEGY_REGISTRY: StrategyRegistryResponse | None = None
_INSTRUMENTS_CONFIG: Any | None = None  # InstrumentsConfig from portfolio.instruments


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


def _load_instruments_config_from_file() -> dict[str, Any]:
    """Private implementation: load instruments config from file (fail fast)."""
    import json
    from pathlib import Path

    config_path = Path("configs/portfolio/instruments.yaml")
    if not config_path.exists():
        raise RuntimeError(
            f"Instruments config not found: {config_path}\n"
            "Please ensure configs/portfolio/instruments.yaml exists"
        )

    # Use portfolio.instruments.load_instruments_config to parse YAML
    from portfolio.instruments import load_instruments_config
    config = load_instruments_config(config_path)
    return config


def _get_instruments_config() -> dict[str, Any]:
    """Return cached instruments config, loading if necessary."""
    global _INSTRUMENTS_CONFIG
    if _INSTRUMENTS_CONFIG is None:
        _INSTRUMENTS_CONFIG = _load_instruments_config_from_file()
    return _INSTRUMENTS_CONFIG


def _reload_instruments_config() -> dict[str, Any]:
    """Force reload instruments config from file and update cache."""
    global _INSTRUMENTS_CONFIG
    _INSTRUMENTS_CONFIG = _load_instruments_config_from_file()
    return _INSTRUMENTS_CONFIG


def load_instruments_config() -> dict[str, Any]:
    """Load instruments config. Supports monkeypatching."""
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_instruments_config")

    # If monkeypatched, call patched function
    if current is not _LOAD_INSTRUMENTS_CONFIG_ORIGINAL:
        return current()

    # If cache is available, return it
    if _INSTRUMENTS_CONFIG is not None:
        return _INSTRUMENTS_CONFIG

    # Fallback for CLI/unit-test paths (may touch filesystem)
    return _load_instruments_config_from_file()


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
    from strategy.registry import (
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
_LOAD_INSTRUMENTS_CONFIG_ORIGINAL = load_instruments_config


def _try_prime_registries() -> None:
    """Prime cache on startup."""
    global _DATASET_INDEX, _STRATEGY_REGISTRY, _INSTRUMENTS_CONFIG
    try:
        _DATASET_INDEX = load_dataset_index()
        _STRATEGY_REGISTRY = load_strategy_registry()
        _INSTRUMENTS_CONFIG = load_instruments_config()
    except Exception:
        _DATASET_INDEX = None
        _STRATEGY_REGISTRY = None
        _INSTRUMENTS_CONFIG = None


def _prime_registries_with_feedback() -> dict[str, Any]:
    """Prime registries and return detailed feedback."""
    global _DATASET_INDEX, _STRATEGY_REGISTRY, _INSTRUMENTS_CONFIG
    result = {
        "dataset_loaded": False,
        "strategy_loaded": False,
        "instruments_loaded": False,
        "dataset_error": None,
        "strategy_error": None,
        "instruments_error": None,
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
    
    # Try instruments
    try:
        _INSTRUMENTS_CONFIG = load_instruments_config()
        result["instruments_loaded"] = True
    except Exception as e:
        _INSTRUMENTS_CONFIG = None
        result["instruments_error"] = str(e)
    
    result["success"] = result["dataset_loaded"] and result["strategy_loaded"] and result["instruments_loaded"]
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

# Middleware to reject path traversal attempts before Starlette normalizes them
from fastapi import Request, Response
from urllib.parse import unquote
import sys

@app.middleware("http")
async def reject_path_traversal_middleware(request: Request, call_next):
    """
    Reject any request whose raw path contains '..' (path traversal) for portfolio and job artifact endpoints.
    This ensures that path normalization does not hide traversal attempts.
    """
    raw_path_bytes = request.scope.get("raw_path", b"")
    raw_path = raw_path_bytes.decode("utf-8") if isinstance(raw_path_bytes, bytes) else raw_path_bytes
    # Decode percent-encoded characters to catch %2e%2e
    decoded_path = unquote(raw_path)
    # Check for '..' in the decoded path
    if ".." in decoded_path:
        # Determine if this is a portfolio or job artifact endpoint
        if "/api/v1/portfolios/" in raw_path or "/api/v1/jobs/" in raw_path:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid artifact filename."}
            )
    # Continue processing
    response = await call_next(request)
    return response

# API v1 router for versioned endpoints
api_v1 = APIRouter(prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@api_v1.get("/run_status")
async def get_run_status() -> dict[str, Any]:
    """
    Read-only endpoint for run status observability via HTTP pull (Heartbeat Pattern).
    
    Contract:
    - GET only, no mutation
    - If run_status.json exists → return JSON
    - If missing → return default IDLE state
    - No partial JSON ever observed (atomic writes guarantee)
    - No Socket.IO / WebSocket / SSE
    """
    try:
        return read_status()
    except Exception:
        # If file missing or unreadable, return default IDLE state
        return {
            "state": "IDLE",
            "progress": 0,
            "step": "init",
            "message": "",
            "started_at": None,
            "updated_at": None,
            "eta_seconds": 0,
            "artifacts": {},
            "error": None
        }


@api_v1.get("/identity")
async def identity() -> dict[str, Any]:
    """Service identity endpoint for topology observability."""
    db_path = get_db_path()
    ident = get_service_identity(service_name="control_api", db_path=db_path)
    return ident


@api_v1.get("/meta/datasets", response_model=DatasetIndex)
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


@api_v1.get("/meta/strategies", response_model=StrategyRegistryResponse)
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


@api_v1.post("/meta/prime")
async def prime_registries() -> dict[str, Any]:
    """
    Prime registries cache (explicit trigger).
    
    This endpoint allows the UI to manually trigger registry loading
    when the automatic startup preload fails (e.g., missing files).
    
    Returns detailed feedback about what succeeded/failed.
    """
    return _prime_registries_with_feedback()


@api_v1.get("/registry/instruments")
async def registry_instruments() -> list[str]:
    """
    Return list of instrument symbols (keys from instruments config).
    
    Contract:
    - Returns simple array of strings, e.g., ["MNQ", "MES", ...]
    - If instruments config not loaded, returns 503.
    - Must not access filesystem during request handling.
    """
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_instruments_config")

    # Enforce no filesystem access during request handling
    if _INSTRUMENTS_CONFIG is None and current is _LOAD_INSTRUMENTS_CONFIG_ORIGINAL:
        raise HTTPException(status_code=503, detail="Instruments registry not preloaded")

    config = load_instruments_config()
    # config is a dict with instrument symbols as keys? Let's assume it's a dict mapping symbol -> instrument definition
    # We'll extract keys.
    if isinstance(config, dict):
        symbols = list(config.keys())
    else:
        # If config is something else (maybe a list), fallback
        symbols = []
    return symbols


@api_v1.get("/registry/datasets")
async def registry_datasets() -> list[str]:
    """
    Return list of dataset IDs (simple strings).
    
    Contract:
    - Returns simple array of strings, e.g., ["None", "VX", "ZN", ...]
    - If dataset registry not loaded, returns 503.
    - Must not access filesystem during request handling.
    """
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_dataset_index")

    # Enforce no filesystem access during request handling
    if _DATASET_INDEX is None and current is _LOAD_DATASET_INDEX_ORIGINAL:
        raise HTTPException(status_code=503, detail="Dataset registry not preloaded")

    idx = load_dataset_index()
    # Return dataset IDs sorted
    dataset_ids = sorted([ds.id for ds in idx.datasets])
    return dataset_ids


@api_v1.get("/registry/strategies")
async def registry_strategies() -> list[str]:
    """
    Return list of strategy IDs (simple strings).
    
    Contract:
    - Returns simple array of strings, e.g., ["s1_v1", "s2_v1", ...]
    - If strategy registry not loaded, returns 503.
    - Must not access filesystem during request handling.
    """
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_strategy_registry")

    # Enforce no filesystem access during request handling
    if _STRATEGY_REGISTRY is None and current is _LOAD_STRATEGY_REGISTRY_ORIGINAL:
        raise HTTPException(status_code=503, detail="Strategy registry not preloaded")

    reg = load_strategy_registry()
    strategy_ids = sorted([s.strategy_id for s in reg.strategies])
    return strategy_ids


class ReadinessResponse(BaseModel):
    """Response for GET /api/v1/readiness/{season}/{dataset_id}/{timeframe}."""
    season: str
    dataset_id: str
    timeframe: str
    bars_ready: bool
    features_ready: bool
    bars_path: Optional[str] = None
    features_path: Optional[str] = None
    error: Optional[str] = None


@api_v1.get("/readiness/{season}/{dataset_id}/{timeframe}", response_model=ReadinessResponse)
async def readiness_check(season: str, dataset_id: str, timeframe: str) -> ReadinessResponse:
    """
    Check if bars and features are ready for a given season, dataset, and timeframe.
    
    Contract:
    - Returns readiness status without performing any writes.
    - If bars/features files exist, returns paths (relative to outputs root).
    - If missing, returns false with optional error.
    - Must not construct filesystem paths in UI; UI must call this endpoint.
    """
    # Determine outputs root (default "outputs")
    outputs_root = Path("outputs")
    # Build paths using the imported helpers
    bars_path = resampled_bars_path(outputs_root, season, dataset_id, timeframe)
    features_path = features_path(outputs_root, season, dataset_id, timeframe)
    
    bars_ready = bars_path.exists()
    features_ready = features_path.exists()
    
    return ReadinessResponse(
        season=season,
        dataset_id=dataset_id,
        timeframe=timeframe,
        bars_ready=bars_ready,
        features_ready=features_ready,
        bars_path=str(bars_path) if bars_ready else None,
        features_path=str(features_path) if features_ready else None,
        error=None,
    )


class SubmitJobRequest(BaseModel):
    spec: DBJobSpec


class JobListResponse(BaseModel):
    """Response for GET /api/v1/jobs."""
    job_id: str
    type: str = "strategy"  # default type
    status: str
    created_at: str
    finished_at: Optional[str] = None
    strategy_name: Optional[str] = None
    instrument: Optional[str] = None
    timeframe: Optional[str] = None
    run_mode: Optional[str] = None
    season: Optional[str] = None
    duration_seconds: Optional[float] = None
    score: Optional[float] = None


def _job_record_to_response(job: JobRecord) -> JobListResponse:
    """Convert a JobRecord to a JobListResponse."""
    # Extract config snapshot
    config = job.spec.config_snapshot if job.spec.config_snapshot else {}
    # Determine type (could be "strategy" or "portfolio"? default "strategy")
    job_type = "strategy"
    # Extract strategy_name from config
    strategy_name = config.get("strategy_id")
    # Extract instrument and timeframe from config (may be nested)
    instrument = None
    timeframe = None
    # Look for instrument in config (could be under "instrument" or "symbol")
    if "instrument" in config:
        instrument = config["instrument"]
    elif "symbol" in config:
        instrument = config["symbol"]
    # Look for timeframe
    if "timeframe" in config:
        timeframe = config["timeframe"]
    # Extract run_mode from config
    run_mode = config.get("run_mode")
    # Extract season from spec
    season = job.spec.season
    # Format timestamps
    created_at = job.created_at.isoformat() if job.created_at else ""
    finished_at = job.finished_at.isoformat() if job.finished_at else None
    # Compute duration_seconds
    duration_seconds = None
    if created_at and finished_at:
        try:
            from datetime import datetime
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            finished_dt = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
            duration_seconds = (finished_dt - created_dt).total_seconds()
        except Exception:
            pass
    elif created_at and job.status == JobStatus.RUNNING:
        # For RUNNING jobs, compute duration from now
        try:
            from datetime import datetime, timezone
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            now_dt = datetime.now(timezone.utc)
            duration_seconds = (now_dt - created_dt).total_seconds()
        except Exception:
            pass
    # Score extraction (from report artifacts) - placeholder for now
    score = None
    # TODO: fetch from strategy_report_v1.json if exists
    return JobListResponse(
        job_id=job.job_id,
        type=job_type,
        status=job.status.value if isinstance(job.status, JobStatus) else job.status,
        created_at=created_at,
        finished_at=finished_at,
        strategy_name=strategy_name,
        instrument=instrument,
        timeframe=timeframe,
        run_mode=run_mode,
        season=season,
        duration_seconds=duration_seconds,
        score=score,
    )


@api_v1.get("/jobs", response_model=list[JobListResponse])
async def list_jobs_endpoint(limit: int = 50) -> list[JobListResponse]:
    db_path = get_db_path()
    jobs = list_jobs(db_path, limit=limit)
    return [_job_record_to_response(job) for job in jobs]


@api_v1.get("/jobs/{job_id}", response_model=JobListResponse)
async def get_job_endpoint(job_id: str) -> JobListResponse:
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
        return _job_record_to_response(job)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# -----------------------------------------------------------------------------
# Phase A: Artifact endpoints helpers
# -----------------------------------------------------------------------------

def _get_jobs_evidence_root() -> Path:
    """
    Return the root directory for job evidence bundles (Phase C).
    LOCKED: outputs/jobs/
    """
    return Path("outputs/jobs")


def _get_job_evidence_dir(job_id: str) -> Path:
    """Return the evidence directory for a job, ensuring containment."""
    root = _get_jobs_evidence_root()
    job_dir = root / job_id
    # Security: ensure job_dir is within root (no path traversal)
    try:
        job_dir.resolve().relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Job ID contains path traversal")
    return job_dir


def _get_strategy_report_v1_path(job_id: str) -> Path:
    """
    Return the path to strategy_report_v1.json for a job.
    Security: ensure containment within outputs/jobs/<job_id>/
    """
    root = Path("outputs/jobs")
    job_dir = root / job_id
    # Security: ensure job_dir is within root (no path traversal)
    try:
        job_dir.resolve().relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Job ID contains path traversal")
    return job_dir / "strategy_report_v1.json"


def _get_portfolio_report_v1_path(portfolio_id: str) -> Path:
    """
    Return the path to portfolio_report_v1.json for a portfolio admission.
    Security: ensure containment within outputs/portfolios/<portfolio_id>/admission/
    """
    root = Path("outputs/portfolios")
    admission_dir = root / portfolio_id / "admission"
    # Security: ensure admission_dir is within root (no path traversal)
    try:
        admission_dir.resolve().relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Portfolio ID contains path traversal")
    return admission_dir / "portfolio_report_v1.json"


def _list_artifacts(job_id: str) -> list[dict[str, Any]]:
    """
    List files in the job evidence directory.
    Returns list of dicts with filename, size_bytes, content_type, sha256, url.
    """
    job_dir = _get_job_evidence_dir(job_id)
    if not job_dir.exists():
        return []
    
    artifacts = []
    for file_path in job_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(job_dir)
            # Skip hidden files and internal evidence files? Include all.
            # Ensure filename is a simple basename (no slashes) for URL safety
            # We'll store relative path as filename (string)
            filename = str(rel_path)
            # Compute size
            size = file_path.stat().st_size
            # Guess content type
            content_type, _ = mimetypes.guess_type(str(file_path))
            if content_type is None:
                content_type = "application/octet-stream"
            # Compute SHA256 (optional, can be expensive for large files)
            sha256 = None
            try:
                if size < 10 * 1024 * 1024:  # 10 MB limit
                    with open(file_path, "rb") as f:
                        sha256 = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                pass
            artifacts.append({
                "filename": filename,
                "size_bytes": size,
                "content_type": content_type,
                "sha256": sha256,
                "url": f"/api/v1/jobs/{job_id}/artifacts/{filename}"
            })
    return artifacts


def _validate_artifact_filename_or_403(filename: str) -> str:
    """
    Validate artifact filename; raise HTTP 403 if invalid (path traversal, slashes, etc.).
    Returns the original filename if valid.
    """
    if filename is None or filename.strip() == "":
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    if filename in (".", ".."):
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    if ".." in filename:
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    # Ensure it's a basename (no directory components)
    from pathlib import Path
    if filename != Path(filename).name:
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    return filename


def _get_policy_check_link(job_id: str) -> Optional[str]:
    """Return URL to policy_check.json if it exists."""
    job_dir = _get_job_evidence_dir(job_id)
    policy_path = job_dir / "policy_check.json"
    if policy_path.exists():
        return f"/api/v1/jobs/{job_id}/artifacts/policy_check.json"
    return None


def _get_stdout_tail_link(job_id: str) -> Optional[str]:
    """Return URL to stdout tail endpoint."""
    # Always present if job evidence directory exists
    job_dir = _get_job_evidence_dir(job_id)
    if job_dir.exists():
        return f"/api/v1/jobs/{job_id}/logs/stdout_tail"
    return None


class ArtifactIndexResponse(BaseModel):
    """Response for GET /api/v1/jobs/{job_id}/artifacts."""
    job_id: str
    links: dict[str, Optional[str]]
    files: list[dict[str, Any]]


class RevealEvidencePathResponse(BaseModel):
    """Response for GET /api/v1/jobs/{job_id}/reveal_evidence_path."""
    approved: bool
    path: str


@api_v1.post("/jobs")
async def submit_job_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Create a job.

    Backward compatible body formats:
    1) Legacy: POST a JobSpec as flat JSON fields
    2) Wrapped: {"spec": <JobSpec>}
    """
    db_path = get_db_path()
    require_worker_or_503(db_path)

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


@api_v1.post("/jobs/{job_id}/stop")
async def stop_job_endpoint(job_id: str, mode: StopMode = StopMode.SOFT) -> dict[str, Any]:
    db_path = get_db_path()
    request_stop(db_path, job_id, mode)
    return {"ok": True}


@api_v1.post("/jobs/{job_id}/pause")
async def pause_job_endpoint(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    db_path = get_db_path()
    pause = payload.get("pause", True)
    request_pause(db_path, job_id, pause)
    return {"ok": True}


@api_v1.get("/jobs/{job_id}/preflight", response_model=PreflightResult)
async def preflight_endpoint(job_id: str) -> PreflightResult:
    db_path = get_db_path()
    job = get_job(db_path, job_id)
    return run_preflight(job.spec.config_snapshot)


@api_v1.post("/jobs/{job_id}/check", response_model=PreflightResult)
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


@api_v1.get("/jobs/{job_id}/run_log_tail")
async def run_log_tail_endpoint(job_id: str, n: int = 200) -> dict[str, Any]:
    db_path = get_db_path()
    job = get_job(db_path, job_id)
    run_id = job.run_id or ""
    if not run_id:
        return {"ok": True, "lines": [], "truncated": False}
    path = run_log_path(Path(job.spec.outputs_root), job.spec.season, run_id)
    lines, truncated = read_tail(path, n=n)
    return {"ok": True, "lines": lines, "truncated": truncated}


@api_v1.get("/jobs/{job_id}/log_tail")
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


# -----------------------------------------------------------------------------
# Phase A: Artifact endpoints
# -----------------------------------------------------------------------------

@api_v1.get("/jobs/{job_id}/artifacts", response_model=ArtifactIndexResponse)
async def get_artifacts_index(job_id: str) -> ArtifactIndexResponse:
    """
    Return artifact index for a job (Phase C evidence bundle).
    
    Contract:
    - job_id must exist in jobs DB (404 if not)
    - Evidence directory must exist (may be empty)
    - Links include reveal_evidence_url, stdout_tail_url, policy_check_url, strategy_report_v1_url (null)
    - Files list includes all files under outputs/jobs/<job_id>/
    """
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    # Build links
    links = {
        "reveal_evidence_url": f"/api/v1/jobs/{job_id}/reveal_evidence_path",
        "stdout_tail_url": _get_stdout_tail_link(job_id),
        "policy_check_url": _get_policy_check_link(job_id),
        "strategy_report_v1_url": None,  # Will be updated below if report exists
    }
    
    # Check if strategy report exists
    report_path = _get_strategy_report_v1_path(job_id)
    if report_path.exists():
        links["strategy_report_v1_url"] = f"/api/v1/reports/strategy/{job_id}"
    
    files = _list_artifacts(job_id)
    
    return ArtifactIndexResponse(
        job_id=job_id,
        links=links,
        files=files,
    )


@api_v1.get("/jobs/{job_id}/artifacts/{filename}")
async def get_artifact_file(job_id: str, filename: str):
    """
    Serve a single artifact file from the job evidence directory.
    
    Security:
    - filename must be a simple basename (no slashes, no path traversal)
    - Must enforce containment within outputs/jobs/<job_id>/
    - Returns 404 if file not found, 403 if path traversal detected.
    """
    # Validate filename does not contain slashes or path traversal attempts
    filename = _validate_artifact_filename_or_403(filename)
    
    job_dir = _get_job_evidence_dir(job_id)
    file_path = job_dir / filename
    
    # Ensure file_path is within job_dir (double-check containment)
    try:
        file_path.resolve().relative_to(job_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal detected")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = "application/octet-stream"
    
    # For text/plain or JSON, we can return as plain text; for binary, use FileResponse
    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=filename,
    )


@api_v1.get("/jobs/{job_id}/logs/stdout_tail")
async def stdout_tail_endpoint(job_id: str, n: int = 200) -> dict[str, Any]:
    """
    Return last n lines of the job's stdout log (from evidence bundle).
    
    Contract:
    - If stdout.log exists in evidence directory, return its tail.
    - If not, fallback to run_log_tail (legacy).
    - Returns 200 even if log file missing.
    """
    job_dir = _get_job_evidence_dir(job_id)
    stdout_path = job_dir / "stdout.log"
    
    if stdout_path.exists():
        lines, truncated = read_tail(stdout_path, n=n)
        return {"ok": True, "lines": lines, "truncated": truncated}
    
    # Fallback to existing log_tail endpoint (which uses run_log_path)
    # We'll reuse the same logic as log_tail_endpoint but with a different path.
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


@api_v1.get("/jobs/{job_id}/reveal_evidence_path", response_model=RevealEvidencePathResponse)
async def reveal_evidence_path(job_id: str) -> RevealEvidencePathResponse:
    """
    Return the absolute path to the job evidence directory after containment check.
    
    Security:
    - Must ensure job_id does not contain path traversal.
    - Must ensure the resolved path is within the locked evidence root (outputs/jobs/).
    - Returns 404 if evidence directory does not exist.
    """
    job_dir = _get_job_evidence_dir(job_id)
    
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job evidence directory not found")
    
    # Already validated containment in _get_job_evidence_dir
    return RevealEvidencePathResponse(
        approved=True,
        path=str(job_dir.resolve()),
    )


@api_v1.get("/jobs/{job_id}/report_link")
async def get_report_link_endpoint(job_id: str) -> dict[str, Any]:
    """
    Get report_link for a job.

    Phase 6 rule: Always return Viewer URL if run_id exists.
    Viewer will handle missing/invalid artifacts gracefully.

    Returns:
        - ok: Always True if job exists
        - report_link: Report link URL (always present if run_id exists)
    """
    from control.report_links import build_report_link

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


def _check_worker_status(db_path: Path) -> dict[str, Any]:
    """
    Check worker status (pidfile existence, process alive, heartbeat age).
    
    Returns dict with:
        - alive: bool
        - pid: int or None
        - last_heartbeat_age_sec: float or None
        - reason: str (diagnostic)
        - expected_db: str
    """
    pidfile = db_path.parent / "worker.pid"
    heartbeat_file = db_path.parent / "worker.heartbeat"
    
    if not pidfile.exists():
        return {
            "alive": False,
            "pid": None,
            "last_heartbeat_age_sec": None,
            "reason": "pidfile missing",
            "expected_db": str(db_path),
        }
    
    # Validate pidfile
    valid, reason = validate_pidfile(pidfile, db_path)
    if not valid:
        return {
            "alive": False,
            "pid": None,
            "last_heartbeat_age_sec": None,
            "reason": reason,
            "expected_db": str(db_path),
        }
    
    # Read PID
    try:
        pid = int(pidfile.read_text().strip())
    except (ValueError, OSError):
        return {
            "alive": False,
            "pid": None,
            "last_heartbeat_age_sec": None,
            "reason": "pidfile corrupted",
            "expected_db": str(db_path),
        }
    
    # Check heartbeat file age if exists
    last_heartbeat_age_sec = None
    if heartbeat_file.exists():
        try:
            mtime = heartbeat_file.stat().st_mtime
            last_heartbeat_age_sec = time.time() - mtime
        except OSError:
            pass
    
    return {
        "alive": True,
        "pid": pid,
        "last_heartbeat_age_sec": last_heartbeat_age_sec,
        "reason": "worker alive",
        "expected_db": str(db_path),
    }


def require_worker_or_503(db_path: Path) -> None:
    """
    If worker not alive, raise HTTPException(status_code=503, detail=...)
    
    Precondition check before accepting job submissions.
    
    Special case: In test mode with FISHBRO_ALLOW_SPAWN_IN_TESTS=1,
    allow submission even without worker (tests assume worker auto-spawn).
    """
    import os
    
    # Check if we're in test mode with override
    if os.getenv("FISHBRO_ALLOW_SPAWN_IN_TESTS") == "1":
        # Test mode: skip worker check, assume worker will be auto-spawned
        # or test doesn't need a real worker
        return
    
    status = _check_worker_status(db_path)
    
    if not status["alive"]:
        # Worker not alive
        raise HTTPException(
            status_code=503,
            detail={
                "error": "WORKER_UNAVAILABLE",
                "message": "No active worker daemon detected. Start worker and retry.",
                "worker": {
                    "alive": False,
                    "pid": None,
                    "last_heartbeat_age_sec": None,
                    "expected_db": str(db_path),
                },
                "action": f"Run: PYTHONPATH=src .venv/bin/python3 -u -m control.worker_main {db_path}"
            }
        )
    
    # Check heartbeat age if available
    if status["last_heartbeat_age_sec"] is not None and status["last_heartbeat_age_sec"] > 5.0:
        # Worker exists but heartbeat is stale
        raise HTTPException(
            status_code=503,
            detail={
                "error": "WORKER_UNAVAILABLE",
                "message": "Worker heartbeat stale (>5s). Restart worker.",
                "worker": {
                    "alive": True,
                    "pid": status["pid"],
                    "last_heartbeat_age_sec": status["last_heartbeat_age_sec"],
                    "expected_db": str(db_path),
                },
                "action": f"Run: PYTHONPATH=src .venv/bin/python3 -u -m control.worker_main {db_path}"
            }
        )
    
    # Worker is alive and responsive
    return


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
    # Check if worker is already running (enhanced pidfile validation)
    pidfile = db_path.parent / "worker.pid"
    if pidfile.exists():
        valid, reason = validate_pidfile(pidfile, db_path)
        if valid:
            return  # Worker already running
        # pidfile is stale or mismatched, remove it
        pidfile.unlink(missing_ok=True)

    # Spawn guard: enforce governance rules
    allowed, reason = can_spawn_worker(db_path)
    if not allowed:
        raise RuntimeError(f"Worker spawn denied: {reason}")

    # Prepare log file (same directory as db_path)
    logs_dir = db_path.parent  # usually outputs/.../control/
    logs_dir.mkdir(parents=True, exist_ok=True)
    worker_log = logs_dir / "worker_process.log"

    # Open in append mode, line-buffered
    out = open(worker_log, "a", buffering=1, encoding="utf-8")  # noqa: SIM115
    try:
        # Start worker in background
        proc = subprocess.Popen(
            [sys.executable, "-m", "control.worker_main", str(db_path)],
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
@api_v1.post("/jobs/batch", response_model=BatchSubmitResponse)
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
    require_worker_or_503(db_path)
    
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


@api_v1.get("/batches/{batch_id}/status", response_model=BatchStatusResponse)
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


@api_v1.get("/batches/{batch_id}/summary", response_model=BatchSummaryResponse)
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


@api_v1.post("/batches/{batch_id}/retry")
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
        from control.batch_execute import retry_failed
        _executor = retry_failed(batch_id, artifacts_root)

        return {
            "status": "retry_started",
            "batch_id": batch_id,
            "message": "Retry initiated for failed jobs",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry batch: {e}")


@api_v1.get("/batches/{batch_id}/index")
async def get_batch_index(batch_id: str) -> dict[str, Any]:
    """Get batch index.json (read-only)."""
    artifacts_root = _get_artifacts_root()
    try:
        idx = read_index(artifacts_root, batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="index.json not found")
    return idx


@api_v1.get("/batches/{batch_id}/artifacts")
async def get_batch_artifacts(batch_id: str) -> dict[str, Any]:
    """List artifacts tree for a batch (read-only)."""
    artifacts_root = _get_artifacts_root()
    try:
        tree = list_artifacts_tree(artifacts_root, batch_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="batch artifacts not found")
    return tree


@api_v1.get("/batches/{batch_id}/metadata", response_model=BatchMetadata)
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


@api_v1.patch("/batches/{batch_id}/metadata", response_model=BatchMetadata)
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


@api_v1.post("/batches/{batch_id}/freeze")
async def freeze_batch(batch_id: str) -> dict[str, str]:
    """Freeze a batch (irreversible)."""
    store = _get_governance_store()
    try:
        store.freeze(batch_id)
        return {"status": "frozen", "batch_id": batch_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Phase 15.0: Season-level governance and index endpoints
@api_v1.get("/seasons/{season}/index")
async def get_season_index(season: str) -> dict[str, Any]:
    """Get season_index.json (read-only)."""
    store = _get_season_store()
    try:
        return store.read_index(season)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="season_index.json not found")


@api_v1.post("/seasons/{season}/rebuild_index")
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


@api_v1.get("/seasons/{season}/metadata")
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


@api_v1.patch("/seasons/{season}/metadata")
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


@api_v1.post("/seasons/{season}/freeze")
async def freeze_season(season: str) -> dict[str, Any]:
    """Freeze a season (irreversible)."""
    store = _get_season_store()
    try:
        store.freeze(season)
        return {"status": "frozen", "season": season}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Phase 15.1: Season-level cross-batch comparison endpoint
@api_v1.get("/seasons/{season}/compare/topk")
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
@api_v1.get("/seasons/{season}/compare/batches")
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


@api_v1.get("/seasons/{season}/compare/leaderboard")
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
@api_v1.post("/seasons/{season}/export")
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
@api_v1.get("/exports/seasons/{season}/compare/topk")
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


@api_v1.get("/exports/seasons/{season}/compare/batches")
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


@api_v1.get("/exports/seasons/{season}/compare/leaderboard")
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

@api_v1.post("/datasets/snapshots", response_model=SnapshotMetadata)
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


@api_v1.get("/datasets/snapshots")
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


@api_v1.post("/datasets/registry/register_snapshot")
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

from contracts.portfolio.plan_payloads import PlanCreatePayload
from contracts.portfolio.plan_models import PortfolioPlan
from portfolio.plan_builder import (
    build_portfolio_plan_from_export,
    write_plan_package,
)

# Phase PV.1: Plan Quality endpoints
from contracts.portfolio.plan_quality_models import PlanQualityReport
from portfolio.plan_quality import compute_quality_from_plan_dir
from portfolio.plan_quality_writer import write_plan_quality_files


# Helper to get outputs root (where portfolio/plans/ will be written)
def _get_outputs_root() -> Path:
    """
    Return outputs root directory.
    Environment override:
      - FISHBRO_OUTPUTS_ROOT (default: outputs)
    """
    return Path(os.environ.get("FISHBRO_OUTPUTS_ROOT", "outputs"))


@api_v1.post("/portfolio/plans", response_model=PortfolioPlan)
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


@api_v1.get("/portfolio/plans")
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


@api_v1.get("/portfolio/plans/{plan_id}")
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


# Worker Status API (Phase 4: DEEPSEEK — NUCLEAR SPEC)
@api_v1.get("/worker/status")
async def worker_status() -> dict[str, Any]:
    """
    Get worker daemon status (read‑only).
    
    Returns:
        - alive: bool (worker process is alive and responsive)
        - pid: int or None
        - last_heartbeat_age_sec: float or None (seconds since last heartbeat)
        - reason: str (diagnostic message)
        - expected_db: str (database path worker is attached to)
        - can_spawn: bool (whether worker can be spawned according to policy)
        - spawn_reason: str (if can_spawn is False, explains why)
    
    Safety Contract:
    - Never kills or modifies worker state
    - Read‑only: only checks pidfile, heartbeat, process existence
    - Returns 200 even if worker is dead (alive: false)
    - Worker daemon is never killed by default
    """
    db_path = get_db_path()
    status = _check_worker_status(db_path)
    
    # Check if worker can be spawned according to policy
    try:
        from control.worker_spawn_policy import can_spawn_worker
        allowed, reason = can_spawn_worker(db_path)
        status["can_spawn"] = allowed
        status["spawn_reason"] = reason
    except Exception:
        # If policy check fails, default to False
        status["can_spawn"] = False
        status["spawn_reason"] = "policy check failed"
    
    return status


# Worker Emergency Stop API (Phase 5: DEEPSEEK — NUCLEAR SPEC)
class WorkerStopRequest(BaseModel):
    """Request for emergency worker stop."""
    force: bool = False
    reason: Optional[str] = None


@api_v1.post("/worker/stop")
async def worker_stop(req: WorkerStopRequest) -> dict[str, Any]:
    """
    Emergency stop worker daemon (controlled mutation).
    
    Safety Contract:
    - Must validate worker is alive before attempting stop
    - Must validate worker belongs to this control API instance (pidfile validation)
    - Must NOT kill worker if there are active jobs (unless force=True)
    - Must clean up pidfile and heartbeat file after successful stop
    - Returns detailed status of what was stopped
    
    Validation Rules:
    1. Worker must be alive (alive: true in status)
    2. Worker must belong to this control API (pidfile validation passes)
    3. If force=False, check for active jobs (jobs with status RUNNING)
    4. If active jobs exist and force=False → 409 Conflict
    5. If validation passes, send SIGTERM, wait up to 5s, then SIGKILL if needed
    6. Clean up pidfile and heartbeat file after stop
    
    Returns:
        - stopped: bool (whether worker was stopped)
        - pid: int or None
        - signal: str (TERM or KILL)
        - active_jobs_count: int (number of active jobs at time of stop)
        - force_used: bool (whether force=True was required)
        - cleanup_performed: bool (whether pidfile/heartbeat were cleaned up)
    """
    import signal
    import psutil
    
    db_path = get_db_path()
    status = _check_worker_status(db_path)
    
    # 1. Check if worker is alive
    if not status["alive"]:
        return {
            "stopped": False,
            "pid": None,
            "signal": None,
            "active_jobs_count": 0,
            "force_used": req.force,
            "cleanup_performed": False,
            "error": "Worker not alive",
            "status": status
        }
    
    pid = status["pid"]
    if pid is None:
        return {
            "stopped": False,
            "pid": None,
            "signal": None,
            "active_jobs_count": 0,
            "force_used": req.force,
            "cleanup_performed": False,
            "error": "No PID found",
            "status": status
        }
    
    # 2. Validate pidfile (ensure worker belongs to this control API)
    pidfile = db_path.parent / "worker.pid"
    valid, reason = validate_pidfile(pidfile, db_path)
    if not valid:
        return {
            "stopped": False,
            "pid": pid,
            "signal": None,
            "active_jobs_count": 0,
            "force_used": req.force,
            "cleanup_performed": False,
            "error": f"PID validation failed: {reason}",
            "status": status
        }
    
    # 3. Check for active jobs (unless force=True)
    active_jobs_count = 0
    if not req.force:
        try:
            from control.jobs_db import list_jobs
            jobs = list_jobs(db_path)
            active_jobs_count = sum(1 for job in jobs if job.status == "RUNNING")
            if active_jobs_count > 0:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "ACTIVE_JOBS_RUNNING",
                        "message": f"Cannot stop worker with {active_jobs_count} active jobs",
                        "active_jobs_count": active_jobs_count,
                        "action": "Use force=True to override, or stop jobs first"
                    }
                )
        except Exception as e:
            # If we can't check jobs, be conservative and require force
            if not req.force:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "JOB_CHECK_FAILED",
                        "message": "Cannot verify active jobs status",
                        "action": "Use force=True to override"
                    }
                )
    
    # 4. Attempt to stop worker
    stopped = False
    signal_used = None
    cleanup_performed = False
    
    try:
        # Send SIGTERM first
        os.kill(pid, signal.SIGTERM)
        signal_used = "TERM"
        
        # Wait up to 5 seconds for graceful shutdown
        for _ in range(50):  # 50 * 0.1 = 5 seconds
            try:
                os.kill(pid, 0)  # Check if process exists
                time.sleep(0.1)
            except ProcessLookupError:
                # Process terminated
                stopped = True
                break
        
        # If still alive after SIGTERM, send SIGKILL
        if not stopped:
            try:
                os.kill(pid, signal.SIGKILL)
                signal_used = "KILL"
                time.sleep(0.5)
                stopped = True
            except ProcessLookupError:
                stopped = True
    except ProcessLookupError:
        # Process already dead
        stopped = True
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "STOP_FAILED",
                "message": f"Failed to stop worker: {str(e)}",
                "pid": pid
            }
        )
    
    # 5. Clean up pidfile and heartbeat file
    if stopped:
        try:
            pidfile.unlink(missing_ok=True)
            heartbeat_file = db_path.parent / "worker.heartbeat"
            heartbeat_file.unlink(missing_ok=True)
            cleanup_performed = True
        except Exception:
            # Cleanup failed, but worker is stopped
            pass
    
    return {
        "stopped": stopped,
        "pid": pid,
        "signal": signal_used,
        "active_jobs_count": active_jobs_count,
        "force_used": req.force,
        "cleanup_performed": cleanup_performed,
        "status": status,
        "reason": req.reason
    }


# Phase PV.1: Plan Quality endpoints
@api_v1.get("/portfolio/plans/{plan_id}/quality", response_model=PlanQualityReport)
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


@api_v1.post("/portfolio/plans/{plan_id}/quality", response_model=PlanQualityReport)
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


# -----------------------------------------------------------------------------
# Phase B: Reporting endpoints
# -----------------------------------------------------------------------------

@api_v1.get("/reports/strategy/{job_id}", response_model=StrategyReportV1)
async def get_strategy_report_v1(job_id: str) -> StrategyReportV1:
    """
    Return precomputed StrategyReportV1 JSON for a job.
    
    Contract:
    - If outputs/jobs/<job_id>/strategy_report_v1.json exists:
      - return its JSON content with application/json
    - Else:
      - 404 with clear message: "strategy_report_v1.json not found; run job or upgrade workers"
    - No heavy compute inside request handler.
    """
    report_path = _get_strategy_report_v1_path(job_id)
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail="strategy_report_v1.json not found; run job or upgrade workers"
        )
    
    try:
        import json
        data = json.loads(report_path.read_text(encoding="utf-8"))
        # Validate against Pydantic model
        return StrategyReportV1.model_validate(data)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read or parse strategy report: {e}"
        )


@api_v1.get("/reports/portfolio/{portfolio_id}", response_model=PortfolioReportV1)
async def get_portfolio_report_v1(portfolio_id: str) -> PortfolioReportV1:
    """
    Return precomputed PortfolioReportV1 JSON for a portfolio admission.
    
    Contract:
    - If outputs/portfolios/<portfolio_id>/admission/portfolio_report_v1.json exists:
      - return its JSON content with application/json
    - Else:
      - 404 with clear message: "portfolio_report_v1.json not found; run portfolio build or upgrade workers"
    - No heavy compute inside request handler.
    """
    report_path = _get_portfolio_report_v1_path(portfolio_id)
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail="portfolio_report_v1.json not found; run portfolio build or upgrade workers"
        )
    
    try:
        import json
        data = json.loads(report_path.read_text(encoding="utf-8"))
        # Validate against Pydantic model
        return PortfolioReportV1.model_validate(data)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read or parse portfolio report: {e}"
        )


@api_v1.get("/outputs/summary")
async def get_outputs_summary() -> dict[str, Any]:
    """
    Return a human-usable summary of outputs (jobs and portfolios) for clean UI navigation.
    
    Contract:
    - Version 1.0 schema
    - No filesystem scanning (use supervisor job store)
    - No filesystem paths returned
    - Dumb client: UI must use this endpoint, not scan filesystem
    """
    import json
    from datetime import datetime, timezone
    
    # Get jobs from supervisor
    jobs = list_jobs()  # Returns list of JobRow objects
    
    # Separate strategy runs from portfolio builds
    strategy_jobs = []
    portfolio_jobs = []
    
    for job in jobs:
        job_type = job.job_type
        if job_type == "BUILD_PORTFOLIO_V2":
            portfolio_jobs.append(job)
        else:
            strategy_jobs.append(job)
    
    # Process strategy jobs for "recent" list (most recent first)
    recent_jobs = []
    status_counts = {}
    
    for job in strategy_jobs[:20]:  # Limit to 20 most recent
        job_id = job.job_id
        status = job.state
        
        # Parse spec_json to get config
        spec = {}
        try:
            spec = json.loads(job.spec_json)
        except (json.JSONDecodeError, AttributeError):
            pass
        
        params = spec.get("params", {})
        metadata = spec.get("metadata", {})
        
        # Count statuses
        status_counts[status] = status_counts.get(status, 0) + 1
        
        # Extract fields
        strategy_name = params.get("strategy_id", "")
        instrument = params.get("instrument") or params.get("symbol", "")
        timeframe = params.get("timeframe", "")
        season = metadata.get("season", "")
        run_mode = params.get("run_mode", "")
        created_at = job.created_at
        finished_at = None  # Supervisor doesn't track finished_at directly
        
        # Check if report exists
        report_url = None
        report_path = _get_strategy_report_v1_path(job_id)
        if report_path.exists():
            report_url = f"/api/v1/reports/strategy/{job_id}"
        
        recent_jobs.append({
            "job_id": job_id,
            "status": status,
            "strategy_name": strategy_name,
            "instrument": instrument,
            "timeframe": timeframe,
            "season": season,
            "run_mode": run_mode,
            "created_at": created_at,
            "finished_at": finished_at,
            "links": {
                "artifacts_url": f"/api/v1/jobs/{job_id}/artifacts",
                "report_url": report_url
            }
        })
    
    # Process portfolio builds for "recent" list
    recent_portfolios = []
    
    for job in portfolio_jobs[:20]:  # Limit to 20 most recent
        job_id = job.job_id
        status = job.state
        
        # Parse spec_json
        spec = {}
        try:
            spec = json.loads(job.spec_json)
        except (json.JSONDecodeError, AttributeError):
            pass
        
        params = spec.get("params", {})
        metadata = spec.get("metadata", {})
        
        # Extract portfolio_id from params or use job_id
        portfolio_id = params.get("portfolio_id") or job_id
        
        # Try to get admission counts (placeholder - would need to read admission artifacts)
        admitted_count = 0
        rejected_count = 0
        
        # Check if portfolio report exists
        report_url = None
        report_path = _get_portfolio_report_v1_path(portfolio_id)
        if report_path.exists():
            report_url = f"/api/v1/reports/portfolio/{portfolio_id}"
        
        recent_portfolios.append({
            "portfolio_id": portfolio_id,
            "created_at": job.created_at,
            "season": metadata.get("season", ""),
            "timeframe": params.get("timeframe", ""),
            "admitted_count": admitted_count,
            "rejected_count": rejected_count,
            "links": {
                "artifacts_url": f"/api/v1/portfolios/{portfolio_id}/artifacts",
                "report_url": report_url
            }
        })
    
    # Build response
    return {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jobs": {
            "recent": recent_jobs,
            "counts_by_status": status_counts
        },
        "portfolios": {
            "recent": recent_portfolios
        },
        "informational": {
            "orphaned_artifact_dirs_count": 0,  # Placeholder
            "notes": ["Summary generated from supervisor job store"]
        }
    }


# Register API v1 router
app.include_router(api_v1)

# Register portfolio API router (Phase D)
app.include_router(portfolio_router)



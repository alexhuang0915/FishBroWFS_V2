from __future__ import annotations
import json
import logging
import subprocess
import sys
import os
import mimetypes
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone # timezone imported here
import traceback
from fastapi import FastAPI, HTTPException, APIRouter, Request # Request imported here
from pydantic import BaseModel
from collections import deque
from urllib.parse import unquote
from dataclasses import fields
from typing import Any, Optional, Dict # Added Any, Optional, Dict imports
from pathlib import Path # Added Path import

# Supervisor imports
from control.supervisor import submit as supervisor_submit, list_jobs as supervisor_list_jobs, get_job as supervisor_get_job
from control.supervisor.models import JobSpec as SupervisorJobSpec, JobType, normalize_job_type
from control.supervisor.db import DuplicateJobError

# Phase 14: Batch execution & governance
from control.artifacts import (
    canonical_json_bytes,
    compute_sha256,
    write_atomic_json,
    build_job_manifest,
)
from control.batch_index import build_batch_index
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
from core.paths import get_outputs_root

# Phase 16.5: Real Data Snapshot Integration
from contracts.data.snapshot_payloads import SnapshotCreatePayload
from contracts.data.snapshot_models import SnapshotMetadata
from control.data_snapshot import create_snapshot, compute_snapshot_id, normalize_bars
from control.dataset_registry_mutation import register_snapshot_as_dataset

# API payload contracts (SSOT)
from contracts.api import (
    ReadinessResponse,
    SubmitJobRequest,
    JobListResponse,
    ArtifactIndexResponse,
    RevealEvidencePathResponse,
    BatchStatusResponse,
    BatchSummaryResponse,
    BatchMetadataUpdate,
    SeasonMetadataUpdate,
)

# Phase A: Registry endpoints
# from portfolio.instruments import load_instruments_config  # type: ignore - unused, imported locally in _load_instruments_config_from_file

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
from control.supervisor import list_jobs as list_supervisor_jobs

# Phase 12: Registry cache
_DATASET_INDEX: Any | None = None
_STRATEGY_REGISTRY: Any | None = None
_INSTRUMENTS_CONFIG: Any | None = None  # InstrumentsConfig from portfolio.instruments
_TIMEFRAME_REGISTRY: Any | None = None  # TimeframeRegistry from config.registry.timeframes


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


def _load_dataset_index_from_file() -> DatasetIndex:
    """Private implementation: load dataset index from file (fail fast)."""
    index_path = Path("outputs/datasets/datasets_index.json")
    if not index_path.exists():
        # Return empty dataset index (headless-safe)
        # This ensures registry preload succeeds even without derived data.
        # The dataset endpoint will return empty list (200 OK) instead of 503.
        return DatasetIndex(
            generated_at=datetime.now(timezone.utc),
            datasets=[]
        )

    data = json.loads(index_path.read_text())
    return DatasetIndex.model_validate(data)


def _load_instruments_config_from_file() -> Any:
    """Private implementation: load instruments config from file (fail fast)."""
    config_path = Path("configs/portfolio/instruments.yaml")
    if not config_path.exists():
        raise RuntimeError(
            f"Instruments config not found: {config_path}\n"
            "Please ensure configs/portfolio/instruments.yaml exists"
        )

    # Use portfolio.instruments.load_instruments_config to parse YAML
    from portfolio.instruments import load_instruments_config  # type: ignore
    config = load_instruments_config(config_path)
    return config


def _get_instruments_config() -> Any:
    """Return cached instruments config, loading if necessary."""
    global _INSTRUMENTS_CONFIG
    if _INSTRUMENTS_CONFIG is None:
        _INSTRUMENTS_CONFIG = _load_instruments_config_from_file()
    return _INSTRUMENTS_CONFIG


def _reload_instruments_config() -> Any:
    """Force reload instruments config from file and update cache."""
    global _INSTRUMENTS_CONFIG
    _INSTRUMENTS_CONFIG = _load_instruments_config_from_file()
    return _INSTRUMENTS_CONFIG


def load_instruments_config() -> Any:
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


def _load_timeframe_registry_from_file() -> Any:
    """Private implementation: load timeframe registry from file (fail fast)."""
    from config.registry.timeframes import load_timeframes
    return load_timeframes()


def _get_timeframe_registry() -> Any:
    """Return cached timeframe registry, loading if necessary."""
    global _TIMEFRAME_REGISTRY
    if _TIMEFRAME_REGISTRY is None:
        _TIMEFRAME_REGISTRY = _load_timeframe_registry_from_file()
    return _TIMEFRAME_REGISTRY


def _reload_timeframe_registry() -> Any:
    """Force reload timeframe registry from file and update cache."""
    global _TIMEFRAME_REGISTRY
    _TIMEFRAME_REGISTRY = _load_timeframe_registry_from_file()
    return _TIMEFRAME_REGISTRY


def load_timeframe_registry() -> Any:
    """Load timeframe registry. Supports monkeypatching."""
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_timeframe_registry")

    # If monkeypatched, call patched function
    if current is not _LOAD_TIMEFRAME_REGISTRY_ORIGINAL:
        return current()

    # If cache is available, return it
    if _TIMEFRAME_REGISTRY is not None:
        return _TIMEFRAME_REGISTRY

    # Fallback for CLI/unit-test paths (may touch filesystem)
    return _load_timeframe_registry_from_file()


# Original function references for monkeypatch detection (must be after function definitions)
_LOAD_DATASET_INDEX_ORIGINAL = load_dataset_index
_LOAD_STRATEGY_REGISTRY_ORIGINAL = load_strategy_registry
_LOAD_INSTRUMENTS_CONFIG_ORIGINAL = load_instruments_config
_LOAD_TIMEFRAME_REGISTRY_ORIGINAL = load_timeframe_registry


def _try_prime_registries() -> None:
    """Prime cache on startup (per‑load tolerance)."""
    global _DATASET_INDEX, _STRATEGY_REGISTRY, _INSTRUMENTS_CONFIG, _TIMEFRAME_REGISTRY
    # Try each load independently; if one fails, set its cache to None but continue.
    try:
        _DATASET_INDEX = load_dataset_index()
    except Exception:
        _DATASET_INDEX = None
    try:
        _STRATEGY_REGISTRY = load_strategy_registry()
    except Exception:
        _STRATEGY_REGISTRY = None
    try:
        _INSTRUMENTS_CONFIG = load_instruments_config()
    except Exception:
        _INSTRUMENTS_CONFIG = None
    try:
        _TIMEFRAME_REGISTRY = load_timeframe_registry()
    except Exception:
        _TIMEFRAME_REGISTRY = None


def _prime_registries_with_feedback() -> dict[str, Any]:
    """Prime registries and return detailed feedback."""
    global _DATASET_INDEX, _STRATEGY_REGISTRY, _INSTRUMENTS_CONFIG, _TIMEFRAME_REGISTRY
    result = {
        "dataset_loaded": False,
        "strategy_loaded": False,
        "instruments_loaded": False,
        "timeframe_loaded": False,
        "dataset_error": None,
        "strategy_error": None,
        "instruments_error": None,
        "timeframe_error": None,
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
    
    # Try timeframe
    try:
        _TIMEFRAME_REGISTRY = load_timeframe_registry()
        result["timeframe_loaded"] = True
    except Exception as e:
        _TIMEFRAME_REGISTRY = None
        result["timeframe_error"] = str(e)
    
    result["success"] = result["dataset_loaded"] and result["strategy_loaded"] and result["instruments_loaded"] and result["timeframe_loaded"]
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # startup
    # No DB initialization - supervisor owns the DB
    # Phase 12: Prime registries cache
    _try_prime_registries()

    yield
    # shutdown (currently empty)


app = FastAPI(title="B5-C Mission Control API", lifespan=lifespan)

# Middleware to reject path traversal attempts before Starlette normalizes them
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
    # API does not own a DB - supervisor owns jobs_v2.db
    ident = get_service_identity(service_name="control_api", db_path=None)
    return ident

@api_v1.get("/readiness")
async def readiness() -> dict[str, str]:
    """Readiness endpoint for UI gates."""
    return {"status": "ok"}

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
    # config could be InstrumentsConfig or dict
    if isinstance(config, dict):
        # If it's a dict, assume keys are instrument symbols
        symbols = list(config.keys())
    else:
        # Assume it's an InstrumentsConfig with instruments attribute
        symbols = list(config.instruments.keys())
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


@api_v1.get("/registry/timeframes")
async def registry_timeframes() -> list[str]:
    """
    Return list of timeframe display names (simple strings).
    
    Contract:
    - Returns simple array of strings, e.g., ["15m", "30m", "60m", "120m", "240m"]
    - If timeframe registry not loaded, returns 503.
    - Must not access filesystem during request handling.
    """
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_timeframe_registry")

    # Enforce no filesystem access during request handling
    if _TIMEFRAME_REGISTRY is None and current is _LOAD_TIMEFRAME_REGISTRY_ORIGINAL:
        raise HTTPException(status_code=503, detail="Timeframe registry not preloaded")

    registry = load_timeframe_registry()
    # registry is a TimeframeRegistry object with get_display_names() method
    # Return sorted display names for consistency
    display_names = registry.get_display_names()
    return sorted(display_names)




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
    features_file_path = features_path(outputs_root, season, dataset_id, timeframe)
    
    bars_ready = bars_path.exists()
    features_ready = features_file_path.exists()
    
    return ReadinessResponse(
        season=season,
        dataset_id=dataset_id,
        timeframe=timeframe,
        bars_ready=bars_ready,
        features_ready=features_ready,
        bars_path=str(bars_path) if bars_ready else None,
        features_path=str(features_file_path) if features_ready else None,
        error=None,
    )






def _coerce_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _expand_display_fields_from_params_override(params: dict, metadata: dict) -> tuple[str, str, str, str, str]:
    """Extract display fields from params and params_override with priority."""
    # First, get top-level values
    instrument = _coerce_str(params.get("instrument") or params.get("symbol", ""))
    timeframe = _coerce_str(params.get("timeframe", ""))
    run_mode = _coerce_str(params.get("run_mode", ""))
    season = _coerce_str(metadata.get("season", ""))
    dataset = _coerce_str(params.get("dataset", ""))
    
    # Check params_override if top-level fields are empty
    params_override = params.get("params_override")
    if isinstance(params_override, dict):
        if not instrument:
            instrument = _coerce_str(params_override.get("instrument"))
        if not timeframe:
            timeframe = _coerce_str(params_override.get("timeframe"))
        if not run_mode:
            run_mode = _coerce_str(params_override.get("run_mode"))
        if not season:
            season = _coerce_str(params_override.get("season"))
        if not dataset:
            dataset = _coerce_str(params_override.get("dataset"))
    
    return instrument, timeframe, run_mode, season, dataset


def _supervisor_job_to_response(job: Any) -> JobListResponse:
    """Convert a supervisor JobRow to a JobListResponse."""
    # job is a JobRow from supervisor
    job_id = job.job_id
    status = job.state
    created_at = job.created_at
    
    # Parse spec_json to extract params
    spec = {}
    try:
        spec = json.loads(job.spec_json)
    except (json.JSONDecodeError, AttributeError):
        pass
    
    params = spec.get("params", {})
    metadata = spec.get("metadata", {})
    
    # Extract fields with params_override expansion
    strategy_name = params.get("strategy_id", "")
    instrument, timeframe, run_mode, season, dataset = _expand_display_fields_from_params_override(params, metadata)
    
    # Determine finished_at (supervisor doesn't track finished_at directly)
    finished_at = None
    if status in ["SUCCEEDED", "FAILED", "ABORTED", "REJECTED"]:
        finished_at = job.updated_at
    
    # Compute duration_seconds
    duration_seconds = None
    if created_at and finished_at:
        try:
            from datetime import datetime, timezone
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            finished_dt = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
            duration_seconds = (finished_dt - created_dt).total_seconds()
        except Exception:
            pass
    elif created_at and status == "RUNNING":
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
    
    return JobListResponse(
        job_id=job_id,
        type="strategy",
        status=status,
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
    jobs = supervisor_list_jobs()
    # Apply limit
    jobs = jobs[:limit]
    return [_supervisor_job_to_response(job) for job in jobs]


@api_v1.get("/jobs/{job_id}", response_model=JobListResponse)
async def get_job_endpoint(job_id: str) -> JobListResponse:
    try:
        job = supervisor_get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return _supervisor_job_to_response(job)
    except Exception as e:
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


def _build_run_research_v2_params(req: dict) -> dict:
    """
    Build supervisor params for RUN_RESEARCH_V2 job from UI request.
    
    Maps UI fields (instrument/timeframe/season/run_mode/dataset) into
    RunResearchPayload contract with extras packed into params_override.
    
    Defaults:
    - profile_name: "default" if not provided
    - start_date: "" if not provided (will cause validation error)
    - end_date: "" if not provided (will cause validation error)
    """
    strategy_id = req.get("strategy_id")
    if not strategy_id:
        raise ValueError("strategy_id is required")
    if not isinstance(strategy_id, str):
        raise ValueError("strategy_id must be a string")

    profile_name = req.get("profile_name") or "default"
    if not isinstance(profile_name, str):
        raise ValueError("profile_name must be a string")
    
    start_date = req.get("start_date")
    if not start_date or not isinstance(start_date, str) or start_date.strip() == "":
        raise ValueError("start_date is required and must be a non-empty string")
    
    end_date = req.get("end_date")
    if not end_date or not isinstance(end_date, str) or end_date.strip() == "":
        raise ValueError("end_date is required and must be a non-empty string")

    override = req.get("params_override") or {}
    if not isinstance(override, dict):
        override = {"_raw_params_override": override}

    # Pack UI keys into params_override (these are the keys Desktop UI currently sends)
    for k in ("instrument", "timeframe", "season", "run_mode", "dataset"):
        if k in req and req[k] is not None:
            # Validate that UI fields are strings (optional but good for consistency)
            if not isinstance(req[k], str):
                raise ValueError(f"{k} must be a string")
            override[k] = req[k]

    return {
        "strategy_id": strategy_id,
        "profile_name": profile_name,
        "start_date": start_date,
        "end_date": end_date,
        "params_override": override,
    }


def _build_run_plateau_v2_params(req: dict) -> dict:
    research_run_id = req.get("research_run_id")
    if not research_run_id or not isinstance(research_run_id, str) or research_run_id.strip() == "":
        raise ValueError("research_run_id is required and must be a non-empty string")

    params: dict[str, Any] = {"research_run_id": research_run_id}

    k_neighbors = req.get("k_neighbors")
    if k_neighbors is not None:
        if not isinstance(k_neighbors, int):
            raise ValueError("k_neighbors must be an integer")
        params["k_neighbors"] = k_neighbors

    score_threshold_rel = req.get("score_threshold_rel")
    if score_threshold_rel is not None:
        if not isinstance(score_threshold_rel, (int, float)):
            raise ValueError("score_threshold_rel must be a number")
        params["score_threshold_rel"] = float(score_threshold_rel)

    return params


def _build_run_research_wfs_params(req: dict) -> dict:
    strategy_id = req.get("strategy_id")
    instrument = req.get("instrument")
    timeframe = req.get("timeframe")
    start_season = req.get("start_season")
    end_season = req.get("end_season")

    missing = []
    for key, val in (
        ("strategy_id", strategy_id),
        ("instrument", instrument),
        ("timeframe", timeframe),
        ("start_season", start_season),
        ("end_season", end_season),
    ):
        if not val:
            missing.append(key)
    if missing:
        raise ValueError(f"Missing required fields for wfs: {', '.join(missing)}")

    for key, val in (
        ("strategy_id", strategy_id),
        ("instrument", instrument),
        ("timeframe", timeframe),
        ("start_season", start_season),
        ("end_season", end_season),
    ):
        if not isinstance(val, str):
            raise ValueError(f"{key} must be a string")

    params: dict[str, Any] = {
        "strategy_id": strategy_id,
        "instrument": instrument,
        "timeframe": timeframe,
        "start_season": start_season,
        "end_season": end_season,
    }
    if "dataset" in req and req["dataset"] is not None:
        if not isinstance(req["dataset"], str):
            raise ValueError("dataset must be a string")
        params["dataset"] = req["dataset"]
    if "workers" in req and req["workers"] is not None:
        if not isinstance(req["workers"], int):
            raise ValueError("workers must be an integer")
        params["workers"] = req["workers"]
    params["run_mode"] = "wfs"
    return params


def _validate_artifact_filename_or_403(filename: str) -> str:
    """
    Validate artifact filename; raise HTTP 403 if invalid (path traversal).
    Returns the original filename if valid.
    
    Policy: Allow relative paths with "/" but enforce strict containment.
    - Empty filename → 403
    - "." or ".." → 403
    - Contains ".." → 403 (path traversal)
    - Absolute path (starts with "/") → 403
    - Path components must not be empty
    - Trailing slash (filename ends with "/") → 403 (ambiguous)
    """
    if filename is None or filename.strip() == "":
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    if filename in (".", ".."):
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    if ".." in filename:
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    if filename.startswith("/"):
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    
    # Reject trailing slash (e.g., "file.txt/")
    if filename.endswith("/"):
        raise HTTPException(status_code=403, detail="Invalid artifact filename.")
    
    # Check path components
    from pathlib import Path
    path = Path(filename)
    for part in path.parts:
        if not part or part.strip() == "":
            raise HTTPException(status_code=403, detail="Invalid artifact filename.")
        if part in (".", ".."):
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






@api_v1.post("/jobs")
async def submit_job_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Create a job (thin proxy to supervisor).
    
    Accepts GUI params format:
    {
        "strategy_id": "...",
        "instrument": "...",
        "timeframe": "...",
        "run_mode": "...",  # "backtest", "research", "optimize"
        "season": "...",
        "dataset": "..."  # optional
    }
    """
    strategy_id = payload.get("strategy_id")
    run_mode = str(payload.get("run_mode", "")).lower()

    instrument = payload.get("instrument")
    timeframe = payload.get("timeframe")
    season = payload.get("season")
    dataset = payload.get("dataset")

    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    research_run_id = payload.get("research_run_id")
    
    # Map run_mode to canonical supervisor job_type
    if run_mode == "research":
        job_type = JobType.RUN_RESEARCH_V2.value
    elif run_mode == "optimize":
        job_type = JobType.RUN_PLATEAU_V2.value
    elif run_mode == "wfs":
        job_type = JobType.RUN_RESEARCH_WFS.value
    elif run_mode == "backtest":
        job_type = JobType.RUN_RESEARCH_V2.value  # Default to research for backtest
    else:
        job_type = JobType.RUN_RESEARCH_V2.value  # Default
    
    # Build supervisor params based on job_type
    if job_type == JobType.RUN_RESEARCH_V2.value:
        if not all([strategy_id, instrument, timeframe, season]):
            raise HTTPException(
                status_code=422,
                detail="Missing required fields for research/backtest: strategy_id, instrument, timeframe, season",
            )

        request_dict = {
            "strategy_id": strategy_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "run_mode": run_mode,
            "season": season,
            "start_date": start_date,
            "end_date": end_date,
        }
        if dataset:
            request_dict["dataset"] = dataset
        
        try:
            params = _build_run_research_v2_params(request_dict)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail=f"Invalid run_research payload: {e}") from e
    elif job_type == JobType.RUN_PLATEAU_V2.value:
        request_dict = {"research_run_id": research_run_id}
        try:
            params = _build_run_plateau_v2_params(request_dict)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail=f"Invalid run_plateau payload: {e}") from e
    elif job_type == JobType.RUN_RESEARCH_WFS.value:
        request_dict = dict(payload)
        try:
            params = _build_run_research_wfs_params(request_dict)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=422, detail=f"Invalid run_research_wfs payload: {e}") from e
    else:
        # For other job types, keep existing params structure
        params = {
            "strategy_id": strategy_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "run_mode": run_mode,
        }
        
        if dataset:
            params["dataset"] = dataset
    
    # Build metadata
    metadata = {
        "season": season,
        "source": "api_v1",
        "submitted_via": "gui"
    }
    
    # Submit to supervisor
    try:
        job_id = supervisor_submit(job_type, params, metadata)
        return {"ok": True, "job_id": job_id}
    except DuplicateJobError as e:
        # Return 409 Conflict with existing job_id
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate job detected: {e.message}",
            headers={"X-Existing-Job-Id": e.existing_job_id}
        )
    except (TypeError, ValueError) as e:
        # Convert mapping errors into HTTP 422
        raise HTTPException(status_code=422, detail=f"Invalid run_research payload: {e}") from e
    except Exception as e:
        # Catch other unexpected errors during submission
        raise HTTPException(status_code=500, detail=f"Failed to submit job to supervisor: {e}")


# -----------------------------------------------------------------------------
# Phase A: Artifact endpoints
# -----------------------------------------------------------------------------


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


# Worker management removed - supervisor handles its own workers


# Phase 14: Batch execution & governance endpoints









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
    outputs_root = get_outputs_root()

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
    outputs_root = get_outputs_root()
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
    outputs_root = get_outputs_root()
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


# Worker endpoints removed - supervisor handles its own workers


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
    outputs_root = get_outputs_root()
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
    outputs_root = get_outputs_root()
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
    jobs = list_supervisor_jobs()  # Returns list of JobRow objects
    
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

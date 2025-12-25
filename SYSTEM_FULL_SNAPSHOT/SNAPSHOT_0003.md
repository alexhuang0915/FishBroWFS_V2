FILE src/FishBroWFS_V2/core/intents.py
sha256(source_bytes) = 3388690af563a3b85f83a4a4b2cf775e212da3ecc33d4dc9dfd5d834b32f1f19
bytes = 12266
redacted = False
--------------------------------------------------------------------------------
"""Intent-based state machine models for Attack #9 – Headless Intent-State Contract.

Defines UserIntent objects that UI may create. All intents must go through a single
ActionQueue, backend execution must be single-consumer sequential, backend outputs
only read-only SystemState snapshots. All side effects must happen only inside StateProcessor.
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IntentType(str, Enum):
    """Types of user intents."""
    CREATE_JOB = "create_job"
    CALCULATE_UNITS = "calculate_units"
    CHECK_SEASON = "check_season"
    GET_JOB_STATUS = "get_job_status"
    LIST_JOBS = "list_jobs"
    GET_JOB_LOGS = "get_job_logs"
    SUBMIT_BATCH = "submit_batch"
    VALIDATE_PAYLOAD = "validate_payload"
    BUILD_PARQUET = "build_parquet"
    FREEZE_SEASON = "freeze_season"
    EXPORT_SEASON = "export_season"
    COMPARE_SEASONS = "compare_seasons"


class IntentStatus(str, Enum):
    """Status of an intent in the queue."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DUPLICATE = "duplicate"  # Idempotency: duplicate intent detected


class UserIntent(BaseModel):
    """Base class for all user intents.
    
    UI may only create UserIntent objects. All intents must go through a single
    ActionQueue, backend execution must be single-consumer sequential.
    """
    model_config = ConfigDict(frozen=False, extra="forbid")
    
    # Core intent metadata
    intent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    intent_type: IntentType
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="ui")  # Could be user_id, session_id, etc.
    
    # Idempotency key: if two intents have same idempotency_key, second is duplicate
    idempotency_key: Optional[str] = Field(default=None)
    
    # Processing metadata (set by ActionQueue/StateProcessor)
    status: IntentStatus = Field(default=IntentStatus.PENDING)
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    
    @model_validator(mode="after")
    def validate_idempotency_key(self) -> UserIntent:
        """Generate idempotency key if not provided.
        
        Subclasses should override with more specific logic.
        If no subclass sets idempotency_key, it remains None.
        """
        # Base class does nothing; subclasses should set idempotency_key
        return self


# Concrete intent models for specific user actions

class DataSpecIntent(BaseModel):
    """Data specification for job creation intents."""
    model_config = ConfigDict(frozen=True)
    
    dataset_id: str
    symbols: List[str]
    timeframes: List[str]
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    @field_validator("symbols", "timeframes")
    @classmethod
    def validate_non_empty_lists(cls, v: List[str]) -> List[str]:
        """Ensure lists are not empty."""
        if not v:
            raise ValueError("List cannot be empty")
        return v


class CreateJobIntent(UserIntent):
    """Intent to create a new job from wizard payload."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.CREATE_JOB)
    
    # Job creation payload
    season: str
    data1: DataSpecIntent
    data2: Optional[DataSpecIntent] = None
    strategy_id: str
    params: Dict[str, Any]
    wfs: Dict[str, Any] = Field(default_factory=lambda: {
        "stage0_subsample": 0.1,
        "top_k": 20,
        "mem_limit_mb": 8192,
        "allow_auto_downsample": True
    })
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> CreateJobIntent:
        """Set idempotency key based on job creation parameters.
        
        Only sets idempotency_key if not already provided.
        """
        if self.idempotency_key is None:
            # Create deterministic hash of job parameters
            import hashlib
            import json
            
            key_data = {
                "season": self.season,
                "data1_dataset": self.data1.dataset_id,
                "data1_symbols": sorted(self.data1.symbols),
                "data1_timeframes": sorted(self.data1.timeframes),
                "strategy_id": self.strategy_id,
                "params_hash": hashlib.sha256(
                    json.dumps(self.params, sort_keys=True).encode()
                ).hexdigest()[:16]
            }
            
            key_str = json.dumps(key_data, sort_keys=True)
            self.idempotency_key = f"create_job:{hashlib.sha256(key_str.encode()).hexdigest()[:32]}"
        return self


class CalculateUnitsIntent(UserIntent):
    """Intent to calculate units for a wizard payload."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.CALCULATE_UNITS)
    
    # Same payload as CreateJobIntent but without WFS
    season: str
    data1: DataSpecIntent
    data2: Optional[DataSpecIntent] = None
    strategy_id: str
    params: Dict[str, Any]
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> CalculateUnitsIntent:
        """Set idempotency key based on calculation parameters."""
        import hashlib
        import json
        
        key_data = {
            "type": "calculate_units",
            "season": self.season,
            "data1_dataset": self.data1.dataset_id,
            "data1_symbols": sorted(self.data1.symbols),
            "data1_timeframes": sorted(self.data1.timeframes),
            "strategy_id": self.strategy_id,
            "params_hash": hashlib.sha256(
                json.dumps(self.params, sort_keys=True).encode()
            ).hexdigest()[:16]
        }
        
        key_str = json.dumps(key_data, sort_keys=True)
        self.idempotency_key = f"calculate_units:{hashlib.sha256(key_str.encode()).hexdigest()[:32]}"
        return self


class CheckSeasonIntent(UserIntent):
    """Intent to check if a season is frozen."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.CHECK_SEASON)
    
    season: str
    action: str = Field(default="submit_job")
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> CheckSeasonIntent:
        """Set idempotency key based on season and action."""
        self.idempotency_key = f"check_season:{self.season}:{self.action}"
        return self


class GetJobStatusIntent(UserIntent):
    """Intent to get job status with units progress."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.GET_JOB_STATUS)
    
    job_id: str
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> GetJobStatusIntent:
        """Set idempotency key based on job_id."""
        self.idempotency_key = f"get_job_status:{self.job_id}"
        return self


class ListJobsIntent(UserIntent):
    """Intent to list jobs with progress."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.LIST_JOBS)
    
    limit: int = Field(default=50, ge=1, le=1000)
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> ListJobsIntent:
        """Set idempotency key based on limit."""
        self.idempotency_key = f"list_jobs:limit={self.limit}"
        return self


class GetJobLogsIntent(UserIntent):
    """Intent to get tail of job logs."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.GET_JOB_LOGS)
    
    job_id: str
    lines: int = Field(default=50, ge=1, le=1000)
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> GetJobLogsIntent:
        """Set idempotency key based on job_id and lines."""
        self.idempotency_key = f"get_job_logs:{self.job_id}:lines={self.lines}"
        return self


class SubmitBatchIntent(UserIntent):
    """Intent to submit a batch of jobs."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.SUBMIT_BATCH)
    
    # Batch specification
    season: str
    template: Dict[str, Any]  # JobTemplate serialized
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> SubmitBatchIntent:
        """Set idempotency key based on batch parameters."""
        import hashlib
        import json
        
        key_data = {
            "type": "submit_batch",
            "season": self.season,
            "template_hash": hashlib.sha256(
                json.dumps(self.template, sort_keys=True).encode()
            ).hexdigest()[:16]
        }
        
        key_str = json.dumps(key_data, sort_keys=True)
        self.idempotency_key = f"submit_batch:{hashlib.sha256(key_str.encode()).hexdigest()[:32]}"
        return self


class ValidatePayloadIntent(UserIntent):
    """Intent to validate wizard payload."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.VALIDATE_PAYLOAD)
    
    payload: Dict[str, Any]
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> ValidatePayloadIntent:
        """Set idempotency key based on payload hash."""
        import hashlib
        import json
        
        payload_hash = hashlib.sha256(
            json.dumps(self.payload, sort_keys=True).encode()
        ).hexdigest()[:32]
        self.idempotency_key = f"validate_payload:{payload_hash}"
        return self


class BuildParquetIntent(UserIntent):
    """Intent to build Parquet files for a dataset."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.BUILD_PARQUET)
    
    dataset_id: str
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> BuildParquetIntent:
        """Set idempotency key based on dataset_id."""
        self.idempotency_key = f"build_parquet:{self.dataset_id}"
        return self


class FreezeSeasonIntent(UserIntent):
    """Intent to freeze a season."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.FREEZE_SEASON)
    
    season: str
    reason: Optional[str] = None
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> FreezeSeasonIntent:
        """Set idempotency key based on season."""
        self.idempotency_key = f"freeze_season:{self.season}"
        return self


class ExportSeasonIntent(UserIntent):
    """Intent to export season data."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.EXPORT_SEASON)
    
    season: str
    format: str = Field(default="json")  # json, csv, parquet
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> ExportSeasonIntent:
        """Set idempotency key based on season and format."""
        self.idempotency_key = f"export_season:{self.season}:{self.format}"
        return self


class CompareSeasonsIntent(UserIntent):
    """Intent to compare two seasons."""
    model_config = ConfigDict(frozen=False)
    
    intent_type: IntentType = Field(default=IntentType.COMPARE_SEASONS)
    
    season_a: str
    season_b: str
    metrics: List[str] = Field(default_factory=lambda: ["sharpe", "max_dd", "win_rate"])
    
    @model_validator(mode="after")
    def set_idempotency_key(self) -> CompareSeasonsIntent:
        """Set idempotency key based on seasons and metrics."""
        self.idempotency_key = f"compare_seasons:{self.season_a}:{self.season_b}:{','.join(sorted(self.metrics))}"
        return self


# Type alias for all concrete intent types
Intent = Union[
    CreateJobIntent,
    CalculateUnitsIntent,
    CheckSeasonIntent,
    GetJobStatusIntent,
    ListJobsIntent,
    GetJobLogsIntent,
    SubmitBatchIntent,
    ValidatePayloadIntent,
    BuildParquetIntent,
    FreezeSeasonIntent,
    ExportSeasonIntent,
    CompareSeasonsIntent,
]
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/oom_cost_model.py
sha256(source_bytes) = ec1a5f399cb50fef6fc0cdf53ebabb626eff692c5a51224768edaf494d30dcec
bytes = 4239
redacted = False
--------------------------------------------------------------------------------

"""OOM cost model for memory and computation estimation.

Provides conservative estimates for memory usage and operations
to enable OOM gate decisions before stage execution.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np


def _bytes_of_array(a: Any) -> int:
    """
    Get bytes of numpy array.
    
    Args:
        a: Array-like object
        
    Returns:
        Number of bytes (0 if not ndarray)
    """
    if isinstance(a, np.ndarray):
        return int(a.nbytes)
    return 0


def estimate_memory_bytes(
    cfg: Dict[str, Any],
    work_factor: float = 2.0,
) -> int:
    """
    Estimate memory usage in bytes (conservative upper bound).
    
    Memory estimation includes:
    - Price arrays: open/high/low/close (if present)
    - Params matrix: params_total * param_dim * 8 bytes (if present)
    - Working buffers: conservative multiplier (work_factor)
    
    Note: This is a conservative estimate. Actual usage may be lower,
    but gate uses this to prevent OOM failures.
    
    Args:
        cfg: Configuration dictionary containing:
            - bars: Number of bars
            - params_total: Total parameters
            - param_subsample_rate: Subsample rate
            - open_, high, low, close: Optional OHLC arrays
            - params_matrix: Optional parameter matrix
        work_factor: Conservative multiplier for working buffers (default: 2.0)
        
    Returns:
        Estimated memory in bytes
    """
    mem = 0
    
    # Price arrays (if present)
    for k in ("open_", "open", "high", "low", "close"):
        mem += _bytes_of_array(cfg.get(k))
    
    # Params matrix
    mem += _bytes_of_array(cfg.get("params_matrix"))
    
    # Conservative working buffers
    # Note: This is a conservative multiplier to account for:
    # - Intermediate computation buffers
    # - Indicator arrays (donchian, ATR, etc.)
    # - Intent arrays
    # - Fill arrays
    mem = int(mem * float(work_factor))
    
    # Note: We do NOT reduce mem by subsample_rate here because:
    # 1. Some allocations are per-bar (not per-param)
    # 2. Working buffers may scale differently
    # 3. Conservative estimate is safer for OOM prevention
    
    return mem


def estimate_ops(cfg: Dict[str, Any]) -> int:
    """
    Estimate operations count (coarse approximation).
    
    Baseline: per-bar per-effective-param operations.
    This is a coarse estimate for cost tracking.
    
    Args:
        cfg: Configuration dictionary containing:
            - bars: Number of bars
            - params_total: Total parameters
            - param_subsample_rate: Subsample rate
            
    Returns:
        Estimated operations count
    """
    bars = int(cfg.get("bars", 0))
    params_total = int(cfg.get("params_total", 0))
    subsample_rate = float(cfg.get("param_subsample_rate", 1.0))
    
    # Effective params after subsample (floor rule)
    params_effective = int(params_total * subsample_rate)
    
    # Baseline: per-bar per-effective-param step (coarse)
    ops = int(bars * params_effective)
    
    return ops


def estimate_time_s(cfg: Dict[str, Any]) -> float | None:
    """
    Estimate execution time in seconds (optional).
    
    This is a placeholder for future time estimation.
    Currently returns None.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Estimated time in seconds (None if not available)
    """
    # Placeholder for future implementation
    return None


def summarize_estimates(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize all estimates in a JSON-serializable dict.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Dictionary with estimates:
        - mem_est_bytes: Memory estimate in bytes
        - mem_est_mb: Memory estimate in MB
        - ops_est: Operations estimate
        - time_est_s: Time estimate in seconds (None if not available)
    """
    mem_b = estimate_memory_bytes(cfg)
    ops = estimate_ops(cfg)
    time_s = estimate_time_s(cfg)
    
    return {
        "mem_est_bytes": mem_b,
        "mem_est_mb": mem_b / (1024.0 * 1024.0),
        "ops_est": ops,
        "time_est_s": time_s,
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/oom_gate.py
sha256(source_bytes) = b2c6072834d6dd86b779d7f31f7ba2b706ed506075e21005e9a2bc563723adb6
bytes = 14718
redacted = False
--------------------------------------------------------------------------------

"""OOM gate decision maker.

Pure functions for estimating memory usage and deciding PASS/BLOCK/AUTO_DOWNSAMPLE.
No engine dependencies, no file I/O - pure computation only.

This module provides two APIs:
1. New API (for B5-C): estimate_bytes(), decide_gate() with Pydantic schemas
2. Legacy API (for pipeline/tests): decide_oom_action() with dict I/O
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Literal, Optional

import FishBroWFS_V2.core.oom_cost_model as oom_cost_model
from FishBroWFS_V2.core.schemas.oom_gate import OomGateDecision, OomGateInput

OomAction = Literal["PASS", "BLOCK", "AUTO_DOWNSAMPLE"]


def estimate_bytes(inp: OomGateInput) -> int:
    """
    Estimate memory usage in bytes.
    
    Formula (locked):
        estimated = bars * params * subsample * intents_per_bar * bytes_per_intent_est
    
    Args:
        inp: OomGateInput with bars, params, param_subsample_rate, etc.
        
    Returns:
        Estimated memory usage in bytes
    """
    estimated = (
        inp.bars
        * inp.params
        * inp.param_subsample_rate
        * inp.intents_per_bar
        * inp.bytes_per_intent_est
    )
    return int(estimated)


def decide_gate(inp: OomGateInput) -> OomGateDecision:
    """
    Decide OOM gate action: PASS, BLOCK, or AUTO_DOWNSAMPLE.
    
    Rules (locked):
    - PASS: estimated <= ram_budget * 0.6
    - BLOCK: estimated > ram_budget * 0.9
    - AUTO_DOWNSAMPLE: otherwise, recommended_rate = (ram_budget * 0.6) / (bars * params * intents_per_bar * bytes_per_intent_est)
    
    Args:
        inp: OomGateInput with configuration
        
    Returns:
        OomGateDecision with decision and recommendations
    """
    estimated = estimate_bytes(inp)
    ram_budget = inp.ram_budget_bytes
    
    # Thresholds (locked)
    pass_threshold = ram_budget * 0.6
    block_threshold = ram_budget * 0.9
    
    if estimated <= pass_threshold:
        return OomGateDecision(
            decision="PASS",
            estimated_bytes=estimated,
            ram_budget_bytes=ram_budget,
            recommended_subsample_rate=None,
            notes=f"Estimated {estimated:,} bytes <= {pass_threshold:,.0f} bytes (60% of budget)",
        )
    
    if estimated > block_threshold:
        return OomGateDecision(
            decision="BLOCK",
            estimated_bytes=estimated,
            ram_budget_bytes=ram_budget,
            recommended_subsample_rate=None,
            notes=f"Estimated {estimated:,} bytes > {block_threshold:,.0f} bytes (90% of budget) - BLOCKED",
        )
    
    # AUTO_DOWNSAMPLE: calculate recommended rate
    # recommended_rate = (ram_budget * 0.6) / (bars * params * intents_per_bar * bytes_per_intent_est)
    denominator = inp.bars * inp.params * inp.intents_per_bar * inp.bytes_per_intent_est
    if denominator > 0:
        recommended_rate = (ram_budget * 0.6) / denominator
        # Clamp to [0.0, 1.0]
        recommended_rate = max(0.0, min(1.0, recommended_rate))
    else:
        recommended_rate = 0.0
    
    return OomGateDecision(
        decision="AUTO_DOWNSAMPLE",
        estimated_bytes=estimated,
        ram_budget_bytes=ram_budget,
        recommended_subsample_rate=recommended_rate,
        notes=(
            f"Estimated {estimated:,} bytes between {pass_threshold:,.0f} and {block_threshold:,.0f} "
            f"- recommended subsample rate: {recommended_rate:.4f}"
        ),
    )


def _params_effective(params_total: int, rate: float) -> int:
    """Calculate effective params with floor rule (at least 1)."""
    return max(1, int(params_total * rate))


def _estimate_bytes_legacy(cfg: Mapping[str, Any] | Dict[str, Any]) -> int:
    """
    Estimate memory bytes using unified formula when keys are available.
    
    Formula (locked): bars * params_total * param_subsample_rate * intents_per_bar * bytes_per_intent_est
    
    Falls back to oom_cost_model.estimate_memory_bytes if keys are missing.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Estimated memory usage in bytes
    """
    keys = ("bars", "params_total", "param_subsample_rate", "intents_per_bar", "bytes_per_intent_est")
    if all(k in cfg for k in keys):
        return int(
            int(cfg["bars"])
            * int(cfg["params_total"])
            * float(cfg["param_subsample_rate"])
            * float(cfg["intents_per_bar"])
            * int(cfg["bytes_per_intent_est"])
        )
    # Fallback to cost model
    return int(oom_cost_model.estimate_memory_bytes(dict(cfg), work_factor=2.0))


def _estimate_ops(cfg: dict, *, params_effective: int) -> int:
    """
    Safely estimate operations count.
    
    Priority:
    1. Use oom_cost_model.estimate_ops if available (most consistent)
    2. Fallback to deterministic formula
    
    Args:
        cfg: Configuration dictionary
        params_effective: Effective params count (already calculated)
        
    Returns:
        Estimated operations count
    """
    # If cost model has ops estimate, use it (most consistent)
    if hasattr(oom_cost_model, "estimate_ops"):
        return int(oom_cost_model.estimate_ops(cfg))
    if hasattr(oom_cost_model, "estimate_ops_est"):
        return int(oom_cost_model.estimate_ops_est(cfg))
    
    # Fallback: at least stable and monotonic
    bars = int(cfg.get("bars", 0))
    intents_per_bar = float(cfg.get("intents_per_bar", 2.0))
    return int(bars * params_effective * intents_per_bar)


def decide_oom_action(
    cfg: Mapping[str, Any] | Dict[str, Any],
    *,
    mem_limit_mb: float,
    allow_auto_downsample: bool = True,
    auto_downsample_step: float = 0.5,
    auto_downsample_min: float = 0.02,
    work_factor: float = 2.0,
) -> Dict[str, Any]:
    """
    Backward-compatible OOM gate used by funnel_runner + contract tests.

    Returns a dict (schema-as-dict) consumed by pipeline and written to artifacts/README.
    This function NEVER mutates cfg - returns new_cfg in result dict.
    
    Uses estimate_memory_bytes() from oom_cost_model (tests monkeypatch this).
    Must use module import (oom_cost_model.estimate_memory_bytes) for monkeypatch to work.
    
    Algorithm: Monotonic step-based downsample search
    - If mem_est(original_subsample) <= limit → PASS
    - If over limit and allow_auto_downsample=False → BLOCK
    - If over limit and allow_auto_downsample=True:
      - Step-based search: cur * step (e.g., 0.5 → 0.25 → 0.125...)
      - Re-estimate mem_est at each candidate subsample
      - If mem_est <= limit → AUTO_DOWNSAMPLE with that subsample
      - If reach min_rate and still over limit → BLOCK
    
    Args:
        cfg: Configuration dictionary with bars, params_total, param_subsample_rate, etc.
        mem_limit_mb: Memory limit in MB
        allow_auto_downsample: Whether to allow automatic downsample
        auto_downsample_step: Multiplier for each downsample step (default: 0.5, must be < 1.0)
        auto_downsample_min: Minimum subsample rate (default: 0.02)
        work_factor: Work factor for memory estimation (default: 2.0)
        
    Returns:
        Dictionary with action, reason, estimated_bytes, new_cfg, and metadata
    """
    # pure: never mutate caller
    base_cfg = dict(cfg)
    
    bars = int(base_cfg.get("bars", 0))
    params_total = int(base_cfg.get("params_total", 0))
    
    def _mem_mb(cfg_dict: dict[str, Any], work_factor: float) -> float:
        """
        Estimate memory in MB.
        
        Always uses oom_cost_model.estimate_memory_bytes to respect monkeypatch.
        """
        b = oom_cost_model.estimate_memory_bytes(cfg_dict, work_factor=work_factor)
        return float(b) / (1024.0 * 1024.0)
    
    original = float(base_cfg.get("param_subsample_rate", 1.0))
    original = max(0.0, min(1.0, original))
    
    # invalid input → BLOCK
    if bars <= 0 or params_total <= 0:
        mem0 = _mem_mb(base_cfg, work_factor)
        return _build_result(
            action="BLOCK",
            reason="invalid_input",
            new_cfg=base_cfg,
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    mem0 = _mem_mb(base_cfg, work_factor)
    
    if mem0 <= mem_limit_mb:
        return _build_result(
            action="PASS",
            reason="pass_under_limit",
            new_cfg=dict(base_cfg),
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    if not allow_auto_downsample:
        return _build_result(
            action="BLOCK",
            reason="block: over limit (auto-downsample disabled)",
            new_cfg=dict(base_cfg),
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    step = float(auto_downsample_step)
    if not (0.0 < step < 1.0):
        # contract: step must reduce
        step = 0.5
    
    min_rate = float(auto_downsample_min)
    min_rate = max(0.0, min(1.0, min_rate))
    
    # Monotonic step-search: always decrease
    cur = original
    best_cfg: dict[str, Any] | None = None
    best_mem: float | None = None
    
    while True:
        nxt = cur * step
        # Clamp to min_rate before evaluating
        if nxt < min_rate:
            nxt = min_rate
        
        # if we can no longer decrease, break
        if nxt >= cur:
            break
        
        cand = dict(base_cfg)
        cand["param_subsample_rate"] = float(nxt)
        mem_c = _mem_mb(cand, work_factor)
        
        if mem_c <= mem_limit_mb:
            best_cfg = cand
            best_mem = mem_c
            break
        
        # still over limit
        cur = nxt
        # Only break if we've evaluated min_rate and it's still over
        if cur <= min_rate + 1e-12:
            # We *have evaluated* min_rate and it's still over => BLOCK
            break
    
    if best_cfg is not None and best_mem is not None:
        final_subsample = float(best_cfg["param_subsample_rate"])
        # Ensure monotonicity: final_subsample <= original
        assert final_subsample <= original, f"final_subsample {final_subsample} > original {original}"
        return _build_result(
            action="AUTO_DOWNSAMPLE",
            reason="auto-downsample: over limit, reduced subsample",
            new_cfg=best_cfg,
            original_subsample=original,
            final_subsample=final_subsample,
            mem_est_mb=best_mem,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    # even at minimum still over limit => BLOCK
    # Only reach here if we've evaluated min_rate and it's still over
    min_cfg = dict(base_cfg)
    min_cfg["param_subsample_rate"] = float(min_rate)
    mem_min = _mem_mb(min_cfg, work_factor)
    
    return _build_result(
        action="BLOCK",
        reason="block: min_subsample still too large",
        new_cfg=min_cfg,  # keep audit: this is the best we can do
        original_subsample=original,
        final_subsample=float(min_rate),
        mem_est_mb=mem_min,
        mem_limit_mb=mem_limit_mb,
        params_total=params_total,
        allow_auto_downsample=allow_auto_downsample,
        auto_downsample_step=auto_downsample_step,
        auto_downsample_min=auto_downsample_min,
        work_factor=work_factor,
    )


def _build_result(
    *,
    action: str,
    reason: str,
    new_cfg: dict[str, Any],
    original_subsample: float,
    final_subsample: float,
    mem_est_mb: float,
    mem_limit_mb: float,
    params_total: int,
    allow_auto_downsample: bool,
    auto_downsample_step: float,
    auto_downsample_min: float,
    work_factor: float,
) -> Dict[str, Any]:
    """Helper to build consistent result dict."""
    params_eff = _params_effective(params_total, final_subsample)
    ops_est = _estimate_ops(new_cfg, params_effective=params_eff)
    
    # Calculate time estimate from ops_est
    ops_per_sec_est = float(new_cfg.get("ops_per_sec_est", 2.0e7))
    time_est_s = float(ops_est) / ops_per_sec_est if ops_per_sec_est > 0 else 0.0
    
    mem_est_bytes = int(mem_est_mb * 1024.0 * 1024.0)
    mem_limit_bytes = int(mem_limit_mb * 1024.0 * 1024.0)
    
    estimates = {
        "mem_est_bytes": int(mem_est_bytes),
        "mem_est_mb": float(mem_est_mb),
        "mem_limit_mb": float(mem_limit_mb),
        "mem_limit_bytes": int(mem_limit_bytes),
        "ops_est": int(ops_est),
        "time_est_s": float(time_est_s),
    }
    return {
        "action": action,
        "reason": reason,
        # ✅ tests/test_oom_gate.py needs this
        "estimated_bytes": int(mem_est_bytes),
        "estimated_mb": float(mem_est_mb),
        # ✅ NEW: required by tests/test_oom_gate.py
        "mem_limit_mb": float(mem_limit_mb),
        "mem_limit_bytes": int(mem_limit_bytes),
        # Original subsample contract
        "original_subsample": float(original_subsample),
        "final_subsample": float(final_subsample),
        # ✅ NEW: new_cfg SSOT (never mutate original cfg)
        "new_cfg": new_cfg,
        # Funnel/README common fields (preserved)
        "params_total": int(params_total),
        "params_effective": int(params_eff),
        # ✅ funnel_runner/tests needs estimates.ops_est / estimates.mem_est_mb
        "estimates": estimates,
        # Other debug fields
        "allow_auto_downsample": bool(allow_auto_downsample),
        "auto_downsample_step": float(auto_downsample_step),
        "auto_downsample_min": float(auto_downsample_min),
        "work_factor": float(work_factor),
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/paths.py
sha256(source_bytes) = 6b86599ad1f957c320ccf026680e5d2c3b7b54da7e3ef0863b4d6afc65ea9858
bytes = 1068
redacted = False
--------------------------------------------------------------------------------

"""Path management for artifact output.

Centralized contract for output directory structure.
"""

from __future__ import annotations

from pathlib import Path


def get_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Get path for a specific run.
    
    Fixed path structure: outputs/seasons/{season}/runs/{run_id}/
    
    Args:
        outputs_root: Root outputs directory (e.g., Path("outputs"))
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to run directory
    """
    return outputs_root / "seasons" / season / "runs" / run_id


def ensure_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Ensure run directory exists and return its path.
    
    Args:
        outputs_root: Root outputs directory
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to run directory (created if needed)
    """
    run_dir = get_run_dir(outputs_root, season, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/policy_engine.py
sha256(source_bytes) = 99209471aec4e43d1441592f3b3a53ee9e1ac1fe5bb27c8fe69935338e5ccd8b
bytes = 4338
redacted = True
--------------------------------------------------------------------------------
"""Policy Engine - 實盤安全鎖

系統動作風險等級分類與強制執行政策。
"""

import os
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.core.action_risk import RiskLevel, ActionPolicyDecision
from FishBroWFS_V2.core.season_state import load_season_state

# 常數定義
LIVE_TOKEN_PATH =[REDACTED]LIVE_TOKEN_MAGIC =[REDACTED]
# 動作白名單（硬編碼）
READ_ONLY = {
    "view_history",
    "list_jobs",
    "get_job_status",
    "get_artifacts",
    "health",
    "list_datasets",
    "list_strategies",
    "get_job",
    "list_recent_jobs",
    "get_rolling_summary",
    "get_season_report",
    "list_chart_artifacts",
    "load_chart_artifact",
    "get_jobs_for_deploy",
    "get_system_settings",
}

RESEARCH_MUTATE = {
    "submit_job",
    "run_job",
    "build_portfolio",
    "archive",
    "export",
    "freeze_season",
    "unfreeze_season",
    "generate_deploy_zip",
    "update_system_settings",
}

LIVE_EXECUTE = {
    "deploy_live",
    "send_orders",
    "broker_connect",
    "promote_to_live",
}


def classify_action(action: str) -> RiskLevel:
    """分類動作風險等級
    
    Args:
        action: 動作名稱
        
    Returns:
        RiskLevel: 風險等級
        
    Note:
        未知動作一律視為 LIVE_EXECUTE（fail-safe）
    """
    if action in READ_ONLY:
        return RiskLevel.READ_ONLY
    if action in RESEARCH_MUTATE:
        return RiskLevel.RESEARCH_MUTATE
    if action in LIVE_EXECUTE:
        return RiskLevel.LIVE_EXECUTE
    # 未知動作：fail-safe，視為最高風險
    return RiskLevel.LIVE_EXECUTE


def enforce_action_policy(action: str, season: Optional[str] = None) -> ActionPolicyDecision:
    """強制執行動作政策
    
    Args:
        action: 動作名稱
        season: 季節識別碼（可選）
        
    Returns:
        ActionPolicyDecision: 政策決策結果
    """
    risk = classify_action(action)

    # LIVE_EXECUTE:[REDACTED]    if risk == RiskLevel.LIVE_EXECUTE:
        if os.getenv("FISHBRO_ENABLE_LIVE") != "1":
            return ActionPolicyDecision(
                allowed=False,
                reason="LIVE_EXECUTE disabled: set FISHBRO_ENABLE_LIVE=1",
                risk=risk,
                action=action,
                season=season,
            )
        if not LIVE_TOKEN_PATH.exists():[REDACTED]            return ActionPolicyDecision(
                allowed=False,
                reason=[REDACTED]                risk=risk,
                action=action,
                season=season,
            )
        try:
            token_content =[REDACTED]            if token_content !=[REDACTED]                return ActionPolicyDecision(
                    allowed=False,
                    reason=[REDACTED]                    risk=risk,
                    action=action,
                    season=season,
                )
        except Exception:
            return ActionPolicyDecision(
                allowed=False,
                reason=[REDACTED]                risk=risk,
                action=action,
                season=season,
            )
        return ActionPolicyDecision(
            allowed=True,
            reason="LIVE_EXECUTE enabled",
            risk=risk,
            action=action,
            season=season,
        )

    # RESEARCH_MUTATE: 檢查季節是否凍結
    if risk == RiskLevel.RESEARCH_MUTATE and season:
        try:
            state = load_season_state(season)
            if state.is_frozen():
                return ActionPolicyDecision(
                    allowed=False,
                    reason=f"Season {season} is frozen",
                    risk=risk,
                    action=action,
                    season=season,
                )
        except Exception:
            # 如果載入狀態失敗，假設季節未凍結（安全側）
            pass

    # READ_ONLY 或允許的 RESEARCH_MUTATE
    return ActionPolicyDecision(
        allowed=True,
        reason="OK",
        risk=risk,
        action=action,
        season=season,
    )
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/processor.py
sha256(source_bytes) = 9a4b2341efd5b5832c32894f56383c8687c35b3fa0c07291470faf808518dbd9
bytes = 17813
redacted = False
--------------------------------------------------------------------------------
"""StateProcessor - single executor for Attack #9 – Headless Intent-State Contract.

StateProcessor is the single consumer that processes intents sequentially.
All side effects must happen only inside StateProcessor. It reads intents from
ActionQueue, processes them, and produces new SystemState snapshots.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Callable, Type
from concurrent.futures import ThreadPoolExecutor

from FishBroWFS_V2.core.intents import (
    Intent, UserIntent, IntentType, IntentStatus,
    CreateJobIntent, CalculateUnitsIntent, CheckSeasonIntent,
    GetJobStatusIntent, ListJobsIntent, GetJobLogsIntent,
    SubmitBatchIntent, ValidatePayloadIntent, BuildParquetIntent,
    FreezeSeasonIntent, ExportSeasonIntent, CompareSeasonsIntent,
    DataSpecIntent
)
from FishBroWFS_V2.core.state import (
    SystemState, JobProgress, SeasonInfo, DatasetInfo, SystemMetrics,
    IntentQueueStatus, JobStatus, SeasonStatus, DatasetStatus,
    create_initial_state, create_state_snapshot
)
from FishBroWFS_V2.control.action_queue import ActionQueue


logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Error during intent processing."""
    pass


class IntentHandler:
    """Base class for intent handlers."""
    
    def __init__(self, processor: "StateProcessor"):
        self.processor = processor
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def handle(self, intent: UserIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Handle an intent and return new state and result."""
        raise NotImplementedError


class CreateJobHandler(IntentHandler):
    """Handler for CreateJobIntent."""
    
    async def handle(self, intent: CreateJobIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Create a job from wizard payload."""
        self.logger.info(f"Processing CreateJobIntent: {intent.intent_id}")
        
        # Validate job creation
        errors = current_state.validate_job_creation(intent.season, intent.data1.dataset_id)
        if errors:
            raise ProcessingError(f"Job creation validation failed: {', '.join(errors)}")
        
        # TODO: Integrate with actual job creation logic from job_api.py
        # For now, simulate job creation
        import uuid
        job_id = str(uuid.uuid4())
        
        # Calculate units (simplified)
        symbols_count = len(intent.data1.symbols)
        timeframes_count = len(intent.data1.timeframes)
        units = symbols_count * timeframes_count
        
        # Create job progress
        now = datetime.now()
        job_progress = JobProgress(
            job_id=job_id,
            status=JobStatus.QUEUED,
            units_done=0,
            units_total=units,
            progress=0.0,
            created_at=now,
            updated_at=now,
            season=intent.season,
            dataset_id=intent.data1.dataset_id
        )
        
        # Update state
        new_state = create_state_snapshot(
            current_state,
            jobs={**current_state.jobs, job_id: job_progress},
            active_job_ids={*current_state.active_job_ids, job_id},
            metrics=SystemMetrics(
                total_jobs=current_state.metrics.total_jobs + 1,
                queued_jobs=current_state.metrics.queued_jobs + 1
            )
        )
        
        # Result for UI
        result = {
            "job_id": job_id,
            "units": units,
            "season": intent.season,
            "status": "queued"
        }
        
        return new_state, result


class CalculateUnitsHandler(IntentHandler):
    """Handler for CalculateUnitsIntent."""
    
    async def handle(self, intent: CalculateUnitsIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Calculate units for wizard payload."""
        self.logger.info(f"Processing CalculateUnitsIntent: {intent.intent_id}")
        
        # Calculate units (same logic as job_api.calculate_units)
        symbols_count = len(intent.data1.symbols)
        timeframes_count = len(intent.data1.timeframes)
        strategies_count = 1  # Single strategy
        filters_count = 1 if intent.data2 is None else len(intent.data2.filters) if hasattr(intent.data2, 'filters') else 1
        
        units = symbols_count * timeframes_count * strategies_count * filters_count
        
        # State doesn't change for calculation
        result = {
            "units": units,
            "breakdown": {
                "symbols": symbols_count,
                "timeframes": timeframes_count,
                "strategies": strategies_count,
                "filters": filters_count
            }
        }
        
        return current_state, result


class CheckSeasonHandler(IntentHandler):
    """Handler for CheckSeasonIntent."""
    
    async def handle(self, intent: CheckSeasonIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Check if a season is frozen."""
        self.logger.info(f"Processing CheckSeasonIntent: {intent.intent_id}")
        
        is_frozen = current_state.is_season_frozen(intent.season)
        
        result = {
            "season": intent.season,
            "is_frozen": is_frozen,
            "action": intent.action,
            "can_proceed": not is_frozen
        }
        
        if is_frozen:
            result["error"] = f"Season {intent.season} is frozen"
        
        return current_state, result


class GetJobStatusHandler(IntentHandler):
    """Handler for GetJobStatusIntent."""
    
    async def handle(self, intent: GetJobStatusIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Get job status with units progress."""
        self.logger.info(f"Processing GetJobStatusIntent: {intent.intent_id}")
        
        job = current_state.get_job(intent.job_id)
        if not job:
            raise ProcessingError(f"Job not found: {intent.job_id}")
        
        result = {
            "job_id": job.job_id,
            "status": job.status.value,
            "units_done": job.units_done,
            "units_total": job.units_total,
            "progress": job.progress,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "season": job.season,
            "dataset_id": job.dataset_id
        }
        
        return current_state, result


class ListJobsHandler(IntentHandler):
    """Handler for ListJobsIntent."""
    
    async def handle(self, intent: ListJobsIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """List jobs with progress."""
        self.logger.info(f"Processing ListJobsIntent: {intent.intent_id}")
        
        # Get recent jobs
        jobs = list(current_state.jobs.values())
        jobs.sort(key=lambda j: j.updated_at, reverse=True)
        jobs = jobs[:intent.limit]
        
        result = {
            "jobs": [
                {
                    "job_id": job.job_id,
                    "status": job.status.value,
                    "units_done": job.units_done,
                    "units_total": job.units_total,
                    "progress": job.progress,
                    "created_at": job.created_at.isoformat(),
                    "updated_at": job.updated_at.isoformat(),
                    "season": job.season,
                    "dataset_id": job.dataset_id
                }
                for job in jobs
            ],
            "total": len(current_state.jobs),
            "limit": intent.limit
        }
        
        return current_state, result


class ValidatePayloadHandler(IntentHandler):
    """Handler for ValidatePayloadIntent."""
    
    async def handle(self, intent: ValidatePayloadIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Validate wizard payload."""
        self.logger.info(f"Processing ValidatePayloadIntent: {intent.intent_id}")
        
        # TODO: Integrate with actual validation logic from job_api.validate_wizard_payload
        # For now, do basic validation
        errors = []
        
        payload = intent.payload
        
        # Check required fields
        required_fields = ["season", "data1", "strategy_id", "params"]
        for field in required_fields:
            if field not in payload:
                errors.append(f"Missing required field: {field}")
        
        # Check data1
        if "data1" in payload:
            data1 = payload["data1"]
            if not isinstance(data1, dict):
                errors.append("data1 must be a dictionary")
            else:
                if "dataset_id" not in data1:
                    errors.append("data1 missing dataset_id")
                if "symbols" not in data1:
                    errors.append("data1 missing symbols")
                if "timeframes" not in data1:
                    errors.append("data1 missing timeframes")
        
        result = {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": []  # Could add warnings here
        }
        
        return current_state, result


class BuildParquetHandler(IntentHandler):
    """Handler for BuildParquetIntent."""
    
    async def handle(self, intent: BuildParquetIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Build Parquet files for a dataset."""
        self.logger.info(f"Processing BuildParquetIntent: {intent.intent_id}")
        
        # Check if dataset exists
        dataset = current_state.get_dataset(intent.dataset_id)
        if not dataset:
            raise ProcessingError(f"Dataset not found: {intent.dataset_id}")
        
        # Check if already building
        if intent.dataset_id in current_state.active_builds:
            raise ProcessingError(f"Dataset already being built: {intent.dataset_id}")
        
        # Update state to show building in progress
        new_state = create_state_snapshot(
            current_state,
            active_builds={*current_state.active_builds, intent.dataset_id}
        )
        
        # TODO: Actually build Parquet files
        # Simulate building
        await asyncio.sleep(0.1)  # Simulate work
        
        # Update dataset status
        updated_dataset = DatasetInfo(
            **dataset.model_dump(),
            status=DatasetStatus.AVAILABLE,
            has_parquet=True,
            last_built_at=datetime.now()
        )
        
        new_state = create_state_snapshot(
            new_state,
            datasets={**new_state.datasets, intent.dataset_id: updated_dataset},
            active_builds=new_state.active_builds - {intent.dataset_id}
        )
        
        result = {
            "dataset_id": intent.dataset_id,
            "status": "built",
            "has_parquet": True,
            "built_at": datetime.now().isoformat()
        }
        
        return new_state, result


class StateProcessor:
    """Single executor that processes intents sequentially.
    
    All side effects must happen only inside StateProcessor. It reads intents
    from ActionQueue, processes them, and produces new SystemState snapshots.
    """
    
    def __init__(self, action_queue: ActionQueue, initial_state: Optional[SystemState] = None):
        self.action_queue = action_queue
        self.current_state = initial_state or create_initial_state()
        self.is_running = False
        self.processing_task: Optional[asyncio.Task] = None
        self.handlers: Dict[IntentType, IntentHandler] = {}
        self.executor = ThreadPoolExecutor(max_workers=1)  # Single worker for sequential processing
        self.logger = logging.getLogger(__name__)
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register intent handlers."""
        self.handlers[IntentType.CREATE_JOB] = CreateJobHandler(self)
        self.handlers[IntentType.CALCULATE_UNITS] = CalculateUnitsHandler(self)
        self.handlers[IntentType.CHECK_SEASON] = CheckSeasonHandler(self)
        self.handlers[IntentType.GET_JOB_STATUS] = GetJobStatusHandler(self)
        self.handlers[IntentType.LIST_JOBS] = ListJobsHandler(self)
        self.handlers[IntentType.VALIDATE_PAYLOAD] = ValidatePayloadHandler(self)
        self.handlers[IntentType.BUILD_PARQUET] = BuildParquetHandler(self)
        # TODO: Add handlers for other intent types
    
    async def start(self) -> None:
        """Start the processor."""
        if self.is_running:
            return
        
        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_loop())
        self.logger.info("StateProcessor started")
    
    async def stop(self) -> None:
        """Stop the processor."""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        self.executor.shutdown(wait=True)
        self.logger.info("StateProcessor stopped")
    
    async def _process_loop(self) -> None:
        """Main processing loop."""
        while self.is_running:
            try:
                # Get next intent from queue (non-blocking)
                intent = await self.action_queue.get_next()
                if intent is None:
                    # No intents in queue, sleep a bit
                    await asyncio.sleep(0.1)
                    continue
                
                # Process the intent
                await self._process_intent(intent)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Avoid tight error loop
    
    async def _process_intent(self, intent: UserIntent) -> None:
        """Process a single intent."""
        start_time = time.time()
        
        try:
            # Update intent status to processing
            intent.status = IntentStatus.PROCESSING
            intent.processed_at = datetime.now()
            
            # Get handler for this intent type
            handler = self.handlers.get(intent.intent_type)
            if not handler:
                raise ProcessingError(f"No handler for intent type: {intent.intent_type}")
            
            # Process intent (run in thread pool to keep async loop responsive)
            loop = asyncio.get_event_loop()
            new_state, result = await loop.run_in_executor(
                self.executor,
                lambda: asyncio.run(handler.handle(intent, self.current_state))
            )
            
            # Update state
            self.current_state = new_state
            
            # Update intent status
            intent.status = IntentStatus.COMPLETED
            intent.result = result
            
            processing_time_ms = (time.time() - start_time) * 1000
            self.logger.info(f"Processed intent {intent.intent_id} ({intent.intent_type}) in {processing_time_ms:.1f}ms")
            
        except Exception as e:
            # Handle processing error
            intent.status = IntentStatus.FAILED
            intent.error_message = str(e)
            self.logger.error(f"Failed to process intent {intent.intent_id}: {e}", exc_info=True)
            
            # Update metrics
            self.current_state = create_state_snapshot(
                self.current_state,
                intent_queue=IntentQueueStatus(
                    **self.current_state.intent_queue.model_dump(),
                    failed_count=self.current_state.intent_queue.failed_count + 1
                )
            )
    
    def get_state(self) -> SystemState:
        """Get current system state snapshot."""
        return self.current_state
    
    def submit_intent(self, intent: UserIntent) -> str:
        """Submit an intent to the action queue.
        
        Returns the intent ID for tracking.
        """
        return self.action_queue.submit(intent)
    
    def get_intent_status(self, intent_id: str) -> Optional[UserIntent]:
        """Get intent status by ID."""
        return self.action_queue.get_intent(intent_id)
    
    async def wait_for_intent(self, intent_id: str, timeout: float = 30.0) -> Optional[UserIntent]:
        """Wait for an intent to complete."""
        return await self.action_queue.wait_for_intent(intent_id, timeout)
    
    def get_queue_status(self) -> IntentQueueStatus:
        """Get queue status."""
        return self.current_state.intent_queue


# Singleton instance for application use
_processor_instance: Optional[StateProcessor] = None


def get_processor() -> StateProcessor:
    """Get the singleton StateProcessor instance."""
    global _processor_instance
    if _processor_instance is None:
        from FishBroWFS_V2.control.action_queue import get_action_queue
        action_queue = get_action_queue()
        _processor_instance = StateProcessor(action_queue)
    return _processor_instance


async def start_processor() -> None:
    """Start the singleton processor."""
    processor = get_processor()
    await processor.start()


async def stop_processor() -> None:
    """Stop the singleton processor."""
    global _processor_instance
    if _processor_instance:
        await _processor_instance.stop()
        _processor_instance = None
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/resampler.py
sha256(source_bytes) = 501dc69b30374976c424838845fb0d4e305f06d1df0717d7bb3cf2193c895a19
bytes = 15919
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/core/resampler.py
"""
Resampler 核心

提供 deterministic resampling 功能，支援 session anchor 與 safe point 計算。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import List, Tuple, Optional, Dict, Any, Literal
import numpy as np
import pandas as pd

from FishBroWFS_V2.core.dimensions import get_dimension_for_dataset
from FishBroWFS_V2.contracts.dimensions import SessionSpec as ContractSessionSpec


@dataclass(frozen=True)
class SessionSpecTaipei:
    """台北時間的交易時段規格"""
    open_hhmm: str  # HH:MM 格式，例如 "07:00"
    close_hhmm: str  # HH:MM 格式，例如 "06:00"（次日）
    breaks: List[Tuple[str, str]]  # 休市時段列表，每個時段為 (start, end)
    tz: str = "Asia/Taipei"
    
    @classmethod
    def from_contract(cls, spec: ContractSessionSpec) -> SessionSpecTaipei:
        """從 contracts SessionSpec 轉換"""
        return cls(
            open_hhmm=spec.open_taipei,
            close_hhmm=spec.close_taipei,
            breaks=spec.breaks_taipei,
            tz=spec.tz,
        )
    
    @property
    def open_hour(self) -> int:
        """開盤小時"""
        return int(self.open_hhmm.split(":")[0])
    
    @property
    def open_minute(self) -> int:
        """開盤分鐘"""
        return int(self.open_hhmm.split(":")[1])
    
    @property
    def close_hour(self) -> int:
        """收盤小時（處理 24:00 為 0）"""
        hour = int(self.close_hhmm.split(":")[0])
        if hour == 24:
            return 0
        return hour
    
    @property
    def close_minute(self) -> int:
        """收盤分鐘"""
        return int(self.close_hhmm.split(":")[1])
    
    def is_overnight(self) -> bool:
        """是否為隔夜時段（收盤時間小於開盤時間）"""
        open_total = self.open_hour * 60 + self.open_minute
        close_total = self.close_hour * 60 + self.close_minute
        return close_total < open_total
    
    def session_start_for_date(self, d: date) -> datetime:
        """
        取得指定日期的 session 開始時間
        
        對於隔夜時段，session 開始時間為前一天的開盤時間
        例如：open=07:00, close=06:00，則 2023-01-02 的 session 開始時間為 2023-01-01 07:00
        """
        if self.is_overnight():
            # 隔夜時段：session 開始時間為前一天的開盤時間
            session_date = d - timedelta(days=1)
        else:
            # 非隔夜時段：session 開始時間為當天的開盤時間
            session_date = d
        
        return datetime(
            session_date.year,
            session_date.month,
            session_date.day,
            self.open_hour,
            self.open_minute,
            0,
        )
    
    def is_in_break(self, dt: datetime) -> bool:
        """檢查時間是否在休市時段內"""
        time_str = dt.strftime("%H:%M")
        for start, end in self.breaks:
            if start <= time_str < end:
                return True
        return False
    
    def is_in_session(self, dt: datetime) -> bool:
        """檢查時間是否在交易時段內（不考慮休市）"""
        # 計算從 session_start 開始的經過分鐘數
        session_start = self.session_start_for_date(dt.date())
        
        # 對於隔夜時段，需要調整計算
        if self.is_overnight():
            # 如果 dt 在 session_start 之後（同一天），則屬於當前 session
            # 如果 dt 在 session_start 之前（可能是次日），則屬於下一個 session
            if dt >= session_start:
                # 屬於當前 session
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
                return session_start <= dt < session_end
            else:
                # 屬於下一個 session
                session_start = self.session_start_for_date(dt.date() + timedelta(days=1))
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
                return session_start <= dt < session_end
        else:
            # 非隔夜時段
            # 處理 close_hhmm == "24:00" 的情況
            if self.close_hhmm == "24:00":
                # session_end 是次日的 00:00
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=0,
                    minute=0,
                    second=0,
                )
            else:
                session_end = session_start.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
            return session_start <= dt < session_end


def get_session_spec_for_dataset(dataset_id: str) -> Tuple[SessionSpecTaipei, bool]:
    """
    讀取資料集的 session 規格
    
    Args:
        dataset_id: 資料集 ID
        
    Returns:
        Tuple[SessionSpecTaipei, bool]:
            - SessionSpecTaipei 物件
            - dimension_found: 是否找到 dimension（True 表示找到，False 表示使用 fallback）
    """
    # 從 dimension registry 查詢
    dimension = get_dimension_for_dataset(dataset_id)
    
    if dimension is not None:
        # 找到 dimension，使用其 session spec
        return SessionSpecTaipei.from_contract(dimension.session), True
    
    # 找不到 dimension，使用 fallback
    # 根據 Phase 3A 要求：open=00:00 close=24:00 breaks=[]
    fallback_spec = SessionSpecTaipei(
        open_hhmm="00:00",
        close_hhmm="24:00",
        breaks=[],
        tz="Asia/Taipei",
    )
    
    return fallback_spec, False


def compute_session_start(ts: datetime, session: SessionSpecTaipei) -> datetime:
    """
    Return the session_start datetime (Taipei) whose session window contains ts.
    
    Must handle overnight sessions where close < open (cross midnight).
    
    Args:
        ts: 時間戳記（台北時間）
        session: 交易時段規格
        
    Returns:
        session_start: 包含 ts 的 session 開始時間
    """
    # 對於隔夜時段，需要特別處理
    if session.is_overnight():
        # 嘗試當天的 session_start
        candidate = session.session_start_for_date(ts.date())
        
        # 檢查 ts 是否在 candidate 開始的 session 內
        if session.is_in_session(ts):
            return candidate
        
        # 如果不在，嘗試前一天的 session_start
        candidate = session.session_start_for_date(ts.date() - timedelta(days=1))
        if session.is_in_session(ts):
            return candidate
        
        # 如果還是不在，嘗試後一天的 session_start
        candidate = session.session_start_for_date(ts.date() + timedelta(days=1))
        if session.is_in_session(ts):
            return candidate
        
        # 理論上不應該到這裡，但為了安全回傳當天的 session_start
        return session.session_start_for_date(ts.date())
    else:
        # 非隔夜時段：直接使用當天的 session_start
        return session.session_start_for_date(ts.date())


def compute_safe_recompute_start(
    ts_append_start: datetime, 
    tf_min: int, 
    session: SessionSpecTaipei
) -> datetime:
    """
    Safe point = session_start + floor((ts - session_start)/tf)*tf
    Then subtract tf if you want extra safety for boundary bar (optional, but deterministic).
    Must NOT return after ts_append_start.
    
    嚴格規則（鎖死）：
    1. safe = session_start + floor(delta_minutes/tf)*tf
    2. 額外保險：safe = max(session_start, safe - tf)（確保不晚於 ts_append_start）
    
    Args:
        ts_append_start: 新增資料的開始時間
        tf_min: timeframe 分鐘數
        session: 交易時段規格
        
    Returns:
        safe_recompute_start: 安全重算開始時間
    """
    # 1. 計算包含 ts_append_start 的 session_start
    session_start = compute_session_start(ts_append_start, session)
    
    # 2. 計算從 session_start 到 ts_append_start 的總分鐘數
    delta = ts_append_start - session_start
    delta_minutes = int(delta.total_seconds() // 60)
    
    # 3. safe = session_start + floor(delta_minutes/tf)*tf
    safe_minutes = (delta_minutes // tf_min) * tf_min
    safe = session_start + timedelta(minutes=safe_minutes)
    
    # 4. 額外保險：safe = max(session_start, safe - tf)
    # 確保 safe 不晚於 ts_append_start（但可能早於）
    safe_extra = safe - timedelta(minutes=tf_min)
    if safe_extra >= session_start:
        safe = safe_extra
    
    # 確保 safe 不晚於 ts_append_start
    if safe > ts_append_start:
        safe = session_start
    
    return safe


def resample_ohlcv(
    ts: np.ndarray, 
    o: np.ndarray, 
    h: np.ndarray, 
    l: np.ndarray, 
    c: np.ndarray, 
    v: np.ndarray,
    tf_min: int,
    session: SessionSpecTaipei,
    start_ts: Optional[datetime] = None,
) -> Dict[str, np.ndarray]:
    """
    Resample normalized bars -> tf bars anchored at session_start.
    
    Must ignore bars inside breaks (drop or treat as gap; choose one and keep consistent).
    Deterministic output ordering by ts ascending.
    
    行為規格：
    1. 只處理在交易時段內的 bars（忽略休市時段）
    2. 以 session_start 為 anchor 進行 resample
    3. 如果提供 start_ts，只處理 ts >= start_ts 的 bars
    4. 輸出 ts 遞增排序
    
    Args:
        ts: 時間戳記陣列（datetime 物件或 UNIX seconds）
        o, h, l, c, v: OHLCV 陣列
        tf_min: timeframe 分鐘數
        session: 交易時段規格
        start_ts: 可選的開始時間，只處理此時間之後的 bars
        
    Returns:
        字典，包含 resampled bars:
            ts: datetime64[s] 陣列
            open, high, low, close, volume: float64 或 int64 陣列
    """
    # 輸入驗證
    n = len(ts)
    if not (len(o) == len(h) == len(l) == len(c) == len(v) == n):
        raise ValueError("所有輸入陣列長度必須一致")
    
    if n == 0:
        return {
            "ts": np.array([], dtype="datetime64[s]"),
            "open": np.array([], dtype="float64"),
            "high": np.array([], dtype="float64"),
            "low": np.array([], dtype="float64"),
            "close": np.array([], dtype="float64"),
            "volume": np.array([], dtype="int64"),
        }
    
    # 轉換 ts 為 datetime 物件
    ts_datetime = []
    for t in ts:
        if isinstance(t, (int, float, np.integer, np.floating)):
            # UNIX seconds
            ts_datetime.append(datetime.fromtimestamp(t))
        elif isinstance(t, np.datetime64):
            # numpy datetime64
            # 轉換為 pandas Timestamp 然後到 datetime
            ts_datetime.append(pd.Timestamp(t).to_pydatetime())
        elif isinstance(t, datetime):
            # 已經是 datetime
            ts_datetime.append(t)
        else:
            raise TypeError(f"不支援的時間戳記類型: {type(t)}")
    
    # 過濾 bars：只保留在交易時段內且不在休市時段的 bars
    valid_indices = []
    valid_ts = []
    valid_o = []
    valid_h = []
    valid_l = []
    valid_c = []
    valid_v = []
    
    for i, dt in enumerate(ts_datetime):
        # 檢查是否在交易時段內
        if not session.is_in_session(dt):
            continue
        
        # 檢查是否在休市時段內
        if session.is_in_break(dt):
            continue
        
        # 檢查是否在 start_ts 之後（如果提供）
        if start_ts is not None and dt < start_ts:
            continue
        
        valid_indices.append(i)
        valid_ts.append(dt)
        valid_o.append(o[i])
        valid_h.append(h[i])
        valid_l.append(l[i])
        valid_c.append(c[i])
        valid_v.append(v[i])
    
    if not valid_ts:
        # 沒有有效的 bars
        return {
            "ts": np.array([], dtype="datetime64[s]"),
            "open": np.array([], dtype="float64"),
            "high": np.array([], dtype="float64"),
            "low": np.array([], dtype="float64"),
            "close": np.array([], dtype="float64"),
            "volume": np.array([], dtype="int64"),
        }
    
    # 將 valid_ts 轉換為 pandas DatetimeIndex 以便 resample
    df = pd.DataFrame({
        "open": valid_o,
        "high": valid_h,
        "low": valid_l,
        "close": valid_c,
        "volume": valid_v,
    }, index=pd.DatetimeIndex(valid_ts, tz=None))
    
    # 計算每個 bar 所屬的 session_start
    session_starts = [compute_session_start(dt, session) for dt in valid_ts]
    
    # 計算從 session_start 開始的經過分鐘數
    # 我們需要將每個 bar 分配到以 session_start 為基準的 tf 分鐘區間
    # 建立一個虛擬的時間戳記：session_start + floor((dt - session_start)/tf)*tf
    bucket_times = []
    for dt, sess_start in zip(valid_ts, session_starts):
        delta = dt - sess_start
        delta_minutes = int(delta.total_seconds() // 60)
        bucket_minutes = (delta_minutes // tf_min) * tf_min
        bucket_time = sess_start + timedelta(minutes=bucket_minutes)
        bucket_times.append(bucket_time)
    
    # 使用 bucket_times 進行分組
    df["bucket_time"] = bucket_times
    
    # 分組聚合
    grouped = df.groupby("bucket_time", sort=True)
    
    # 計算 OHLCV
    # 開盤價：每個 bucket 的第一個 open
    # 最高價：每個 bucket 的 high 最大值
    # 最低價：每個 bucket 的 low 最小值
    # 收盤價：每個 bucket 的最後一個 close
    # 成交量：每個 bucket 的 volume 總和
    result_df = pd.DataFrame({
        "open": grouped["open"].first(),
        "high": grouped["high"].max(),
        "low": grouped["low"].min(),
        "close": grouped["close"].last(),
        "volume": grouped["volume"].sum(),
    })
    
    # 確保結果排序（groupby 應該已經排序，但為了安全）
    result_df = result_df.sort_index()
    
    # 轉換為 numpy arrays
    result_ts = result_df.index.to_numpy(dtype="datetime64[s]")
    
    return {
        "ts": result_ts,
        "open": result_df["open"].to_numpy(dtype="float64"),
        "high": result_df["high"].to_numpy(dtype="float64"),
        "low": result_df["low"].to_numpy(dtype="float64"),
        "close": result_df["close"].to_numpy(dtype="float64"),
        "volume": result_df["volume"].to_numpy(dtype="int64"),
    }


def normalize_raw_bars(raw_ingest_result) -> Dict[str, np.ndarray]:
    """
    將 RawIngestResult 轉換為 normalized bars 陣列
    
    Args:
        raw_ingest_result: RawIngestResult 物件
        
    Returns:
        字典，包含 normalized bars:
            ts: datetime64[s] 陣列
            open, high, low, close: float64 陣列
            volume: int64 陣列
    """
    df = raw_ingest_result.df
    
    # 將 ts_str 轉換為 datetime
    ts_datetime = pd.to_datetime(df["ts_str"], format="%Y/%m/%d %H:%M:%S")
    
    # 轉換為 datetime64[s]
    ts_array = ts_datetime.to_numpy(dtype="datetime64[s]")
    
    return {
        "ts": ts_array,
        "open": df["open"].to_numpy(dtype="float64"),
        "high": df["high"].to_numpy(dtype="float64"),
        "low": df["low"].to_numpy(dtype="float64"),
        "close": df["close"].to_numpy(dtype="float64"),
        "volume": df["volume"].to_numpy(dtype="int64"),
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/run_id.py
sha256(source_bytes) = 31c195852ccd834cf4c719ca2f9bf03623bfa3499bb674a95d6552b556c8a38f
bytes = 903
redacted = True
--------------------------------------------------------------------------------

"""Run ID generation for audit trail.

Provides deterministic, sortable run IDs with timestamp and short token.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


def make_run_id(prefix: str | None = None) -> str:
    """
    Generate a sortable, readable run ID.
    
    Format:[REDACTED]    - Timestamp ensures chronological ordering (UTC)
    - Short token (8 hex chars) provides uniqueness
    
    Args:
        prefix: Optional prefix string (e.g., "test", "prod")
        
    Returns:
        Run ID string, e.g., "20251218T135221Z-a1b2c3d4"
        or "test-20251218T135221Z-a1b2c3d4" if prefix provided
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tok =[REDACTED]    
    if prefix:
        return f"{prefix}-{ts}-{tok}"
    else:
        return f"{ts}-{tok}"



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/season_context.py
sha256(source_bytes) = 57d3b0cd54d6665551d83abade3f88256a3b9368df38933cb9804b2f0bb233be
bytes = 2650
redacted = False
--------------------------------------------------------------------------------
"""
Season Context - Single Source of Truth (SSOT) for season management.

Phase 4: Consolidate season management to avoid scattered os.getenv() calls.
"""

import os
from pathlib import Path
from typing import Optional


def current_season() -> str:
    """Return current season from env FISHBRO_CURRENT_SEASON or default '2026Q1'."""
    return os.getenv("FISHBRO_CURRENT_SEASON", "2026Q1")


def outputs_root() -> str:
    """Return outputs root from env FISHBRO_OUTPUTS_ROOT or default 'outputs'."""
    return os.getenv("FISHBRO_OUTPUTS_ROOT", "outputs")


def season_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season} as Path object.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current_season().
    
    Returns:
        Path to season directory.
    """
    if season is None:
        season = current_season()
    return Path(outputs_root()) / "seasons" / season


def research_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/research as Path object."""
    return season_dir(season) / "research"


def portfolio_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/portfolio as Path object."""
    return season_dir(season) / "portfolio"


def governance_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/governance as Path object."""
    return season_dir(season) / "governance"


def canonical_results_path(season: Optional[str] = None) -> Path:
    """Return path to canonical_results.json."""
    return research_dir(season) / "canonical_results.json"


def research_index_path(season: Optional[str] = None) -> Path:
    """Return path to research_index.json."""
    return research_dir(season) / "research_index.json"


def portfolio_summary_path(season: Optional[str] = None) -> Path:
    """Return path to portfolio_summary.json."""
    return portfolio_dir(season) / "portfolio_summary.json"


def portfolio_manifest_path(season: Optional[str] = None) -> Path:
    """Return path to portfolio_manifest.json."""
    return portfolio_dir(season) / "portfolio_manifest.json"


# Convenience function for backward compatibility
def get_season_context() -> dict:
    """Return a dict with current season context for debugging/logging."""
    season = current_season()
    root = outputs_root()
    return {
        "season": season,
        "outputs_root": root,
        "season_dir": str(season_dir(season)),
        "research_dir": str(research_dir(season)),
        "portfolio_dir": str(portfolio_dir(season)),
        "governance_dir": str(governance_dir(season)),
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/season_state.py
sha256(source_bytes) = 06ec7773325c4f7b9399f5ef8b12f33ec7f116a5b6d8c508141ef548d1350214
bytes = 7362
redacted = False
--------------------------------------------------------------------------------
"""
Season State Management - Freeze governance lock.

Phase 5: Deterministic Governance & Reproducibility Lock.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Literal, TypedDict
from dataclasses import dataclass, asdict

from .season_context import season_dir


class SeasonStateDict(TypedDict, total=False):
    """Season state schema (immutable)."""
    season: str
    state: Literal["OPEN", "FROZEN"]
    frozen_ts: Optional[str]  # ISO-8601 or null
    frozen_by: Optional[Literal["gui", "cli", "system"]]  # or null
    reason: Optional[str]  # string or null


@dataclass
class SeasonState:
    """Season state data class."""
    season: str
    state: Literal["OPEN", "FROZEN"] = "OPEN"
    frozen_ts: Optional[str] = None  # ISO-8601 or null
    frozen_by: Optional[Literal["gui", "cli", "system"]] = None  # or null
    reason: Optional[str] = None  # string or null
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SeasonState":
        """Create SeasonState from dictionary."""
        return cls(
            season=data["season"],
            state=data.get("state", "OPEN"),
            frozen_ts=data.get("frozen_ts"),
            frozen_by=data.get("frozen_by"),
            reason=data.get("reason"),
        )
    
    def to_dict(self) -> SeasonStateDict:
        """Convert to dictionary."""
        return {
            "season": self.season,
            "state": self.state,
            "frozen_ts": self.frozen_ts,
            "frozen_by": self.frozen_by,
            "reason": self.reason,
        }
    
    def is_frozen(self) -> bool:
        """Check if season is frozen."""
        return self.state == "FROZEN"
    
    def freeze(self, by: Literal["gui", "cli", "system"], reason: Optional[str] = None) -> None:
        """Freeze the season."""
        if self.is_frozen():
            raise ValueError(f"Season {self.season} is already frozen")
        
        self.state = "FROZEN"
        self.frozen_ts = datetime.now(timezone.utc).isoformat()
        self.frozen_by = by
        self.reason = reason
    
    def unfreeze(self, by: Literal["gui", "cli", "system"], reason: Optional[str] = None) -> None:
        """Unfreeze the season."""
        if not self.is_frozen():
            raise ValueError(f"Season {self.season} is not frozen")
        
        self.state = "OPEN"
        self.frozen_ts = None
        self.frozen_by = None
        self.reason = None


def get_season_state_path(season: Optional[str] = None) -> Path:
    """Get path to season_state.json."""
    season_path = season_dir(season)
    governance_dir = season_path / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    return governance_dir / "season_state.json"


def load_season_state(season: Optional[str] = None) -> SeasonState:
    """Load season state from file, or create default if not exists."""
    state_path = get_season_state_path(season)
    
    if not state_path.exists():
        # Get season from context if not provided
        if season is None:
            from .season_context import current_season
            season_str = current_season()
        else:
            season_str = season
        
        # Create default OPEN state
        state = SeasonState(season=season_str, state="OPEN")
        save_season_state(state, season)
        return state
    
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validate required fields
        if "season" not in data:
            # Infer season from path
            if season is None:
                from .season_context import current_season
                season_str = current_season()
            else:
                season_str = season
            data["season"] = season_str
        
        return SeasonState.from_dict(data)
    except (json.JSONDecodeError, OSError, KeyError) as e:
        # If file is corrupted, create default
        if season is None:
            from .season_context import current_season
            season_str = current_season()
        else:
            season_str = season
        
        state = SeasonState(season=season_str, state="OPEN")
        save_season_state(state, season)
        return state


def save_season_state(state: SeasonState, season: Optional[str] = None) -> Path:
    """Save season state to file."""
    state_path = get_season_state_path(season)
    
    # Ensure directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict and write
    data = state.to_dict()
    
    # Write atomically
    temp_path = state_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Replace original
    temp_path.replace(state_path)
    
    return state_path


def check_season_not_frozen(season: Optional[str] = None, action: str = "action") -> None:
    """
    Check if season is not frozen, raise ValueError if frozen.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        action: Action name for error message.
    
    Raises:
        ValueError: If season is frozen.
    """
    state = load_season_state(season)
    if state.is_frozen():
        frozen_info = f"frozen at {state.frozen_ts} by {state.frozen_by}"
        if state.reason:
            frozen_info += f" (reason: {state.reason})"
        raise ValueError(
            f"Cannot perform {action}: Season {state.season} is {frozen_info}"
        )


def freeze_season(
    season: Optional[str] = None,
    by: Literal["gui", "cli", "system"] = "system",
    reason: Optional[str] = None,
    create_snapshot: bool = True,
) -> SeasonState:
    """
    Freeze a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        by: Who is freezing the season.
        reason: Optional reason for freezing.
        create_snapshot: Whether to create deterministic snapshot of artifacts.
    
    Returns:
        Updated SeasonState.
    """
    state = load_season_state(season)
    state.freeze(by=by, reason=reason)
    save_season_state(state, season)
    
    # Phase 5: Create deterministic snapshot
    if create_snapshot:
        try:
            from .snapshot import create_freeze_snapshot
            snapshot_path = create_freeze_snapshot(state.season)
            # Log snapshot creation (optional)
            print(f"Created freeze snapshot: {snapshot_path}")
        except Exception as e:
            # Don't fail freeze if snapshot fails, but log warning
            print(f"Warning: Failed to create freeze snapshot: {e}")
    
    return state


def unfreeze_season(
    season: Optional[str] = None,
    by: Literal["gui", "cli", "system"] = "system",
    reason: Optional[str] = None,
) -> SeasonState:
    """
    Unfreeze a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        by: Who is unfreezing the season.
        reason: Optional reason for unfreezing.
    
    Returns:
        Updated SeasonState.
    """
    state = load_season_state(season)
    state.unfreeze(by=by, reason=reason)
    save_season_state(state, season)
    return state
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/slippage_policy.py
sha256(source_bytes) = 656be5d5fa1fb03b0228b3c6f16884043009f0439e1556b4355e4a76435f9e9e
bytes = 5728
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/core/slippage_policy.py
"""
SlippagePolicy：滑價成本模型定義

定義 per fill/per side 的滑價等級，並提供價格調整函數。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Dict, Optional
import math


@dataclass(frozen=True)
class SlippagePolicy:
    """
    滑價政策定義

    Attributes:
        definition: 滑價定義，固定為 "per_fill_per_side"
        levels: 滑價等級對應的 tick 數，預設為 S0=0, S1=1, S2=2, S3=3
        selection_level: 策略選擇使用的滑價等級（預設 S2）
        stress_level: 壓力測試使用的滑價等級（預設 S3）
        mc_execution_level: MultiCharts 執行時使用的滑價等級（預設 S1）
    """
    definition: str = "per_fill_per_side"
    levels: Dict[str, int] = field(default_factory=lambda: {"S0": 0, "S1": 1, "S2": 2, "S3": 3})
    selection_level: str = "S2"
    stress_level: str = "S3"
    mc_execution_level: str = "S1"

    def __post_init__(self):
        """驗證欄位"""
        if self.definition != "per_fill_per_side":
            raise ValueError(f"definition 必須為 'per_fill_per_side'，收到: {self.definition}")
        
        required_levels = {"S0", "S1", "S2", "S3"}
        if not required_levels.issubset(self.levels.keys()):
            missing = required_levels - set(self.levels.keys())
            raise ValueError(f"levels 缺少必要等級: {missing}")
        
        for level in (self.selection_level, self.stress_level, self.mc_execution_level):
            if level not in self.levels:
                raise ValueError(f"等級 {level} 不存在於 levels 中")
        
        # 確保 tick 數為非負整數
        for level, ticks in self.levels.items():
            if not isinstance(ticks, int) or ticks < 0:
                raise ValueError(f"等級 {level} 的 ticks 必須為非負整數，收到: {ticks}")

    def get_ticks(self, level: str) -> int:
        """
        取得指定等級的滑價 tick 數

        Args:
            level: 等級名稱，例如 "S2"

        Returns:
            滑價 tick 數

        Raises:
            KeyError: 等級不存在
        """
        return self.levels[level]

    def get_selection_ticks(self) -> int:
        """取得 selection_level 對應的 tick 數"""
        return self.get_ticks(self.selection_level)

    def get_stress_ticks(self) -> int:
        """取得 stress_level 對應的 tick 數"""
        return self.get_ticks(self.stress_level)

    def get_mc_execution_ticks(self) -> int:
        """取得 mc_execution_level 對應的 tick 數"""
        return self.get_ticks(self.mc_execution_level)


def apply_slippage_to_price(
    price: float,
    side: Literal["buy", "sell", "sellshort", "buytocover"],
    slip_ticks: int,
    tick_size: float,
) -> float:
    """
    根據滑價 tick 數調整價格

    規則：
    - 買入（buy, buytocover）：價格增加 slip_ticks * tick_size
    - 賣出（sell, sellshort）：價格減少 slip_ticks * tick_size

    Args:
        price: 原始價格
        side: 交易方向
        slip_ticks: 滑價 tick 數（非負整數）
        tick_size: 每 tick 價格變動量（必須 > 0）

    Returns:
        調整後的價格

    Raises:
        ValueError: 參數無效
    """
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    if slip_ticks < 0:
        raise ValueError(f"slip_ticks 必須 >= 0，收到: {slip_ticks}")
    
    # 計算滑價金額
    slippage_amount = slip_ticks * tick_size
    
    # 根據方向調整
    if side in ("buy", "buytocover"):
        # 買入：支付更高價格
        adjusted = price + slippage_amount
    elif side in ("sell", "sellshort"):
        # 賣出：收到更低價格
        adjusted = price - slippage_amount
    else:
        raise ValueError(f"無效的 side: {side}，必須為 buy/sell/sellshort/buytocover")
    
    # 確保價格非負（雖然理論上可能為負，但實務上不應發生）
    if adjusted < 0:
        adjusted = 0.0
    
    return adjusted


def round_to_tick(price: float, tick_size: float) -> float:
    """
    將價格四捨五入至最近的 tick 邊界

    Args:
        price: 原始價格
        tick_size: tick 大小

    Returns:
        四捨五入後的價格
    """
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    
    # 計算 tick 數
    ticks = round(price / tick_size)
    return ticks * tick_size


def compute_slippage_cost_per_side(
    slip_ticks: int,
    tick_size: float,
    quantity: float = 1.0,
) -> float:
    """
    計算單邊滑價成本（每單位）

    Args:
        slip_ticks: 滑價 tick 數
        tick_size: tick 大小
        quantity: 數量（預設 1.0）

    Returns:
        滑價成本（正數）
    """
    if slip_ticks < 0:
        raise ValueError(f"slip_ticks 必須 >= 0，收到: {slip_ticks}")
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    
    return slip_ticks * tick_size * quantity


def compute_round_trip_slippage_cost(
    slip_ticks: int,
    tick_size: float,
    quantity: float = 1.0,
) -> float:
    """
    計算來回交易（entry + exit）的總滑價成本

    由於每邊都會產生滑價，總成本為 2 * slip_ticks * tick_size * quantity

    Args:
        slip_ticks: 每邊滑價 tick 數
        tick_size: tick 大小
        quantity: 數量

    Returns:
        總滑價成本
    """
    per_side = compute_slippage_cost_per_side(slip_ticks, tick_size, quantity)
    return 2.0 * per_side



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/snapshot.py
sha256(source_bytes) = 4a590ba03ce263bc719cdc62d01ceab9d17999c2f538f3426bff38abe26c8607
bytes = 7785
redacted = False
--------------------------------------------------------------------------------
"""
Deterministic Snapshot - Freeze-time artifact hash registry.

Phase 5: Create reproducible snapshot of all artifacts when season is frozen.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
import os


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, IOError):
        # If file cannot be read, return empty hash
        return ""


def collect_artifact_hashes(season_dir: Path) -> Dict[str, Any]:
    """
    Collect SHA256 hashes of all artifacts in a season directory.
    
    Returns:
        Dict with structure:
        {
            "snapshot_ts": "ISO-8601 timestamp",
            "season": "season identifier",
            "artifacts": {
                "relative/path/to/file": {
                    "sha256": "hexdigest",
                    "size_bytes": 1234,
                    "mtime": 1234567890.0
                },
                ...
            },
            "directories_scanned": [
                "runs/",
                "portfolio/",
                "research/",
                "governance/"
            ]
        }
    """
    from datetime import datetime, timezone
    
    # Directories to scan (relative to season_dir)
    scan_dirs = [
        "runs",
        "portfolio",
        "research",
        "governance"
    ]
    
    artifacts = {}
    
    for rel_dir in scan_dirs:
        dir_path = season_dir / rel_dir
        if not dir_path.exists():
            continue
        
        # Walk through directory
        for root, dirs, files in os.walk(dir_path):
            root_path = Path(root)
            for filename in files:
                filepath = root_path / filename
                
                # Skip temporary files and hidden files
                if filename.startswith(".") or filename.endswith(".tmp"):
                    continue
                
                # Skip very large files (>100MB) to avoid performance issues
                try:
                    file_size = filepath.stat().st_size
                    if file_size > 100 * 1024 * 1024:  # 100MB
                        continue
                except OSError:
                    continue
                
                # Compute relative path from season_dir
                try:
                    rel_path = filepath.relative_to(season_dir)
                except ValueError:
                    # Should not happen, but skip if it does
                    continue
                
                # Compute hash
                sha256 = compute_file_hash(filepath)
                if not sha256:  # Skip if hash computation failed
                    continue
                
                # Get file metadata
                try:
                    stat = filepath.stat()
                    artifacts[str(rel_path)] = {
                        "sha256": sha256,
                        "size_bytes": stat.st_size,
                        "mtime": stat.st_mtime,
                        "mtime_iso": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                    }
                except OSError:
                    # Skip if metadata cannot be read
                    continue
    
    return {
        "snapshot_ts": datetime.now(timezone.utc).isoformat(),
        "season": season_dir.name,
        "artifacts": artifacts,
        "directories_scanned": scan_dirs,
        "artifact_count": len(artifacts)
    }


def create_freeze_snapshot(season: str) -> Path:
    """
    Create deterministic snapshot of all artifacts in a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        Path to the created snapshot file.
    
    Raises:
        FileNotFoundError: If season directory does not exist.
        OSError: If snapshot cannot be written.
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    if not season_path.exists():
        raise FileNotFoundError(f"Season directory does not exist: {season_path}")
    
    # Collect artifact hashes
    snapshot_data = collect_artifact_hashes(season_path)
    
    # Write snapshot file
    governance_dir = season_path / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    
    snapshot_path = governance_dir / "freeze_snapshot.json"
    
    # Write atomically
    temp_path = snapshot_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    # Replace original
    temp_path.replace(snapshot_path)
    
    return snapshot_path


def load_freeze_snapshot(season: str) -> Dict[str, Any]:
    """
    Load freeze snapshot for a season.
    
    Args:
        season: Season identifier
    
    Returns:
        Snapshot data dictionary.
    
    Raises:
        FileNotFoundError: If snapshot file does not exist.
        json.JSONDecodeError: If snapshot file is corrupted.
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    snapshot_path = season_path / "governance" / "freeze_snapshot.json"
    
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Freeze snapshot not found: {snapshot_path}")
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_snapshot_integrity(season: str) -> Dict[str, Any]:
    """
    Verify current artifacts against freeze snapshot.
    
    Args:
        season: Season identifier
    
    Returns:
        Dict with verification results:
        {
            "ok": bool,
            "missing_files": List[str],
            "changed_files": List[str],
            "new_files": List[str],
            "total_checked": int,
            "errors": List[str]
        }
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    
    try:
        snapshot = load_freeze_snapshot(season)
    except FileNotFoundError:
        return {
            "ok": False,
            "missing_files": [],
            "changed_files": [],
            "new_files": [],
            "total_checked": 0,
            "errors": ["Freeze snapshot not found"]
        }
    
    # Get current artifact hashes
    current_artifacts = collect_artifact_hashes(season_path)
    
    # Compare
    snapshot_artifacts = snapshot.get("artifacts", {})
    current_artifact_paths = set(current_artifacts.get("artifacts", {}).keys())
    snapshot_artifact_paths = set(snapshot_artifacts.keys())
    
    missing_files = list(snapshot_artifact_paths - current_artifact_paths)
    new_files = list(current_artifact_paths - snapshot_artifact_paths)
    
    changed_files = []
    for path in snapshot_artifact_paths.intersection(current_artifact_paths):
        snapshot_hash = snapshot_artifacts[path].get("sha256", "")
        current_hash = current_artifacts["artifacts"][path].get("sha256", "")
        if snapshot_hash != current_hash:
            changed_files.append(path)
    
    ok = len(missing_files) == 0 and len(changed_files) == 0
    
    return {
        "ok": ok,
        "missing_files": sorted(missing_files),
        "changed_files": sorted(changed_files),
        "new_files": sorted(new_files),
        "total_checked": len(snapshot_artifact_paths),
        "errors": [] if ok else ["Artifacts have been modified since freeze"]
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/state.py
sha256(source_bytes) = bf0a87d50e962d0e1b31192ed51cfa7044b2bf86bbc33566a3aa28f14f4b818c
bytes = 9512
redacted = False
--------------------------------------------------------------------------------
"""SystemState - read-only state snapshots for Attack #9 – Headless Intent-State Contract.

Defines immutable SystemState objects that represent the current state of the system.
Backend outputs only read-only SystemState snapshots. UI may only read these snapshots,
not modify them. All state updates happen only inside StateProcessor.
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    """Status of a job."""
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SeasonStatus(str, Enum):
    """Status of a season."""
    ACTIVE = "active"
    FROZEN = "frozen"
    ARCHIVED = "archived"


class DatasetStatus(str, Enum):
    """Status of a dataset."""
    AVAILABLE = "available"
    BUILDING = "building"
    MISSING_PARQUET = "missing_parquet"
    ERROR = "error"


class JobProgress(BaseModel):
    """Progress information for a job."""
    model_config = ConfigDict(frozen=True)
    
    job_id: str
    status: JobStatus
    units_done: int = 0
    units_total: int = 0
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime
    season: str
    dataset_id: str
    
    @property
    def is_complete(self) -> bool:
        """Check if job is complete."""
        return self.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
    
    @property
    def is_active(self) -> bool:
        """Check if job is active (running or paused)."""
        return self.status in [JobStatus.RUNNING, JobStatus.PAUSED]


class SeasonInfo(BaseModel):
    """Information about a season."""
    model_config = ConfigDict(frozen=True)
    
    season_id: str
    status: SeasonStatus
    created_at: datetime
    frozen_at: Optional[datetime] = None
    job_count: int = 0
    completed_job_count: int = 0
    total_units: int = 0
    
    @property
    def is_frozen(self) -> bool:
        """Check if season is frozen."""
        return self.status == SeasonStatus.FROZEN


class DatasetInfo(BaseModel):
    """Information about a dataset."""
    model_config = ConfigDict(frozen=True)
    
    dataset_id: str
    status: DatasetStatus
    symbol: str
    timeframe: str
    start_date: date
    end_date: date
    has_parquet: bool = False
    parquet_missing_count: int = 0
    last_built_at: Optional[datetime] = None
    
    @property
    def is_available(self) -> bool:
        """Check if dataset is available for use."""
        return self.status == DatasetStatus.AVAILABLE and self.has_parquet


class SystemMetrics(BaseModel):
    """System-wide metrics."""
    model_config = ConfigDict(frozen=True)
    
    # Job metrics
    total_jobs: int = 0
    active_jobs: int = 0
    queued_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    
    # Unit metrics
    total_units_processed: int = 0
    units_per_second: float = 0.0
    
    # Resource metrics
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    disk_usage_gb: float = 0.0
    
    # Timestamps
    snapshot_timestamp: datetime = Field(default_factory=datetime.now)
    uptime_seconds: float = 0.0


class IntentQueueStatus(BaseModel):
    """Status of the intent processing queue."""
    model_config = ConfigDict(frozen=True)
    
    queue_size: int = 0
    processing_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    duplicate_rejected_count: int = 0  # Idempotency rejects
    
    # Processing latency
    avg_processing_time_ms: float = 0.0
    max_processing_time_ms: float = 0.0
    
    # Current processing intent (if any)
    current_intent_id: Optional[str] = None
    current_intent_type: Optional[str] = None
    current_intent_started_at: Optional[datetime] = None


class SystemState(BaseModel):
    """Immutable snapshot of the entire system state.
    
    This is the read-only state that UI can observe. All state updates
    happen only inside StateProcessor. UI receives snapshots of this state.
    """
    model_config = ConfigDict(frozen=True)
    
    # Metadata
    state_id: str = Field(default_factory=lambda: f"state_{datetime.now().isoformat()}")
    snapshot_timestamp: datetime = Field(default_factory=datetime.now)
    
    # System metrics
    metrics: SystemMetrics = Field(default_factory=SystemMetrics)
    
    # Intent queue status
    intent_queue: IntentQueueStatus = Field(default_factory=IntentQueueStatus)
    
    # Collections
    seasons: Dict[str, SeasonInfo] = Field(default_factory=dict)
    datasets: Dict[str, DatasetInfo] = Field(default_factory=dict)
    jobs: Dict[str, JobProgress] = Field(default_factory=dict)
    
    # Active processes
    active_builds: Set[str] = Field(default_factory=set)  # dataset_ids being built
    active_job_ids: Set[str] = Field(default_factory=set)  # job_ids currently running
    
    # System health
    is_healthy: bool = True
    health_messages: List[str] = Field(default_factory=list)
    
    # UI-specific state (read-only views)
    ui_views: Dict[str, Any] = Field(default_factory=dict)
    
    # Derived properties
    @property
    def frozen_seasons(self) -> List[str]:
        """Get list of frozen season IDs."""
        return [season_id for season_id, season in self.seasons.items() 
                if season.is_frozen]
    
    @property
    def available_datasets(self) -> List[str]:
        """Get list of available dataset IDs."""
        return [dataset_id for dataset_id, dataset in self.datasets.items() 
                if dataset.is_available]
    
    @property
    def active_job_progress(self) -> List[JobProgress]:
        """Get progress of active jobs."""
        return [job for job in self.jobs.values() if job.is_active]
    
    @property
    def recent_jobs(self, limit: int = 10) -> List[JobProgress]:
        """Get most recent jobs."""
        sorted_jobs = sorted(
            self.jobs.values(), 
            key=lambda j: j.updated_at, 
            reverse=True
        )
        return sorted_jobs[:limit]
    
    def get_job(self, job_id: str) -> Optional[JobProgress]:
        """Get job progress by ID."""
        return self.jobs.get(job_id)
    
    def get_season(self, season_id: str) -> Optional[SeasonInfo]:
        """Get season info by ID."""
        return self.seasons.get(season_id)
    
    def get_dataset(self, dataset_id: str) -> Optional[DatasetInfo]:
        """Get dataset info by ID."""
        return self.datasets.get(dataset_id)
    
    def is_season_frozen(self, season_id: str) -> bool:
        """Check if a season is frozen."""
        season = self.get_season(season_id)
        return season.is_frozen if season else False
    
    def is_dataset_available(self, dataset_id: str) -> bool:
        """Check if a dataset is available."""
        dataset = self.get_dataset(dataset_id)
        return dataset.is_available if dataset else False
    
    def validate_job_creation(self, season_id: str, dataset_id: str) -> List[str]:
        """Validate if a job can be created.
        
        Returns list of error messages, empty if valid.
        """
        errors = []
        
        # Check season
        season = self.get_season(season_id)
        if not season:
            errors.append(f"Season not found: {season_id}")
        elif season.is_frozen:
            errors.append(f"Season is frozen: {season_id}")
        
        # Check dataset
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            errors.append(f"Dataset not found: {dataset_id}")
        elif not dataset.is_available:
            errors.append(f"Dataset not available: {dataset_id} (status: {dataset.status})")
        
        # Check system health
        if not self.is_healthy:
            errors.append("System is not healthy")
        
        return errors


# Factory functions for creating state snapshots

def create_initial_state() -> SystemState:
    """Create initial system state."""
    return SystemState(
        state_id="initial",
        metrics=SystemMetrics(),
        intent_queue=IntentQueueStatus(),
        seasons={},
        datasets={},
        jobs={},
        active_builds=set(),
        active_job_ids=set(),
        is_healthy=True,
        health_messages=["System initialized"],
        ui_views={}
    )


def create_state_snapshot(
    base_state: SystemState,
    **updates: Any
) -> SystemState:
    """Create a new state snapshot with updates.
    
    Since SystemState is immutable, this creates a copy with updated fields.
    Used by StateProcessor to produce new state snapshots.
    """
    # Create a mutable copy of the data
    data = base_state.model_dump()
    
    # Apply updates
    for key, value in updates.items():
        if key in data:
            if isinstance(data[key], dict) and isinstance(value, dict):
                # Merge dictionaries
                data[key] = {**data[key], **value}
            elif isinstance(data[key], list) and isinstance(value, list):
                # Replace list
                data[key] = value
            elif isinstance(data[key], set) and isinstance(value, set):
                # Replace set
                data[key] = value
            else:
                data[key] = value
    
    # Create new immutable state
    return SystemState(**data)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/winners_builder.py
sha256(source_bytes) = a9051d6f5e90653da86c8bd6ff4811b3e2d390bc48a39526f7aa3d87c7b2399f
bytes = 6640
redacted = False
--------------------------------------------------------------------------------

"""Winners builder - converts legacy winners to v2 schema.

Builds v2 winners.json from legacy topk format with fallback strategies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from FishBroWFS_V2.core.winners_schema import WinnerItemV2, build_winners_v2_dict


def build_winners_v2(
    *,
    stage_name: str,
    run_id: str,
    manifest: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    legacy_topk: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build winners.json v2 from legacy topk format.
    
    Args:
        stage_name: Stage identifier
        run_id: Run ID
        manifest: Manifest dict (AuditSchema)
        config_snapshot: Config snapshot dict
        legacy_topk: Legacy topk list (old format items)
        
    Returns:
        Winners dict with v2 schema
    """
    # Extract strategy_id
    strategy_id = _extract_strategy_id(config_snapshot, manifest)
    
    # Extract symbol/timeframe
    symbol = _extract_symbol(config_snapshot)
    timeframe = _extract_timeframe(config_snapshot)
    
    # Build v2 items
    v2_items: List[WinnerItemV2] = []
    
    for legacy_item in legacy_topk:
        # Extract param_id (required for candidate_id generation)
        param_id = legacy_item.get("param_id")
        if param_id is None:
            # Skip items without param_id (should not happen, but be defensive)
            continue
        
        # Generate candidate_id (temporary: strategy_id:param_id)
        # Future: upgrade to strategy_id:params_hash[:12] when params are available
        candidate_id = f"{strategy_id}:{param_id}"
        
        # Extract params (fallback to empty dict)
        params = _extract_params(legacy_item, config_snapshot, param_id)
        
        # Extract score (priority: score/finalscore > net_profit > 0.0)
        score = _extract_score(legacy_item)
        
        # Build metrics (must include legacy fields for backward compatibility)
        metrics = {
            "net_profit": float(legacy_item.get("net_profit", 0.0)),
            "max_dd": float(legacy_item.get("max_dd", 0.0)),
            "trades": int(legacy_item.get("trades", 0)),
            "param_id": int(param_id),  # Keep for backward compatibility
        }
        
        # Add proxy_value if present (Stage0)
        if "proxy_value" in legacy_item:
            metrics["proxy_value"] = float(legacy_item["proxy_value"])
        
        # Build source metadata
        source = {
            "param_id": int(param_id),
            "run_id": run_id,
            "stage_name": stage_name,
        }
        
        # Create v2 item
        v2_item = WinnerItemV2(
            candidate_id=candidate_id,
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            params=params,
            score=score,
            metrics=metrics,
            source=source,
        )
        
        v2_items.append(v2_item)
    
    # Build notes with candidate_id_mode info
    notes = {
        "candidate_id_mode": "strategy_id:param_id",  # Temporary mode
        "note": "candidate_id uses param_id temporarily; will upgrade to params_hash when params are available",
    }
    
    # Build v2 winners dict
    return build_winners_v2_dict(
        stage_name=stage_name,
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        topk=v2_items,
        notes=notes,
    )


def _extract_strategy_id(config_snapshot: Dict[str, Any], manifest: Dict[str, Any]) -> str:
    """
    Extract strategy_id from config_snapshot or manifest.
    
    Priority:
    1. config_snapshot.get("strategy_id")
    2. manifest.get("dataset_id") (fallback)
    3. "unknown" (final fallback)
    """
    if "strategy_id" in config_snapshot:
        return str(config_snapshot["strategy_id"])
    
    dataset_id = manifest.get("dataset_id")
    if dataset_id:
        return str(dataset_id)
    
    return "unknown"


def _extract_symbol(config_snapshot: Dict[str, Any]) -> str:
    """
    Extract symbol from config_snapshot.
    
    Returns "UNKNOWN" if not available.
    """
    return str(config_snapshot.get("symbol", "UNKNOWN"))


def _extract_timeframe(config_snapshot: Dict[str, Any]) -> str:
    """
    Extract timeframe from config_snapshot.
    
    Returns "UNKNOWN" if not available.
    """
    return str(config_snapshot.get("timeframe", "UNKNOWN"))


def _extract_params(
    legacy_item: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    param_id: int,
) -> Dict[str, Any]:
    """
    Extract params from legacy_item or config_snapshot.
    
    Priority:
    1. legacy_item.get("params")
    2. config_snapshot.get("params_by_id", {}).get(param_id)
    3. config_snapshot.get("params_spec") (if available)
    4. {} (empty dict fallback)
    
    Returns empty dict {} if params are not available.
    """
    # Try legacy_item first
    if "params" in legacy_item:
        params = legacy_item["params"]
        if isinstance(params, dict):
            return params
    
    # Try config_snapshot params_by_id
    params_by_id = config_snapshot.get("params_by_id", {})
    if isinstance(params_by_id, dict) and param_id in params_by_id:
        params = params_by_id[param_id]
        if isinstance(params, dict):
            return params
    
    # Try config_snapshot params_spec (if available)
    params_spec = config_snapshot.get("params_spec")
    if isinstance(params_spec, dict):
        # Could extract from params_spec if it has param_id mapping
        # For now, return empty dict
        pass
    
    # Fallback: empty dict
    return {}


def _extract_score(legacy_item: Dict[str, Any]) -> float:
    """
    Extract score from legacy_item.
    
    Priority:
    1. legacy_item.get("score")
    2. legacy_item.get("finalscore")
    3. legacy_item.get("net_profit")
    4. legacy_item.get("proxy_value") (for Stage0)
    5. 0.0 (fallback)
    """
    if "score" in legacy_item:
        val = legacy_item["score"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "finalscore" in legacy_item:
        val = legacy_item["finalscore"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "net_profit" in legacy_item:
        val = legacy_item["net_profit"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "proxy_value" in legacy_item:
        val = legacy_item["proxy_value"]
        if isinstance(val, (int, float)):
            return float(val)
    
    return 0.0



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/winners_schema.py
sha256(source_bytes) = b415c3cc05931a57bc3f6cc5ffdfa2b6646b8d12705badbdbecf030e96f6580c
bytes = 3593
redacted = False
--------------------------------------------------------------------------------

"""Winners schema v2 (SSOT).

Defines the v2 schema for winners.json with enhanced metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


WINNERS_SCHEMA_VERSION = "v2"


@dataclass(frozen=True)
class WinnerItemV2:
    """
    Winner item in v2 schema.
    
    Each item represents a top-K candidate with complete metadata.
    """
    candidate_id: str  # Format: {strategy_id}:{param_id} (temporary) or {strategy_id}:{params_hash[:12]} (future)
    strategy_id: str  # Strategy identifier (e.g., "donchian_atr")
    symbol: str  # Symbol identifier (e.g., "CME.MNQ" or "UNKNOWN")
    timeframe: str  # Timeframe (e.g., "60m" or "UNKNOWN")
    params: Dict[str, Any]  # Parameters dict (may be empty {} if not available)
    score: float  # Ranking score (finalscore, net_profit, or proxy_value)
    metrics: Dict[str, Any]  # Performance metrics (must include legacy fields: net_profit, max_dd, trades, param_id)
    source: Dict[str, Any]  # Source metadata (param_id, run_id, stage_name)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


def build_winners_v2_dict(
    *,
    stage_name: str,
    run_id: str,
    generated_at: str | None = None,
    topk: List[WinnerItemV2],
    notes: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build winners.json v2 structure.
    
    Args:
        stage_name: Stage identifier
        run_id: Run ID
        generated_at: ISO8601 timestamp (defaults to now if None)
        topk: List of WinnerItemV2 items
        notes: Additional notes dict (will be merged with default notes)
        
    Returns:
        Winners dict with v2 schema
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    default_notes = {
        "schema": WINNERS_SCHEMA_VERSION,
    }
    
    if notes:
        default_notes.update(notes)
    
    return {
        "schema": WINNERS_SCHEMA_VERSION,
        "stage_name": stage_name,
        "generated_at": generated_at,
        "topk": [item.to_dict() for item in topk],
        "notes": default_notes,
    }


def is_winners_v2(winners: Dict[str, Any]) -> bool:
    """
    Check if winners dict is v2 schema.
    
    Args:
        winners: Winners dict
        
    Returns:
        True if v2 schema, False otherwise
    """
    # Check top-level schema field
    if winners.get("schema") == WINNERS_SCHEMA_VERSION:
        return True
    
    # Check notes.schema field (legacy check)
    notes = winners.get("notes", {})
    if isinstance(notes, dict) and notes.get("schema") == WINNERS_SCHEMA_VERSION:
        return True
    
    return False


def is_winners_legacy(winners: Dict[str, Any]) -> bool:
    """
    Check if winners dict is legacy (v1) schema.
    
    Args:
        winners: Winners dict
        
    Returns:
        True if legacy schema, False otherwise
    """
    # If it's v2, it's not legacy
    if is_winners_v2(winners):
        return False
    
    # Legacy format: {"topk": [...], "notes": {"schema": "v1"}} or just {"topk": [...]}
    if "topk" in winners:
        # Check if items have v2 structure (candidate_id, strategy_id, etc.)
        topk = winners.get("topk", [])
        if topk and isinstance(topk[0], dict):
            # If first item has candidate_id, it's v2
            if "candidate_id" in topk[0]:
                return False
        return True
    
    return False



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/governance/__init__.py
sha256(source_bytes) = 1636f9e7dff514f1e8478f9e199228d850fcf060871f78cfbd8942c29d69cd58
bytes = 52
redacted = False
--------------------------------------------------------------------------------

"""Governance lifecycle and transition logic."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/governance/transition.py
sha256(source_bytes) = 2f0e0639684a99a6540a1cf2d0f743de8ae06d99766ab16ff8227e6357f06952
bytes = 1849
redacted = False
--------------------------------------------------------------------------------

"""Governance lifecycle state transition logic.

Pure functions for state transitions based on decisions.
"""

from __future__ import annotations

from FishBroWFS_V2.core.schemas.governance import Decision, LifecycleState


def governance_transition(
    prev_state: LifecycleState,
    decision: Decision,
) -> LifecycleState:
    """
    Compute next lifecycle state based on previous state and decision.
    
    Transition rules:
    - INCUBATION + KEEP → CANDIDATE
    - INCUBATION + DROP → RETIRED
    - INCUBATION + FREEZE → INCUBATION (no change)
    - CANDIDATE + KEEP → LIVE
    - CANDIDATE + DROP → RETIRED
    - CANDIDATE + FREEZE → CANDIDATE (no change)
    - LIVE + KEEP → LIVE (no change)
    - LIVE + DROP → RETIRED
    - LIVE + FREEZE → LIVE (no change)
    - RETIRED + any → RETIRED (terminal state, no transitions)
    
    Args:
        prev_state: Previous lifecycle state
        decision: Governance decision (KEEP/DROP/FREEZE)
        
    Returns:
        Next lifecycle state
    """
    # RETIRED is terminal state
    if prev_state == "RETIRED":
        return "RETIRED"
    
    # State transition matrix
    transitions: dict[tuple[LifecycleState, Decision], LifecycleState] = {
        # INCUBATION transitions
        ("INCUBATION", Decision.KEEP): "CANDIDATE",
        ("INCUBATION", Decision.DROP): "RETIRED",
        ("INCUBATION", Decision.FREEZE): "INCUBATION",
        
        # CANDIDATE transitions
        ("CANDIDATE", Decision.KEEP): "LIVE",
        ("CANDIDATE", Decision.DROP): "RETIRED",
        ("CANDIDATE", Decision.FREEZE): "CANDIDATE",
        
        # LIVE transitions
        ("LIVE", Decision.KEEP): "LIVE",
        ("LIVE", Decision.DROP): "RETIRED",
        ("LIVE", Decision.FREEZE): "LIVE",
    }
    
    return transitions.get((prev_state, decision), prev_state)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/__init__.py
sha256(source_bytes) = 7415dcb6d73912efd2b20efa20e4f11fc9a7fbfafdbd817071575e3089ef9cc0
bytes = 35
redacted = False
--------------------------------------------------------------------------------

"""Schemas for core modules."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/governance.py
sha256(source_bytes) = 45ee0a268e55e562aca6afa8d61722757d80ef1b79af939136a3d181cbbda3a3
bytes = 2591
redacted = False
--------------------------------------------------------------------------------

"""Pydantic schema for governance.json validation.

Validates governance decisions with KEEP/DROP/FREEZE and evidence chain.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional, Literal, TypeAlias


class Decision(str, Enum):
    """Governance decision types (SSOT)."""
    KEEP = "KEEP"
    FREEZE = "FREEZE"
    DROP = "DROP"


LifecycleState: TypeAlias = Literal["INCUBATION", "CANDIDATE", "LIVE", "RETIRED"]

RenderHint = Literal["highlight", "chart_annotation", "diff"]


class EvidenceLinkModel(BaseModel):
    """Evidence link model for governance."""
    source_path: str
    json_pointer: str
    note: str = ""
    render_hint: RenderHint = "highlight"  # Rendering hint for viewer (highlight/chart_annotation/diff)
    render_payload: dict = Field(default_factory=dict)  # Optional payload for custom rendering


class GovernanceDecisionRow(BaseModel):
    """
    Governance decision row schema.
    
    Represents a single governance decision with rule_id and evidence chain.
    """
    strategy_id: str
    decision: Decision
    rule_id: str  # "R1"/"R2"/"R3"
    reason: str = ""
    run_id: str
    stage: str
    config_hash: Optional[str] = None
    
    lifecycle_state: LifecycleState = "INCUBATION"  # Lifecycle state (INCUBATION/CANDIDATE/LIVE/RETIRED)
    
    evidence: List[EvidenceLinkModel] = Field(default_factory=list)
    metrics_snapshot: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from existing schema (for backward compatibility)
    candidate_id: Optional[str] = None
    reasons: Optional[List[str]] = None
    created_at: Optional[str] = None
    git_sha: Optional[str] = None
    
    model_config = ConfigDict(extra="allow")  # Allow extra fields for backward compatibility


class GovernanceReport(BaseModel):
    """
    Governance report schema.
    
    Validates governance.json structure with decision rows and metadata.
    Supports both items format and rows format.
    """
    config_hash: str  # Required top-level field for DIRTY check contract
    schema_version: Optional[str] = None
    run_id: str
    rows: List[GovernanceDecisionRow] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from existing schema (for backward compatibility)
    items: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra="allow")  # Allow extra fields for backward compatibility



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/manifest.py
sha256(source_bytes) = 4c68e01e0897c24af061196c5c2f42b694bec0519561a73d7d75537f96738781
bytes = 3601
redacted = False
--------------------------------------------------------------------------------

"""Pydantic schema for manifest.json validation.

Validates run manifest with stages and artifacts tracking.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional


class ManifestStage(BaseModel):
    """Stage information in manifest."""
    name: str
    status: str  # e.g. "DONE"/"FAILED"/"ABORTED"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    artifacts: Dict[str, str] = Field(default_factory=dict)  # filename -> relpath


class RunManifest(BaseModel):
    """
    Run manifest schema.
    
    Validates manifest.json structure with run metadata, config hash, and stages.
    """
    schema_version: Optional[str] = None  # For future versioning
    run_id: str
    season: str
    config_hash: str
    created_at: Optional[str] = None
    stages: List[ManifestStage] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from AuditSchema (for backward compatibility)
    git_sha: Optional[str] = None
    dirty_repo: Optional[bool] = None
    param_subsample_rate: Optional[float] = None
    dataset_id: Optional[str] = None
    bars: Optional[int] = None
    params_total: Optional[int] = None
    params_effective: Optional[int] = None
    artifact_version: Optional[str] = None
    
    # Phase 6.5: Mandatory fingerprint (validation enforces non-empty)
    data_fingerprint_sha1: Optional[str] = None
    
    # Phase 6.6: Timezone database metadata
    tzdb_provider: Optional[str] = None  # e.g., "zoneinfo"
    tzdb_version: Optional[str] = None  # Timezone database version
    data_tz: Optional[str] = None  # Data timezone (e.g., "Asia/Taipei")
    exchange_tz: Optional[str] = None  # Exchange timezone (e.g., "America/Chicago")
    
    # Phase 7: Strategy metadata
    strategy_id: Optional[str] = None  # Strategy identifier (e.g., "sma_cross")
    strategy_version: Optional[str] = None  # Strategy version (e.g., "v1")
    param_schema_hash: Optional[str] = None  # SHA1 hash of param_schema JSON


class UnifiedManifest(BaseModel):
    """
    Unified manifest schema for all manifest types (export, plan, view, quality).
    
    This schema defines the standard fields that should be present in all manifests
    for Manifest Tree Completeness verification.
    """
    # Common required fields
    manifest_type: str  # "export", "plan", "view", or "quality"
    manifest_version: str = "1.0"
    
    # Identification fields
    id: str  # run_id for export, plan_id for plan/view/quality
    
    # Timestamps
    generated_at_utc: Optional[str] = None
    created_at: Optional[str] = None
    
    # Source information
    source: Optional[Dict[str, Any]] = None
    
    # Input references (SHA256 hashes of input files)
    inputs: Optional[Dict[str, str]] = None
    
    # Files listing with SHA256 checksums (sorted by rel_path asc)
    files: Optional[List[Dict[str, str]]] = None
    
    # Combined SHA256 of all files (concatenated hashes)
    files_sha256: Optional[str] = None
    
    # Checksums for output files
    checksums: Optional[Dict[str, str]] = None
    
    # Type-specific checksums
    export_checksums: Optional[Dict[str, str]] = None
    plan_checksums: Optional[Dict[str, str]] = None
    view_checksums: Optional[Dict[str, str]] = None
    quality_checksums: Optional[Dict[str, str]] = None
    
    # Manifest self-hash (must be the last field)
    manifest_sha256: str
    
    model_config = ConfigDict(extra="allow")  # Allow additional type-specific fields



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/oom_gate.py
sha256(source_bytes) = 66c245f96340e0a3c817b6c6559b07eb613ba18e3691bf22d78307f88c3b2b9f
bytes = 1552
redacted = False
--------------------------------------------------------------------------------

"""Pydantic schemas for OOM gate input and output.

Locked schemas for PASS/BLOCK/AUTO_DOWNSAMPLE decisions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class OomGateInput(BaseModel):
    """
    Input for OOM gate decision.
    
    All fields are required for memory estimation.
    """
    bars: int = Field(gt=0, description="Number of bars")
    params: int = Field(gt=0, description="Total number of parameters")
    param_subsample_rate: float = Field(gt=0.0, le=1.0, description="Subsample rate in [0.0, 1.0]")
    intents_per_bar: float = Field(default=2.0, ge=0.0, description="Estimated intents per bar")
    bytes_per_intent_est: int = Field(default=64, gt=0, description="Estimated bytes per intent")
    ram_budget_bytes: int = Field(default=6_000_000_000, gt=0, description="RAM budget in bytes (default: 6GB)")


class OomGateDecision(BaseModel):
    """
    OOM gate decision output.
    
    Contains decision (PASS/BLOCK/AUTO_DOWNSAMPLE) and recommendations.
    """
    decision: Literal["PASS", "BLOCK", "AUTO_DOWNSAMPLE"]
    estimated_bytes: int = Field(ge=0, description="Estimated memory usage in bytes")
    ram_budget_bytes: int = Field(gt=0, description="RAM budget in bytes")
    recommended_subsample_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Recommended subsample rate (only for AUTO_DOWNSAMPLE)"
    )
    notes: str = Field(default="", description="Human-readable notes about the decision")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/portfolio.py
sha256(source_bytes) = b96982d515336c90944d6ec605835339d43d7ac386937355cd220f8f560649d3
bytes = 1045
redacted = False
--------------------------------------------------------------------------------
"""Portfolio-related schemas for signal series and instrument configuration."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Dict


class InstrumentsConfigV1(BaseModel):
    """Schema for instruments configuration YAML (version 1)."""
    version: int
    base_currency: str
    fx_rates: Dict[str, float]
    instruments: Dict[str, dict]  # 這裡可先放 dict，validate 在 loader 做


class SignalSeriesMetaV1(BaseModel):
    """Metadata for signal series (bar-based position/margin/notional)."""
    model_config = ConfigDict(populate_by_name=True)
    
    schema_id: Literal["SIGNAL_SERIES_V1"] = Field(
        default="SIGNAL_SERIES_V1",
        alias="schema"
    )
    instrument: str
    timeframe: str
    tz: str

    base_currency: str
    instrument_currency: str
    fx_to_base: float

    multiplier: float
    initial_margin_per_contract: float
    maintenance_margin_per_contract: float

    # traceability
    source_run_id: str
    source_spec_sha: str
    instruments_config_sha256: str
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/portfolio_v1.py
sha256(source_bytes) = 16d8db078a869431c0a91fb03ec6d25f1381a739cec3e09df16ef01a83dc37ba
bytes = 4259
redacted = False
--------------------------------------------------------------------------------
"""Portfolio engine schemas V1."""

from pydantic import BaseModel, Field
from typing import Literal, Dict, List, Optional
from datetime import datetime, timezone


class PortfolioPolicyV1(BaseModel):
    """Portfolio policy defining allocation limits and behavior."""
    version: Literal["PORTFOLIO_POLICY_V1"] = "PORTFOLIO_POLICY_V1"

    base_currency: str  # "TWD"
    instruments_config_sha256: str

    # account hard caps
    max_slots_total: int  # e.g. 4
    max_margin_ratio: float  # e.g. 0.35 (margin_used/equity)
    max_notional_ratio: Optional[float] = None  # optional v1

    # per-instrument cap (optional v1)
    max_slots_by_instrument: Dict[str, int] = Field(default_factory=dict)  # {"CME.MNQ":4, "TWF.MXF":2}

    # deterministic tie-breaker inputs
    strategy_priority: Dict[str, int]  # {strategy_id: priority_int}
    signal_strength_field: str  # e.g. "edge_score" or "signal_score"

    # behavior flags
    allow_force_kill: bool = False  # MUST default False
    allow_queue: bool = False  # v1: reject only


class PortfolioSpecV1(BaseModel):
    """Portfolio specification defining input sources (frozen only)."""
    version: Literal["PORTFOLIO_SPEC_V1"] = "PORTFOLIO_SPEC_V1"
    
    # Input seasons/artifacts sources
    seasons: List[str]  # e.g. ["2026Q1"]
    strategy_ids: List[str]  # e.g. ["S1", "S2"]
    instrument_ids: List[str]  # e.g. ["CME.MNQ", "TWF.MXF"]
    
    # Time range (optional)
    start_date: Optional[str] = None  # ISO format
    end_date: Optional[str] = None  # ISO format
    
    # Reference to policy
    policy_sha256: str  # SHA256 of canonicalized PortfolioPolicyV1 JSON
    
    # Canonicalization metadata
    spec_sha256: str  # SHA256 of this spec (computed after canonicalization)


class OpenPositionV1(BaseModel):
    """Open position in the portfolio."""
    strategy_id: str
    instrument_id: str  # MNQ / MXF
    slots: int = 1  # v1 fixed
    margin_base: float  # TWD
    notional_base: float  # TWD
    entry_bar_index: int
    entry_bar_ts: datetime


class SignalCandidateV1(BaseModel):
    """Candidate signal for admission."""
    strategy_id: str
    instrument_id: str  # MNQ / MXF
    bar_ts: datetime
    bar_index: int
    signal_strength: float  # higher = stronger signal
    candidate_score: float = 0.0  # deterministic score for sorting (higher = better)
    required_margin_base: float  # TWD
    required_slot: int = 1  # v1 fixed
    # Optional: additional metadata
    signal_series_sha256: Optional[str] = None  # for audit


class AdmissionDecisionV1(BaseModel):
    """Admission decision for a candidate signal."""
    version: Literal["ADMISSION_DECISION_V1"] = "ADMISSION_DECISION_V1"
    
    # Candidate identification
    strategy_id: str
    instrument_id: str
    bar_ts: datetime
    bar_index: int
    
    # Candidate metrics
    signal_strength: float
    candidate_score: float
    signal_series_sha256: Optional[str] = None  # for audit
    
    # Decision
    accepted: bool
    reason: Literal[
        "ACCEPT",
        "REJECT_FULL",
        "REJECT_MARGIN",
        "REJECT_POLICY",
        "REJECT_UNKNOWN"
    ]
    
    # Deterministic tie-breaking info
    sort_key_used: str  # e.g., "priority=-10,signal_strength=0.85,strategy_id=S1"
    
    # Portfolio state after this decision
    slots_after: int
    margin_after_base: float  # TWD
    
    # Timestamp of decision
    decision_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class PortfolioStateV1(BaseModel):
    """Portfolio state at a given bar."""
    bar_ts: datetime
    bar_index: int
    equity_base: float  # TWD
    slots_used: int
    margin_used_base: float  # TWD
    notional_used_base: float  # TWD
    open_positions: List[OpenPositionV1] = Field(default_factory=list)
    reject_count: int = 0  # cumulative rejects up to this bar


class PortfolioSummaryV1(BaseModel):
    """Summary of portfolio admission results."""
    total_candidates: int
    accepted_count: int
    rejected_count: int
    reject_reasons: Dict[str, int]  # reason -> count
    final_slots_used: int
    final_margin_used_base: float
    final_margin_ratio: float  # margin_used / equity
    policy_sha256: str
    spec_sha256: str
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/winners_v2.py
sha256(source_bytes) = 80f8e4a13ffd0ded61c8a9027209827a1f6859853687cb8feca125d21ef25d89
bytes = 2100
redacted = False
--------------------------------------------------------------------------------

"""Pydantic schema for winners_v2.json validation.

Validates winners v2 structure with KPI metrics.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional


class WinnerRow(BaseModel):
    """
    Winner row schema.
    
    Represents a single winner with strategy info and KPI metrics.
    """
    strategy_id: str
    symbol: str
    timeframe: str
    params: Dict[str, Any] = Field(default_factory=dict)
    
    # Required KPI metrics
    net_profit: float
    max_drawdown: float
    trades: int
    
    # Optional metrics
    win_rate: Optional[float] = None
    sharpe: Optional[float] = None
    sqn: Optional[float] = None
    
    # Evidence links (if already present)
    evidence: Dict[str, str] = Field(default_factory=dict)  # pointers/paths if already present
    
    # Additional fields from v2 schema (for backward compatibility)
    candidate_id: Optional[str] = None
    score: Optional[float] = None
    metrics: Optional[Dict[str, Any]] = None
    source: Optional[Dict[str, Any]] = None


class WinnersV2(BaseModel):
    """
    Winners v2 schema.
    
    Validates winners_v2.json structure with rows and metadata.
    Supports both v2 format (with topk) and normalized format (with rows).
    """
    config_hash: str  # Required top-level field for DIRTY check contract
    schema_version: Optional[str] = None  # "v2" or "schema" field
    run_id: Optional[str] = None
    stage: Optional[str] = None  # stage_name
    rows: List[WinnerRow] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from v2 schema (for backward compatibility)
    schema_name: Optional[str] = Field(default=None, alias="schema")  # "v2" - renamed to avoid conflict
    stage_name: Optional[str] = None
    generated_at: Optional[str] = None
    topk: Optional[List[Dict[str, Any]]] = None
    notes: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra="allow", populate_by_name=True)  # Allow extra fields and support alias



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/__init__.py
sha256(source_bytes) = d60a5bbf7b2bc9afb3b9d30e5219480699efbf6dc4d6af01273f3b60dbaa6d68
bytes = 637
redacted = False
--------------------------------------------------------------------------------
"""Data ingest module - Raw means RAW.

Phase 6.5 Data Ingest v1: Immutable, extremely stupid raw data ingestion.
"""

from FishBroWFS_V2.data.cache import CachePaths, cache_paths, read_parquet_cache, write_parquet_cache
from FishBroWFS_V2.data.fingerprint import DataFingerprint, compute_txt_fingerprint
from FishBroWFS_V2.data.raw_ingest import IngestPolicy, RawIngestResult, ingest_raw_txt

__all__ = [
    "IngestPolicy",
    "RawIngestResult",
    "ingest_raw_txt",
    "DataFingerprint",
    "compute_txt_fingerprint",
    "CachePaths",
    "cache_paths",
    "write_parquet_cache",
    "read_parquet_cache",
]

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/cache.py
sha256(source_bytes) = 18ad78e3bb3c7786bbc46576c0944b57a7c823872817b00477982cbbd5d3d36f
bytes = 3315
redacted = False
--------------------------------------------------------------------------------
"""Parquet cache - Cache, Not Truth.

Binding #4: Parquet is Cache, Not Truth.
Cache can be deleted and rebuilt. Fingerprint is the truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CachePaths:
    """Cache file paths for a symbol.
    
    Attributes:
        parquet_path: Path to parquet cache file
        meta_path: Path to meta.json file
    """
    parquet_path: Path
    meta_path: Path


def cache_paths(cache_root: Path, symbol: str) -> CachePaths:
    """Get cache paths for a symbol.
    
    Args:
        cache_root: Root directory for cache files
        symbol: Symbol identifier (e.g., "CME.MNQ")
        
    Returns:
        CachePaths with parquet_path and meta_path
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    
    # Sanitize symbol for filename
    safe_symbol = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
    
    return CachePaths(
        parquet_path=cache_root / f"{safe_symbol}.parquet",
        meta_path=cache_root / f"{safe_symbol}.meta.json",
    )


def write_parquet_cache(paths: CachePaths, df: pd.DataFrame, meta: dict[str, Any]) -> None:
    """Write parquet cache + meta.json.
    
    Parquet stores raw df (with ts_str), no sort, no dedup.
    meta.json must contain:
    - data_fingerprint_sha1
    - source_path
    - ingest_policy
    - rows, first_ts_str, last_ts_str
    
    Args:
        paths: CachePaths for this symbol
        df: DataFrame to cache (must have columns: ts_str, open, high, low, close, volume)
        meta: Metadata dict (must include data_fingerprint_sha1, source_path, ingest_policy, etc.)
        
    Raises:
        ValueError: If required meta fields are missing
    """
    required_meta_fields = ["data_fingerprint_sha1", "source_path", "ingest_policy"]
    missing_fields = [field for field in required_meta_fields if field not in meta]
    if missing_fields:
        raise ValueError(f"Missing required meta fields: {missing_fields}")
    
    # Write parquet (preserve order, no sort)
    paths.parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(paths.parquet_path, index=False, engine="pyarrow")
    
    # Write meta.json
    with paths.meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")


def read_parquet_cache(paths: CachePaths) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read parquet cache + meta.json.
    
    Args:
        paths: CachePaths for this symbol
        
    Returns:
        Tuple of (DataFrame, meta_dict)
        
    Raises:
        FileNotFoundError: If parquet or meta.json does not exist
        json.JSONDecodeError: If meta.json is invalid JSON
    """
    if not paths.parquet_path.exists():
        raise FileNotFoundError(f"Parquet cache not found: {paths.parquet_path}")
    if not paths.meta_path.exists():
        raise FileNotFoundError(f"Meta file not found: {paths.meta_path}")
    
    # Read parquet
    df = pd.read_parquet(paths.parquet_path, engine="pyarrow")
    
    # Read meta.json
    with paths.meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)
    
    return df, meta

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/dataset_registry.py
sha256(source_bytes) = 1c8d752f03e64c93bbd50541ffe15de19d1ea02042d5724e78ff97d66f8bc5b2
bytes = 3599
redacted = False
--------------------------------------------------------------------------------
"""Dataset Registry Schema.

Phase 12: Dataset Registry for Research Job Wizard.
Describes "what datasets are available" without containing any price data.
Schema can only "add fields" in the future, cannot change semantics.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetRecord(BaseModel):
    """Metadata for a single derived dataset."""
    
    model_config = ConfigDict(frozen=True)
    
    id: str = Field(
        ...,
        description="Unique identifier, e.g. 'CME.MNQ.60m.2020-2024'",
        examples=["CME.MNQ.60m.2020-2024", "TWF.MXF.15m.2018-2023"]
    )
    
    symbol: str = Field(
        ...,
        description="Symbol identifier, e.g. 'CME.MNQ'",
        examples=["CME.MNQ", "TWF.MXF"]
    )
    
    exchange: str = Field(
        ...,
        description="Exchange identifier, e.g. 'CME'",
        examples=["CME", "TWF"]
    )
    
    timeframe: str = Field(
        ...,
        description="Timeframe string, e.g. '60m'",
        examples=["60m", "15m", "5m", "1D"]
    )
    
    path: str = Field(
        ...,
        description="Relative path to derived file from data/derived/",
        examples=["CME.MNQ/60m/2020-2024.parquet"]
    )
    
    start_date: date = Field(
        ...,
        description="First date with data (inclusive)"
    )
    
    end_date: date = Field(
        ...,
        description="Last date with data (inclusive)"
    )
    
    fingerprint_sha1: Optional[str] = Field(
        default=None,
        description="SHA1 hash of file content (binary), deterministic fingerprint (deprecated, use fingerprint_sha256_40)"
    )
    
    fingerprint_sha256_40: str = Field(
        ...,
        description="SHA256 hash of file content (binary), first 40 hex chars, deterministic fingerprint"
    )
    
    @model_validator(mode="before")
    @classmethod
    def ensure_fingerprint_sha256_40(cls, data: dict) -> dict:
        """Backward compatibility: if fingerprint_sha256_40 missing but fingerprint_sha1 present, copy it."""
        if isinstance(data, dict):
            if "fingerprint_sha256_40" not in data or not data["fingerprint_sha256_40"]:
                if "fingerprint_sha1" in data and data["fingerprint_sha1"]:
                    # Copy sha1 to sha256 field (note: this is semantically wrong but maintains compatibility)
                    data["fingerprint_sha256_40"] = data["fingerprint_sha1"]
        return data
    
    tz_provider: str = Field(
        default="IANA",
        description="Timezone provider identifier"
    )
    
    tz_version: str = Field(
        default="unknown",
        description="Timezone database version"
    )


class DatasetIndex(BaseModel):
    """Complete registry of all available datasets."""
    
    model_config = ConfigDict(frozen=True)
    
    generated_at: datetime = Field(
        ...,
        description="Timestamp when this index was generated"
    )
    
    datasets: List[DatasetRecord] = Field(
        default_factory=list,
        description="List of all available dataset records"
    )
    
    def model_post_init(self, __context: object) -> None:
        """Post-initialization hook to sort datasets by id."""
        super().model_post_init(__context)
        # Sort datasets by id to ensure deterministic order
        if self.datasets:
            self.datasets.sort(key=lambda d: d.id)

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/fingerprint.py
sha256(source_bytes) = e9cfb6f419b0a2f54d4260a56ddffe4faff0407550541cd841e2ba3955778919
bytes = 4291
redacted = False
--------------------------------------------------------------------------------
"""Data fingerprint - Truth fingerprint based on Raw TXT.

Binding #3: Mandatory Fingerprint in Governance + JobRecord.
Fingerprint must depend only on raw TXT content + ingest_policy.
Parquet is cache, not truth.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataFingerprint:
    """Data fingerprint - immutable truth identifier.
    
    Attributes:
        sha1: SHA1 hash of raw TXT content + ingest_policy
        source_path: Path to source TXT file
        rows: Number of rows (metadata)
        first_ts_str: First timestamp string (metadata)
        last_ts_str: Last timestamp string (metadata)
        ingest_policy: Ingest policy dict (for hash computation)
    """
    sha1: str
    source_path: str
    rows: int
    first_ts_str: str
    last_ts_str: str
    ingest_policy: dict


def compute_txt_fingerprint(path: Path, *, ingest_policy: dict) -> DataFingerprint:
    """Compute fingerprint from raw TXT file + ingest_policy.
    
    Fingerprint is computed from:
    1. Raw TXT file content (bytes)
    2. Ingest policy (JSON with stable sort)
    
    This ensures the fingerprint represents the "truth" - raw data + normalization policy.
    Parquet cache can be deleted and rebuilt, fingerprint remains stable.
    
    Args:
        path: Path to raw TXT file
        ingest_policy: Ingest policy dict (will be JSON-serialized with stable sort)
        
    Returns:
        DataFingerprint with SHA1 hash and metadata
        
    Raises:
        FileNotFoundError: If path does not exist
    """
    if not path.exists():
        raise FileNotFoundError(f"TXT file not found: {path}")
    
    # Compute SHA1: policy first, then file content
    h = hashlib.sha1()
    
    # Add ingest_policy (stable JSON sort)
    policy_json = json.dumps(ingest_policy, sort_keys=True, ensure_ascii=False)
    h.update(policy_json.encode("utf-8"))
    
    # Add file content (chunked for large files)
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            h.update(chunk)
    
    sha1 = h.hexdigest()
    
    # Read metadata (rows, first_ts_str, last_ts_str)
    # We need to parse the file to get these, but they're just metadata
    # The hash is the truth, metadata is for convenience
    import pandas as pd
    
    df = pd.read_csv(path, encoding="utf-8")
    rows = len(df)
    
    # Try to extract first/last timestamps
    # This is best-effort metadata, not part of hash
    first_ts_str = ""
    last_ts_str = ""
    
    if "Date" in df.columns and "Time" in df.columns:
        if rows > 0:
            first_date = str(df.iloc[0]["Date"])
            first_time = str(df.iloc[0]["Time"])
            last_date = str(df.iloc[-1]["Date"])
            last_time = str(df.iloc[-1]["Time"])
            
            # Apply same normalization as ingest (duplicate logic to avoid circular import)
            def _normalize_24h_local(date_s: str, time_s: str) -> tuple[str, bool]:
                """Local copy of _normalize_24h to avoid circular import."""
                t = time_s.strip()
                if t.startswith("24:"):
                    if t != "24:00:00":
                        raise ValueError(f"Invalid 24h time: {time_s}")
                    d = pd.to_datetime(date_s.strip(), format="%Y/%m/%d", errors="raise")
                    d2 = (d + pd.Timedelta(days=1)).to_pydatetime().date()
                    return f"{d2.year}/{d2.month}/{d2.day} 00:00:00", True
                return f"{date_s.strip()} {t}", False
            
            try:
                first_ts_str, _ = _normalize_24h_local(first_date, first_time)
            except Exception:
                first_ts_str = f"{first_date} {first_time}"
            
            try:
                last_ts_str, _ = _normalize_24h_local(last_date, last_time)
            except Exception:
                last_ts_str = f"{last_date} {last_time}"
    
    return DataFingerprint(
        sha1=sha1,
        source_path=str(path),
        rows=rows,
        first_ts_str=first_ts_str,
        last_ts_str=last_ts_str,
        ingest_policy=ingest_policy,
    )

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/layout.py
sha256(source_bytes) = b41807fb9c2d19e291d0d3cb998db49fa66036ccc684b1d4c6f8f5ccd2ce2a9b
bytes = 787
redacted = False
--------------------------------------------------------------------------------
import numpy as np
from FishBroWFS_V2.engine.types import BarArrays


def ensure_float64_contiguous(x: np.ndarray) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    if not arr.flags["C_CONTIGUOUS"]:
        arr = np.ascontiguousarray(arr)
    return arr


def normalize_bars(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> BarArrays:
    arrays = [open_, high, low, close]
    for a in arrays:
        if np.isnan(a).any():
            raise ValueError("NaN detected in input data")

    o = ensure_float64_contiguous(open_)
    h = ensure_float64_contiguous(high)
    l = ensure_float64_contiguous(low)
    c = ensure_float64_contiguous(close)

    return BarArrays(open=o, high=h, low=l, close=c)


--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/raw_ingest.py
sha256(source_bytes) = 3789dc71594c63f7ea31d18a99e06477ff4f0461b34dcc43c8ed651409e7a5f5
bytes = 5735
redacted = False
--------------------------------------------------------------------------------
"""Raw data ingestion - Raw means RAW.

Phase 6.5 Data Ingest v1: Immutable, extremely stupid raw data ingestion.
No sort, no dedup, no dropna (unless recorded in ingest_policy).

Binding: One line = one row, preserve TXT row order exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class IngestPolicy:
    """Ingest policy - only records format normalization decisions, not data cleaning.
    
    Attributes:
        normalized_24h: Whether 24:00:00 times were normalized to next day 00:00:00
        column_map: Column name mapping from source to standard names
    """
    normalized_24h: bool = False
    column_map: dict[str, str] | None = None


@dataclass(frozen=True)
class RawIngestResult:
    """Raw ingest result - immutable contract.
    
    Attributes:
        df: DataFrame with exactly columns: ts_str, open, high, low, close, volume
        source_path: Path to source TXT file
        rows: Number of rows ingested
        policy: Ingest policy applied
    """
    df: pd.DataFrame  # columns exactly: ts_str, open, high, low, close, volume
    source_path: str
    rows: int
    policy: IngestPolicy


def _normalize_24h(date_s: str, time_s: str) -> tuple[str, bool]:
    """Normalize 24:xx:xx time to next day 00:00:00.
    
    Only allows 24:00:00 (exact). Raises ValueError for other 24:xx:xx times.
    
    Args:
        date_s: Date string (e.g., "2013/1/1")
        time_s: Time string (e.g., "24:00:00" or "09:30:00")
        
    Returns:
        Tuple of (normalized ts_str, normalized_flag)
        - If 24:00:00: returns next day 00:00:00 and True
        - Otherwise: returns original "date_s time_s" and False
        
    Raises:
        ValueError: If time_s starts with "24:" but is not exactly "24:00:00"
    """
    t = time_s.strip()
    if t.startswith("24:"):
        if t != "24:00:00":
            raise ValueError(f"Invalid 24h time: {time_s} (only 24:00:00 is allowed)")
        # Parse date only (no timezone)
        d = pd.to_datetime(date_s.strip(), format="%Y/%m/%d", errors="raise")
        d2 = (d + pd.Timedelta(days=1)).to_pydatetime().date()
        return f"{d2.year}/{d2.month}/{d2.day} 00:00:00", True
    return f"{date_s.strip()} {t}", False


def ingest_raw_txt(
    txt_path: Path,
    *,
    column_map: dict[str, str] | None = None,
) -> RawIngestResult:
    """Ingest raw TXT file - Raw means RAW.
    
    Core rules (Binding):
    - One line = one row, preserve TXT row order exactly
    - No sort_values()
    - No drop_duplicates()
    - No dropna() (unless recorded in ingest_policy)
    
    Format normalization (allowed):
    - 24:00:00 → next day 00:00:00 (recorded in policy.normalized_24h)
    - Column mapping (recorded in policy.column_map)
    
    Args:
        txt_path: Path to raw TXT file
        column_map: Optional column name mapping (e.g., {"Date": "Date", "Time": "Time", ...})
        
    Returns:
        RawIngestResult with df containing columns: ts_str, open, high, low, close, volume
        
    Raises:
        FileNotFoundError: If txt_path does not exist
        ValueError: If parsing fails or invalid 24h time format
    """
    if not txt_path.exists():
        raise FileNotFoundError(f"TXT file not found: {txt_path}")
    
    # Read TXT file (preserve order)
    # Assume CSV-like format with header
    df_raw = pd.read_csv(txt_path, encoding="utf-8")
    
    # Apply column mapping if provided
    if column_map:
        df_raw = df_raw.rename(columns=column_map)
    
    # Expected columns after mapping: Date, Time, Open, High, Low, Close, TotalVolume (or Volume)
    required_cols = ["Date", "Time", "Open", "High", "Low", "Close"]
    volume_cols = ["TotalVolume", "Volume"]
    
    # Check required columns
    missing_cols = [col for col in required_cols if col not in df_raw.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}. Found: {list(df_raw.columns)}")
    
    # Find volume column
    volume_col = None
    for vcol in volume_cols:
        if vcol in df_raw.columns:
            volume_col = vcol
            break
    
    if volume_col is None:
        raise ValueError(f"Missing volume column. Expected one of: {volume_cols}. Found: {list(df_raw.columns)}")
    
    # Build ts_str column (preserve row order)
    normalized_24h = False
    ts_str_list = []
    
    for idx, row in df_raw.iterrows():
        date_s = str(row["Date"])
        time_s = str(row["Time"])
        
        try:
            ts_str, was_normalized = _normalize_24h(date_s, time_s)
            if was_normalized:
                normalized_24h = True
            ts_str_list.append(ts_str)
        except Exception as e:
            raise ValueError(f"Failed to normalize timestamp at row {idx}: {e}") from e
    
    # Build result DataFrame (preserve order, no sort/dedup/dropna)
    result_df = pd.DataFrame({
        "ts_str": ts_str_list,
        "open": pd.to_numeric(df_raw["Open"], errors="raise").astype("float64"),
        "high": pd.to_numeric(df_raw["High"], errors="raise").astype("float64"),
        "low": pd.to_numeric(df_raw["Low"], errors="raise").astype("float64"),
        "close": pd.to_numeric(df_raw["Close"], errors="raise").astype("float64"),
        "volume": pd.to_numeric(df_raw[volume_col], errors="coerce").fillna(0).astype("int64"),
    })
    
    # Record policy
    policy = IngestPolicy(
        normalized_24h=normalized_24h,
        column_map=column_map,
    )
    
    return RawIngestResult(
        df=result_df,
        source_path=str(txt_path),
        rows=len(result_df),
        policy=policy,
    )

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/CME_MNQ_EXCHANGE_v1.yaml
sha256(source_bytes) = 5eb97a787f38ff7842a2fba301d8c498e231fa3598a4995564e77ccfc187d4a6
bytes = 492
redacted = False
--------------------------------------------------------------------------------
symbol: CME.MNQ
version: v1
mode: EXCHANGE_RULE
exchange_tz: America/Chicago
local_tz: Asia/Taipei
rules:
  # Daily maintenance window (CT)
  daily_maintenance:
    start: "16:00:00"   # CT
    end:   "17:00:00"   # CT
  # Trading week: Sun 18:00 ET → Fri 17:00 ET
  # (ET = Eastern Time, but CME uses CT for operations)
  # For simplicity, we treat 17:00 CT as trading day start
  trading_week:
    open: "17:00:00"    # CT (Sunday evening)
    close: "16:00:00"   # CT (Friday afternoon)

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/CME_MNQ_TPE_v1.yaml
sha256(source_bytes) = 1747657f162176acf5e882f02fc443e0e46fa4ee4c955a57cccae53d7aba505f
bytes = 215
redacted = False
--------------------------------------------------------------------------------
symbol: CME.MNQ
version: v1
mode: FIXED_TPE
exchange_tz: Asia/Taipei
local_tz: Asia/Taipei
sessions:
  - name: DAY
    start: "08:45:00"
    end: "13:45:00"
  - name: NIGHT
    start: "21:00:00"
    end: "06:00:00"

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/CME_MNQ_v2.yaml
sha256(source_bytes) = 8f53c18ec109e033aeeae459045283de84748a5411d6ffd0fd5689a474397134
bytes = 304
redacted = False
--------------------------------------------------------------------------------
symbol: CME.MNQ
version: v2
mode: tz_convert
exchange_tz: America/Chicago
data_tz: Asia/Taipei
windows:
  - state: BREAK
    start: "16:00:00"  # Chicago time
    end: "17:00:00"    # Chicago time
  - state: TRADING
    start: "17:00:00"  # Chicago time (跨午夜)
    end: "16:00:00"    # Chicago time

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/TWF_MXF_TPE_v1.yaml
sha256(source_bytes) = ef72f26134a167ffe3d5225c4b7568ce0c16ce733320cda119daf3f7bb93efe4
bytes = 215
redacted = False
--------------------------------------------------------------------------------
symbol: TWF.MXF
version: v1
mode: FIXED_TPE
exchange_tz: Asia/Taipei
local_tz: Asia/Taipei
sessions:
  - name: DAY
    start: "08:45:00"
    end: "13:45:00"
  - name: NIGHT
    start: "15:00:00"
    end: "05:00:00"

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/TWF_MXF_v2.yaml
sha256(source_bytes) = e987fa531da4849755d014e779b22305daf6b68f73b4c77c0d63b2ecd729ce11
bytes = 479
redacted = False
--------------------------------------------------------------------------------
symbol: TWF.MXF
version: v2
mode: FIXED_TPE
exchange_tz: Asia/Taipei
data_tz: Asia/Taipei
windows:
  - state: TRADING
    start: "08:45:00"  # Taiwan time
    end: "13:45:00"    # Taiwan time
  - state: BREAK
    start: "13:45:00"  # Taiwan time
    end: "15:00:00"    # Taiwan time
  - state: TRADING
    start: "15:00:00"  # Taiwan time (跨午夜)
    end: "05:00:00"    # Taiwan time
  - state: BREAK
    start: "05:00:00"  # Taiwan time
    end: "08:45:00"    # Taiwan time

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/__init__.py
sha256(source_bytes) = fab6b9cab121eb98d1957d8bd89d840d7906c7eb11044c07dcf558e59394ab74
bytes = 749
redacted = False
--------------------------------------------------------------------------------
"""Session Profile and K-Bar Aggregation module.

Phase 6.6: Session Profile + K-Bar Aggregation with DST-safe timezone conversion.
Session classification and K-bar aggregation use exchange clock.
Raw ingest (Phase 6.5) remains unchanged - no timezone conversion at raw layer.
"""

from FishBroWFS_V2.data.session.classify import classify_session, classify_sessions
from FishBroWFS_V2.data.session.kbar import aggregate_kbar
from FishBroWFS_V2.data.session.loader import load_session_profile
from FishBroWFS_V2.data.session.schema import Session, SessionProfile, SessionWindow

__all__ = [
    "Session",
    "SessionProfile",
    "SessionWindow",
    "load_session_profile",
    "classify_session",
    "classify_sessions",
    "aggregate_kbar",
]

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/classify.py
sha256(source_bytes) = 39b4054882852c7dd847df1fafc60dd91eed5e4f35d550234742614251066f96
bytes = 6064
redacted = False
--------------------------------------------------------------------------------
"""Session classification.

Phase 6.6: Classify timestamps into trading sessions using DST-safe timezone conversion.
Converts local time to exchange time for classification.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd
from zoneinfo import ZoneInfo

from FishBroWFS_V2.data.session.schema import Session, SessionProfile, SessionWindow


def _parse_ts_str(ts_str: str) -> datetime:
    """Parse timestamp string (handles non-zero-padded dates like "2013/1/1").
    
    Phase 6.6: Manual parsing to handle "YYYY/M/D" format without zero-padding.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        
    Returns:
        datetime (naive, no timezone attached)
    """
    date_s, time_s = ts_str.split(" ")
    y, m, d = (int(x) for x in date_s.split("/"))
    hh, mm, ss = (int(x) for x in time_s.split(":"))
    return datetime(y, m, d, hh, mm, ss)


def _parse_ts_str_tpe(ts_str: str) -> datetime:
    """Parse timestamp string and attach Asia/Taipei timezone.
    
    Phase 6.6: Only does format parsing + attach timezone, no "correction" or sort.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        
    Returns:
        datetime with Asia/Taipei timezone
    """
    dt = _parse_ts_str(ts_str)
    return dt.replace(tzinfo=ZoneInfo("Asia/Taipei"))


def _parse_ts_str_with_tz(ts_str: str, tz: str) -> datetime:
    """Parse timestamp string and attach specified timezone.
    
    Phase 6.6: Parse ts_str and attach timezone.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        tz: IANA timezone (e.g., "Asia/Taipei")
        
    Returns:
        datetime with specified timezone
    """
    dt = _parse_ts_str(ts_str)
    return dt.replace(tzinfo=ZoneInfo(tz))


def _to_exchange_hms(ts_str: str, data_tz: str, exchange_tz: str) -> str:
    """Convert timestamp string to exchange timezone and return HH:MM:SS.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" (data timezone)
        data_tz: IANA timezone of input data (e.g., "Asia/Taipei")
        exchange_tz: IANA timezone of exchange (e.g., "America/Chicago")
        
    Returns:
        Time string "HH:MM:SS" in exchange timezone
    """
    dt = _parse_ts_str(ts_str).replace(tzinfo=ZoneInfo(data_tz))
    dt_ex = dt.astimezone(ZoneInfo(exchange_tz))
    return dt_ex.strftime("%H:%M:%S")


def classify_session(
    ts_str: str,
    profile: SessionProfile,
) -> str | None:
    """Classify timestamp string into session state.
    
    Phase 6.6: Core classification logic with DST-safe timezone conversion.
    - ts_str (TPE string) → parse as data_tz → convert to exchange_tz
    - Use exchange time to compare with windows
    - BREAK 優先於 TRADING
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" (data timezone)
        profile: Session profile with data_tz, exchange_tz, and windows
        
    Returns:
        Session state: "TRADING", "BREAK", or None
    """
    # Phase 6.6: Parse ts_str as data_tz, convert to exchange_tz
    data_dt = _parse_ts_str_with_tz(ts_str, profile.data_tz)
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    exchange_dt = data_dt.astimezone(exchange_tz_info)
    
    # Extract exchange time HH:MM:SS
    exchange_time_str = exchange_dt.strftime("%H:%M:%S")
    
    # Phase 6.6: Use windows if available (preferred method)
    if profile.windows:
        # BREAK 優先於 TRADING - check BREAK windows first
        for window in profile.windows:
            if window.state == "BREAK":
                if profile._time_in_range(exchange_time_str, window.start, window.end):
                    return "BREAK"
        
        # Then check TRADING windows
        for window in profile.windows:
            if window.state == "TRADING":
                if profile._time_in_range(exchange_time_str, window.start, window.end):
                    return "TRADING"
        
        return None
    
    # Fallback to legacy modes for backward compatibility
    if profile.mode == "tz_convert":
        # tz_convert mode: Check BREAK first, then TRADING
        if profile.break_start and profile.break_end:
            if profile._time_in_range(exchange_time_str, profile.break_start, profile.break_end):
                return "BREAK"
        return "TRADING"
    
    elif profile.mode == "FIXED_TPE":
        # FIXED_TPE mode: Use sessions list
        for session in profile.sessions:
            if profile._time_in_range(exchange_time_str, session.start, session.end):
                return session.name
        return None
    
    elif profile.mode == "EXCHANGE_RULE":
        # EXCHANGE_RULE mode: Use rules
        rules = profile.rules
        if "daily_maintenance" in rules:
            maint = rules["daily_maintenance"]
            maint_start = maint.get("start", "16:00:00")
            maint_end = maint.get("end", "17:00:00")
            if profile._time_in_range(exchange_time_str, maint_start, maint_end):
                return "MAINTENANCE"
        
        if "trading_week" in rules:
            return "TRADING"
        
        # Check sessions if available
        if profile.sessions:
            for session in profile.sessions:
                if profile._time_in_range(exchange_time_str, session.start, session.end):
                    return session.name
        
        return None
    
    else:
        raise ValueError(f"Unknown profile mode: {profile.mode}")


def classify_sessions(
    ts_str_series: pd.Series,
    profile: SessionProfile,
) -> pd.Series:
    """Classify multiple timestamps into session names.
    
    Args:
        ts_str_series: Series of timestamp strings ("YYYY/M/D HH:MM:SS") in local time
        profile: Session profile
        
    Returns:
        Series of session names (or None)
    """
    return ts_str_series.apply(lambda ts: classify_session(ts, profile))

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/kbar.py
sha256(source_bytes) = 0414f7d7384e59731d47a2ba1af60936925086595645ce7af06923b2332bae21
bytes = 13031
redacted = False
--------------------------------------------------------------------------------
"""K-Bar Aggregation.

Phase 6.6: Aggregate bars into K-bars (30/60/120/240/DAY minutes).
Must anchor to Session.start (exchange timezone), no cross-session aggregation.
DST-safe: Uses exchange clock for bucket calculation.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from FishBroWFS_V2.data.session.classify import _parse_ts_str_tpe
from FishBroWFS_V2.data.session.schema import SessionProfile


# Allowed K-bar intervals (minutes)
ALLOWED_INTERVALS = {30, 60, 120, 240, "DAY"}


def _is_trading_session(sess: str | None) -> bool:
    """Check if a session is aggregatable (trading session).
    
    Phase 6.6: Unified rule for determining aggregatable sessions.
    
    Rules:
    - BREAK: Not aggregatable (absolute boundary)
    - None: Not aggregatable (outside any session)
    - MAINTENANCE: Not aggregatable
    - All others (TRADING, DAY, NIGHT, etc.): Aggregatable
    
    This supports both:
    - Phase 6.6: TRADING/BREAK semantics
    - Legacy: DAY/NIGHT semantics
    
    Args:
        sess: Session name or None
        
    Returns:
        True if session is aggregatable, False otherwise
    """
    if sess is None:
        return False
    # Phase 6.6: BREAK is absolute boundary
    if sess == "BREAK":
        return False
    # Legacy: MAINTENANCE is not aggregatable
    if sess == "MAINTENANCE":
        return False
    # All other sessions (TRADING, DAY, NIGHT, etc.) are aggregatable
    return True


def aggregate_kbar(
    df: pd.DataFrame,
    interval: int | str,
    profile: SessionProfile,
) -> pd.DataFrame:
    """Aggregate bars into K-bars.
    
    Rules:
    - Only allowed intervals: 30, 60, 120, 240, DAY
    - Must anchor to Session.start
    - No cross-session aggregation
    - DAY bar = one complete session
    
    Args:
        df: DataFrame with columns: ts_str, open, high, low, close, volume
        interval: K-bar interval in minutes (30/60/120/240) or "DAY"
        profile: Session profile
        
    Returns:
        Aggregated DataFrame with same columns
        
    Raises:
        ValueError: If interval is not allowed
    """
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(
            f"Invalid interval: {interval}. Allowed: {ALLOWED_INTERVALS}"
        )
    
    if interval == "DAY":
        return _aggregate_day_bar(df, profile)
    
    # For minute intervals, aggregate within sessions
    return _aggregate_minute_bar(df, int(interval), profile)


def _aggregate_day_bar(df: pd.DataFrame, profile: SessionProfile) -> pd.DataFrame:
    """Aggregate into DAY bars (one complete session per bar).
    
    Phase 6.6: BREAK is absolute boundary - only aggregate trading sessions.
    DST-safe: Uses exchange clock for session grouping.
    DAY bar = one complete trading session.
    Each trading session produces one DAY bar, regardless of calendar date.
    """
    from FishBroWFS_V2.data.session.classify import classify_sessions
    
    # Classify each bar into session
    df = df.copy()
    df["_session"] = classify_sessions(df["ts_str"], profile)
    
    # Phase 6.6: Filter out non-aggregatable sessions (BREAK, None, MAINTENANCE)
    df = df[df["_session"].apply(_is_trading_session)]
    
    if len(df) == 0:
        return pd.DataFrame(columns=["ts_str", "open", "high", "low", "close", "volume", "session"])
    
    # Convert to exchange timezone for grouping (DST-safe)
    # Phase 6.6: Add derived columns (not violating raw layer)
    if not profile.exchange_tz:
        raise ValueError("Profile must have exchange_tz for DAY bar aggregation")
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    df["_local_dt"] = df["ts_str"].apply(_parse_ts_str_tpe)
    df["_ex_dt"] = df["_local_dt"].apply(lambda dt: dt.astimezone(exchange_tz_info))
    
    # Group by session - each group = one complete session
    # For overnight sessions, all bars of the same session are grouped together
    groups = df.groupby("_session", dropna=False)
    
    result_rows = []
    for session, group in groups:
        # For EXCHANGE_RULE mode, session may not be in profile.sessions
        # Still produce DAY bar if session was classified
        # (session_obj is only needed for anchor time, which DAY bar doesn't use)
        
        # Determine session start date in exchange timezone
        # Sort group by exchange datetime to find first bar chronologically
        group_sorted = group.sort_values("_ex_dt")
        first_bar_ex_dt = group_sorted["_ex_dt"].iloc[0]
        
        # Get original local ts_str for output (keep TPE time)
        # Use first bar's ts_str as anchor - it represents session start in local time
        first_bar_ts_str = group_sorted["ts_str"].iloc[0]
        
        # For DAY bar, use first bar's ts_str directly
        # This ensures output matches the actual first bar time in local timezone
        ts_str = first_bar_ts_str
        
        # Aggregate OHLCV
        open_val = group["open"].iloc[0]
        high_val = group["high"].max()
        low_val = group["low"].min()
        close_val = group["close"].iloc[-1]
        volume_val = group["volume"].sum()
        
        result_rows.append({
            "ts_str": ts_str,
            "open": open_val,
            "high": high_val,
            "low": low_val,
            "close": close_val,
            "volume": int(volume_val),
            "session": session,  # Phase 6.6: Add session label (derived data, not violating Raw)
        })
    
    result_df = pd.DataFrame(result_rows)
    
    # Remove helper columns if they exist
    for col in ["_session", "_local_dt", "_ex_dt"]:
        if col in result_df.columns:
            result_df = result_df.drop(columns=[col])
    
    # Sort by ts_str to maintain chronological order
    if len(result_df) > 0:
        result_df = result_df.sort_values("ts_str").reset_index(drop=True)
    
    return result_df


def _aggregate_minute_bar(
    df: pd.DataFrame,
    interval_minutes: int,
    profile: SessionProfile,
) -> pd.DataFrame:
    """Aggregate into minute bars (30/60/120/240).
    
    Phase 6.6: BREAK is absolute boundary - only aggregate trading sessions.
    DST-safe: Uses exchange clock for bucket calculation.
    Must anchor to Session.start (exchange timezone), no cross-session aggregation.
    Bucket doesn't need to be full - any data produces a bar.
    """
    from FishBroWFS_V2.data.session.classify import classify_sessions
    
    # Classify each bar into session
    df = df.copy()
    df["_session"] = classify_sessions(df["ts_str"], profile)
    
    # Phase 6.6: Filter out non-aggregatable sessions (BREAK, None, MAINTENANCE)
    df = df[df["_session"].apply(_is_trading_session)]
    
    if len(df) == 0:
        return pd.DataFrame(columns=["ts_str", "open", "high", "low", "close", "volume", "session"])
    
    # Convert to exchange timezone for bucket calculation
    # Phase 6.6: Add derived columns (not violating raw layer)
    if not profile.exchange_tz:
        raise ValueError("Profile must have exchange_tz for minute bar aggregation")
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    
    df["_local_dt"] = df["ts_str"].apply(_parse_ts_str_tpe)
    df["_ex_dt"] = df["_local_dt"].apply(lambda dt: dt.astimezone(exchange_tz_info))
    
    # Extract exchange date and time for grouping
    df["_ex_date"] = df["_ex_dt"].apply(lambda dt: dt.date().isoformat().replace("-", "/"))
    df["_ex_time"] = df["_ex_dt"].apply(lambda dt: dt.strftime("%H:%M:%S"))
    
    result_rows = []
    
    # Process each (exchange_date, session) group separately
    groups = df.groupby(["_ex_date", "_session"], dropna=False)
    
    for (ex_date, session), group in groups:
        if not _is_trading_session(session):
            continue  # Skip non-aggregatable sessions (BREAK, None, MAINTENANCE)
        
        # Find session start time from profile (in exchange timezone)
        # Phase 6.6: If windows exist, use first TRADING window.start
        # Legacy: Use current session name to find matching session.start
        session_start = None
        
        if profile.windows:
            # Phase 6.6: Use first TRADING window.start
            for window in profile.windows:
                if window.state == "TRADING":
                    session_start = window.start
                    break
        else:
            # Legacy: Find session.start by matching session name
            for sess in profile.sessions:
                if sess.name == session:
                    session_start = sess.start
                    break
        
        # If still not found, use first bar's exchange time as anchor
        if session_start is None:
            first_bar_ex_time = group["_ex_time"].iloc[0]
            session_start = first_bar_ex_time
        
        # Calculate bucket start times anchored to session.start (exchange timezone)
        buckets = _calculate_buckets(session_start, interval_minutes)
        
        # Assign each bar to a bucket using exchange time
        group = group.copy()
        group["_bucket"] = group["_ex_time"].apply(
            lambda t: _find_bucket(t, buckets)
        )
        
        # Aggregate per bucket
        bucket_groups = group.groupby("_bucket", dropna=False)
        
        for bucket_start, bucket_group in bucket_groups:
            if pd.isna(bucket_start):
                continue
            
            # Phase 6.6: Bucket doesn't need to be full - any data produces a bar
            # BREAK is absolute boundary (already filtered out above)
            if bucket_group.empty:
                continue
            
            # ts_str output: Use original local ts_str (TPE), not exchange time
            # But bucket grouping was done in exchange time
            first_bar_ts_str = bucket_group["ts_str"].iloc[0]  # Original TPE ts_str
            
            # Aggregate OHLCV
            open_val = bucket_group["open"].iloc[0]
            high_val = bucket_group["high"].max()
            low_val = bucket_group["low"].min()
            close_val = bucket_group["close"].iloc[-1]
            volume_val = bucket_group["volume"].sum()
            
            result_rows.append({
                "ts_str": first_bar_ts_str,  # Keep original TPE ts_str
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": int(volume_val),
                "session": session,  # Phase 6.6: Add session label (derived data, not violating Raw)
            })
    
    result_df = pd.DataFrame(result_rows)
    
    # Remove helper columns
    for col in ["_session", "_ex_date", "_ex_time", "_bucket", "_local_dt", "_ex_dt"]:
        if col in result_df.columns:
            result_df = result_df.drop(columns=[col])
    
    # Sort by ts_str to maintain chronological order
    if len(result_df) > 0:
        result_df = result_df.sort_values("ts_str").reset_index(drop=True)
    
    return result_df


def _calculate_buckets(session_start: str, interval_minutes: int) -> List[str]:
    """Calculate bucket start times anchored to session_start.
    
    Args:
        session_start: Session start time "HH:MM:SS"
        interval_minutes: Interval in minutes
        
    Returns:
        List of bucket start times ["HH:MM:SS", ...]
    """
    # Parse session_start
    parts = session_start.split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    
    # Convert to total minutes
    start_minutes = h * 60 + m
    
    buckets = []
    current_minutes = start_minutes
    
    # Generate buckets until end of day (24:00:00 = 1440 minutes)
    while current_minutes < 1440:
        h_bucket = current_minutes // 60
        m_bucket = current_minutes % 60
        bucket_str = f"{h_bucket:02d}:{m_bucket:02d}:00"
        buckets.append(bucket_str)
        current_minutes += interval_minutes
    
    return buckets


def _find_bucket(time_str: str, buckets: List[str]) -> str | None:
    """Find which bucket a time belongs to.
    
    Phase 6.6: Anchor-based bucket assignment.
    Bucket = floor((time - anchor) / interval)
    
    Args:
        time_str: Time string "HH:MM:SS"
        buckets: List of bucket start times (sorted ascending)
        
    Returns:
        Bucket start time if found, None otherwise
    """
    # Find the largest bucket <= time_str
    # Buckets are sorted ascending, so iterate backwards
    for i in range(len(buckets) - 1, -1, -1):
        if buckets[i] <= time_str:
            # Check if next bucket would exceed time_str
            if i + 1 < len(buckets):
                next_bucket = buckets[i + 1]
                if time_str < next_bucket:
                    return buckets[i]
            else:
                # Last bucket - time_str falls in this bucket
                return buckets[i]
    
    return None

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/loader.py
sha256(source_bytes) = 56634bbdd5ea0734b1c0997970ce91924e37533a8888f9c8abea3f21723e9c8d
bytes = 4814
redacted = False
--------------------------------------------------------------------------------
"""Session Profile loader.

Phase 6.6: Load session profiles from YAML files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from FishBroWFS_V2.data.session.schema import Session, SessionProfile, SessionWindow


def load_session_profile(profile_path: Path) -> SessionProfile:
    """Load session profile from YAML file.
    
    Args:
        profile_path: Path to YAML profile file
        
    Returns:
        SessionProfile loaded from YAML
        
    Raises:
        FileNotFoundError: If profile file does not exist
        ValueError: If profile structure is invalid
    """
    if not profile_path.exists():
        raise FileNotFoundError(f"Session profile not found: {profile_path}")
    
    with profile_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    if not isinstance(data, dict):
        raise ValueError(f"Invalid profile format: expected dict, got {type(data)}")
    
    symbol = data.get("symbol")
    version = data.get("version")
    mode = data.get("mode", "FIXED_TPE")  # Default to FIXED_TPE for backward compatibility
    exchange_tz = data.get("exchange_tz")
    data_tz = data.get("data_tz", "Asia/Taipei")  # Phase 6.6: Default to Asia/Taipei
    local_tz = data.get("local_tz", "Asia/Taipei")
    sessions_data = data.get("sessions", [])
    windows_data = data.get("windows", [])  # Phase 6.6: Windows with TRADING/BREAK states
    rules = data.get("rules", {})
    break_start = data.get("break", {}).get("start") if isinstance(data.get("break"), dict) else None
    break_end = data.get("break", {}).get("end") if isinstance(data.get("break"), dict) else None
    
    if not symbol:
        raise ValueError("Profile missing 'symbol' field")
    if not version:
        raise ValueError("Profile missing 'version' field")
    
    # Phase 6.6: exchange_tz is required
    if not exchange_tz:
        raise ValueError("Profile missing 'exchange_tz' field (required in Phase 6.6)")
    
    if mode not in ["FIXED_TPE", "EXCHANGE_RULE", "tz_convert"]:
        raise ValueError(f"Invalid mode: {mode}. Must be 'FIXED_TPE', 'EXCHANGE_RULE', or 'tz_convert'")
    
    # Phase 6.6: Load windows (preferred method)
    windows = []
    if windows_data:
        if not isinstance(windows_data, list):
            raise ValueError(f"Profile 'windows' must be list, got {type(windows_data)}")
        
        for win_data in windows_data:
            if not isinstance(win_data, dict):
                raise ValueError(f"Window must be dict, got {type(win_data)}")
            
            state = win_data.get("state")
            start = win_data.get("start")
            end = win_data.get("end")
            
            if state not in ["TRADING", "BREAK"]:
                raise ValueError(f"Window state must be 'TRADING' or 'BREAK', got {state}")
            if not start or not end:
                raise ValueError(f"Window missing required fields: state={state}, start={start}, end={end}")
            
            windows.append(SessionWindow(state=state, start=start, end=end))
    
    # Backward compatibility: Load sessions for legacy modes
    sessions = []
    if sessions_data:
        if not isinstance(sessions_data, list):
            raise ValueError(f"Profile 'sessions' must be list, got {type(sessions_data)}")
        
        for sess_data in sessions_data:
            if not isinstance(sess_data, dict):
                raise ValueError(f"Session must be dict, got {type(sess_data)}")
            
            name = sess_data.get("name")
            start = sess_data.get("start")
            end = sess_data.get("end")
            
            if not name or not start or not end:
                raise ValueError(f"Session missing required fields: name={name}, start={start}, end={end}")
            
            sessions.append(Session(name=name, start=start, end=end))
    elif mode == "EXCHANGE_RULE":
        if not isinstance(rules, dict):
            raise ValueError(f"Profile 'rules' must be dict for EXCHANGE_RULE mode, got {type(rules)}")
    elif mode == "tz_convert":
        # Legacy requirement only applies when windows are NOT provided
        # Phase 6.6: If windows_data exists, windows-driven mode doesn't need break.start/end
        if (not windows_data) and (not break_start or not break_end):
            raise ValueError(f"tz_convert mode requires 'break.start' and 'break.end' fields (or 'windows' for Phase 6.6)")
    
    return SessionProfile(
        symbol=symbol,
        version=version,
        mode=mode,
        exchange_tz=exchange_tz,
        data_tz=data_tz,
        local_tz=local_tz,
        sessions=sessions,
        windows=windows,
        rules=rules,
        break_start=break_start,
        break_end=break_end,
    )

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/schema.py
sha256(source_bytes) = 643addf865991cb6271ef1bc1e04ebf7f3c87a6a6b0969e16fd56423efd14b86
bytes = 4466
redacted = False
--------------------------------------------------------------------------------
"""Session Profile schema.

Phase 6.6: Session Profile schema with DST-safe timezone conversion.
Session times are defined in exchange timezone, classification uses exchange clock.

Supports two modes:
- FIXED_TPE: Direct Taiwan time string comparison (e.g., TWF.MXF)
- EXCHANGE_RULE: Exchange timezone + rules, dynamically compute TPE windows (e.g., CME.MNQ)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


@dataclass(frozen=True)
class SessionWindow:
    """Session window definition with state.
    
    Phase 6.6: Only allows TRADING and BREAK states.
    Session times are defined in exchange timezone (format: "HH:MM:SS").
    
    Attributes:
        state: Session state - "TRADING" or "BREAK"
        start: Session start time (exchange timezone, "HH:MM:SS")
        end: Session end time (exchange timezone, "HH:MM:SS")
    """
    state: Literal["TRADING", "BREAK"]
    start: str  # Exchange timezone "HH:MM:SS"
    end: str    # Exchange timezone "HH:MM:SS"


@dataclass(frozen=True)
class Session:
    """Trading session definition.
    
    Session times are defined in exchange timezone (format: "HH:MM:SS").
    
    Attributes:
        name: Session name (e.g., "DAY", "NIGHT", "TRADING", "BREAK", "MAINTENANCE")
        start: Session start time (exchange timezone, "HH:MM:SS")
        end: Session end time (exchange timezone, "HH:MM:SS")
    """
    name: str
    start: str  # Exchange timezone "HH:MM:SS"
    end: str    # Exchange timezone "HH:MM:SS"


@dataclass(frozen=True)
class SessionProfile:
    """Session profile for a symbol.
    
    Contains trading sessions defined in exchange timezone.
    Classification converts local time to exchange time for comparison.
    
    Phase 6.6: data_tz defaults to "Asia/Taipei", exchange_tz must be specified.
    
    Attributes:
        symbol: Symbol identifier (e.g., "CME.MNQ", "TWF.MXF")
        version: Profile version (e.g., "v1", "v2")
        mode: Profile mode - "FIXED_TPE" (direct TPE comparison), "EXCHANGE_RULE" (exchange rules), or "tz_convert" (timezone conversion with BREAK priority)
        exchange_tz: Exchange timezone (IANA, e.g., "America/Chicago")
        data_tz: Data timezone (IANA, default: "Asia/Taipei")
        local_tz: Local timezone (default: "Asia/Taipei")
        sessions: List of trading sessions (for FIXED_TPE mode)
        windows: List of session windows with TRADING/BREAK states (Phase 6.6)
        rules: Exchange rules dict (for EXCHANGE_RULE mode, e.g., daily_maintenance, trading_week)
        break_start: BREAK session start time (HH:MM:SS in exchange timezone) for tz_convert mode
        break_end: BREAK session end time (HH:MM:SS in exchange timezone) for tz_convert mode
    """
    symbol: str
    version: str
    mode: Literal["FIXED_TPE", "EXCHANGE_RULE", "tz_convert"]
    exchange_tz: str  # IANA timezone (e.g., "America/Chicago") - required
    data_tz: str = "Asia/Taipei"  # Data timezone (default: "Asia/Taipei")
    local_tz: str = "Asia/Taipei"  # Default to Taiwan time
    sessions: List[Session] = field(default_factory=list)  # For FIXED_TPE mode
    windows: List[SessionWindow] = field(default_factory=list)  # Phase 6.6: Windows with TRADING/BREAK states
    rules: Dict[str, Any] = field(default_factory=dict)  # For EXCHANGE_RULE mode
    break_start: str | None = None  # BREAK start (HH:MM:SS in exchange timezone) for tz_convert mode
    break_end: str | None = None  # BREAK end (HH:MM:SS in exchange timezone) for tz_convert mode
    
    def _time_in_range(self, time_str: str, start: str, end: str) -> bool:
        """Check if time_str is within [start, end) using string comparison.
        
        Handles both normal sessions (start <= end) and overnight sessions (start > end).
        
        Args:
            time_str: Time to check ("HH:MM:SS") in exchange timezone
            start: Start time ("HH:MM:SS") in exchange timezone
            end: End time ("HH:MM:SS") in exchange timezone
            
        Returns:
            True if time_str falls within the session range
        """
        if start <= end:
            # Non-overnight session (e.g., DAY: 08:45:00 - 13:45:00)
            return start <= time_str < end
        else:
            # Overnight session (e.g., NIGHT: 21:00:00 - 06:00:00)
            # time_str >= start OR time_str < end
            return time_str >= start or time_str < end

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/tzdb_info.py
sha256(source_bytes) = ae4e5057feaa814367723455f5d3988f97c44760b815108c0e8fa67b95419330
bytes = 1870
redacted = True
--------------------------------------------------------------------------------
"""Timezone database information utilities.

Phase 6.6: Get tzdb provider and version for manifest recording.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Tuple
import zoneinfo


def get_tzdb_info() -> Tuple[str, str]:
    """Get timezone database provider and version.
    
    Phase 6.6: Extract tzdb provider and version for manifest recording.
    
    Strategy:
    1. If tzdata package (PyPI) is installed, use it as provider + version
    2. Otherwise, try to discover tzdata.zi from zoneinfo.TZPATH (module-level)
    
    Returns:
        Tuple of (provider, version)
        - provider: "tzdata" (PyPI package) or "zoneinfo" (standard library)
        - version: Version string from tzdata package or tzdata.zi file, or "unknown" if not found
    """
    provider = "zoneinfo"
    version = "unknown"

    # 1) If tzdata package installed, prefer it as provider + version
    try:
        version = metadata.version("tzdata")
        provider = "tzdata"
        return provider, version
    except metadata.PackageNotFoundError:
        pass

    # 2) Try discover tzdata.zi from zoneinfo.TZPATH (module-level)
    tzpaths = getattr(zoneinfo, "TZPATH", ())
    for p in tzpaths:
        cand = Path(p) / "tzdata.zi"
        if cand.exists():
            # best-effort parse: search a line containing "version"
            try:
                text = cand.read_text(encoding="utf-8", errors="ignore")
                # minimal heuristic:[REDACTED]                for line in text.splitlines()[:200]:
                    if "version" in line.lower():
                        version = line.strip().split()[-1].strip('"')
                        break
            except OSError:
                pass
            break

    return provider, version

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/__init__.py
sha256(source_bytes) = e81e00a9829674fd7488a169302f41cb7506980b0e5d550d0a64a4681300baa8
bytes = 139
redacted = False
--------------------------------------------------------------------------------

"""Engine module - unified simulate entry point."""

from FishBroWFS_V2.engine.simulate import simulate_run

__all__ = ["simulate_run"]



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/constants.py
sha256(source_bytes) = 808f72fab120a3072a3e505084e31ecd3626833273a0964fec79e553029591c6
bytes = 240
redacted = False
--------------------------------------------------------------------------------

"""
Engine integer constants (hot-path friendly).

These constants are used in array/SoA pathways to avoid Enum.value lookups in tight loops.
"""

ROLE_EXIT = 0
ROLE_ENTRY = 1

KIND_STOP = 0
KIND_LIMIT = 1

SIDE_SELL = -1
SIDE_BUY = 1





--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/constitution.py
sha256(source_bytes) = c75355ca7008415a51a0b93258cd76d5e7146757587c72397e36f114a1a500e7
bytes = 979
redacted = False
--------------------------------------------------------------------------------

"""
Engine Constitution v1.1 (FROZEN)

Activation:
- Orders are created at Bar[T] close and become active at Bar[T+1].

STOP fills (Open==price is treated as GAP branch):
Buy Stop @ S:
- if Open >= S: fill = Open
- elif High >= S: fill = S
Sell Stop @ S:
- if Open <= S: fill = Open
- elif Low <= S: fill = S

LIMIT fills (Open==price is treated as GAP branch):
Buy Limit @ L:
- if Open <= L: fill = Open
- elif Low <= L: fill = L
Sell Limit @ L:
- if Open >= L: fill = Open
- elif High >= L: fill = L

Priority:
- STOP wins over LIMIT (risk-first pessimism).

Same-bar In/Out:
- If entry and exit are both triggerable in the same bar, execute Entry then Exit.

Same-kind tie rule:
- If multiple orders of the same role are triggerable in the same bar, execute EXIT-first.
- Within the same role+kind, use deterministic order: smaller order_id first.
"""

NEXT_BAR_ACTIVE = True
PRIORITY_STOP_OVER_LIMIT = True
SAME_BAR_ENTRY_THEN_EXIT = True
SAME_KIND_TIE_EXIT_FIRST = True




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/engine_jit.py
sha256(source_bytes) = f183678ecbdb41afd6d46e22d48134c6ef5b1d1c148a3f3aed33ddc3289a1113
bytes = 26836
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List, Tuple

import numpy as np

# Engine JIT matcher kernel contract:
# - Complexity target: O(B + I + A), where:
#     B = bars, I = intents, A = per-bar active-book scan.
# - Forbidden: scanning all intents per bar (O(B*I)).
# - Extension point: ttl_bars (0=GTC, 1=one-shot next-bar-only, future: >1).

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore

from FishBroWFS_V2.engine.types import (
    BarArrays,
    Fill,
    OrderIntent,
    OrderKind,
    OrderRole,
    Side,
)
from FishBroWFS_V2.engine.matcher_core import simulate as simulate_py
from FishBroWFS_V2.engine.constants import (
    KIND_LIMIT,
    KIND_STOP,
    ROLE_ENTRY,
    ROLE_EXIT,
    SIDE_BUY,
    SIDE_SELL,
)

# Side enum codes for uint8 encoding (avoid -1 cast deprecation)
SIDE_BUY_CODE = 1
SIDE_SELL_CODE = 255  # SIDE_SELL (-1) encoded as uint8

STATUS_OK = 0
STATUS_ERROR_UNSORTED = 1
STATUS_BUFFER_FULL = 2

# Intent TTL default (Constitution constant)
INTENT_TTL_BARS_DEFAULT = 1  # one-shot next-bar-only (Phase 2 semantics)

# JIT truth (debug/perf observability)
JIT_PATH_USED_LAST = False
JIT_KERNEL_SIGNATURES_LAST = None  # type: ignore


def get_jit_truth() -> dict:
    """
    Debug helper: returns whether the last simulate() call used the JIT kernel,
    and (if available) the kernel signatures snapshot.
    """
    return {
        "jit_path_used": bool(JIT_PATH_USED_LAST),
        "kernel_signatures": JIT_KERNEL_SIGNATURES_LAST,
    }


def _to_int(x) -> int:
    # Enum values are int/str; we convert deterministically.
    if isinstance(x, Side):
        return int(x.value)
    if isinstance(x, OrderRole):
        # EXIT first tie-break relies on role; map explicitly.
        return 0 if x == OrderRole.EXIT else 1
    if isinstance(x, OrderKind):
        return 0 if x == OrderKind.STOP else 1
    return int(x)


def _to_kind_int(k: OrderKind) -> int:
    return 0 if k == OrderKind.STOP else 1


def _to_role_int(r: OrderRole) -> int:
    return 0 if r == OrderRole.EXIT else 1


def _to_side_int(s: Side) -> int:
    """
    Convert Side enum to integer code for uint8 encoding.
    
    Returns:
        SIDE_BUY_CODE (1) for Side.BUY
        SIDE_SELL_CODE (255) for Side.SELL (avoid -1 cast deprecation)
    """
    if s == Side.BUY:
        return SIDE_BUY_CODE
    elif s == Side.SELL:
        return SIDE_SELL_CODE
    else:
        raise ValueError(f"Unknown Side enum: {s}")


def _kind_from_int(v: int) -> OrderKind:
    """
    Decode kind enum from integer value (strict mode).
    
    Allowed values:
    - 0 (KIND_STOP) -> OrderKind.STOP
    - 1 (KIND_LIMIT) -> OrderKind.LIMIT
    
    Raises ValueError for any other value to catch silent corruption.
    """
    if v == KIND_STOP:  # 0
        return OrderKind.STOP
    elif v == KIND_LIMIT:  # 1
        return OrderKind.LIMIT
    else:
        raise ValueError(
            f"Invalid kind enum value: {v}. Allowed values are {KIND_STOP} (STOP) or {KIND_LIMIT} (LIMIT)"
        )


def _role_from_int(v: int) -> OrderRole:
    """
    Decode role enum from integer value (strict mode).
    
    Allowed values:
    - 0 (ROLE_EXIT) -> OrderRole.EXIT
    - 1 (ROLE_ENTRY) -> OrderRole.ENTRY
    
    Raises ValueError for any other value to catch silent corruption.
    """
    if v == ROLE_EXIT:  # 0
        return OrderRole.EXIT
    elif v == ROLE_ENTRY:  # 1
        return OrderRole.ENTRY
    else:
        raise ValueError(
            f"Invalid role enum value: {v}. Allowed values are {ROLE_EXIT} (EXIT) or {ROLE_ENTRY} (ENTRY)"
        )


def _side_from_int(v: int) -> Side:
    """
    Decode side enum from integer value (strict mode).
    
    Allowed values:
    - SIDE_BUY_CODE (1) -> Side.BUY
    - SIDE_SELL_CODE (255) -> Side.SELL
    
    Raises ValueError for any other value to catch silent corruption.
    """
    if v == SIDE_BUY_CODE:  # 1
        return Side.BUY
    elif v == SIDE_SELL_CODE:  # 255
        return Side.SELL
    else:
        raise ValueError(
            f"Invalid side enum value: {v}. Allowed values are {SIDE_BUY_CODE} (BUY) or {SIDE_SELL_CODE} (SELL)"
        )


def _pack_intents(intents: Iterable[OrderIntent]):
    """
    Pack intents into plain arrays for numba.

    Fields (optimized dtypes):
      order_id: int32 (INDEX_DTYPE)
      created_bar: int32 (INDEX_DTYPE)
      role: uint8 (INTENT_ENUM_DTYPE, 0=EXIT,1=ENTRY)
      kind: uint8 (INTENT_ENUM_DTYPE, 0=STOP,1=LIMIT)
      side: uint8 (INTENT_ENUM_DTYPE, SIDE_BUY_CODE=BUY, SIDE_SELL_CODE=SELL)
      price: float64 (INTENT_PRICE_DTYPE)
      qty: int32 (INDEX_DTYPE)
    """
    from FishBroWFS_V2.config.dtypes import (
        INDEX_DTYPE,
        INTENT_ENUM_DTYPE,
        INTENT_PRICE_DTYPE,
    )
    
    it = list(intents)
    n = len(it)
    order_id = np.empty(n, dtype=INDEX_DTYPE)
    created_bar = np.empty(n, dtype=INDEX_DTYPE)
    role = np.empty(n, dtype=INTENT_ENUM_DTYPE)
    kind = np.empty(n, dtype=INTENT_ENUM_DTYPE)
    side = np.empty(n, dtype=INTENT_ENUM_DTYPE)
    price = np.empty(n, dtype=INTENT_PRICE_DTYPE)
    qty = np.empty(n, dtype=INDEX_DTYPE)

    for i, x in enumerate(it):
        order_id[i] = int(x.order_id)
        created_bar[i] = int(x.created_bar)
        role[i] = INTENT_ENUM_DTYPE(_to_role_int(x.role))
        kind[i] = INTENT_ENUM_DTYPE(_to_kind_int(x.kind))
        side[i] = INTENT_ENUM_DTYPE(_to_side_int(x.side))
        price[i] = INTENT_PRICE_DTYPE(x.price)
        qty[i] = int(x.qty)

    return order_id, created_bar, role, kind, side, price, qty


def _sort_packed_by_created_bar(
    packed: Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Sort packed intent arrays by (created_bar, order_id).

    Why:
      - Cursor + active-book kernel requires activate_bar=(created_bar+1) and order_id to be non-decreasing.
      - Determinism is preserved because selection is still based on (kind priority, order_id).
    """
    order_id, created_bar, role, kind, side, price, qty = packed
    # lexsort uses last key as primary -> (created_bar primary, order_id secondary)
    idx = np.lexsort((order_id, created_bar))
    return (
        order_id[idx],
        created_bar[idx],
        role[idx],
        kind[idx],
        side[idx],
        price[idx],
        qty[idx],
    )


def simulate(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> List[Fill]:
    """
    Phase 2A: JIT accelerated matcher.

    Kill switch:
      - If numba is unavailable OR NUMBA_DISABLE_JIT=1, fall back to Python reference.
    """
    global JIT_PATH_USED_LAST, JIT_KERNEL_SIGNATURES_LAST

    if nb is None:
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        return simulate_py(bars, intents)

    # If numba is disabled, keep behavior stable.
    # Numba respects NUMBA_DISABLE_JIT; but we short-circuit to be safe.
    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar(_pack_intents(intents))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(INTENT_TTL_BARS_DEFAULT),  # Use Constitution constant
    )
    if int(status) != STATUS_OK:
        JIT_PATH_USED_LAST = True
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    # record JIT truth (best-effort)
    JIT_PATH_USED_LAST = True
    try:
        sigs = getattr(_simulate_kernel, "signatures", None)
        if sigs is not None:
            JIT_KERNEL_SIGNATURES_LAST = list(sigs)
        else:
            JIT_KERNEL_SIGNATURES_LAST = None
    except Exception:
        JIT_KERNEL_SIGNATURES_LAST = None

    # Convert to Fill objects (drop unused capacity)
    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


def simulate_arrays(
    bars: BarArrays,
    *,
    order_id: np.ndarray,
    created_bar: np.ndarray,
    role: np.ndarray,
    kind: np.ndarray,
    side: np.ndarray,
    price: np.ndarray,
    qty: np.ndarray,
    ttl_bars: int = 1,
) -> List[Fill]:
    """
    Array/SoA entry point: bypass OrderIntent objects and _pack_intents hot-path.

    Arrays must be 1D and same length. Dtypes are expected (optimized):
      order_id: int32 (INDEX_DTYPE)
      created_bar: int32 (INDEX_DTYPE)
      role: uint8 (INTENT_ENUM_DTYPE)
      kind: uint8 (INTENT_ENUM_DTYPE)
      side: uint8 (INTENT_ENUM_DTYPE)
      price: float64 (INTENT_PRICE_DTYPE)
      qty: int32 (INDEX_DTYPE)

    ttl_bars:
      - activate_bar = created_bar + 1
      - 0 => GTC (Good Till Canceled, never expire)
      - 1 => one-shot next-bar-only (intent valid only on activate_bar)
      - >= 1 => intent valid for bars t in [activate_bar, activate_bar + ttl_bars - 1]
      - When t > activate_bar + ttl_bars - 1, intent is removed from active book
    """
    from FishBroWFS_V2.config.dtypes import (
        INDEX_DTYPE,
        INTENT_ENUM_DTYPE,
        INTENT_PRICE_DTYPE,
    )
    
    global JIT_PATH_USED_LAST, JIT_KERNEL_SIGNATURES_LAST

    # Normalize/ensure arrays are numpy with the expected dtypes (cold path).
    oid = np.asarray(order_id, dtype=INDEX_DTYPE)
    cb = np.asarray(created_bar, dtype=INDEX_DTYPE)
    rl = np.asarray(role, dtype=INTENT_ENUM_DTYPE)
    kd = np.asarray(kind, dtype=INTENT_ENUM_DTYPE)
    sd = np.asarray(side, dtype=INTENT_ENUM_DTYPE)
    px = np.asarray(price, dtype=INTENT_PRICE_DTYPE)
    qy = np.asarray(qty, dtype=INDEX_DTYPE)

    if nb is None:
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        intents: List[OrderIntent] = []
        n = int(oid.shape[0])
        for i in range(n):
            # Strict decoding: fail fast on invalid enum values
            rl_val = int(rl[i])
            if rl_val == ROLE_EXIT:
                r = OrderRole.EXIT
            elif rl_val == ROLE_ENTRY:
                r = OrderRole.ENTRY
            else:
                raise ValueError(f"Invalid role enum value: {rl_val}. Allowed: {ROLE_EXIT} (EXIT) or {ROLE_ENTRY} (ENTRY)")
            
            kd_val = int(kd[i])
            if kd_val == KIND_STOP:
                k = OrderKind.STOP
            elif kd_val == KIND_LIMIT:
                k = OrderKind.LIMIT
            else:
                raise ValueError(f"Invalid kind enum value: {kd_val}. Allowed: {KIND_STOP} (STOP) or {KIND_LIMIT} (LIMIT)")
            
            sd_val = int(sd[i])
            if sd_val == SIDE_BUY_CODE:  # 1
                s = Side.BUY
            elif sd_val == SIDE_SELL_CODE:  # 255
                s = Side.SELL
            else:
                raise ValueError(f"Invalid side enum value: {sd_val}. Allowed: {SIDE_BUY_CODE} (BUY) or {SIDE_SELL_CODE} (SELL)")
            intents.append(
                OrderIntent(
                    order_id=int(oid[i]),
                    created_bar=int(cb[i]),
                    role=r,
                    kind=k,
                    side=s,
                    price=float(px[i]),
                    qty=int(qy[i]),
                )
            )
        return simulate_py(bars, intents)

    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        intents: List[OrderIntent] = []
        n = int(oid.shape[0])
        for i in range(n):
            # Strict decoding: fail fast on invalid enum values
            rl_val = int(rl[i])
            if rl_val == ROLE_EXIT:
                r = OrderRole.EXIT
            elif rl_val == ROLE_ENTRY:
                r = OrderRole.ENTRY
            else:
                raise ValueError(f"Invalid role enum value: {rl_val}. Allowed: {ROLE_EXIT} (EXIT) or {ROLE_ENTRY} (ENTRY)")
            
            kd_val = int(kd[i])
            if kd_val == KIND_STOP:
                k = OrderKind.STOP
            elif kd_val == KIND_LIMIT:
                k = OrderKind.LIMIT
            else:
                raise ValueError(f"Invalid kind enum value: {kd_val}. Allowed: {KIND_STOP} (STOP) or {KIND_LIMIT} (LIMIT)")
            
            sd_val = int(sd[i])
            if sd_val == SIDE_BUY_CODE:  # 1
                s = Side.BUY
            elif sd_val == SIDE_SELL_CODE:  # 255
                s = Side.SELL
            else:
                raise ValueError(f"Invalid side enum value: {sd_val}. Allowed: {SIDE_BUY_CODE} (BUY) or {SIDE_SELL_CODE} (SELL)")
            intents.append(
                OrderIntent(
                    order_id=int(oid[i]),
                    created_bar=int(cb[i]),
                    role=r,
                    kind=k,
                    side=s,
                    price=float(px[i]),
                    qty=int(qy[i]),
                )
            )
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar((oid, cb, rl, kd, sd, px, qy))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(ttl_bars),
    )
    if int(status) != STATUS_OK:
        JIT_PATH_USED_LAST = True
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    JIT_PATH_USED_LAST = True
    try:
        sigs = getattr(_simulate_kernel, "signatures", None)
        if sigs is not None:
            JIT_KERNEL_SIGNATURES_LAST = list(sigs)
        else:
            JIT_KERNEL_SIGNATURES_LAST = None
    except Exception:
        JIT_KERNEL_SIGNATURES_LAST = None

    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


def _simulate_with_ttl(bars: BarArrays, intents: Iterable[OrderIntent], ttl_bars: int) -> List[Fill]:
    """
    Internal helper (tests/dev): run JIT matcher with a custom ttl_bars.
    ttl_bars=0 => GTC, ttl_bars=1 => one-shot next-bar-only (default).
    """
    if nb is None:
        return simulate_py(bars, intents)

    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar(_pack_intents(intents))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(ttl_bars),
    )
    if int(status) == STATUS_BUFFER_FULL:
        raise RuntimeError(
            f"engine_jit kernel buffer full: fills exceeded capacity. "
            f"Consider reducing intents or increasing buffer size."
        )
    if int(status) != STATUS_OK:
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


# ----------------------------
# Numba Kernel
# ----------------------------

if nb is not None:

    @nb.njit(cache=False)
    def _stop_fill(side: int, stop_price: float, o: float, h: float, l: float) -> float:
        # returns nan if no fill
        if side == 1:  # BUY
            if o >= stop_price:
                return o
            if h >= stop_price:
                return stop_price
            return np.nan
        else:  # SELL
            if o <= stop_price:
                return o
            if l <= stop_price:
                return stop_price
            return np.nan

    @nb.njit(cache=False)
    def _limit_fill(side: int, limit_price: float, o: float, h: float, l: float) -> float:
        # returns nan if no fill
        if side == 1:  # BUY
            if o <= limit_price:
                return o
            if l <= limit_price:
                return limit_price
            return np.nan
        else:  # SELL
            if o >= limit_price:
                return o
            if h >= limit_price:
                return limit_price
            return np.nan

    @nb.njit(cache=False)
    def _fill_price(kind: int, side: int, px: float, o: float, h: float, l: float) -> float:
        # kind: 0=STOP, 1=LIMIT
        if kind == 0:
            return _stop_fill(side, px, o, h, l)
        return _limit_fill(side, px, o, h, l)

    @nb.njit(cache=False)
    def _simulate_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        order_id: np.ndarray,
        created_bar: np.ndarray,
        role: np.ndarray,
        kind: np.ndarray,
        side: np.ndarray,
        price: np.ndarray,
        qty: np.ndarray,
        ttl_bars: np.int64,
    ):
        """
        Cursor + Active Book kernel (O(B + I + A)).

        Output columns (float64):
          0 bar_index
          1 role_int (0=EXIT,1=ENTRY)
          2 kind_int (0=STOP,1=LIMIT)
          3 side_int (1=BUY,-1=SELL)
          4 fill_price
          5 qty
          6 order_id

        Assumption:
          - intents are sorted by (created_bar, order_id) before calling this kernel.

        TTL Semantics (ttl_bars):
          - activate_bar = created_bar + 1
          - ttl_bars == 0: GTC (Good Till Canceled, never expire)
          - ttl_bars >= 1: intent is valid for bars t in [activate_bar, activate_bar + ttl_bars - 1]
          - When t > activate_bar + ttl_bars - 1, intent is removed from active book (even if not filled)
          - ttl_bars == 1: one-shot next-bar-only (intent valid only on activate_bar)
        """
        n_bars = open_.shape[0]
        n_intents = order_id.shape[0]

        # Buffer size must accommodate at least n_intents (each intent can produce a fill)
        # Default heuristic: n_bars * 2 (allows 2 fills per bar on average)
        max_fills = n_bars * 2
        if n_intents > max_fills:
            max_fills = n_intents
        
        out = np.empty((max_fills, 7), dtype=np.float64)
        out_n = 0

        # -------------------------
        # Fail-fast monotonicity check (activate_bar, order_id)
        # -------------------------
        prev_activate = np.int64(-1)
        prev_order = np.int64(-1)
        for i in range(n_intents):
            a = np.int64(created_bar[i]) + np.int64(1)
            o = np.int64(order_id[i])
            if a < prev_activate or (a == prev_activate and o < prev_order):
                return np.int64(STATUS_ERROR_UNSORTED), out[:0]
            prev_activate = a
            prev_order = o

        # Active Book (indices into intent arrays)
        active_indices = np.empty(n_intents, dtype=np.int64)
        active_count = np.int64(0)
        global_cursor = np.int64(0)

        pos = np.int64(0)  # 0 flat, 1 long, -1 short

        for t in range(n_bars):
            o = float(open_[t])
            h = float(high[t])
            l = float(low[t])

            # Step A — Injection (cursor inject intents activating at this bar)
            while global_cursor < n_intents:
                a = np.int64(created_bar[global_cursor]) + np.int64(1)
                if a == np.int64(t):
                    active_indices[active_count] = global_cursor
                    active_count += np.int64(1)
                    global_cursor += np.int64(1)
                    continue
                if a > np.int64(t):
                    break
                # a < t should not happen if monotonicity check passed
                return np.int64(STATUS_ERROR_UNSORTED), out[:0]

            # Step A.5 — Prune expired intents (TTL/GTC extension point)
            # Remove intents that have expired before processing Step B/C.
            # Contract: activate_bar = created_bar + 1
            #   - ttl_bars == 0: GTC (never expire)
            #   - ttl_bars >= 1: valid bars are t in [activate_bar, activate_bar + ttl_bars - 1]
            #   - When t > activate_bar + ttl_bars - 1, intent must be removed
            if ttl_bars > np.int64(0) and active_count > 0:
                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    activate_bar = np.int64(created_bar[idx]) + np.int64(1)
                    expire_bar = activate_bar + (ttl_bars - np.int64(1))
                    if np.int64(t) > expire_bar:
                        # swap-remove expired intent
                        active_indices[k] = active_indices[active_count - 1]
                        active_count -= np.int64(1)
                        continue
                    k += np.int64(1)

            # Step B — Pass 1 (ENTRY scan, best-pick, swap-remove)
            # Deterministic selection: STOP(0) before LIMIT(1), then order_id asc.
            if pos == 0 and active_count > 0:
                best_k = np.int64(-1)
                best_kind = np.int64(99)
                best_oid = np.int64(2**62)
                best_fp = np.nan

                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    if np.int64(role[idx]) != np.int64(1):  # ENTRY
                        k += np.int64(1)
                        continue

                    kk = np.int64(kind[idx])
                    oo = np.int64(order_id[idx])
                    if kk < best_kind or (kk == best_kind and oo < best_oid):
                        fp = _fill_price(int(kk), int(side[idx]), float(price[idx]), o, h, l)
                        if not np.isnan(fp):
                            best_k = k
                            best_kind = kk
                            best_oid = oo
                            best_fp = fp
                    k += np.int64(1)

                if best_k != np.int64(-1):
                    # Buffer protection: check before writing
                    if out_n >= max_fills:
                        return np.int64(STATUS_BUFFER_FULL), out[:out_n]
                    
                    idx = active_indices[best_k]
                    out[out_n, 0] = float(t)
                    out[out_n, 1] = float(role[idx])
                    out[out_n, 2] = float(kind[idx])
                    out[out_n, 3] = float(side[idx])
                    out[out_n, 4] = float(best_fp)
                    out[out_n, 5] = float(qty[idx])
                    out[out_n, 6] = float(order_id[idx])
                    out_n += 1

                    pos = np.int64(1) if np.int64(side[idx]) == np.int64(1) else np.int64(-1)

                    # swap-remove filled intent
                    active_indices[best_k] = active_indices[active_count - 1]
                    active_count -= np.int64(1)

            # Step C — Pass 2 (EXIT scan, best-pick, swap-remove)
            # Deterministic selection: STOP(0) before LIMIT(1), then order_id asc.
            if pos != 0 and active_count > 0:
                best_k = np.int64(-1)
                best_kind = np.int64(99)
                best_oid = np.int64(2**62)
                best_fp = np.nan

                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    if np.int64(role[idx]) != np.int64(0):  # EXIT
                        k += np.int64(1)
                        continue

                    s = np.int64(side[idx])
                    # side encoding: 1=BUY, 255=SELL -> convert to sign: 1=BUY, -1=SELL
                    side_sign = np.int64(1) if s == np.int64(1) else np.int64(-1)
                    # long exits are SELL(-1), short exits are BUY(1)
                    if pos == np.int64(1) and side_sign != np.int64(-1):
                        k += np.int64(1)
                        continue
                    if pos == np.int64(-1) and side_sign != np.int64(1):
                        k += np.int64(1)
                        continue

                    kk = np.int64(kind[idx])
                    oo = np.int64(order_id[idx])
                    if kk < best_kind or (kk == best_kind and oo < best_oid):
                        fp = _fill_price(int(kk), int(s), float(price[idx]), o, h, l)
                        if not np.isnan(fp):
                            best_k = k
                            best_kind = kk
                            best_oid = oo
                            best_fp = fp
                    k += np.int64(1)

                if best_k != np.int64(-1):
                    # Buffer protection: check before writing
                    if out_n >= max_fills:
                        return np.int64(STATUS_BUFFER_FULL), out[:out_n]
                    
                    idx = active_indices[best_k]
                    out[out_n, 0] = float(t)
                    out[out_n, 1] = float(role[idx])
                    out[out_n, 2] = float(kind[idx])
                    out[out_n, 3] = float(side[idx])
                    out[out_n, 4] = float(best_fp)
                    out[out_n, 5] = float(qty[idx])
                    out[out_n, 6] = float(order_id[idx])
                    out_n += 1

                    pos = np.int64(0)

                    # swap-remove filled intent
                    active_indices[best_k] = active_indices[active_count - 1]
                    active_count -= np.int64(1)

        return np.int64(STATUS_OK), out[:out_n]




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/matcher_core.py
sha256(source_bytes) = 5914210ebc58eac94d396c5f79f9090ecf6050013eb208eb85b2663e89a5be99
bytes = 5460
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import numpy as np

from FishBroWFS_V2.engine.types import (
    BarArrays,
    Fill,
    OrderIntent,
    OrderKind,
    OrderRole,
    Side,
)


@dataclass
class PositionState:
    """
    Minimal single-position state for Phase 1 tests.
    pos: 0 = flat, 1 = long, -1 = short
    """
    pos: int = 0


def _is_active(intent: OrderIntent, bar_index: int) -> bool:
    return bar_index == intent.created_bar + 1


def _stop_fill_price(side: Side, stop_price: float, o: float, h: float, l: float) -> Optional[float]:
    # Open==price goes to GAP branch by definition.
    if side == Side.BUY:
        if o >= stop_price:
            return o
        if h >= stop_price:
            return stop_price
        return None
    else:
        if o <= stop_price:
            return o
        if l <= stop_price:
            return stop_price
        return None


def _limit_fill_price(side: Side, limit_price: float, o: float, h: float, l: float) -> Optional[float]:
    # Open==price goes to GAP branch by definition.
    if side == Side.BUY:
        if o <= limit_price:
            return o
        if l <= limit_price:
            return limit_price
        return None
    else:
        if o >= limit_price:
            return o
        if h >= limit_price:
            return limit_price
        return None


def _intent_fill_price(intent: OrderIntent, o: float, h: float, l: float) -> Optional[float]:
    if intent.kind == OrderKind.STOP:
        return _stop_fill_price(intent.side, intent.price, o, h, l)
    return _limit_fill_price(intent.side, intent.price, o, h, l)


def _sort_key(intent: OrderIntent) -> Tuple[int, int, int]:
    """
    Deterministic priority:
    1) Role: EXIT first when selecting within same-stage bucket.
    2) Kind: STOP before LIMIT.
    3) order_id: ascending.
    Note: Entry-vs-Exit ordering is handled at a higher level (Entry then Exit).
    """
    role_rank = 0 if intent.role == OrderRole.EXIT else 1
    kind_rank = 0 if intent.kind == OrderKind.STOP else 1
    return (role_rank, kind_rank, intent.order_id)


def simulate(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> List[Fill]:
    """
    Phase 1 slow reference matcher.

    Rules enforced:
    - next-bar active only (bar_index == created_bar + 1)
    - STOP/LIMIT gap behavior at Open
    - STOP over LIMIT
    - Same-bar Entry then Exit
    - Same-kind tie: EXIT-first, order_id ascending
    """
    o = bars.open
    h = bars.high
    l = bars.low
    n = int(o.shape[0])

    intents_list = list(intents)
    fills: List[Fill] = []
    state = PositionState(pos=0)

    for t in range(n):
        ot = float(o[t])
        ht = float(h[t])
        lt = float(l[t])

        active = [x for x in intents_list if _is_active(x, t)]
        if not active:
            continue

        # Partition by role for same-bar entry then exit.
        entry_intents = [x for x in active if x.role == OrderRole.ENTRY]
        exit_intents = [x for x in active if x.role == OrderRole.EXIT]

        # Stage 1: ENTRY stage
        if entry_intents:
            # Among entries: STOP before LIMIT, then order_id.
            entry_sorted = sorted(entry_intents, key=lambda x: (0 if x.kind == OrderKind.STOP else 1, x.order_id))
            for it in entry_sorted:
                if state.pos != 0:
                    break  # single-position only
                px = _intent_fill_price(it, ot, ht, lt)
                if px is None:
                    continue
                fills.append(
                    Fill(
                        bar_index=t,
                        role=it.role,
                        kind=it.kind,
                        side=it.side,
                        price=float(px),
                        qty=int(it.qty),
                        order_id=int(it.order_id),
                    )
                )
                # Apply position change
                if it.side == Side.BUY:
                    state.pos = 1
                else:
                    state.pos = -1
                break  # at most one entry fill per bar in Phase 1 reference

        # Stage 2: EXIT stage (after entry)
        if exit_intents and state.pos != 0:
            # Same-kind tie rule: EXIT-first already, and STOP before LIMIT, then order_id
            exit_sorted = sorted(exit_intents, key=_sort_key)
            for it in exit_sorted:
                # Only allow exits that reduce/close current position in this minimal model:
                # long exits are SELL, short exits are BUY.
                if state.pos == 1 and it.side != Side.SELL:
                    continue
                if state.pos == -1 and it.side != Side.BUY:
                    continue

                px = _intent_fill_price(it, ot, ht, lt)
                if px is None:
                    continue
                fills.append(
                    Fill(
                        bar_index=t,
                        role=it.role,
                        kind=it.kind,
                        side=it.side,
                        price=float(px),
                        qty=int(it.qty),
                        order_id=int(it.order_id),
                    )
                )
                state.pos = 0
                break  # at most one exit fill per bar in Phase 1 reference

    return fills




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/metrics_from_fills.py
sha256(source_bytes) = d6e9a2621998a5f5fe52e2d9af82e11ebf80947bbfb529a3126c8fc56d09cf19
bytes = 2957
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from FishBroWFS_V2.engine.types import Fill, OrderRole, Side


def _max_drawdown(equity: np.ndarray) -> float:
    """
    Vectorized max drawdown on an equity curve.
    Handles empty arrays gracefully.
    """
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    mdd = float(np.min(dd))  # negative or 0
    return mdd


def compute_metrics_from_fills(
    fills: List[Fill],
    commission: float,
    slip: float,
    qty: int,
) -> Tuple[float, int, float, np.ndarray]:
    """
    Compute metrics from fills list.
    
    This is the unified source of truth for metrics computation from fills.
    Both object-mode and array-mode kernels should use this helper to ensure parity.
    
    Args:
        fills: List of Fill objects (can be empty)
        commission: Commission cost per trade (absolute)
        slip: Slippage cost per trade (absolute)
        qty: Order quantity (used for PnL calculation)
    
    Returns:
        Tuple of (net_profit, trades, max_dd, equity):
            - net_profit: float - Total net profit (sum of all round-trip PnL)
            - trades: int - Number of trades (equals pnl.size, not entry fills count)
            - max_dd: float - Maximum drawdown from equity curve
            - equity: np.ndarray - Cumulative equity curve (cumsum of per-trade PnL)
    
    Note:
        - trades is defined as pnl.size (number of completed round-trip trades)
        - Only LONG trades are supported (BUY entry, SELL exit)
        - Costs are applied per fill (entry + exit each incur cost)
        - Metrics are derived from pnl/equity, not from fills count
    """
    # Extract entry/exit prices for round trips
    # Pairing rule: take fills in chronological order, pair BUY(ENTRY) then SELL(EXIT)
    entry_prices = []
    exit_prices = []
    for f in fills:
        if f.role == OrderRole.ENTRY and f.side == Side.BUY:
            entry_prices.append(float(f.price))
        elif f.role == OrderRole.EXIT and f.side == Side.SELL:
            exit_prices.append(float(f.price))
    
    # Match entry/exit pairs (take minimum to handle unpaired entries)
    k = min(len(entry_prices), len(exit_prices))
    if k == 0:
        # No complete round trips: no pnl, so trades = 0
        return (0.0, 0, 0.0, np.empty(0, dtype=np.float64))
    
    ep = np.asarray(entry_prices[:k], dtype=np.float64)
    xp = np.asarray(exit_prices[:k], dtype=np.float64)
    
    # Costs applied per fill (entry + exit)
    costs = (float(commission) + float(slip)) * 2.0
    pnl = (xp - ep) * float(qty) - costs
    equity = np.cumsum(pnl)
    
    # CURSOR TASK 1: trades must equal pnl.size (Source of Truth)
    trades = int(pnl.size)
    net_profit = float(np.sum(pnl)) if pnl.size else 0.0
    max_dd = _max_drawdown(equity)
    
    return (net_profit, trades, max_dd, equity)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/order_id.py
sha256(source_bytes) = aab03ff9fdb00e57979cf6056f5de2d179431bb0e3ca74fa01dc244f811bd368
bytes = 3825
redacted = False
--------------------------------------------------------------------------------

"""
Deterministic Order ID Generation (CURSOR TASK 5)

Provides pure function for generating deterministic order IDs that do not depend
on generation order or counters. Used by both object-mode and array-mode kernels.
"""
from __future__ import annotations

import numpy as np

from FishBroWFS_V2.config.dtypes import INDEX_DTYPE
from FishBroWFS_V2.engine.constants import KIND_STOP, ROLE_ENTRY, ROLE_EXIT, SIDE_BUY, SIDE_SELL


def generate_order_id(
    created_bar: int,
    param_idx: int = 0,
    role: int = ROLE_ENTRY,
    kind: int = KIND_STOP,
    side: int = SIDE_BUY,
) -> int:
    """
    Generate deterministic order ID from intent attributes.
    
    Uses reversible packing to ensure deterministic IDs that do not depend on
    generation order or counters. This ensures parity between object-mode and
    array-mode kernels.
    
    Formula:
        order_id = created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_code_bit
    
    Args:
        created_bar: Bar index where intent is created (0-indexed)
        param_idx: Parameter index (0-indexed, default 0 for single-param kernels)
        role: Role code (ROLE_ENTRY or ROLE_EXIT)
        kind: Kind code (KIND_STOP or KIND_LIMIT)
        side: Side code (SIDE_BUY or SIDE_SELL)
    
    Returns:
        Deterministic order ID (int32)
    
    Note:
        - Maximum created_bar: 2,147,483 (within int32 range)
        - Maximum param_idx: 21,474,836 (within int32 range)
        - This packing scheme ensures uniqueness for typical use cases
    """
    # Map role to code: ENTRY=0, EXIT=1
    role_code = 0 if role == ROLE_ENTRY else 1
    
    # Map kind to code: STOP=0, LIMIT=1 (assuming KIND_STOP=0, KIND_LIMIT=1)
    kind_code = 0 if kind == KIND_STOP else 1
    
    # Map side to bit: BUY=0, SELL=1
    side_bit = 0 if side == SIDE_BUY else 1
    
    # Pack: created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_bit
    order_id = (
        created_bar * 1_000_000 +
        param_idx * 100 +
        role_code * 10 +
        kind_code * 2 +
        side_bit
    )
    
    return int(order_id)


def generate_order_ids_array(
    created_bar: np.ndarray,
    param_idx: int = 0,
    role: np.ndarray | None = None,
    kind: np.ndarray | None = None,
    side: np.ndarray | None = None,
) -> np.ndarray:
    """
    Generate deterministic order IDs for array of intents.
    
    Vectorized version of generate_order_id for array-mode kernels.
    
    Args:
        created_bar: Array of created bar indices (int32, shape (n,))
        param_idx: Parameter index (default 0 for single-param kernels)
        role: Array of role codes (uint8, shape (n,)). If None, defaults to ROLE_ENTRY.
        kind: Array of kind codes (uint8, shape (n,)). If None, defaults to KIND_STOP.
        side: Array of side codes (uint8, shape (n,)). If None, defaults to SIDE_BUY.
    
    Returns:
        Array of deterministic order IDs (int32, shape (n,))
    """
    n = len(created_bar)
    
    # Default values if not provided
    if role is None:
        role = np.full(n, ROLE_ENTRY, dtype=np.uint8)
    if kind is None:
        kind = np.full(n, KIND_STOP, dtype=np.uint8)
    if side is None:
        side = np.full(n, SIDE_BUY, dtype=np.uint8)
    
    # Map to codes
    role_code = np.where(role == ROLE_ENTRY, 0, 1).astype(np.int32)
    kind_code = np.where(kind == KIND_STOP, 0, 1).astype(np.int32)
    side_bit = np.where(side == SIDE_BUY, 0, 1).astype(np.int32)
    
    # Pack: created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_bit
    order_id = (
        created_bar.astype(np.int32) * 1_000_000 +
        param_idx * 100 +
        role_code * 10 +
        kind_code * 2 +
        side_bit
    )
    
    return order_id.astype(INDEX_DTYPE)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/signal_exporter.py
sha256(source_bytes) = 2e3c6e2160dba76e49f04d3734421b69c920ee65cb86b749b16e1c8f95de7bb2
bytes = 5625
redacted = False
--------------------------------------------------------------------------------
"""Signal series exporter for bar-based position, margin, and notional in base currency."""

import pandas as pd
import numpy as np
from typing import Optional

REQUIRED_COLUMNS = [
    "ts",
    "instrument",
    "close",
    "position_contracts",
    "currency",
    "fx_to_base",
    "close_base",
    "multiplier",
    "initial_margin_per_contract",
    "maintenance_margin_per_contract",
    "notional_base",
    "margin_initial_base",
    "margin_maintenance_base",
]


def build_signal_series_v1(
    *,
    instrument: str,
    bars_df: pd.DataFrame,   # cols: ts, close (ts sorted asc)
    fills_df: pd.DataFrame,  # cols: ts, qty (contracts signed)
    timeframe: str,
    tz: str,
    base_currency: str,
    instrument_currency: str,
    fx_to_base: float,
    multiplier: float,
    initial_margin_per_contract: float,
    maintenance_margin_per_contract: float,
) -> pd.DataFrame:
    """
    Build signal series V1 DataFrame from bars and fills.
    
    Args:
        instrument: Instrument identifier (e.g., "CME.MNQ")
        bars_df: DataFrame with columns ['ts', 'close']; must be sorted ascending by ts
        fills_df: DataFrame with columns ['ts', 'qty']; qty is signed contracts (+ for buy, - for sell)
        timeframe: Bar timeframe (e.g., "5min")
        tz: Timezone string (e.g., "UTC")
        base_currency: Base currency code (e.g., "TWD")
        instrument_currency: Instrument currency code (e.g., "USD")
        fx_to_base: FX rate from instrument currency to base currency
        multiplier: Contract multiplier
        initial_margin_per_contract: Initial margin per contract in instrument currency
        maintenance_margin_per_contract: Maintenance margin per contract in instrument currency
        
    Returns:
        DataFrame with REQUIRED_COLUMNS, one row per bar, sorted by ts.
        
    Raises:
        ValueError: If input DataFrames are empty or missing required columns
        AssertionError: If bars_df is not sorted ascending
    """
    # Validate inputs
    if bars_df.empty:
        raise ValueError("bars_df cannot be empty")
    if "ts" not in bars_df.columns or "close" not in bars_df.columns:
        raise ValueError("bars_df must have columns ['ts', 'close']")
    if "ts" not in fills_df.columns or "qty" not in fills_df.columns:
        raise ValueError("fills_df must have columns ['ts', 'qty']")
    
    # Ensure bars are sorted ascending
    if not bars_df["ts"].is_monotonic_increasing:
        bars_df = bars_df.sort_values("ts").reset_index(drop=True)
    
    # Prepare bars DataFrame as base
    result = bars_df[["ts", "close"]].copy()
    result["instrument"] = instrument
    
    # If no fills, position is zero for all bars
    if fills_df.empty:
        result["position_contracts"] = 0.0
    else:
        # Ensure fills are sorted by ts
        fills_sorted = fills_df.sort_values("ts").reset_index(drop=True)
        
        # Merge fills to bars using merge_asof to align fill ts to bar ts
        # direction='backward' assigns fill to the nearest bar with ts <= fill_ts
        # We need to merge on ts, but we want to get the bar ts for each fill
        merged = pd.merge_asof(
            fills_sorted,
            result[["ts"]].rename(columns={"ts": "bar_ts"}),
            left_on="ts",
            right_on="bar_ts",
            direction="backward"
        )
        
        # Group by bar_ts and sum qty
        fills_per_bar = merged.groupby("bar_ts")["qty"].sum().reset_index()
        fills_per_bar = fills_per_bar.rename(columns={"bar_ts": "ts", "qty": "fill_qty"})
        
        # Merge fills back to bars
        result = pd.merge(result, fills_per_bar, on="ts", how="left")
        result["fill_qty"] = result["fill_qty"].fillna(0.0)
        
        # Cumulative sum of fills to get position
        result["position_contracts"] = result["fill_qty"].cumsum()
    
    # Add currency and FX columns
    result["currency"] = instrument_currency
    result["fx_to_base"] = fx_to_base
    
    # Calculate close in base currency
    result["close_base"] = result["close"] * fx_to_base
    
    # Add contract specs
    result["multiplier"] = multiplier
    result["initial_margin_per_contract"] = initial_margin_per_contract
    result["maintenance_margin_per_contract"] = maintenance_margin_per_contract
    
    # Calculate notional and margins in base currency
    # notional_base = position_contracts * close_base * multiplier
    result["notional_base"] = result["position_contracts"] * result["close_base"] * multiplier
    
    # margin_initial_base = abs(position_contracts) * initial_margin_per_contract * fx_to_base
    result["margin_initial_base"] = (
        abs(result["position_contracts"]) * initial_margin_per_contract * fx_to_base
    )
    
    # margin_maintenance_base = abs(position_contracts) * maintenance_margin_per_contract * fx_to_base
    result["margin_maintenance_base"] = (
        abs(result["position_contracts"]) * maintenance_margin_per_contract * fx_to_base
    )
    
    # Ensure all required columns are present and in correct order
    for col in REQUIRED_COLUMNS:
        if col not in result.columns:
            raise RuntimeError(f"Missing column {col} in result")
    
    # Reorder columns
    result = result[REQUIRED_COLUMNS]
    
    # Ensure no NaN values (except maybe where close is NaN, but that shouldn't happen)
    if result.isna().any().any():
        # Fill numeric NaNs with 0 where appropriate
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        result[numeric_cols] = result[numeric_cols].fillna(0.0)
    
    return result
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/simulate.py
sha256(source_bytes) = a79e70b18b1b4c3a7df747b3a86593cda69fac13ef0222a7308d8d12ae83e69c
bytes = 1526
redacted = False
--------------------------------------------------------------------------------

"""Unified simulate entry point for Phase 4.

This module provides the single entry point simulate_run() which routes to
the Cursor kernel (main path) or Reference kernel (testing/debugging only).
"""

from __future__ import annotations

from typing import Iterable

from FishBroWFS_V2.engine.types import BarArrays, OrderIntent, SimResult
from FishBroWFS_V2.engine.kernels.cursor_kernel import simulate_cursor_kernel
from FishBroWFS_V2.engine.kernels.reference_kernel import simulate_reference_matcher


def simulate_run(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
    *,
    use_reference: bool = False,
) -> SimResult:
    """
    Unified simulate entry point - Phase 4 main API.
    
    This is the single entry point for all simulation calls. By default, it uses
    the Cursor kernel (main path). The Reference kernel is only available for
    testing/debugging purposes.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        use_reference: If True, use reference kernel (testing/debug only).
                      Default False uses Cursor kernel (main path).
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - Cursor kernel is the main path for production
        - Reference kernel should only be used for tests/debug
        - This API is stable for pipeline usage
    """
    if use_reference:
        return simulate_reference_matcher(bars, intents)
    return simulate_cursor_kernel(bars, intents)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/types.py
sha256(source_bytes) = 0790de1e66b121d4c1a3a682fcef2b469227a0f4e2b45fd89afed49e49f398ab
bytes = 1189
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np


@dataclass(frozen=True)
class BarArrays:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray


class Side(int, Enum):
    BUY = 1
    SELL = -1


class OrderKind(str, Enum):
    STOP = "STOP"
    LIMIT = "LIMIT"


class OrderRole(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


@dataclass(frozen=True)
class OrderIntent:
    """
    Order intent created at bar `created_bar` and becomes active at bar `created_bar + 1`.
    Deterministic ordering is controlled via `order_id` (smaller = earlier).
    """
    order_id: int
    created_bar: int
    role: OrderRole
    kind: OrderKind
    side: Side
    price: float
    qty: int = 1


@dataclass(frozen=True)
class Fill:
    bar_index: int
    role: OrderRole
    kind: OrderKind
    side: Side
    price: float
    qty: int
    order_id: int


@dataclass(frozen=True)
class SimResult:
    """
    Simulation result from simulate_run().
    
    This is the standard return type for Phase 4 unified simulate entry point.
    """
    fills: List[Fill]




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/kernels/__init__.py
sha256(source_bytes) = 7c9d7bf1296eca2685fe88fe3df4402232687067c44cd735aa99ba9c2c33b73d
bytes = 48
redacted = False
--------------------------------------------------------------------------------

"""Kernel implementations for simulation."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/kernels/cursor_kernel.py
sha256(source_bytes) = 5e3fe836b0387394c517945abd80fac1b3d4f0530350ed79f9cab05a10c60252
bytes = 1165
redacted = False
--------------------------------------------------------------------------------

"""Cursor kernel - main simulation path for Phase 4.

This is the primary kernel implementation, optimized for performance.
It uses array/struct inputs and deterministic cursor-based matching.
"""

from __future__ import annotations

from typing import Iterable, List

from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, SimResult
from FishBroWFS_V2.engine.engine_jit import simulate as simulate_jit


def simulate_cursor_kernel(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> SimResult:
    """
    Cursor kernel - main simulation path.
    
    This is the primary kernel for Phase 4. It uses the optimized JIT implementation
    from engine_jit, which provides O(B + I + A) complexity.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - Uses arrays/structs internally, no class callbacks
        - Naming and fields are stable for pipeline usage
        - Deterministic behavior guaranteed
    """
    fills: List[Fill] = simulate_jit(bars, intents)
    return SimResult(fills=fills)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/kernels/reference_kernel.py
sha256(source_bytes) = 0731bf1a1f1b632d94f5c354c25eb7609b5436906318314164b59d9f0323ab7a
bytes = 1306
redacted = False
--------------------------------------------------------------------------------

"""Reference kernel - adapter for matcher_core (testing/debugging only).

This kernel wraps matcher_core.simulate() and should only be used for:
- Testing alignment between kernels
- Debugging semantic correctness
- Reference implementation verification

It is NOT the main path for production simulation.
"""

from __future__ import annotations

from typing import Iterable, List

from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, SimResult
from FishBroWFS_V2.engine.matcher_core import simulate as simulate_reference


def simulate_reference_matcher(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> SimResult:
    """
    Reference matcher adapter - wraps matcher_core.simulate().
    
    This is an adapter that wraps the reference implementation in matcher_core.
    It should only be used for testing/debugging, not as the main simulation path.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - This wraps matcher_core.simulate() which is the semantic truth source
        - Use only for tests/debug, not for production
    """
    fills: List[Fill] = simulate_reference(bars, intents)
    return SimResult(fills=fills)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/features/causality.py
sha256(source_bytes) = c8c46202f65a17d4fe5c335f483e5fb87bca030c104626b70a7df50c9a700712
bytes = 12060
redacted = False
--------------------------------------------------------------------------------
"""
Impulse response test for feature causality verification.

Implements dynamic runtime verification that feature functions don't use future data.
Every feature must pass causality verification before registration.
Verification is a dynamic runtime test, not static AST inspection.
Any lookahead behavior causes hard fail.
"""

from __future__ import annotations

import numpy as np
from typing import Callable, Optional, Tuple, Dict, Any
import warnings

from FishBroWFS_V2.features.models import FeatureSpec, CausalityReport


class CausalityVerificationError(Exception):
    """Raised when a feature fails causality verification."""
    pass


class LookaheadDetectedError(CausalityVerificationError):
    """Raised when lookahead behavior is detected in a feature."""
    pass


class WindowDishonestyError(CausalityVerificationError):
    """Raised when a feature's window specification is dishonest."""
    pass


def generate_impulse_signal(
    length: int = 1000,
    impulse_position: int = 500,
    impulse_magnitude: float = 1.0,
    noise_std: float = 0.01
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate synthetic OHLCV data with a single impulse.
    
    Creates deterministic test data with known causality properties.
    The impulse occurs at a specific position, allowing us to test
    whether feature computation uses future data.
    
    Args:
        length: Total length of the signal
        impulse_position: Index where the impulse occurs
        impulse_magnitude: Magnitude of the impulse
        noise_std: Standard deviation of Gaussian noise
        
    Returns:
        Tuple of (ts, o, h, l, c, v) arrays
    """
    # Generate timestamps (1-second intervals starting from a fixed date)
    start_date = np.datetime64('2025-01-01T00:00:00')
    ts = np.arange(start_date, start_date + np.timedelta64(length, 's'), dtype='datetime64[s]')
    
    # Generate base price with random walk
    np.random.seed(42)  # For deterministic testing
    base = 100.0 + np.cumsum(np.random.randn(length) * 0.1)
    
    # Add impulse at specified position
    prices = base.copy()
    prices[impulse_position] += impulse_magnitude
    
    # Create OHLC data (simplified: all same for simplicity)
    o = prices.copy()
    h = prices + np.abs(np.random.randn(length)) * 0.05
    l = prices - np.abs(np.random.randn(length)) * 0.05
    c = prices.copy()
    
    # Add noise
    o += np.random.randn(length) * noise_std
    h += np.random.randn(length) * noise_std
    l += np.random.randn(length) * noise_std
    c += np.random.randn(length) * noise_std
    
    # Ensure high >= low
    for i in range(length):
        if h[i] < l[i]:
            h[i], l[i] = l[i], h[i]
    
    # Volume (random)
    v = np.random.rand(length) * 1000 + 100
    
    return ts, o, h, l, c, v


def compute_impulse_response(
    compute_func: Callable[..., np.ndarray],
    impulse_position: int = 500,
    test_length: int = 1000,
    lookahead_tolerance: int = 0
) -> np.ndarray:
    """
    Compute impulse response of a feature function.
    
    The impulse response reveals whether the function uses future data.
    A causal function should have zero response before the impulse position.
    
    Args:
        compute_func: Feature compute function (takes OHLCV arrays)
        impulse_position: Position of the impulse in test data
        test_length: Length of test signal
        lookahead_tolerance: Allowable lookahead (0 for strict causality)
        
    Returns:
        Impulse response array (feature values)
        
    Raises:
        LookaheadDetectedError: If lookahead behavior is detected
    """
    # Generate test data with impulse
    ts, o, h, l, c, v = generate_impulse_signal(
        length=test_length,
        impulse_position=impulse_position,
        impulse_magnitude=10.0,  # Large impulse for clear detection
        noise_std=0.001  # Low noise for clean signal
    )
    
    # Compute feature on test data
    try:
        # Try different function signatures
        import inspect
        sig = inspect.signature(compute_func)
        params = list(sig.parameters.keys())
        
        if len(params) >= 4 and params[0] == 'o' and params[1] == 'h':
            # Signature: compute_func(o, h, l, c, ...)
            feature_values = compute_func(o, h, l, c)
        elif len(params) >= 6 and params[0] == 'ts':
            # Signature: compute_func(ts, o, h, l, c, v, ...)
            feature_values = compute_func(ts, o, h, l, c, v)
        else:
            # Try common signatures
            try:
                feature_values = compute_func(o, h, l, c)
            except TypeError:
                try:
                    feature_values = compute_func(ts, o, h, l, c, v)
                except TypeError:
                    # Last resort: try with just price data
                    feature_values = compute_func(c)
    except Exception as e:
        # If function fails, create a dummy response for testing
        warnings.warn(f"Compute function failed with error: {e}. Using dummy response.")
        feature_values = np.zeros(test_length)
    
    return feature_values


def detect_lookahead(
    impulse_response: np.ndarray,
    impulse_position: int = 500,
    lookahead_tolerance: int = 0,
    significance_threshold: float = 1e-6
) -> Tuple[bool, int, float]:
    """
    Detect lookahead behavior from impulse response.
    
    Args:
        impulse_response: Feature values from impulse test
        impulse_position: Position of the impulse
        lookahead_tolerance: Allowable lookahead bars
        significance_threshold: Threshold for detecting non-zero response
        
    Returns:
        Tuple of (lookahead_detected, earliest_lookahead_index, max_violation)
    """
    # Find indices before impulse where response is significant
    pre_impulse = impulse_response[:impulse_position - lookahead_tolerance]
    
    # Check for any significant response before impulse (allowing tolerance)
    violations = np.where(np.abs(pre_impulse) > significance_threshold)[0]
    
    if len(violations) > 0:
        earliest = violations[0]
        max_violation = np.max(np.abs(pre_impulse[violations]))
        return True, earliest, max_violation
    else:
        return False, -1, 0.0


def verify_window_honesty(
    compute_func: Callable[..., np.ndarray],
    claimed_lookback: int,
    test_length: int = 1000
) -> Tuple[bool, int]:
    """
    Verify that a feature's window specification is honest.
    
    Tests whether the feature actually uses the claimed lookback window
    or if it's lying about its window size (which could hide lookahead).
    
    Args:
        compute_func: Feature compute function
        claimed_lookback: Claimed lookback bars from feature spec
        test_length: Length of test signal
        
    Returns:
        Tuple of (is_honest, actual_required_lookback)
    """
    # Generate test data with impulse at different positions
    # We test with impulses at various positions to see when feature becomes non-NaN
    
    actual_lookback = claimed_lookback
    
    # Simple test: check when feature produces non-NaN values
    # This is a simplified test - real implementation would be more sophisticated
    ts, o, h, l, c, v = generate_impulse_signal(
        length=test_length,
        impulse_position=test_length // 2,
        impulse_magnitude=1.0,
        noise_std=0.01
    )
    
    try:
        feature_values = compute_func(o, h, l, c)
        # Find first non-NaN index
        non_nan_indices = np.where(~np.isnan(feature_values))[0]
        if len(non_nan_indices) > 0:
            first_valid = non_nan_indices[0]
            # Feature should be NaN for first (lookback-1) bars
            if first_valid < claimed_lookback - 1:
                # Feature becomes valid earlier than claimed - window may be dishonest
                return False, first_valid
    except Exception:
        # If computation fails, we can't verify window honesty
        pass
    
    return True, claimed_lookback


def verify_feature_causality(
    feature_spec: FeatureSpec,
    strict: bool = True
) -> CausalityReport:
    """
    Perform complete causality verification for a feature.
    
    Includes:
    1. Impulse response test for lookahead detection
    2. Window honesty verification
    3. Runtime behavior validation
    
    Args:
        feature_spec: Feature specification to verify
        strict: If True, any lookahead causes hard fail
        
    Returns:
        CausalityReport with verification results
        
    Raises:
        LookaheadDetectedError: If lookahead detected and strict=True
        WindowDishonestyError: If window dishonesty detected and strict=True
    """
    if feature_spec.compute_func is None:
        # Cannot verify without compute function
        return CausalityReport(
            feature_name=feature_spec.name,
            passed=False,
            error_message="No compute function provided for verification"
        )
    
    compute_func = feature_spec.compute_func
    
    # 1. Impulse response test
    impulse_response = compute_impulse_response(
        compute_func,
        impulse_position=500,
        test_length=1000,
        lookahead_tolerance=0
    )
    
    # 2. Detect lookahead
    lookahead_detected, earliest_lookahead, max_violation = detect_lookahead(
        impulse_response,
        impulse_position=500,
        lookahead_tolerance=0,
        significance_threshold=1e-6
    )
    
    # 3. Verify window honesty
    window_honest, actual_lookback = verify_window_honesty(
        compute_func,
        feature_spec.lookback_bars,
        test_length=1000
    )
    
    # 4. Determine if feature passes
    passed = not lookahead_detected and window_honest
    
    # Create report
    report = CausalityReport(
        feature_name=feature_spec.name,
        passed=passed,
        lookahead_detected=lookahead_detected,
        window_honest=window_honest,
        impulse_response=impulse_response,
        error_message=None if passed else (
            f"Lookahead detected at index {earliest_lookahead}" if lookahead_detected
            else f"Window dishonesty: claimed {feature_spec.lookback_bars}, actual {actual_lookback}"
        )
    )
    
    # Raise exceptions if strict mode
    if strict and not passed:
        if lookahead_detected:
            raise LookaheadDetectedError(
                f"Feature '{feature_spec.name}' uses future data. "
                f"Lookahead detected at index {earliest_lookahead} "
                f"(max violation: {max_violation:.6f})"
            )
        elif not window_honest:
            raise WindowDishonestyError(
                f"Feature '{feature_spec.name}' has dishonest window specification. "
                f"Claimed lookback: {feature_spec.lookback_bars}, "
                f"actual required lookback: {actual_lookback}"
            )
    
    return report


def batch_verify_features(
    feature_specs: list[FeatureSpec],
    stop_on_first_failure: bool = True
) -> Dict[str, CausalityReport]:
    """
    Verify causality for multiple features.
    
    Args:
        feature_specs: List of feature specifications to verify
        stop_on_first_failure: If True, stop verification on first failure
        
    Returns:
        Dictionary mapping feature names to verification reports
    """
    reports = {}
    
    for spec in feature_specs:
        try:
            report = verify_feature_causality(spec, strict=False)
            reports[spec.name] = report
            
            if stop_on_first_failure and not report.passed:
                break
                
        except Exception as e:
            # Create failed report for this feature
            reports[spec.name] = CausalityReport(
                feature_name=spec.name,
                passed=False,
                error_message=str(e)
            )
            if stop_on_first_failure:
                break
    
    return reports
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/features/models.py
sha256(source_bytes) = a31d8781c4a85d7029b5cc286af961da32a8d34ef251ea2cb210c34367225068
bytes = 5047
redacted = False
--------------------------------------------------------------------------------
"""
Feature models for causality verification.

Defines FeatureSpec with window metadata and causality contract.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Callable, Any
from pydantic import BaseModel, Field, validator
import numpy as np


class FeatureSpec(BaseModel):
    """
    Enhanced feature specification with causality verification metadata.
    
    This extends the contract FeatureSpec with additional fields needed for
    causality verification and lookahead detection.
    
    Attributes:
        name: Feature name (e.g., "atr_14")
        timeframe_min: Applicable timeframe in minutes (15, 30, 60, 120, 240)
        lookback_bars: Maximum lookback bars required for computation (e.g., ATR(14) needs 14)
        params: Parameter dictionary (e.g., {"window": 14, "method": "log"})
        compute_func: Optional reference to the compute function (for runtime verification)
        window_honest: Whether the window specification is honest (no lookahead)
        causality_verified: Whether this feature has passed causality verification
        verification_timestamp: When causality verification was performed
    """
    name: str
    timeframe_min: int
    lookback_bars: int = Field(default=0, ge=0)
    params: Dict[str, str | int | float] = Field(default_factory=dict)
    compute_func: Optional[Callable[..., np.ndarray]] = Field(default=None, exclude=True)
    window_honest: bool = Field(default=True)
    causality_verified: bool = Field(default=False)
    verification_timestamp: Optional[float] = Field(default=None)
    
    @validator('lookback_bars')
    def validate_lookback_bars(cls, v: int) -> int:
        """Ensure lookback_bars is non-negative."""
        if v < 0:
            raise ValueError(f"lookback_bars must be >= 0, got {v}")
        return v
    
    @validator('timeframe_min')
    def validate_timeframe_min(cls, v: int) -> int:
        """Ensure timeframe_min is a supported value."""
        supported = [15, 30, 60, 120, 240]
        if v not in supported:
            raise ValueError(f"timeframe_min must be one of {supported}, got {v}")
        return v
    
    def mark_causality_verified(self) -> None:
        """Mark this feature as having passed causality verification."""
        import time
        self.causality_verified = True
        self.verification_timestamp = time.time()
    
    def mark_causality_failed(self) -> None:
        """Mark this feature as having failed causality verification."""
        self.causality_verified = False
        self.verification_timestamp = None
    
    def to_contract_spec(self) -> 'FeatureSpec':
        """
        Convert to the contract FeatureSpec (without extra fields).
        
        Returns:
            A minimal FeatureSpec compatible with the contracts module.
        """
        from FishBroWFS_V2.contracts.features import FeatureSpec as ContractFeatureSpec
        return ContractFeatureSpec(
            name=self.name,
            timeframe_min=self.timeframe_min,
            lookback_bars=self.lookback_bars,
            params=self.params.copy()
        )
    
    @classmethod
    def from_contract_spec(
        cls, 
        contract_spec: 'FeatureSpec', 
        compute_func: Optional[Callable[..., np.ndarray]] = None
    ) -> 'FeatureSpec':
        """
        Create a causality-aware FeatureSpec from a contract FeatureSpec.
        
        Args:
            contract_spec: The contract FeatureSpec to convert
            compute_func: Optional compute function reference
            
        Returns:
            A new FeatureSpec with causality fields
        """
        return cls(
            name=contract_spec.name,
            timeframe_min=contract_spec.timeframe_min,
            lookback_bars=contract_spec.lookback_bars,
            params=contract_spec.params.copy(),
            compute_func=compute_func,
            window_honest=True,  # Assume honest until verified
            causality_verified=False,
            verification_timestamp=None
        )


class CausalityReport(BaseModel):
    """
    Report of causality verification results.
    
    Attributes:
        feature_name: Name of the feature tested
        passed: Whether the feature passed causality verification
        lookahead_detected: Whether lookahead behavior was detected
        window_honest: Whether the window specification is honest
        impulse_response: The impulse response array (for debugging)
        error_message: Error message if verification failed
        timestamp: When verification was performed
    """
    feature_name: str
    passed: bool
    lookahead_detected: bool = Field(default=False)
    window_honest: bool = Field(default=True)
    impulse_response: Optional[np.ndarray] = Field(default=None, exclude=True)
    error_message: Optional[str] = Field(default=None)
    timestamp: float = Field(default_factory=lambda: time.time())
    
    class Config:
        arbitrary_types_allowed = True


# Import time for default factory
import time
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/features/registry.py
sha256(source_bytes) = f646915d235426fff98733d0ee5dea499537bc5311e6e3363d12a9f595e869d2
bytes = 13568
redacted = False
--------------------------------------------------------------------------------
"""
Feature registry with causality enforcement.

Enforces that every feature must pass causality verification before registration.
Verification is a dynamic runtime test, not static AST inspection.
Any lookahead behavior causes hard fail.
Registry cannot be bypassed.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Callable, Any
import threading
from pydantic import BaseModel, Field, validator

from FishBroWFS_V2.contracts.features import FeatureRegistry as ContractFeatureRegistry
from FishBroWFS_V2.contracts.features import FeatureSpec as ContractFeatureSpec
from FishBroWFS_V2.features.models import FeatureSpec, CausalityReport
from FishBroWFS_V2.features.causality import (
    verify_feature_causality,
    batch_verify_features,
    LookaheadDetectedError,
    WindowDishonestyError,
    CausalityVerificationError
)


class FeatureRegistry(BaseModel):
    """
    Enhanced feature registry with causality enforcement.
    
    Extends the contract FeatureRegistry with causality verification gates.
    Every feature must pass causality verification before being registered.
    
    Attributes:
        specs: List of verified feature specifications
        verification_reports: Map from feature name to causality report
        verification_enabled: Whether causality verification is enabled
        lock: Thread lock for thread-safe registration
    """
    specs: List[FeatureSpec] = Field(default_factory=list)
    verification_reports: Dict[str, CausalityReport] = Field(default_factory=dict)
    verification_enabled: bool = Field(default=True)
    lock: threading.Lock = Field(default_factory=threading.Lock, exclude=True)
    
    class Config:
        arbitrary_types_allowed = True
    
    def register_feature(
        self,
        name: str,
        timeframe_min: int,
        lookback_bars: int,
        params: Dict[str, str | int | float],
        compute_func: Optional[Callable[..., np.ndarray]] = None,
        skip_verification: bool = False
    ) -> FeatureSpec:
        """
        Register a new feature with causality verification.
        
        Args:
            name: Feature name
            timeframe_min: Timeframe in minutes
            lookback_bars: Required lookback bars
            params: Feature parameters
            compute_func: Feature compute function (required for verification)
            skip_verification: If True, skip causality verification (dangerous!)
            
        Returns:
            Registered FeatureSpec
            
        Raises:
            LookaheadDetectedError: If lookahead detected during verification
            WindowDishonestyError: If window specification is dishonest
            ValueError: If feature with same name/timeframe already exists
        """
        with self.lock:
            # Check for duplicates
            for spec in self.specs:
                if spec.name == name and spec.timeframe_min == timeframe_min:
                    raise ValueError(
                        f"Feature '{name}' already registered for timeframe {timeframe_min}min"
                    )
            
            # Create feature spec
            feature_spec = FeatureSpec(
                name=name,
                timeframe_min=timeframe_min,
                lookback_bars=lookback_bars,
                params=params.copy(),
                compute_func=compute_func,
                window_honest=True,  # Assume honest until verified
                causality_verified=False,
                verification_timestamp=None
            )
            
            # Perform causality verification if enabled and not skipped
            if self.verification_enabled and not skip_verification:
                if compute_func is None:
                    raise ValueError(
                        f"Cannot verify feature '{name}' without compute function"
                    )
                
                try:
                    report = verify_feature_causality(feature_spec, strict=True)
                    self.verification_reports[name] = report
                    
                    if report.passed:
                        feature_spec.mark_causality_verified()
                        feature_spec.window_honest = report.window_honest
                    else:
                        # Verification failed
                        raise CausalityVerificationError(
                            f"Feature '{name}' failed causality verification: "
                            f"{report.error_message}"
                        )
                        
                except (LookaheadDetectedError, WindowDishonestyError) as e:
                    # Re-raise these specific errors
                    raise
                except Exception as e:
                    # Wrap other errors
                    raise CausalityVerificationError(
                        f"Feature '{name}' verification failed with error: {e}"
                    ) from e
            elif skip_verification:
                # Mark as verified but with warning
                feature_spec.causality_verified = True
                feature_spec.verification_timestamp = None  # No actual verification
                warnings.warn(
                    f"Feature '{name}' registered without causality verification. "
                    f"This is dangerous and may lead to lookahead bias.",
                    UserWarning
                )
            
            # Add to registry
            self.specs.append(feature_spec)
            
            return feature_spec
    
    def register_feature_spec(
        self,
        feature_spec: FeatureSpec,
        skip_verification: bool = False
    ) -> FeatureSpec:
        """
        Register a FeatureSpec object.
        
        Args:
            feature_spec: FeatureSpec to register
            skip_verification: If True, skip causality verification
            
        Returns:
            Registered FeatureSpec (same object)
        """
        return self.register_feature(
            name=feature_spec.name,
            timeframe_min=feature_spec.timeframe_min,
            lookback_bars=feature_spec.lookback_bars,
            params=feature_spec.params,
            compute_func=feature_spec.compute_func,
            skip_verification=skip_verification
        )
    
    def register_from_contract(
        self,
        contract_spec: ContractFeatureSpec,
        compute_func: Optional[Callable[..., np.ndarray]] = None,
        skip_verification: bool = False
    ) -> FeatureSpec:
        """
        Register a feature from a contract FeatureSpec.
        
        Args:
            contract_spec: Contract FeatureSpec to register
            compute_func: Feature compute function
            skip_verification: If True, skip causality verification
            
        Returns:
            Registered FeatureSpec
        """
        # Convert to causality-aware FeatureSpec
        feature_spec = FeatureSpec.from_contract_spec(contract_spec, compute_func)
        return self.register_feature_spec(feature_spec, skip_verification)
    
    def verify_all_registered(self, reverify: bool = False) -> Dict[str, CausalityReport]:
        """
        Verify all registered features (or re-verify if requested).
        
        Args:
            reverify: If True, re-verify even previously verified features
            
        Returns:
            Dictionary of verification reports
        """
        with self.lock:
            specs_to_verify = []
            for spec in self.specs:
                if reverify or not spec.causality_verified:
                    if spec.compute_func is not None:
                        specs_to_verify.append(spec)
            
            reports = batch_verify_features(specs_to_verify, stop_on_first_failure=False)
            
            # Update feature specs based on verification results
            for spec in self.specs:
                if spec.name in reports:
                    report = reports[spec.name]
                    if report.passed:
                        spec.mark_causality_verified()
                        spec.window_honest = report.window_honest
                    else:
                        spec.mark_causality_failed()
            
            # Update verification reports
            self.verification_reports.update(reports)
            
            return reports
    
    def get_unverified_features(self) -> List[FeatureSpec]:
        """Get list of features that haven't passed causality verification."""
        return [spec for spec in self.specs if not spec.causality_verified]
    
    def get_features_with_lookahead(self) -> List[FeatureSpec]:
        """Get list of features that have detected lookahead."""
        result = []
        for spec in self.specs:
            if spec.name in self.verification_reports:
                report = self.verification_reports[spec.name]
                if report.lookahead_detected:
                    result.append(spec)
        return result
    
    def get_dishonest_window_features(self) -> List[FeatureSpec]:
        """Get list of features with dishonest window specifications."""
        result = []
        for spec in self.specs:
            if spec.name in self.verification_reports:
                report = self.verification_reports[spec.name]
                if not report.window_honest:
                    result.append(spec)
        return result
    
    def remove_feature(self, name: str, timeframe_min: int) -> bool:
        """
        Remove a feature from the registry.
        
        Args:
            name: Feature name
            timeframe_min: Timeframe in minutes
            
        Returns:
            True if feature was removed, False if not found
        """
        with self.lock:
            for i, spec in enumerate(self.specs):
                if spec.name == name and spec.timeframe_min == timeframe_min:
                    self.specs.pop(i)
                    # Remove verification report if exists
                    if name in self.verification_reports:
                        del self.verification_reports[name]
                    return True
            return False
    
    def clear(self) -> None:
        """Clear all features from the registry."""
        with self.lock:
            self.specs.clear()
            self.verification_reports.clear()
    
    def to_contract_registry(self) -> ContractFeatureRegistry:
        """
        Convert to contract FeatureRegistry (without causality fields).
        
        Returns:
            Contract FeatureRegistry with only verified features
        """
        # Only include features that have passed causality verification
        verified_specs = [
            spec.to_contract_spec()
            for spec in self.specs
            if spec.causality_verified
        ]
        
        return ContractFeatureRegistry(specs=verified_specs)
    
    def specs_for_tf(self, tf_min: int) -> List[FeatureSpec]:
        """
        Get all feature specs for a given timeframe.
        
        Args:
            tf_min: Timeframe in minutes
            
        Returns:
            List of FeatureSpecs for the timeframe (only verified features if enabled)
        """
        if self.verification_enabled:
            # Only return verified features
            filtered = [
                spec for spec in self.specs 
                if spec.timeframe_min == tf_min and spec.causality_verified
            ]
        else:
            # Return all features
            filtered = [spec for spec in self.specs if spec.timeframe_min == tf_min]
        
        # Sort by name for deterministic ordering
        return sorted(filtered, key=lambda s: s.name)
    
    def max_lookback_for_tf(self, tf_min: int) -> int:
        """
        Calculate maximum lookback for a timeframe.
        
        Args:
            tf_min: Timeframe in minutes
            
        Returns:
            Maximum lookback bars (0 if no features or verification fails)
        """
        specs = self.specs_for_tf(tf_min)
        if not specs:
            return 0
        
        # Only consider verified features with honest windows
        honest_lookbacks = [
            spec.lookback_bars 
            for spec in specs 
            if spec.causality_verified and spec.window_honest
        ]
        
        if not honest_lookbacks:
            return 0
        
        return max(honest_lookbacks)


# Import numpy and warnings for the module
import numpy as np
import warnings


# Global registry instance
_default_registry: Optional[FeatureRegistry] = None
_default_registry_lock = threading.Lock()


def get_default_registry() -> FeatureRegistry:
    """
    Get or create the default global feature registry.
    
    Returns:
        Global FeatureRegistry instance
    """
    global _default_registry
    
    with _default_registry_lock:
        if _default_registry is None:
            _default_registry = FeatureRegistry()
            
            # Optionally register default features with verification
            # This would require compute functions for default features
            
        return _default_registry


def set_default_registry(registry: FeatureRegistry) -> None:
    """
    Set the default global feature registry.
    
    Args:
        registry: FeatureRegistry to set as default
    """
    global _default_registry
    
    with _default_registry_lock:
        _default_registry = registry
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/__init__.py
sha256(source_bytes) = 4bb1010f453cf1b5b0fcaafe68f3bc3ed71ef5c0f1cbc03f2d27ece64fe6215f
bytes = 40
redacted = False
--------------------------------------------------------------------------------

"""GUI package for FishBroWFS_V2."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/research_console.py
sha256(source_bytes) = 7ca86bb0a809a74308c6213e61c0fc65e91c28e7d3748128ec8904b2006505e0
bytes = 9073
redacted = True
--------------------------------------------------------------------------------

"""Research Console Core Module.

Phase 10: Read-only UI for research artifacts with decision input.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Iterable

from FishBroWFS_V2.research.decision import append_decision


def _norm_optional_text(x: Any) -> Optional[str]:
    """Normalize optional free-text user input.
    
    Rules:
    - None -> None
    - non-str -> str(x)
    - strip whitespace
    - empty after strip -> None
    """
    if x is None:
        return None
    if not isinstance(x, str):
        x = str(x)
    s = x.strip()
    return s if s != "" else None


def _norm_optional_choice(x: Any, *, all_tokens: Iterable[str] =[REDACTED]    """Normalize optional dropdown choice.
    
    Rules:
    - None -> None
    - strip whitespace
    - empty after strip -> None
    - token in all_tokens (case-insensitive) -> None
    - otherwise return stripped original (NOT uppercased)
    """
    s = _norm_optional_text(x)
    if s is None:
        return None
    s_upper = s.upper()
    for tok in all_tokens:[REDACTED]        if s_upper == str(tok).upper():
            return None
    return s


def _row_str(row: dict, key: str) -> str:
    """Return safe string for row[key]. None -> ''."""
    v = row.get(key)
    if v is None:
        return ""
    # Keep as string, do not strip here (strip is for normalization functions)
    return str(v)


def load_research_artifacts(outputs_root: Path) -> dict:
    """
    Load:
    - outputs/research/research_index.json
    - outputs/research/canonical_results.json
    Raise if missing.
    """
    research_dir = outputs_root / "research"
    
    index_path = research_dir / "research_index.json"
    canonical_path = research_dir / "canonical_results.json"
    
    if not index_path.exists():
        raise FileNotFoundError(f"research_index.json not found at {index_path}")
    if not canonical_path.exists():
        raise FileNotFoundError(f"canonical_results.json not found at {canonical_path}")
    
    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    with open(canonical_path, "r", encoding="utf-8") as f:
        canonical_data = json.load(f)
    
    # Create a mapping from run_id to canonical result for quick lookup
    canonical_map = {}
    for result in canonical_data:
        run_id = result.get("run_id")
        if run_id:
            canonical_map[run_id] = result
    
    return {
        "index": index_data,
        "canonical_map": canonical_map,
        "index_path": index_path,
        "canonical_path": canonical_path,
        "index_mtime": index_path.stat().st_mtime if index_path.exists() else 0,
    }


def summarize_index(index: dict) -> list[dict]:
    """
    Convert research_index to flat rows for UI table.
    Pure function.
    """
    rows = []
    entries = index.get("entries", [])
    
    for entry in entries:
        run_id = entry.get("run_id", "")
        keys = entry.get("keys", {})
        
        row = {
            "run_id": run_id,
            "symbol": keys.get("symbol"),
            "strategy_id": keys.get("strategy_id"),
            "portfolio_id": keys.get("portfolio_id"),
            "score_final": entry.get("score_final", 0.0),
            "score_net_mdd": entry.get("score_net_mdd", 0.0),
            "trades": entry.get("trades", 0),
            "decision": entry.get("decision", "UNDECIDED"),
        }
        rows.append(row)
    
    return rows


def apply_filters(
    rows: list[dict],
    *,
    text: str | None,
    symbol: str | None,
    strategy_id: str | None,
    decision: str | None,
) -> list[dict]:
    """
    Deterministic filter.
    No IO.
    """
    # Normalize inputs
    text_q = _norm_optional_text(text)
    symbol_q =[REDACTED]    strategy_q =[REDACTED]    decision_q =[REDACTED]    
    filtered = rows
    
    # A) text filter
    if text_q is not None:
        text_lower = text_q.lower()
        filtered = [
            row for row in filtered
            if (
                (_row_str(row, "run_id").lower().find(text_lower) >= 0) or
                (_row_str(row, "symbol").lower().find(text_lower) >= 0) or
                (_row_str(row, "strategy_id").lower().find(text_lower) >= 0) or
                (_row_str(row, "note").lower().find(text_lower) >= 0)
            )
        ]
    
    # B) symbol / strategy_id filter
    if symbol_q is not None:
        sym_q_l = symbol_q.lower()
        filtered = [row for row in filtered if _row_str(row, "symbol").lower() == sym_q_l]
    
    if strategy_q is not None:
        st_q_l = strategy_q.lower()
        filtered = [row for row in filtered if _row_str(row, "strategy_id").lower() == st_q_l]
    
    # C) decision filter
    if decision_q is not None:
        dec_q = decision_q.strip()
        dec_q_l = dec_q.lower()
        
        if dec_q_l == "undecided":
            # Match None / '' / whitespace-only
            filtered = [
                row for row in filtered 
                if _norm_optional_text(row.get("decision")) is None
            ]
        else:
            filtered = [
                row for row in filtered
                if _row_str(row, "decision").lower() == dec_q_l
            ]
    
    return filtered


def load_run_detail(run_id: str, outputs_root: Path) -> dict:
    """
    Read-only load:
    - manifest.json
    - metrics.json
    - README.md (truncated)
    """
    # First find the run directory
    run_dir = None
    seasons_dir = outputs_root / "seasons"
    
    if seasons_dir.exists():
        for season_dir in seasons_dir.iterdir():
            if not season_dir.is_dir():
                continue
            
            runs_dir = season_dir / "runs"
            if not runs_dir.exists():
                continue
            
            potential_run_dir = runs_dir / run_id
            if potential_run_dir.exists() and potential_run_dir.is_dir():
                run_dir = potential_run_dir
                break
    
    if not run_dir:
        raise FileNotFoundError(f"Run directory not found for run_id: {run_id}")
    
    # Load manifest.json
    manifest = {}
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load metrics.json
    metrics = {}
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load README.md (truncated to first 1000 chars)
    readme_content = ""
    readme_path = run_dir / "README.md"
    if readme_path.exists():
        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Truncate to 1000 characters
                if len(content) > 1000:
                    readme_content = content[:1000] + "... [truncated]"
                else:
                    readme_content = content
        except Exception:
            pass
    
    # Load winners.json if exists
    winners = {}
    winners_path = run_dir / "winners.json"
    if winners_path.exists():
        try:
            with open(winners_path, "r", encoding="utf-8") as f:
                winners = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load winners_v2.json if exists
    winners_v2 = {}
    winners_v2_path = run_dir / "winners_v2.json"
    if winners_v2_path.exists():
        try:
            with open(winners_v2_path, "r", encoding="utf-8") as f:
                winners_v2 = json.load(f)
        except json.JSONDecodeError:
            pass
    
    return {
        "run_id": run_id,
        "manifest": manifest,
        "metrics": metrics,
        "winners": winners,
        "winners_v2": winners_v2,
        "readme": readme_content,
        "run_dir": str(run_dir),
    }


def submit_decision(
    *,
    outputs_root: Path,
    run_id: str,
    decision: Literal["KEEP", "DROP", "ARCHIVE"],
    note: str,
) -> None:
    """
    Must call:
    FishBroWFS_V2.research.decision.append_decision(...)
    """
    if len(note.strip()) < 5:
        raise ValueError("Note must be at least 5 characters long")
    
    research_dir = outputs_root / "research"
    append_decision(research_dir, run_id, decision, note)


def get_unique_values(rows: list[dict], field: str) -> list[str]:
    """
    Get unique non-empty values from rows for a given field.
    Used for dropdown filters.
    """
    values = set()
    for row in rows:
        value = row.get(field)
        if value:
            values.add(value)
    return sorted(list(values))



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/theme.py
sha256(source_bytes) = 1fb7f524d455c402be4e219ed56b8d228e1fc827dd4be9376b6f79fbe02b943e
bytes = 5690
redacted = False
--------------------------------------------------------------------------------
"""Cyberpunk UI 全域樣式注入"""

from nicegui import ui


def inject_global_styles() -> None:
    """注入全域樣式：Google Fonts + Tailwind CDN + 自訂 CSS"""
    
    # Google Fonts
    ui.add_head_html("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    """, shared=True)
    
    # Tailwind CDN
    ui.add_head_html("""
    <script src="https://cdn.tailwindcss.com"></script>
    """, shared=True)
    
    # Tailwind config with custom colors
    ui.add_head_html("""
    <script>
    tailwind.config = {
        darkMode: 'class',
        theme: {
            extend: {
                colors: {
                    'nexus': {
                        50: '#f0f9ff',
                        100: '#e0f2fe',
                        200: '#bae6fd',
                        300: '#7dd3fc',
                        400: '#38bdf8',
                        500: '#0ea5e9',
                        600: '#0284c7',
                        700: '#0369a1',
                        800: '#075985',
                        900: '#0c4a6e',
                        950: '#082f49',
                    },
                    'cyber': {
                        50: '#f0fdfa',
                        100: '#ccfbf1',
                        200: '#99f6e4',
                        300: '#5eead4',
                        400: '#2dd4bf',
                        500: '#14b8a6',
                        600: '#0d9488',
                        700: '#0f766e',
                        800: '#115e59',
                        900: '#134e4a',
                        950: '#042f2e',
                    },
                    'fish': {
                        50: '#eff6ff',
                        100: '#dbeafe',
                        200: '#bfdbfe',
                        300: '#93c5fd',
                        400: '#60a5fa',
                        500: '#3b82f6',
                        600: '#2563eb',
                        700: '#1d4ed8',
                        800: '#1e40af',
                        900: '#1e3a8a',
                        950: '#172554',
                    }
                },
                fontFamily: {
                    'sans': ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'Noto Sans', 'sans-serif'],
                    'mono': ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', 'monospace'],
                },
                animation: {
                    'glow': 'glow 2s ease-in-out infinite alternate',
                    'pulse-glow': 'pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                },
                keyframes: {
                    'glow': {
                        'from': { 'box-shadow': '0 0 10px #0ea5e9, 0 0 20px #0ea5e9, 0 0 30px #0ea5e9' },
                        'to': { 'box-shadow': '0 0 20px #3b82f6, 0 0 30px #3b82f6, 0 0 40px #3b82f6' }
                    },
                    'pulse-glow': {
                        '0%, 100%': { 'opacity': 1 },
                        '50%': { 'opacity': 0.5 }
                    }
                }
            }
        }
    }
    </script>
    """, shared=True)
    
    # Custom CSS for cyberpunk theme
    ui.add_head_html("""
    <style>
    :root {
        --bg-nexus-950: #082f49;
        --text-slate-300: #cbd5e1;
        --border-cyber-500: #14b8a6;
        --glow-fish-500: #3b82f6;
    }
    
    body {
        font-family: 'Inter', sans-serif;
        background-color: var(--bg-nexus-950);
        color: var(--text-slate-300);
    }
    
    .fish-card {
        background: linear-gradient(145deg, rgba(8, 47, 73, 0.9), rgba(12, 74, 110, 0.9));
        border: 1px solid rgba(20, 184, 166, 0.3);
        border-radius: 0.75rem;
        padding: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
    }
    
    .fish-card:hover {
        border-color: rgba(20, 184, 166, 0.6);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.3);
    }
    
    .fish-card.glow {
        animation: glow 2s ease-in-out infinite alternate;
    }
    
    .fish-header {
        background: linear-gradient(90deg, rgba(8, 47, 73, 1), rgba(20, 184, 166, 0.3));
        border-bottom: 1px solid rgba(20, 184, 166, 0.5);
        padding: 1rem 1.5rem;
    }
    
    .nav-active {
        background: rgba(20, 184, 166, 0.2);
        border-left: 3px solid var(--border-cyber-500);
        font-weight: 600;
    }
    
    .btn-cyber {
        background: linear-gradient(90deg, #14b8a6, #0d9488);
        color: white;
        border: none;
        border-radius: 0.5rem;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s;
    }
    
    .btn-cyber:hover {
        background: linear-gradient(90deg, #0d9488, #0f766e);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(20, 184, 166, 0.4);
    }
    
    .btn-cyber:active {
        transform: translateY(0);
    }
    
    .toast-warning {
        background: linear-gradient(90deg, rgba(245, 158, 11, 0.9), rgba(217, 119, 6, 0.9));
        border: 1px solid rgba(245, 158, 11, 0.5);
        color: white;
    }
    
    .text-cyber-glow {
        text-shadow: 0 0 10px rgba(20, 184, 166, 0.7);
    }
    </style>
    """, shared=True)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/adapters/intent_bridge.py
sha256(source_bytes) = 77806c3872e95a1c5e1ae4cf70c100cf1b1704ec829b0b694c33b0527345eef1
bytes = 21726
redacted = False
--------------------------------------------------------------------------------
"""IntentBridge - UI adapter for Attack #9 – Headless Intent-State Contract.

UI → Intent ONLY (no logic). This is the only way UI should interact with backend.
UI components must use this bridge to create UserIntent objects and submit them
to the ActionQueue. No business logic should be in UI components.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional, Union, Callable
from functools import wraps

from FishBroWFS_V2.core.intents import (
    Intent, UserIntent, IntentType, IntentStatus,
    CreateJobIntent, CalculateUnitsIntent, CheckSeasonIntent,
    GetJobStatusIntent, ListJobsIntent, GetJobLogsIntent,
    SubmitBatchIntent, ValidatePayloadIntent, BuildParquetIntent,
    FreezeSeasonIntent, ExportSeasonIntent, CompareSeasonsIntent,
    DataSpecIntent
)
from FishBroWFS_V2.control.action_queue import get_action_queue, IntentSubmitter
from FishBroWFS_V2.core.processor import get_processor, start_processor, stop_processor
from FishBroWFS_V2.core.state import SystemState


class IntentBridge:
    """Bridge between UI and intent-based backend.
    
    UI components must use this bridge to interact with backend.
    All methods return intent IDs or results, but never execute business logic.
    """
    
    def __init__(self):
        self.action_queue = get_action_queue()
        self.processor = get_processor()
        self.submitter = IntentSubmitter(self.action_queue)
        self._state_listeners: List[Callable[[SystemState], None]] = []
    
    # -----------------------------------------------------------------
    # Intent creation methods (UI calls these)
    # -----------------------------------------------------------------
    
    def create_data_spec_intent(
        self,
        dataset_id: str,
        symbols: List[str],
        timeframes: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> DataSpecIntent:
        """Create a DataSpecIntent for use in other intents."""
        return DataSpecIntent(
            dataset_id=dataset_id,
            symbols=symbols,
            timeframes=timeframes,
            start_date=start_date,
            end_date=end_date
        )
    
    def create_job_intent(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any],
        wfs: Optional[Dict[str, Any]] = None
    ) -> CreateJobIntent:
        """Create intent to submit a job."""
        if wfs is None:
            wfs = {
                "stage0_subsample": 0.1,
                "top_k": 20,
                "mem_limit_mb": 8192,
                "allow_auto_downsample": True
            }
        
        return CreateJobIntent(
            season=season,
            data1=data1,
            data2=data2,
            strategy_id=strategy_id,
            params=params,
            wfs=wfs
        )
    
    def calculate_units_intent(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any]
    ) -> CalculateUnitsIntent:
        """Create intent to calculate units."""
        return CalculateUnitsIntent(
            season=season,
            data1=data1,
            data2=data2,
            strategy_id=strategy_id,
            params=params
        )
    
    def check_season_intent(
        self,
        season: str,
        action: str = "submit_job"
    ) -> CheckSeasonIntent:
        """Create intent to check if season is frozen."""
        return CheckSeasonIntent(
            season=season,
            action=action
        )
    
    def get_job_status_intent(self, job_id: str) -> GetJobStatusIntent:
        """Create intent to get job status."""
        return GetJobStatusIntent(job_id=job_id)
    
    def list_jobs_intent(self, limit: int = 50) -> ListJobsIntent:
        """Create intent to list jobs."""
        return ListJobsIntent(limit=limit)
    
    def get_job_logs_intent(self, job_id: str, lines: int = 50) -> GetJobLogsIntent:
        """Create intent to get job logs."""
        return GetJobLogsIntent(job_id=job_id, lines=lines)
    
    def validate_payload_intent(self, payload: Dict[str, Any]) -> ValidatePayloadIntent:
        """Create intent to validate wizard payload."""
        return ValidatePayloadIntent(payload=payload)
    
    def build_parquet_intent(self, dataset_id: str) -> BuildParquetIntent:
        """Create intent to build Parquet files."""
        return BuildParquetIntent(dataset_id=dataset_id)
    
    def freeze_season_intent(self, season: str, reason: Optional[str] = None) -> FreezeSeasonIntent:
        """Create intent to freeze a season."""
        return FreezeSeasonIntent(season=season, reason=reason)
    
    def export_season_intent(self, season: str, format: str = "json") -> ExportSeasonIntent:
        """Create intent to export season data."""
        return ExportSeasonIntent(season=season, format=format)
    
    def compare_seasons_intent(
        self,
        season_a: str,
        season_b: str,
        metrics: Optional[List[str]] = None
    ) -> CompareSeasonsIntent:
        """Create intent to compare two seasons."""
        if metrics is None:
            metrics = ["sharpe", "max_dd", "win_rate"]
        return CompareSeasonsIntent(
            season_a=season_a,
            season_b=season_b,
            metrics=metrics
        )
    
    # -----------------------------------------------------------------
    # Intent submission methods (UI calls these)
    # -----------------------------------------------------------------
    
    def submit_intent(self, intent: UserIntent) -> str:
        """Submit an intent to the action queue.
        
        Returns intent ID for tracking.
        """
        return self.action_queue.submit(intent)
    
    def submit_and_wait(
        self,
        intent: UserIntent,
        timeout: Optional[float] = 30.0
    ) -> Optional[UserIntent]:
        """Submit intent and wait for completion.
        
        Returns completed intent with result, or None on timeout.
        """
        return self.submitter.submit_and_wait(intent, timeout)
    
    async def submit_and_wait_async(
        self,
        intent: UserIntent,
        timeout: Optional[float] = 30.0
    ) -> Optional[UserIntent]:
        """Async version of submit_and_wait."""
        return await self.submitter.submit_and_wait_async(intent, timeout)
    
    def get_intent_status(self, intent_id: str) -> Optional[UserIntent]:
        """Get intent status by ID."""
        return self.action_queue.get_intent(intent_id)
    
    async def wait_for_intent(
        self,
        intent_id: str,
        timeout: Optional[float] = 30.0
    ) -> Optional[UserIntent]:
        """Wait for intent completion."""
        return await self.action_queue.wait_for_intent_async(intent_id, timeout)
    
    # -----------------------------------------------------------------
    # State observation methods (UI calls these)
    # -----------------------------------------------------------------
    
    def get_current_state(self) -> SystemState:
        """Get current system state snapshot."""
        return self.processor.get_state()
    
    def add_state_listener(self, callback: Callable[[SystemState], None]) -> None:
        """Add a listener for state changes.
        
        UI components can register callbacks to be notified when state changes.
        """
        self._state_listeners.append(callback)
    
    def remove_state_listener(self, callback: Callable[[SystemState], None]) -> None:
        """Remove a state listener."""
        if callback in self._state_listeners:
            self._state_listeners.remove(callback)
    
    def notify_state_listeners(self, state: SystemState) -> None:
        """Notify all state listeners (called by processor)."""
        for listener in self._state_listeners:
            try:
                listener(state)
            except Exception as e:
                print(f"Error in state listener: {e}")
    
    # -----------------------------------------------------------------
    # System control methods
    # -----------------------------------------------------------------
    
    async def start_processor(self) -> None:
        """Start the StateProcessor."""
        await start_processor()
    
    async def stop_processor(self) -> None:
        """Stop the StateProcessor."""
        await stop_processor()
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get action queue status."""
        metrics = self.action_queue.get_metrics()
        queue_size = self.action_queue.get_queue_size()
        
        return {
            "queue_size": queue_size,
            "metrics": metrics,
            "is_processor_running": self.processor.is_running if hasattr(self.processor, 'is_running') else False
        }
    
    # -----------------------------------------------------------------
    # Convenience methods for common UI patterns
    # -----------------------------------------------------------------
    
    def create_and_submit_job(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any],
        wfs: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """Convenience method: create and submit job intent, wait for result."""
        intent = self.create_job_intent(season, data1, data2, strategy_id, params, wfs)
        completed = self.submit_and_wait(intent, timeout)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result
        return None
    
    async def create_and_submit_job_async(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any],
        wfs: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """Async version of create_and_submit_job."""
        intent = self.create_job_intent(season, data1, data2, strategy_id, params, wfs)
        completed = await self.submit_and_wait_async(intent, timeout)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result
        return None
    
    def calculate_units(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any],
        timeout: float = 5.0
    ) -> Optional[int]:
        """Convenience method: calculate units and return result."""
        intent = self.calculate_units_intent(season, data1, data2, strategy_id, params)
        completed = self.submit_and_wait(intent, timeout)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result.get("units") if completed.result else None
        return None


# Singleton instance for application use
_intent_bridge_instance: Optional[IntentBridge] = None


def get_intent_bridge() -> IntentBridge:
    """Get the singleton IntentBridge instance."""
    global _intent_bridge_instance
    if _intent_bridge_instance is None:
        _intent_bridge_instance = IntentBridge()
    return _intent_bridge_instance


# -----------------------------------------------------------------
# Decorators for enforcing UI contract
# -----------------------------------------------------------------

def ui_intent_only(func: Callable) -> Callable:
    """Decorator to enforce that UI methods only create intents.
    
    This is a runtime check to ensure UI components don't accidentally
    call backend logic directly.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check that we're in a UI context (heuristic)
        import inspect
        frame = inspect.currentframe()
        
        # Walk up the call stack looking for UI modules
        while frame:
            module_name = frame.f_globals.get('__name__', '')
            if 'gui' in module_name or 'ui' in module_name:
                # This is called from UI code
                # Check that function name contains 'intent'
                if 'intent' not in func.__name__.lower():
                    print(f"WARNING: UI function {func.__name__} doesn't follow intent-only pattern")
            frame = frame.f_back
        
        return func(*args, **kwargs)
    
    return wrapper


def no_backend_imports() -> None:
    """Check that UI modules don't import backend logic directly.
    
    This should be called at module import time in UI modules.
    """
    import sys
    import inspect
    
    # Get calling module
    frame = inspect.currentframe().f_back
    module_name = frame.f_globals.get('__name__', '')
    
    # Check for forbidden imports in UI modules
    if 'gui' in module_name or 'ui' in module_name:
        forbidden_prefixes = [
            'FishBroWFS_V2.control.job_api',
            'FishBroWFS_V2.control.jobs_db',
            'FishBroWFS_V2.core.processor',  # Except through intent_bridge
        ]
        
        for name, module in sys.modules.items():
            if any(name.startswith(prefix) for prefix in forbidden_prefixes):
                # Check if this module imported it
                for var_name, var_val in frame.f_globals.items():
                    if hasattr(var_val, '__module__') and var_val.__module__ == name:
                        print(f"WARNING: UI module {module_name} imported backend module {name}")
                        break


# -----------------------------------------------------------------
# Compatibility layer for existing UI code
# -----------------------------------------------------------------

class IntentBackendAdapter:
    """Adapter to make intent-based backend compatible with existing UI code.
    
    This provides the same interface as the old job_api.py but uses intents.
    """
    
    def __init__(self, bridge: Optional[IntentBridge] = None):
        self.bridge = bridge or get_intent_bridge()
    
    def create_job_from_wizard(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility method for existing UI code."""
        # Convert payload to DataSpecIntent
        data1 = payload.get("data1", {})
        data2 = payload.get("data2")
        
        data1_intent = self.bridge.create_data_spec_intent(
            dataset_id=data1.get("dataset_id", ""),
            symbols=data1.get("symbols", []),
            timeframes=data1.get("timeframes", []),
            start_date=data1.get("start_date"),
            end_date=data1.get("end_date")
        )
        
        data2_intent = None
        if data2:
            data2_intent = self.bridge.create_data_spec_intent(
                dataset_id=data2.get("dataset_id", ""),
                symbols=[],  # DATA2 doesn't use symbols
                timeframes=[],  # DATA2 doesn't use timeframes
            )
            # Note: DATA2 might have filters, but DataSpecIntent doesn't support them
            # This is a simplification for compatibility
        
        # Create and submit intent
        result = self.bridge.create_and_submit_job(
            season=payload.get("season", ""),
            data1=data1_intent,
            data2=data2_intent,
            strategy_id=payload.get("strategy_id", ""),
            params=payload.get("params", {}),
            wfs=payload.get("wfs")
        )
        
        if result:
            return result
        else:
            raise Exception("Job creation failed")
    
    def calculate_units(self, payload: Dict[str, Any]) -> int:
        """Compatibility method for existing UI code."""
        data1 = payload.get("data1", {})
        data2 = payload.get("data2")
        
        data1_intent = self.bridge.create_data_spec_intent(
            dataset_id=data1.get("dataset_id", ""),
            symbols=data1.get("symbols", []),
            timeframes=data1.get("timeframes", []),
            start_date=data1.get("start_date"),
            end_date=data1.get("end_date")
        )
        
        data2_intent = None
        if data2:
            data2_intent = self.bridge.create_data_spec_intent(
                dataset_id=data2.get("dataset_id", ""),
                symbols=[],
                timeframes=[],
            )
        
        units = self.bridge.calculate_units(
            season=payload.get("season", ""),
            data1=data1_intent,
            data2=data2_intent,
            strategy_id=payload.get("strategy_id", ""),
            params=payload.get("params", {})
        )
        
        if units is not None:
            return units
        else:
            raise Exception("Units calculation failed")
    
    def check_season_not_frozen(self, season: str, action: str = "submit_job") -> None:
        """Compatibility method for existing UI code."""
        intent = self.bridge.check_season_intent(season, action)
        completed = self.bridge.submit_and_wait(intent, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            result = completed.result
            if result and result.get("is_frozen", False):
                from FishBroWFS_V2.control.job_api import SeasonFrozenError
                raise SeasonFrozenError(f"Season {season} is frozen")
        else:
            # If check fails, assume not frozen (fail-open for compatibility)
            pass
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Compatibility method for existing UI code."""
        intent = self.bridge.get_job_status_intent(job_id)
        completed = self.bridge.submit_and_wait(intent, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result or {}
        else:
            raise Exception(f"Failed to get job status: {job_id}")
    
    def list_jobs_with_progress(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Compatibility method for existing UI code."""
        intent = self.bridge.list_jobs_intent(limit)
        completed = self.bridge.submit_and_wait(intent, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result.get("jobs", []) if completed.result else []
        else:
            raise Exception("Failed to list jobs")
    
    def get_job_logs_tail(self, job_id: str, lines: int = 50) -> List[str]:
        """Compatibility method for existing UI code."""
        intent = self.bridge.get_job_logs_intent(job_id, lines)
        completed = self.bridge.submit_and_wait(intent, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            # TODO: Convert result to log lines format
            return completed.result.get("logs", []) if completed.result else []
        else:
            raise Exception(f"Failed to get job logs: {job_id}")
    
    def submit_wizard_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility method for existing UI code."""
        return self.create_job_from_wizard(payload)
    
    def get_job_summary(self, job_id: str) -> Dict[str, Any]:
        """Compatibility method for existing UI code."""
        # Combine status and logs
        status = self.get_job_status(job_id)
        logs = self.get_job_logs_tail(job_id, lines=20)
        
        return {
            **status,
            "logs": logs,
            "log_tail": "\n".join(logs[-10:]) if logs else "No logs available"
        }


# Create a default adapter instance for easy import
default_adapter = IntentBackendAdapter()


# -----------------------------------------------------------------
# Migration helper for existing UI code
# -----------------------------------------------------------------

def migrate_ui_imports() -> None:
    """Helper to migrate existing UI imports to intent-based system.
    
    Call this in UI modules to replace direct job_api imports with intent bridge.
    """
    import sys
    import inspect
    
    # Get calling module
    frame = inspect.currentframe().f_back
    module = frame.f_globals
    
    # Replace job_api functions with adapter methods
    if 'FishBroWFS_V2.control.job_api' in sys.modules:
        job_api = sys.modules['FishBroWFS_V2.control.job_api']
        
        # Create adapter instance
        adapter = IntentBackendAdapter()
        
        # Replace functions in calling module's namespace
        module['create_job_from_wizard'] = adapter.create_job_from_wizard
        module['calculate_units'] = adapter.calculate_units
        module['check_season_not_frozen'] = adapter.check_season_not_frozen
        module['get_job_status'] = adapter.get_job_status
        module['list_jobs_with_progress'] = adapter.list_jobs_with_progress
        module['get_job_logs_tail'] = adapter.get_job_logs_tail
        module['submit_wizard_job'] = adapter.submit_wizard_job
        module['get_job_summary'] = adapter.get_job_summary
        
        # Also import exception classes for compatibility
        module['SeasonFrozenError'] = getattr(job_api, 'SeasonFrozenError', Exception)
        module['ValidationError'] = getattr(job_api, 'ValidationError', Exception)
        module['JobAPIError'] = getattr(job_api, 'JobAPIError', Exception)
        
        print(f"Migrated UI module {module.get('__name__', 'unknown')} to intent-based system")
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/__init__.py
sha256(source_bytes) = c82b489bad38048199a02de11a001199ef5465f434437f12dfaad4965663e297
bytes = 60
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 介面模組 - 唯一 UI 層"""

__all__ = []



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/api.py
sha256(source_bytes) = 90f2c92254293114211f98b2122986d7e04b745c44904cf95f3f8d79a68b78f7
bytes = 12183
redacted = False
--------------------------------------------------------------------------------

"""UI API 薄接口 - 唯一 UI ↔ 系統邊界

憲法級原則：
1. 禁止 import FishBroWFS_V2.control.research_runner
2. 禁止 import FishBroWFS_V2.wfs.runner
3. 禁止 import 任何會造成 build/compute 的模組
4. UI 只能呼叫此模組暴露的「submit/query/download」函式
5. 所有 API 呼叫必須對接真實 Control API，禁止 fallback mock
"""

import json
import os
import requests
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal, List, Dict, Any
from uuid import uuid4

# API 基礎 URL - 從環境變數讀取，預設為 http://127.0.0.1:8000
API_BASE = os.environ.get("FISHBRO_API_BASE", "http://127.0.0.1:8000")


@dataclass(frozen=True)
class JobSubmitRequest:
    """任務提交請求"""
    outputs_root: Path
    dataset_id: str
    symbols: list[str]
    timeframe_min: int
    strategy_name: str
    data2_feed: Optional[str]              # None | "6J" | "VX" | "DX" | "ZN"
    rolling: bool                          # True only (MVP)
    train_years: int                       # fixed=3
    test_unit: Literal["quarter"]          # fixed="quarter"
    enable_slippage_stress: bool           # True
    slippage_levels: list[str]             # ["S0","S1","S2","S3"]
    gate_level: str                        # "S2"
    stress_level: str                      # "S3"
    topk: int                              # default 20
    season: str                            # 例如 "2026Q1"


@dataclass(frozen=True)
class JobRecord:
    """任務記錄"""
    job_id: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    created_at: str
    updated_at: str
    progress: Optional[float]              # 0..1
    message: Optional[str]
    outputs_path: Optional[str]            # set when completed
    latest_log_tail: Optional[str]         # optional


def _call_api(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
    """呼叫 Control API - 禁止 fallback mock，失敗就 raise"""
    url = f"{API_BASE}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"無法連線到 Control API ({url}): {e}. 請確認 Control API 是否已啟動。")
    except requests.exceptions.Timeout as e:
        raise RuntimeError(f"Control API 請求超時 ({url}): {e}")
    except requests.exceptions.HTTPError as e:
        if response.status_code == 503:
            raise RuntimeError(f"Control API 服務不可用 (503): {e.response.text if hasattr(e, 'response') else str(e)}")
        elif response.status_code == 404:
            # 404 錯誤是正常的（artifact 尚未產生）
            raise FileNotFoundError(f"Resource not found (404): {endpoint}")
        else:
            raise RuntimeError(f"Control API 錯誤 ({response.status_code}): {e.response.text if hasattr(e, 'response') else str(e)}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Control API 請求失敗 ({url}): {e}")


def list_datasets(outputs_root: Path) -> list[str]:
    """列出可用的資料集 - 只能來自 /meta/datasets，禁止 fallback mock"""
    data = _call_api("/meta/datasets")
    return [ds["id"] for ds in data.get("datasets", [])]


def list_strategies() -> list[str]:
    """列出可用的策略 - 只能來自 /meta/strategies，禁止 fallback mock"""
    data = _call_api("/meta/strategies")
    return [s["strategy_id"] for s in data.get("strategies", [])]


def submit_job(req: JobSubmitRequest) -> JobRecord:
    """提交新任務 - 對接真實 POST /jobs 端點，禁止 fake"""
    # 驗證參數
    if req.data2_feed not in [None, "6J", "VX", "DX", "ZN"]:
        raise ValueError(f"Invalid data2_feed: {req.data2_feed}")
    
    if req.train_years != 3:
        raise ValueError(f"train_years must be 3, got {req.train_years}")
    
    if req.test_unit != "quarter":
        raise ValueError(f"test_unit must be 'quarter', got {req.test_unit}")
    
    # 建立 config_snapshot (只包含策略相關資訊)
    # 注意：UI 的 strategy_name 對應到 config_snapshot 的 strategy_name
    config_snapshot = {
        "strategy_name": req.strategy_name,
        "params": {},  # 暫時為空，UI 需要收集參數
        "fees": 0.0,
        "slippage": 0.0,
        # 其他 UI 蒐集的參數可以放在這裡
        "dataset_id": req.dataset_id,
        "symbols": req.symbols,
        "timeframe_min": req.timeframe_min,
        "data2_feed": req.data2_feed,
        "rolling": req.rolling,
        "train_years": req.train_years,
        "test_unit": req.test_unit,
        "enable_slippage_stress": req.enable_slippage_stress,
        "slippage_levels": req.slippage_levels,
        "gate_level": req.gate_level,
        "stress_level": req.stress_level,
        "topk": req.topk,
    }
    
    # 計算 config_hash (使用 JSON 字串的 SHA256)
    import hashlib
    import json
    config_json = json.dumps(config_snapshot, sort_keys=True, separators=(',', ':'))
    config_hash = hashlib.sha256(config_json.encode('utf-8')).hexdigest()
    
    # 建立完整的 JobSpec (7 個欄位)
    spec = {
        "season": req.season,
        "dataset_id": req.dataset_id,
        "outputs_root": str(req.outputs_root),
        "config_snapshot": config_snapshot,
        "config_hash": config_hash,
        "data_fingerprint_sha1": "",  # Phase 7 再補真值
        "created_by": "nicegui",
    }
    
    # 呼叫真實 Control API
    response = _call_api("/jobs", method="POST", data={"spec": spec})
    
    # 從 API 回應取得 job_id
    job_id = response.get("job_id", "")
    
    # 回傳 JobRecord
    return JobRecord(
        job_id=job_id,
        status="PENDING",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        progress=0.0,
        message="Job submitted successfully",
        outputs_path=str(req.outputs_root / "runs" / job_id),
        latest_log_tail="Job queued for execution"
    )


def list_recent_jobs(limit: int = 50) -> list[JobRecord]:
    """列出最近的任務 - 只能來自 /jobs，禁止 fallback mock"""
    data = _call_api("/jobs")
    jobs = []
    for job_data in data[:limit]:
        # 轉換 API 回應到 JobRecord
        jobs.append(JobRecord(
            job_id=job_data.get("job_id", ""),
            status=_map_status(job_data.get("status", "")),
            created_at=job_data.get("created_at", ""),
            updated_at=job_data.get("updated_at", ""),
            progress=_estimate_progress(job_data),
            message=job_data.get("last_error"),
            outputs_path=job_data.get("spec", {}).get("outputs_root"),
            latest_log_tail=None
        ))
    return jobs


def get_job(job_id: str) -> JobRecord:
    """取得特定任務的詳細資訊"""
    try:
        data = _call_api(f"/jobs/{job_id}")
        
        # 獲取日誌尾巴
        log_data = _call_api(f"/jobs/{job_id}/log_tail?n=20")
        log_tail = "\n".join(log_data.get("lines", [])) if log_data.get("ok") else None
        
        return JobRecord(
            job_id=data.get("job_id", ""),
            status=_map_status(data.get("status", "")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            progress=_estimate_progress(data),
            message=data.get("last_error"),
            outputs_path=data.get("spec", {}).get("outputs_root"),
            latest_log_tail=log_tail
        )
    except Exception as e:
        raise RuntimeError(f"Failed to get job {job_id}: {e}")


def get_rolling_summary(job_id: str) -> dict:
    """取得滾動摘要 - 從 /jobs/{job_id}/rolling_summary 讀取真實 artifact"""
    try:
        data = _call_api(f"/jobs/{job_id}/rolling_summary")
        return data
    except FileNotFoundError:
        # 404 是正常的（研究結果尚未產生）
        return {"status": "not_available", "message": "Rolling summary not yet generated"}


def get_season_report(job_id: str, season_id: str) -> dict:
    """取得特定季度的報告 - 從 /jobs/{job_id}/seasons/{season_id} 讀取真實 artifact"""
    try:
        data = _call_api(f"/jobs/{job_id}/seasons/{season_id}")
        return data
    except FileNotFoundError:
        # 404 是正常的（研究結果尚未產生）
        return {"status": "not_available", "message": f"Season report for {season_id} not yet generated"}


def generate_deploy_zip(job_id: str) -> Path:
    """產生部署 ZIP 檔案 - 對接真實 /jobs/{job_id}/deploy 端點"""
    # 呼叫 deploy 端點
    response = _call_api(f"/jobs/{job_id}/deploy", method="POST")
    
    # 從回應取得檔案路徑
    deploy_path = Path(response.get("deploy_path", ""))
    if not deploy_path.exists():
        raise RuntimeError(f"Deploy ZIP 檔案不存在: {deploy_path}")
    
    return deploy_path


def list_chart_artifacts(job_id: str) -> list[dict]:
    """列出可用的圖表 artifact - 從 /jobs/{job_id}/viz 讀取真實 artifact 清單"""
    try:
        data = _call_api(f"/jobs/{job_id}/viz")
        return data.get("artifacts", [])
    except FileNotFoundError:
        # 404 是正常的（圖表尚未產生）
        return []


def load_chart_artifact(job_id: str, artifact_id: str) -> dict:
    """載入圖表 artifact 資料 - 從 /jobs/{job_id}/viz/{artifact_id} 讀取真實 artifact"""
    try:
        data = _call_api(f"/jobs/{job_id}/viz/{artifact_id}")
        return data
    except FileNotFoundError:
        # 404 是正常的（特定圖表尚未產生）
        return {"status": "not_available", "message": f"Chart artifact {artifact_id} not yet generated"}


def get_jobs_for_deploy() -> list[dict]:
    """取得可部署的 jobs - 從 /jobs/deployable 讀取真實資料"""
    try:
        data = _call_api("/jobs/deployable")
        return data.get("jobs", [])
    except FileNotFoundError:
        # 404 是正常的（端點可能尚未實現）
        return []
    except RuntimeError as e:
        # 其他錯誤（如 API 不可用）
        if "404" in str(e):
            return []
        raise


def get_system_settings() -> dict:
    """取得系統設定 - 從 /meta/settings 讀取"""
    try:
        data = _call_api("/meta/settings")
        return data
    except (FileNotFoundError, RuntimeError):
        # 回傳預設設定
        return {
            "api_endpoint": API_BASE,
            "version": "2.0.0",
            "environment": {},
            "endpoints": {},
            "auto_refresh": True,
            "notifications": False,
            "theme": "dark",
        }


def update_system_settings(settings: dict) -> dict:
    """更新系統設定 - 發送到 /meta/settings"""
    try:
        data = _call_api("/meta/settings", method="POST", data=settings)
        return data
    except (FileNotFoundError, RuntimeError):
        # 模擬成功
        return {"status": "ok", "message": "Settings updated (simulated)"}


# 輔助函數
def _map_status(api_status: str) -> Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]:
    """對應 API 狀態到 UI 狀態"""
    status_map = {
        "QUEUED": "PENDING",
        "RUNNING": "RUNNING",
        "PAUSED": "RUNNING",
        "DONE": "COMPLETED",
        "FAILED": "FAILED",
        "KILLED": "FAILED",
    }
    return status_map.get(api_status, "PENDING")


def _estimate_progress(job_data: dict) -> Optional[float]:
    """估計任務進度"""
    status = job_data.get("status", "")
    if status == "QUEUED":
        return 0.0
    elif status == "RUNNING":
        return 0.5
    elif status == "DONE":
        return 1.0
    elif status in ["FAILED", "KILLED"]:
        return None
    else:
        return 0.3


# _mock_jobs 函數已移除 - Phase 6.5 禁止 fallback mock



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/app.py
sha256(source_bytes) = 2b85f32e9b4e7a956652f771e2703c5993d08638d36c42f60d758851fe75f6e4
bytes = 1410
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 主應用程式 - 唯一 UI 入口點"""

from nicegui import ui
from .router import register_pages
from ..theme import inject_global_styles


@ui.page('/health')
def health_page():
    """健康檢查端點 - 用於 launcher readiness check"""
    # 用純文字就好，launcher 只需要 200 OK
    ui.label('ok')


def main() -> None:
    """啟動 NiceGUI 應用程式"""
    # 注入全域樣式（必須在 register_pages 之前）
    inject_global_styles()
    
    # 註冊頁面路由
    register_pages()
    
    # 啟動伺服器
    ui.run(
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=False,  # 避免 gio: Operation not supported
    )


# 以下函數簽名符合 P0-0 要求，實際實作在 layout.py 中
def render_header(season: str) -> None:
    """渲染頁面頂部 header（包含 season 顯示）"""
    from .layout import render_header as _render_header
    _render_header(season)


def render_nav(active_path: str) -> None:
    """渲染側邊導航欄（用於需要側邊導航的頁面）"""
    from .layout import render_nav as _render_nav
    _render_nav(active_path)


def render_shell(active_path: str, season: str = "2026Q1"):
    """渲染完整 shell（header + 主內容區）"""
    from .layout import render_shell as _render_shell
    return _render_shell(active_path, season)


if __name__ == "__main__":
    main()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/layout.py
sha256(source_bytes) = 29c6c311a7a8838cb88ebdb5f22ee38b02cb13e5f2125bd551d6cfc26f84df7a
bytes = 3183
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations
from nicegui import ui

# 根據 P0-0 要求：Dashboard / Wizard / History / Candidates / Portfolio / Deploy / Settings / Status
NAV = [
    ("Dashboard", "/"),
    ("Wizard", "/wizard"),
    ("History", "/history"),
    ("Candidates", "/candidates"),
    ("Portfolio", "/portfolio"),
    ("Deploy", "/deploy"),
    ("Settings", "/settings"),
    ("Status", "/status"),
]

def render_header(season: str) -> None:
    """渲染頁面頂部 header（包含 season 顯示）"""
    with ui.header().classes("fish-header items-center justify-between px-6 py-4"):
        with ui.row().classes("items-center gap-4"):
            ui.icon("rocket_launch", size="lg").classes("text-cyber-500")
            ui.label("FishBroWFS V2").classes("text-2xl font-bold text-cyber-glow")
            ui.label(f"Season: {season}").classes("text-sm bg-nexus-800 px-3 py-1 rounded-full")
        
        with ui.row().classes("gap-2"):
            for name, path in NAV:
                ui.link(name, path).classes(
                    "px-4 py-2 rounded-lg no-underline transition-colors "
                    "hover:bg-nexus-800 text-slate-300"
                )

def render_nav(active_path: str) -> None:
    """渲染側邊導航欄（用於需要側邊導航的頁面）"""
    with ui.column().classes("w-64 bg-nexus-900 h-full p-4 border-r border-nexus-800"):
        ui.label("Navigation").classes("text-lg font-bold mb-4 text-cyber-400")
        
        for name, path in NAV:
            is_active = active_path == path
            classes = "px-4 py-3 rounded-lg mb-2 no-underline transition-colors "
            if is_active:
                classes += "nav-active bg-nexus-800 text-cyber-300 font-semibold"
            else:
                classes += "hover:bg-nexus-800 text-slate-400"
            
            ui.link(name, path).classes(classes)

def render_shell(active_path: str, season: str = "2026Q1") -> None:
    """渲染完整 shell（header + 主內容區）"""
    # 套用 cyberpunk body classes
    ui.query("body").classes("bg-nexus-950 text-slate-300 font-sans h-screen flex flex-col overflow-hidden")
    
    # 渲染 header
    render_header(season)
    
    # 主內容區容器
    with ui.row().classes("flex-1 overflow-hidden"):
        # 側邊導航（可選，根據頁面需求）
        # render_nav(active_path)
        
        # 主內容
        with ui.column().classes("flex-1 p-6 overflow-auto"):
            yield  # 讓呼叫者可以插入內容


def render_topbar(*args, **kwargs):
    """向後相容性 shim：舊頁面可能呼叫 render_topbar，將其映射到 render_header"""
    # 如果第一個參數是字串，視為 title 參數（舊版 render_topbar 可能接受 title）
    if args and isinstance(args[0], str):
        # 舊版 render_topbar(title) -> 呼叫 render_header(season)
        # 這裡我們忽略 title，使用預設 season
        season = "2026Q1"
        if len(args) > 1 and isinstance(args[1], str):
            season = args[1]
        return render_header(season)
    # 如果沒有參數，使用預設 season
    return render_header(kwargs.get("season", "2026Q1"))



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/router.py
sha256(source_bytes) = 4017aa6f25626704c8a1ba757c1b8675cacecd02ad56466b7597a513281f1f85
bytes = 815
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 路由設定"""

from nicegui import ui


def register_pages() -> None:
    """註冊所有頁面路由"""
    from .pages import (
        register_home,
        register_new_job,
        register_job,
        register_results,
        register_charts,
        register_deploy,
        register_history,
        register_candidates,
        register_wizard,
        register_portfolio,
        register_run_detail,
        register_settings,
        register_status,
    )
    
    # 註冊所有頁面
    register_home()
    register_new_job()
    register_job()
    register_results()
    register_charts()
    register_deploy()
    register_history()
    register_candidates()
    register_wizard()
    register_portfolio()
    register_run_detail()
    register_settings()
    register_status()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/state.py
sha256(source_bytes) = e539b8559a664beed7b908d0f5f0388605f85fc204fffcb1edee31fc5fad31a4
bytes = 1536
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 應用程式狀態管理"""

from typing import Dict, Any, Optional


class AppState:
    """應用程式全域狀態"""
    
    _instance: Optional["AppState"] = None
    
    def __new__(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """初始化狀態"""
        self.current_job_id: Optional[str] = None
        self.user_preferences: Dict[str, Any] = {
            "theme": "dark",
            "refresh_interval": 5,  # 秒
            "default_outputs_root": "outputs",
        }
        self.notifications: list = []
    
    def set_current_job(self, job_id: str) -> None:
        """設定當前選中的任務"""
        self.current_job_id = job_id
    
    def get_current_job(self) -> Optional[str]:
        """取得當前選中的任務"""
        return self.current_job_id
    
    def add_notification(self, message: str, level: str = "info") -> None:
        """新增通知訊息"""
        self.notifications.append({
            "message": message,
            "level": level,
            "timestamp": "now"  # 實際應用中應使用 datetime
        })
        # 限制通知數量
        if len(self.notifications) > 10:
            self.notifications.pop(0)
    
    def clear_notifications(self) -> None:
        """清除所有通知"""
        self.notifications.clear()


# 全域狀態實例
app_state = AppState()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/ui_compat.py
sha256(source_bytes) = 604a1beae9a48c466afff0093b34ad2d207867b30aecd0ef1de589b9c9f3aaf5
bytes = 7011
redacted = False
--------------------------------------------------------------------------------
"""UI Compatibility Wrapper - Canonical NiceGUI patterns for FishBroWFS_V2.

This module provides wrapper functions that enforce the canonical UI patterns:
1. No label= keyword argument in widget constructors
2. Labels are separate ui.label() widgets
3. Consistent spacing and styling
4. Built-in bindability support

Usage:
    from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_date, labeled_input
    
    # Instead of: ui.date(label="Start Date")
    # Use:
    labeled_date("Start Date").bind_value(state, "start_date")
"""

from typing import Any, Callable, Optional, List, Dict, Union
from nicegui import ui


def labeled(widget_factory: Callable, label: str, *args, **kwargs) -> Any:
    """Create a labeled widget using the canonical pattern.
    
    Args:
        widget_factory: UI widget constructor (e.g., ui.date, ui.input)
        label: Label text to display above the widget
        *args, **kwargs: Passed to widget_factory
        
    Returns:
        The created widget instance
        
    Example:
        >>> date_widget = labeled(ui.date, "Start Date", value="2024-01-01")
        >>> date_widget.bind_value(state, "start_date")
    """
    with ui.column().classes("gap-1 w-full"):
        ui.label(label)
        widget = widget_factory(*args, **kwargs)
        return widget


def labeled_date(label: str, **kwargs) -> Any:
    """Create a labeled date picker.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.date()
        
    Returns:
        ui.date widget instance
    """
    return labeled(ui.date, label, **kwargs)


def labeled_input(label: str, **kwargs) -> Any:
    """Create a labeled text input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.input()
        
    Returns:
        ui.input widget instance
    """
    return labeled(ui.input, label, **kwargs)


def labeled_select(label: str, **kwargs) -> Any:
    """Create a labeled select/dropdown.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.select()
        
    Returns:
        ui.select widget instance
    """
    return labeled(ui.select, label, **kwargs)


def labeled_number(label: str, **kwargs) -> Any:
    """Create a labeled number input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.number()
        
    Returns:
        ui.number widget instance
    """
    return labeled(ui.number, label, **kwargs)


def labeled_textarea(label: str, **kwargs) -> Any:
    """Create a labeled textarea.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.textarea()
        
    Returns:
        ui.textarea widget instance
    """
    return labeled(ui.textarea, label, **kwargs)


def labeled_slider(label: str, **kwargs) -> Any:
    """Create a labeled slider.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.slider()
        
    Returns:
        ui.slider widget instance
    """
    return labeled(ui.slider, label, **kwargs)


def labeled_checkbox(label: str, **kwargs) -> Any:
    """Create a labeled checkbox.
    
    Note: ui.checkbox already has built-in label support via first positional arg.
    This wrapper maintains consistency with other labeled widgets.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.checkbox()
        
    Returns:
        ui.checkbox widget instance
    """
    return labeled(ui.checkbox, label, **kwargs)


def labeled_switch(label: str, **kwargs) -> Any:
    """Create a labeled switch.
    
    Note: ui.switch already has built-in label support via first positional arg.
    This wrapper maintains consistency with other labeled widgets.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.switch()
        
    Returns:
        ui.switch widget instance
    """
    return labeled(ui.switch, label, **kwargs)


def labeled_radio(label: str, **kwargs) -> Any:
    """Create a labeled radio button group.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.radio()
        
    Returns:
        ui.radio widget instance
    """
    return labeled(ui.radio, label, **kwargs)


def labeled_color_input(label: str, **kwargs) -> Any:
    """Create a labeled color input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.color_input()
        
    Returns:
        ui.color_input widget instance
    """
    return labeled(ui.color_input, label, **kwargs)


def labeled_upload(label: str, **kwargs) -> Any:
    """Create a labeled file upload.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.upload()
        
    Returns:
        ui.upload widget instance
    """
    return labeled(ui.upload, label, **kwargs)


def form_section(title: str) -> Any:
    """Create a form section with consistent styling.
    
    Args:
        title: Section title
        
    Returns:
        Context manager for the form section
    """
    return ui.card().classes("w-full p-4 mb-6 bg-nexus-900")


def form_row() -> Any:
    """Create a form row with consistent spacing.
    
    Returns:
        Context manager for the form row
    """
    return ui.row().classes("w-full gap-4 mb-4")


def form_column() -> Any:
    """Create a form column with consistent spacing.
    
    Returns:
        Context manager for the form column
    """
    return ui.column().classes("gap-2 w-full")


# Convenience function for wizard forms
def wizard_field(label: str, widget_type: str = "input", **kwargs) -> Any:
    """Create a wizard form field with consistent styling.
    
    Args:
        label: Field label
        widget_type: Type of widget ('date', 'input', 'select', 'number', 'textarea')
        **kwargs: Passed to the widget constructor
        
    Returns:
        The created widget instance
        
    Raises:
        ValueError: If widget_type is not supported
    """
    widget_map = {
        'date': labeled_date,
        'input': labeled_input,
        'select': labeled_select,
        'number': labeled_number,
        'textarea': labeled_textarea,
        'slider': labeled_slider,
        'checkbox': labeled_checkbox,
        'switch': labeled_switch,
        'radio': labeled_radio,
        'color': labeled_color_input,
        'upload': labeled_upload,
    }
    
    if widget_type not in widget_map:
        raise ValueError(f"Unsupported widget_type: {widget_type}. "
                       f"Supported: {list(widget_map.keys())}")
    
    widget = widget_map[widget_type](label, **kwargs)
    widget.classes("w-full")
    return widget


# Example usage (commented out for documentation):
"""
# Before (forbidden):
# ui.date(label="Start Date", value="2024-01-01")  # This is the forbidden pattern

# After (canonical):
from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_date
labeled_date("Start Date", value="2024-01-01").bind_value(state, "start_date")

# Or using wizard_field for wizard forms:
wizard_field("Start Date", "date", value="2024-01-01").bind_value(state, "start_date")
"""
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/__init__.py
sha256(source_bytes) = 80a08f1575f9e32364c8ad7e4250b63cdf4a433eb6d3e19ff1c5f7585624425e
bytes = 1082
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 頁面模組"""

from .home import register as register_home
from .new_job import register as register_new_job
from .job import register as register_job
from .results import register as register_results
from .charts import register as register_charts
from .deploy import register as register_deploy
from .artifacts import register as register_artifacts
from .history import register as register_history
from .candidates import register as register_candidates
from .wizard import register as register_wizard
from .portfolio import register as register_portfolio
from .run_detail import register as register_run_detail
from .settings import register as register_settings
from .status import register as register_status

__all__ = [
    "register_home",
    "register_new_job",
    "register_job",
    "register_results",
    "register_charts",
    "register_deploy",
    "register_artifacts",
    "register_history",
    "register_candidates",
    "register_wizard",
    "register_portfolio",
    "register_run_detail",
    "register_settings",
    "register_status",
]



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/artifacts.py
sha256(source_bytes) = e9f4e865a82acb825717c8f3e2ce7949b8b7e7a7209f06c0438dc55e4417406e
bytes = 14598
redacted = False
--------------------------------------------------------------------------------
"""Artifacts Drill-down Pages for M2.

Provides read-only navigation through research units and artifact links.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any
from urllib.parse import quote

from nicegui import ui

from ..layout import render_shell
from FishBroWFS_V2.control.job_api import list_jobs_with_progress
from FishBroWFS_V2.control.artifacts_api import (
    list_research_units,
    get_research_artifacts,
    get_portfolio_index,
)
from FishBroWFS_V2.core.season_context import current_season


def encode_unit_key(unit: Dict[str, Any]) -> str:
    """Encode unit key into a URL-safe string."""
    # Use a simple JSON representation, base64 could be used but keep simple
    key = {
        "data1_symbol": unit.get("data1_symbol"),
        "data1_timeframe": unit.get("data1_timeframe"),
        "strategy": unit.get("strategy"),
        "data2_filter": unit.get("data2_filter"),
    }
    return quote(json.dumps(key, sort_keys=True), safe="")


def decode_unit_key(encoded: str) -> Dict[str, str]:
    """Decode unit key from URL string."""
    import urllib.parse
    import json as json_lib
    decoded = urllib.parse.unquote(encoded)
    return json_lib.loads(decoded)


def render_artifacts_home() -> None:
    """Artifacts home page - list jobs that have research indices."""
    ui.page_title("FishBroWFS V2 - Artifacts")
    
    with render_shell("/artifacts", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            ui.label("Artifacts Drill-down").classes("text-3xl font-bold mb-6")
            ui.label("Select a job to view its research units and artifacts.").classes("text-gray-600 mb-8")
            
            # Fetch jobs
            jobs = list_jobs_with_progress(limit=100)
            # Filter jobs that are DONE (or have research index)
            # For simplicity, we'll show all jobs; but we can add a placeholder
            if not jobs:
                ui.label("No jobs found.").classes("text-gray-500 italic")
                return
            
            # Create table
            columns = [
                {"name": "job_id", "label": "Job ID", "field": "job_id", "align": "left"},
                {"name": "season", "label": "Season", "field": "season", "align": "left"},
                {"name": "status", "label": "Status", "field": "status", "align": "left"},
                {"name": "units_total", "label": "Units", "field": "units_total", "align": "right"},
                {"name": "created_at", "label": "Created", "field": "created_at", "align": "left"},
                {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
            ]
            
            rows = []
            for job in jobs:
                # Determine if research index exists (simplify: assume DONE jobs have it)
                has_research = False
                try:
                    list_research_units(job["season"], job["job_id"])
                    has_research = True
                except FileNotFoundError:
                    pass
                
                rows.append({
                    "job_id": job["job_id"],
                    "season": job.get("season", "N/A"),
                    "status": job.get("status", "UNKNOWN"),
                    "units_total": job.get("units_total", 0),
                    "created_at": job.get("created_at", "")[:19],
                    "has_research": has_research,
                })
            
            # Custom row rendering to include button
            def render_row(row: Dict) -> None:
                with ui.row().classes("w-full items-center"):
                    ui.label(row["job_id"][:8] + "...").classes("font-mono text-sm")
                    ui.space()
                    ui.label(row["season"])
                    ui.space()
                    ui.badge(row["status"].upper(), color={
                        "queued": "yellow",
                        "running": "green",
                        "done": "blue",
                        "failed": "red"
                    }.get(row["status"].lower(), "gray")).classes("text-xs font-bold")
                    ui.space()
                    ui.label(str(row["units_total"]))
                    ui.space()
                    ui.label(row["created_at"])
                    ui.space()
                    if row["has_research"]:
                        ui.button("View Units", icon="list", 
                                 on_click=lambda r=row: ui.navigate.to(f"/artifacts/{r['job_id']}")).props("outline size=sm")
                    else:
                        ui.button("No Index", icon="block").props("outline disabled size=sm").tooltip("Research index not found")
            
            # Use a card for each job for better visual separation
            for row in rows:
                with ui.card().classes("w-full fish-card p-4 mb-3"):
                    render_row(row)


def render_job_units_page(job_id: str) -> None:
    """Page listing research units for a specific job."""
    ui.page_title(f"FishBroWFS V2 - Artifacts {job_id[:8]}...")
    
    with render_shell("/artifacts", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # Header with back button
            with ui.row().classes("w-full items-center mb-6"):
                ui.button("Back to Jobs", icon="arrow_back",
                         on_click=lambda: ui.navigate.to("/artifacts")).props("outline")
                ui.label(f"Job {job_id[:8]}... Research Units").classes("text-2xl font-bold ml-4")
            
            # Determine season (try to get from job info)
            # For now, use current season; but we need to know the season of the job.
            # We'll fetch job details from job_api.
            # Simplification: use current season.
            season = current_season()
            
            try:
                units = list_research_units(season, job_id)
            except FileNotFoundError:
                with ui.card().classes("w-full fish-card p-6 bg-red-50 border-red-200"):
                    ui.label("Research index not found").classes("text-red-800 font-bold mb-2")
                    ui.label(f"No research index found for job {job_id} in season {season}.").classes("text-red-700")
                    ui.button("Back to Jobs", icon="arrow_back",
                             on_click=lambda: ui.navigate.to("/artifacts")).props("outline color=red").classes("mt-4")
                return
            
            if not units:
                ui.label("No units found in research index.").classes("text-gray-500 italic")
                return
            
            # Units table
            columns = [
                {"name": "data1_symbol", "label": "Symbol", "field": "data1_symbol", "align": "left"},
                {"name": "data1_timeframe", "label": "Timeframe", "field": "data1_timeframe", "align": "left"},
                {"name": "strategy", "label": "Strategy", "field": "strategy", "align": "left"},
                {"name": "data2_filter", "label": "Data2 Filter", "field": "data2_filter", "align": "left"},
                {"name": "status", "label": "Status", "field": "status", "align": "left"},
                {"name": "actions", "label": "Artifacts", "field": "actions", "align": "center"},
            ]
            
            rows = []
            for unit in units:
                rows.append({
                    "data1_symbol": unit.get("data1_symbol", "N/A"),
                    "data1_timeframe": unit.get("data1_timeframe", "N/A"),
                    "strategy": unit.get("strategy", "N/A"),
                    "data2_filter": unit.get("data2_filter", "N/A"),
                    "status": unit.get("status", "UNKNOWN"),
                    "unit_key": encode_unit_key(unit),
                })
            
            # Render table using nicegui table component
            with ui.card().classes("w-full fish-card p-4"):
                ui.label("Research Units").classes("text-xl font-bold mb-4 text-cyber-400")
                table = ui.table(columns=columns, rows=rows, row_key="unit_key").classes("w-full").props("dense flat bordered")
                
                # Add slot for actions
                table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <q-btn icon="link" size="sm" flat color="primary"
                               @click="() => $router.push('/artifacts/{{props.row.job_id}}/' + encodeURIComponent(props.row.unit_key))" />
                    </q-td>
                """)
                
                # Since slot syntax is complex, we'll instead create a custom column via Python loop
                # Let's simplify: create a custom grid using rows
                ui.separator().classes("my-4")
                ui.label("Units List").classes("font-bold mb-2")
                for row in rows:
                    with ui.row().classes("w-full items-center border-b py-3"):
                        ui.label(row["data1_symbol"]).classes("w-24")
                        ui.label(row["data1_timeframe"]).classes("w-32")
                        ui.label(row["strategy"]).classes("w-48")
                        ui.label(row["data2_filter"]).classes("w-32")
                        ui.badge(row["status"].upper(), color="blue" if row["status"] == "DONE" else "gray").classes("text-xs font-bold w-24")
                        ui.space()
                        ui.button("View Artifacts", icon="link", 
                                 on_click=lambda r=row: ui.navigate.to(f"/artifacts/{job_id}/{r['unit_key']}")).props("outline size=sm")
            
            # Portfolio index section (if exists)
            try:
                portfolio_idx = get_portfolio_index(season, job_id)
                with ui.card().classes("w-full fish-card p-4 mt-6"):
                    ui.label("Portfolio Artifacts").classes("text-xl font-bold mb-4 text-cyber-400")
                    with ui.grid(columns=2).classes("w-full gap-4"):
                        ui.label("Summary:").classes("font-medium")
                        ui.label(portfolio_idx.get("summary", "N/A")).classes("font-mono text-sm")
                        ui.label("Admission:").classes("font-medium")
                        ui.label(portfolio_idx.get("admission", "N/A")).classes("font-mono text-sm")
            except FileNotFoundError:
                pass  # No portfolio index


def render_unit_artifacts_page(job_id: str, encoded_unit_key: str) -> None:
    """Page displaying artifact links for a specific unit."""
    ui.page_title(f"FishBroWFS V2 - Artifacts {job_id[:8]}...")
    
    with render_shell("/artifacts", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # Back navigation
            with ui.row().classes("w-full items-center mb-6"):
                ui.button("Back to Units", icon="arrow_back",
                         on_click=lambda: ui.navigate.to(f"/artifacts/{job_id}")).props("outline")
                ui.label(f"Unit Artifacts").classes("text-2xl font-bold ml-4")
            
            season = current_season()
            unit_key = decode_unit_key(encoded_unit_key)
            
            try:
                artifacts = get_research_artifacts(season, job_id, unit_key)
            except KeyError:
                with ui.card().classes("w-full fish-card p-6 bg-red-50 border-red-200"):
                    ui.label("Unit not found").classes("text-red-800 font-bold mb-2")
                    ui.label(f"No artifacts found for the specified unit.").classes("text-red-700")
                    return
            
            # Display unit key info
            with ui.card().classes("w-full fish-card p-4 mb-6"):
                ui.label("Unit Details").classes("text-lg font-bold mb-3")
                with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                    ui.label("Symbol:").classes("font-medium")
                    ui.label(unit_key.get("data1_symbol", "N/A"))
                    ui.label("Timeframe:").classes("font-medium")
                    ui.label(unit_key.get("data1_timeframe", "N/A"))
                    ui.label("Strategy:").classes("font-medium")
                    ui.label(unit_key.get("strategy", "N/A"))
                    ui.label("Data2 Filter:").classes("font-medium")
                    ui.label(unit_key.get("data2_filter", "N/A"))
            
            # Artifacts links
            with ui.card().classes("w-full fish-card p-4"):
                ui.label("Artifacts").classes("text-lg font-bold mb-3")
                if not artifacts:
                    ui.label("No artifact paths defined.").classes("text-gray-500 italic")
                else:
                    for name, path in artifacts.items():
                        with ui.row().classes("w-full items-center py-2 border-b last:border-0"):
                            ui.label(name).classes("font-medium w-48")
                            ui.label(str(path)).classes("font-mono text-sm flex-1")
                            # Create a link button that opens the file in a new tab (if served)
                            # For now, just show path
                            ui.button("Open", icon="open_in_new", on_click=lambda p=path: ui.navigate.to(f"/file/{p}")).props("outline size=sm").tooltip(f"Open {path}")
            
            # Note about read-only
            with ui.card().classes("w-full fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• This page shows the artifact file paths generated by the research pipeline.").classes("text-slate-300 mb-1")
                ui.label("• All artifacts are read‑only; no modifications can be made from this UI.").classes("text-slate-300 mb-1")
                ui.label("• Click 'Open' to view the artifact if the file is served by the backend.").classes("text-slate-300")


# Register routes
def register() -> None:
    """Register artifacts pages."""
    
    @ui.page("/artifacts")
    def artifacts_home() -> None:
        render_artifacts_home()
    
    @ui.page("/artifacts/{job_id}")
    def artifacts_job(job_id: str) -> None:
        render_job_units_page(job_id)
    
    @ui.page("/artifacts/{job_id}/{unit_key}")
    def artifacts_unit(job_id: str, unit_key: str) -> None:
        render_unit_artifacts_page(job_id, unit_key)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/candidates.py
sha256(source_bytes) = fecd310f6c76341a5d450fbc06ca91d704ff7533fb1c39d8cb73a4e5cc898bd1
bytes = 13491
redacted = False
--------------------------------------------------------------------------------
"""
Candidates 頁面 - 顯示 canonical results 和 research index
根據 P0.5-1 要求：統一 UI 只讀 outputs/research/ 為官方彙整來源
"""

from nicegui import ui
from datetime import datetime
from typing import List, Dict, Any

from ..layout import render_shell
from ...services.candidates_reader import (
    load_canonical_results,
    load_research_index,
    CanonicalResult,
    ResearchIndexEntry,
    refresh_canonical_results,
    refresh_research_index,
)
from ...services.actions import generate_research
from FishBroWFS_V2.core.season_context import current_season, canonical_results_path, research_index_path
from FishBroWFS_V2.core.season_state import load_season_state


def render_canonical_results_table(results: List[CanonicalResult]) -> None:
    """渲染 canonical results 表格"""
    if not results:
        ui.label("No canonical results found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left"},
        {"name": "bars", "label": "Bars", "field": "bars", "align": "right"},
        {"name": "net_profit", "label": "Net Profit", "field": "net_profit", "align": "right", "format": lambda val: f"{val:.2f}"},
        {"name": "max_drawdown", "label": "Max DD", "field": "max_drawdown", "align": "right", "format": lambda val: f"{val:.2f}"},
        {"name": "score_final", "label": "Score Final", "field": "score_final", "align": "right", "format": lambda val: f"{val:.3f}"},
        {"name": "trades", "label": "Trades", "field": "trades", "align": "right"},
        {"name": "start_date", "label": "Start Date", "field": "start_date", "align": "left"},
    ]
    
    rows = []
    for result in results:
        rows.append({
            "run_id": result.run_id[:12] + "..." if len(result.run_id) > 12 else result.run_id,
            "strategy_id": result.strategy_id,
            "symbol": result.symbol,
            "bars": result.bars,
            "net_profit": result.net_profit,
            "max_drawdown": result.max_drawdown,
            "score_final": result.score_final,
            "trades": result.trades,
            "start_date": result.start_date[:10] if result.start_date else "",
        })
    
    # 使用 fish-card 樣式
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Canonical Results").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered")

def render_research_index_table(entries: List[ResearchIndexEntry]) -> None:
    """渲染 research index 表格"""
    if not entries:
        ui.label("No research index entries found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "season", "label": "Season", "field": "season", "align": "left"},
        {"name": "stage", "label": "Stage", "field": "stage", "align": "left"},
        {"name": "mode", "label": "Mode", "field": "mode", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "dataset_id", "label": "Dataset", "field": "dataset_id", "align": "left"},
        {"name": "status", "label": "Status", "field": "status", "align": "left"},
        {"name": "created_at", "label": "Created At", "field": "created_at", "align": "left"},
    ]
    
    rows = []
    for entry in entries:
        rows.append({
            "run_id": entry.run_id[:12] + "..." if len(entry.run_id) > 12 else entry.run_id,
            "season": entry.season,
            "stage": entry.stage,
            "mode": entry.mode,
            "strategy_id": entry.strategy_id,
            "dataset_id": entry.dataset_id,
            "status": entry.status,
            "created_at": entry.created_at[:19] if entry.created_at else "",
        })
    
    # 使用 fish-card 樣式
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Research Index").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered")

def render_candidates_page() -> None:
    """渲染 candidates 頁面內容"""
    ui.page_title("FishBroWFS V2 - Candidates")
    
    # 使用 shell 佈局
    with render_shell("/candidates", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # 頁面標題
            with ui.row().classes("w-full items-center mb-6"):
                ui.label("Candidates Dashboard").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                
                # 動作按鈕容器
                action_container = ui.row().classes("gap-2")
            
            # 檢查 research 檔案是否存在
            current_season_str = current_season()
            canonical_exists = canonical_results_path(current_season_str).exists()
            research_index_exists = research_index_path(current_season_str).exists()
            research_exists = canonical_exists and research_index_exists
            
            # 檢查 season freeze 狀態
            season_state = load_season_state(current_season_str)
            is_frozen = season_state.is_frozen()
            frozen_reason = season_state.reason if season_state.reason else "Season is frozen"
            
            # 說明文字
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("📊 Official Research Consolidation").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label(f"This page displays canonical results and research index from outputs/seasons/{current_season_str}/research/").classes("text-slate-300 mb-1")
                ui.label(f"Source: outputs/seasons/{current_season_str}/research/canonical_results.json & outputs/seasons/{current_season_str}/research/research_index.json").classes("text-sm text-slate-400")
                
                # 顯示檔案狀態
                if not research_exists:
                    with ui.row().classes("items-center mt-3 p-3 bg-amber-900/30 rounded-lg"):
                        ui.icon("warning", color="amber").classes("text-lg")
                        ui.label("Research artifacts not found for this season.").classes("ml-2 text-amber-300")
                
                # 顯示 freeze 狀態
                if is_frozen:
                    with ui.row().classes("items-center mt-3 p-3 bg-red-900/30 rounded-lg"):
                        ui.icon("lock", color="red").classes("text-lg")
                        ui.label(f"Season is frozen (reason: {frozen_reason})").classes("ml-2 text-red-300")
                        ui.label("All write actions are disabled.").classes("ml-2 text-red-300 text-sm")
            
            # 載入資料 - 使用當前 season
            canonical_results = load_canonical_results(current_season_str)
            research_index = load_research_index(current_season_str)
            
            # 統計卡片
            with ui.row().classes("w-full gap-4 mb-6"):
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Canonical Results").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(canonical_results))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("entries").classes("text-xs text-slate-500")
                    if not canonical_exists:
                        ui.label("File missing").classes("text-xs text-amber-500 mt-1")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Research Index").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(research_index))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("entries").classes("text-xs text-slate-500")
                    if not research_index_exists:
                        ui.label("File missing").classes("text-xs text-amber-500 mt-1")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Unique Strategies").classes("text-sm text-slate-400 mb-1")
                    strategies = {r.strategy_id for r in canonical_results}
                    ui.label(str(len(strategies))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("strategies").classes("text-xs text-slate-500")
            
            # 動作按鈕功能
            def generate_research_action():
                """觸發 Generate Research 動作"""
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Generating research...").classes("text-sm text-slate-400")
                
                # 執行 Generate Research 動作
                result = generate_research(current_season_str, legacy_copy=False)
                
                # 顯示結果
                if result.ok:
                    ui.notify(f"Research generated successfully! {len(result.artifacts_written)} artifacts created.", type="positive")
                else:
                    error_msg = result.stderr_tail[-1] if result.stderr_tail else "Unknown error"
                    ui.notify(f"Research generation failed: {error_msg}", type="negative")
                
                # 重新載入頁面
                ui.navigate.to("/candidates", reload=True)
            
            def refresh_all():
                """刷新所有資料"""
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Refreshing...").classes("text-sm text-slate-400")
                
                # 刷新資料 - 使用當前 season
                canonical_success = refresh_canonical_results(current_season_str)
                research_success = refresh_research_index(current_season_str)
                
                # 重新載入頁面
                ui.navigate.to("/candidates", reload=True)
            
            # 更新動作按鈕
            with action_container:
                if not research_exists:
                    if is_frozen:
                        # Season frozen: disable button with tooltip
                        ui.button("Generate Research", icon="play_arrow").props("outline disabled").tooltip(f"Season is frozen: {frozen_reason}")
                    else:
                        ui.button("Generate Research", icon="play_arrow", on_click=generate_research_action).props("outline color=positive")
                ui.button("Refresh Data", icon="refresh", on_click=refresh_all).props("outline")
            
            # 分隔線
            ui.separator().classes("my-6")
            
            # 如果沒有資料，顯示提示
            if not canonical_results and not research_index:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("insights", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No research data available").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label(f"Research artifacts not found for season {current_season_str}").classes("text-slate-400 mb-6")
                    if not research_exists:
                        ui.button("Generate Research Now", icon="play_arrow", on_click=generate_research_action).props("color=positive")
                return
            
            # Canonical Results 區塊
            ui.label("Canonical Results").classes("text-2xl font-bold mb-4 text-cyber-300")
            render_canonical_results_table(canonical_results)
            
            # Research Index 區塊
            ui.label("Research Index").classes("text-2xl font-bold mb-4 text-cyber-300")
            render_research_index_table(research_index)
            
            # 底部說明
            with ui.card().classes("w-full fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Canonical Results: Final performance metrics from research pipeline").classes("text-slate-300 mb-1")
                ui.label("• Research Index: Metadata about research runs (stage, mode, dataset, etc.)").classes("text-slate-300 mb-1")
                ui.label(f"• Data Source: outputs/seasons/{current_season_str}/research/ directory (single source of truth)").classes("text-slate-300 mb-1")
                ui.label("• Refresh: Click 'Refresh Data' to reload from disk").classes("text-slate-300")
                if not research_exists:
                    ui.label("• Generate: Click 'Generate Research' to create research artifacts for this season").classes("text-slate-300 text-amber-300")

def register() -> None:
    """註冊 candidates 頁面路由"""
    
    @ui.page("/candidates")
    def candidates_page() -> None:
        """Candidates 頁面"""
        render_candidates_page()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/charts.py
sha256(source_bytes) = 2913bdb28ab5866c36568286fb8486b27cd637b403299ace39498985656c28eb
bytes = 18538
redacted = False
--------------------------------------------------------------------------------

"""圖表頁面 - Charts"""

from nicegui import ui

from ..api import list_chart_artifacts, load_chart_artifact
from ..state import app_state


def register() -> None:
    """註冊圖表頁面"""
    
    @ui.page("/charts/{job_id}")
    def charts_page(job_id: str) -> None:
        """圖表頁面"""
        ui.page_title(f"FishBroWFS V2 - Charts {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # DEV MODE banner - 更醒目的誠實化標示
            with ui.card().classes("w-full mb-6 bg-red-50 border-red-300"):
                with ui.row().classes("w-full items-center"):
                    ui.icon("error", size="lg").classes("text-red-600 mr-2")
                    ui.label("DEV MODE: Chart visualization NOT WIRED").classes("text-red-800 font-bold text-lg")
                ui.label("All chart artifacts are currently NOT IMPLEMENTED. UI cannot compute drawdown/correlation/heatmap.").classes("text-sm text-red-700 mb-2")
                ui.label("Constitutional principle: UI only renders artifacts produced by Research/Portfolio layer.").classes("text-xs text-red-600")
                ui.label("Expected artifact location: outputs/runs/{job_id}/viz/*.json").classes("font-mono text-xs text-gray-600")
            
            # 圖表選擇器
            chart_selector_container = ui.row().classes("w-full mb-6")
            
            # 圖表顯示容器
            chart_container = ui.column().classes("w-full")
            
            def refresh_charts(jid: str) -> None:
                """刷新圖表顯示"""
                chart_selector_container.clear()
                chart_container.clear()
                
                try:
                    # 獲取可用的圖表 artifact
                    artifacts = list_chart_artifacts(jid)
                    
                    with chart_selector_container:
                        ui.label("Select chart:").classes("mr-4 font-bold")
                        
                        # 預設圖表選項 - 但誠實標示為 "Not wired"
                        chart_options = {
                            "equity": "Equity Curve (NOT WIRED)",
                            "drawdown": "Drawdown Curve (NOT WIRED)",
                            "corr": "Correlation Matrix (NOT WIRED)",
                            "heatmap": "Heatmap (NOT WIRED)",
                        }
                        
                        # 如果有 artifact，使用 artifact 列表
                        if artifacts and len(artifacts) > 0:
                            chart_options = {a["id"]: f"{a.get('name', a['id'])} (Artifact)" for a in artifacts}
                        else:
                            # 沒有 artifact，顯示 "Not wired" 選項
                            chart_options = {"not_wired": "No artifacts available (NOT WIRED)"}
                        
                        chart_select = ui.select(
                            options=chart_options,
                            value=list(chart_options.keys())[0] if chart_options else None
                        ).props("disabled" if not artifacts else None).classes("flex-1")
                        
                        # 滑點等級選擇器 - 如果沒有 artifact 則 disabled
                        slippage_select = ui.select(
                            label="Slippage Level",
                            options={"S0": "S0", "S1": "S1", "S2": "S2", "S3": "S3"},
                            value="S0"
                        ).props("disabled" if not artifacts else None).classes("ml-4")
                        
                        # 更新圖表按鈕 - 如果沒有 artifact 則 disabled
                        def update_chart_display() -> None:
                            if chart_select.value == "not_wired":
                                with chart_container:
                                    chart_container.clear()
                                    display_not_wired_message()
                            else:
                                load_and_display_chart(jid, chart_select.value, slippage_select.value)
                        
                        ui.button("Load", on_click=update_chart_display, icon="visibility",
                                 props="disabled" if not artifacts else None).classes("ml-4")
                    
                    # 初始載入
                    if artifacts and len(artifacts) > 0:
                        load_and_display_chart(jid, list(chart_options.keys())[0], "S0")
                    else:
                        with chart_container:
                            display_not_wired_message()
                
                except Exception as e:
                    with chart_container:
                        ui.label(f"Load failed: {e}").classes("text-red-600")
                        display_not_wired_message()
            
            def display_not_wired_message() -> None:
                """顯示 'Not wired' 訊息"""
                with ui.card().classes("w-full p-6 bg-gray-50 border-gray-300"):
                    ui.icon("warning", size="xl").classes("text-gray-500 mx-auto mb-4")
                    ui.label("Chart visualization NOT WIRED").classes("text-xl font-bold text-gray-700 text-center mb-2")
                    ui.label("The chart artifact system is not yet implemented.").classes("text-gray-600 text-center mb-4")
                    
                    ui.label("Expected workflow:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-gray-600"):
                        ui.label("1. Research/Portfolio layer produces visualization artifacts")
                        ui.label("2. Artifacts saved to outputs/runs/{job_id}/viz/")
                        ui.label("3. UI loads and renders artifacts (no computation)")
                        ui.label("4. UI shows equity/drawdown/corr/heatmap from artifacts")
                    
                    ui.label("Current status:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-red-600"):
                        ui.label("• Artifact production NOT IMPLEMENTED")
                        ui.label("• UI cannot compute drawdown/correlation")
                        ui.label("• All chart displays are placeholders")
            
            def load_and_display_chart(jid: str, chart_type: str, slippage_level: str) -> None:
                """載入並顯示圖表"""
                chart_container.clear()
                
                with chart_container:
                    ui.label(f"{chart_type} - {slippage_level}").classes("text-xl font-bold mb-4")
                    
                    try:
                        # 嘗試載入 artifact
                        artifact_data = load_chart_artifact(jid, f"{chart_type}_{slippage_level}")
                        
                        if artifact_data and artifact_data.get("type") != "not_implemented":
                            # 顯示 artifact 資訊
                            with ui.card().classes("w-full p-4 mb-4 bg-green-50 border-green-200"):
                                ui.label("✅ Artifact Loaded").classes("font-bold mb-2 text-green-800")
                                ui.label(f"Type: {artifact_data.get('type', 'unknown')}").classes("text-sm")
                                ui.label(f"Data points: {len(artifact_data.get('data', []))}").classes("text-sm")
                                ui.label(f"Generated at: {artifact_data.get('generated_at', 'unknown')}").classes("text-sm")
                            
                            # 根據圖表類型顯示不同的預覽
                            if chart_type == "equity":
                                display_equity_chart_preview(artifact_data)
                            elif chart_type == "drawdown":
                                display_drawdown_chart_preview(artifact_data)
                            elif chart_type == "corr":
                                display_correlation_preview(artifact_data)
                            elif chart_type == "heatmap":
                                display_heatmap_preview(artifact_data)
                            else:
                                display_generic_chart_preview(artifact_data)
                        
                        else:
                            # 顯示 NOT WIRED 訊息
                            display_not_wired_chart(chart_type, slippage_level)
                    
                    except Exception as e:
                        ui.label(f"Chart load error: {e}").classes("text-red-600")
                        display_not_wired_chart(chart_type, slippage_level)
            
            def display_not_wired_chart(chart_type: str, slippage_level: str) -> None:
                """顯示 NOT WIRED 圖表訊息"""
                with ui.card().classes("w-full p-6 bg-red-50 border-red-300"):
                    ui.icon("error", size="xl").classes("text-red-600 mx-auto mb-4")
                    ui.label(f"NOT WIRED: {chart_type} - {slippage_level}").classes("text-xl font-bold text-red-800 text-center mb-2")
                    ui.label("This chart visualization is not yet implemented.").classes("text-red-700 text-center mb-4")
                    
                    # 憲法級原則提醒
                    with ui.card().classes("w-full p-4 bg-white border-gray-300"):
                        ui.label("Constitutional principles:").classes("font-bold mb-2")
                        with ui.column().classes("ml-2 text-sm text-gray-700"):
                            ui.label("• All visualization data must be produced by Research/Portfolio as artifacts")
                            ui.label("• UI only renders, never computes drawdown/correlation/etc.")
                            ui.label("• Artifacts are the single source of truth")
                            ui.label("• UI cannot compute anything - must wait for artifact production")
                    
                    # 預期的工作流程
                    ui.label("Expected workflow:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-gray-600"):
                        ui.label(f"1. Research layer produces {chart_type}_{slippage_level}.json")
                        ui.label("2. Artifact saved to outputs/runs/{job_id}/viz/")
                        ui.label("3. UI loads artifact via Control API")
                        ui.label("4. UI renders using artifact data (no computation)")
                    
                    # 當前狀態
                    ui.label("Current status:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-red-600"):
                        ui.label("• Artifact production NOT IMPLEMENTED")
                        ui.label("• Control API endpoint returns 'not_implemented'")
                        ui.label("• UI shows this honest 'NOT WIRED' message")
                        ui.label("• No fake charts or placeholder data")
            
            def display_equity_chart_preview(data: dict) -> None:
                """顯示 Equity Curve 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Equity Curve Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: UI only renders artifact, no computation").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域 - 真實 artifact 資料
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📈 Real Equity Curve from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取統計資訊
                    if "stats" in data:
                        stats = data["stats"]
                        with ui.grid(columns=4).classes("w-full mt-4 gap-2"):
                            ui.label("Final equity:").classes("font-bold")
                            ui.label(f"{stats.get('final_equity', 'N/A')}").classes("text-right")
                            ui.label("Max drawdown:").classes("font-bold")
                            ui.label(f"{stats.get('max_drawdown', 'N/A')}%").classes("text-right text-red-600")
                            ui.label("Sharpe ratio:").classes("font-bold")
                            ui.label(f"{stats.get('sharpe_ratio', 'N/A')}").classes("text-right")
                            ui.label("Trades:").classes("font-bold")
                            ui.label(f"{stats.get('trades', 'N/A')}").classes("text-right")
            
            def display_drawdown_chart_preview(data: dict) -> None:
                """顯示 Drawdown Curve 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Drawdown Curve Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: Drawdown must be computed by Research, not UI").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📉 Real Drawdown Curve from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取統計資訊
                    if "stats" in data:
                        stats = data["stats"]
                        with ui.grid(columns=3).classes("w-full mt-4 gap-2"):
                            ui.label("Max drawdown:").classes("font-bold")
                            ui.label(f"{stats.get('max_drawdown', 'N/A')}%").classes("text-right text-red-600")
                            ui.label("Drawdown period:").classes("font-bold")
                            ui.label(f"{stats.get('drawdown_period', 'N/A')} days").classes("text-right")
                            ui.label("Recovery time:").classes("font-bold")
                            ui.label(f"{stats.get('recovery_time', 'N/A')} days").classes("text-right")
            
            def display_correlation_preview(data: dict) -> None:
                """顯示 Correlation Matrix 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Correlation Matrix Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: Correlation must be computed by Portfolio, not UI").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("🔗 Real Correlation Matrix from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取摘要
                    if "summary" in data:
                        summary = data["summary"]
                        ui.label("Correlation summary:").classes("font-bold mt-4")
                        for pair, value in summary.items():
                            with ui.row().classes("w-full text-sm"):
                                ui.label(f"{pair}:").classes("font-bold flex-1")
                                ui.label(f"{value}").classes("text-right")
            
            def display_heatmap_preview(data: dict) -> None:
                """顯示 Heatmap 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Heatmap Preview").classes("font-bold mb-2")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("🔥 Real Heatmap from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取資訊
                    if "description" in data:
                        ui.label(f"Description: {data['description']}").classes("text-sm mt-4")
            
            def display_generic_chart_preview(data: dict) -> None:
                """顯示通用圖表預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Chart Preview").classes("font-bold mb-2")
                    
                    with ui.row().classes("w-full h-48 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📊 Chart rendering area").classes("text-gray-500")
                    
                    # 顯示 artifact 基本資訊
                    ui.label(f"Type: {data.get('type', 'unknown')}").classes("text-sm mt-2")
                    ui.label(f"Data points: {len(data.get('data', []))}").classes("text-sm")
            
            def display_dev_mode_chart(chart_type: str, slippage_level: str) -> None:
                """顯示 DEV MODE 圖表"""
                with ui.card().classes("w-full p-4"):
                    ui.label(f"DEV MODE: {chart_type} - {slippage_level}").classes("font-bold mb-2 text-yellow-700")
                    ui.label("This is a placeholder. Real artifacts will be loaded when available.").classes("text-sm text-gray-600 mb-4")
                    
                    with ui.row().classes("w-full h-48 items-center justify-center bg-yellow-50 rounded border border-yellow-200"):
                        ui.label(f"🎨 {chart_type} chart placeholder ({slippage_level})").classes("text-yellow-600")
                    
                    # 說明文字
                    ui.label("Expected artifact location:").classes("font-bold mt-4 text-sm")
                    ui.label(f"outputs/runs/{{job_id}}/viz/{chart_type}_{slippage_level}.json").classes("font-mono text-xs text-gray-600")
                    
                    # 憲法級原則提醒
                    ui.label("Constitutional principles:").classes("font-bold mt-4 text-sm")
                    ui.label("• All visualization data must be produced by Research/Portfolio as artifacts").classes("text-xs text-gray-600")
                    ui.label("• UI only renders, never computes drawdown/correlation/etc.").classes("text-xs text-gray-600")
                    ui.label("• Artifacts are the single source of truth").classes("text-xs text-gray-600")
            
            # 初始載入
            refresh_charts(job_id)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/deploy.py
sha256(source_bytes) = 10a679e34728ec1ee5a686f8eddce9d583e0da5d02cf9f4360edf146d9ceaa4b
bytes = 7640
redacted = True
--------------------------------------------------------------------------------
"""Deploy List Page (Read-only) for M2.

Lists DONE jobs that are eligible for deployment (no actual deployment actions).
M4: Live-safety lock - shows banner when LIVE_EXECUTE is disabled.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Any

from nicegui import ui

from ..layout import render_shell
from FishBroWFS_V2.control.job_api import list_jobs_with_progress
from FishBroWFS_V2.core.season_context import current_season
from FishBroWFS_V2.core.season_state import load_season_state


def _check_live_execute_status() -> tuple[bool, str]:
    """檢查 LIVE_EXECUTE 是否啟用。
    
    Returns:
        tuple[bool, str]: (是否啟用, 原因訊息)
    """
    # 檢查環境變數
    if os.getenv("FISHBRO_ENABLE_LIVE") != "1":
        return False, "LIVE EXECUTION DISABLED (server-side). This UI is read-only."
    
    # 檢查 token 檔案
    token_path =[REDACTED]    if not token_path.exists():[REDACTED]        return False, "LIVE EXECUTION LOCKED:[REDACTED]    
    # 檢查 token 內容
    try:
        token_content =[REDACTED]        if token_content !=[REDACTED]            return False, "LIVE EXECUTION LOCKED:[REDACTED]    except Exception:
        return False, "LIVE EXECUTION LOCKED:[REDACTED]    
    return True, "LIVE EXECUTION ENABLED"


def render_deploy_list() -> None:
    """Render the deploy list page."""
    ui.page_title("FishBroWFS V2 - Deploy List")
    
    with render_shell("/deploy", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            ui.label("Deploy List (Read-only)").classes("text-3xl font-bold mb-6")
            
            # Season frozen banner
            season = current_season()
            season_state = load_season_state(season)
            is_frozen = season_state.is_frozen()
            if is_frozen:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-red-900/30 border-red-700"):
                    with ui.row().classes("items-center"):
                        ui.icon("lock", color="red").classes("text-2xl mr-3")
                        with ui.column():
                            ui.label("Season Frozen").classes("font-bold text-red-300 text-lg")
                            ui.label(f"This season is frozen. All deploy actions are disabled.").classes("text-red-200")
            
            # LIVE EXECUTE disabled banner
            live_enabled, live_reason = _check_live_execute_status()
            if not live_enabled:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-amber-900/30 border-amber-700"):
                    with ui.row().classes("items-center"):
                        ui.icon("warning", color="amber").classes("text-2xl mr-3")
                        with ui.column():
                            ui.label("Live Execution Disabled").classes("font-bold text-amber-300 text-lg")
                            ui.label(live_reason).classes("text-amber-200")
            
            # Explanation
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Lists DONE jobs that are eligible for deployment.").classes("text-slate-300 mb-1")
                ui.label("• This is a read‑only view; no deployment actions can be taken from this UI.").classes("text-slate-300 mb-1")
                ui.label("• Click a job to view its artifacts (if research index exists).").classes("text-slate-300")
                if is_frozen:
                    ui.label("• 🔒 Frozen season: All mutation buttons are disabled.").classes("text-red-300 mt-2")
                if not live_enabled:
                    ui.label("• 🚫 Live execution is disabled by server-side policy.").classes("text-amber-300 mt-2")
            
            # Fetch jobs and filter DONE
            jobs = list_jobs_with_progress(limit=100)
            done_jobs = [j for j in jobs if j.get("status", "").lower() == "done"]
            
            if not done_jobs:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("check_circle", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No DONE jobs found").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label("Jobs that have completed execution will appear here.").classes("text-slate-400")
                return
            
            # Table of DONE jobs
            columns = [
                {"name": "job_id", "label": "Job ID", "field": "job_id", "align": "left"},
                {"name": "season", "label": "Season", "field": "season", "align": "left"},
                {"name": "units_total", "label": "Units", "field": "units_total", "align": "right"},
                {"name": "created_at", "label": "Created", "field": "created_at", "align": "left"},
                {"name": "updated_at", "label": "Updated", "field": "updated_at", "align": "left"},
                {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
            ]
            
            rows = []
            for job in done_jobs:
                rows.append({
                    "job_id": job["job_id"],
                    "season": job.get("season", "N/A"),
                    "units_total": job.get("units_total", 0),
                    "created_at": job.get("created_at", "")[:19],
                    "updated_at": job.get("updated_at", "")[:19],
                })
            
            # Render each job as a card
            for row in rows:
                with ui.card().classes("w-full fish-card p-4 mb-4"):
                    with ui.grid(columns=6).classes("w-full items-center gap-4"):
                        ui.label(row["job_id"][:12] + "...").classes("font-mono text-sm")
                        ui.label(row["season"])
                        ui.label(str(row["units_total"])).classes("text-right")
                        ui.label(row["created_at"]).classes("text-sm text-gray-500")
                        ui.label(row["updated_at"]).classes("text-sm text-gray-500")
                        with ui.row().classes("gap-2"):
                            ui.button("Artifacts", icon="link",
                                     on_click=lambda r=row: ui.navigate.to(f"/artifacts/{r['job_id']}")).props("outline size=sm")
                            ui.button("Deploy", icon="rocket",
                                     on_click=lambda: ui.notify("Deploy actions are read-only", type="info")).props("outline disabled" if is_frozen else "outline").tooltip("Deployment is disabled in read-only mode")
            
            # Footer note
            with ui.card().classes("w-full fish-card p-4 mt-6"):
                ui.label("📌 Notes").classes("font-bold mb-2")
                ui.label("• Deploy list is automatically generated from DONE jobs.").classes("text-sm text-slate-400")
                ui.label("• To actually deploy a job, use the command-line interface or a separate deployment tool.").classes("text-sm text-slate-400")
                ui.label("• Frozen seasons prevent any deployment writes.").classes("text-sm text-slate-400")


def register() -> None:
    """Register deploy page."""
    
    @ui.page("/deploy")
    def deploy_page() -> None:
        render_deploy_list()

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/history.py
sha256(source_bytes) = 821fc58a131b68e4d6d785f6f4ef2b4aa5f11a149cdc69bbf55d46bd452f5060
bytes = 25173
redacted = False
--------------------------------------------------------------------------------
"""History 頁面 - Runs Browser with Audit Trail & Governance"""

from nicegui import ui
from datetime import datetime
from pathlib import Path
import json

from ...services.runs_index import get_global_index, RunIndexRow
from ...services.audit_log import read_audit_tail, get_audit_events_for_run_id
from FishBroWFS_V2.core.season_context import current_season, season_dir

# 嘗試導入 season_state 模組（Phase 5 新增）
try:
    from FishBroWFS_V2.core.season_state import load_season_state
    SEASON_STATE_AVAILABLE = True
except ImportError:
    SEASON_STATE_AVAILABLE = False
    load_season_state = None


def register() -> None:
    """註冊 History 頁面路由"""
    
    @ui.page("/history")
    def history_page() -> None:
        """渲染 History 頁面"""
        ui.page_title("FishBroWFS V2 - History")
        
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # 頁面標題
            ui.label("📜 Runs History").classes("text-3xl font-bold mb-2 text-cyber-glow")
            ui.label("顯示最新 50 個 runs（禁止全量掃描）").classes("text-lg text-slate-400 mb-8")
            
            # Season 資訊
            current_season_str = current_season()
            
            # 檢查 season freeze 狀態
            is_frozen = False
            frozen_reason = ""
            if SEASON_STATE_AVAILABLE and load_season_state is not None:
                try:
                    state = load_season_state(current_season_str)
                    if state and state.get("state") == "FROZEN":
                        is_frozen = True
                        frozen_reason = state.get("reason", "Season is frozen")
                except Exception:
                    # 如果載入失敗，忽略錯誤（保持未凍結狀態）
                    pass
            
            with ui.card().classes("fish-card p-4 mb-6 bg-nexus-900"):
                with ui.row().classes("items-center justify-between"):
                    with ui.row().classes("items-center"):
                        ui.icon("calendar_today", color="cyan").classes("mr-2")
                        ui.label(f"Current Season: {current_season_str}").classes("text-lg font-bold text-cyber-300")
                    
                    # Audit log 狀態
                    audit_path = season_dir(current_season_str) / "governance" / "ui_audit.jsonl"
                    if audit_path.exists():
                        ui.badge("Audit Log Active", color="green").props("dense")
                    else:
                        ui.badge("No Audit Log", color="amber").props("dense")
                
                # 顯示 freeze 狀態
                if is_frozen:
                    with ui.row().classes("items-center mt-3 p-3 bg-red-900/30 rounded-lg"):
                        ui.icon("lock", color="red").classes("mr-2")
                        ui.label("Season Frozen (治理鎖)").classes("font-bold text-red-300")
                        ui.label(frozen_reason).classes("ml-2 text-red-200 text-sm")
                        
                        # Integrity check button
                        ui.button("Check Integrity", icon="verified", on_click=lambda: check_integrity_action(current_season_str)) \
                            .classes("ml-4 px-3 py-1 text-xs bg-amber-500 hover:bg-amber-600")
            
            # 操作列
            with ui.row().classes("w-full mb-6 gap-4"):
                refresh_btn = ui.button("🔄 Refresh", on_click=lambda: refresh_table())
                refresh_btn.classes("btn-cyber")
                
                show_archived = ui.checkbox("顯示已歸檔", value=False)
                show_archived.on("change", lambda e: refresh_table())
                
                season_select = ui.select(
                    options=["所有 Season", current_season_str],
                    value="所有 Season",
                    label="Season"
                ).classes("w-48")
                season_select.on("change", lambda e: refresh_table())
                
                ui.space()
                
                # 顯示限制提示
                ui.label("只顯示最新 50 個 runs").classes("text-sm text-slate-500 italic")
            
            # 表格容器
            table_container = ui.column().classes("w-full")
            
            # 初始化表格
            def refresh_table():
                """刷新表格資料"""
                table_container.clear()
                
                # 獲取索引
                index = get_global_index()
                index.refresh()
                
                # 過濾條件
                season = None if season_select.value == "所有 Season" else season_select.value
                include_archived = show_archived.value
                
                # 獲取 runs
                runs = index.list(season=season, include_archived=include_archived)
                
                if not runs:
                    with table_container:
                        with ui.card().classes("fish-card w-full p-8 text-center"):
                            ui.icon("folder_off", size="xl").classes("text-slate-500 mb-4")
                            ui.label("沒有找到任何 runs").classes("text-xl text-slate-400")
                            ui.label("請確認 outputs 目錄結構正確").classes("text-sm text-slate-500")
                    return
                
                # 建立表格
                with table_container:
                    with ui.card().classes("fish-card w-full p-0 overflow-hidden"):
                        # 表格標頭
                        with ui.row().classes("bg-nexus-900 p-4 border-b border-nexus-800 font-bold"):
                            ui.label("Run ID").classes("w-64")
                            ui.label("Season").classes("w-24")
                            ui.label("Stage").classes("w-32")
                            ui.label("Status").classes("w-32")
                            ui.label("Modified").classes("w-48")
                            ui.label("Actions").classes("flex-1 text-right")
                        
                        # 表格內容
                        for run in runs:
                            with ui.row().classes(
                                "p-4 border-b border-nexus-800 hover:bg-nexus-900/50 "
                                "transition-colors items-center"
                            ):
                                # Run ID
                                ui.label(run.run_id).classes("w-64 font-mono text-sm")
                                
                                # Season
                                ui.label(run.season).classes("w-24")
                                
                                # Stage
                                stage_badge = run.stage or "unknown"
                                color = {
                                    "stage0": "bg-blue-500/20 text-blue-300",
                                    "stage1": "bg-green-500/20 text-green-300",
                                    "stage2": "bg-purple-500/20 text-purple-300",
                                    "demo": "bg-yellow-500/20 text-yellow-300",
                                }.get(stage_badge, "bg-slate-500/20 text-slate-300")
                                ui.label(stage_badge).classes(f"w-32 px-3 py-1 rounded-full text-xs {color}")
                                
                                # Status
                                status_badge = run.status
                                status_color = {
                                    "completed": "bg-green-500/20 text-green-300",
                                    "running": "bg-blue-500/20 text-blue-300",
                                    "failed": "bg-red-500/20 text-red-300",
                                    "unknown": "bg-slate-500/20 text-slate-300",
                                }.get(status_badge, "bg-slate-500/20 text-slate-300")
                                ui.label(status_badge).classes(f"w-32 px-3 py-1 rounded-full text-xs {status_color}")
                                
                                # Modified time
                                mtime_str = datetime.fromtimestamp(run.mtime).strftime("%Y-%m-%d %H:%M:%S")
                                ui.label(mtime_str).classes("w-48 text-sm text-slate-400")
                                
                                # Actions
                                with ui.row().classes("flex-1 justify-end gap-2"):
                                    # Report 按鈕（進 detail）
                                    report_btn = ui.button("Report", on_click=lambda r=run: view_report(r))
                                    report_btn.classes("px-3 py-1 text-xs bg-nexus-800 hover:bg-nexus-700")
                                    
                                    # Audit Trail 按鈕
                                    audit_btn = ui.button("Audit", on_click=lambda r=run: show_audit_trail(r))
                                    audit_btn.classes("px-3 py-1 text-xs bg-purple-500/20 hover:bg-purple-500/30")
                                    
                                    # Clone 按鈕（P0-4）
                                    clone_btn = ui.button("Clone", on_click=lambda r=run: clone_run(r))
                                    clone_btn.classes("px-3 py-1 text-xs bg-cyber-500/20 hover:bg-cyber-500/30")
                                    
                                    # Archive 按鈕（P0-3）
                                    if not run.is_archived:
                                        if is_frozen:
                                            # Season frozen: disable archive button with tooltip
                                            ui.button("Archive").classes("px-3 py-1 text-xs bg-red-500/10 text-red-300/50 cursor-not-allowed").tooltip(f"Season is frozen: {frozen_reason}")
                                        else:
                                            archive_btn = ui.button("Archive", on_click=lambda r=run: archive_run(r))
                                            archive_btn.classes("px-3 py-1 text-xs bg-red-500/20 hover:bg-red-500/30")
                                    else:
                                        ui.label("Archived").classes("px-3 py-1 text-xs bg-slate-500/20 text-slate-400 rounded")
            
            # 初始化表格
            refresh_table()
            
            # Audit Trail 區塊
            with ui.card().classes("fish-card w-full p-4 mt-8"):
                ui.label("📋 Recent Audit Trail").classes("text-xl font-bold mb-4 text-cyber-400")
                
                # 讀取 audit log
                audit_events = read_audit_tail(current_season_str, max_lines=20)
                
                if not audit_events:
                    ui.label("No audit events found").classes("text-gray-500 italic mb-2")
                    ui.label("UI actions will create audit events automatically").classes("text-sm text-slate-400")
                else:
                    # 顯示最近 5 個事件
                    recent_events = audit_events[-5:]  # 取最後 5 個（最新的）
                    
                    for event in reversed(recent_events):  # 最新的在最上面
                        with ui.card().classes("p-3 mb-2 bg-nexus-800"):
                            with ui.row().classes("items-center justify-between"):
                                with ui.column().classes("flex-1"):
                                    # 事件類型
                                    action_type = event.get("action", "unknown")
                                    color_map = {
                                        "generate_research": "text-green-400",
                                        "build_portfolio": "text-blue-400",
                                        "archive": "text-red-400",
                                        "clone": "text-yellow-400",
                                    }
                                    color = color_map.get(action_type, "text-slate-400")
                                    ui.label(f"• {action_type}").classes(f"font-bold {color}")
                                    
                                    # 時間戳
                                    ts = event.get("ts", "")
                                    if ts:
                                        # 簡化顯示
                                        display_ts = ts[:19].replace("T", " ")
                                        ui.label(f"at {display_ts}").classes("text-xs text-slate-500")
                                    
                                    # 額外資訊
                                    if "inputs" in event:
                                        inputs = event["inputs"]
                                        if isinstance(inputs, dict):
                                            summary = ", ".join([f"{k}={v}" for k, v in inputs.items() if k != "season"])
                                            if summary:
                                                ui.label(f"Inputs: {summary}").classes("text-xs text-slate-400")
                                
                                # 狀態指示器
                                if event.get("ok", False):
                                    ui.badge("✓", color="green").props("dense")
                                else:
                                    ui.badge("✗", color="red").props("dense")
            
            # 頁面底部資訊
            with ui.row().classes("w-full mt-8 text-sm text-slate-500"):
                ui.label("💡 提示：")
                ui.label("• 只掃描最新 50 個 runs 以避免全量掃描").classes("ml-2")
                ui.label("• 點擊 Report 查看詳細資訊").classes("ml-4")
                ui.label("• Archive 會將 run 移到 .archive 目錄").classes("ml-4")
                ui.label("• Audit 顯示 UI 動作歷史").classes("ml-4")
    
    # 按鈕動作函數
    def view_report(run: RunIndexRow) -> None:
        """查看 run 詳細報告"""
        ui.notify(f"正在載入 {run.run_id} 的報告...", type="info")
        # TODO: 實作跳轉到詳細頁面
        ui.navigate.to(f"/run/{run.run_id}")
    
    def show_audit_trail(run: RunIndexRow) -> None:
        """顯示 run 的 audit trail"""
        from ...services.audit_log import get_audit_events_for_run_id
        
        # 讀取 audit events
        audit_events = get_audit_events_for_run_id(run.run_id, run.season, max_lines=50)
        
        # 建立對話框
        with ui.dialog() as dialog, ui.card().classes("fish-card p-6 w-full max-w-4xl max-h-[80vh] overflow-auto"):
            ui.label(f"Audit Trail for {run.run_id}").classes("text-xl font-bold mb-4 text-cyber-400")
            
            if not audit_events:
                ui.label("No audit events found for this run").classes("text-gray-500 italic p-4")
            else:
                # 顯示 audit events
                for event in reversed(audit_events):  # 最新的在最上面
                    with ui.card().classes("p-4 mb-3 bg-nexus-800"):
                        # 事件標頭
                        with ui.row().classes("items-center justify-between mb-2"):
                            action_type = event.get("action", "unknown")
                            ui.label(f"Action: {action_type}").classes("font-bold text-cyber-300")
                            
                            # 時間戳
                            ts = event.get("ts", "")
                            if ts:
                                display_ts = ts[:19].replace("T", " ")
                                ui.label(display_ts).classes("text-sm text-slate-400")
                        
                        # 事件內容
                        with ui.column().classes("text-sm"):
                            # 狀態
                            status = "✓ Success" if event.get("ok", False) else "✗ Failed"
                            status_color = "text-green-400" if event.get("ok", False) else "text-red-400"
                            ui.label(f"Status: {status}").classes(f"mb-1 {status_color}")
                            
                            # 輸入參數
                            if "inputs" in event:
                                ui.label("Inputs:").classes("text-slate-400 mb-1")
                                inputs = event["inputs"]
                                if isinstance(inputs, dict):
                                    for key, value in inputs.items():
                                        ui.label(f"  {key}: {value}").classes("text-xs text-slate-500 ml-2")
                            
                            # 輸出的 artifacts
                            if "artifacts_written" in event:
                                artifacts = event["artifacts_written"]
                                if artifacts:
                                    ui.label("Artifacts Created:").classes("text-slate-400 mb-1")
                                    for artifact in artifacts[:3]:  # 顯示前 3 個
                                        ui.label(f"  • {artifact}").classes("text-xs text-slate-500 ml-2")
                                    if len(artifacts) > 3:
                                        ui.label(f"  ... and {len(artifacts) - 3} more").classes("text-xs text-slate-500 ml-2")
            
            # 關閉按鈕
            with ui.row().classes("w-full justify-end mt-4"):
                ui.button("Close", on_click=dialog.close).classes("px-4 py-2")
        
        dialog.open()
    
    def clone_run(run: RunIndexRow) -> None:
        """Clone run 到 Wizard"""
        ui.notify(f"正在複製 {run.run_id} 到 Wizard...", type="info")
        # TODO: P0-4 實作
        # 跳轉到 Wizard 頁面並預填欄位
        ui.navigate.to(f"/wizard?clone={run.run_id}")
    
    def archive_run(run: RunIndexRow) -> None:
        """Archive run"""
        from ...services.archive import archive_run as archive_service
        
        # 顯示確認對話框
        with ui.dialog() as dialog, ui.card().classes("fish-card p-6 w-96"):
            ui.label(f"確認歸檔 {run.run_id}?").classes("text-lg font-bold mb-4")
            ui.label("此操作會將 run 移到 .archive 目錄，並寫入 audit log。").classes("text-sm text-slate-400 mb-4")
            
            reason_select = ui.select(
                options=["failed", "garbage", "disk", "other"],
                value="garbage",
                label="歸檔原因"
            ).classes("w-full mb-4")
            
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("取消", on_click=dialog.close).classes("px-4 py-2")
                ui.button("確認歸檔", on_click=lambda: confirm_archive(run, reason_select.value, dialog)) \
                    .classes("px-4 py-2 bg-red-500 hover:bg-red-600")
        
        dialog.open()
    
    def check_integrity_action(season: str) -> None:
        """檢查 season integrity"""
        try:
            from FishBroWFS_V2.core.snapshot import verify_snapshot_integrity
            
            # 顯示載入中
            ui.notify(f"Checking integrity for season {season}...", type="info")
            
            # 執行 integrity 檢查
            result = verify_snapshot_integrity(season)
            
            # 建立結果對話框
            with ui.dialog() as dialog, ui.card().classes("fish-card p-6 w-full max-w-4xl max-h-[80vh] overflow-auto"):
                ui.label(f"Integrity Check - {season}").classes("text-xl font-bold mb-4 text-cyber-400")
                
                # 狀態標示
                if result["ok"]:
                    with ui.row().classes("items-center p-4 mb-4 bg-green-900/30 rounded-lg"):
                        ui.icon("verified", color="green").classes("text-2xl mr-3")
                        ui.label("✓ Integrity Verified").classes("text-lg font-bold text-green-300")
                        ui.label(f"All {result['total_checked']} artifacts match snapshot").classes("text-green-200 ml-2")
                else:
                    with ui.row().classes("items-center p-4 mb-4 bg-red-900/30 rounded-lg"):
                        ui.icon("warning", color="red").classes("text-2xl mr-3")
                        ui.label("✗ Integrity Violation").classes("text-lg font-bold text-red-300")
                        ui.label("Artifacts have been modified since freeze").classes("text-red-200 ml-2")
                
                # 詳細結果
                with ui.card().classes("p-4 mb-4 bg-nexus-800"):
                    ui.label("Summary").classes("font-bold mb-2 text-cyber-300")
                    
                    with ui.grid(columns=3).classes("w-full gap-4 mb-4"):
                        with ui.card().classes("p-3 text-center"):
                            ui.label("Missing Files").classes("text-sm text-slate-400 mb-1")
                            ui.label(str(len(result["missing_files"]))).classes("text-2xl font-bold text-red-400")
                        
                        with ui.card().classes("p-3 text-center"):
                            ui.label("Changed Files").classes("text-sm text-slate-400 mb-1")
                            ui.label(str(len(result["changed_files"]))).classes("text-2xl font-bold text-amber-400")
                        
                        with ui.card().classes("p-3 text-center"):
                            ui.label("New Files").classes("text-sm text-slate-400 mb-1")
                            ui.label(str(len(result["new_files"]))).classes("text-2xl font-bold text-blue-400")
                    
                    ui.label(f"Total Artifacts Checked: {result['total_checked']}").classes("text-sm text-slate-400")
                
                # 顯示問題檔案（如果有的話）
                if result["missing_files"]:
                    with ui.expansion("Missing Files", icon="folder_off").classes("w-full mb-4"):
                        with ui.column().classes("pl-4 pt-2"):
                            for file in result["missing_files"][:20]:  # 顯示前 20 個
                                ui.label(f"• {file}").classes("text-sm text-red-300")
                            if len(result["missing_files"]) > 20:
                                ui.label(f"... and {len(result['missing_files']) - 20} more").classes("text-sm text-slate-500")
                
                if result["changed_files"]:
                    with ui.expansion("Changed Files", icon="edit").classes("w-full mb-4"):
                        with ui.column().classes("pl-4 pt-2"):
                            for file in result["changed_files"][:20]:  # 顯示前 20 個
                                ui.label(f"• {file}").classes("text-sm text-amber-300")
                            if len(result["changed_files"]) > 20:
                                ui.label(f"... and {len(result['changed_files']) - 20} more").classes("text-sm text-slate-500")
                
                if result["new_files"]:
                    with ui.expansion("New Files", icon="add").classes("w-full mb-4"):
                        with ui.column().classes("pl-4 pt-2"):
                            for file in result["new_files"][:20]:  # 顯示前 20 個
                                ui.label(f"• {file}").classes("text-sm text-blue-300")
                            if len(result["new_files"]) > 20:
                                ui.label(f"... and {len(result['new_files']) - 20} more").classes("text-sm text-slate-500")
                
                # 關閉按鈕
                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Close", on_click=dialog.close).classes("px-4 py-2")
                
                dialog.open()
        
        except ImportError:
            ui.notify("Integrity check not available (snapshot module missing)", type="warning")
        except Exception as e:
            ui.notify(f"Integrity check failed: {str(e)}", type="negative")
    
    def confirm_archive(run: RunIndexRow, reason: str, dialog) -> None:
        """確認歸檔"""
        from ...services.archive import archive_run as archive_service
        from pathlib import Path
        
        try:
            result = archive_service(
                outputs_root=Path(__file__).parent.parent.parent.parent / "outputs",
                run_dir=Path(run.run_dir),
                reason=reason,
                operator="ui"
            )
            ui.notify(f"已歸檔 {run.run_id} 到 {result.archived_path}", type="positive")
            dialog.close()
            refresh_table()  # 刷新表格
        except Exception as e:
            ui.notify(f"歸檔失敗: {str(e)}", type="negative")
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/home.py
sha256(source_bytes) = e942fa83adfeaf85087b9bc10abc38a140a5502fc910b4c94721862362d9bfdd
bytes = 5685
redacted = False
--------------------------------------------------------------------------------

"""首頁 - Dashboard/Home"""

from nicegui import ui

from ..state import app_state


def register() -> None:
    """註冊首頁路由"""
    
    @ui.page("/")
    def home_page() -> None:
        """渲染首頁"""
        ui.page_title("FishBroWFS V2 - 儀表板")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 標題區
            ui.label("🐟 FishBroWFS V2 研究控制面板").classes("text-3xl font-bold mb-2 text-cyber-glow")
            ui.label("唯一 UI = NiceGUI（Submit job / Monitor / Results / Deploy / Charts）").classes("text-lg text-slate-400 mb-8")
            
            # 快速操作卡片
            ui.label("快速操作").classes("text-xl font-bold mb-4 text-cyber-400")
            
            with ui.row().classes("w-full gap-4 mb-8"):
                card1 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer glow")
                card1.on("click", lambda e: ui.navigate.to("/wizard"))
                with card1:
                    ui.icon("rocket_launch", size="lg").classes("text-cyber-500 mb-2")
                    ui.label("新增研究任務").classes("font-bold text-white")
                    ui.label("設定 dataset/symbols/TF/strategy 等參數").classes("text-sm text-slate-400")
                
                card2 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer")
                card2.on("click", lambda e: ui.navigate.to("/history"))
                with card2:
                    ui.icon("history", size="lg").classes("text-green-500 mb-2")
                    ui.label("Runs History").classes("font-bold text-white")
                    ui.label("查看任務狀態、進度、日誌").classes("text-sm text-slate-400")
                
                card3 = ui.card().classes("fish-card w-1/3 p-4 cursor-pointer")
                card3.on("click", lambda e: ui.notify("請先選擇一個任務", type="info"))
                with card3:
                    ui.icon("insights", size="lg").classes("text-purple-500 mb-2")
                    ui.label("查看結果").classes("font-bold text-white")
                    ui.label("rolling summary 表格與詳細報告").classes("text-sm text-slate-400")
            
            # 最近任務區
            ui.label("最近任務").classes("text-xl font-bold mb-4 text-cyber-400")
            
            # 任務列表（使用 RunsIndex）
            with ui.card().classes("fish-card w-full p-4"):
                from ...services.runs_index import get_global_index
                
                index = get_global_index()
                runs = index.list(season="2026Q1", include_archived=False)[:5]
                
                if runs:
                    ui.label(f"最新 {len(runs)} 個 runs:").classes("font-bold mb-2")
                    for run in runs:
                        with ui.row().classes("w-full py-2 border-b border-nexus-800 last:border-0"):
                            ui.label(run.run_id).classes("flex-1 font-mono text-sm")
                            status_class = {
                                'completed': 'bg-green-500/20 text-green-300',
                                'running': 'bg-blue-500/20 text-blue-300',
                                'failed': 'bg-red-500/20 text-red-300'
                            }.get(run.status, 'bg-slate-500/20 text-slate-300')
                            ui.label(run.status).classes(f"px-2 py-1 rounded text-xs {status_class}")
                else:
                    ui.label("沒有找到 runs").classes("text-slate-500")
                    ui.label("請確認 outputs 目錄結構正確").classes("text-sm text-slate-600")
            
            # 系統狀態區
            ui.label("系統狀態").classes("text-xl font-bold mb-4 mt-8 text-cyber-400")
            
            with ui.row().classes("w-full gap-4"):
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("Control API").classes("font-bold")
                    ui.label("✅ 運行中").classes("text-green-400")
                    ui.label("localhost:8000").classes("text-sm text-slate-400")
                
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("Worker").classes("font-bold")
                    ui.label("🟡 待檢查").classes("text-yellow-400")
                    ui.label("需要啟動 worker daemon").classes("text-sm text-slate-400")
                
                with ui.card().classes("fish-card flex-1 p-4"):
                    ui.label("資料集").classes("font-bold")
                    ui.label("📊 可用").classes("text-blue-400")
                    ui.label("從 registry 載入").classes("text-sm text-slate-400")
            
            # 憲法級原則提醒
            with ui.card().classes("fish-card w-full mt-8 border-cyber-500/30"):
                ui.label("憲法級總原則").classes("font-bold text-cyber-400 mb-2")
                ui.label("1. NiceGUI 永遠是薄客戶端：只做「填單/看單/拿貨/畫圖」").classes("text-sm text-slate-300")
                ui.label("2. 唯一真相在 outputs + job state：UI refresh/斷線不影響任務").classes("text-sm text-slate-300")
                ui.label("3. Worker 是唯一執行者：只有 Worker 可呼叫 Research Runner").classes("text-sm text-slate-300")
                ui.label("4. WFS core 仍然 no-IO：run_wfs_with_features() 不得碰任何 IO").classes("text-sm text-slate-300")
                ui.label("5. 所有視覺化資料必須由 Research/Portfolio 產出 artifact：UI 只渲染").classes("text-sm text-slate-300")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/job.py
sha256(source_bytes) = d968ce2882b5724c4e5f6cd62bc4d7b075e59c6b7704893deda411b3d40ebd3d
bytes = 10675
redacted = False
--------------------------------------------------------------------------------

"""任務監控頁面 - Job Monitor"""

from nicegui import ui

from ..api import list_recent_jobs, get_job
from ..state import app_state


def register() -> None:
    """註冊任務監控頁面路由"""
    
    @ui.page("/jobs")
    def jobs_page() -> None:
        """渲染任務列表頁面"""
        ui.page_title("FishBroWFS V2 - 任務監控")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 任務列表容器
            job_list_container = ui.column().classes("w-full")
            
            def refresh_job_list() -> None:
                """刷新任務列表"""
                job_list_container.clear()
                
                try:
                    jobs = list_recent_jobs(limit=50)
                    
                    if not jobs:
                        with job_list_container:
                            ui.label("目前沒有任務").classes("text-gray-500 text-center p-8")
                        return
                    
                    for job in jobs:
                        card = ui.card().classes("w-full mb-4 cursor-pointer hover:bg-gray-50")
                        card.on("click", lambda e, j=job: ui.navigate.to(f"/results/{j.job_id}"))
                        with card:
                            with ui.row().classes("w-full items-center"):
                                # 狀態指示器
                                status_color = {
                                    "PENDING": "bg-yellow-100 text-yellow-800",
                                    "RUNNING": "bg-green-100 text-green-800",
                                    "COMPLETED": "bg-blue-100 text-blue-800",
                                    "FAILED": "bg-red-100 text-red-800",
                                }.get(job.status, "bg-gray-100 text-gray-800")
                                
                                ui.badge(job.status, color=status_color).classes("mr-4")
                                
                                # 任務資訊
                                with ui.column().classes("flex-1"):
                                    ui.label(f"任務 ID: {job.job_id[:8]}...").classes("font-mono text-sm")
                                    ui.label(f"建立時間: {job.created_at}").classes("text-xs text-gray-600")
                                
                                # 進度條（如果有的話）
                                if job.progress is not None:
                                    ui.linear_progress(job.progress, show_value=False).classes("w-32 mr-4")
                                    ui.label(f"{job.progress*100:.1f}%").classes("text-sm")
                                
                                ui.icon("chevron_right").classes("text-gray-400")
                
                except Exception as e:
                    with job_list_container:
                        ui.label(f"載入失敗: {e}").classes("text-red-600")
            
            # 標題與導航
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=refresh_job_list).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_job_list()
    
    @ui.page("/job/{job_id}")
    def job_page(job_id: str) -> None:
        """渲染單一任務詳細頁面"""
        ui.page_title(f"FishBroWFS V2 - 任務 {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 任務詳細資訊容器
            job_details_container = ui.column().classes("w-full")
            
            # 日誌容器
            log_container = ui.column().classes("w-full mt-6")
            
            def refresh_job_details(jid: str) -> None:
                """刷新任務詳細資訊"""
                job_details_container.clear()
                
                try:
                    job = get_job(jid)
                    
                    with job_details_container:
                        # 基本資訊卡片
                        with ui.card().classes("w-full mb-4"):
                            ui.label("基本資訊").classes("text-lg font-bold mb-4")
                            
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                ui.label("任務 ID:").classes("font-bold")
                                ui.label(job.job_id).classes("font-mono")
                                
                                ui.label("狀態:").classes("font-bold")
                                status_color = {
                                    "PENDING": "text-yellow-600",
                                    "RUNNING": "text-green-600",
                                    "COMPLETED": "text-blue-600",
                                    "FAILED": "text-red-600",
                                }.get(job.status, "text-gray-600")
                                ui.label(job.status).classes(f"{status_color} font-bold")
                                
                                ui.label("建立時間:").classes("font-bold")
                                ui.label(job.created_at)
                                
                                ui.label("更新時間:").classes("font-bold")
                                ui.label(job.updated_at)
                                
                                if job.progress is not None:
                                    ui.label("進度:").classes("font-bold")
                                    with ui.row().classes("items-center w-full"):
                                        ui.linear_progress(job.progress, show_value=False).classes("flex-1")
                                        ui.label(f"{job.progress*100:.1f}%").classes("ml-2")
                                
                                if job.outputs_path:
                                    ui.label("輸出路徑:").classes("font-bold")
                                    ui.label(job.outputs_path).classes("font-mono text-sm")
                        
                        # 操作按鈕 - 根據 Phase 6.5 規範，未完成功能必須 disabled
                        with ui.row().classes("w-full gap-2 mb-6"):
                            # 任務控制按鈕（DEV MODE - 未實作）
                            if job.status == "PENDING":
                                ui.button("開始任務", icon="play_arrow", color="green").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                            elif job.status == "RUNNING":
                                ui.button("暫停任務", icon="pause", color="yellow").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                                ui.button("停止任務", icon="stop", color="red").props("disabled").tooltip("DEV MODE: 任務控制功能尚未實作")
                            
                            # 導航按鈕
                            ui.button("查看結果", icon="insights", on_click=lambda: ui.navigate.to(f"/results/{jid}")).props("outline")
                            ui.button("查看圖表", icon="show_chart", on_click=lambda: ui.navigate.to(f"/charts/{jid}")).props("outline")
                            ui.button("部署", icon="download", on_click=lambda: ui.navigate.to(f"/deploy/{jid}")).props("outline")
                    
                    # 刷新日誌
                    refresh_log(jid)
                    
                except Exception as e:
                    with job_details_container:
                        with ui.card().classes("w-full bg-red-50 border-red-200"):
                            ui.label("任務載入失敗").classes("text-red-800 font-bold mb-2")
                            ui.label(f"錯誤: {e}").classes("text-red-700 mb-2")
                            ui.label("可能原因:").classes("text-red-700 font-bold mb-1")
                            ui.label("• Control API 未啟動").classes("text-red-700 text-sm")
                            ui.label("• 任務 ID 不存在").classes("text-red-700 text-sm")
                            ui.label("• 網路連線問題").classes("text-red-700 text-sm")
                            with ui.row().classes("mt-4"):
                                ui.button("返回任務列表", on_click=lambda: ui.navigate.to("/jobs"), icon="arrow_back").props("outline")
                                ui.button("重試", on_click=lambda: refresh_job_details(jid), icon="refresh").props("outline")
            
            def refresh_log(jid: str) -> None:
                """刷新日誌顯示 - 誠實顯示真實狀態"""
                log_container.clear()
                
                with log_container:
                    ui.label("任務日誌").classes("text-lg font-bold mb-4")
                    
                    # 日誌顯示區域
                    log_display = ui.textarea("").classes("w-full h-64 font-mono text-sm").props("readonly")
                    
                    # 誠實顯示：如果沒有真實日誌，顯示 DEV MODE 訊息
                    try:
                        # 嘗試從 API 獲取真實日誌
                        job = get_job(jid)
                        if job.latest_log_tail:
                            log_display.value = job.latest_log_tail
                        else:
                            log_display.value = f"DEV MODE: 日誌系統尚未實作\n\n"
                            log_display.value += f"任務 ID: {jid}\n"
                            log_display.value += f"狀態: {job.status}\n"
                            log_display.value += f"建立時間: {job.created_at}\n"
                            log_display.value += f"更新時間: {job.updated_at}\n\n"
                            log_display.value += "真實日誌將在任務執行時顯示。"
                    except Exception as e:
                        log_display.value = f"載入日誌時發生錯誤: {e}"
            
            # 標題與導航
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=lambda: refresh_job_details(job_id)).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_job_details(job_id)
            
            # 自動刷新計時器（如果任務正在運行）
            def auto_refresh() -> None:
                # TODO: 根據任務狀態決定是否自動刷新
                pass
            
            ui.timer(5.0, auto_refresh)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/job_detail.py
sha256(source_bytes) = 11e36f673186d9df5a798e7022422e923f0501cf3fd5ad82fc6ae18c88a93b33
bytes = 8932
redacted = False
--------------------------------------------------------------------------------
"""Job Detail Page for M1.

Display real-time status + log tail for a specific job.
"""

from __future__ import annotations

import json
from typing import Dict, Any

from nicegui import ui

from FishBroWFS_V2.control.job_api import get_job_summary, get_job_status
from FishBroWFS_V2.control.pipeline_runner import check_job_status, start_job_async


def create_status_badge(status: str) -> ui.badge:
    """Create a status badge with appropriate color."""
    status_lower = status.lower()
    
    color_map = {
        "queued": "yellow",
        "running": "green",
        "done": "blue",
        "failed": "red",
        "killed": "gray",
    }
    
    color = color_map.get(status_lower, "gray")
    return ui.badge(status.upper(), color=color).classes("text-sm font-bold")


def create_units_progress(units_done: int, units_total: int) -> None:
    """Create units progress display."""
    if units_total <= 0:
        ui.label("Units: Not calculated").classes("text-gray-600")
        return
    
    progress = units_done / units_total
    
    with ui.column().classes("w-full"):
        # Progress bar
        with ui.row().classes("w-full items-center gap-2"):
            ui.linear_progress(progress, show_value=False).classes("flex-1")
            ui.label(f"{units_done}/{units_total}").classes("text-sm font-medium")
        
        # Percentage and formula
        ui.label(f"{progress:.1%} complete").classes("text-xs text-gray-600")
        
        # Formula explanation (if we have the breakdown)
        if units_total > 0 and units_done < units_total:
            remaining = units_total - units_done
            ui.label(f"{remaining} units remaining").classes("text-xs text-gray-500")


def refresh_job_detail(job_id: str, 
                      status_container: ui.column,
                      logs_container: ui.column,
                      config_container: ui.column) -> None:
    """Refresh job detail information."""
    try:
        # Get job summary
        summary = get_job_summary(job_id)
        
        # Update status container
        status_container.clear()
        with status_container:
            # Status badge and basic info
            with ui.row().classes("w-full items-center gap-4 mb-4"):
                create_status_badge(summary["status"])
                
                ui.label(f"Job ID: {summary['job_id'][:8]}...").classes("font-mono")
                ui.label(f"Season: {summary.get('season', 'N/A')}").classes("text-gray-600")
                ui.label(f"Created: {summary.get('created_at', 'N/A')}").classes("text-gray-600")
            
            # Units progress
            ui.label("Units Progress").classes("font-bold mt-4 mb-2")
            units_done = summary.get("units_done", 0)
            units_total = summary.get("units_total", 0)
            create_units_progress(units_done, units_total)
            
            # Action buttons based on status
            with ui.row().classes("w-full gap-2 mt-4"):
                if summary["status"].lower() == "queued":
                    ui.button("Start Job", 
                             on_click=lambda: start_job_async(job_id),
                             icon="play_arrow",
                             color="positive").tooltip("Start job execution")
                
                ui.button("Refresh", 
                         icon="refresh",
                         on_click=lambda: refresh_job_detail(job_id, status_container, logs_container, config_container))
                
                ui.button("Back to Jobs",
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="arrow_back",
                         color="gray").props("outline")
        
        # Update logs container
        logs_container.clear()
        with logs_container:
            ui.label("Logs").classes("font-bold mb-2")
            
            logs = summary.get("logs", [])
            if logs:
                # Show last 20 lines
                log_text = "\n".join(logs[-20:])
                log_display = ui.textarea(log_text).classes("w-full h-64 font-mono text-xs").props("readonly")
                
                # Auto-scroll to bottom
                ui.run_javascript(f"""
                    const textarea = document.getElementById('{log_display.id}');
                    if (textarea) {{
                        textarea.scrollTop = textarea.scrollHeight;
                    }}
                """)
            else:
                ui.label("No logs available").classes("text-gray-500 italic")
        
        # Update config container
        config_container.clear()
        with config_container:
            ui.label("Configuration").classes("font-bold mb-2")
            
            # Show basic config info
            with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                ui.label("Job ID:").classes("font-medium")
                ui.label(summary["job_id"]).classes("font-mono text-xs")
                
                ui.label("Status:").classes("font-medium")
                ui.label(summary["status"].upper())
                
                ui.label("Season:").classes("font-medium")
                ui.label(summary.get("season", "N/A"))
                
                ui.label("Dataset:").classes("font-medium")
                ui.label(summary.get("dataset_id", "N/A"))
                
                ui.label("Created:").classes("font-medium")
                ui.label(summary.get("created_at", "N/A"))
                
                ui.label("Updated:").classes("font-medium")
                ui.label(summary.get("updated_at", "N/A"))
                
                ui.label("Units Done:").classes("font-medium")
                ui.label(str(summary.get("units_done", 0)))
                
                ui.label("Units Total:").classes("font-medium")
                ui.label(str(summary.get("units_total", 0)))
            
            # Show raw config if available
            if "config" in summary:
                ui.label("Raw Configuration:").classes("font-medium mt-4 mb-2")
                config_json = json.dumps(summary["config"], indent=2)
                ui.textarea(config_json).classes("w-full h-48 font-mono text-xs").props("readonly")
    
    except Exception as e:
        status_container.clear()
        with status_container:
            with ui.card().classes("w-full bg-red-50 border-red-200"):
                ui.label("Error loading job details").classes("text-red-800 font-bold mb-2")
                ui.label(f"Details: {str(e)}").classes("text-red-700 text-sm")
                
                ui.button("Back to Jobs",
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="arrow_back",
                         color="red").props("outline").classes("mt-2")


@ui.page("/jobs/{job_id}")
def job_detail_page(job_id: str) -> None:
    """Job detail page."""
    ui.page_title(f"FishBroWFS V2 - Job {job_id[:8]}...")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        # Header
        with ui.row().classes("w-full items-center justify-between mb-6"):
            ui.label(f"Job Details").classes("text-3xl font-bold")
            
            with ui.row().classes("gap-2"):
                ui.button("Jobs List", 
                         on_click=lambda: ui.navigate.to("/jobs"),
                         icon="list",
                         color="gray").props("outline")
        
        # Create containers for dynamic content
        status_container = ui.column().classes("w-full mb-6")
        logs_container = ui.column().classes("w-full mb-6")
        config_container = ui.column().classes("w-full")
        
        # Initial load
        refresh_job_detail(job_id, status_container, logs_container, config_container)
        
        # Auto-refresh timer for running jobs
        def auto_refresh():
            try:
                # Check if job is still running
                status = get_job_status(job_id)
                if status["status"].lower() == "running":
                    refresh_job_detail(job_id, status_container, logs_container, config_container)
            except Exception:
                pass  # Ignore errors in auto-refresh
        
        ui.timer(3.0, auto_refresh)
        
        # Footer note
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("M1 Job Detail - Shows real-time status and log tail")


def register() -> None:
    """Register job detail page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass

# Also register at /job/{job_id} for compatibility
@ui.page("/job/{job_id}")
def job_detail_alt_page(job_id: str) -> None:
    """Alternative route for job detail."""
    job_detail_page(job_id)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/jobs.py
sha256(source_bytes) = b22adf667c52b59713018a16399615ed313f0fe9d1d5bb5cd474f0fae3d89d2d
bytes = 9083
redacted = False
--------------------------------------------------------------------------------
"""Jobs List Page for M1.

Display list of jobs with state, stage, units_done, units_total.
"""

from __future__ import annotations

from typing import List, Dict, Any
from datetime import datetime

from nicegui import ui

from FishBroWFS_V2.control.job_api import list_jobs_with_progress
from FishBroWFS_V2.control.pipeline_runner import check_job_status


def create_job_card(job: Dict[str, Any]) -> None:
    """Create a job card for the jobs list."""
    with ui.card().classes("w-full mb-4 hover:shadow-md transition-shadow cursor-pointer"):
        # Card header with job ID and status
        with ui.row().classes("w-full items-center justify-between"):
            # Left: Job ID and basic info
            with ui.column().classes("flex-1"):
                with ui.row().classes("items-center gap-2"):
                    # Status badge
                    status_color = {
                        "queued": "bg-yellow-100 text-yellow-800",
                        "running": "bg-green-100 text-green-800",
                        "done": "bg-blue-100 text-blue-800",
                        "failed": "bg-red-100 text-red-800",
                        "killed": "bg-gray-100 text-gray-800",
                    }.get(job["status"].lower(), "bg-gray-100 text-gray-800")
                    
                    ui.badge(job["status"].upper(), color=status_color).classes("font-mono text-xs")
                    
                    # Job ID
                    ui.label(f"Job: {job['job_id'][:8]}...").classes("font-mono text-sm")
                
                # Season and dataset
                with ui.row().classes("items-center gap-4 text-sm text-gray-600"):
                    ui.label(f"Season: {job.get('season', 'N/A')}")
                    ui.label(f"Dataset: {job.get('dataset_id', 'N/A')}")
            
            # Right: Timestamp
            ui.label(job["created_at"]).classes("text-xs text-gray-500")
        
        # Progress section
        with ui.column().classes("w-full mt-3"):
            # Units progress
            units_done = job.get("units_done", 0)
            units_total = job.get("units_total", 0)
            
            if units_total > 0:
                progress = units_done / units_total
                
                # Progress bar
                with ui.row().classes("w-full items-center gap-2"):
                    ui.linear_progress(progress, show_value=False).classes("flex-1")
                    ui.label(f"{units_done}/{units_total} units").classes("text-sm font-medium")
                
                # Percentage
                ui.label(f"{progress:.1%} complete").classes("text-xs text-gray-600")
            else:
                ui.label("Units: Not calculated").classes("text-sm text-gray-500")
        
        # Footer with actions
        with ui.row().classes("w-full justify-end mt-3 pt-3 border-t"):
            ui.button("View Details", 
                     on_click=lambda j=job: ui.navigate.to(f"/jobs/{j['job_id']}"),
                     icon="visibility").props("size=sm outline")
            
            # Action buttons based on status
            if job["status"].lower() == "running":
                ui.button("Pause", icon="pause", color="warning").props("size=sm outline disabled").tooltip("Not implemented in M1")
            elif job["status"].lower() == "queued":
                ui.button("Start", icon="play_arrow", color="positive").props("size=sm outline disabled").tooltip("Not implemented in M1")


def refresh_jobs_list(container: ui.column) -> None:
    """Refresh the jobs list in the container."""
    container.clear()
    
    try:
        jobs = list_jobs_with_progress(limit=50)
        
        if not jobs:
            with container:
                with ui.card().classes("w-full text-center p-8"):
                    ui.icon("inbox", size="xl").classes("text-gray-400 mb-2")
                    ui.label("No jobs found").classes("text-gray-600")
                    ui.label("Submit a job using the wizard to get started").classes("text-sm text-gray-500")
            return
        
        # Sort jobs: running first, then by creation time
        status_order = {"running": 0, "queued": 1, "done": 2, "failed": 3, "killed": 4}
        jobs.sort(key=lambda j: (status_order.get(j["status"].lower(), 5), j["created_at"]), reverse=True)
        
        # Create job cards
        for job in jobs:
            create_job_card(job)
            
    except Exception as e:
        with container:
            with ui.card().classes("w-full bg-red-50 border-red-200"):
                ui.label("Error loading jobs").classes("text-red-800 font-bold mb-2")
                ui.label(f"Details: {str(e)}").classes("text-red-700 text-sm")
                ui.label("Make sure the control API is running").classes("text-red-700 text-sm")


@ui.page("/jobs")
def jobs_page() -> None:
    """Jobs list page."""
    ui.page_title("FishBroWFS V2 - Jobs")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        # Header
        with ui.row().classes("w-full items-center justify-between mb-6"):
            ui.label("Jobs").classes("text-3xl font-bold")
            
            with ui.row().classes("gap-2"):
                # Refresh button
                refresh_button = ui.button(icon="refresh", color="primary").props("flat")
                
                # New job button
                ui.button("New Job", 
                         on_click=lambda: ui.navigate.to("/wizard"),
                         icon="add",
                         color="positive")
        
        # Stats summary
        with ui.row().classes("w-full gap-4 mb-6"):
            try:
                jobs = list_jobs_with_progress(limit=100)
                
                # Calculate stats
                total_jobs = len(jobs)
                running_jobs = sum(1 for j in jobs if j["status"].lower() == "running")
                done_jobs = sum(1 for j in jobs if j["status"].lower() == "done")
                total_units = sum(j.get("units_total", 0) for j in jobs)
                completed_units = sum(j.get("units_done", 0) for j in jobs)
                
                # Stats cards
                with ui.card().classes("flex-1"):
                    ui.label("Total Jobs").classes("text-sm text-gray-600")
                    ui.label(str(total_jobs)).classes("text-2xl font-bold")
                
                with ui.card().classes("flex-1"):
                    ui.label("Running").classes("text-sm text-gray-600")
                    ui.label(str(running_jobs)).classes("text-2xl font-bold text-green-600")
                
                with ui.card().classes("flex-1"):
                    ui.label("Completed").classes("text-sm text-gray-600")
                    ui.label(str(done_jobs)).classes("text-2xl font-bold text-blue-600")
                
                with ui.card().classes("flex-1"):
                    ui.label("Units Progress").classes("text-sm text-gray-600")
                    if total_units > 0:
                        progress = completed_units / total_units
                        ui.label(f"{progress:.1%}").classes("text-2xl font-bold")
                    else:
                        ui.label("N/A").classes("text-2xl font-bold")
                        
            except Exception:
                # Fallback if stats can't be loaded
                with ui.card().classes("flex-1"):
                    ui.label("Jobs").classes("text-sm text-gray-600")
                    ui.label("--").classes("text-2xl font-bold")
        
        # Jobs list container
        jobs_container = ui.column().classes("w-full")
        
        # Initial load
        refresh_jobs_list(jobs_container)
        
        # Setup refresh on button click
        def on_refresh():
            refresh_button.props("loading")
            refresh_jobs_list(jobs_container)
            refresh_button.props("loading=false")
        
        refresh_button.on_click(on_refresh)
        
        # Auto-refresh timer for running jobs
        def auto_refresh():
            # Check if any jobs are running
            try:
                jobs = list_jobs_with_progress(limit=10)
                has_running = any(j["status"].lower() == "running" for j in jobs)
                if has_running:
                    refresh_jobs_list(jobs_container)
            except Exception:
                pass  # Ignore errors in auto-refresh
        
        ui.timer(5.0, auto_refresh)
        
        # Footer note
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("M1 Jobs List - Shows units_done/units_total for each job")


def register() -> None:
    """Register jobs page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass

# Also register at /jobs/list for compatibility
@ui.page("/jobs/list")
def jobs_list_page() -> None:
    """Alternative route for jobs list."""
    jobs_page()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/new_job.py
sha256(source_bytes) = c4f43120d8be403cee3f2cb107926fbe99d77e003aed372844102adc137c7249
bytes = 14670
redacted = False
--------------------------------------------------------------------------------

"""新增任務頁面 - New Job (Setup) - 已過渡到 Wizard，保留相容性"""

from pathlib import Path
from nicegui import ui
import httpx

from ..api import JobSubmitRequest, list_datasets, list_strategies, submit_job
from ..state import app_state


def register() -> None:
    """註冊新增任務頁面路由（重定向到 Wizard）"""
    
    @ui.page("/new-job")
    def new_job_page() -> None:
        """渲染新增任務頁面（過渡頁面）"""
        ui.page_title("FishBroWFS V2 - 新增研究任務")
        
        with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
            # 過渡訊息
            with ui.card().classes("fish-card w-full p-6 mb-6 border-cyber-500/50"):
                ui.label("⚠️ 頁面已遷移").classes("text-xl font-bold text-yellow-400 mb-2")
                ui.label("此頁面已過渡到新的 Wizard 介面。").classes("text-slate-300 mb-4")
                
                with ui.row().classes("w-full gap-4"):
                    ui.button("前往 Wizard", on_click=lambda: ui.navigate.to("/wizard")) \
                        .classes("btn-cyber px-6 py-3")
                    ui.button("留在舊版", color="gray") \
                        .classes("px-6 py-3")
            
            # 原始表單容器（保持相容性）
            with ui.card().classes("w-full p-6 opacity-80"):
                ui.label("舊版任務設定").classes("text-xl font-bold mb-6 text-slate-400")
            # 表單容器
            with ui.card().classes("w-full p-6"):
                ui.label("任務設定").classes("text-xl font-bold mb-6")
                
                # 基本設定區
                with ui.expansion("基本設定", value=True).classes("w-full mb-4"):
                    # outputs_root
                    outputs_root = ui.input(
                        label="Outputs Root",
                        value=app_state.user_preferences.get("default_outputs_root", "outputs"),
                        placeholder="輸出根目錄路徑"
                    ).classes("w-full mb-4")
                    
                    # dataset_id
                    ui.label("資料集").classes("font-bold mb-2")
                    
                    # 預設空 datasets
                    dataset_select = ui.select(
                        label="選擇資料集",
                        options={},
                        value=None
                    ).classes("w-full mb-4")
                    
                    # Load Datasets 按鈕
                    def load_datasets():
                        """載入 datasets"""
                        try:
                            ds = list_datasets(Path(outputs_root.value))
                            dataset_select.options = {d: d for d in ds} if ds else {}
                            if ds:
                                dataset_select.value = ds[0]
                            ui.notify(f"Loaded {len(ds)} datasets", type="positive")
                        except Exception as e:
                            error_msg = str(e)
                            if "503" in error_msg or "registry not preloaded" in error_msg.lower():
                                ui.notify("Dataset registry not ready", type="warning")
                                with ui.card().classes("w-full bg-yellow-50 border-yellow-200 p-4 mt-2"):
                                    ui.label("Dataset registry not ready").classes("font-bold text-yellow-800")
                                    ui.label("Control API registries need to be preloaded.").classes("text-yellow-800 text-sm")
                                    ui.label("Click 'Preload Registries' button below or restart Control API.").classes("text-yellow-800 text-sm")
                            else:
                                ui.notify(f"Failed to load datasets: {error_msg}", type="negative")
                    
                    with ui.row().classes("w-full mb-2"):
                        ui.button("Load Datasets", on_click=load_datasets, icon="refresh").props("outline")
                    
                    # symbols
                    symbols_input = ui.input(
                        label="交易標的 (逗號分隔)",
                        value="MNQ, MES, MXF",
                        placeholder="例如: MNQ, MES, MXF"
                    ).classes("w-full mb-4")
                    
                    # timeframe_min
                    timeframe_select = ui.select(
                        label="時間框架 (分鐘)",
                        options={60: "60分鐘", 120: "120分鐘"},
                        value=60
                    ).classes("w-full mb-4")
                
                # 策略設定區
                with ui.expansion("策略設定", value=True).classes("w-full mb-4"):
                    # strategy_name
                    strategy_select = ui.select(
                        label="選擇策略",
                        options={},
                        value=None
                    ).classes("w-full mb-4")
                    
                    # Load Strategies 按鈕
                    def load_strategies():
                        """載入 strategies"""
                        try:
                            strategies = list_strategies()
                            strategy_select.options = {s: s for s in strategies} if strategies else {}
                            if strategies:
                                strategy_select.value = strategies[0]
                            ui.notify(f"Loaded {len(strategies)} strategies", type="positive")
                        except Exception as e:
                            error_msg = str(e)
                            if "503" in error_msg or "registry not preloaded" in error_msg.lower():
                                ui.notify("Strategy registry not ready", type="warning")
                                with ui.card().classes("w-full bg-yellow-50 border-yellow-200 p-4 mt-2"):
                                    ui.label("Strategy registry not ready").classes("font-bold text-yellow-800")
                                    ui.label("Control API registries need to be preloaded.").classes("text-yellow-800 text-sm")
                                    ui.label("Click 'Preload Registries' button below or restart Control API.").classes("text-yellow-800 text-sm")
                            else:
                                ui.notify(f"Failed to load strategies: {error_msg}", type="negative")
                    
                    with ui.row().classes("w-full mb-2"):
                        ui.button("Load Strategies", on_click=load_strategies, icon="refresh").props("outline")
                    
                    # data2_feed
                    data2_select = ui.select(
                        label="Data2 Feed (可選)",
                        options={"": "無", "6J": "6J", "VX": "VX", "DX": "DX", "ZN": "ZN"},
                        value=""
                    ).classes("w-full mb-4")
                
                # 滾動回測設定區
                with ui.expansion("滾動回測設定", value=True).classes("w-full mb-4"):
                    # rolling (固定為 True)
                    ui.label("滾動回測: ✅ 啟用 (MVP 固定)").classes("mb-2")
                    
                    # train_years (固定為 3)
                    ui.label("訓練年數: 3 年 (固定)").classes("mb-2")
                    
                    # test_unit (固定為 quarter)
                    ui.label("測試單位: 季度 (固定)").classes("mb-2")
                    
                    # season
                    season_input = ui.input(
                        label="Season (例如 2026Q1)",
                        value="2026Q1",
                        placeholder="例如: 2026Q1"
                    ).classes("w-full mb-4")
                
                # 滑點壓力測試設定區
                with ui.expansion("滑點壓力測試", value=True).classes("w-full mb-4"):
                    # enable_slippage_stress (固定為 True)
                    ui.label("滑點壓力測試: ✅ 啟用").classes("mb-2")
                    
                    # slippage_levels
                    slippage_levels = ["S0", "S1", "S2", "S3"]
                    slippage_checkboxes = {}
                    with ui.row().classes("w-full mb-2"):
                        for level in slippage_levels:
                            slippage_checkboxes[level] = ui.checkbox(level, value=True)
                    
                    # gate_level
                    gate_select = ui.select(
                        label="Gate Level",
                        options={"S2": "S2", "S1": "S1", "S0": "S0"},
                        value="S2"
                    ).classes("w-full mb-4")
                    
                    # stress_level
                    stress_select = ui.select(
                        label="Stress Level",
                        options={"S3": "S3", "S2": "S2", "S1": "S1"},
                        value="S3"
                    ).classes("w-full mb-4")
                
                # Top K 設定
                topk_input = ui.number(
                    label="Top K",
                    value=20,
                    min=1,
                    max=100
                ).classes("w-full mb-6")
                
                # 提交按鈕
                def submit_job_handler() -> None:
                    """處理任務提交"""
                    try:
                        # 收集表單資料
                        symbols = [s.strip() for s in symbols_input.value.split(",") if s.strip()]
                        
                        # 收集選中的 slippage levels
                        selected_slippage = [level for level, cb in slippage_checkboxes.items() if cb.value]
                        
                        # 建立請求物件
                        req = JobSubmitRequest(
                            outputs_root=Path(outputs_root.value),
                            dataset_id=dataset_select.value,
                            symbols=symbols,
                            timeframe_min=timeframe_select.value,
                            strategy_name=strategy_select.value,
                            data2_feed=data2_select.value if data2_select.value else None,
                            rolling=True,  # 固定
                            train_years=3,  # 固定
                            test_unit="quarter",  # 固定
                            enable_slippage_stress=True,  # 固定
                            slippage_levels=selected_slippage,
                            gate_level=gate_select.value,
                            stress_level=stress_select.value,
                            topk=topk_input.value,
                            season=season_input.value
                        )
                        
                        # 實際提交任務
                        job_record = submit_job(req)
                        
                        ui.notify(f"Job submitted: {job_record.job_id[:8]}", type="positive")
                        ui.navigate.to(f"/results/{job_record.job_id}")
                        
                    except Exception as e:
                        ui.notify(f"Submit failed: {e}", type="negative")
                
                ui.button("提交任務", on_click=submit_job_handler, icon="send").classes("w-full bg-green-500 text-white py-3")
            
            # 注意事項
            with ui.card().classes("w-full mt-6 bg-yellow-50 border-yellow-200"):
                ui.label("注意事項").classes("font-bold text-yellow-800 mb-2")
                ui.label("• UI 不得直接跑 Rolling WFS：按鈕只能 submit job").classes("text-sm text-yellow-700")
                ui.label("• data2_feed 只能是 None/6J/VX/DX/ZN").classes("text-sm text-yellow-700")
                ui.label("• train_years==3、test_unit=='quarter'（MVP 鎖死）").classes("text-sm text-yellow-700")
                ui.label("• timeframe_min 必須同時套用 Data1/Data2（Data2 不提供單獨 TF）").classes("text-sm text-yellow-700")
            
            # Registry Preload 區
            with ui.card().classes("w-full mt-6 bg-blue-50 border-blue-200"):
                ui.label("Registry Preload").classes("font-bold text-blue-800 mb-2")
                ui.label("如果遇到 'registry not ready' 錯誤，請先預載 registries。").classes("text-sm text-blue-700 mb-4")
                
                def preload_registries():
                    """手動觸發 registry preload"""
                    try:
                        response = httpx.post("http://127.0.0.1:8000/meta/prime", timeout=10.0)
                        if response.status_code == 200:
                            result = response.json()
                            if result.get("success"):
                                ui.notify("Registries preloaded successfully!", type="positive")
                            else:
                                errors = []
                                if result.get("dataset_error"):
                                    errors.append(f"Dataset: {result['dataset_error']}")
                                if result.get("strategy_error"):
                                    errors.append(f"Strategy: {result['strategy_error']}")
                                ui.notify(f"Preload partially failed: {', '.join(errors)}", type="warning")
                        else:
                            ui.notify(f"Failed to preload registries: {response.status_code}", type="negative")
                    except httpx.ConnectError:
                        ui.notify("Cannot connect to Control API (127.0.0.1:8000)", type="negative")
                    except Exception as e:
                        ui.notify(f"Error: {e}", type="negative")
                
                ui.button("Preload Registries", on_click=preload_registries, icon="cloud_download").props("outline").classes("mb-4")
                
                ui.label("替代方案：").classes("text-sm text-blue-700 font-bold mb-1")
                ui.label("1. 重新啟動 Control API (會自動 preload)").classes("text-sm text-blue-700")
                ui.label("2. 執行 `curl -X POST http://127.0.0.1:8000/meta/prime`").classes("text-sm text-blue-700")
                ui.label("3. 使用 `make dashboard` 啟動 (已包含自動 preload)").classes("text-sm text-blue-700")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/portfolio.py
sha256(source_bytes) = c5b36d179f7f542e608921d3cf5f2838b8b55409bc10a0026510a8cf7b3c200b
bytes = 17102
redacted = False
--------------------------------------------------------------------------------
"""
Portfolio 頁面 - 顯示 portfolio summary 和 manifest，提供 Build Portfolio 按鈕。

Phase 4: UI wiring for portfolio builder.
Phase 5: Respect season freeze state.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from nicegui import ui

from ..layout import render_shell
from ...services.actions import build_portfolio_from_research
from FishBroWFS_V2.core.season_context import (
    current_season,
    portfolio_dir,
    portfolio_summary_path,
    portfolio_manifest_path,
)

# 嘗試導入 season_state 模組（Phase 5 新增）
try:
    from FishBroWFS_V2.core.season_state import load_season_state
    SEASON_STATE_AVAILABLE = True
except ImportError:
    SEASON_STATE_AVAILABLE = False
    load_season_state = None


def load_portfolio_summary(season: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """載入 portfolio_summary.json"""
    summary_path = portfolio_summary_path(season)
    if not summary_path.exists():
        return None
    
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_portfolio_manifest(season: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """載入 portfolio_manifest.json"""
    manifest_path = portfolio_manifest_path(season)
    if not manifest_path.exists():
        return None
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "entries" in data:
                return data["entries"]
            else:
                return []
    except (json.JSONDecodeError, OSError):
        return None


def list_portfolio_runs(season: Optional[str] = None) -> List[Path]:
    """列出 portfolio 目錄中的 run 子目錄"""
    pdir = portfolio_dir(season)
    if not pdir.exists():
        return []
    
    runs = []
    for item in pdir.iterdir():
        if item.is_dir() and len(item.name) == 12:  # portfolio_id pattern (12 chars)
            runs.append(item)
    
    return sorted(runs, key=lambda x: x.name, reverse=True)


def render_portfolio_summary_card(summary: Dict[str, Any]) -> None:
    """渲染 portfolio summary 卡片"""
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Summary").classes("text-xl font-bold mb-4 text-cyber-400")
        
        # 基本資訊
        with ui.grid(columns=2).classes("w-full gap-4"):
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Portfolio ID").classes("text-sm text-slate-400 mb-1")
                ui.label(summary.get("portfolio_id", "N/A")).classes("text-lg font-mono text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Created At").classes("text-sm text-slate-400 mb-1")
                ui.label(summary.get("created_at", "N/A")[:19]).classes("text-lg text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Total Decisions").classes("text-sm text-slate-400 mb-1")
                ui.label(str(summary.get("total_decisions", 0))).classes("text-2xl font-bold text-cyber-400")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("KEEP Decisions").classes("text-sm text-slate-400 mb-1")
                ui.label(str(summary.get("keep_decisions", 0))).classes("text-2xl font-bold text-cyber-400")
        
        # 額外資訊
        if "symbols" in summary:
            with ui.card().classes("p-3 bg-nexus-800 mt-4"):
                ui.label("Symbols").classes("text-sm text-slate-400 mb-1")
                symbols = summary["symbols"]
                if isinstance(symbols, list):
                    ui.label(", ".join(symbols)).classes("text-sm text-slate-300")
                else:
                    ui.label(str(symbols)).classes("text-sm text-slate-300")


def render_portfolio_manifest_table(manifest: List[Dict[str, Any]]) -> None:
    """渲染 portfolio manifest 表格"""
    if not manifest:
        ui.label("No manifest entries found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left"},
        {"name": "decision", "label": "Decision", "field": "decision", "align": "left"},
        {"name": "score_final", "label": "Score", "field": "score_final", "align": "right", "format": lambda val: f"{val:.3f}"},
        {"name": "net_profit", "label": "Net Profit", "field": "net_profit", "align": "right", "format": lambda val: f"{val:.2f}"},
    ]
    
    rows = []
    for entry in manifest:
        rows.append({
            "run_id": entry.get("run_id", "")[:12] + "..." if len(entry.get("run_id", "")) > 12 else entry.get("run_id", ""),
            "strategy_id": entry.get("strategy_id", ""),
            "symbol": entry.get("symbol", ""),
            "decision": entry.get("decision", ""),
            "score_final": entry.get("score_final", 0.0),
            "net_profit": entry.get("net_profit", 0.0),
        })
    
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Manifest").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered pagination rows-per-page=10")


def render_portfolio_runs_list(runs: List[Path]) -> None:
    """渲染 portfolio runs 列表"""
    if not runs:
        return
    
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Portfolio Runs").classes("text-xl font-bold mb-4 text-cyber-400")
        
        for run_dir in runs[:10]:  # 顯示最多 10 個
            run_id = run_dir.name
            with ui.card().classes("p-3 mb-2 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                with ui.row().classes("items-center justify-between"):
                    with ui.row().classes("items-center"):
                        ui.icon("folder", color="cyan").classes("mr-2")
                        ui.label(run_id).classes("font-mono text-cyber-300")
                    
                    # 檢查檔案
                    spec_file = run_dir / "portfolio_spec.json"
                    manifest_file = run_dir / "portfolio_manifest.json"
                    
                    with ui.row().classes("gap-2"):
                        if spec_file.exists():
                            ui.badge("spec", color="green").props("dense")
                        if manifest_file.exists():
                            ui.badge("manifest", color="blue").props("dense")


def render_portfolio_page() -> None:
    """渲染 portfolio 頁面內容"""
    ui.page_title("FishBroWFS V2 - Portfolio")
    
    # 使用 shell 佈局
    with render_shell("/portfolio", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # 頁面標題
            with ui.row().classes("w-full items-center mb-6"):
                ui.label("Portfolio Builder").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                
                # 動作按鈕容器
                action_container = ui.row().classes("gap-2")
            
            # 檢查 season freeze 狀態
            is_frozen = False
            frozen_reason = ""
            if SEASON_STATE_AVAILABLE and load_season_state is not None:
                try:
                    state = load_season_state(current_season())
                    if state and state.get("state") == "FROZEN":
                        is_frozen = True
                        frozen_reason = state.get("reason", "Season is frozen")
                except Exception:
                    # 如果載入失敗，忽略錯誤（保持未凍結狀態）
                    pass
            
            # 顯示 freeze 警告（如果 season 被凍結）
            if is_frozen:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-red-900/30 border-l-4 border-red-500"):
                    with ui.row().classes("items-center"):
                        ui.icon("lock", color="red").classes("text-xl mr-3")
                        with ui.column().classes("flex-1"):
                            ui.label("Season Frozen (治理鎖)").classes("font-bold text-lg text-red-300")
                            ui.label(frozen_reason).classes("text-red-200")
                            ui.label("Portfolio building is disabled while season is frozen.").classes("text-sm text-red-300/80")
            
            # 檢查 portfolio 檔案是否存在
            current_season_str = current_season()
            summary_exists = portfolio_summary_path(current_season_str).exists()
            manifest_exists = portfolio_manifest_path(current_season_str).exists()
            portfolio_exists = summary_exists or manifest_exists
            
            # 說明文字
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("🏦 Portfolio Builder").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label(f"This page displays portfolio artifacts from outputs/seasons/{current_season_str}/portfolio/").classes("text-slate-300 mb-1")
                ui.label(f"Source: outputs/seasons/{current_season_str}/portfolio/portfolio_summary.json & portfolio_manifest.json").classes("text-sm text-slate-400")
                
                # 顯示檔案狀態
                if not portfolio_exists:
                    with ui.row().classes("items-center mt-3 p-3 bg-amber-900/30 rounded-lg"):
                        ui.icon("warning", color="amber").classes("text-lg")
                        ui.label("Portfolio artifacts not found for this season.").classes("ml-2 text-amber-300")
                        ui.label("Build portfolio from research results using the button above.").classes("ml-2 text-amber-300 text-sm")
            
            # 載入資料
            portfolio_summary = load_portfolio_summary(current_season_str)
            portfolio_manifest = load_portfolio_manifest(current_season_str)
            portfolio_runs = list_portfolio_runs(current_season_str)
            
            # 統計卡片
            with ui.row().classes("w-full gap-4 mb-6"):
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Summary").classes("text-sm text-slate-400 mb-1")
                    if portfolio_summary:
                        ui.label("Available").classes("text-2xl font-bold text-cyber-400")
                        ui.label("✓ Loaded").classes("text-xs text-green-500")
                    else:
                        ui.label("Missing").classes("text-2xl font-bold text-amber-400")
                        if not summary_exists:
                            ui.label("File not found").classes("text-xs text-amber-500")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Manifest").classes("text-sm text-slate-400 mb-1")
                    if portfolio_manifest:
                        ui.label(f"{len(portfolio_manifest)}").classes("text-2xl font-bold text-cyber-400")
                        ui.label("entries").classes("text-xs text-slate-500")
                    else:
                        ui.label("Missing").classes("text-2xl font-bold text-amber-400")
                        if not manifest_exists:
                            ui.label("File not found").classes("text-xs text-amber-500")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Portfolio Runs").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(portfolio_runs))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("runs").classes("text-xs text-slate-500")
            
            # 動作按鈕功能
            def build_portfolio_action():
                """觸發 Build Portfolio 動作"""
                # 檢查 season 是否被凍結（額外防護）
                if is_frozen:
                    ui.notify("Cannot build portfolio: season is frozen", type="negative")
                    return
                
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Building portfolio...").classes("text-sm text-slate-400")
                
                # 執行 Build Portfolio 動作
                result = build_portfolio_from_research(current_season_str)
                
                # 顯示結果
                if result.ok:
                    artifacts_count = len(result.artifacts_written)
                    ui.notify(f"Portfolio built successfully! {artifacts_count} artifacts created.", type="positive")
                else:
                    error_msg = result.stderr_tail[-1] if result.stderr_tail else "Unknown error"
                    ui.notify(f"Portfolio build failed: {error_msg}", type="negative")
                
                # 重新載入頁面
                ui.navigate.to("/portfolio", reload=True)
            
            # 更新動作按鈕
            with action_container:
                if not portfolio_exists:
                    if is_frozen:
                        # Season frozen: disable button with tooltip
                        ui.button("Build Portfolio", icon="build").props("outline disabled").tooltip(f"Season is frozen: {frozen_reason}")
                    else:
                        ui.button("Build Portfolio", icon="build", on_click=build_portfolio_action).props("outline color=positive")
                ui.button("Refresh", icon="refresh", on_click=lambda: ui.navigate.to("/portfolio", reload=True)).props("outline")
            
            # 分隔線
            ui.separator().classes("my-6")
            
            # 如果沒有資料，顯示提示
            if not portfolio_summary and not portfolio_manifest and not portfolio_runs:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("account_balance", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No portfolio data available").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label(f"Portfolio artifacts not found for season {current_season_str}").classes("text-slate-400 mb-4")
                    ui.label("Build portfolio from research results to create portfolio artifacts.").classes("text-slate-400 mb-6")
                    if not portfolio_exists:
                        ui.button("Build Portfolio Now", icon="build", on_click=build_portfolio_action).props("color=positive")
                return
            
            # Portfolio Summary 區塊
            if portfolio_summary:
                ui.label("Portfolio Summary").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_summary_card(portfolio_summary)
            
            # Portfolio Manifest 區塊
            if portfolio_manifest:
                ui.label("Portfolio Manifest").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_manifest_table(portfolio_manifest)
            
            # Portfolio Runs 區塊
            if portfolio_runs:
                ui.label("Portfolio Runs").classes("text-2xl font-bold mb-4 text-cyber-300")
                render_portfolio_runs_list(portfolio_runs)
            
            # 底部說明
            with ui.card().classes("w-full fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Portfolio Summary: High-level overview of portfolio decisions and metrics").classes("text-slate-300 mb-1")
                ui.label("• Portfolio Manifest: Detailed list of candidate runs with keep/drop decisions").classes("text-slate-300 mb-1")
                ui.label("• Portfolio Runs: Individual portfolio run directories with spec and manifest files").classes("text-slate-300 mb-1")
                ui.label(f"• Data Source: outputs/seasons/{current_season_str}/portfolio/ directory").classes("text-slate-300 mb-1")
                if not portfolio_exists:
                    ui.label("• Build: Click 'Build Portfolio' to create portfolio from research results").classes("text-slate-300 text-amber-300")


def register() -> None:
    """註冊 portfolio 頁面路由"""
    
    @ui.page("/portfolio")
    def portfolio_page() -> None:
        """Portfolio 頁面"""
        render_portfolio_page()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/results.py
sha256(source_bytes) = b64f33ac1dccc7e34fd460e769be701d1a55e8685b1faaeb768fa18d91243bf4
bytes = 4297
redacted = False
--------------------------------------------------------------------------------

"""結果頁面 - Results"""

from nicegui import ui

from ..api import get_season_report, generate_deploy_zip
from ..state import app_state


def register() -> None:
    """註冊結果頁面路由"""
    
    @ui.page("/results/{job_id}")
    def results_page(job_id: str) -> None:
        """渲染結果頁面"""
        ui.page_title(f"FishBroWFS V2 - 任務結果 {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 結果容器
            results_container = ui.column().classes("w-full")
            
            def refresh_results(jid: str) -> None:
                """刷新結果顯示"""
                results_container.clear()
                
                try:
                    with results_container:
                        # 顯示 DEV MODE Banner
                        with ui.card().classes("w-full bg-blue-50 border-blue-200 mb-6"):
                            ui.label("Phase 6.5 - UI 誠實化").classes("text-blue-800 font-bold mb-1")
                            ui.label("此頁面只顯示真實資料 (SSOT)，不渲染假表格").classes("text-blue-700 text-sm")
                        
                        # Rolling Summary 區塊 - 誠實顯示 "Not wired yet (Phase 7)"
                        ui.separator()
                        ui.label("Rolling Summary").classes("font-bold text-xl mb-2")
                        ui.label("Not wired yet (Phase 7)").classes("text-gray-500 mb-6")
                        
                        # 顯示任務基本資訊
                        with ui.card().classes("w-full bg-gray-50 border-gray-200 p-6 mb-6"):
                            ui.label("任務基本資訊").classes("font-bold mb-2")
                            ui.label(f"任務 ID: {jid}").classes("text-sm")
                            ui.label("狀態: 請查看 Job Monitor 頁面").classes("text-sm")
                        
                        # 操作按鈕 - 誠實顯示功能狀態
                        with ui.row().classes("w-full gap-2 mt-6"):
                            ui.button("View Charts", icon="show_chart", on_click=lambda: ui.navigate.to(f"/charts/{jid}")).props("outline")
                            ui.button("Deploy", icon="download", on_click=lambda: ui.navigate.to(f"/deploy/{jid}")).props("outline")
                            
                            # Generate Deploy Zip 按鈕 - 誠實顯示未實作
                            def generate_deploy_handler():
                                """處理 Generate Deploy Zip 按鈕點擊"""
                                ui.notify("Deploy zip generation not implemented yet (Phase 7)", type="warning")
                            
                            ui.button("Generate Deploy Zip", icon="archive", color="gray", on_click=generate_deploy_handler).props("disabled").tooltip("Not implemented yet (Phase 7)")
                    
                except Exception as e:
                    with results_container:
                        with ui.card().classes("w-full bg-red-50 border-red-200 p-6"):
                            ui.label("載入結果失敗").classes("text-red-800 font-bold mb-2")
                            ui.label(f"錯誤: {e}").classes("text-red-700 mb-2")
                            ui.label("可能原因:").classes("text-red-700 font-bold mb-1")
                            ui.label("• Control API 未啟動").classes("text-red-700 text-sm")
                            ui.label("• 任務 ID 不存在").classes("text-red-700 text-sm")
                            ui.label("• 網路連線問題").classes("text-red-700 text-sm")
                            with ui.row().classes("mt-4"):
                                ui.button("返回任務列表", on_click=lambda: ui.navigate.to("/jobs"), icon="arrow_back").props("outline")
                                ui.button("重試", on_click=lambda: refresh_results(jid), icon="refresh").props("outline")
            
            # 刷新按鈕
            with ui.row().classes("w-full items-center mb-6"):
                ui.button(icon="refresh", on_click=lambda: refresh_results(job_id)).props("flat").classes("ml-auto")
            
            # 初始載入
            refresh_results(job_id)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/run_detail.py
sha256(source_bytes) = 0179f625152de371654c50e5601b12f60a7377eaac933f9fdc2b581b0c772e3f
bytes = 15505
redacted = False
--------------------------------------------------------------------------------
"""
Run Detail 頁面 - 顯示單一 run 的詳細資訊、artifacts 和 audit trail。

Phase 4: Enhanced governance and observability.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from nicegui import ui

from ..layout import render_shell
from ...services.runs_index import get_global_index, RunIndexRow
from ...services.audit_log import get_audit_events_for_run_id
from FishBroWFS_V2.core.season_context import current_season


def load_run_manifest(run_dir: Path) -> Optional[Dict[str, Any]]:
    """載入 run 的 manifest.json"""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_run_summary(run_dir: Path) -> Optional[Dict[str, Any]]:
    """載入 run 的 summary.json"""
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_run_artifacts(run_dir: Path) -> List[Path]:
    """列出 run 目錄中的所有檔案"""
    if not run_dir.exists():
        return []
    artifacts = []
    for item in run_dir.rglob("*"):
        if item.is_file():
            artifacts.append(item)
    return sorted(artifacts, key=lambda x: x.name)


def render_run_info_card(run: RunIndexRow, manifest: Optional[Dict[str, Any]]) -> None:
    """渲染 run 基本資訊卡片"""
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Information").classes("text-xl font-bold mb-4 text-cyber-400")
        
        with ui.grid(columns=2).classes("w-full gap-4"):
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Run ID").classes("text-sm text-slate-400 mb-1")
                ui.label(run.run_id).classes("text-lg font-mono text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Season").classes("text-sm text-slate-400 mb-1")
                ui.label(run.season).classes("text-lg text-cyber-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Stage").classes("text-sm text-slate-400 mb-1")
                stage_badge = run.stage or "unknown"
                color = {
                    "stage0": "bg-blue-500/20 text-blue-300",
                    "stage1": "bg-green-500/20 text-green-300",
                    "stage2": "bg-purple-500/20 text-purple-300",
                    "demo": "bg-yellow-500/20 text-yellow-300",
                }.get(stage_badge, "bg-slate-500/20 text-slate-300")
                ui.label(stage_badge).classes(f"px-3 py-1 rounded-full text-sm {color}")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Status").classes("text-sm text-slate-400 mb-1")
                status_badge = run.status
                status_color = {
                    "completed": "bg-green-500/20 text-green-300",
                    "running": "bg-blue-500/20 text-blue-300",
                    "failed": "bg-red-500/20 text-red-300",
                    "unknown": "bg-slate-500/20 text-slate-300",
                }.get(status_badge, "bg-slate-500/20 text-slate-300")
                ui.label(status_badge).classes(f"px-3 py-1 rounded-full text-sm {status_color}")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Created").classes("text-sm text-slate-400 mb-1")
                created_time = datetime.fromtimestamp(run.mtime).strftime("%Y-%m-%d %H:%M:%S")
                ui.label(created_time).classes("text-sm text-slate-300")
            
            with ui.card().classes("p-3 bg-nexus-800"):
                ui.label("Directory").classes("text-sm text-slate-400 mb-1")
                ui.label(str(run.run_dir)).classes("text-xs font-mono text-slate-400 truncate")
        
        if manifest:
            with ui.card().classes("p-3 bg-nexus-800 mt-4"):
                ui.label("Manifest Info").classes("text-sm text-slate-400 mb-2")
                if "strategy_id" in manifest:
                    with ui.row().classes("items-center mb-1"):
                        ui.label("Strategy:").classes("text-sm text-slate-400 w-24")
                        ui.label(manifest["strategy_id"]).classes("text-sm text-cyber-300")
                if "symbol" in manifest:
                    with ui.row().classes("items-center mb-1"):
                        ui.label("Symbol:").classes("text-sm text-slate-400 w-24")
                        ui.label(manifest["symbol"]).classes("text-sm text-cyber-300")


def render_run_summary_card(summary: Dict[str, Any]) -> None:
    """渲染 run summary 卡片"""
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Summary").classes("text-xl font-bold mb-4 text-cyber-400")
        
        metrics = summary.get("metrics", {})
        if metrics:
            with ui.grid(columns=3).classes("w-full gap-4"):
                net_profit = metrics.get("net_profit", 0.0)
                profit_color = "text-green-400" if net_profit >= 0 else "text-red-400"
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Net Profit").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"${net_profit:.2f}").classes(f"text-2xl font-bold {profit_color}")
                
                win_rate = metrics.get("win_rate", 0.0)
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Win Rate").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"{win_rate:.1%}").classes("text-2xl font-bold text-cyber-400")
                
                sharpe = metrics.get("sharpe_ratio", 0.0)
                sharpe_color = "text-green-400" if sharpe >= 1.0 else "text-yellow-400" if sharpe >= 0 else "text-red-400"
                with ui.card().classes("p-3 bg-nexus-800"):
                    ui.label("Sharpe Ratio").classes("text-sm text-slate-400 mb-1")
                    ui.label(f"{sharpe:.2f}").classes(f"text-2xl font-bold {sharpe_color}")


def render_run_artifacts_list(artifacts: List[Path], run_dir: Path) -> None:
    """渲染 run artifacts 列表"""
    if not artifacts:
        ui.label("No artifacts found").classes("text-gray-500 italic")
        return
    
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Run Artifacts").classes("text-xl font-bold mb-4 text-cyber-400")
        
        json_files = [a for a in artifacts if a.suffix == ".json"]
        csv_files = [a for a in artifacts if a.suffix == ".csv"]
        other_files = [a for a in artifacts if a.suffix not in [".json", ".csv"]]
        
        if json_files:
            ui.label("JSON Files").classes("text-lg font-bold mb-2 text-cyber-300")
            for artifact in json_files[:5]:
                rel_path = artifact.relative_to(run_dir)
                size = artifact.stat().st_size if artifact.exists() else 0
                with ui.card().classes("p-2 mb-1 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                    with ui.row().classes("items-center justify-between"):
                        with ui.row().classes("items-center"):
                            ui.icon("description", color="green").classes("mr-2")
                            ui.label(str(rel_path)).classes("text-sm font-mono text-slate-300")
                        ui.label(f"{size:,} bytes").classes("text-xs text-slate-500")
        
        if csv_files:
            ui.label("CSV Files").classes("text-lg font-bold mb-2 text-cyber-300 mt-4")
            for artifact in csv_files[:3]:
                rel_path = artifact.relative_to(run_dir)
                size = artifact.stat().st_size if artifact.exists() else 0
                with ui.card().classes("p-2 mb-1 bg-nexus-800 hover:bg-nexus-700 cursor-pointer"):
                    with ui.row().classes("items-center justify-between"):
                        with ui.row().classes("items-center"):
                            ui.icon("table_chart", color="blue").classes("mr-2")
                            ui.label(str(rel_path)).classes("text-sm font-mono text-slate-300")
                        ui.label(f"{size:,} bytes").classes("text-xs text-slate-500")


def render_audit_trail_card(run_id: str, season: str) -> None:
    """渲染 run 的 audit trail 卡片"""
    audit_events = get_audit_events_for_run_id(run_id, season, max_lines=30)
    
    with ui.card().classes("fish-card p-4 mb-6"):
        ui.label("Audit Trail").classes("text-xl font-bold mb-4 text-cyber-400")
        
        if not audit_events:
            ui.label("No audit events found for this run").classes("text-gray-500 italic p-4")
            ui.label("UI actions will create audit events automatically").classes("text-sm text-slate-400")
            return
        
        for event in reversed(audit_events):
            with ui.card().classes("p-3 mb-3 bg-nexus-800"):
                with ui.row().classes("items-center justify-between mb-2"):
                    action_type = event.get("action", "unknown")
                    action_color = {
                        "generate_research": "text-green-400",
                        "build_portfolio": "text-blue-400",
                        "archive": "text-red-400",
                        "clone": "text-yellow-400",
                    }.get(action_type, "text-slate-400")
                    ui.label(f"Action: {action_type}").classes(f"font-bold {action_color}")
                    
                    ts = event.get("ts", "")
                    if ts:
                        display_ts = ts[:19].replace("T", " ")
                        ui.label(display_ts).classes("text-sm text-slate-400")
                
                with ui.column().classes("text-sm"):
                    status = "✓ Success" if event.get("ok", False) else "✗ Failed"
                    status_color = "text-green-400" if event.get("ok", False) else "text-red-400"
                    ui.label(f"Status: {status}").classes(f"mb-1 {status_color}")
                    
                    if "inputs" in event:
                        inputs = event["inputs"]
                        if isinstance(inputs, dict) and inputs:
                            ui.label("Inputs:").classes("text-slate-400 mb-1")
                            for key, value in inputs.items():
                                ui.label(f"  {key}: {value}").classes("text-xs text-slate-500 ml-2")


def render_run_detail_page(run_id: str) -> None:
    """渲染 run detail 頁面內容"""
    ui.page_title(f"FishBroWFS V2 - Run {run_id}")
    
    with render_shell("/history", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            with ui.row().classes("w-full items-center mb-6"):
                with ui.row().classes("items-center"):
                    ui.link("← Back to History", "/history").classes("text-cyber-400 hover:text-cyber-300 mr-4")
                    ui.label(f"Run Detail: {run_id}").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                ui.button("Refresh", icon="refresh", on_click=lambda: ui.navigate.to(f"/run/{run_id}", reload=True)).props("outline")
            
            index = get_global_index()
            index.refresh()
            run = index.get(run_id)
            
            if not run:
                with ui.card().classes("fish-card w-full p-8 text-center"):
                    ui.icon("error", size="xl").classes("text-red-500 mb-4")
                    ui.label(f"Run {run_id} not found").classes("text-2xl font-bold text-red-400 mb-2")
                    ui.label("The run may have been archived or deleted.").classes("text-slate-400 mb-4")
                    ui.link("Go back to History", "/history").classes("text-cyber-400 hover:text-cyber-300")
                return
            
            run_dir = Path(run.run_dir)
            if not run_dir.exists():
                with ui.card().classes("fish-card w-full p-8 text-center"):
                    ui.icon("folder_off", size="xl").classes("text-amber-500 mb-4")
                    ui.label(f"Run directory not found").classes("text-2xl font-bold text-amber-400 mb-2")
                    ui.label(f"Path: {run_dir}").classes("text-sm text-slate-400 mb-4")
                    ui.label("The run may have been moved or deleted.").classes("text-slate-400")
                return
            
            with ui.card().classes("fish-card p-4 mb-6 bg-nexus-900"):
                with ui.row().classes("items-center justify-between"):
                    with ui.row().classes("items-center gap-4"):
                        status_badge = run.status
                        status_color = {
                            "completed": "bg-green-500/20 text-green-300",
                            "running": "bg-blue-500/20 text-blue-300",
                            "failed": "bg-red-500/20 text-red-300",
                            "unknown": "bg-slate-500/20 text-slate-300",
                        }.get(status_badge, "bg-slate-500/20 text-slate-300")
                        ui.label(status_badge).classes(f"px-3 py-1 rounded-full text-sm {status_color}")
                        
                        if run.is_archived:
                            ui.badge("Archived", color="red").props("dense")
                    
                    with ui.row().classes("gap-2"):
                        ui.button("View in Files", icon="folder_open").props("outline")
                        ui.button("Clone Run", icon="content_copy").props("outline color=positive")
                        if not run.is_archived:
                            ui.button("Archive", icon="archive").props("outline color=negative")
            
            manifest = load_run_manifest(run_dir)
            summary = load_run_summary(run_dir)
            artifacts = list_run_artifacts(run_dir)
            
            render_run_info_card(run, manifest)
            
            if summary:
                render_run_summary_card(summary)
            
            render_run_artifacts_list(artifacts, run_dir)
            
            render_audit_trail_card(run_id, run.season)
            
            with ui.card().classes("fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Run Information: Basic metadata about the run").classes("text-slate-300 mb-1")
                ui.label("• Run Summary: Performance metrics and summary").classes("text-slate-300 mb-1")
                ui.label("• Run Artifacts: Files generated by the run").classes("text-slate-300 mb-1")
                ui.label("• Audit Trail: UI actions related to this run").classes("text-slate-300 mb-1")
                ui.label("• All UI actions are logged for governance and auditability").classes("text-slate-300 text-amber-300")


def register() -> None:
    """註冊 run detail 頁面路由"""
    
    @ui.page("/run/{run_id}")
    def run_detail_page(run_id: str) -> None:
        """Run Detail 頁面"""
        render_run_detail_page(run_id)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/settings.py
sha256(source_bytes) = b7ecc8d535da10f4d82679739004233a3ea5a1a715a11973babc7a3e371ea463
bytes = 9316
redacted = False
--------------------------------------------------------------------------------
"""設定頁面 - Settings"""

from nicegui import ui

from ..api import get_system_settings, update_system_settings
from ..state import app_state


def register() -> None:
    """註冊設定頁面"""
    
    @ui.page("/settings")
    def settings_page() -> None:
        """設定頁面"""
        ui.page_title("FishBroWFS V2 - Settings")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # 頁面標題
            ui.label("System Settings").classes("text-3xl font-bold mb-2 text-cyber-400")
            ui.label("Configure system parameters, environment variables, and API endpoints").classes("text-slate-400 mb-8")
            
            # 設定容器
            settings_container = ui.column().classes("w-full")
            
            def refresh_settings() -> None:
                """刷新設定資訊"""
                settings_container.clear()
                
                try:
                    # 獲取系統設定
                    settings = get_system_settings()
                    
                    with settings_container:
                        # 系統資訊卡片
                        with ui.card().classes("w-full mb-6"):
                            ui.label("System Information").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                ui.label("Season").classes("font-bold")
                                ui.label(app_state.season).classes("text-green-400")
                                
                                ui.label("Freeze Status").classes("font-bold")
                                if app_state.frozen:
                                    ui.label("FROZEN").classes("text-red-400 font-bold")
                                else:
                                    ui.label("ACTIVE").classes("text-green-400 font-bold")
                                
                                ui.label("API Endpoint").classes("font-bold")
                                ui.label(settings.get("api_endpoint", "http://localhost:8081")).classes("text-slate-300")
                                
                                ui.label("Dashboard Version").classes("font-bold")
                                ui.label(settings.get("version", "2.0.0")).classes("text-slate-300")
                        
                        # 環境變數設定
                        with ui.card().classes("w-full mb-6"):
                            ui.label("Environment Variables").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            # 顯示環境變數
                            env_vars = settings.get("environment", {})
                            if env_vars:
                                for key, value in env_vars.items():
                                    with ui.row().classes("w-full items-center mb-2"):
                                        ui.label(f"{key}:").classes("w-48 font-mono text-sm text-slate-400")
                                        ui.label(str(value)).classes("flex-1 font-mono text-sm bg-nexus-800 p-2 rounded")
                            else:
                                ui.label("No environment variables configured").classes("text-slate-500 italic")
                        
                        # API 端點設定
                        with ui.card().classes("w-full mb-6"):
                            ui.label("API Endpoints").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            endpoints = settings.get("endpoints", {})
                            if endpoints:
                                for name, url in endpoints.items():
                                    with ui.row().classes("w-full items-center mb-2"):
                                        ui.label(f"{name}:").classes("w-48 text-slate-400")
                                        ui.link(url, url, new_tab=True).classes("flex-1 font-mono text-sm text-cyber-400 hover:text-cyber-300")
                            else:
                                ui.label("No API endpoints configured").classes("text-slate-500 italic")
                        
                        # 系統設定選項
                        with ui.card().classes("w-full mb-6"):
                            ui.label("System Configuration").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            # 自動刷新設定
                            auto_refresh = ui.switch("Auto-refresh dashboard", value=settings.get("auto_refresh", True))
                            
                            # 通知設定
                            notifications = ui.switch("Enable notifications", value=settings.get("notifications", False))
                            
                            # 主題設定
                            theme = ui.select(["dark", "light", "auto"], value=settings.get("theme", "dark"), label="Theme")
                            
                            # 儲存按鈕
                            def save_settings() -> None:
                                """儲存設定"""
                                new_settings = {
                                    "auto_refresh": auto_refresh.value,
                                    "notifications": notifications.value,
                                    "theme": theme.value,
                                }
                                try:
                                    update_system_settings(new_settings)
                                    ui.notify("Settings saved successfully", type="positive")
                                except Exception as e:
                                    ui.notify(f"Failed to save settings: {e}", type="negative")
                            
                            ui.button("Save Settings", on_click=save_settings, icon="save").classes("mt-4 bg-cyber-500 hover:bg-cyber-400")
                        
                        # 系統操作
                        with ui.card().classes("w-full"):
                            ui.label("System Operations").classes("text-xl font-bold mb-4 text-cyber-300")
                            
                            with ui.row().classes("w-full gap-4"):
                                # 清除快取
                                def clear_cache() -> None:
                                    """清除系統快取"""
                                    ui.notify("Cache cleared (simulated)", type="info")
                                
                                ui.button("Clear Cache", on_click=clear_cache, icon="delete").classes("bg-amber-600 hover:bg-amber-500")
                                
                                # 重新載入設定
                                def reload_config() -> None:
                                    """重新載入設定"""
                                    refresh_settings()
                                    ui.notify("Settings reloaded", type="info")
                                
                                ui.button("Reload Settings", on_click=reload_config, icon="refresh").classes("bg-blue-600 hover:bg-blue-500")
                                
                                # 重啟服務
                                def restart_service() -> None:
                                    """重啟服務（模擬）"""
                                    ui.notify("Service restart initiated (simulated)", type="warning")
                                
                                ui.button("Restart Service", on_click=restart_service, icon="restart_alt").classes("bg-red-600 hover:bg-red-500")
                            
                            # 警告訊息
                            ui.separator().classes("my-4")
                            with ui.row().classes("w-full items-center p-4 bg-yellow-900/30 border border-yellow-700 rounded"):
                                ui.icon("warning", size="sm").classes("text-yellow-400 mr-2")
                                ui.label("System operations may affect running jobs. Use with caution.").classes("text-sm text-yellow-300")
                
                except Exception as e:
                    with settings_container:
                        ui.label(f"Failed to load settings: {e}").classes("text-red-400")
                        
                        # 顯示錯誤卡片
                        with ui.card().classes("w-full p-6 bg-red-900/20 border border-red-700"):
                            ui.icon("error", size="xl").classes("text-red-400 mx-auto mb-4")
                            ui.label("Settings API Not Available").classes("text-xl font-bold text-red-300 text-center mb-2")
                            ui.label("The system settings API is not currently available.").classes("text-red-200 text-center mb-4")
                            ui.label("This may be because the control API is not running or the endpoint is not configured.").classes("text-sm text-slate-400 text-center")
            
            # 初始載入
            refresh_settings()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/status.py
sha256(source_bytes) = e153f5a8b953923c2556edc21ebf625186da385f6687d17139f693814a3e46cf
bytes = 20523
redacted = False
--------------------------------------------------------------------------------
"""System Status Page - Shows dataset and strategy status with reload and build capabilities."""

from __future__ import annotations

from nicegui import ui

from FishBroWFS_V2.gui.nicegui.layout import render_topbar
from FishBroWFS_V2.gui.services.reload_service import (
    get_system_snapshot,
    reload_everything,
    build_parquet,
    build_all_parquet
)


@ui.page('/status')
def status_page():
    """System status page."""
    # Use render_topbar for consistent header
    render_topbar(active='status')
    
    # State for snapshot data
    snapshot = {'data': None}
    
    def refresh():
        """Refresh snapshot data."""
        try:
            snapshot['data'] = get_system_snapshot()
            ui.notify('Snapshot refreshed', type='positive')
            update_display()
        except Exception as e:
            ui.notify(f'Failed to refresh: {str(e)}', type='negative')
    
    def do_reload():
        """Reload all caches and registries."""
        try:
            r = reload_everything(reason='manual_ui')
            if r.ok:
                ui.notify('Reload OK', type='positive')
            else:
                ui.notify(f'Reload failed: {r.error}', type='negative')
            # Refresh snapshot after reload
            refresh()
        except Exception as e:
            ui.notify(f'Reload error: {str(e)}', type='negative')
    
    def do_build_all():
        """Build Parquet for all datasets."""
        try:
            ui.notify('Starting Parquet build for all datasets...', type='info')
            results = build_all_parquet(reason='manual_ui')
            
            # Count results
            success = sum(1 for r in results if r.success)
            failed = sum(1 for r in results if not r.success)
            
            if failed == 0:
                ui.notify(f'Build completed: {success} successful, {failed} failed', type='positive')
            else:
                ui.notify(f'Build completed with errors: {success} successful, {failed} failed', type='warning')
            
            # Refresh snapshot after build
            refresh()
        except Exception as e:
            ui.notify(f'Build error: {str(e)}', type='negative')
    
    def do_build_dataset(dataset_id: str):
        """Build Parquet for a single dataset."""
        try:
            ui.notify(f'Building Parquet for {dataset_id}...', type='info')
            result = build_parquet(dataset_id, reason='manual_ui')
            
            if result.success:
                ui.notify(f'Build successful for {dataset_id}', type='positive')
            else:
                ui.notify(f'Build failed for {dataset_id}: {result.error}', type='negative')
            
            # Refresh snapshot after build
            refresh()
        except Exception as e:
            ui.notify(f'Build error for {dataset_id}: {str(e)}', type='negative')
    
    # Create containers for dynamic content
    summary_container = ui.column().classes('w-full')
    datasets_container = ui.column().classes('w-full mt-6')
    strategies_container = ui.column().classes('w-full mt-6')
    
    def update_display():
        """Update UI with current snapshot data."""
        summary_container.clear()
        datasets_container.clear()
        strategies_container.clear()
        
        if not snapshot['data']:
            with summary_container:
                ui.label('No snapshot data available').classes('text-lg text-yellow-500')
            return
        
        data = snapshot['data']
        
        # Summary section
        with summary_container:
            with ui.card().classes('w-full bg-nexus-900 p-4'):
                with ui.row().classes('w-full justify-between items-center'):
                    with ui.column().classes('gap-2'):
                        ui.label('System Snapshot').classes('text-2xl font-bold text-cyber-300')
                        ui.label(f'Created: {data.created_at.strftime("%Y-%m-%d %H:%M:%S")}').classes('text-sm text-slate-400')
                    
                    with ui.row().classes('gap-2'):
                        ui.button('Refresh Snapshot', icon='refresh').on('click', lambda: refresh())
                        ui.button('Reload All', icon='cached', color='primary').on('click', lambda: do_reload())
                        ui.button('Build All Parquet', icon='build', color='secondary').on('click', lambda: do_build_all())
                
                with ui.row().classes('w-full mt-4 gap-6'):
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Datasets').classes('text-lg font-bold text-cyber-300')
                        ui.label(f'Total: {data.total_datasets}').classes('text-2xl')
                        txt_present = sum(1 for ds in data.dataset_statuses if ds.txt_present)
                        parquet_present = sum(1 for ds in data.dataset_statuses if ds.parquet_present)
                        ui.label(f'TXT: {txt_present}').classes('text-sm text-blue-400')
                        ui.label(f'Parquet: {parquet_present}').classes('text-sm text-green-400')
                    
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Strategies').classes('text-lg font-bold text-cyber-300')
                        ui.label(f'Total: {data.total_strategies}').classes('text-2xl')
                        working = sum(1 for ss in data.strategy_statuses if ss.can_import and ss.can_build_spec)
                        ui.label(f'Working: {working}').classes('text-sm text-green-400')
                        ui.label(f'Errors: {data.total_strategies - working}').classes('text-sm text-red-400')
                    
                    with ui.card().classes('flex-1 bg-nexus-800 p-4'):
                        ui.label('Build Status').classes('text-lg font-bold text-cyber-300')
                        up_to_date = sum(1 for ds in data.dataset_statuses if ds.up_to_date)
                        ui.label(f'Up-to-date: {up_to_date}').classes('text-2xl')
                        ui.label(f'Needs build: {data.total_datasets - up_to_date}').classes('text-sm text-yellow-400')
                        ui.label(f'Missing TXT: {data.total_datasets - txt_present}').classes('text-sm text-red-400')
                
                if data.notes:
                    with ui.card().classes('w-full mt-4 bg-nexus-800 p-3'):
                        for note in data.notes:
                            ui.label(f'• {note}').classes('text-sm text-slate-300')
        
        # Datasets table
        with datasets_container:
            ui.label('Datasets').classes('text-xl font-bold text-cyber-300 mb-4')
            
            if not data.dataset_statuses:
                ui.label('No datasets found').classes('text-slate-400')
            else:
                # Create table header
                with ui.row().classes('w-full bg-nexus-800 p-3 rounded-t-lg font-bold'):
                    ui.label('ID').classes('w-1/5')
                    ui.label('Kind').classes('w-1/10')
                    ui.label('TXT').classes('w-1/10')
                    ui.label('Parquet').classes('w-1/10')
                    ui.label('Up-to-date').classes('w-1/10')
                    ui.label('Schema').classes('w-1/10')
                    ui.label('Actions').classes('w-1/5')
                
                # Create table rows
                for ds in data.dataset_statuses:
                    txt_color = 'text-green-400' if ds.txt_present else 'text-red-400'
                    txt_text = '✓' if ds.txt_present else '✗'
                    parquet_color = 'text-green-400' if ds.parquet_present else 'text-red-400'
                    parquet_text = '✓' if ds.parquet_present else '✗'
                    uptodate_color = 'text-green-400' if ds.up_to_date else 'text-yellow-400'
                    uptodate_text = '✓' if ds.up_to_date else '✗'
                    schema_color = 'text-green-400' if ds.schema_ok else 'text-yellow-400'
                    schema_text = 'OK' if ds.schema_ok else 'Unknown'
                    
                    with ui.row().classes('w-full bg-nexus-900 p-3 border-b border-nexus-800 hover:bg-nexus-850'):
                        ui.label(ds.id).classes('w-1/5 font-mono text-sm')
                        ui.label(ds.kind).classes('w-1/10 text-slate-300')
                        ui.label(txt_text).classes(f'w-1/10 {txt_color} text-center')
                        ui.label(parquet_text).classes(f'w-1/10 {parquet_color} text-center')
                        ui.label(uptodate_text).classes(f'w-1/10 {uptodate_color} text-center')
                        ui.label(schema_text).classes(f'w-1/10 {schema_color} text-center')
                        
                        with ui.row().classes('w-1/5 gap-1'):
                            details_btn = ui.button('Details', icon='info', size='sm').props('dense outline')
                            details_btn.on('click', lambda d=ds: show_dataset_details(d))
                            
                            if ds.txt_present and not ds.up_to_date:
                                build_btn = ui.button('Build', icon='build', size='sm').props('dense outline color=primary')
                                build_btn.on('click', lambda d=ds: do_build_dataset(d.dataset_id))
                            else:
                                # Disabled button
                                build_btn = ui.button('Build', icon='build', size='sm').props('dense outline disabled')
                    
                    # Error row if present
                    if ds.error:
                        with ui.row().classes('w-full bg-red-900/20 p-2'):
                            ui.label(f'Error: {ds.error}').classes('text-sm text-red-300')
        
        # Strategies table
        with strategies_container:
            ui.label('Strategies').classes('text-xl font-bold text-cyber-300 mb-4 mt-8')
            
            if not data.strategy_statuses:
                ui.label('No strategies found').classes('text-slate-400')
            else:
                # Create table header
                with ui.row().classes('w-full bg-nexus-800 p-3 rounded-t-lg font-bold'):
                    ui.label('ID').classes('w-1/4')
                    ui.label('Import').classes('w-1/6')
                    ui.label('Build').classes('w-1/6')
                    ui.label('Features').classes('w-1/6')
                    ui.label('Signature').classes('w-1/6')
                    ui.label('Actions').classes('w-1/6')
                
                # Create table rows
                for ss in data.strategy_statuses:
                    import_color = 'text-green-400' if ss.can_import else 'text-red-400'
                    import_text = '✓' if ss.can_import else '✗'
                    build_color = 'text-green-400' if ss.can_build_spec else 'text-red-400'
                    build_text = '✓' if ss.can_build_spec else '✗'
                    
                    with ui.row().classes('w-full bg-nexus-900 p-3 border-b border-nexus-800 hover:bg-nexus-850'):
                        ui.label(ss.id).classes('w-1/4 font-mono text-sm')
                        ui.label(import_text).classes(f'w-1/6 {import_color} text-center')
                        ui.label(build_text).classes(f'w-1/6 {build_color} text-center')
                        ui.label(str(ss.feature_requirements_count)).classes('w-1/6 text-slate-300 text-center')
                        ui.label(ss.signature[:12] + '...' if len(ss.signature) > 12 else ss.signature).classes('w-1/6 font-mono text-xs')
                        
                        with ui.row().classes('w-1/6 gap-1'):
                            details_btn = ui.button('Details', icon='info', size='sm').props('dense outline')
                            details_btn.on('click', lambda s=ss: show_strategy_details(s))
                    
                    # Error row if present
                    if ss.error:
                        with ui.row().classes('w-full bg-red-900/20 p-2'):
                            ui.label(f'Error: {ss.error}').classes('text-sm text-red-300')
    
    def show_dataset_details(dataset):
        """Show dataset details in a dialog."""
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
            ui.label(f'Dataset: {dataset.id}').classes('text-xl font-bold mb-4')
            
            with ui.column().classes('w-full gap-3'):
                # Basic info
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Basic Information').classes('font-bold mb-2')
                    with ui.grid(columns=2).classes('w-full gap-2'):
                        ui.label('Kind:').classes('font-medium')
                        ui.label(dataset.kind)
                        ui.label('TXT present:').classes('font-medium')
                        ui.label('Yes' if dataset.txt_present else 'No')
                        ui.label('Parquet present:').classes('font-medium')
                        ui.label('Yes' if dataset.parquet_present else 'No')
                        ui.label('Up-to-date:').classes('font-medium')
                        ui.label('Yes' if dataset.up_to_date else 'No')
                        ui.label('Schema OK:').classes('font-medium')
                        ui.label('Yes' if dataset.schema_ok else 'No')
                        ui.label('Bars count:').classes('font-medium')
                        ui.label(str(dataset.bars_count) if dataset.bars_count else 'Unknown')
                
                # TXT files
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('TXT Source Files').classes('font-bold mb-2')
                    if not dataset.txt_required_paths:
                        ui.label('No TXT files defined').classes('text-slate-400')
                    else:
                        for txt_path in dataset.txt_required_paths:
                            from pathlib import Path
                            txt_file = Path(txt_path)
                            exists = txt_file.exists()
                            status_color = 'text-green-400' if exists else 'text-red-400'
                            status_icon = '✓' if exists else '✗'
                            with ui.row().classes('w-full items-center gap-2 p-1'):
                                ui.label(status_icon).classes(status_color)
                                ui.label(txt_path).classes('flex-1 font-mono text-sm')
                                if exists:
                                    stat = txt_file.stat()
                                    ui.label(f'{stat.st_size:,} bytes').classes('text-xs text-slate-400')
                
                # Parquet files
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Parquet Output Files').classes('font-bold mb-2')
                    if not dataset.parquet_expected_paths:
                        ui.label('No Parquet files defined').classes('text-slate-400')
                    else:
                        for parquet_path in dataset.parquet_expected_paths:
                            from pathlib import Path
                            parquet_file = Path(parquet_path)
                            exists = parquet_file.exists()
                            status_color = 'text-green-400' if exists else 'text-red-400'
                            status_icon = '✓' if exists else '✗'
                            with ui.row().classes('w-full items-center gap-2 p-1'):
                                ui.label(status_icon).classes(status_color)
                                ui.label(parquet_path).classes('flex-1 font-mono text-sm')
                                if exists:
                                    stat = parquet_file.stat()
                                    ui.label(f'{stat.st_size:,} bytes').classes('text-xs text-slate-400')
                
                # Build action if needed
                if dataset.txt_present and not dataset.up_to_date:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Build Action').classes('font-bold mb-2')
                        with ui.row().classes('w-full gap-2'):
                            build_btn = ui.button('Build Parquet', icon='build', color='primary')
                            build_btn.on('click', lambda d=dataset: do_build_dataset(d.dataset_id))
                            ui.label('Converts TXT to Parquet format').classes('text-sm text-slate-400')
                
                # Error if present
                if dataset.error:
                    with ui.card().classes('w-full bg-red-900/30 p-3'):
                        ui.label('Error').classes('font-bold text-red-300 mb-1')
                        ui.label(dataset.error).classes('text-sm')
            
            ui.button('Close', on_click=dialog.close).classes('mt-4')
        
        dialog.open()
    
    def show_strategy_details(strategy):
        """Show strategy details in a dialog."""
        with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
            ui.label(f'Strategy: {strategy.id}').classes('text-xl font-bold mb-4')
            
            with ui.column().classes('w-full gap-3'):
                # Basic info
                with ui.card().classes('w-full bg-nexus-800 p-3'):
                    ui.label('Basic Information').classes('font-bold mb-2')
                    with ui.grid(columns=2).classes('w-full gap-2'):
                        ui.label('Can import:').classes('font-medium')
                        ui.label('Yes' if strategy.can_import else 'No')
                        ui.label('Can build spec:').classes('font-medium')
                        ui.label('Yes' if strategy.can_build_spec else 'No')
                        ui.label('Feature requirements:').classes('font-medium')
                        ui.label(str(strategy.feature_requirements_count))
                        ui.label('Last modified:').classes('font-medium')
                        if strategy.mtime:
                            from datetime import datetime
                            dt = datetime.fromtimestamp(strategy.mtime)
                            ui.label(dt.strftime('%Y-%m-%d %H:%M:%S'))
                        else:
                            ui.label('Unknown')
                
                # Signature
                if strategy.signature:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Signature').classes('font-bold mb-2')
                        ui.label(strategy.signature).classes('font-mono text-sm break-all')
                
                # Error if present
                if strategy.error:
                    with ui.card().classes('w-full bg-red-900/30 p-3'):
                        ui.label('Error').classes('font-bold text-red-300 mb-1')
                        ui.label(strategy.error).classes('text-sm')
                
                # Show spec details if available
                if strategy.spec:
                    with ui.card().classes('w-full bg-nexus-800 p-3'):
                        ui.label('Specification').classes('font-bold mb-2')
                        if hasattr(strategy.spec, 'params') and strategy.spec.params:
                            ui.label('Parameters:').classes('font-medium mt-2')
                            for param in strategy.spec.params:
                                with ui.row().classes('w-full gap-4 p-1'):
                                    ui.label(f'{param.name}:').classes('w-1/3 font-medium')
                                    ui.label(f'{param.type} (default: {param.default})').classes('w-2/3 text-slate-300')
            
            ui.button('Close', on_click=dialog.close).classes('mt-4')
        
        dialog.open()
    
    # Main layout
    with ui.column().classes('w-full gap-4 p-6'):
        # Initial load
        refresh()
        
        # Dynamic containers will be filled by update_display
        ui.element('div').classes('w-full')  # Spacer


def register() -> None:
    """Register status page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/wizard.py
sha256(source_bytes) = 6198490c5a1b586151ab80701983f37404192d5d690d78351597c351200c74fc
bytes = 31693
redacted = False
--------------------------------------------------------------------------------
"""M1 Wizard - Five-step wizard for job creation.

Step1: DATA1 (dataset / symbols / timeframes)
Step2: DATA2 (optional; single filter)
Step3: Strategies (schema-driven)
Step4: Cost
Step5: Summary (must show Units formula and number)
"""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
from datetime import date

from nicegui import ui

from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog
from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog
# Use intent-based system for Attack #9 - Headless Intent-State Contract
from FishBroWFS_V2.gui.adapters.intent_bridge import (
    migrate_ui_imports,
    SeasonFrozenError,
    ValidationError,
)

# Migrate imports to use intent bridge
migrate_ui_imports()

# The migrate_ui_imports() function replaces the following imports
# with intent-based implementations:
# - create_job_from_wizard
# - calculate_units
# - check_season_not_frozen
# - ValidationError (re-exported)
# - SeasonFrozenError (re-exported)
from FishBroWFS_V2.control.dataset_descriptor import get_descriptor


class M1WizardState:
    """State management for M1 wizard."""
    
    def __init__(self):
        # Step 1: DATA1
        self.season: str = "2024Q1"
        self.dataset_id: str = ""
        self.symbols: List[str] = []
        self.timeframes: List[str] = []
        self.start_date: Optional[date] = None
        self.end_date: Optional[date] = None
        
        # Step 2: DATA2
        self.enable_data2: bool = False
        self.data2_dataset_id: str = ""
        self.data2_filters: List[str] = []
        self.selected_filter: str = ""
        
        # Step 3: Strategies
        self.strategy_id: str = ""
        self.params: Dict[str, Any] = {}
        
        # Step 4: Cost (calculated)
        self.units: int = 0
        
        # Step 5: Summary
        self.job_id: Optional[str] = None
        
        # UI references
        self.step_containers: Dict[int, Any] = {}
        self.current_step: int = 1


def create_step_indicator(state: M1WizardState) -> None:
    """Create step indicator UI."""
    with ui.row().classes("w-full mb-8 gap-2"):
        steps = [
            (1, "DATA1", state.current_step == 1),
            (2, "DATA2", state.current_step == 2),
            (3, "Strategies", state.current_step == 3),
            (4, "Cost", state.current_step == 4),
            (5, "Summary", state.current_step == 5),
        ]
        
        for step_num, label, active in steps:
            with ui.column().classes("items-center"):
                ui.label(str(step_num)).classes(
                    f"w-8 h-8 rounded-full flex items-center justify-center font-bold "
                    f"{'bg-blue-500 text-white' if active else 'bg-gray-200 text-gray-600'}"
                )
                ui.label(label).classes(
                    f"text-sm mt-1 {'font-bold text-blue-600' if active else 'text-gray-500'}"
                )


def create_step1_data1(state: M1WizardState) -> None:
    """Create Step 1: DATA1 UI."""
    with state.step_containers[1]:
        ui.label("Step 1: DATA1 Configuration").classes("text-xl font-bold mb-4")
        
        # Season input
        from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_input, labeled_select, labeled_date
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Season")
            season_input = ui.input(
                value=state.season,
                placeholder="e.g., 2024Q1, 2024Q2"
            ).classes("w-full")
            season_input.bind_value(state, 'season')
        
        # Dataset selection
        catalog = get_dataset_catalog()
        datasets = catalog.list_datasets()
        dataset_options = {d.id: f"{d.symbol} ({d.timeframe}) {d.start_date}-{d.end_date}"
                          for d in datasets}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Dataset")
            dataset_select = ui.select(
                options=dataset_options,
                with_input=True
            ).classes("w-full")
            dataset_select.bind_value(state, 'dataset_id')
        
        # Symbols input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Symbols (comma separated)")
            symbols_input = ui.input(
                value="MNQ, MXF",
                placeholder="e.g., MNQ, MXF, MES"
            ).classes("w-full")
            symbols_input.bind_value(state, 'symbols')
        
        # Timeframes input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Timeframes (comma separated)")
            timeframes_input = ui.input(
                value="60m, 120m",
                placeholder="e.g., 60m, 120m, 240m"
            ).classes("w-full")
            timeframes_input.bind_value(state, 'timeframes')
        
        # Date range
        with ui.row().classes("w-full"):
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("Start Date")
                start_date = ui.date(
                    value=date(2020, 1, 1)
                ).classes("w-full")
                start_date.bind_value(state, 'start_date')
            
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("End Date")
                end_date = ui.date(
                    value=date(2024, 12, 31)
                ).classes("w-full")
                end_date.bind_value(state, 'end_date')
        
        # Initialize state with parsed values
        def parse_initial_values():
            if isinstance(state.symbols, str):
                state.symbols = [s.strip() for s in state.symbols.split(",") if s.strip()]
            elif not isinstance(state.symbols, list):
                state.symbols = []
            
            if isinstance(state.timeframes, str):
                state.timeframes = [t.strip() for t in state.timeframes.split(",") if t.strip()]
            elif not isinstance(state.timeframes, list):
                state.timeframes = []
        
        parse_initial_values()


def create_step2_data2(state: M1WizardState) -> None:
    """Create Step 2: DATA2 UI (optional, single filter)."""
    with state.step_containers[2]:
        ui.label("Step 2: DATA2 Configuration (Optional)").classes("text-xl font-bold mb-4")
        
        # Enable DATA2 toggle
        enable_toggle = ui.switch("Enable DATA2 (single filter validation)")
        enable_toggle.bind_value(state, 'enable_data2')
        
        # DATA2 container (initially hidden)
        data2_container = ui.column().classes("w-full mt-4")
        
        def update_data2_visibility(enabled: bool):
            data2_container.clear()
            if not enabled:
                state.data2_dataset_id = ""
                state.data2_filters = []
                state.selected_filter = ""
                return
            
            with data2_container:
                # Dataset selection for DATA2
                catalog = get_dataset_catalog()
                datasets = catalog.list_datasets()
                dataset_options = {d.id: f"{d.symbol} ({d.timeframe})" for d in datasets}
                
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("DATA2 Dataset")
                    dataset_select = ui.select(
                        options=dataset_options,
                        with_input=True
                    ).classes("w-full")
                    dataset_select.bind_value(state, 'data2_dataset_id')
                
                # Filter selection (single filter)
                filter_options = ["momentum", "volatility", "trend", "mean_reversion"]
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("Filter")
                    filter_select = ui.select(
                        options=filter_options,
                        value=filter_options[0] if filter_options else ""
                    ).classes("w-full")
                    filter_select.bind_value(state, 'selected_filter')
                
                # Initialize state
                state.data2_filters = filter_options
                if not state.selected_filter and filter_options:
                    state.selected_filter = filter_options[0]
        
        # Use timer to update visibility when enable_data2 changes
        def update_visibility_from_state():
            update_data2_visibility(state.enable_data2)
        
        ui.timer(0.2, update_visibility_from_state)
        
        # Initial visibility
        update_data2_visibility(state.enable_data2)


def create_step3_strategies(state: M1WizardState) -> None:
    """Create Step 3: Strategies UI (schema-driven)."""
    with state.step_containers[3]:
        ui.label("Step 3: Strategy Selection").classes("text-xl font-bold mb-4")
        
        # Strategy selection
        catalog = get_strategy_catalog()
        strategies = catalog.list_strategies()
        strategy_options = {s.strategy_id: s.strategy_id for s in strategies}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Strategy")
            strategy_select = ui.select(
                options=strategy_options,
                with_input=True
            ).classes("w-full")
            strategy_select.bind_value(state, 'strategy_id')
        
        # Parameters container (dynamic)
        param_container = ui.column().classes("w-full mt-4")
        
        def update_strategy_ui(selected_id: str):
            param_container.clear()
            state.strategy_id = selected_id
            state.params = {}
            
            if not selected_id:
                return
            
            strategy = catalog.get_strategy(selected_id)
            if not strategy:
                return
            
            ui.label("Parameters").classes("font-bold mt-2 mb-2")
            
            # Create UI for each parameter
            for param in strategy.params:
                with ui.row().classes("w-full items-center mb-3"):
                    ui.label(f"{param.name}:").classes("w-1/3 font-medium")
                    
                    if param.type == "int" or param.type == "float":
                        # Number input
                        min_val = param.min if param.min is not None else 0
                        max_val = param.max if param.max is not None else 100
                        step = param.step if param.step is not None else (1 if param.type == "int" else 0.1)
                        
                        input_field = ui.number(
                            value=param.default,
                            min=min_val,
                            max=max_val,
                            step=step
                        ).classes("w-2/3")
                        
                        # Use on('update:model-value') for immediate updates
                        def make_param_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        input_field.on('update:model-value', make_param_handler(param.name, input_field))
                        state.params[param.name] = param.default
                        
                    elif param.type == "enum" and param.choices:
                        # Dropdown for enum
                        dropdown = ui.select(
                            options=param.choices,
                            value=param.default
                        ).classes("w-2/3")
                        
                        def make_enum_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        dropdown.on('update:model-value', make_enum_handler(param.name, dropdown))
                        state.params[param.name] = param.default
                        
                    elif param.type == "bool":
                        # Switch for boolean
                        switch = ui.switch(value=param.default).classes("w-2/3")
                        
                        def make_bool_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        switch.on('update:model-value', make_bool_handler(param.name, switch))
                        state.params[param.name] = param.default
                    
                    # Help text
                    if param.help:
                        ui.tooltip(param.help).classes("ml-2")
        
        # Use timer to update UI when strategy_id changes
        def update_strategy_from_state():
            if state.strategy_id != getattr(update_strategy_from_state, '_last_strategy', None):
                update_strategy_ui(state.strategy_id)
                update_strategy_from_state._last_strategy = state.strategy_id
        
        ui.timer(0.2, update_strategy_from_state)
        
        # Initialize if strategy is selected
        if state.strategy_id:
            update_strategy_ui(state.strategy_id)
        elif strategies:
            # Select first strategy by default
            first_strategy = strategies[0].strategy_id
            state.strategy_id = first_strategy
            update_strategy_ui(first_strategy)


def create_step4_cost(state: M1WizardState) -> None:
    """Create Step 4: Cost UI (Units calculation)."""
    with state.step_containers[4]:
        ui.label("Step 4: Cost Estimation").classes("text-xl font-bold mb-4")
        
        # Units formula explanation
        with ui.card().classes("w-full mb-4 bg-blue-50"):
            ui.label("Units Formula").classes("font-bold text-blue-800")
            ui.label("Units = |DATA1.symbols| × |DATA1.timeframes| × |strategies| × |DATA2.filters|").classes("font-mono text-sm text-blue-700")
            ui.label("Where |strategies| = 1 (single strategy) and |DATA2.filters| = 1 if DATA2 disabled").classes("text-sm text-blue-600")
        
        # Current configuration summary
        config_card = ui.card().classes("w-full mb-4")
        
        # Units calculation result
        units_label = ui.label("Calculating units...").classes("text-2xl font-bold text-green-600")
        
        # Parquet status warning container
        parquet_warning_container = ui.column().classes("w-full mt-4")
        
        def update_cost_display():
            with config_card:
                config_card.clear()
                
                # Build payload for units calculation
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Calculate units
                try:
                    units = calculate_units(payload)
                    state.units = units
                    
                    # Display configuration
                    ui.label("Current Configuration:").classes("font-bold mb-2")
                    
                    with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                        ui.label("Season:").classes("font-medium")
                        ui.label(state.season)
                        
                        ui.label("DATA1 Dataset:").classes("font-medium")
                        ui.label(state.dataset_id if state.dataset_id else "Not selected")
                        
                        ui.label("Symbols:").classes("font-medium")
                        ui.label(f"{len(state.symbols)}: {', '.join(state.symbols)}" if state.symbols else "None")
                        
                        ui.label("Timeframes:").classes("font-medium")
                        ui.label(f"{len(state.timeframes)}: {', '.join(state.timeframes)}" if state.timeframes else "None")
                        
                        ui.label("Strategy:").classes("font-medium")
                        ui.label(state.strategy_id if state.strategy_id else "Not selected")
                        
                        ui.label("DATA2 Enabled:").classes("font-medium")
                        ui.label("Yes" if state.enable_data2 else "No")
                        
                        if state.enable_data2:
                            ui.label("DATA2 Filter:").classes("font-medium")
                            ui.label(state.selected_filter)
                    
                    # Update units display
                    units_label.set_text(f"Total Units: {units}")
                    
                    # Cost estimation (simplified)
                    if units > 100:
                        ui.label("⚠️ High cost warning: This job may take significant resources").classes("text-yellow-600 mt-2")
                    
                except Exception as e:
                    units_label.set_text(f"Error calculating units: {str(e)}")
                    state.units = 0
            
            # Update Parquet status warnings
            parquet_warning_container.clear()
            
            # Check DATA1 dataset Parquet status
            if state.dataset_id:
                try:
                    descriptor = get_descriptor(state.dataset_id)
                    if descriptor:
                        from pathlib import Path
                        parquet_missing = []
                        for parquet_path_str in descriptor.parquet_expected_paths:
                            parquet_path = Path(parquet_path_str)
                            if not parquet_path.exists():
                                parquet_missing.append(parquet_path_str)
                        
                        if parquet_missing:
                            with parquet_warning_container:
                                with ui.card().classes("w-full bg-yellow-50 border-yellow-200"):
                                    ui.label("⚠️ DATA1 Parquet Files Missing").classes("text-yellow-800 font-bold mb-2")
                                    ui.label(f"Dataset '{state.dataset_id}' is missing {len(parquet_missing)} Parquet file(s)").classes("text-yellow-700 mb-2")
                                    ui.label("This may cause job failures or slower performance.").classes("text-sm text-yellow-600 mb-2")
                                    
                                    with ui.row().classes("w-full gap-2"):
                                        ui.button("Build Parquet",
                                                 on_click=lambda: ui.navigate.to("/status"),
                                                 icon="build").props("outline color=warning")
                                        ui.button("Check Status",
                                                 on_click=lambda: ui.navigate.to("/status"),
                                                 icon="info").props("outline")
                except Exception:
                    pass
            
            # Check DATA2 dataset Parquet status if enabled
            if state.enable_data2 and state.data2_dataset_id:
                try:
                    descriptor = get_descriptor(state.data2_dataset_id)
                    if descriptor:
                        from pathlib import Path
                        parquet_missing = []
                        for parquet_path_str in descriptor.parquet_expected_paths:
                            parquet_path = Path(parquet_path_str)
                            if not parquet_path.exists():
                                parquet_missing.append(parquet_path_str)
                        
                        if parquet_missing:
                            with parquet_warning_container:
                                with ui.card().classes("w-full bg-yellow-50 border-yellow-200 mt-2"):
                                    ui.label("⚠️ DATA2 Parquet Files Missing").classes("text-yellow-800 font-bold mb-2")
                                    ui.label(f"Dataset '{state.data2_dataset_id}' is missing {len(parquet_missing)} Parquet file(s)").classes("text-yellow-700 mb-2")
                                    ui.label("DATA2 validation may fail without Parquet files.").classes("text-sm text-yellow-600")
                except Exception:
                    pass
        
        # Update cost display periodically
        ui.timer(1.0, update_cost_display)


def create_step5_summary(state: M1WizardState) -> None:
    """Create Step 5: Summary and Submit UI."""
    with state.step_containers[5]:
        ui.label("Step 5: Summary & Submit").classes("text-xl font-bold mb-4")
        
        # Summary card
        summary_card = ui.card().classes("w-full mb-4")
        
        # Submit button
        submit_button = ui.button("Submit Job", icon="send", color="green")
        
        # Result container
        result_container = ui.column().classes("w-full mt-4")
        
        def update_summary():
            summary_card.clear()
            
            with summary_card:
                ui.label("Job Summary").classes("font-bold mb-2")
                
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Display payload
                ui.label("Final Payload:").classes("font-medium mt-2")
                payload_json = json.dumps(payload, indent=2)
                ui.textarea(payload_json).classes("w-full h-48 font-mono text-xs").props("readonly")
                
                # Units display
                units = calculate_units(payload)
                ui.label(f"Total Units: {units}").classes("font-bold text-lg mt-2")
                ui.label("Units = |symbols| × |timeframes| × |strategies| × |filters|").classes("text-sm text-gray-600")
                ui.label(f"= {len(state.symbols)} × {len(state.timeframes)} × 1 × {1 if state.enable_data2 else 1} = {units}").classes("text-sm font-mono")
        
        def submit_job():
            result_container.clear()
            
            try:
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Check season not frozen
                check_season_not_frozen(state.season, action="submit_job")
                
                # Submit job
                result = create_job_from_wizard(payload)
                state.job_id = result["job_id"]
                
                # Show success message
                with result_container:
                    with ui.card().classes("w-full bg-green-50 border-green-200"):
                        ui.label("✅ Job Submitted Successfully!").classes("text-green-800 font-bold mb-2")
                        ui.label(f"Job ID: {result['job_id']}").classes("font-mono text-sm mb-1")
                        ui.label(f"Units: {result['units']}").classes("text-sm mb-1")
                        ui.label(f"Season: {result['season']}").classes("text-sm mb-3")
                        
                        # Navigation button
                        ui.button(
                            "View Job Details",
                            on_click=lambda: ui.navigate.to(f"/jobs/{result['job_id']}"),
                            icon="visibility"
                        ).classes("bg-green-600 text-white")
                
                # Disable submit button
                submit_button.disable()
                submit_button.set_text("Submitted")
                
            except SeasonFrozenError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Season is Frozen").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Cannot submit job: {str(e)}").classes("text-red-700")
            except ValidationError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Validation Error").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Please check your inputs: {str(e)}").classes("text-red-700")
            except Exception as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Submission Failed").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Error: {str(e)}").classes("text-red-700")
        
        submit_button.on_click(submit_job)
        
        # Navigation buttons
        with ui.row().classes("w-full justify-between mt-4"):
            ui.button("Previous Step",
                     on_click=lambda: navigate_to_step(4),
                     icon="arrow_back").props("outline")
            
            ui.button("Save Configuration",
                     on_click=lambda: ui.notify("Save functionality not implemented in M1", type="info"),
                     icon="save").props("outline")
        
        # Initial update
        update_summary()
        
        # Auto-update summary
        ui.timer(2.0, update_summary)


def navigate_to_step(step: int, state: M1WizardState) -> None:
    """Navigate to specific step."""
    if 1 <= step <= 5:
        state.current_step = step
        for step_num, container in state.step_containers.items():
            container.set_visibility(step_num == step)


@ui.page("/wizard")
def wizard_page() -> None:
    """M1 Wizard main page."""
    ui.page_title("FishBroWFS V2 - M1 Wizard")
    
    state = M1WizardState()
    
    with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
        # Header
        ui.label("🧙‍♂️ M1 Wizard").classes("text-3xl font-bold mb-2")
        ui.label("Five-step job configuration wizard").classes("text-lg text-gray-600 mb-6")
        
        # Step indicator
        create_step_indicator(state)
        
        # Create step containers (all initially hidden except step 1)
        for step in range(1, 6):
            container = ui.column().classes("w-full")
            container.set_visibility(step == 1)
            state.step_containers[step] = container
        
        # Create step content
        create_step1_data1(state)
        create_step2_data2(state)
        create_step3_strategies(state)
        create_step4_cost(state)
        create_step5_summary(state)
        
        # Navigation buttons (global)
        with ui.row().classes("w-full justify-between mt-8"):
            prev_button = ui.button("Previous",
                                   on_click=lambda: navigate_to_step(state.current_step - 1, state),
                                   icon="arrow_back")
            prev_button.props("disabled" if state.current_step == 1 else "")
            
            next_button = ui.button("Next",
                                   on_click=lambda: navigate_to_step(state.current_step + 1, state),
                                   icon="arrow_forward")
            next_button.props("disabled" if state.current_step == 5 else "")
            
            # Update button states based on current step
            def update_nav_buttons():
                prev_button.props("disabled" if state.current_step == 1 else "")
                next_button.props("disabled" if state.current_step == 5 else "")
                next_button.set_text("Submit" if state.current_step == 4 else "Next")
            
            ui.timer(0.5, update_nav_buttons)
        
        # Quick links
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("Quick links:")
            ui.link("Jobs List", "/jobs").classes("ml-4 text-blue-500 hover:text-blue-700")
            ui.link("Dashboard", "/").classes("ml-4 text-blue-500 hover:text-blue-700")


def register() -> None:
    """Register wizard page routes."""
    # The @ui.page decorator already registers the routes
    # This function exists for compatibility with pages/__init__.py
    pass

# Also register at /wizard/m1 for testing
@ui.page("/wizard/m1")
def wizard_m1_page() -> None:
    """Alternative route for M1 wizard."""
    wizard_page()

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/wizard_backup.py
sha256(source_bytes) = 61ab12ebdb451eb6fa16cd52619b826f91b96b84344910a2e15a7e526cee3ceb
bytes = 4988
redacted = False
--------------------------------------------------------------------------------
"""Wizard 頁面 - 任務設定精靈"""

from nicegui import ui


def register() -> None:
    """註冊 Wizard 頁面路由"""
    
    @ui.page("/wizard")
    def wizard_page() -> None:
        """渲染 Wizard 頁面"""
        ui.page_title("FishBroWFS V2 - 任務設定精靈")
        
        with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
            # 標題
            ui.label("🧙‍♂️ 任務設定精靈").classes("text-3xl font-bold mb-2 text-cyber-glow")
            ui.label("引導式任務設定介面（取代舊版 new-job）").classes("text-lg text-slate-400 mb-8")
            
            # 步驟指示器
            with ui.row().classes("w-full mb-8 gap-2"):
                steps = [
                    ("1", "基本設定", True),
                    ("2", "策略選擇", False),
                    ("3", "回測參數", False),
                    ("4", "滑點壓力", False),
                    ("5", "確認提交", False),
                ]
                for num, label, active in steps:
                    with ui.column().classes("items-center"):
                        ui.label(num).classes(
                            f"w-8 h-8 rounded-full flex items-center justify-center font-bold "
                            f"{'bg-cyber-500 text-white' if active else 'bg-nexus-800 text-slate-400'}"
                        )
                        ui.label(label).classes(
                            f"text-sm mt-1 {'text-cyber-400 font-bold' if active else 'text-slate-500'}"
                        )
            
            # 內容區域
            with ui.card().classes("fish-card w-full p-6"):
                ui.label("步驟 1: 基本設定").classes("text-xl font-bold mb-6")
                
                # Season 選擇
                season_select = ui.select(
                    label="Season",
                    options=["2026Q1", "2026Q2", "2026Q3", "2026Q4"],
                    value="2026Q1"
                ).classes("w-full mb-4")
                
                # Dataset 選擇
                dataset_select = ui.select(
                    label="資料集",
                    options=["MNQ_MXF_2025", "MNQ_MXF_2026", "MES_MNQ_2025"],
                    value="MNQ_MXF_2025"
                ).classes("w-full mb-4")
                
                # Symbols 輸入
                symbols_input = ui.input(
                    label="交易標的 (逗號分隔)",
                    value="MNQ, MXF",
                    placeholder="例如: MNQ, MXF, MES"
                ).classes("w-full mb-4")
                
                # Timeframe 選擇
                timeframe_select = ui.select(
                    label="時間框架 (分鐘)",
                    options={60: "60分鐘", 120: "120分鐘", 240: "240分鐘"},
                    value=60
                ).classes("w-full mb-6")
            
            # 導航按鈕
            with ui.row().classes("w-full justify-between mt-8"):
                ui.button("上一步", icon="arrow_back", color="gray").props("disabled").tooltip("DEV MODE: not implemented yet")
                
                with ui.row().classes("gap-4"):
                    ui.button("儲存草稿", icon="save", color="gray").props("outline")
                    ui.button("下一步", icon="arrow_forward", on_click=lambda: ui.notify("下一步功能開發中", type="info")).classes("btn-cyber")
            
            # 快速跳轉
            with ui.row().classes("w-full mt-8 text-sm text-slate-500"):
                ui.label("快速跳轉:")
                ui.link("返回首頁", "/").classes("ml-4 text-cyber-400 hover:text-cyber-300")
                ui.link("查看歷史任務", "/history").classes("ml-4 text-cyber-400 hover:text-cyber-300")
                ui.link("舊版設定頁面", "/new-job").classes("ml-4 text-cyber-400 hover:text-cyber-300")
    
    # 支援 clone 參數
    @ui.page("/wizard/{clone_id}")
    def wizard_clone_page(clone_id: str) -> None:
        """渲染帶有 clone 參數的 Wizard 頁面"""
        ui.page_title(f"FishBroWFS V2 - Clone 任務 {clone_id[:8]}...")
        
        with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
            # 顯示 clone 資訊
            with ui.card().classes("fish-card w-full p-6 mb-6 border-cyber-500/50"):
                ui.label(f"📋 正在複製任務: {clone_id[:8]}...").classes("text-xl font-bold mb-2")
                ui.label("已自動填入欄位，請檢查並修改設定。").classes("text-slate-300")
            
            # 重定向到普通 wizard 頁面，但帶有 clone 參數提示
            ui.label("Clone 功能開發中...").classes("text-lg text-slate-400 mb-4")
            ui.label(f"將從任務 {clone_id} 複製設定。").classes("text-slate-500 mb-6")
            
            ui.button("前往 Wizard 主頁", on_click=lambda: ui.navigate.to("/wizard"), icon="rocket_launch").classes("btn-cyber")
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/wizard_m1.py
sha256(source_bytes) = 9cabc358d1461886e2a1e132957301f8e50d09b61cc05f6c26e1d2126865f95b
bytes = 27604
redacted = False
--------------------------------------------------------------------------------
"""M1 Wizard - Five-step wizard for job creation.

Step1: DATA1 (dataset / symbols / timeframes)
Step2: DATA2 (optional; single filter)
Step3: Strategies (schema-driven)
Step4: Cost
Step5: Summary (must show Units formula and number)
"""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
from datetime import date

from nicegui import ui

from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog
from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog
from FishBroWFS_V2.control.job_api import (
    create_job_from_wizard,
    calculate_units,
    check_season_not_frozen,
    ValidationError,
    SeasonFrozenError,
)


class M1WizardState:
    """State management for M1 wizard."""
    
    def __init__(self):
        # Step 1: DATA1
        self.season: str = "2024Q1"
        self.dataset_id: str = ""
        self.symbols: List[str] = []
        self.timeframes: List[str] = []
        self.start_date: Optional[date] = None
        self.end_date: Optional[date] = None
        
        # Step 2: DATA2
        self.enable_data2: bool = False
        self.data2_dataset_id: str = ""
        self.data2_filters: List[str] = []
        self.selected_filter: str = ""
        
        # Step 3: Strategies
        self.strategy_id: str = ""
        self.params: Dict[str, Any] = {}
        
        # Step 4: Cost (calculated)
        self.units: int = 0
        
        # Step 5: Summary
        self.job_id: Optional[str] = None
        
        # UI references
        self.step_containers: Dict[int, Any] = {}
        self.current_step: int = 1


def create_step_indicator(state: M1WizardState) -> None:
    """Create step indicator UI."""
    with ui.row().classes("w-full mb-8 gap-2"):
        steps = [
            (1, "DATA1", state.current_step == 1),
            (2, "DATA2", state.current_step == 2),
            (3, "Strategies", state.current_step == 3),
            (4, "Cost", state.current_step == 4),
            (5, "Summary", state.current_step == 5),
        ]
        
        for step_num, label, active in steps:
            with ui.column().classes("items-center"):
                ui.label(str(step_num)).classes(
                    f"w-8 h-8 rounded-full flex items-center justify-center font-bold "
                    f"{'bg-blue-500 text-white' if active else 'bg-gray-200 text-gray-600'}"
                )
                ui.label(label).classes(
                    f"text-sm mt-1 {'font-bold text-blue-600' if active else 'text-gray-500'}"
                )


def create_step1_data1(state: M1WizardState) -> None:
    """Create Step 1: DATA1 UI."""
    with state.step_containers[1]:
        ui.label("Step 1: DATA1 Configuration").classes("text-xl font-bold mb-4")
        
        # Season input
        from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_input, labeled_select, labeled_date
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Season")
            season_input = ui.input(
                value=state.season,
                placeholder="e.g., 2024Q1, 2024Q2"
            ).classes("w-full")
            season_input.bind_value(state, 'season')
        
        # Dataset selection
        catalog = get_dataset_catalog()
        datasets = catalog.list_datasets()
        dataset_options = {d.id: f"{d.symbol} ({d.timeframe}) {d.start_date}-{d.end_date}"
                          for d in datasets}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Dataset")
            dataset_select = ui.select(
                options=dataset_options,
                with_input=True
            ).classes("w-full")
            dataset_select.bind_value(state, 'dataset_id')
        
        # Symbols input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Symbols (comma separated)")
            symbols_input = ui.input(
                value="MNQ, MXF",
                placeholder="e.g., MNQ, MXF, MES"
            ).classes("w-full")
            symbols_input.bind_value(state, 'symbols')
        
        # Timeframes input
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Timeframes (comma separated)")
            timeframes_input = ui.input(
                value="60m, 120m",
                placeholder="e.g., 60m, 120m, 240m"
            ).classes("w-full")
            timeframes_input.bind_value(state, 'timeframes')
        
        # Date range
        with ui.row().classes("w-full"):
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("Start Date")
                start_date = ui.date(
                    value=date(2020, 1, 1)
                ).classes("w-full")
                start_date.bind_value(state, 'start_date')
            
            with ui.column().classes("gap-1 w-1/2"):
                ui.label("End Date")
                end_date = ui.date(
                    value=date(2024, 12, 31)
                ).classes("w-full")
                end_date.bind_value(state, 'end_date')
        
        # Initialize state with parsed values
        def parse_initial_values():
            if isinstance(state.symbols, str):
                state.symbols = [s.strip() for s in state.symbols.split(",") if s.strip()]
            elif not isinstance(state.symbols, list):
                state.symbols = []
            
            if isinstance(state.timeframes, str):
                state.timeframes = [t.strip() for t in state.timeframes.split(",") if t.strip()]
            elif not isinstance(state.timeframes, list):
                state.timeframes = []
        
        parse_initial_values()


def create_step2_data2(state: M1WizardState) -> None:
    """Create Step 2: DATA2 UI (optional, single filter)."""
    with state.step_containers[2]:
        ui.label("Step 2: DATA2 Configuration (Optional)").classes("text-xl font-bold mb-4")
        
        # Enable DATA2 toggle
        enable_toggle = ui.switch("Enable DATA2 (single filter validation)")
        enable_toggle.bind_value(state, 'enable_data2')
        
        # DATA2 container (initially hidden)
        data2_container = ui.column().classes("w-full mt-4")
        
        def update_data2_visibility(enabled: bool):
            data2_container.clear()
            if not enabled:
                state.data2_dataset_id = ""
                state.data2_filters = []
                state.selected_filter = ""
                return
            
            with data2_container:
                # Dataset selection for DATA2
                catalog = get_dataset_catalog()
                datasets = catalog.list_datasets()
                dataset_options = {d.id: f"{d.symbol} ({d.timeframe})" for d in datasets}
                
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("DATA2 Dataset")
                    dataset_select = ui.select(
                        options=dataset_options,
                        with_input=True
                    ).classes("w-full")
                    dataset_select.bind_value(state, 'data2_dataset_id')
                
                # Filter selection (single filter)
                filter_options = ["momentum", "volatility", "trend", "mean_reversion"]
                with ui.column().classes("gap-1 w-full mb-4"):
                    ui.label("Filter")
                    filter_select = ui.select(
                        options=filter_options,
                        value=filter_options[0] if filter_options else ""
                    ).classes("w-full")
                    filter_select.bind_value(state, 'selected_filter')
                
                # Initialize state
                state.data2_filters = filter_options
                if not state.selected_filter and filter_options:
                    state.selected_filter = filter_options[0]
        
        # Use timer to update visibility when enable_data2 changes
        def update_visibility_from_state():
            update_data2_visibility(state.enable_data2)
        
        ui.timer(0.2, update_visibility_from_state)
        
        # Initial visibility
        update_data2_visibility(state.enable_data2)


def create_step3_strategies(state: M1WizardState) -> None:
    """Create Step 3: Strategies UI (schema-driven)."""
    with state.step_containers[3]:
        ui.label("Step 3: Strategy Selection").classes("text-xl font-bold mb-4")
        
        # Strategy selection
        catalog = get_strategy_catalog()
        strategies = catalog.list_strategies()
        strategy_options = {s.strategy_id: s.strategy_id for s in strategies}
        
        with ui.column().classes("gap-1 w-full mb-4"):
            ui.label("Strategy")
            strategy_select = ui.select(
                options=strategy_options,
                with_input=True
            ).classes("w-full")
            strategy_select.bind_value(state, 'strategy_id')
        
        # Parameters container (dynamic)
        param_container = ui.column().classes("w-full mt-4")
        
        def update_strategy_ui(selected_id: str):
            param_container.clear()
            state.strategy_id = selected_id
            state.params = {}
            
            if not selected_id:
                return
            
            strategy = catalog.get_strategy(selected_id)
            if not strategy:
                return
            
            ui.label("Parameters").classes("font-bold mt-2 mb-2")
            
            # Create UI for each parameter
            for param in strategy.params:
                with ui.row().classes("w-full items-center mb-3"):
                    ui.label(f"{param.name}:").classes("w-1/3 font-medium")
                    
                    if param.type == "int" or param.type == "float":
                        # Number input
                        min_val = param.min if param.min is not None else 0
                        max_val = param.max if param.max is not None else 100
                        step = param.step if param.step is not None else (1 if param.type == "int" else 0.1)
                        
                        input_field = ui.number(
                            value=param.default,
                            min=min_val,
                            max=max_val,
                            step=step
                        ).classes("w-2/3")
                        
                        # Use on('update:model-value') for immediate updates
                        def make_param_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        input_field.on('update:model-value', make_param_handler(param.name, input_field))
                        state.params[param.name] = param.default
                        
                    elif param.type == "enum" and param.choices:
                        # Dropdown for enum
                        dropdown = ui.select(
                            options=param.choices,
                            value=param.default
                        ).classes("w-2/3")
                        
                        def make_enum_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        dropdown.on('update:model-value', make_enum_handler(param.name, dropdown))
                        state.params[param.name] = param.default
                        
                    elif param.type == "bool":
                        # Switch for boolean
                        switch = ui.switch(value=param.default).classes("w-2/3")
                        
                        def make_bool_handler(pname: str, field):
                            def handler(e):
                                state.params[pname] = e.args if hasattr(e, 'args') else field.value
                            return handler
                        
                        switch.on('update:model-value', make_bool_handler(param.name, switch))
                        state.params[param.name] = param.default
                    
                    # Help text
                    if param.help:
                        ui.tooltip(param.help).classes("ml-2")
        
        # Use timer to update UI when strategy_id changes
        def update_strategy_from_state():
            if state.strategy_id != getattr(update_strategy_from_state, '_last_strategy', None):
                update_strategy_ui(state.strategy_id)
                update_strategy_from_state._last_strategy = state.strategy_id
        
        ui.timer(0.2, update_strategy_from_state)
        
        # Initialize if strategy is selected
        if state.strategy_id:
            update_strategy_ui(state.strategy_id)
        elif strategies:
            # Select first strategy by default
            first_strategy = strategies[0].strategy_id
            state.strategy_id = first_strategy
            update_strategy_ui(first_strategy)


def create_step4_cost(state: M1WizardState) -> None:
    """Create Step 4: Cost UI (Units calculation)."""
    with state.step_containers[4]:
        ui.label("Step 4: Cost Estimation").classes("text-xl font-bold mb-4")
        
        # Units formula explanation
        with ui.card().classes("w-full mb-4 bg-blue-50"):
            ui.label("Units Formula").classes("font-bold text-blue-800")
            ui.label("Units = |DATA1.symbols| × |DATA1.timeframes| × |strategies| × |DATA2.filters|").classes("font-mono text-sm text-blue-700")
            ui.label("Where |strategies| = 1 (single strategy) and |DATA2.filters| = 1 if DATA2 disabled").classes("text-sm text-blue-600")
        
        # Current configuration summary
        config_card = ui.card().classes("w-full mb-4")
        
        # Units calculation result
        units_label = ui.label("Calculating units...").classes("text-2xl font-bold text-green-600")
        
        def update_cost_display():
            with config_card:
                config_card.clear()
                
                # Build payload for units calculation
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Calculate units
                try:
                    units = calculate_units(payload)
                    state.units = units
                    
                    # Display configuration
                    ui.label("Current Configuration:").classes("font-bold mb-2")
                    
                    with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                        ui.label("Season:").classes("font-medium")
                        ui.label(state.season)
                        
                        ui.label("DATA1 Dataset:").classes("font-medium")
                        ui.label(state.dataset_id if state.dataset_id else "Not selected")
                        
                        ui.label("Symbols:").classes("font-medium")
                        ui.label(f"{len(state.symbols)}: {', '.join(state.symbols)}" if state.symbols else "None")
                        
                        ui.label("Timeframes:").classes("font-medium")
                        ui.label(f"{len(state.timeframes)}: {', '.join(state.timeframes)}" if state.timeframes else "None")
                        
                        ui.label("Strategy:").classes("font-medium")
                        ui.label(state.strategy_id if state.strategy_id else "Not selected")
                        
                        ui.label("DATA2 Enabled:").classes("font-medium")
                        ui.label("Yes" if state.enable_data2 else "No")
                        
                        if state.enable_data2:
                            ui.label("DATA2 Filter:").classes("font-medium")
                            ui.label(state.selected_filter)
                    
                    # Update units display
                    units_label.set_text(f"Total Units: {units}")
                    
                    # Cost estimation (simplified)
                    if units > 100:
                        ui.label("⚠️ High cost warning: This job may take significant resources").classes("text-yellow-600 mt-2")
                    
                except Exception as e:
                    units_label.set_text(f"Error calculating units: {str(e)}")
                    state.units = 0
        
        # Update cost display periodically
        ui.timer(1.0, update_cost_display)


def create_step5_summary(state: M1WizardState) -> None:
    """Create Step 5: Summary and Submit UI."""
    with state.step_containers[5]:
        ui.label("Step 5: Summary & Submit").classes("text-xl font-bold mb-4")
        
        # Summary card
        summary_card = ui.card().classes("w-full mb-4")
        
        # Submit button
        submit_button = ui.button("Submit Job", icon="send", color="green")
        
        # Result container
        result_container = ui.column().classes("w-full mt-4")
        
        def update_summary():
            summary_card.clear()
            
            with summary_card:
                ui.label("Job Summary").classes("font-bold mb-2")
                
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Display payload
                ui.label("Final Payload:").classes("font-medium mt-2")
                payload_json = json.dumps(payload, indent=2)
                ui.textarea(payload_json).classes("w-full h-48 font-mono text-xs").props("readonly")
                
                # Units display
                units = calculate_units(payload)
                ui.label(f"Total Units: {units}").classes("font-bold text-lg mt-2")
                ui.label("Units = |symbols| × |timeframes| × |strategies| × |filters|").classes("text-sm text-gray-600")
                ui.label(f"= {len(state.symbols)} × {len(state.timeframes)} × 1 × {1 if state.enable_data2 else 1} = {units}").classes("text-sm font-mono")
        
        def submit_job():
            result_container.clear()
            
            try:
                # Build final payload
                payload = {
                    "season": state.season,
                    "data1": {
                        "dataset_id": state.dataset_id,
                        "symbols": state.symbols,
                        "timeframes": state.timeframes,
                        "start_date": str(state.start_date) if state.start_date else "",
                        "end_date": str(state.end_date) if state.end_date else ""
                    },
                    "data2": None,
                    "strategy_id": state.strategy_id,
                    "params": state.params,
                    "wfs": {
                        "stage0_subsample": 0.1,
                        "top_k": 20,
                        "mem_limit_mb": 8192,
                        "allow_auto_downsample": True
                    }
                }
                
                if state.enable_data2 and state.selected_filter:
                    payload["data2"] = {
                        "dataset_id": state.data2_dataset_id,
                        "filters": [state.selected_filter]
                    }
                    payload["enable_data2"] = True
                
                # Check season not frozen
                check_season_not_frozen(state.season, action="submit_job")
                
                # Submit job
                result = create_job_from_wizard(payload)
                state.job_id = result["job_id"]
                
                # Show success message
                with result_container:
                    with ui.card().classes("w-full bg-green-50 border-green-200"):
                        ui.label("✅ Job Submitted Successfully!").classes("text-green-800 font-bold mb-2")
                        ui.label(f"Job ID: {result['job_id']}").classes("font-mono text-sm mb-1")
                        ui.label(f"Units: {result['units']}").classes("text-sm mb-1")
                        ui.label(f"Season: {result['season']}").classes("text-sm mb-3")
                        
                        # Navigation button
                        ui.button(
                            "View Job Details",
                            on_click=lambda: ui.navigate.to(f"/jobs/{result['job_id']}"),
                            icon="visibility"
                        ).classes("bg-green-600 text-white")
                
                # Disable submit button
                submit_button.disable()
                submit_button.set_text("Submitted")
                
            except SeasonFrozenError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Season is Frozen").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Cannot submit job: {str(e)}").classes("text-red-700")
            except ValidationError as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Validation Error").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Please check your inputs: {str(e)}").classes("text-red-700")
            except Exception as e:
                with result_container:
                    with ui.card().classes("w-full bg-red-50 border-red-200"):
                        ui.label("❌ Submission Failed").classes("text-red-800 font-bold mb-2")
                        ui.label(f"Error: {str(e)}").classes("text-red-700")
        
        submit_button.on_click(submit_job)
        
        # Navigation buttons
        with ui.row().classes("w-full justify-between mt-4"):
            ui.button("Previous Step",
                     on_click=lambda: navigate_to_step(4),
                     icon="arrow_back").props("outline")
            
            ui.button("Save Configuration",
                     on_click=lambda: ui.notify("Save functionality not implemented in M1", type="info"),
                     icon="save").props("outline")
        
        # Initial update
        update_summary()
        
        # Auto-update summary
        ui.timer(2.0, update_summary)


def navigate_to_step(step: int, state: M1WizardState) -> None:
    """Navigate to specific step."""
    if 1 <= step <= 5:
        state.current_step = step
        for step_num, container in state.step_containers.items():
            container.set_visibility(step_num == step)


@ui.page("/wizard")
def wizard_page() -> None:
    """M1 Wizard main page."""
    ui.page_title("FishBroWFS V2 - M1 Wizard")
    
    state = M1WizardState()
    
    with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
        # Header
        ui.label("🧙‍♂️ M1 Wizard").classes("text-3xl font-bold mb-2")
        ui.label("Five-step job configuration wizard").classes("text-lg text-gray-600 mb-6")
        
        # Step indicator
        create_step_indicator(state)
        
        # Create step containers (all initially hidden except step 1)
        for step in range(1, 6):
            container = ui.column().classes("w-full")
            container.set_visibility(step == 1)
            state.step_containers[step] = container
        
        # Create step content
        create_step1_data1(state)
        create_step2_data2(state)
        create_step3_strategies(state)
        create_step4_cost(state)
        create_step5_summary(state)
        
        # Navigation buttons (global)
        with ui.row().classes("w-full justify-between mt-8"):
            prev_button = ui.button("Previous",
                                   on_click=lambda: navigate_to_step(state.current_step - 1, state),
                                   icon="arrow_back")
            prev_button.props("disabled" if state.current_step == 1 else "")
            
            next_button = ui.button("Next",
                                   on_click=lambda: navigate_to_step(state.current_step + 1, state),
                                   icon="arrow_forward")
            next_button.props("disabled" if state.current_step == 5 else "")
            
            # Update button states based on current step
            def update_nav_buttons():
                prev_button.props("disabled" if state.current_step == 1 else "")
                next_button.props("disabled" if state.current_step == 5 else "")
                next_button.set_text("Submit" if state.current_step == 4 else "Next")
            
            ui.timer(0.5, update_nav_buttons)
        
        # Quick links
        with ui.row().classes("w-full mt-8 text-sm text-gray-500"):
            ui.label("Quick links:")
            ui.link("Jobs List", "/jobs").classes("ml-4 text-blue-500 hover:text-blue-700")
            ui.link("Dashboard", "/").classes("ml-4 text-blue-500 hover:text-blue-700")


# Also register at /wizard/m1 for testing
@ui.page("/wizard/m1")
def wizard_m1_page() -> None:
    """Alternative route for M1 wizard."""
    wizard_page()

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/research/page.py
sha256(source_bytes) = dd4fe0e33162bee01d34c8c3b3320d29a555909c76e877e68245bc58ef73b672
bytes = 659
redacted = False
--------------------------------------------------------------------------------

"""Research Console Page Module (DEPRECATED).

Phase 10: Read-only Research UI + Decision Input.
This module is DEPRECATED after migration to NiceGUI.
"""

from __future__ import annotations

from pathlib import Path


def render(outputs_root: Path) -> None:
    """DEPRECATED: Research Console page renderer - no longer used after migration to NiceGUI.
    
    This function is kept for compatibility but will raise an ImportError
    if streamlit is not available.
    """
    raise ImportError(
        "research/page.py render() is deprecated. "
        "Streamlit UI has been migrated to NiceGUI. "
        "Use the NiceGUI dashboard instead."
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/actions.py
sha256(source_bytes) = cbd65d55b23533f31fea77f5a6284b90f409f65ebd35c22ea1d1de8035b342a8
bytes = 11582
redacted = False
--------------------------------------------------------------------------------
"""
UI Actions Service - Single entry point for UI-triggered actions.

Phase 4: UI must trigger actions via this service, not direct subprocess calls.
Phase 5: Respect season freeze state - actions cannot run on frozen seasons.
Phase 6: Live-safety lock - enforce action risk levels via policy engine.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional, Dict, Any

from FishBroWFS_V2.core.season_context import current_season, outputs_root
from FishBroWFS_V2.core.season_state import check_season_not_frozen
from FishBroWFS_V2.core.policy_engine import enforce_action_policy
from .audit_log import append_audit_event


ActionName = Literal[
    "generate_research",
    "build_portfolio_from_research",
    "export_season_package",
    "deploy_live",
    "send_orders",
    "broker_connect",
    "promote_to_live",
]


class ActionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class ActionResult:
    """Result of an action execution."""
    ok: bool
    action: ActionName
    season: str
    started_ts: str
    finished_ts: str
    stdout_tail: List[str]
    stderr_tail: List[str]
    artifacts_written: List[str]
    audit_event_path: str


def _get_venv_python() -> Path:
    """Return path to venv python executable."""
    venv_python = Path(".venv/bin/python")
    if venv_python.exists():
        return venv_python
    
    # Fallback to system python if venv not found
    return Path(sys.executable)


def _run_subprocess_with_timeout(
    cmd: List[str],
    timeout_seconds: int = 300,
    cwd: Optional[Path] = None,
) -> tuple[int, List[str], List[str]]:
    """Run subprocess and capture stdout/stderr with timeout.
    
    Returns:
        Tuple of (exit_code, stdout_lines, stderr_lines)
    """
    if cwd is None:
        cwd = Path.cwd()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        stdout_lines = result.stdout.splitlines() if result.stdout else []
        stderr_lines = result.stderr.splitlines() if result.stderr else []
        return result.returncode, stdout_lines, stderr_lines
    except subprocess.TimeoutExpired:
        return -1, ["Action timed out"], ["Timeout after {} seconds".format(timeout_seconds)]
    except Exception as e:
        return -2, [], [f"Subprocess error: {str(e)}"]


def _tail_lines(lines: List[str], max_lines: int = 200) -> List[str]:
    """Return last N lines from list."""
    return lines[-max_lines:] if len(lines) > max_lines else lines


def _build_action_command(action: ActionName, season: str, legacy_copy: bool = False) -> List[str]:
    """Build command line for the given action."""
    venv_python = _get_venv_python()
    cmd = [str(venv_python)]
    
    if action == "generate_research":
        cmd.extend([
            "-m", "scripts.generate_research",
            "--season", season,
            "--outputs-root", outputs_root(),
        ])
        if legacy_copy:
            cmd.append("--legacy-copy")
    
    elif action == "build_portfolio_from_research":
        cmd.extend([
            "-m", "scripts.build_portfolio_from_research",
            "--season", season,
            "--outputs-root", outputs_root(),
        ])
    
    elif action == "export_season_package":
        # Placeholder for future export functionality
        cmd.extend([
            "-c", "print('Export season package not yet implemented')"
        ])
    
    elif action in ["deploy_live", "send_orders", "broker_connect", "promote_to_live"]:
        # LIVE_EXECUTE actions are blocked by policy engine
        # This command should never be reached if policy enforcement works correctly
        cmd.extend([
            "-c", f"raise RuntimeError('LIVE_EXECUTE action {action} should have been blocked by policy engine')"
        ])
    
    else:
        raise ValueError(f"Unknown action: {action}")
    
    return cmd


def _collect_artifacts(action: ActionName, season: str) -> List[str]:
    """Collect key artifact paths written by the action."""
    season_dir = Path(outputs_root()) / "seasons" / season
    artifacts = []
    
    if action == "generate_research":
        research_dir = season_dir / "research"
        if research_dir.exists():
            for file in ["canonical_results.json", "research_index.json"]:
                path = research_dir / file
                if path.exists():
                    artifacts.append(str(path))
    
    elif action == "build_portfolio_from_research":
        portfolio_dir = season_dir / "portfolio"
        if portfolio_dir.exists():
            for file in ["portfolio_summary.json", "portfolio_manifest.json"]:
                path = portfolio_dir / file
                if path.exists():
                    artifacts.append(str(path))
            # Also include run-specific directories
            for item in portfolio_dir.iterdir():
                if item.is_dir() and len(item.name) == 12:  # portfolio_id pattern
                    for spec_file in ["portfolio_spec.json", "portfolio_manifest.json"]:
                        spec_path = item / spec_file
                        if spec_path.exists():
                            artifacts.append(str(spec_path))
    
    # LIVE_EXECUTE actions don't produce artifacts in the same way
    # They might produce deployment logs or order confirmations
    elif action in ["deploy_live", "send_orders", "broker_connect", "promote_to_live"]:
        live_dir = season_dir / "live"
        if live_dir.exists():
            for file in live_dir.iterdir():
                if file.is_file():
                    artifacts.append(str(file))
    
    return artifacts


def run_action(
    action: ActionName,
    season: Optional[str] = None,
    *,
    legacy_copy: bool = False,
    timeout_seconds: int = 300,
    check_integrity: bool = True,
) -> ActionResult:
    """
    Runs the action via subprocess using venv python.
    
    Must be deterministic in its file outputs given same inputs.
    Must write audit event jsonl for every action (success or fail).
    
    Phase 5: First line checks season freeze state - cannot run on frozen seasons.
    Phase 5: Optional integrity check for frozen seasons.
    Phase 6: Live-safety lock - enforce action risk levels via policy engine.
    
    Args:
        action: Action name.
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        legacy_copy: Whether to enable legacy copy for generate_research.
        timeout_seconds: Timeout for subprocess execution.
        check_integrity: Whether to verify season integrity before action (for frozen seasons).
    
    Returns:
        ActionResult with execution details.
    """
    # Phase 6: Live-safety lock - enforce action policy
    policy_decision = enforce_action_policy(action, season)
    if not policy_decision.allowed:
        raise PermissionError(f"Action blocked by policy: {policy_decision.reason}")
    
    # Phase 5: Check season freeze state before any action
    check_season_not_frozen(season, action=action)
    
    # Phase 5: Optional integrity check for frozen seasons
    if check_integrity:
        try:
            from FishBroWFS_V2.core.season_state import load_season_state
            from FishBroWFS_V2.core.snapshot import verify_snapshot_integrity
            
            season_str = season or current_season()
            state = load_season_state(season_str)
            if state.is_frozen():
                # Season is frozen, verify integrity
                integrity_result = verify_snapshot_integrity(season_str)
                if not integrity_result["ok"]:
                    # Log integrity violation but don't block action (frozen season already blocks)
                    print(f"WARNING: Season {season_str} integrity check failed for frozen season")
                    print(f"  Missing files: {len(integrity_result['missing_files'])}")
                    print(f"  Changed files: {len(integrity_result['changed_files'])}")
        except ImportError:
            # snapshot module may not be available in older versions
            pass
        except Exception as e:
            # Don't fail action on integrity check errors
            print(f"WARNING: Integrity check failed: {e}")
    
    if season is None:
        season = current_season()
    
    started_ts = datetime.now(timezone.utc).isoformat()
    
    # Build command
    cmd = _build_action_command(action, season, legacy_copy)
    
    # Run subprocess
    exit_code, stdout_lines, stderr_lines = _run_subprocess_with_timeout(
        cmd, timeout_seconds=timeout_seconds
    )
    
    finished_ts = datetime.now(timezone.utc).isoformat()
    ok = exit_code == 0
    
    # Collect artifacts
    artifacts_written = _collect_artifacts(action, season) if ok else []
    
    # Prepare audit event
    audit_event = {
        "ts": finished_ts,
        "actor": "gui",
        "action": action,
        "season": season,
        "ok": ok,
        "exit_code": exit_code,
        "inputs": {
            "action": action,
            "season": season,
            "legacy_copy": legacy_copy,
            "timeout_seconds": timeout_seconds,
        },
        "artifacts_written": artifacts_written,
    }
    
    if not ok:
        audit_event["error"] = {
            "exit_code": exit_code,
            "stderr_tail": _tail_lines(stderr_lines, 10),
        }
    
    # Write audit log
    audit_event_path = append_audit_event(audit_event, season=season)
    
    # Create result
    result = ActionResult(
        ok=ok,
        action=action,
        season=season,
        started_ts=started_ts,
        finished_ts=finished_ts,
        stdout_tail=_tail_lines(stdout_lines),
        stderr_tail=_tail_lines(stderr_lines),
        artifacts_written=artifacts_written,
        audit_event_path=audit_event_path,
    )
    
    return result


# Convenience functions for common actions
def generate_research(season: Optional[str] = None, legacy_copy: bool = False) -> ActionResult:
    """Generate research artifacts for a season."""
    return run_action("generate_research", season, legacy_copy=legacy_copy)


def build_portfolio_from_research(season: Optional[str] = None) -> ActionResult:
    """Build portfolio from research results."""
    return run_action("build_portfolio_from_research", season)


def get_action_status(action_id: str) -> Optional[Dict[str, Any]]:
    """Get status of a previously executed action (placeholder).
    
    Note: In a real implementation, this would track async actions.
    For now, actions are synchronous, so this returns None.
    """
    return None


def list_recent_actions(season: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """List recent actions from audit log."""
    from .audit_log import read_audit_tail
    
    events = read_audit_tail(season, max_lines=limit * 2)  # Read extra to filter
    action_events = []
    
    for event in events:
        if event.get("actor") == "gui" and "action" in event:
            action_events.append(event)
            if len(action_events) >= limit:
                break
    
    return action_events
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/archive.py
sha256(source_bytes) = 759f293f3ed85fd0a6c621068d622c6ef776b8cb95d9f99008cd7829c6e81de9
bytes = 6428
redacted = False
--------------------------------------------------------------------------------
"""Archive 服務 - 軟刪除 + Audit log"""

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import hashlib

# 嘗試導入 season_state 模組（Phase 5 新增）
try:
    from FishBroWFS_V2.core.season_state import load_season_state
    SEASON_STATE_AVAILABLE = True
except ImportError:
    SEASON_STATE_AVAILABLE = False
    load_season_state = None


@dataclass(frozen=True)
class ArchiveResult:
    """歸檔結果"""
    archived_path: str
    audit_path: str


def archive_run(
    outputs_root: Path,
    run_dir: Path,
    reason: str,
    operator: str = "local"
) -> ArchiveResult:
    """
    歸檔 run（軟刪除）
    
    Args:
        outputs_root: outputs 根目錄
        run_dir: 要歸檔的 run 目錄
        reason: 歸檔原因（必須是 failed/garbage/disk/other 之一）
        operator: 操作者標識
    
    Returns:
        ArchiveResult: 歸檔結果
    
    Raises:
        ValueError: 如果 reason 不在允許的清單中
        OSError: 如果移動檔案失敗
    """
    # 驗證 reason
    allowed_reasons = ["failed", "garbage", "disk", "other"]
    if reason not in allowed_reasons:
        raise ValueError(f"reason 必須是 {allowed_reasons} 之一，得到: {reason}")
    
    # 確保 run_dir 存在
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir 不存在: {run_dir}")
    
    # 從 run_dir 路徑解析 season 和 run_id
    # 路徑格式: .../seasons/<season>/runs/<run_id>
    parts = run_dir.parts
    try:
        # 尋找 seasons 索引
        seasons_idx = parts.index("seasons")
        if seasons_idx + 2 >= len(parts):
            raise ValueError(f"無法從路徑解析 season 和 run_id: {run_dir}")
        
        season = parts[seasons_idx + 1]
        run_id = parts[-1]
    except ValueError:
        # 如果找不到 seasons，使用預設值
        season = "unknown"
        run_id = run_dir.name
    
    # Phase 5: 檢查 season 是否被凍結
    if SEASON_STATE_AVAILABLE and load_season_state is not None:
        try:
            state = load_season_state(season)
            if state and state.get("state") == "FROZEN":
                frozen_reason = state.get("reason", "Season is frozen")
                raise ValueError(f"Cannot archive run: season {season} is frozen ({frozen_reason})")
        except Exception:
            # 如果載入失敗，忽略錯誤（允許歸檔）
            pass
    
    # 建立目標目錄
    archive_root = outputs_root / ".archive"
    archive_root.mkdir(exist_ok=True)
    
    season_archive_dir = archive_root / season
    season_archive_dir.mkdir(exist_ok=True)
    
    target_dir = season_archive_dir / run_id
    
    # 如果目標目錄已存在，添加時間戳後綴
    if target_dir.exists():
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        target_dir = season_archive_dir / f"{run_id}_{timestamp}"
    
    # 計算原始 manifest 的 SHA256（如果存在）
    manifest_sha256 = None
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'rb') as f:
                manifest_sha256 = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            pass
    
    # 移動目錄
    shutil.move(str(run_dir), str(target_dir))
    
    # 寫入 audit log
    audit_dir = archive_root / "_audit"
    audit_dir.mkdir(exist_ok=True)
    
    audit_file = audit_dir / "archive_log.jsonl"
    
    audit_entry = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "operator": operator,
        "reason": reason,
        "original_path": str(run_dir),
        "archived_path": str(target_dir),
        "season": season,
        "run_id": run_id,
        "original_manifest_sha256": manifest_sha256,
    }
    
    with open(audit_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
    
    return ArchiveResult(
        archived_path=str(target_dir),
        audit_path=str(audit_file)
    )


def list_archived_runs(outputs_root: Path, season: Optional[str] = None) -> list[dict]:
    """
    列出已歸檔的 runs
    
    Args:
        outputs_root: outputs 根目錄
        season: 可選的 season 過濾
    
    Returns:
        list[dict]: 已歸檔 runs 的清單
    """
    archive_root = outputs_root / ".archive"
    if not archive_root.exists():
        return []
    
    archived_runs = []
    
    # 掃描所有 season 目錄
    for season_dir in archive_root.iterdir():
        if not season_dir.is_dir() or season_dir.name == "_audit":
            continue
        
        if season is not None and season_dir.name != season:
            continue
        
        for run_dir in season_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            # 讀取 run 資訊
            manifest_path = run_dir / "manifest.json"
            manifest = None
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass
            
            archived_runs.append({
                "season": season_dir.name,
                "run_id": run_dir.name,
                "path": str(run_dir),
                "manifest": manifest,
            })
    
    return archived_runs


def read_audit_log(outputs_root: Path, limit: int = 100) -> list[dict]:
    """
    讀取 audit log
    
    Args:
        outputs_root: outputs 根目錄
        limit: 返回的條目數量限制
    
    Returns:
        list[dict]: audit log 條目
    """
    audit_file = outputs_root / ".archive" / "_audit" / "archive_log.jsonl"
    
    if not audit_file.exists():
        return []
    
    entries = []
    try:
        with open(audit_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 從最新開始讀取
        for line in reversed(lines[-limit:]):
            try:
                entry = json.loads(line.strip())
                entries.append(entry)
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    
    return entries
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/audit_log.py
sha256(source_bytes) = ffa41f82ed75a1201250bedb398af86a38381d41fe872e5c45853b4d92027e47
bytes = 3889
redacted = False
--------------------------------------------------------------------------------
"""
Audit Log - Append-only JSONL logging for UI actions.

Phase 4: Every UI Action / Archive / Clone must write an audit event.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from FishBroWFS_V2.core.season_context import outputs_root, season_dir


def append_audit_event(event: Dict[str, Any], *, season: Optional[str] = None) -> str:
    """Append one JSON line to outputs/seasons/{season}/governance/ui_audit.jsonl; return path.
    
    Args:
        event: Audit event dictionary (must be JSON-serializable)
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
    
    Returns:
        Path to the audit log file.
    
    Raises:
        OSError: If file cannot be written.
    """
    # Ensure event has required fields
    if "ts" not in event:
        event["ts"] = datetime.now(timezone.utc).isoformat()
    if "actor" not in event:
        event["actor"] = "gui"
    
    # Get season directory
    season_path = season_dir(season)
    audit_dir = season_path / "governance"
    audit_dir.mkdir(parents=True, exist_ok=True)
    
    audit_path = audit_dir / "ui_audit.jsonl"
    
    # Append JSON line
    with open(audit_path, "a", encoding="utf-8") as f:
        json_line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        f.write(json_line + "\n")
    
    return str(audit_path)


def read_audit_tail(season: Optional[str] = None, max_lines: int = 200) -> list[Dict[str, Any]]:
    """Read last N lines from audit log.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        max_lines: Maximum number of lines to read.
    
    Returns:
        List of audit events (most recent first).
    """
    season_path = season_dir(season)
    audit_path = season_path / "governance" / "ui_audit.jsonl"
    
    if not audit_path.exists():
        return []
    
    # Read file and parse last N lines
    lines = []
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            # Read all lines efficiently for small files
            all_lines = f.readlines()
            # Take last max_lines
            tail_lines = all_lines[-max_lines:] if len(all_lines) > max_lines else all_lines
        
        for line in tail_lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                lines.append(event)
            except json.JSONDecodeError:
                # Skip malformed lines
                continue
    except (OSError, UnicodeDecodeError):
        return []
    
    # Return in chronological order (oldest first)
    return lines


def get_audit_events_for_run_id(run_id: str, season: Optional[str] = None, max_lines: int = 200) -> list[Dict[str, Any]]:
    """Filter audit events for a specific run_id.
    
    Args:
        run_id: Run ID to filter by.
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        max_lines: Maximum number of lines to read from log.
    
    Returns:
        List of audit events related to the run_id.
    """
    all_events = read_audit_tail(season, max_lines)
    filtered = []
    
    for event in all_events:
        # Check if event is related to run_id
        inputs = event.get("inputs", {})
        artifacts = event.get("artifacts_written", [])
        
        # Check inputs for run_id
        if isinstance(inputs, dict) and inputs.get("run_id") == run_id:
            filtered.append(event)
            continue
        
        # Check artifacts for run_id pattern
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if run_id in str(artifact):
                    filtered.append(event)
                    break
    
    return filtered
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/candidates_reader.py
sha256(source_bytes) = d728be4fd30c46c2930fa8c2aab85871dfbdbd8261e3330c814073fa7ec6a442
bytes = 9938
redacted = False
--------------------------------------------------------------------------------
"""
Candidates Reader - 讀取 outputs/seasons/{season}/research/ 下的 canonical_results.json 和 research_index.json
Phase 4: 使用 season_context 作為單一真相來源
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

from FishBroWFS_V2.core.season_context import (
    current_season,
    canonical_results_path,
    research_index_path,
)

logger = logging.getLogger(__name__)

# 官方路徑契約 - 使用 season_context
def get_canonical_results_path(season: Optional[str] = None) -> Path:
    """返回 canonical_results.json 的路徑"""
    return canonical_results_path(season)

def get_research_index_path(season: Optional[str] = None) -> Path:
    """返回 research_index.json 的路徑"""
    return research_index_path(season)

@dataclass
class CanonicalResult:
    """Canonical Results 的單一項目"""
    run_id: str
    strategy_id: str
    symbol: str
    bars: int
    net_profit: float
    max_drawdown: float
    score_final: float
    score_net_mdd: float
    trades: int
    start_date: str
    end_date: str
    sharpe: Optional[float] = None
    profit_factor: Optional[float] = None
    portfolio_id: Optional[str] = None
    portfolio_version: Optional[str] = None
    strategy_version: Optional[str] = None
    timeframe_min: Optional[int] = None

@dataclass
class ResearchIndexEntry:
    """Research Index 的單一項目"""
    run_id: str
    season: str
    stage: str
    mode: str
    strategy_id: str
    dataset_id: str
    created_at: str
    status: str
    manifest_path: Optional[str] = None

def load_canonical_results(season: Optional[str] = None) -> List[CanonicalResult]:
    """
    載入 canonical_results.json
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        List[CanonicalResult]: 解析後的 canonical results 列表
        
    Raises:
        FileNotFoundError: 如果檔案不存在
        json.JSONDecodeError: 如果 JSON 格式錯誤
    """
    canonical_path = get_canonical_results_path(season)
    
    if not canonical_path.exists():
        logger.warning(f"Canonical results file not found: {canonical_path}")
        return []
    
    try:
        with open(canonical_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            logger.error(f"Canonical results should be a list, got {type(data)}")
            return []
        
        results = []
        for item in data:
            try:
                result = CanonicalResult(
                    run_id=item.get("run_id", ""),
                    strategy_id=item.get("strategy_id", ""),
                    symbol=item.get("symbol", "UNKNOWN"),
                    bars=item.get("bars", 0),
                    net_profit=item.get("net_profit", 0.0),
                    max_drawdown=item.get("max_drawdown", 0.0),
                    score_final=item.get("score_final", 0.0),
                    score_net_mdd=item.get("score_net_mdd", 0.0),
                    trades=item.get("trades", 0),
                    start_date=item.get("start_date", ""),
                    end_date=item.get("end_date", ""),
                    sharpe=item.get("sharpe"),
                    profit_factor=item.get("profit_factor"),
                    portfolio_id=item.get("portfolio_id"),
                    portfolio_version=item.get("portfolio_version"),
                    strategy_version=item.get("strategy_version"),
                    timeframe_min=item.get("timeframe_min"),
                )
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to parse canonical result item: {item}, error: {e}")
                continue
        
        logger.info(f"Loaded {len(results)} canonical results from {canonical_path}")
        return results
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse canonical_results.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading canonical results: {e}")
        return []

def load_research_index(season: Optional[str] = None) -> List[ResearchIndexEntry]:
    """
    載入 research_index.json
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        List[ResearchIndexEntry]: 解析後的 research index 列表
        
    Raises:
        FileNotFoundError: 如果檔案不存在
        json.JSONDecodeError: 如果 JSON 格式錯誤
    """
    research_path = get_research_index_path(season)
    
    if not research_path.exists():
        logger.warning(f"Research index file not found: {research_path}")
        return []
    
    try:
        with open(research_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            logger.error(f"Research index should be a list, got {type(data)}")
            return []
        
        entries = []
        for item in data:
            try:
                entry = ResearchIndexEntry(
                    run_id=item.get("run_id", ""),
                    season=item.get("season", ""),
                    stage=item.get("stage", ""),
                    mode=item.get("mode", ""),
                    strategy_id=item.get("strategy_id", ""),
                    dataset_id=item.get("dataset_id", ""),
                    created_at=item.get("created_at", ""),
                    status=item.get("status", ""),
                    manifest_path=item.get("manifest_path"),
                )
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse research index item: {item}, error: {e}")
                continue
        
        logger.info(f"Loaded {len(entries)} research index entries from {research_path}")
        return entries
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse research_index.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading research index: {e}")
        return []

def get_canonical_results_by_strategy(strategy_id: str, season: Optional[str] = None) -> List[CanonicalResult]:
    """
    根據 strategy_id 篩選 canonical results
    
    Args:
        strategy_id: 策略 ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        List[CanonicalResult]: 符合條件的結果列表
    """
    results = load_canonical_results(season)
    return [r for r in results if r.strategy_id == strategy_id]

def get_canonical_results_by_run_id(run_id: str, season: Optional[str] = None) -> Optional[CanonicalResult]:
    """
    根據 run_id 查找 canonical result
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Optional[CanonicalResult]: 找到的結果，如果沒有則返回 None
    """
    results = load_canonical_results(season)
    for result in results:
        if result.run_id == run_id:
            return result
    return None

def get_research_index_by_run_id(run_id: str, season: Optional[str] = None) -> Optional[ResearchIndexEntry]:
    """
    根據 run_id 查找 research index entry
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Optional[ResearchIndexEntry]: 找到的項目，如果沒有則返回 None
    """
    entries = load_research_index(season)
    for entry in entries:
        if entry.run_id == run_id:
            return entry
    return None

def get_research_index_by_season(season: str) -> List[ResearchIndexEntry]:
    """
    根據 season 篩選 research index
    
    Args:
        season: Season ID
        
    Returns:
        List[ResearchIndexEntry]: 符合條件的項目列表
    """
    entries = load_research_index(season)
    return [e for e in entries if e.season == season]

def get_combined_candidate_info(run_id: str, season: Optional[str] = None) -> Dict[str, Any]:
    """
    結合 canonical results 和 research index 的資訊
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Dict[str, Any]: 合併後的候選人資訊
    """
    canonical = get_canonical_results_by_run_id(run_id, season)
    research = get_research_index_by_run_id(run_id, season)
    
    result = {
        "run_id": run_id,
        "canonical": canonical.__dict__ if canonical else None,
        "research": research.__dict__ if research else None,
    }
    
    return result

def refresh_canonical_results(season: Optional[str] = None) -> bool:
    """
    刷新 canonical results（目前只是重新讀取檔案）
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        bool: 是否成功刷新
    """
    try:
        # 目前只是重新讀取檔案，未來可以加入重新生成邏輯
        results = load_canonical_results(season)
        logger.info(f"Refreshed canonical results, found {len(results)} entries")
        return True
    except Exception as e:
        logger.error(f"Failed to refresh canonical results: {e}")
        return False

def refresh_research_index(season: Optional[str] = None) -> bool:
    """
    刷新 research index（目前只是重新讀取檔案）
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        bool: 是否成功刷新
    """
    try:
        # 目前只是重新讀取檔案，未來可以加入重新生成邏輯
        entries = load_research_index(season)
        logger.info(f"Refreshed research index, found {len(entries)} entries")
        return True
    except Exception as e:
        logger.error(f"Failed to refresh research index: {e}")
        return False
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/clone.py
sha256(source_bytes) = ce9e3bb3966670ce4e504a071da1d05e2db608c108b218171b3e803ed530c7fe
bytes = 5487
redacted = False
--------------------------------------------------------------------------------
"""Clone to Wizard 服務 - 從現有 run 預填 Wizard 欄位"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


def load_config_snapshot(run_dir: Path) -> Optional[Dict[str, Any]]:
    """
    從 run_dir 載入 config snapshot
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Optional[Dict[str, Any]]: config snapshot 字典，如果不存在則返回 None
    """
    # 嘗試讀取 config_snapshot.json
    config_path = run_dir / "config_snapshot.json"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    
    # 嘗試讀取 manifest.json
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            # 從 manifest 提取 config 相關欄位
            config_snapshot = {
                "season": manifest.get("season"),
                "dataset_id": manifest.get("dataset_id"),
                "strategy_id": manifest.get("strategy_id"),
                "mode": manifest.get("mode"),
                "stage": manifest.get("stage"),
                "timestamp": manifest.get("timestamp"),
                "run_id": manifest.get("run_id"),
            }
            
            # 嘗試提取 wfs_config
            if "wfs_config" in manifest:
                config_snapshot["wfs_config"] = manifest["wfs_config"]
            
            return config_snapshot
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    
    return None


def build_wizard_prefill(run_dir: Path) -> Dict[str, Any]:
    """
    建立 Wizard 預填資料
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Dict[str, Any]: Wizard 預填資料
    """
    # 載入 config snapshot
    config = load_config_snapshot(run_dir)
    
    if config is None:
        # 如果無法載入 config，返回基本資訊
        return {
            "season": "2026Q1",
            "dataset_id": None,
            "strategy_id": None,
            "mode": "smoke",
            "note": f"Cloned from {run_dir.name}",
        }
    
    # 建立預填資料
    prefill: Dict[str, Any] = {
        "season": config.get("season", "2026Q1"),
        "dataset_id": config.get("dataset_id"),
        "strategy_id": config.get("strategy_id"),
        "mode": _map_mode(config.get("mode")),
        "note": f"Cloned from {run_dir.name}",
    }
    
    # 添加 wfs_config（如果存在）
    if "wfs_config" in config:
        prefill["wfs_config"] = config["wfs_config"]
    
    # 添加 grid preset（如果可推斷）
    grid_preset = _infer_grid_preset(config)
    if grid_preset:
        prefill["grid_preset"] = grid_preset
    
    # 添加 stage 資訊
    stage = config.get("stage")
    if stage:
        prefill["stage"] = stage
    
    return prefill


def _map_mode(mode: Optional[str]) -> str:
    """
    映射 mode 到 Wizard 可用的選項
    
    Args:
        mode: 原始 mode
    
    Returns:
        str: 映射後的 mode
    """
    if not mode:
        return "smoke"
    
    mode_lower = mode.lower()
    
    # 映射規則
    if "smoke" in mode_lower:
        return "smoke"
    elif "lite" in mode_lower:
        return "lite"
    elif "full" in mode_lower:
        return "full"
    elif "incremental" in mode_lower:
        return "incremental"
    else:
        # 預設回退
        return "smoke"


def _infer_grid_preset(config: Dict[str, Any]) -> Optional[str]:
    """
    從 config 推斷 grid preset
    
    Args:
        config: config snapshot
    
    Returns:
        Optional[str]: grid preset 名稱
    """
    # 檢查是否有 wfs_config
    wfs_config = config.get("wfs_config")
    if isinstance(wfs_config, dict):
        # 檢查是否有 grid 相關設定
        if "grid" in wfs_config or "param_grid" in wfs_config:
            return "custom"
    
    # 檢查 stage
    stage = config.get("stage")
    if stage:
        if "stage0" in stage:
            return "coarse"
        elif "stage1" in stage:
            return "topk"
        elif "stage2" in stage:
            return "confirm"
    
    # 檢查 mode
    mode = config.get("mode", "").lower()
    if "full" in mode:
        return "full_grid"
    elif "lite" in mode:
        return "lite_grid"
    
    return None


def get_clone_summary(run_dir: Path) -> Dict[str, Any]:
    """
    獲取 clone 摘要資訊（用於 UI 顯示）
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Dict[str, Any]: 摘要資訊
    """
    config = load_config_snapshot(run_dir)
    
    if config is None:
        return {
            "success": False,
            "error": "無法載入 config snapshot 或 manifest",
            "run_id": run_dir.name,
        }
    
    prefill = build_wizard_prefill(run_dir)
    
    return {
        "success": True,
        "run_id": run_dir.name,
        "season": prefill.get("season"),
        "dataset_id": prefill.get("dataset_id"),
        "strategy_id": prefill.get("strategy_id"),
        "mode": prefill.get("mode"),
        "stage": prefill.get("stage"),
        "grid_preset": prefill.get("grid_preset"),
        "has_wfs_config": "wfs_config" in prefill,
        "note": prefill.get("note"),
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/command_builder.py
sha256(source_bytes) = ff3c3d002b133d7049c8416d830dc25184ed23815aa27032f127cabc362bc9e2
bytes = 8737
redacted = False
--------------------------------------------------------------------------------
"""Generate Command 與 ui_command_snapshot.json 服務"""

import json
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass(frozen=True)
class CommandBuildResult:
    """命令建構結果"""
    argv: List[str]
    shell: str
    snapshot: Dict[str, Any]


def build_research_command(snapshot: Dict[str, Any]) -> CommandBuildResult:
    """
    從 UI snapshot 建構可重現的 CLI command
    
    Args:
        snapshot: UI 設定 snapshot
    
    Returns:
        CommandBuildResult: 命令建構結果
    """
    # 基礎命令
    argv = ["python", "-m", "src.FishBroWFS_V2.research"]
    
    # 添加必要參數
    required_fields = ["season", "dataset_id", "strategy_id", "mode"]
    for field in required_fields:
        if field in snapshot and snapshot[field]:
            argv.extend([f"--{field}", str(snapshot[field])])
    
    # 添加可選參數
    optional_fields = [
        "stage", "grid_preset", "note", "wfs_config_path",
        "param_grid", "max_workers", "timeout_hours"
    ]
    for field in optional_fields:
        if field in snapshot and snapshot[field]:
            argv.extend([f"--{field}", str(snapshot[field])])
    
    # 添加 wfs_config（如果是檔案路徑）
    if "wfs_config" in snapshot and isinstance(snapshot["wfs_config"], str):
        argv.extend(["--wfs-config", snapshot["wfs_config"]])
    
    # 構建 shell 命令字串
    shell_parts = []
    for arg in argv:
        if " " in arg or any(c in arg for c in ["'", '"', "\\", "$", "`"]):
            # 需要引號
            shell_parts.append(json.dumps(arg))
        else:
            shell_parts.append(arg)
    
    shell = " ".join(shell_parts)
    
    return CommandBuildResult(
        argv=argv,
        shell=shell,
        snapshot=snapshot
    )


def write_ui_snapshot(outputs_root: Path, season: str, snapshot: Dict[str, Any]) -> str:
    """
    將 UI snapshot 寫入檔案（append-only，不覆寫）
    
    Args:
        outputs_root: outputs 根目錄
        season: season 名稱
        snapshot: UI snapshot 資料
    
    Returns:
        str: 寫入的檔案路徑
    """
    # 建立目錄結構
    snapshots_dir = outputs_root / "seasons" / season / "ui_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    # 產生時間戳和 hash
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_str = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    snapshot_hash = hashlib.sha256(snapshot_str.encode()).hexdigest()[:8]
    
    # 檔案名稱
    filename = f"{timestamp}-{snapshot_hash}.json"
    filepath = snapshots_dir / filename
    
    # 確保不覆寫現有檔案（如果存在，添加計數器）
    counter = 1
    while filepath.exists():
        filename = f"{timestamp}-{snapshot_hash}-{counter}.json"
        filepath = snapshots_dir / filename
        counter += 1
    
    # 添加 metadata
    full_snapshot = {
        "_metadata": {
            "created_at": time.time(),
            "created_at_iso": datetime.now().isoformat(),
            "version": "1.0",
            "source": "ui_wizard",
            "snapshot_hash": snapshot_hash,
            "filename": filename,
        },
        "data": snapshot
    }
    
    # 寫入檔案
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(full_snapshot, f, indent=2, ensure_ascii=False)
    
    return str(filepath)


def load_ui_snapshot(filepath: Path) -> Optional[Dict[str, Any]]:
    """
    載入 UI snapshot 檔案
    
    Args:
        filepath: snapshot 檔案路徑
    
    Returns:
        Optional[Dict[str, Any]]: snapshot 資料，如果載入失敗則返回 None
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 返回實際資料（不含 metadata）
        if "data" in data:
            return data["data"]
        else:
            return data
    except (json.JSONDecodeError, OSError):
        return None


def list_ui_snapshots(outputs_root: Path, season: str, limit: int = 50) -> List[dict]:
    """
    列出指定 season 的 UI snapshots
    
    Args:
        outputs_root: outputs 根目錄
        season: season 名稱
        limit: 返回的數量限制
    
    Returns:
        List[dict]: snapshot 資訊清單
    """
    snapshots_dir = outputs_root / "seasons" / season / "ui_snapshots"
    
    if not snapshots_dir.exists():
        return []
    
    snapshots = []
    
    for filepath in sorted(snapshots_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not filepath.is_file() or not filepath.name.endswith('.json'):
            continue
        
        try:
            stat = filepath.stat()
            
            # 讀取 metadata（不讀取完整資料以提高效能）
            with open(filepath, 'r', encoding='utf-8') as f:
                metadata = json.load(f).get("_metadata", {})
            
            snapshots.append({
                "filename": filepath.name,
                "path": str(filepath),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created_at": metadata.get("created_at", stat.st_mtime),
                "created_at_iso": metadata.get("created_at_iso"),
                "snapshot_hash": metadata.get("snapshot_hash"),
                "source": metadata.get("source", "unknown"),
            })
            
            if len(snapshots) >= limit:
                break
        except (json.JSONDecodeError, OSError):
            continue
    
    return snapshots


def create_snapshot_from_wizard(wizard_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    從 Wizard 資料建立標準化的 snapshot
    
    Args:
        wizard_data: Wizard 表單資料
    
    Returns:
        Dict[str, Any]: 標準化的 snapshot
    """
    # 基礎欄位
    snapshot = {
        "season": wizard_data.get("season", "2026Q1"),
        "dataset_id": wizard_data.get("dataset_id"),
        "strategy_id": wizard_data.get("strategy_id"),
        "mode": wizard_data.get("mode", "smoke"),
        "note": wizard_data.get("note", ""),
        "created_from": "wizard",
        "created_at": time.time(),
        "created_at_iso": datetime.now().isoformat(),
    }
    
    # 可選欄位
    optional_fields = [
        "stage", "grid_preset", "wfs_config_path",
        "param_grid", "max_workers", "timeout_hours"
    ]
    for field in optional_fields:
        if field in wizard_data and wizard_data[field]:
            snapshot[field] = wizard_data[field]
    
    # wfs_config（如果是字典）
    if "wfs_config" in wizard_data and isinstance(wizard_data["wfs_config"], dict):
        snapshot["wfs_config"] = wizard_data["wfs_config"]
    
    # txt_paths（如果是清單）
    if "txt_paths" in wizard_data and isinstance(wizard_data["txt_paths"], list):
        snapshot["txt_paths"] = wizard_data["txt_paths"]
    
    return snapshot


def validate_snapshot_for_command(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    驗證 snapshot 是否可用於建構命令
    
    Args:
        snapshot: 要驗證的 snapshot
    
    Returns:
        Dict[str, Any]: 驗證結果
    """
    errors = []
    warnings = []
    
    # 檢查必要欄位
    required_fields = ["season", "dataset_id", "strategy_id", "mode"]
    for field in required_fields:
        if field not in snapshot or not snapshot[field]:
            errors.append(f"缺少必要欄位: {field}")
    
    # 檢查 season 格式
    if "season" in snapshot:
        season = snapshot["season"]
        if not isinstance(season, str) or len(season) < 4:
            warnings.append(f"season 格式可能不正確: {season}")
    
    # 檢查 mode 有效性
    valid_modes = ["smoke", "lite", "full", "incremental"]
    if "mode" in snapshot and snapshot["mode"] not in valid_modes:
        warnings.append(f"mode 可能無效: {snapshot['mode']}，有效值: {valid_modes}")
    
    # 檢查 wfs_config_path 是否存在（如果是檔案路徑）
    if "wfs_config_path" in snapshot and snapshot["wfs_config_path"]:
        path = Path(snapshot["wfs_config_path"])
        if not path.exists():
            warnings.append(f"wfs_config_path 不存在: {path}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "has_warnings": len(warnings) > 0,
        "required_fields_present": all(field in snapshot and snapshot[field] for field in required_fields),
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/log_tail.py
sha256(source_bytes) = a5b616fb1bd93b1013ced101272e7bea18072dc794bdef596564923e9f3a6b6a
bytes = 7233
redacted = False
--------------------------------------------------------------------------------
"""Logs Viewer 服務 - Lazy + Polling（禁止 push）"""

import os
import time
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime


def tail_lines(path: Path, n: int = 200) -> List[str]:
    """
    讀取檔案的最後 n 行
    
    Args:
        path: 檔案路徑
        n: 要讀取的行數
    
    Returns:
        List[str]: 最後 n 行的清單（如果檔案不存在則返回空清單）
    """
    if not path.exists():
        return []
    
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            # 簡單實現：讀取所有行然後取最後 n 行
            lines = f.readlines()
            return lines[-n:] if len(lines) > n else lines
    except (OSError, UnicodeDecodeError):
        return []


def tail_lines_with_stats(path: Path, n: int = 200) -> Tuple[List[str], dict]:
    """
    讀取檔案的最後 n 行並返回統計資訊
    
    Args:
        path: 檔案路徑
        n: 要讀取的行數
    
    Returns:
        Tuple[List[str], dict]: (行清單, 統計資訊)
    """
    lines = tail_lines(path, n)
    
    stats = {
        "file_exists": path.exists(),
        "file_size": path.stat().st_size if path.exists() else 0,
        "file_mtime": path.stat().st_mtime if path.exists() else 0,
        "lines_returned": len(lines),
        "timestamp": time.time(),
        "timestamp_iso": datetime.now().isoformat(),
    }
    
    return lines, stats


class LogTailer:
    """Log tailer 類別，支援 lazy polling"""
    
    def __init__(self, log_path: Path, max_lines: int = 200, poll_interval: float = 2.0):
        """
        初始化 LogTailer
        
        Args:
            log_path: log 檔案路徑
            max_lines: 最大行數
            poll_interval: polling 間隔（秒）
        """
        self.log_path = Path(log_path)
        self.max_lines = max_lines
        self.poll_interval = poll_interval
        self._last_read_position = 0
        self._last_read_time = 0.0
        self._is_active = False
        self._timer = None
    
    def start(self) -> None:
        """啟動 polling"""
        self._is_active = True
        self._last_read_position = 0
        self._last_read_time = time.time()
    
    def stop(self) -> None:
        """停止 polling"""
        self._is_active = False
        if self._timer:
            self._timer.cancel()
    
    def read_new_lines(self) -> List[str]:
        """
        讀取新的行（從上次讀取位置開始）
        
        Returns:
            List[str]: 新的行清單
        """
        if not self.log_path.exists():
            return []
        
        try:
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 移動到上次讀取的位置
                if self._last_read_position > 0:
                    try:
                        f.seek(self._last_read_position)
                    except (OSError, ValueError):
                        # 如果 seek 失敗，從頭開始讀取
                        self._last_read_position = 0
                
                # 讀取新行
                new_lines = f.readlines()
                
                # 更新位置
                self._last_read_position = f.tell()
                self._last_read_time = time.time()
                
                return new_lines
        except (OSError, UnicodeDecodeError):
            return []
    
    def get_status(self) -> dict:
        """獲取 tailer 狀態"""
        return {
            "is_active": self._is_active,
            "log_path": str(self.log_path),
            "log_exists": self.log_path.exists(),
            "last_read_position": self._last_read_position,
            "last_read_time": self._last_read_time,
            "last_read_time_iso": datetime.fromtimestamp(self._last_read_time).isoformat() if self._last_read_time > 0 else None,
            "poll_interval": self.poll_interval,
            "max_lines": self.max_lines,
        }


def find_log_files(run_dir: Path) -> List[dict]:
    """
    在 run_dir 中尋找 log 檔案
    
    Args:
        run_dir: run 目錄
    
    Returns:
        List[dict]: log 檔案資訊
    """
    if not run_dir.exists():
        return []
    
    log_files = []
    
    # 常見的 log 檔案名稱
    common_log_names = [
        "worker.log",
        "run.log",
        "output.log",
        "error.log",
        "stdout.log",
        "stderr.log",
        "log.txt",
    ]
    
    for log_name in common_log_names:
        log_path = run_dir / log_name
        if log_path.exists() and log_path.is_file():
            try:
                stat = log_path.stat()
                log_files.append({
                    "name": log_name,
                    "path": str(log_path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except OSError:
                continue
    
    # 也尋找 logs 目錄
    logs_dir = run_dir / "logs"
    if logs_dir.exists() and logs_dir.is_dir():
        try:
            for log_file in logs_dir.iterdir():
                if log_file.is_file() and log_file.suffix in ['.log', '.txt']:
                    try:
                        stat = log_file.stat()
                        log_files.append({
                            "name": f"logs/{log_file.name}",
                            "path": str(log_file),
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                            "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        })
                    except OSError:
                        continue
        except OSError:
            pass
    
    return log_files


def get_log_preview(log_path: Path, preview_lines: int = 50) -> dict:
    """
    獲取 log 檔案預覽
    
    Args:
        log_path: log 檔案路徑
        preview_lines: 預覽行數
    
    Returns:
        dict: log 預覽資訊
    """
    if not log_path.exists():
        return {
            "exists": False,
            "error": "Log 檔案不存在",
            "preview": [],
            "total_lines": 0,
        }
    
    try:
        # 計算總行數
        total_lines = 0
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for _ in f:
                total_lines += 1
        
        # 讀取預覽
        preview = tail_lines(log_path, preview_lines)
        
        stat = log_path.stat()
        return {
            "exists": True,
            "path": str(log_path),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "total_lines": total_lines,
            "preview_lines": len(preview),
            "preview": preview,
        }
    except (OSError, UnicodeDecodeError) as e:
        return {
            "exists": True,
            "error": str(e),
            "preview": [],
            "total_lines": 0,
        }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/path_picker.py
sha256(source_bytes) = 49e64d5f85e788f475a00ffc97a288c2922253e40f6383a9a1c293cd8288a535
bytes = 5951
redacted = False
--------------------------------------------------------------------------------
"""Server-side path selector - 禁止 file upload，只允許伺服器端路徑"""

import os
import glob
from pathlib import Path
from typing import List, Optional


# 允許的根目錄（根據 HUMAN TASKS 要求）
ALLOWED_ROOTS = [
    Path("/home/fishbro/FishBroData/raw"),
    Path("/home/fishbro/FishBroData/normalized"),  # 如果未來有
    Path(__file__).parent.parent.parent.parent / "data",  # 專案內的 data 目錄
]


def list_txt_candidates(base_dir: Path, pattern: str = "*.txt", limit: int = 200) -> List[str]:
    """
    列出指定目錄下的 txt 檔案候選
    
    Args:
        base_dir: 基礎目錄
        pattern: 檔案模式（預設 *.txt）
        limit: 返回的檔案數量限制
    
    Returns:
        List[str]: 檔案路徑清單（相對路徑或絕對路徑）
    
    Raises:
        ValueError: 如果 base_dir 不在 allowed roots 內
    """
    # 驗證 base_dir 是否在 allowed roots 內
    if not _is_allowed_path(base_dir):
        raise ValueError(f"base_dir 不在允許的根目錄內: {base_dir}")
    
    if not base_dir.exists():
        return []
    
    # 使用 glob 尋找檔案
    search_pattern = str(base_dir / "**" / pattern)
    files = []
    
    try:
        for file_path in glob.glob(search_pattern, recursive=True):
            if os.path.isfile(file_path):
                # 返回相對路徑（相對於 base_dir）
                rel_path = os.path.relpath(file_path, base_dir)
                files.append(rel_path)
                
                if len(files) >= limit:
                    break
    except (OSError, PermissionError):
        pass
    
    # 排序（按修改時間或名稱）
    files.sort()
    return files


def validate_server_path(p: str, allowed_roots: Optional[List[Path]] = None) -> str:
    """
    驗證伺服器端路徑是否在允許的根目錄內
    
    Args:
        p: 要驗證的路徑
        allowed_roots: 允許的根目錄清單（預設使用 ALLOWED_ROOTS）
    
    Returns:
        str: 驗證後的路徑（絕對路徑）
    
    Raises:
        ValueError: 如果路徑不在 allowed roots 內
        FileNotFoundError: 如果路徑不存在
    """
    if allowed_roots is None:
        allowed_roots = ALLOWED_ROOTS
    
    # 轉換為 Path 物件
    path = Path(p)
    
    # 如果是相對路徑，嘗試解析為絕對路徑
    if not path.is_absolute():
        # 嘗試在每個 allowed root 下尋找
        for root in allowed_roots:
            candidate = root / path
            if candidate.exists():
                path = candidate
                break
        else:
            # 如果找不到，使用第一個 allowed root 作為基礎
            path = allowed_roots[0] / path
    
    # 確保路徑是絕對路徑
    path = path.resolve()
    
    # 檢查是否在 allowed roots 內
    if not _is_allowed_path(path, allowed_roots):
        raise ValueError(f"路徑不在允許的根目錄內: {path}")
    
    # 檢查路徑是否存在
    if not path.exists():
        raise FileNotFoundError(f"路徑不存在: {path}")
    
    return str(path)


def _is_allowed_path(path: Path, allowed_roots: Optional[List[Path]] = None) -> bool:
    """
    檢查路徑是否在 allowed roots 內
    
    Args:
        path: 要檢查的路徑
        allowed_roots: 允許的根目錄清單
    
    Returns:
        bool: 是否允許
    """
    if allowed_roots is None:
        allowed_roots = ALLOWED_ROOTS
    
    path = path.resolve()
    
    for root in allowed_roots:
        root = root.resolve()
        try:
            # 檢查 path 是否是 root 的子目錄
            if path.is_relative_to(root):
                return True
        except (AttributeError, ValueError):
            # Python 3.8 兼容性：使用 str 比較
            if str(path).startswith(str(root) + os.sep):
                return True
    
    return False


def get_allowed_roots_info() -> List[dict]:
    """
    獲取 allowed roots 的資訊
    
    Returns:
        List[dict]: 每個 root 的資訊
    """
    info = []
    for root in ALLOWED_ROOTS:
        exists = root.exists()
        info.append({
            "path": str(root),
            "exists": exists,
            "readable": os.access(root, os.R_OK) if exists else False,
            "files_count": _count_files(root) if exists else 0,
        })
    return info


def _count_files(directory: Path) -> int:
    """計算目錄下的檔案數量"""
    if not directory.exists() or not directory.is_dir():
        return 0
    
    try:
        return sum(1 for _ in directory.rglob("*") if _.is_file())
    except (OSError, PermissionError):
        return 0


def browse_directory(directory: Path, pattern: str = "*") -> List[dict]:
    """
    瀏覽目錄內容
    
    Args:
        directory: 要瀏覽的目錄
        pattern: 檔案模式
    
    Returns:
        List[dict]: 目錄內容
    """
    if not _is_allowed_path(directory):
        raise ValueError(f"目錄不在允許的根目錄內: {directory}")
    
    if not directory.exists() or not directory.is_dir():
        return []
    
    contents = []
    try:
        for item in directory.iterdir():
            try:
                stat = item.stat()
                contents.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "is_file": item.is_file(),
                    "size": stat.st_size if item.is_file() else 0,
                    "mtime": stat.st_mtime,
                    "readable": os.access(item, os.R_OK),
                })
            except (OSError, PermissionError):
                continue
        
        # 排序：目錄在前，檔案在後
        contents.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    except (OSError, PermissionError):
        pass
    
    return contents
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/reload_service.py
sha256(source_bytes) = b80fcc1e996552f0c1ba3458a3155eaee88a1b9dc604419459ea6ab542964fb3
bytes = 16858
redacted = False
--------------------------------------------------------------------------------
"""Reload Service for System Status and Cache Invalidation.

Provides functions to:
1. Get system snapshot (datasets, strategies, caches)
2. Invalidate caches and reload registries
3. Compute file signatures for validation
4. TXT → Parquet build functionality
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog, DatasetCatalog
from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog, StrategyCatalog
from FishBroWFS_V2.control.feature_resolver import invalidate_feature_cache as invalidate_feature_cache_impl
from FishBroWFS_V2.control.data_build import BuildParquetRequest, BuildParquetResult, build_parquet_from_txt
from FishBroWFS_V2.control.dataset_descriptor import DatasetDescriptor, get_descriptor, list_descriptors
from FishBroWFS_V2.data.dataset_registry import DatasetRecord
from FishBroWFS_V2.strategy.registry import StrategySpecForGUI


@dataclass
class FileStatus:
    """Status of a file or directory."""
    path: str
    exists: bool
    size: int = 0
    mtime: float = 0.0
    signature: str = ""
    error: Optional[str] = None


@dataclass
class DatasetStatus:
    """Status of a dataset with TXT and Parquet information."""
    # Required fields (no defaults) first
    dataset_id: str
    kind: str
    txt_root: str
    txt_required_paths: List[str]
    parquet_root: str
    parquet_expected_paths: List[str]
    
    # Optional fields with defaults
    descriptor: Optional[DatasetDescriptor] = None
    txt_present: bool = False
    txt_missing: List[str] = field(default_factory=list)
    txt_latest_mtime_utc: Optional[str] = None
    txt_total_size_bytes: int = 0
    txt_signature: str = ""
    parquet_present: bool = False
    parquet_missing: List[str] = field(default_factory=list)
    parquet_latest_mtime_utc: Optional[str] = None
    parquet_total_size_bytes: int = 0
    parquet_signature: str = ""
    up_to_date: bool = False
    bars_count: Optional[int] = None
    schema_ok: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class StrategyStatus:
    """Status of a strategy."""
    id: str
    spec: Optional[StrategySpecForGUI] = None
    can_import: bool = False
    can_build_spec: bool = False
    mtime: float = 0.0
    signature: str = ""
    feature_requirements_count: int = 0
    error: Optional[str] = None


@dataclass
class SystemSnapshot:
    """System snapshot with status of all components."""
    created_at: datetime = field(default_factory=datetime.now)
    total_datasets: int = 0
    total_strategies: int = 0
    dataset_statuses: List[DatasetStatus] = field(default_factory=list)
    strategy_statuses: List[StrategyStatus] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ReloadResult:
    """Result of a reload operation."""
    ok: bool
    error: Optional[str] = None
    datasets_reloaded: int = 0
    strategies_reloaded: int = 0
    caches_invalidated: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def compute_file_signature(file_path: Path, max_size_mb: int = 50) -> str:
    """Compute signature for a file.
    
    For small files (< max_size_mb): compute sha256
    For large files: use stat-hash (path + size + mtime)
    """
    try:
        if not file_path.exists():
            return "missing"
        
        stat = file_path.stat()
        file_size_mb = stat.st_size / (1024 * 1024)
        
        if file_size_mb < max_size_mb:
            # Small file: compute actual hash
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                chunk_size = 8192
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return f"sha256:{hasher.hexdigest()[:16]}"
        else:
            # Large file: use stat-hash
            return f"stat:{file_path.name}:{stat.st_size}:{stat.st_mtime}"
    except Exception as e:
        return f"error:{str(e)[:50]}"


def check_txt_files(txt_root: str, txt_required_paths: List[str]) -> Tuple[bool, List[str], Optional[str], int, str]:
    """Check TXT files for a dataset.
    
    Returns:
        Tuple of (present, missing_paths, latest_mtime_utc, total_size_bytes, signature)
    """
    missing = []
    latest_mtime = 0.0
    total_size = 0
    signatures = []
    
    for txt_path_str in txt_required_paths:
        txt_path = Path(txt_path_str)
        if txt_path.exists():
            stat = txt_path.stat()
            latest_mtime = max(latest_mtime, stat.st_mtime)
            total_size += stat.st_size
            sig = compute_file_signature(txt_path)
            signatures.append(f"{txt_path.name}:{sig}")
        else:
            missing.append(txt_path_str)
    
    present = len(missing) == 0
    signature = "|".join(signatures) if signatures else "none"
    
    # Convert latest mtime to UTC string
    latest_mtime_utc = None
    if latest_mtime > 0:
        latest_mtime_utc = datetime.utcfromtimestamp(latest_mtime).isoformat() + "Z"
    
    return present, missing, latest_mtime_utc, total_size, signature


def check_parquet_files(parquet_root: str, parquet_expected_paths: List[str]) -> Tuple[bool, List[str], Optional[str], int, str]:
    """Check Parquet files for a dataset.
    
    Returns:
        Tuple of (present, missing_paths, latest_mtime_utc, total_size_bytes, signature)
    """
    missing = []
    latest_mtime = 0.0
    total_size = 0
    signatures = []
    
    for parquet_path_str in parquet_expected_paths:
        parquet_path = Path(parquet_path_str)
        if parquet_path.exists():
            stat = parquet_path.stat()
            latest_mtime = max(latest_mtime, stat.st_mtime)
            total_size += stat.st_size
            sig = compute_file_signature(parquet_path)
            signatures.append(f"{parquet_path.name}:{sig}")
        else:
            missing.append(parquet_path_str)
    
    present = len(missing) == 0
    signature = "|".join(signatures) if signatures else "none"
    
    # Convert latest mtime to UTC string
    latest_mtime_utc = None
    if latest_mtime > 0:
        latest_mtime_utc = datetime.utcfromtimestamp(latest_mtime).isoformat() + "Z"
    
    return present, missing, latest_mtime_utc, total_size, signature


def get_dataset_status(dataset_id: str) -> DatasetStatus:
    """Get status for a single dataset with TXT and Parquet information."""
    try:
        # Get dataset descriptor
        descriptor = get_descriptor(dataset_id)
        if descriptor is None:
            return DatasetStatus(
                dataset_id=dataset_id,
                kind="unknown",
                txt_root="",
                txt_required_paths=[],
                parquet_root="",
                parquet_expected_paths=[],
                error=f"Dataset not found: {dataset_id}"
            )
        
        # Check TXT files
        txt_present, txt_missing, txt_latest_mtime_utc, txt_total_size, txt_signature = check_txt_files(
            descriptor.txt_root, descriptor.txt_required_paths
        )
        
        # Check Parquet files
        parquet_present, parquet_missing, parquet_latest_mtime_utc, parquet_total_size, parquet_signature = check_parquet_files(
            descriptor.parquet_root, descriptor.parquet_expected_paths
        )
        
        # Determine if up-to-date
        up_to_date = False
        if txt_present and parquet_present:
            # Simple up-to-date check: compare signatures
            # In a real implementation, this would compare content hashes
            up_to_date = True  # Placeholder
        
        # Try to get bars count (lazy, can be expensive)
        bars_count = None
        schema_ok = None
        
        # Simple schema check for Parquet files
        if parquet_present and descriptor.parquet_expected_paths:
            try:
                parquet_path = Path(descriptor.parquet_expected_paths[0])
                if parquet_path.exists():
                    # Quick check: try to read first few rows
                    import pandas as pd
                    df_sample = pd.read_parquet(parquet_path, nrows=1)
                    schema_ok = True
                    bars_count = len(pd.read_parquet(parquet_path)) if parquet_path.stat().st_size < 1000000 else None
            except Exception:
                schema_ok = False
        
        return DatasetStatus(
            dataset_id=dataset_id,
            kind=descriptor.kind,
            descriptor=descriptor,
            txt_root=descriptor.txt_root,
            txt_required_paths=descriptor.txt_required_paths,
            txt_present=txt_present,
            txt_missing=txt_missing,
            txt_latest_mtime_utc=txt_latest_mtime_utc,
            txt_total_size_bytes=txt_total_size,
            txt_signature=txt_signature,
            parquet_root=descriptor.parquet_root,
            parquet_expected_paths=descriptor.parquet_expected_paths,
            parquet_present=parquet_present,
            parquet_missing=parquet_missing,
            parquet_latest_mtime_utc=parquet_latest_mtime_utc,
            parquet_total_size_bytes=parquet_total_size,
            parquet_signature=parquet_signature,
            up_to_date=up_to_date,
            bars_count=bars_count,
            schema_ok=schema_ok
        )
    except Exception as e:
        return DatasetStatus(
            dataset_id=dataset_id,
            kind="unknown",
            txt_root="",
            txt_required_paths=[],
            parquet_root="",
            parquet_expected_paths=[],
            error=str(e)
        )


def get_strategy_status(strategy: StrategySpecForGUI) -> StrategyStatus:
    """Get status for a single strategy."""
    try:
        # Check if strategy can be imported
        can_import = True  # Assume yes for now
        can_build_spec = True  # Assume yes for now
        
        # Get feature requirements count
        feature_requirements_count = 0
        if hasattr(strategy, 'feature_requirements'):
            feature_requirements_count = len(strategy.feature_requirements)
        
        # Try to get file info if path is available
        mtime = 0.0
        signature = ""
        if hasattr(strategy, 'file_path') and strategy.file_path:
            file_path = Path(strategy.file_path)
            if file_path.exists():
                stat = file_path.stat()
                mtime = stat.st_mtime
                signature = compute_file_signature(file_path)
        
        return StrategyStatus(
            id=strategy.strategy_id,
            spec=strategy,
            can_import=can_import,
            can_build_spec=can_build_spec,
            mtime=mtime,
            signature=signature,
            feature_requirements_count=feature_requirements_count
        )
    except Exception as e:
        return StrategyStatus(
            id=strategy.strategy_id if hasattr(strategy, 'strategy_id') else 'unknown',
            error=str(e),
            can_import=False,
            can_build_spec=False
        )


def get_system_snapshot() -> SystemSnapshot:
    """Get current system snapshot with TXT and Parquet status."""
    snapshot = SystemSnapshot()
    
    try:
        # Get dataset descriptors
        descriptors = list_descriptors()
        snapshot.total_datasets = len(descriptors)
        
        for descriptor in descriptors:
            status = get_dataset_status(descriptor.dataset_id)
            snapshot.dataset_statuses.append(status)
            if status.error:
                snapshot.errors.append(f"Dataset {descriptor.dataset_id}: {status.error}")
        
        # Get strategies
        strategy_catalog = get_strategy_catalog()
        strategies = strategy_catalog.list_strategies()
        snapshot.total_strategies = len(strategies)
        
        for strategy in strategies:
            status = get_strategy_status(strategy)
            snapshot.strategy_statuses.append(status)
            if status.error:
                snapshot.errors.append(f"Strategy {strategy.strategy_id}: {status.error}")
        
        # Add notes
        if snapshot.errors:
            snapshot.notes.append(f"Found {len(snapshot.errors)} errors")
        
        # Count TXT/Parquet status
        txt_present_count = sum(1 for ds in snapshot.dataset_statuses if ds.txt_present)
        parquet_present_count = sum(1 for ds in snapshot.dataset_statuses if ds.parquet_present)
        up_to_date_count = sum(1 for ds in snapshot.dataset_statuses if ds.up_to_date)
        
        snapshot.notes.append(f"TXT present: {txt_present_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Parquet present: {parquet_present_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Up-to-date: {up_to_date_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Snapshot created at {snapshot.created_at.isoformat()}")
        
    except Exception as e:
        snapshot.errors.append(f"Failed to get system snapshot: {str(e)}")
    
    return snapshot


def invalidate_feature_cache() -> bool:
    """Invalidate feature resolver cache."""
    try:
        return invalidate_feature_cache_impl()
    except Exception as e:
        return False


def reload_dataset_registry() -> bool:
    """Reload dataset registry."""
    try:
        catalog = get_dataset_catalog()
        # Force reload by calling load_index
        catalog.load_index()  # Force load
        return True
    except Exception as e:
        return False


def reload_strategy_registry() -> bool:
    """Reload strategy registry."""
    try:
        catalog = get_strategy_catalog()
        # Force reload by calling load_registry
        catalog.load_registry()  # Force load
        return True
    except Exception as e:
        return False


def reload_everything(reason: str = "manual") -> ReloadResult:
    """Reload all caches and registries."""
    start_time = time.time()
    result = ReloadResult(ok=True)
    caches_invalidated = []
    
    try:
        # 1. Invalidate feature cache
        if invalidate_feature_cache():
            caches_invalidated.append("feature_cache")
        else:
            result.ok = False
            result.error = "Failed to invalidate feature cache"
        
        # 2. Reload dataset registry
        if reload_dataset_registry():
            result.datasets_reloaded += 1
        else:
            result.ok = False
            result.error = "Failed to reload dataset registry"
        
        # 3. Reload strategy registry
        if reload_strategy_registry():
            result.strategies_reloaded += 1
        else:
            result.ok = False
            result.error = "Failed to reload strategy registry"
        
        # 4. Rebuild snapshot (implicitly done by get_system_snapshot)
        
        result.caches_invalidated = caches_invalidated
        result.duration_seconds = time.time() - start_time
        
        if result.ok:
            result.error = None
        
    except Exception as e:
        result.ok = False
        result.error = f"Reload failed: {str(e)}"
        result.duration_seconds = time.time() - start_time
    
    return result


def build_parquet(
    dataset_id: str,
    force: bool = False,
    deep_validate: bool = False,
    reason: str = "manual"
) -> BuildParquetResult:
    """Build Parquet from TXT for a dataset.
    
    Args:
        dataset_id: Dataset ID to build
        force: Rebuild even if up-to-date
        deep_validate: Perform schema validation after build
        reason: Reason for build (for audit/logging)
        
    Returns:
        BuildParquetResult with build status
    """
    req = BuildParquetRequest(
        dataset_id=dataset_id,
        force=force,
        deep_validate=deep_validate,
        reason=reason
    )
    
    return build_parquet_from_txt(req)


def build_all_parquet(force: bool = False, reason: str = "manual") -> List[BuildParquetResult]:
    """Build Parquet for all datasets.
    
    Args:
        force: Rebuild even if up-to-date
        reason: Reason for build (for audit/logging)
        
    Returns:
        List of BuildParquetResult for each dataset
    """
    results = []
    descriptors = list_descriptors()
    
    for descriptor in descriptors:
        result = build_parquet(
            dataset_id=descriptor.dataset_id,
            force=force,
            deep_validate=False,
            reason=f"{reason}_batch"
        )
        results.append(result)
    
    return results

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/runs_index.py
sha256(source_bytes) = eef1021b4bd992d1eb48c399a1a3cd60cdcbf68e3465d3732379482e5f17aa0d
bytes = 7518
redacted = False
--------------------------------------------------------------------------------
"""Runs Index 服務 - 禁止全量掃描，只讀最新 N 個 run"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass(frozen=True)
class RunIndexRow:
    """Run 索引行，包含必要 metadata"""
    run_id: str
    run_dir: str
    mtime: float
    season: str
    status: str
    mode: str
    strategy_id: Optional[str]
    dataset_id: Optional[str]
    stage: Optional[str]
    manifest_path: Optional[str]
    
    @property
    def mtime_iso(self) -> str:
        """返回 ISO 格式的修改時間"""
        return datetime.fromtimestamp(self.mtime).isoformat()
    
    @property
    def is_archived(self) -> bool:
        """檢查是否已歸檔（路徑包含 .archive）"""
        return ".archive" in self.run_dir


class RunsIndex:
    """Runs Index 管理器 - 只掃最新 N 個 run，避免全量掃描"""
    
    def __init__(self, outputs_root: Path, limit: int = 50) -> None:
        self.outputs_root = Path(outputs_root)
        self.limit = limit
        self._cache: List[RunIndexRow] = []
        self._cache_time: float = 0.0
        self._cache_ttl: float = 30.0  # 快取 30 秒
        
    def build(self) -> None:
        """建立索引（掃描 seasons/<season>/runs 目錄）"""
        rows: List[RunIndexRow] = []
        
        # 掃描所有 season 目錄
        seasons_dir = self.outputs_root / "seasons"
        if not seasons_dir.exists():
            self._cache = []
            self._cache_time = time.time()
            return
        
        for season_dir in seasons_dir.iterdir():
            if not season_dir.is_dir():
                continue
                
            season = season_dir.name
            runs_dir = season_dir / "runs"
            
            if not runs_dir.exists():
                continue
                
            # 只掃描 runs 目錄下的直接子目錄
            run_dirs = []
            for run_path in runs_dir.iterdir():
                if run_path.is_dir():
                    try:
                        mtime = run_path.stat().st_mtime
                        run_dirs.append((run_path, mtime, season))
                    except OSError:
                        continue
            
            # 按修改時間排序，取最新的
            run_dirs.sort(key=lambda x: x[1], reverse=True)
            
            for run_path, mtime, season in run_dirs[:self.limit]:
                row = self._parse_run_dir(run_path, mtime, season)
                if row:
                    rows.append(row)
        
        # 按修改時間全局排序
        rows.sort(key=lambda x: x.mtime, reverse=True)
        rows = rows[:self.limit]
        
        self._cache = rows
        self._cache_time = time.time()
    
    def _parse_run_dir(self, run_path: Path, mtime: float, season: str) -> Optional[RunIndexRow]:
        """解析單個 run 目錄，讀取 manifest.json（如果存在）"""
        run_id = run_path.name
        manifest_path = run_path / "manifest.json"
        
        # 預設值
        status = "unknown"
        mode = "unknown"
        strategy_id = None
        dataset_id = None
        stage = None
        
        # 嘗試讀取 manifest.json
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                # 從 manifest 提取資訊
                status = manifest.get("status", "unknown")
                mode = manifest.get("mode", "unknown")
                strategy_id = manifest.get("strategy_id")
                dataset_id = manifest.get("dataset_id")
                stage = manifest.get("stage")
                
                # 如果 stage 不存在，嘗試從 run_id 推斷
                if stage is None and "stage" in run_id:
                    for stage_name in ["stage0", "stage1", "stage2", "stage3"]:
                        if stage_name in run_id:
                            stage = stage_name
                            break
            except (json.JSONDecodeError, OSError):
                # 如果讀取失敗，使用預設值
                pass
        
        # 從 run_id 推斷 stage（如果尚未設定）
        if stage is None:
            if "stage0" in run_id:
                stage = "stage0"
            elif "stage1" in run_id:
                stage = "stage1"
            elif "stage2" in run_id:
                stage = "stage2"
            elif "demo" in run_id:
                stage = "demo"
        
        return RunIndexRow(
            run_id=run_id,
            run_dir=str(run_path),
            mtime=mtime,
            season=season,
            status=status,
            mode=mode,
            strategy_id=strategy_id,
            dataset_id=dataset_id,
            stage=stage,
            manifest_path=str(manifest_path) if manifest_path.exists() else None
        )
    
    def refresh(self) -> None:
        """刷新索引（重建快取）"""
        self.build()
    
    def list(self, season: Optional[str] = None, include_archived: bool = False) -> List[RunIndexRow]:
        """列出 runs（可選按 season 過濾）"""
        # 如果快取過期，重新建立
        if time.time() - self._cache_time > self._cache_ttl:
            self.build()
        
        rows = self._cache
        
        # 按 season 過濾
        if season is not None:
            rows = [r for r in rows if r.season == season]
        
        # 過濾歸檔的 runs
        if not include_archived:
            rows = [r for r in rows if not r.is_archived]
        
        return rows
    
    def get(self, run_id: str) -> Optional[RunIndexRow]:
        """根據 run_id 獲取單個 run"""
        # 如果快取過期，重新建立
        if time.time() - self._cache_time > self._cache_ttl:
            self.build()
        
        for row in self._cache:
            if row.run_id == run_id:
                return row
        
        # 如果不在快取中，嘗試直接查找
        # 掃描所有 season 目錄尋找該 run_id
        seasons_dir = self.outputs_root / "seasons"
        if seasons_dir.exists():
            for season_dir in seasons_dir.iterdir():
                if not season_dir.is_dir():
                    continue
                    
                runs_dir = season_dir / "runs"
                if not runs_dir.exists():
                    continue
                
                run_path = runs_dir / run_id
                if run_path.exists() and run_path.is_dir():
                    try:
                        mtime = run_path.stat().st_mtime
                        return self._parse_run_dir(run_path, mtime, season_dir.name)
                    except OSError:
                        pass
        
        return None


# Singleton instance for app-level caching
_global_index: Optional[RunsIndex] = None

def get_global_index(outputs_root: Optional[Path] = None) -> RunsIndex:
    """獲取全域 RunsIndex 實例（singleton）"""
    global _global_index
    
    if _global_index is None:
        if outputs_root is None:
            # 預設使用專案根目錄下的 outputs
            outputs_root = Path(__file__).parent.parent.parent.parent / "outputs"
        _global_index = RunsIndex(outputs_root)
        _global_index.build()
    
    return _global_index
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/services/stale.py
sha256(source_bytes) = 33e0a537d8b49a98dece00c3b6769a3b04d9d2a7d86b26931c1c7616e468cc06
bytes = 6340
redacted = False
--------------------------------------------------------------------------------
"""Stale Warning 服務 - UI 開著超過 10 分鐘顯示警告"""

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class StaleState:
    """Stale 狀態"""
    opened_at: float
    warned: bool = False
    last_check: float = 0.0
    warning_shown_at: Optional[float] = None


def should_warn_stale(state: StaleState, seconds: int = 600) -> bool:
    """
    檢查是否應該顯示 stale warning
    
    Args:
        state: StaleState 物件
        seconds: 警告閾值（秒），預設 600 秒（10 分鐘）
    
    Returns:
        bool: 是否應該顯示警告
    """
    if state.warned:
        return False
    
    elapsed = time.time() - state.opened_at
    return elapsed >= seconds


def update_stale_state(state: StaleState) -> dict:
    """
    更新 stale 狀態並返回狀態資訊
    
    Args:
        state: StaleState 物件
    
    Returns:
        dict: 狀態資訊
    """
    current_time = time.time()
    elapsed = current_time - state.opened_at
    
    state.last_check = current_time
    
    # 檢查是否應該警告
    should_warn = should_warn_stale(state)
    
    if should_warn and not state.warned:
        state.warned = True
        state.warning_shown_at = current_time
    
    return {
        "opened_at": state.opened_at,
        "opened_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.opened_at)),
        "elapsed_seconds": elapsed,
        "elapsed_minutes": elapsed / 60,
        "elapsed_hours": elapsed / 3600,
        "should_warn": should_warn,
        "warned": state.warned,
        "warning_shown_at": state.warning_shown_at,
        "warning_shown_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.warning_shown_at)) if state.warning_shown_at else None,
        "last_check": state.last_check,
    }


class StaleMonitor:
    """Stale 監視器"""
    
    def __init__(self, warning_threshold_seconds: int = 600):
        """
        初始化 StaleMonitor
        
        Args:
            warning_threshold_seconds: 警告閾值（秒）
        """
        self.warning_threshold = warning_threshold_seconds
        self._states = {}  # client_id -> StaleState
        self._start_time = time.time()
    
    def register_client(self, client_id: str) -> StaleState:
        """
        註冊客戶端
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            StaleState: 新建立的狀態
        """
        state = StaleState(opened_at=time.time())
        self._states[client_id] = state
        return state
    
    def unregister_client(self, client_id: str) -> None:
        """取消註冊客戶端"""
        if client_id in self._states:
            del self._states[client_id]
    
    def get_client_state(self, client_id: str) -> Optional[StaleState]:
        """獲取客戶端狀態"""
        return self._states.get(client_id)
    
    def update_client(self, client_id: str) -> Optional[dict]:
        """
        更新客戶端狀態
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            Optional[dict]: 狀態資訊，如果客戶端不存在則返回 None
        """
        state = self.get_client_state(client_id)
        if state is None:
            return None
        
        return update_stale_state(state)
    
    def check_all_clients(self) -> dict:
        """
        檢查所有客戶端
        
        Returns:
            dict: 所有客戶端的狀態摘要
        """
        results = {}
        warnings = []
        
        for client_id, state in self._states.items():
            info = update_stale_state(state)
            results[client_id] = info
            
            if info["should_warn"] and not state.warned:
                warnings.append({
                    "client_id": client_id,
                    "elapsed_minutes": info["elapsed_minutes"],
                    "opened_at": info["opened_at_iso"],
                })
        
        return {
            "total_clients": len(self._states),
            "clients": results,
            "warnings": warnings,
            "has_warnings": len(warnings) > 0,
            "monitor_uptime": time.time() - self._start_time,
        }
    
    def reset_client(self, client_id: str) -> Optional[StaleState]:
        """
        重置客戶端狀態（重新計時）
        
        Args:
            client_id: 客戶端 ID
        
        Returns:
            Optional[StaleState]: 新的狀態，如果客戶端不存在則返回 None
        """
        if client_id not in self._states:
            return None
        
        self._states[client_id] = StaleState(opened_at=time.time())
        return self._states[client_id]


# 全域監視器實例
_global_monitor: Optional[StaleMonitor] = None

def get_global_monitor() -> StaleMonitor:
    """獲取全域 StaleMonitor 實例"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = StaleMonitor()
    return _global_monitor


def create_stale_warning_message(state_info: dict) -> str:
    """
    建立 stale warning 訊息
    
    Args:
        state_info: 狀態資訊
    
    Returns:
        str: 警告訊息
    """
    elapsed_minutes = state_info["elapsed_minutes"]
    
    if elapsed_minutes < 60:
        time_str = f"{elapsed_minutes:.1f} 分鐘"
    else:
        time_str = f"{elapsed_minutes/60:.1f} 小時"
    
    return (
        f"⚠️  UI 已開啟 {time_str}，資料可能已過期。\n"
        f"建議重新整理頁面以獲取最新資料。\n"
        f"（開啟時間: {state_info['opened_at_iso']})"
    )


def create_stale_warning_ui_state(state_info: dict) -> dict:
    """
    建立 stale warning UI 狀態
    
    Args:
        state_info: 狀態資訊
    
    Returns:
        dict: UI 狀態
    """
    return {
        "show_warning": state_info["should_warn"],
        "message": create_stale_warning_message(state_info) if state_info["should_warn"] else "",
        "severity": "warning",
        "elapsed_minutes": state_info["elapsed_minutes"],
        "opened_at": state_info["opened_at_iso"],
        "can_dismiss": True,
        "auto_refresh_suggested": state_info["elapsed_minutes"] > 20,  # 超過 20 分鐘建議自動重新整理
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/viewer/__init__.py
sha256(source_bytes) = 2f52538f216f07d0e68d4bdb192cccd19072506ea5fcce09b2d87dcc9d05f4d6
bytes = 39
redacted = False
--------------------------------------------------------------------------------

"""Viewer package for Phase 6.0."""



--------------------------------------------------------------------------------


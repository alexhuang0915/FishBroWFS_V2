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
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
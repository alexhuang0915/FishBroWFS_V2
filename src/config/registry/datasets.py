"""
Dataset Registry Loader

Defines available datasets with storage details and metadata.
"""

from pathlib import Path
from typing import List, Dict, Optional
from functools import lru_cache
from enum import Enum

from pydantic import BaseModel, Field, field_validator


def get_registry_path(filename: str) -> Path:
    """Get path to registry configuration file."""
    from .. import get_config_root
    return get_config_root() / "registry" / filename


def load_yaml(path: Path) -> dict:
    """Load YAML file with proper error handling."""
    from .. import load_yaml as _load_yaml
    return _load_yaml(path)


class StorageType(str, Enum):
    """Type of dataset storage."""
    NPZ = "npz"
    PARQUET = "parquet"
    CSV = "csv"
    HDF5 = "h5"
    FEATHER = "feather"


class CalendarType(str, Enum):
    """Trading calendar type."""
    CME_ELECTRONIC = "CME_ELECTRONIC"
    TAIFEX = "TAIFEX"
    NYSE = "NYSE"
    LSE = "LSE"
    CUSTOM = "custom"


class DatasetSpec(BaseModel):
    """Specification for a single dataset."""
    
    id: str = Field(..., description="Dataset identifier (e.g., 'CME.MNQ.60m.2020-2024')")
    instrument_id: str = Field(..., description="Instrument ID this dataset belongs to")
    timeframe: int = Field(..., description="Timeframe in minutes")
    date_range: str = Field(..., description="Date range (e.g., '2020-2024')")
    
    storage_type: StorageType = Field(..., description="Storage format")
    uri: str = Field(..., description="URI template for dataset location")
    
    timezone: str = Field(..., description="Timezone for data (e.g., 'Asia/Taipei')")
    calendar: CalendarType = Field(..., description="Trading calendar type")
    
    # Optional fields
    description: Optional[str] = Field(None, description="Human-readable description")
    bar_count: Optional[int] = Field(None, description="Approximate number of bars")
    size_mb: Optional[float] = Field(None, description="Approximate size in MB")
    checksum: Optional[str] = Field(None, description="Data checksum for validation")
    
    class Config:
        frozen = True
    
    @field_validator('uri')
    @classmethod
    def validate_uri_template(cls, v: str) -> str:
        """Validate URI template contains {season} placeholder."""
        if '{season}' not in v:
            raise ValueError("URI must contain {season} placeholder for season substitution")
        return v


class DatasetRegistry(BaseModel):
    """Dataset registry configuration."""
    
    version: str = Field(..., description="Registry schema version")
    datasets: List[DatasetSpec] = Field(
        ..., 
        description="List of available datasets"
    )
    default: str = Field(
        ..., 
        description="Default dataset ID (must be in datasets)"
    )
    
    @field_validator('datasets')
    @classmethod
    def validate_datasets(cls, v: List[DatasetSpec]) -> List[DatasetSpec]:
        """Validate dataset list."""
        if not v:
            raise ValueError("datasets cannot be empty")
        
        # Check for duplicate IDs
        ids = [ds.id for ds in v]
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Duplicate dataset IDs: {duplicates}")
        
        return v
    
    @field_validator('default')
    @classmethod
    def validate_default_in_datasets(cls, v: str, info) -> str:
        """Validate default is in datasets."""
        datasets = info.data.get('datasets', [])
        dataset_ids = [ds.id for ds in datasets]
        if v not in dataset_ids:
            raise ValueError(f"Default dataset {v} not in datasets: {dataset_ids}")
        return v
    
    def get_dataset_by_id(self, dataset_id: str) -> Optional[DatasetSpec]:
        """Get dataset by ID."""
        for ds in self.datasets:
            if ds.id == dataset_id:
                return ds
        return None
    
    def get_datasets_by_instrument(self, instrument_id: str) -> List[DatasetSpec]:
        """Get all datasets for a specific instrument."""
        return [ds for ds in self.datasets if ds.instrument_id == instrument_id]
    
    def get_datasets_by_timeframe(self, timeframe: int) -> List[DatasetSpec]:
        """Get all datasets for a specific timeframe."""
        return [ds for ds in self.datasets if ds.timeframe == timeframe]
    
    def get_dataset_ids(self) -> List[str]:
        """Get list of all dataset IDs."""
        return [ds.id for ds in self.datasets]
    
    def get_dataset_choices(self) -> List[tuple[str, str]]:
        """Get (id, display_string) pairs for UI dropdowns."""
        choices = []
        for ds in self.datasets:
            display = f"{ds.instrument_id} - {ds.timeframe}m - {ds.date_range}"
            choices.append((ds.id, display))
        return choices
    
    def resolve_uri(self, dataset_id: str, season: str) -> Optional[str]:
        """
        Resolve dataset URI with season substitution.
        
        Args:
            dataset_id: Dataset ID
            season: Season identifier (e.g., "2026Q1")
            
        Returns:
            Resolved URI or None if dataset not found
        """
        dataset = self.get_dataset_by_id(dataset_id)
        if dataset is None:
            return None
        return dataset.uri.format(season=season)


@lru_cache(maxsize=1)
def load_datasets(path: Optional[Path] = None) -> DatasetRegistry:
    """
    Load dataset registry from YAML file.
    
    Args:
        path: Optional path to dataset registry YAML file.
              Defaults to configs/registry/datasets.yaml
    
    Returns:
        DatasetRegistry instance
        
    Raises:
        ConfigError: If loading or validation fails
    """
    if path is None:
        path = get_registry_path("datasets.yaml")
    
    data = load_yaml(path)
    try:
        return DatasetRegistry(**data)
    except Exception as e:
        from .. import ConfigError
        raise ConfigError(f"Failed to validate dataset registry at {path}: {e}")
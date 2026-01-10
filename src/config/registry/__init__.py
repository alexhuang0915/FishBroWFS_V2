"""
Registry Configuration Loaders

Registry files define UI menus and selection sources:
- timeframes.yaml: Allowed timeframes for strategy execution
- instruments.yaml: Available instruments with display names
- datasets.yaml: Available datasets with storage details  
- strategy_catalog.yaml: Available strategies with metadata

All registry files must be YAML with strict validation.
"""

from pathlib import Path
from typing import List, Optional
from functools import lru_cache

from pydantic import BaseModel, Field, ConfigDict, field_validator

from .. import get_registry_path, ConfigError
from .. import load_yaml


class RegistryBase(BaseModel):
    """Base model for all registry configurations."""
    model_config = ConfigDict(frozen=True)
    
    version: str = Field(..., description="Registry schema version")
    

@lru_cache(maxsize=1)
def _load_registry_cached(path: Path, model_class):
    """
    Load and cache registry configuration.
    
    Args:
        path: Path to registry YAML file
        model_class: Pydantic model class for validation
        
    Returns:
        Validated registry model instance
    """
    data = load_yaml(path)
    try:
        return model_class(**data)
    except Exception as e:
        raise ConfigError(f"Failed to validate registry at {path}: {e}")


# Re-export specific registry loaders
from .timeframes import load_timeframes, TimeframeRegistry
from .instruments import load_instruments, InstrumentRegistry
from .datasets import load_datasets, DatasetRegistry
from .strategy_catalog import load_strategy_catalog, StrategyCatalogRegistry

__all__ = [
    'RegistryBase',
    'load_timeframes', 'TimeframeRegistry',
    'load_instruments', 'InstrumentRegistry',
    'load_datasets', 'DatasetRegistry',
    'load_strategy_catalog', 'StrategyCatalogRegistry',
]
"""
Instrument Registry Loader

Defines available instruments with display names and metadata.
"""

from pathlib import Path
from typing import List, Dict, Optional
from functools import lru_cache
from enum import Enum

from pydantic import BaseModel, Field, field_validator, ConfigDict


def get_registry_path(filename: str) -> Path:
    """Get path to registry configuration file."""
    from .. import get_config_root
    return get_config_root() / "registry" / filename


def load_yaml(path: Path) -> dict:
    """Load YAML file with proper error handling."""
    from .. import load_yaml as _load_yaml
    return _load_yaml(path)


class InstrumentType(str, Enum):
    """Type of financial instrument."""
    FUTURE = "future"
    STOCK = "stock"
    FOREX = "forex"
    CRYPTO = "crypto"
    OPTION = "option"
    ETF = "etf"


class InstrumentSpec(BaseModel):
    """Specification for a single instrument."""
    
    id: str = Field(..., description="Instrument identifier (e.g., 'CME.MNQ')")
    display_name: str = Field(..., description="Display name for UI")
    type: InstrumentType = Field(..., description="Instrument type")
    profile: str = Field(..., description="Profile ID for this instrument", alias="default_profile")
    currency: str = Field(..., description="Trading currency")
    default_timeframe: int = Field(60, description="Default timeframe in minutes")
    
    # Optional fields
    exchange: Optional[str] = Field(None, description="Exchange name")
    multiplier: Optional[float] = Field(None, description="Contract multiplier")
    tick_size: Optional[float] = Field(None, description="Minimum price increment")
    tick_value: Optional[float] = Field(None, description="Value per tick")
    
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra='forbid')


class InstrumentRegistry(BaseModel):
    """Instrument registry configuration."""
    
    version: str = Field(..., description="Registry schema version")
    instruments: List[InstrumentSpec] = Field(
        ...,
        description="List of available instruments"
    )
    default: str = Field(
        ...,
        description="Default instrument ID (must be in instruments)"
    )
    
    model_config = ConfigDict(frozen=True, extra='forbid')
    
    @field_validator('instruments')
    @classmethod
    def validate_instruments(cls, v: List[InstrumentSpec]) -> List[InstrumentSpec]:
        """Validate instrument list."""
        if not v:
            raise ValueError("instruments cannot be empty")
        
        # Check for duplicate IDs
        ids = [inst.id for inst in v]
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Duplicate instrument IDs: {duplicates}")
        
        return v
    
    @field_validator('default')
    @classmethod
    def validate_default_in_instruments(cls, v: str, info) -> str:
        """Validate default is in instruments."""
        instruments = info.data.get('instruments', [])
        instrument_ids = [inst.id for inst in instruments]
        if v not in instrument_ids:
            raise ValueError(f"Default instrument {v} not in instruments: {instrument_ids}")
        return v
    
    def get_instrument_by_id(self, instrument_id: str) -> Optional[InstrumentSpec]:
        """Get instrument by ID."""
        for inst in self.instruments:
            if inst.id == instrument_id:
                return inst
        return None
    
    def get_instrument_ids(self) -> List[str]:
        """Get list of all instrument IDs."""
        return [inst.id for inst in self.instruments]
    
    def get_display_names(self) -> Dict[str, str]:
        """Get mapping of instrument ID to display name."""
        return {inst.id: inst.display_name for inst in self.instruments}
    
    def get_instrument_choices(self) -> List[tuple[str, str]]:
        """Get (id, display_name) pairs for UI dropdowns."""
        return [(inst.id, inst.display_name) for inst in self.instruments]
    
    def get_instruments_by_profile(self, profile_id: str) -> List[InstrumentSpec]:
        """Get all instruments that use a specific profile."""
        return [inst for inst in self.instruments if inst.profile == profile_id]


@lru_cache(maxsize=1)
def load_instruments(path: Optional[Path] = None) -> InstrumentRegistry:
    """
    Load instrument registry from YAML file.
    
    Args:
        path: Optional path to instrument registry YAML file.
              Defaults to configs/registry/instruments.yaml
    
    Returns:
        InstrumentRegistry instance
        
    Raises:
        ConfigError: If loading or validation fails
    """
    if path is None:
        path = get_registry_path("instruments.yaml")
    
    data = load_yaml(path)
    try:
        return InstrumentRegistry(**data)
    except Exception as e:
        from .. import ConfigError
        raise ConfigError(f"Failed to validate instrument registry at {path}: {e}")
"""
Timeframe Registry Loader

Defines allowed timeframes for strategy execution.
"""

from pathlib import Path
from typing import List, Optional
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator


def get_registry_path(filename: str) -> Path:
    """Get path to registry configuration file."""
    from .. import get_config_root
    return get_config_root() / "registry" / filename


def load_yaml(path: Path) -> dict:
    """Load YAML file with proper error handling."""
    from .. import load_yaml as _load_yaml
    return _load_yaml(path)


class TimeframeRegistry(BaseModel):
    """Timeframe registry configuration."""
    
    version: str = Field(..., description="Registry schema version")
    allowed_timeframes: List[int] = Field(
        ..., 
        description="List of allowed timeframe values in minutes"
    )
    default: int = Field(
        ..., 
        description="Default timeframe (must be in allowed_timeframes)"
    )
    
    @field_validator('allowed_timeframes')
    @classmethod
    def validate_timeframes(cls, v: List[int]) -> List[int]:
        """Validate timeframe values."""
        if not v:
            raise ValueError("allowed_timeframes cannot be empty")
        for tf in v:
            if tf <= 0:
                raise ValueError(f"Timeframe must be positive: {tf}")
            if tf % 15 != 0:
                raise ValueError(f"Timeframe must be multiple of 15 minutes: {tf}")
        # Ensure sorted for consistency
        return sorted(v)
    
    @field_validator('default')
    @classmethod
    def validate_default_in_allowed(cls, v: int, info) -> int:
        """Validate default is in allowed_timeframes."""
        allowed = info.data.get('allowed_timeframes', [])
        if v not in allowed:
            raise ValueError(f"Default timeframe {v} not in allowed_timeframes: {allowed}")
        return v
    
    def get_display_name(self, timeframe: int) -> str:
        """Get display name for timeframe."""
        if timeframe < 60:
            return f"{timeframe}m"
        elif timeframe == 60:
            return "1h"
        elif timeframe % 60 == 0:
            return f"{timeframe // 60}h"
        else:
            return f"{timeframe}m"
    
    def get_display_names(self) -> List[str]:
        """Get display names for all allowed timeframes."""
        return [self.get_display_name(tf) for tf in self.allowed_timeframes]
    
    def get_timeframe_choices(self) -> List[tuple[int, str]]:
        """Get (value, display_name) pairs for UI dropdowns."""
        return [(tf, self.get_display_name(tf)) for tf in self.allowed_timeframes]


@lru_cache(maxsize=1)
def load_timeframes(path: Optional[Path] = None) -> TimeframeRegistry:
    """
    Load timeframe registry from YAML file.
    
    Args:
        path: Optional path to timeframe registry YAML file.
              Defaults to configs/registry/timeframes.yaml
    
    Returns:
        TimeframeRegistry instance
        
    Raises:
        ConfigError: If loading or validation fails
    """
    if path is None:
        path = get_registry_path("timeframes.yaml")
    
    data = load_yaml(path)
    try:
        return TimeframeRegistry(**data)
    except Exception as e:
        from .. import ConfigError
        raise ConfigError(f"Failed to validate timeframe registry at {path}: {e}")


# Default timeframes (used as fallback during migration)
DEFAULT_TIMEFRAMES = [15, 30, 60, 120, 240]
DEFAULT_TIMEFRAME = 60
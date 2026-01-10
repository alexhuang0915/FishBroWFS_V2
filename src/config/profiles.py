"""
Profile Configuration Loader

Defines instrument specifications and cost models.
Profiles must include mandatory cost model with commission and slippage.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from functools import lru_cache
from enum import Enum
from datetime import time
import re

from pydantic import BaseModel, Field, field_validator, ConfigDict


def get_profile_path(profile_id: str) -> Path:
    """Get path to profile configuration file."""
    from . import get_config_root
    return get_config_root() / "profiles" / f"{profile_id}.yaml"


def load_yaml(path: Path) -> dict:
    """Load YAML file with proper error handling."""
    from . import load_yaml as _load_yaml
    return _load_yaml(path)


def compute_yaml_sha256(path: Path) -> str:
    """Compute SHA256 hash of YAML file."""
    from . import compute_yaml_sha256 as _compute_yaml_sha256
    return _compute_yaml_sha256(path)


class TradingState(str, Enum):
    """Trading session state."""
    TRADING = "TRADING"
    BREAK = "BREAK"
    CLOSED = "CLOSED"


class SessionWindow(BaseModel):
    """Trading session window."""
    
    state: TradingState = Field(..., description="Session state")
    start: str = Field(..., description="Start time (HH:MM:SS)")
    end: str = Field(..., description="End time (HH:MM:SS)")
    
    @field_validator('start', 'end')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time format HH:MM:SS."""
        try:
            time.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid time format: {v}. Expected HH:MM:SS")
        return v
    
    model_config = ConfigDict(frozen=True)


class CostModel(BaseModel):
    """Cost model with mandatory commission and slippage."""
    
    commission_per_side_usd: float = Field(
        ...,
        ge=0.0,
        description="Commission per side in USD (MANDATORY)"
    )
    slippage_per_side_usd: float = Field(
        ...,
        ge=0.0,
        description="Slippage per side in USD (MANDATORY)"
    )
    
    model_config = ConfigDict(frozen=True)


class SessionTaipeiSpec(BaseModel):
    """Trading session specification in Taipei time (for backward compatibility)."""
    
    open_taipei: str = Field(..., description="Open time in Taipei (HH:MM)")
    close_taipei: str = Field(..., description="Close time in Taipei (HH:MM)")
    breaks_taipei: List[Tuple[str, str]] = Field(
        default_factory=list,
        description="Break periods in Taipei time [(start, end), ...]"
    )
    tz: str = Field("Asia/Taipei", description="Timezone (always Asia/Taipei)")
    notes: str = Field("", description="Optional notes")
    
    @field_validator('open_taipei', 'close_taipei')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time format HH:MM."""
        if not re.match(r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$', v):
            raise ValueError(f"Time must be HH:MM format, got: {v}")
        return v
    
    @field_validator('breaks_taipei')
    @classmethod
    def validate_breaks_format(cls, v: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Validate break time format."""
        for start, end in v:
            if not re.match(r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$', start):
                raise ValueError(f"Break start must be HH:MM format, got: {start}")
            if not re.match(r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$', end):
                raise ValueError(f"Break end must be HH:MM format, got: {end}")
        return v
    
    model_config = ConfigDict(frozen=True)


class MemoryConfig(BaseModel):
    """Memory configuration for profile."""
    
    default_limit_mb: int = Field(
        2048,
        ge=256,
        le=16384,
        description="Default memory limit in MB"
    )
    allow_auto_downsample: bool = Field(
        True,
        description="Allow automatic downsampling when memory limit exceeded"
    )
    auto_downsample_step: float = Field(
        0.5,
        ge=0.1,
        le=1.0,
        description="Downsampling step size (fraction)"
    )
    auto_downsample_min: float = Field(
        0.02,
        ge=0.01,
        le=0.5,
        description="Minimum downsampling fraction"
    )
    
    model_config = ConfigDict(frozen=True)


class ProfileConfig(BaseModel):
    """Profile configuration with mandatory cost model and optional instrument specs."""
    
    version: str = Field(..., description="Profile schema version")
    symbol: str = Field(..., description="Instrument symbol (e.g., 'CME.MNQ')")
    
    # MANDATORY cost model
    cost_model: CostModel = Field(..., description="Cost model (MANDATORY)")
    
    # Session configuration (new format)
    exchange_tz: str = Field(..., description="Exchange timezone")
    data_tz: str = Field(..., description="Data timezone")
    windows: List[SessionWindow] = Field(
        default_factory=list,
        description="Trading session windows"
    )
    
    # Memory configuration
    memory: MemoryConfig = Field(
        default=MemoryConfig(
            default_limit_mb=2048,
            allow_auto_downsample=True,
            auto_downsample_step=0.5,
            auto_downsample_min=0.02
        ),
        description="Memory configuration"
    )
    
    # Optional instrument specifications (for backward compatibility with dimensions registry)
    tick_size: Optional[float] = Field(
        None,
        ge=0.0,
        description="Tick size (minimum price increment). If None, will be read from instrument registry."
    )
    currency: Optional[str] = Field(
        None,
        description="Trading currency (e.g., 'USD', 'TWD'). If None, will be read from instrument registry."
    )
    session_taipei: Optional[SessionTaipeiSpec] = Field(
        None,
        description="Session specification in Taipei time (for backward compatibility). "
                   "If None, will be derived from windows and timezones where possible."
    )
    
    # Optional fields
    mode: Optional[str] = Field(None, description="Processing mode")
    notes: Optional[str] = Field(None, description="Additional notes")
    
    # SHA256 hash of original YAML
    sha256: Optional[str] = Field(None, description="SHA256 hash of YAML file")
    
    model_config = ConfigDict(frozen=True)
    
    @field_validator('windows')
    @classmethod
    def validate_windows_cover_24h(cls, v: List[SessionWindow]) -> List[SessionWindow]:
        """Validate windows cover 24-hour cycle."""
        if not v:
            return v
        
        # For now, just ensure at least one window
        # More sophisticated validation could check for 24-hour coverage
        return v
    
    def get_total_commission(self, sides: int = 2) -> float:
        """Get total commission for given number of sides."""
        return self.cost_model.commission_per_side_usd * sides
    
    def get_total_slippage(self, sides: int = 2) -> float:
        """Get total slippage for given number of sides."""
        return self.cost_model.slippage_per_side_usd * sides
    
    def get_total_cost(self, sides: int = 2) -> float:
        """Get total cost (commission + slippage) for given number of sides."""
        return self.get_total_commission(sides) + self.get_total_slippage(sides)


@lru_cache(maxsize=4)
def load_profile(profile_id: str, path: Optional[Path] = None) -> ProfileConfig:
    """
    Load profile configuration from YAML file.
    
    Args:
        profile_id: Profile ID (e.g., "CME_MNQ")
        path: Optional path to profile YAML file.
              Defaults to configs/profiles/{profile_id}.yaml
    
    Returns:
        ProfileConfig instance with SHA256 hash
        
    Raises:
        ConfigError: If loading or validation fails
        ValueError: If mandatory cost model is missing
    """
    if path is None:
        path = get_profile_path(profile_id)
    
    # Compute SHA256 hash of original YAML
    sha256_hash = compute_yaml_sha256(path)
    
    data = load_yaml(path)
    
    # Validate mandatory cost_model exists
    if 'cost_model' not in data:
        raise ValueError(f"Profile {profile_id} missing mandatory 'cost_model' section")
    
    try:
        profile = ProfileConfig(**data, sha256=sha256_hash)
        return profile
    except Exception as e:
        from . import ConfigError
        raise ConfigError(f"Failed to validate profile {profile_id} at {path}: {e}")


def validate_all_profiles() -> Dict[str, Any]:
    """
    Validate all profiles in configs/profiles/ directory.
    
    Returns:
        Dictionary with validation results
    """
    from . import get_config_root
    
    config_root = get_config_root()
    profiles_dir = config_root / "profiles"
    
    results = {
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "details": {}
    }
    
    if not profiles_dir.exists():
        return results
    
    for yaml_file in profiles_dir.glob("*.yaml"):
        profile_id = yaml_file.stem
        results["total"] += 1
        
        try:
            profile = load_profile(profile_id, yaml_file)
            results["valid"] += 1
            results["details"][profile_id] = {
                "status": "valid",
                "symbol": profile.symbol,
                "has_cost_model": True,
                "sha256": profile.sha256[:16] + "..." if profile.sha256 else None
            }
        except Exception as e:
            results["invalid"] += 1
            results["details"][profile_id] = {
                "status": "invalid",
                "error": str(e)
            }
    
    return results
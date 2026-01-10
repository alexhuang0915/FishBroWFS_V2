"""
Config Constitution v1 - Unified Configuration Loader Infrastructure

This module provides a unified interface for loading and validating all configuration
files according to the Config Constitution v1 taxonomy.

Taxonomy:
- registry/: UI menus and selection sources (timeframes, instruments, datasets, strategy catalog)
- profiles/: Instrument specifications & cost models
- strategies/: Strategy parameters & feature flags  
- portfolio/: Governance & admission rules

All human-edited configs must be YAML-only with strict validation.
"""

from pathlib import Path
from typing import Optional
import hashlib

from pydantic import BaseModel, Field, ConfigDict, field_validator
import yaml

# Note: We use lazy imports to avoid circular imports
# Registry loaders are imported on demand
__all__ = [
    # Registry (imported lazily)
    'load_timeframes', 'TimeframeRegistry',
    'load_instruments', 'InstrumentRegistry',
    'load_datasets', 'DatasetRegistry',
    'load_strategy_catalog', 'StrategyCatalogRegistry',
    
    # Profiles
    'load_profile', 'ProfileConfig',
    
    # Strategies
    'load_strategy', 'StrategyConfig',
    
    # Portfolio
    'load_portfolio_config', 'PortfolioConfig',
    
    # Errors
    'ConfigError', 'ConfigValidationError', 'ConfigNotFoundError',
    
    # Utilities
    'load_yaml', 'compute_yaml_sha256', 'get_config_root',
    'get_registry_path', 'get_profile_path', 'get_strategy_path', 'get_portfolio_path',
    
    # Cost utilities (new in Config Constitution v1)
    'CostModelError', 'get_cost_model_for_instrument', 'get_commission_slippage_for_instrument',
]


# Lazy imports for registry modules to avoid circular imports
def __getattr__(name):
    if name == 'load_timeframes':
        from .registry.timeframes import load_timeframes
        return load_timeframes
    elif name == 'TimeframeRegistry':
        from .registry.timeframes import TimeframeRegistry
        return TimeframeRegistry
    elif name == 'load_instruments':
        from .registry.instruments import load_instruments
        return load_instruments
    elif name == 'InstrumentRegistry':
        from .registry.instruments import InstrumentRegistry
        return InstrumentRegistry
    elif name == 'load_datasets':
        from .registry.datasets import load_datasets
        return load_datasets
    elif name == 'DatasetRegistry':
        from .registry.datasets import DatasetRegistry
        return DatasetRegistry
    elif name == 'load_strategy_catalog':
        from .registry.strategy_catalog import load_strategy_catalog
        return load_strategy_catalog
    elif name == 'StrategyCatalogRegistry':
        from .registry.strategy_catalog import StrategyCatalogRegistry
        return StrategyCatalogRegistry
    elif name == 'load_profile':
        from .profiles import load_profile
        return load_profile
    elif name == 'ProfileConfig':
        from .profiles import ProfileConfig
        return ProfileConfig
    elif name == 'load_strategy':
        from .strategies import load_strategy
        return load_strategy
    elif name == 'StrategyConfig':
        from .strategies import StrategyConfig
        return StrategyConfig
    elif name == 'load_portfolio_config':
        from .portfolio import load_portfolio_config
        return load_portfolio_config
    elif name == 'PortfolioConfig':
        from .portfolio import PortfolioConfig
        return PortfolioConfig
    elif name == 'CostModelError':
        from .cost_utils import CostModelError
        return CostModelError
    elif name == 'get_cost_model_for_instrument':
        from .cost_utils import get_cost_model_for_instrument
        return get_cost_model_for_instrument
    elif name == 'get_commission_slippage_for_instrument':
        from .cost_utils import get_commission_slippage_for_instrument
        return get_commission_slippage_for_instrument
    else:
        raise AttributeError(f"module 'src.config' has no attribute '{name}'")


class ConfigError(Exception):
    """Base exception for configuration errors."""
    pass


class ConfigValidationError(ConfigError):
    """Raised when configuration validation fails."""
    pass


class ConfigNotFoundError(ConfigError):
    """Raised when configuration file is not found."""
    pass


def compute_yaml_sha256(path: Path) -> str:
    """
    Compute SHA256 hash of YAML file bytes for deterministic hashing.
    
    Args:
        path: Path to YAML file
        
    Returns:
        SHA256 hex digest
    """
    raw_bytes = path.read_bytes()
    return hashlib.sha256(raw_bytes).hexdigest()


def load_yaml(path: Path) -> dict:
    """
    Load YAML file with proper error handling.
    
    Args:
        path: Path to YAML file
        
    Returns:
        Parsed YAML data as dict
        
    Raises:
        ConfigNotFoundError: If file doesn't exist
        ConfigValidationError: If YAML is malformed
    """
    if not path.exists():
        raise ConfigNotFoundError(f"Config file not found: {path}")
    
    try:
        raw_bytes = path.read_bytes()
        data = yaml.safe_load(raw_bytes)
        if data is None:
            data = {}
        return data
    except yaml.YAMLError as e:
        raise ConfigValidationError(f"Invalid YAML in {path}: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to load config from {path}: {e}")


def get_config_root() -> Path:
    """
    Get the root directory for configuration files.
    
    Returns:
        Path to configs/ directory
    """
    return Path("configs")


def get_registry_path(filename: str) -> Path:
    """
    Get path to registry configuration file.
    
    Args:
        filename: Registry filename (e.g., "timeframes.yaml")
        
    Returns:
        Full path to registry file
    """
    return get_config_root() / "registry" / filename


def get_profile_path(profile_id: str) -> Path:
    """
    Get path to profile configuration file.
    
    Args:
        profile_id: Profile ID (e.g., "CME_MNQ")
        
    Returns:
        Full path to profile file
    """
    return get_config_root() / "profiles" / f"{profile_id}.yaml"


def get_strategy_path(strategy_id: str) -> Path:
    """
    Get path to strategy configuration file.
    
    Args:
        strategy_id: Strategy ID (e.g., "s1_v1")
        
    Returns:
        Full path to strategy file
    """
    return get_config_root() / "strategies" / f"{strategy_id}.yaml"


def get_portfolio_path(filename: str) -> Path:
    """
    Get path to portfolio configuration file.
    
    Args:
        filename: Portfolio filename (e.g., "governance.yaml")
        
    Returns:
        Full path to portfolio file
    """
    return get_config_root() / "portfolio" / filename

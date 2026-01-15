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
from typing import Optional, Dict, List, Any
import hashlib
from collections import defaultdict

from pydantic import BaseModel, Field, ConfigDict, field_validator
import yaml

# Configuration load instrumentation
_loaded_configs: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "sha256": None})
_config_recording_enabled = True

def record_config_load(path: Path, sha256: Optional[str] = None) -> None:
    """Record a config file load for reachability reporting."""
    if not _config_recording_enabled:
        return
    rel_path = str(path.relative_to(get_config_root())) if path.is_relative_to(get_config_root()) else str(path)
    if sha256 is None:
        sha256 = compute_yaml_sha256(path)
    entry = _loaded_configs[rel_path]
    entry["count"] += 1
    entry["sha256"] = sha256

def reset_config_load_records() -> None:
    """Clear all recorded config loads."""
    _loaded_configs.clear()

def get_config_load_records() -> Dict[str, Dict[str, Any]]:
    """Get a copy of recorded config loads."""
    return dict(_loaded_configs)

def enable_config_recording(enabled: bool = True) -> None:
    """Enable or disable config load recording."""
    global _config_recording_enabled
    _config_recording_enabled = enabled


def clear_config_caches() -> None:
    """Clear all LRU caches in config loaders to force fresh loads."""
    from .profiles import load_profile
    from .strategies import load_strategy
    from .registry.instruments import load_instruments
    from .registry.datasets import load_datasets
    from .registry.strategy_catalog import load_strategy_catalog
    from .registry.timeframes import load_timeframes
    from .registry import _load_registry_cached
    from .portfolio import load_portfolio_config
    from .cost_utils import get_instrument_spec, get_profile_for_instrument

    # List of functions that are known to be cached
    cached_functions = [
        load_profile,
        load_strategy,
        load_instruments,
        load_datasets,
        load_strategy_catalog,
        load_timeframes,
        _load_registry_cached,
        load_portfolio_config,
        get_instrument_spec,
        get_profile_for_instrument,
    ]
    
    for func in cached_functions:
        try:
            # Check if function has cache_clear attribute and it's callable
            cache_clear = getattr(func, 'cache_clear', None)
            if cache_clear is not None and callable(cache_clear):
                cache_clear()
        except Exception:
            # Silently ignore any errors; cache clearing is non-critical
            pass


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
    
    # Instrumentation
    'record_config_load', 'reset_config_load_records', 'get_config_load_records', 'enable_config_recording',
    'clear_config_caches', 'write_config_load_report',
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
        # Record config load for reachability reporting
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        record_config_load(path, sha256)
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


def write_config_load_report(output_dir: Path) -> None:
    """
    Write recorded config loads to a JSON report.
    
    Args:
        output_dir: Directory where report should be written.
                    The report will be saved as 'loaded_configs_report.json'.
    """
    import json
    import time
    
    records = get_config_load_records()
    report = {
        "generated_at": time.time(),
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "configs_loaded": len(records),
        "records": records,
    }
    
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "loaded_configs_report.json"
    
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # Also write a summary text file for quick inspection
    summary_path = output_dir / "loaded_configs_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Config Load Reachability Report\n")
        f.write(f"Generated at: {report['generated_at_iso']}\n")
        f.write(f"Total config files loaded: {len(records)}\n")
        f.write("\n")
        for rel_path, info in sorted(records.items()):
            f.write(f"{rel_path}: count={info['count']}, sha256={info['sha256'][:16]}...\n")

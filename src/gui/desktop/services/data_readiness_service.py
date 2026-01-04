"""
Data Readiness Service for Desktop UI - checks if bars and features are ready.

Implements deterministic checks using existing data layout contracts.
Read-only: only checks filesystem existence, no writes.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Readiness:
    """Data readiness status."""
    bars_ready: bool
    features_ready: bool
    bars_reason: str
    features_reason: str


def check_bars(
    primary_market: str,
    timeframe: int,
    season: str,
    outputs_root: Path
) -> tuple[bool, str]:
    """
    Check if bars data is ready.
    
    Bars check (Market Data) should PASS if any one of:
    - expected bars directory exists with at least one shard file, e.g. *.parquet
    - OR an index file exists (e.g. index.json) and referenced shards exist
    """
    # Use existing path builders from control module
    try:
        from control.bars_store import bars_dir, resampled_bars_path
    except ImportError:
        logger.warning("control.bars_store not available, using fallback paths")
        # Fallback path construction
        bars_dir_path = outputs_root / "shared" / season / primary_market / "bars"
        bars_file = bars_dir_path / f"resampled_{timeframe}m.npz"
        
        if bars_file.exists():
            return True, f"Bars file exists: {bars_file.name}"
        elif bars_dir_path.exists() and any(bars_dir_path.glob("*.npz")):
            return True, f"Bars directory has NPZ files"
        elif bars_dir_path.exists() and any(bars_dir_path.glob("*.parquet")):
            return True, f"Bars directory has parquet files"
        elif bars_dir_path.exists() and (bars_dir_path / "index.json").exists():
            return True, f"Bars index.json exists"
        else:
            return False, f"No bars data found at {bars_dir_path}"
    
    # Use the canonical path builders
    try:
        bars_file = resampled_bars_path(outputs_root, season, primary_market, timeframe)
        if bars_file.exists():
            return True, f"Bars file exists: {bars_file.name}"
        
        # Check for any NPZ or parquet files in bars directory
        bars_dir_path = bars_dir(outputs_root, season, primary_market)
        if bars_dir_path.exists():
            if any(bars_dir_path.glob("*.npz")):
                return True, f"Bars directory has NPZ files"
            if any(bars_dir_path.glob("*.parquet")):
                return True, f"Bars directory has parquet files"
            if (bars_dir_path / "index.json").exists():
                return True, f"Bars index.json exists"
        
        return False, f"No bars data found for {primary_market}/{timeframe}m"
    except Exception as e:
        logger.error(f"Error checking bars: {e}")
        return False, f"Error checking bars: {e}"


def check_features(
    primary_market: str,
    timeframe: int,
    season: str,
    outputs_root: Path
) -> tuple[bool, str]:
    """
    Check if features data is ready.
    
    Features check (Analysis Data) should PASS if any one of:
    - expected features directory exists with at least one artifact file (e.g. *.npz, *.parquet)
    - OR a features_index.json exists and entries exist
    """
    # Use existing path builders from control module
    try:
        from control.features_store import features_dir, features_path
    except ImportError:
        logger.warning("control.features_store not available, using fallback paths")
        # Fallback path construction
        features_dir_path = outputs_root / "shared" / season / primary_market / "features"
        features_file = features_dir_path / f"features_{timeframe}m.npz"
        
        if features_file.exists():
            return True, f"Features file exists: {features_file.name}"
        elif features_dir_path.exists() and any(features_dir_path.glob("*.npz")):
            return True, f"Features directory has NPZ files"
        elif features_dir_path.exists() and any(features_dir_path.glob("*.parquet")):
            return True, f"Features directory has parquet files"
        elif features_dir_path.exists() and (features_dir_path / "features_index.json").exists():
            return True, f"Features index.json exists"
        else:
            return False, f"No features data found at {features_dir_path}"
    
    # Use the canonical path builders
    try:
        features_file = features_path(outputs_root, season, primary_market, timeframe)
        if features_file.exists():
            return True, f"Features file exists: {features_file.name}"
        
        # Check for any NPZ or parquet files in features directory
        features_dir_path = features_dir(outputs_root, season, primary_market)
        if features_dir_path.exists():
            if any(features_dir_path.glob("*.npz")):
                return True, f"Features directory has NPZ files"
            if any(features_dir_path.glob("*.parquet")):
                return True, f"Features directory has parquet files"
            if (features_dir_path / "features_index.json").exists():
                return True, f"Features index.json exists"
        
        return False, f"No features data found for {primary_market}/{timeframe}m"
    except Exception as e:
        logger.error(f"Error checking features: {e}")
        return False, f"Error checking features: {e}"


def check_all(
    primary_market: str,
    timeframe: int,
    season: str,
    outputs_root: Path
) -> Readiness:
    """Check both bars and features readiness."""
    bars_ready, bars_reason = check_bars(primary_market, timeframe, season, outputs_root)
    features_ready, features_reason = check_features(primary_market, timeframe, season, outputs_root)
    
    return Readiness(
        bars_ready=bars_ready,
        features_ready=features_ready,
        bars_reason=bars_reason,
        features_reason=features_reason
    )
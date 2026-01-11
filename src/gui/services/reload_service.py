#!/usr/bin/env python3
"""
Reload service for file signatures, system snapshots, and UI dropdowns.
"""

# pylint: disable=no-name-in-module,c-extension-no-member

import logging
logger = logging.getLogger(__name__)

import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from config.registry.strategy_catalog import load_strategy_catalog  # pylint: disable=no-name-in-module
from config import ConfigError
from .timeframe_options import get_timeframe_id_label_pairs, get_timeframe_registry

@dataclass
class SystemSnapshot:
    """Snapshot of system state."""
    created_at: datetime
    total_datasets: int
    total_strategies: int
    notes: List[str]
    errors: List[str]


def compute_file_signature(file_path: Path) -> str:
    """Compute SHA256 signature of a file.
    
    Args:
        file_path: Path to file
        
    Returns:
        SHA256 hex digest, or empty string on error.
    """
    try:
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()
    except Exception:
        return ""


def get_system_snapshot() -> SystemSnapshot:
    """Generate a system snapshot by loading from registries.
    
    Returns:
        SystemSnapshot with current counts.
    """
    notes = ["Snapshot generated from config registries."]
    errors = []
    
    try:
        strategy_catalog = load_strategy_catalog()
        total_strategies = len(strategy_catalog.strategies)
    except ConfigError as e:
        total_strategies = 0
        errors.append(f"Failed to load strategy catalog: {e}")

    # In a real system, we would also scan datasets.
    # For now, we'll keep this as a placeholder.
    total_datasets = 0
        
    return SystemSnapshot(
        created_at=datetime.now(timezone.utc),
        total_datasets=total_datasets,
        total_strategies=total_strategies,
        notes=notes,
        errors=errors
    )

def get_available_timeframes() -> List[Tuple[int, str]]:
    """
    Get available timeframes from the registry for UI dropdowns.
    Returns a list of (value, display_name) tuples.
    """
    try:
        # Use the SSOT provider but convert back to int values for compatibility
        pairs = get_timeframe_id_label_pairs()
        # Convert string keys back to int for backward compatibility
        return [(int(value), display) for value, display in pairs]
    except Exception:
        # Fallback to registry directly
        try:
            registry = get_timeframe_registry()
            return registry.get_timeframe_choices()
        except Exception:
            logger.warning("All timeframe fallbacks failed, returning empty list")
            return []

def get_available_strategies() -> List[Tuple[str, str]]:
    """
    Get available strategies from the registry for UI dropdowns.
    Returns a list of (strategy_id, display_name) tuples.
    """
    try:
        registry = load_strategy_catalog()
        return [(s.strategy_id, s.display_name) for s in registry.strategies]
    except ConfigError:
        return [("default", "Default Strategy")]

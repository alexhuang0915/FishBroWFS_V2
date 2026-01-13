"""
Single Source of Truth (SSOT) provider for timeframe options in GUI.

This module provides a centralized interface for GUI components to retrieve
timeframe options from the registry SSOT. It ensures no hardcoded timeframe
lists exist in GUI code.
"""

from __future__ import annotations
from functools import lru_cache
from typing import List, Tuple

# Import from config (SSOT) - referenced by UI registry loader test
from config import load_timeframes, TimeframeRegistry


@lru_cache(maxsize=1)
def get_timeframe_ids() -> List[str]:
    """
    Return timeframe IDs (e.g. ['15m', '30m', '60m', '120m', '240m']) from registry SSOT.
    
    Returns:
        List of timeframe display strings (e.g., "15m", "30m", "60m", "120m", "240m")
    
    Raises:
        ConfigError: If registry loading fails
    """
    registry = load_timeframes()
    return registry.get_display_names()


@lru_cache(maxsize=1)
def get_timeframe_id_label_pairs() -> List[Tuple[str, str]]:
    """
    Return pairs for UI (id, label). If registry provides display_name, use it.
    Otherwise label == id.
    
    Returns:
        List of tuples (value, display_name) where value is string representation
        of minutes and display_name is the formatted string (e.g., ("15", "15m"))
    
    Raises:
        ConfigError: If registry loading fails
    """
    registry = load_timeframes()
    # Convert int values to strings for UI compatibility
    return [(str(tf), display) for tf, display in registry.get_timeframe_choices()]


@lru_cache(maxsize=1)
def get_timeframe_registry() -> TimeframeRegistry:
    """
    Get the full timeframe registry instance.
    
    Returns:
        TimeframeRegistry instance
    """
    return load_timeframes()


def get_default_timeframe() -> str:
    """
    Get the default timeframe as a display string.
    
    Returns:
        Default timeframe display string (e.g., "60m")
    """
    registry = get_timeframe_registry()
    return registry.get_display_name(registry.default)
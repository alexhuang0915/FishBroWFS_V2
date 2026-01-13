#!/usr/bin/env python3
"""
Reload service for file signatures, system snapshots, and UI dropdowns.
"""

# pylint: disable=no-name-in-module,c-extension-no-member

import logging
logger = logging.getLogger(__name__)


from typing import List, Tuple

# Import from src.config (SSOT) - referenced by UI registry loader test
from config.registry.strategy_catalog import load_strategy_catalog  # pylint: disable=no-name-in-module
from config import ConfigError
from .timeframe_options import get_timeframe_id_label_pairs, get_timeframe_registry









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
            return list()

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

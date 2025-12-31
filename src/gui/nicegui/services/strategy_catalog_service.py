"""Strategy catalog service for NiceGUI UI.

Provides filtered list of real strategies (S1/S2/S3 only) for the wizard and other UI components.
"""
from typing import List, Optional, Dict, Any
import logging

from control.strategy_catalog import StrategyCatalog, get_strategy_catalog
from strategy.registry import StrategySpecForGUI

logger = logging.getLogger(__name__)


class StrategyCatalogService:
    """Service for accessing strategy catalog with UI-specific filtering."""
    
    def __init__(self, catalog: Optional[StrategyCatalog] = None):
        """Initialize with optional catalog instance."""
        self._catalog = catalog or get_strategy_catalog()
        # Real strategy IDs that are baseline/no-flip ready, governance strict
        self._real_strategy_ids = {"S1", "S2", "S3"}
    
    def get_real_strategies(self) -> List[StrategySpecForGUI]:
        """Get list of real strategies (S1/S2/S3 only)."""
        all_strategies = self._catalog.list_strategies()
        real = [s for s in all_strategies if s.strategy_id in self._real_strategy_ids]
        # Ensure ordering S1, S2, S3
        real.sort(key=lambda s: s.strategy_id)
        return real
    
    def get_real_strategy_ids(self) -> List[str]:
        """Get list of real strategy IDs (S1/S2/S3 only)."""
        return sorted(self._real_strategy_ids)
    
    def get_strategy_by_id(self, strategy_id: str) -> Optional[StrategySpecForGUI]:
        """Get a real strategy by ID, returns None if not real."""
        if strategy_id not in self._real_strategy_ids:
            return None
        return self._catalog.get_strategy(strategy_id)
    
    def get_strategy_parameter_defaults(self, strategy_id: str) -> Dict[str, Any]:
        """Get default parameter values for a real strategy."""
        strategy = self.get_strategy_by_id(strategy_id)
        if strategy is None:
            return {}
        defaults = {}
        for param in strategy.params:
            if param.default is not None:
                defaults[param.name] = param.default
        return defaults
    
    def get_all_strategies_with_metadata(self) -> List[Dict[str, Any]]:
        """Get real strategies with additional metadata for UI display."""
        strategies = self.get_real_strategies()
        result = []
        for spec in strategies:
            result.append({
                "id": spec.strategy_id,
                "name": spec.name,
                "version": spec.version,
                "description": spec.description or "",
                "parameter_count": len(spec.params),
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "default": p.default,
                        "min": p.min,
                        "max": p.max,
                        "choices": p.choices,
                        "description": p.description or "",
                    }
                    for p in spec.params
                ],
                "is_long_capable": True,  # Assume all real strategies can be used long
                "is_short_capable": True,  # Assume all real strategies can be used short
            })
        return result


# Singleton instance
_strategy_catalog_service_instance: Optional[StrategyCatalogService] = None

def get_strategy_catalog_service() -> StrategyCatalogService:
    """Get singleton strategy catalog service instance."""
    global _strategy_catalog_service_instance
    if _strategy_catalog_service_instance is None:
        _strategy_catalog_service_instance = StrategyCatalogService()
    return _strategy_catalog_service_instance


# Public API functions
def list_real_strategies() -> List[StrategySpecForGUI]:
    """Public API: Get list of real strategies (S1/S2/S3 only)."""
    return get_strategy_catalog_service().get_real_strategies()

def list_real_strategy_ids() -> List[str]:
    """Public API: Get list of real strategy IDs (S1/S2/S3 only)."""
    return get_strategy_catalog_service().get_real_strategy_ids()

def get_real_strategy(strategy_id: str) -> Optional[StrategySpecForGUI]:
    """Public API: Get a real strategy by ID."""
    return get_strategy_catalog_service().get_strategy_by_id(strategy_id)
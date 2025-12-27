"""Strategy Catalog for M1 Wizard.

Provides strategy listing and parameter schema capabilities for the wizard UI.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any

from strategy.registry import (
    get_strategy_registry,
    StrategyRegistryResponse,
    StrategySpecForGUI,
    load_builtin_strategies,
    list_strategies,
    get as get_strategy_spec,
)
from strategy.param_schema import ParamSpec


class StrategyCatalog:
    """Catalog for available strategies."""
    
    def __init__(self, load_builtin: bool = True):
        """Initialize strategy catalog.
        
        Args:
            load_builtin: Whether to load built-in strategies on initialization.
        """
        self._registry_response: Optional[StrategyRegistryResponse] = None
        
        if load_builtin:
            # Ensure built-in strategies are loaded
            try:
                load_builtin_strategies()
            except Exception:
                # Already loaded or error, continue
                pass
    
    def load_registry(self) -> StrategyRegistryResponse:
        """Load strategy registry."""
        self._registry_response = get_strategy_registry()
        return self._registry_response
    
    @property
    def registry(self) -> StrategyRegistryResponse:
        """Get strategy registry (loads if not already loaded)."""
        if self._registry_response is None:
            self.load_registry()
        return self._registry_response
    
    def list_strategies(self) -> List[StrategySpecForGUI]:
        """List all available strategies for GUI."""
        return self.registry.strategies
    
    def get_strategy(self, strategy_id: str) -> Optional[StrategySpecForGUI]:
        """Get strategy by ID for GUI."""
        for strategy in self.registry.strategies:
            if strategy.strategy_id == strategy_id:
                return strategy
        return None
    
    def get_strategy_spec(self, strategy_id: str):
        """Get internal StrategySpec by ID."""
        try:
            return get_strategy_spec(strategy_id)
        except KeyError:
            return None
    
    def get_parameters(self, strategy_id: str) -> List[ParamSpec]:
        """Get parameter schema for a strategy."""
        strategy = self.get_strategy(strategy_id)
        if strategy is None:
            return []
        return strategy.params
    
    def get_parameter_defaults(self, strategy_id: str) -> Dict[str, Any]:
        """Get default parameter values for a strategy."""
        params = self.get_parameters(strategy_id)
        defaults = {}
        for param in params:
            if param.default is not None:
                defaults[param.name] = param.default
        return defaults
    
    def validate_parameters(
        self, 
        strategy_id: str, 
        parameters: Dict[str, Any]
    ) -> Dict[str, str]:
        """Validate parameter values against schema.
        
        Args:
            strategy_id: Strategy ID
            parameters: Parameter values to validate
            
        Returns:
            Dictionary of validation errors (empty if valid)
        """
        errors = {}
        params = self.get_parameters(strategy_id)
        
        # Build lookup by parameter name
        param_map = {p.name: p for p in params}
        
        for param_name, param_spec in param_map.items():
            value = parameters.get(param_name)
            
            # Check required (all parameters are required for now)
            if value is None:
                errors[param_name] = f"Parameter '{param_name}' is required"
                continue
            
            # Type validation
            if param_spec.type == "int":
                if not isinstance(value, (int, float)):
                    try:
                        int(value)
                    except (ValueError, TypeError):
                        errors[param_name] = f"Parameter '{param_name}' must be an integer"
                else:
                    # Check min/max
                    if param_spec.min is not None and value < param_spec.min:
                        errors[param_name] = f"Parameter '{param_name}' must be >= {param_spec.min}"
                    if param_spec.max is not None and value > param_spec.max:
                        errors[param_name] = f"Parameter '{param_name}' must be <= {param_spec.max}"
            
            elif param_spec.type == "float":
                if not isinstance(value, (int, float)):
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        errors[param_name] = f"Parameter '{param_name}' must be a number"
                else:
                    # Check min/max
                    if param_spec.min is not None and value < param_spec.min:
                        errors[param_name] = f"Parameter '{param_name}' must be >= {param_spec.min}"
                    if param_spec.max is not None and value > param_spec.max:
                        errors[param_name] = f"Parameter '{param_name}' must be <= {param_spec.max}"
            
            elif param_spec.type == "bool":
                if not isinstance(value, bool):
                    errors[param_name] = f"Parameter '{param_name}' must be a boolean"
            
            elif param_spec.type == "enum":
                if param_spec.choices and value not in param_spec.choices:
                    errors[param_name] = (
                        f"Parameter '{param_name}' must be one of: {', '.join(map(str, param_spec.choices))}"
                    )
        
        # Check for extra parameters not in schema
        for param_name in parameters:
            if param_name not in param_map:
                errors[param_name] = f"Unknown parameter '{param_name}' for strategy '{strategy_id}'"
        
        return errors
    
    def get_strategy_ids(self) -> List[str]:
        """Get list of all strategy IDs."""
        return [s.strategy_id for s in self.registry.strategies]
    
    def filter_by_parameter_count(self, min_params: int = 0, max_params: int = 10) -> List[StrategySpecForGUI]:
        """Filter strategies by parameter count."""
        return [
            s for s in self.registry.strategies
            if min_params <= len(s.params) <= max_params
        ]
    
    def list_strategy_ids(self) -> List[str]:
        """Get list of all strategy IDs.
        
        Returns:
            List of strategy IDs sorted alphabetically
        """
        return sorted([s.strategy_id for s in self.registry.strategies])
    
    def get_strategy_spec_public(self, strategy_id: str) -> Optional[StrategySpecForGUI]:
        """Public API: Get strategy spec by ID.
        
        Args:
            strategy_id: Strategy ID to get
            
        Returns:
            StrategySpecForGUI if found, None otherwise
        """
        return self.get_strategy(strategy_id)


# Singleton instance for easy access
_catalog_instance: Optional[StrategyCatalog] = None

def get_strategy_catalog() -> StrategyCatalog:
    """Get singleton strategy catalog instance."""
    global _catalog_instance
    if _catalog_instance is None:
        _catalog_instance = StrategyCatalog()
    return _catalog_instance


# Public API functions for registry access
def list_strategy_ids() -> List[str]:
    """Public API: Get list of all strategy IDs.
    
    Returns:
        List of strategy IDs sorted alphabetically
    """
    catalog = get_strategy_catalog()
    return catalog.list_strategy_ids()


def get_strategy_spec(strategy_id: str) -> Optional[StrategySpecForGUI]:
    """Public API: Get strategy spec by ID.
    
    Args:
        strategy_id: Strategy ID to get
        
    Returns:
        StrategySpecForGUI if found, None otherwise
    """
    catalog = get_strategy_catalog()
    return catalog.get_strategy_spec_public(strategy_id)
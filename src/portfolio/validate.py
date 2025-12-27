
"""Portfolio specification validator.

Phase 8: Validate portfolio spec against contracts.
"""

from __future__ import annotations

from pathlib import Path

from data.session.loader import load_session_profile
from portfolio.spec import PortfolioSpec
from strategy.registry import get


def validate_portfolio_spec(spec: PortfolioSpec) -> None:
    """Validate portfolio specification.
    
    Validates:
    - portfolio_id/version non-empty (already checked in PortfolioSpec.__post_init__)
    - legs non-empty; each leg_id unique (already checked in PortfolioSpec.__post_init__)
    - timeframe_min > 0 (already checked in PortfolioLeg.__post_init__)
    - session_profile path exists and can be loaded
    - strategy_id exists in registry
    - strategy_version matches registry (strict match)
    - params is dict with float values (already checked in loader)
    
    Args:
        spec: Portfolio specification to validate
        
    Raises:
        ValueError: If validation fails
        FileNotFoundError: If session profile not found
        KeyError: If strategy not found in registry
    """
    if not spec.legs:
        raise ValueError("Portfolio must have at least one leg")
    
    # Validate each leg
    for leg in spec.legs:
        # Validate session_profile path exists and can be loaded
        session_profile_path = Path(leg.session_profile)
        
        # Handle relative paths (relative to project root or current working directory)
        if not session_profile_path.is_absolute():
            # Try relative to current working directory first
            if not session_profile_path.exists():
                # Try relative to project root (if path starts with src/)
                if leg.session_profile.startswith("src/"):
                    # Path is already relative to project root
                    if not session_profile_path.exists():
                        # Try from current directory
                        pass
                else:
                    # Check configs/profiles/ location
                    configs_profile_path = Path("configs/profiles") / session_profile_path.name
                    if configs_profile_path.exists():
                        session_profile_path = configs_profile_path
        
        if not session_profile_path.exists():
            raise FileNotFoundError(
                f"Leg '{leg.leg_id}': session_profile not found: {leg.session_profile}"
            )
        
        # Try to load session profile
        try:
            load_session_profile(session_profile_path)
        except Exception as e:
            raise ValueError(
                f"Leg '{leg.leg_id}': failed to load session_profile '{leg.session_profile}': {e}"
            )
        
        # Validate strategy_id exists in registry
        try:
            strategy_spec = get(leg.strategy_id)
        except KeyError as e:
            raise KeyError(
                f"Leg '{leg.leg_id}': strategy_id '{leg.strategy_id}' not found in registry: {e}"
            )
        
        # Validate strategy_version matches (strict match)
        if strategy_spec.version != leg.strategy_version:
            raise ValueError(
                f"Leg '{leg.leg_id}': strategy_version mismatch. "
                f"Expected '{strategy_spec.version}' (from registry), got '{leg.strategy_version}'"
            )
        
        # Validate params keys exist in strategy param_schema (optional check)
        # This is a best-effort check - runner will handle defaults
        param_schema = strategy_spec.param_schema
        if isinstance(param_schema, dict) and "properties" in param_schema:
            schema_props = param_schema.get("properties", {})
            for param_key in leg.params.keys():
                if param_key not in schema_props and param_key not in strategy_spec.defaults:
                    # Warning: extra param, but allowed (runner will log warning)
                    pass



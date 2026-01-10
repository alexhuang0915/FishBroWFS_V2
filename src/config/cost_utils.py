"""
Cost Model Utilities for Config Constitution v1.

Provides clean API for retrieving cost models (commission + slippage) from
instrument symbols via the instrument registry and profile configurations.
"""

from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from functools import lru_cache

from .registry.instruments import load_instruments, InstrumentSpec
from .profiles import load_profile, ProfileConfig, CostModel


class CostModelError(Exception):
    """Error raised when cost model cannot be retrieved."""
    pass


@lru_cache(maxsize=8)
def get_instrument_spec(instrument_id: str) -> Optional[InstrumentSpec]:
    """
    Get instrument specification by ID.
    
    Args:
        instrument_id: Instrument ID (e.g., "CME.MNQ")
        
    Returns:
        InstrumentSpec if found, None otherwise
    """
    registry = load_instruments()
    return registry.get_instrument_by_id(instrument_id)


@lru_cache(maxsize=8)
def get_profile_for_instrument(instrument_id: str) -> Optional[ProfileConfig]:
    """
    Get profile configuration for an instrument.
    
    Args:
        instrument_id: Instrument ID (e.g., "CME.MNQ")
        
    Returns:
        ProfileConfig if found, None otherwise
        
    Raises:
        CostModelError: If instrument not found or profile loading fails
    """
    spec = get_instrument_spec(instrument_id)
    if not spec:
        raise CostModelError(f"Instrument {instrument_id} not found in registry")
    
    try:
        return load_profile(spec.profile)
    except Exception as e:
        raise CostModelError(f"Failed to load profile {spec.profile} for instrument {instrument_id}: {e}")


def get_cost_model_for_instrument(instrument_id: str) -> CostModel:
    """
    Get cost model for an instrument.
    
    Args:
        instrument_id: Instrument ID (e.g., "CME.MNQ")
        
    Returns:
        CostModel with commission_per_side_usd and slippage_per_side_usd
        
    Raises:
        CostModelError: If instrument not found or cost model missing
    """
    profile = get_profile_for_instrument(instrument_id)
    return profile.cost_model


def get_commission_slippage_for_instrument(instrument_id: str) -> Tuple[float, float]:
    """
    Get commission and slippage for an instrument.
    
    Args:
        instrument_id: Instrument ID (e.g., "CME.MNQ")
        
    Returns:
        Tuple of (commission_per_side_usd, slippage_per_side_usd)
        
    Raises:
        CostModelError: If instrument not found or cost model missing
    """
    cost_model = get_cost_model_for_instrument(instrument_id)
    return (cost_model.commission_per_side_usd, cost_model.slippage_per_side_usd)


def get_cost_model_dict(instrument_id: str) -> Dict[str, float]:
    """
    Get cost model as dictionary.
    
    Args:
        instrument_id: Instrument ID (e.g., "CME.MNQ")
        
    Returns:
        Dictionary with keys "commission_per_side_usd" and "slippage_per_side_usd"
    """
    commission, slippage = get_commission_slippage_for_instrument(instrument_id)
    return {
        "commission_per_side_usd": commission,
        "slippage_per_side_usd": slippage,
    }


def get_total_cost_per_trade(instrument_id: str, sides: int = 2) -> float:
    """
    Get total cost per trade (commission + slippage) for given number of sides.
    
    Args:
        instrument_id: Instrument ID (e.g., "CME.MNQ")
        sides: Number of sides (1 for one-way, 2 for round-trip)
        
    Returns:
        Total cost in USD
    """
    profile = get_profile_for_instrument(instrument_id)
    return profile.get_total_cost(sides)


def validate_all_instruments_have_cost_models() -> Dict[str, Any]:
    """
    Validate that all instruments in registry have valid cost models.
    
    Returns:
        Dictionary with validation results
    """
    registry = load_instruments()
    results = {
        "total": len(registry.instruments),
        "valid": 0,
        "invalid": 0,
        "details": {}
    }
    
    for instrument in registry.instruments:
        try:
            cost_model = get_cost_model_for_instrument(instrument.id)
            results["valid"] += 1
            results["details"][instrument.id] = {
                "status": "valid",
                "profile": instrument.profile,
                "commission_per_side_usd": cost_model.commission_per_side_usd,
                "slippage_per_side_usd": cost_model.slippage_per_side_usd,
            }
        except Exception as e:
            results["invalid"] += 1
            results["details"][instrument.id] = {
                "status": "invalid",
                "profile": instrument.profile,
                "error": str(e)
            }
    
    return results


# Convenience functions for backward compatibility
def get_commission(instrument_id: str) -> float:
    """Get commission per side for instrument (backward compatibility)."""
    commission, _ = get_commission_slippage_for_instrument(instrument_id)
    return commission


def get_slippage(instrument_id: str) -> float:
    """Get slippage per side for instrument (backward compatibility)."""
    _, slippage = get_commission_slippage_for_instrument(instrument_id)
    return slippage
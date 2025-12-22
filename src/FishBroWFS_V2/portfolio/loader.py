
"""Portfolio specification loader.

Phase 8: Load portfolio specs from YAML/JSON files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from FishBroWFS_V2.portfolio.spec import PortfolioLeg, PortfolioSpec


def load_portfolio_spec(path: Path) -> PortfolioSpec:
    """Load portfolio specification from YAML or JSON file.
    
    Args:
        path: Path to portfolio spec file (.yaml, .yml, or .json)
        
    Returns:
        PortfolioSpec loaded from file
        
    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file format is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"Portfolio spec not found: {path}")
    
    # Load based on file extension
    suffix = path.suffix.lower()
    if suffix in [".yaml", ".yml"]:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Must be .yaml, .yml, or .json")
    
    if not isinstance(data, dict):
        raise ValueError(f"Invalid portfolio format: expected dict, got {type(data)}")
    
    # Extract fields
    portfolio_id = data.get("portfolio_id")
    version = data.get("version")
    data_tz = data.get("data_tz", "Asia/Taipei")
    legs_data = data.get("legs", [])
    
    if not portfolio_id:
        raise ValueError("Portfolio spec missing 'portfolio_id' field")
    if not version:
        raise ValueError("Portfolio spec missing 'version' field")
    
    # Load legs
    legs = []
    for leg_data in legs_data:
        if not isinstance(leg_data, dict):
            raise ValueError(f"Leg must be dict, got {type(leg_data)}")
        
        leg_id = leg_data.get("leg_id")
        symbol = leg_data.get("symbol")
        timeframe_min = leg_data.get("timeframe_min")
        session_profile = leg_data.get("session_profile")
        strategy_id = leg_data.get("strategy_id")
        strategy_version = leg_data.get("strategy_version")
        params = leg_data.get("params", {})
        enabled = leg_data.get("enabled", True)
        tags = leg_data.get("tags", [])
        
        # Validate required fields
        if not leg_id:
            raise ValueError("Leg missing 'leg_id' field")
        if not symbol:
            raise ValueError(f"Leg '{leg_id}' missing 'symbol' field")
        if timeframe_min is None:
            raise ValueError(f"Leg '{leg_id}' missing 'timeframe_min' field")
        if not session_profile:
            raise ValueError(f"Leg '{leg_id}' missing 'session_profile' field")
        if not strategy_id:
            raise ValueError(f"Leg '{leg_id}' missing 'strategy_id' field")
        if not strategy_version:
            raise ValueError(f"Leg '{leg_id}' missing 'strategy_version' field")
        
        # Convert params values to float
        if not isinstance(params, dict):
            raise ValueError(f"Leg '{leg_id}' params must be dict, got {type(params)}")
        
        params_float = {}
        for key, value in params.items():
            try:
                params_float[key] = float(value)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Leg '{leg_id}' param '{key}' must be numeric, got {type(value)}: {e}"
                )
        
        # Convert tags to list
        if not isinstance(tags, list):
            raise ValueError(f"Leg '{leg_id}' tags must be list, got {type(tags)}")
        
        leg = PortfolioLeg(
            leg_id=leg_id,
            symbol=symbol,
            timeframe_min=int(timeframe_min),
            session_profile=session_profile,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            params=params_float,
            enabled=bool(enabled),
            tags=list(tags),
        )
        legs.append(leg)
    
    return PortfolioSpec(
        portfolio_id=portfolio_id,
        version=version,
        data_tz=data_tz,
        legs=legs,
    )



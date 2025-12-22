
"""Winners builder - converts legacy winners to v2 schema.

Builds v2 winners.json from legacy topk format with fallback strategies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from FishBroWFS_V2.core.winners_schema import WinnerItemV2, build_winners_v2_dict


def build_winners_v2(
    *,
    stage_name: str,
    run_id: str,
    manifest: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    legacy_topk: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build winners.json v2 from legacy topk format.
    
    Args:
        stage_name: Stage identifier
        run_id: Run ID
        manifest: Manifest dict (AuditSchema)
        config_snapshot: Config snapshot dict
        legacy_topk: Legacy topk list (old format items)
        
    Returns:
        Winners dict with v2 schema
    """
    # Extract strategy_id
    strategy_id = _extract_strategy_id(config_snapshot, manifest)
    
    # Extract symbol/timeframe
    symbol = _extract_symbol(config_snapshot)
    timeframe = _extract_timeframe(config_snapshot)
    
    # Build v2 items
    v2_items: List[WinnerItemV2] = []
    
    for legacy_item in legacy_topk:
        # Extract param_id (required for candidate_id generation)
        param_id = legacy_item.get("param_id")
        if param_id is None:
            # Skip items without param_id (should not happen, but be defensive)
            continue
        
        # Generate candidate_id (temporary: strategy_id:param_id)
        # Future: upgrade to strategy_id:params_hash[:12] when params are available
        candidate_id = f"{strategy_id}:{param_id}"
        
        # Extract params (fallback to empty dict)
        params = _extract_params(legacy_item, config_snapshot, param_id)
        
        # Extract score (priority: score/finalscore > net_profit > 0.0)
        score = _extract_score(legacy_item)
        
        # Build metrics (must include legacy fields for backward compatibility)
        metrics = {
            "net_profit": float(legacy_item.get("net_profit", 0.0)),
            "max_dd": float(legacy_item.get("max_dd", 0.0)),
            "trades": int(legacy_item.get("trades", 0)),
            "param_id": int(param_id),  # Keep for backward compatibility
        }
        
        # Add proxy_value if present (Stage0)
        if "proxy_value" in legacy_item:
            metrics["proxy_value"] = float(legacy_item["proxy_value"])
        
        # Build source metadata
        source = {
            "param_id": int(param_id),
            "run_id": run_id,
            "stage_name": stage_name,
        }
        
        # Create v2 item
        v2_item = WinnerItemV2(
            candidate_id=candidate_id,
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            params=params,
            score=score,
            metrics=metrics,
            source=source,
        )
        
        v2_items.append(v2_item)
    
    # Build notes with candidate_id_mode info
    notes = {
        "candidate_id_mode": "strategy_id:param_id",  # Temporary mode
        "note": "candidate_id uses param_id temporarily; will upgrade to params_hash when params are available",
    }
    
    # Build v2 winners dict
    return build_winners_v2_dict(
        stage_name=stage_name,
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        topk=v2_items,
        notes=notes,
    )


def _extract_strategy_id(config_snapshot: Dict[str, Any], manifest: Dict[str, Any]) -> str:
    """
    Extract strategy_id from config_snapshot or manifest.
    
    Priority:
    1. config_snapshot.get("strategy_id")
    2. manifest.get("dataset_id") (fallback)
    3. "unknown" (final fallback)
    """
    if "strategy_id" in config_snapshot:
        return str(config_snapshot["strategy_id"])
    
    dataset_id = manifest.get("dataset_id")
    if dataset_id:
        return str(dataset_id)
    
    return "unknown"


def _extract_symbol(config_snapshot: Dict[str, Any]) -> str:
    """
    Extract symbol from config_snapshot.
    
    Returns "UNKNOWN" if not available.
    """
    return str(config_snapshot.get("symbol", "UNKNOWN"))


def _extract_timeframe(config_snapshot: Dict[str, Any]) -> str:
    """
    Extract timeframe from config_snapshot.
    
    Returns "UNKNOWN" if not available.
    """
    return str(config_snapshot.get("timeframe", "UNKNOWN"))


def _extract_params(
    legacy_item: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    param_id: int,
) -> Dict[str, Any]:
    """
    Extract params from legacy_item or config_snapshot.
    
    Priority:
    1. legacy_item.get("params")
    2. config_snapshot.get("params_by_id", {}).get(param_id)
    3. config_snapshot.get("params_spec") (if available)
    4. {} (empty dict fallback)
    
    Returns empty dict {} if params are not available.
    """
    # Try legacy_item first
    if "params" in legacy_item:
        params = legacy_item["params"]
        if isinstance(params, dict):
            return params
    
    # Try config_snapshot params_by_id
    params_by_id = config_snapshot.get("params_by_id", {})
    if isinstance(params_by_id, dict) and param_id in params_by_id:
        params = params_by_id[param_id]
        if isinstance(params, dict):
            return params
    
    # Try config_snapshot params_spec (if available)
    params_spec = config_snapshot.get("params_spec")
    if isinstance(params_spec, dict):
        # Could extract from params_spec if it has param_id mapping
        # For now, return empty dict
        pass
    
    # Fallback: empty dict
    return {}


def _extract_score(legacy_item: Dict[str, Any]) -> float:
    """
    Extract score from legacy_item.
    
    Priority:
    1. legacy_item.get("score")
    2. legacy_item.get("finalscore")
    3. legacy_item.get("net_profit")
    4. legacy_item.get("proxy_value") (for Stage0)
    5. 0.0 (fallback)
    """
    if "score" in legacy_item:
        val = legacy_item["score"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "finalscore" in legacy_item:
        val = legacy_item["finalscore"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "net_profit" in legacy_item:
        val = legacy_item["net_profit"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "proxy_value" in legacy_item:
        val = legacy_item["proxy_value"]
        if isinstance(val, (int, float)):
            return float(val)
    
    return 0.0



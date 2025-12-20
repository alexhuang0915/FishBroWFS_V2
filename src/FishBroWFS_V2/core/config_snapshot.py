"""Config snapshot sanitizer.

Creates JSON-serializable config snapshots by excluding large ndarrays
and converting numpy types to Python native types.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

# These keys will make artifacts garbage or directly crash JSON serialization
_DEFAULT_DROP_KEYS = {
    "open_",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "params_matrix",
}


def _ndarray_meta(x: np.ndarray) -> Dict[str, Any]:
    """
    Create metadata dict for ndarray (shape and dtype only).
    
    Args:
        x: numpy array
        
    Returns:
        Metadata dictionary with shape and dtype
    """
    return {
        "__ndarray__": True,
        "shape": list(x.shape),
        "dtype": str(x.dtype),
    }


def make_config_snapshot(
    cfg: Dict[str, Any],
    drop_keys: set[str] | None = None,
) -> Dict[str, Any]:
    """
    Create sanitized config snapshot for JSON serialization and hashing.
    
    Rules (locked):
    - Must include: season, dataset_id, bars, params_total, param_subsample_rate,
      stage_name, topk, commission, slip, order_qty, config knobs...
    - Must exclude/replace: open_, high, low, close, params_matrix (ndarrays)
    - If metadata needed, only keep shape/dtype (no bytes hash to avoid cost)
    
    Args:
        cfg: Configuration dictionary (may contain ndarrays)
        drop_keys: Optional set of keys to drop. If None, uses default.
        
    Returns:
        Sanitized config dictionary (JSON-serializable)
    """
    drop = _DEFAULT_DROP_KEYS if drop_keys is None else drop_keys
    out: Dict[str, Any] = {}
    
    for k, v in cfg.items():
        if k in drop:
            # Don't keep raw data, only metadata (optional)
            if isinstance(v, np.ndarray):
                out[k + "_meta"] = _ndarray_meta(v)
            continue
        
        # numpy scalar -> python scalar
        if isinstance(v, (np.floating, np.integer)):
            out[k] = v.item()
        # ndarray (if slipped through) -> meta
        elif isinstance(v, np.ndarray):
            out[k + "_meta"] = _ndarray_meta(v)
        # Basic types: keep as-is
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        # list/tuple: conservative handling (avoid strange objects)
        elif isinstance(v, (list, tuple)):
            # Check if list contains only serializable types
            try:
                # Try to serialize to verify
                import json
                json.dumps(v)
                out[k] = v
            except (TypeError, ValueError):
                # If not serializable, convert to string representation
                out[k] = str(v)
        # Other types: convert to string (avoid JSON crash)
        else:
            out[k] = str(v)
    
    return out

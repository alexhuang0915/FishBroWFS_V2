"""Portfolio artifacts writer.

Phase 8: Write portfolio artifacts for replayability and audit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from FishBroWFS_V2.portfolio.spec import PortfolioSpec


def _normalize_spec_for_hash(spec: PortfolioSpec) -> Dict[str, Any]:
    """Normalize spec to dict for hashing (exclude runtime-dependent fields).
    
    Excludes:
    - Absolute paths (convert to relative or normalize)
    - Timestamps
    - Runtime-dependent fields
    
    Args:
        spec: Portfolio specification
        
    Returns:
        Normalized dict suitable for hashing
    """
    legs_dict = []
    for leg in spec.legs:
        # Normalize session_profile path (use relative path, not absolute)
        session_profile = leg.session_profile
        # Remove any absolute path components, keep relative structure
        if Path(session_profile).is_absolute():
            # Try to make relative to common base
            try:
                session_profile = str(Path(session_profile).relative_to(Path.cwd()))
            except ValueError:
                # If can't make relative, use basename as fallback
                session_profile = Path(session_profile).name
        
        leg_dict = {
            "leg_id": leg.leg_id,
            "symbol": leg.symbol,
            "timeframe_min": leg.timeframe_min,
            "session_profile": session_profile,  # Normalized path
            "strategy_id": leg.strategy_id,
            "strategy_version": leg.strategy_version,
            "params": dict(sorted(leg.params.items())),  # Sort for determinism
            "enabled": leg.enabled,
            "tags": sorted(leg.tags),  # Sort for determinism
        }
        legs_dict.append(leg_dict)
    
    # Sort legs by leg_id for determinism
    legs_dict.sort(key=lambda x: x["leg_id"])
    
    return {
        "portfolio_id": spec.portfolio_id,
        "version": spec.version,
        "data_tz": spec.data_tz,
        "legs": legs_dict,
    }


def compute_portfolio_hash(spec: PortfolioSpec) -> str:
    """Compute deterministic hash of portfolio specification.
    
    Uses SHA1 (consistent with Phase 6.5 fingerprint style).
    Hash is computed from normalized spec dict (sorted keys, stable serialization).
    
    Args:
        spec: Portfolio specification
        
    Returns:
        SHA1 hash hex string (40 chars)
    """
    normalized = _normalize_spec_for_hash(spec)
    
    # Stable JSON serialization
    spec_json = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),  # Compact, no spaces
        ensure_ascii=False,
    )
    
    # SHA1 hash
    return hashlib.sha1(spec_json.encode("utf-8")).hexdigest()


def write_portfolio_artifacts(
    spec: PortfolioSpec,
    jobs: List[Dict[str, Any]],
    out_dir: Path,
) -> Dict[str, str]:
    """Write portfolio artifacts to output directory.
    
    Creates:
    - portfolio_spec_snapshot.yaml: Portfolio spec snapshot
    - compiled_jobs.json: Compiled job configurations
    - portfolio_index.json: Portfolio index with metadata
    - portfolio_hash.txt: Portfolio hash (single line)
    
    Args:
        spec: Portfolio specification
        jobs: Compiled job configurations (from compile_portfolio)
        out_dir: Output directory (will be created if needed)
        
    Returns:
        Dict mapping artifact names to file paths (relative to out_dir)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Compute hash
    portfolio_hash = compute_portfolio_hash(spec)
    
    # Write portfolio_spec_snapshot.yaml
    spec_snapshot_path = out_dir / "portfolio_spec_snapshot.yaml"
    normalized_spec = _normalize_spec_for_hash(spec)
    with spec_snapshot_path.open("w", encoding="utf-8") as f:
        yaml.dump(normalized_spec, f, default_flow_style=False, sort_keys=True)
    
    # Write compiled_jobs.json
    jobs_path = out_dir / "compiled_jobs.json"
    with jobs_path.open("w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, sort_keys=True, ensure_ascii=False)
    
    # Write portfolio_index.json
    index = {
        "portfolio_id": spec.portfolio_id,
        "version": spec.version,
        "portfolio_hash": portfolio_hash,
        "legs": [
            {
                "leg_id": leg.leg_id,
                "symbol": leg.symbol,
                "timeframe_min": leg.timeframe_min,
                "strategy_id": leg.strategy_id,
                "strategy_version": leg.strategy_version,
            }
            for leg in spec.legs
        ],
    }
    index_path = out_dir / "portfolio_index.json"
    with index_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, sort_keys=True, ensure_ascii=False)
    
    # Write portfolio_hash.txt (single line)
    hash_path = out_dir / "portfolio_hash.txt"
    hash_path.write_text(portfolio_hash + "\n", encoding="utf-8")
    
    # Return artifact paths (relative to out_dir)
    return {
        "spec_snapshot": str(spec_snapshot_path.relative_to(out_dir)),
        "compiled_jobs": str(jobs_path.relative_to(out_dir)),
        "index": str(index_path.relative_to(out_dir)),
        "hash": str(hash_path.relative_to(out_dir)),
    }

"""Portfolio artifacts writer V1."""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

from FishBroWFS_V2.core.schemas.portfolio_v1 import (
    AdmissionDecisionV1,
    PortfolioStateV1,
    PortfolioSummaryV1,
    PortfolioPolicyV1,
    PortfolioSpecV1,
)
from FishBroWFS_V2.control.artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    write_json_atomic,
)


def write_portfolio_artifacts(
    output_dir: Path,
    decisions: List[AdmissionDecisionV1],
    bar_states: Dict[Any, PortfolioStateV1],
    summary: PortfolioSummaryV1,
    policy: PortfolioPolicyV1,
    spec: PortfolioSpecV1,
    replay_mode: bool = False,
) -> Dict[str, str]:
    """
    Write portfolio artifacts to disk.
    
    Args:
        output_dir: Directory to write artifacts
        decisions: List of admission decisions
        bar_states: Dict mapping (bar_index, bar_ts) to PortfolioStateV1
        summary: Portfolio summary
        policy: Portfolio policy
        spec: Portfolio specification
        replay_mode: If True, read-only mode (no writes)
        
    Returns:
        Dict mapping filename to SHA256 hash
    """
    if replay_mode:
        logger.info("Replay mode: skipping artifact writes")
        return {}
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    hashes = {}
    
    # 1. Write portfolio_admission.parquet
    if decisions:
        admission_df = pd.DataFrame([d.dict() for d in decisions])
        admission_path = output_dir / "portfolio_admission.parquet"
        admission_df.to_parquet(admission_path, index=False)
        
        # Compute hash
        admission_bytes = admission_path.read_bytes()
        hashes["portfolio_admission.parquet"] = sha256_bytes(admission_bytes)
    
    # 2. Write portfolio_state_timeseries.parquet
    if bar_states:
        # Convert bar_states to list of dicts
        states_list = []
        for state in bar_states.values():
            state_dict = state.dict()
            # Convert open_positions to count for simplicity
            state_dict["open_positions_count"] = len(state.open_positions)
            # Remove the actual positions to keep file size manageable
            state_dict.pop("open_positions", None)
            states_list.append(state_dict)
        
        states_df = pd.DataFrame(states_list)
        states_path = output_dir / "portfolio_state_timeseries.parquet"
        states_df.to_parquet(states_path, index=False)
        
        states_bytes = states_path.read_bytes()
        hashes["portfolio_state_timeseries.parquet"] = sha256_bytes(states_bytes)
    
    # 3. Write portfolio_summary.json
    summary_dict = summary.dict()
    summary_path = output_dir / "portfolio_summary.json"
    write_json_atomic(summary_path, summary_dict)
    
    summary_bytes = canonical_json_bytes(summary_dict)
    hashes["portfolio_summary.json"] = sha256_bytes(summary_bytes)
    
    # 4. Write policy and spec for audit
    policy_dict = policy.dict()
    policy_path = output_dir / "portfolio_policy.json"
    write_json_atomic(policy_path, policy_dict)
    
    spec_dict = spec.dict()
    spec_path = output_dir / "portfolio_spec.json"
    write_json_atomic(spec_path, spec_dict)
    
    # 5. Create manifest
    manifest = {
        "version": "PORTFOLIO_MANIFEST_V1",
        "created_at": pd.Timestamp.now().isoformat(),
        "policy_sha256": sha256_bytes(canonical_json_bytes(policy_dict)),
        "spec_sha256": spec.spec_sha256 if hasattr(spec, "spec_sha256") else "",
        "artifacts": [
            {
                "path": path,
                "sha256": hash_val,
                "type": "parquet" if path.endswith(".parquet") else "json",
            }
            for path, hash_val in hashes.items()
        ],
        "summary": {
            "total_candidates": summary.total_candidates,
            "accepted_count": summary.accepted_count,
            "rejected_count": summary.rejected_count,
            "final_slots_used": summary.final_slots_used,
            "final_margin_ratio": summary.final_margin_ratio,
        },
    }
    
    # Compute manifest hash (excluding the hash field itself)
    manifest_without_hash = manifest.copy()
    manifest_without_hash.pop("manifest_hash", None)
    manifest_hash = sha256_bytes(canonical_json_bytes(manifest_without_hash))
    manifest["manifest_hash"] = manifest_hash
    
    # Write manifest
    manifest_path = output_dir / "portfolio_manifest.json"
    write_json_atomic(manifest_path, manifest)
    
    hashes["portfolio_manifest.json"] = manifest_hash
    
    logger.info(f"Portfolio artifacts written to {output_dir}")
    logger.info(f"Artifacts: {list(hashes.keys())}")
    
    return hashes


def compute_spec_sha256(spec: PortfolioSpecV1) -> str:
    """
    Compute SHA256 hash of canonicalized portfolio spec.
    
    Args:
        spec: Portfolio specification
        
    Returns:
        SHA256 hex digest
    """
    # Create dict without spec_sha256 field
    spec_dict = spec.dict()
    spec_dict.pop("spec_sha256", None)
    
    # Canonicalize and hash
    canonical = canonical_json_bytes(spec_dict)
    return sha256_bytes(canonical)


def compute_policy_sha256(policy: PortfolioPolicyV1) -> str:
    """
    Compute SHA256 hash of canonicalized portfolio policy.
    
    Args:
        policy: Portfolio policy
        
    Returns:
        SHA256 hex digest
    """
    policy_dict = policy.dict()
    canonical = canonical_json_bytes(policy_dict)
    return sha256_bytes(canonical)


# Setup logging
import logging
logger = logging.getLogger(__name__)
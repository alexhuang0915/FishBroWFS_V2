"""Portfolio runner - compile and write portfolio artifacts.

Phase 8: Load, validate, compile, and write portfolio artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from FishBroWFS_V2.portfolio.artifacts import write_portfolio_artifacts
from FishBroWFS_V2.portfolio.compiler import compile_portfolio
from FishBroWFS_V2.portfolio.loader import load_portfolio_spec
from FishBroWFS_V2.portfolio.validate import validate_portfolio_spec


def run_portfolio(spec_path: Path, outputs_root: Path) -> Dict[str, Any]:
    """Run portfolio compilation pipeline.
    
    Process:
    1. Load portfolio spec
    2. Validate spec
    3. Compile jobs
    4. Write portfolio artifacts
    
    Args:
        spec_path: Path to portfolio spec file
        outputs_root: Root outputs directory
        
    Returns:
        Dict with:
            - portfolio_id: Portfolio ID
            - portfolio_version: Portfolio version
            - portfolio_hash: Portfolio hash
            - artifacts: Dict mapping artifact names to relative paths
            - artifacts_dir: Absolute path to artifacts directory
    """
    # Load spec
    spec = load_portfolio_spec(spec_path)
    
    # Validate spec
    validate_portfolio_spec(spec)
    
    # Compile jobs
    jobs = compile_portfolio(spec)
    
    # Determine artifacts directory
    # Format: outputs_root/portfolios/{portfolio_id}/{version}/
    artifacts_dir = outputs_root / "portfolios" / spec.portfolio_id / spec.version
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Write artifacts
    artifact_paths = write_portfolio_artifacts(spec, jobs, artifacts_dir)
    
    # Compute hash
    from FishBroWFS_V2.portfolio.artifacts import compute_portfolio_hash
    portfolio_hash = compute_portfolio_hash(spec)
    
    return {
        "portfolio_id": spec.portfolio_id,
        "portfolio_version": spec.version,
        "portfolio_hash": portfolio_hash,
        "artifacts": artifact_paths,
        "artifacts_dir": str(artifacts_dir),
        "jobs_count": len(jobs),
    }

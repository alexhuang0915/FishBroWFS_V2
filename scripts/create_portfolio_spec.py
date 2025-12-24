#!/usr/bin/env python3
"""Create a portfolio spec for testing."""

import json
import hashlib
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from FishBroWFS_V2.core.schemas.portfolio_v1 import PortfolioPolicyV1, PortfolioSpecV1
from FishBroWFS_V2.portfolio.artifacts_writer_v1 import compute_policy_sha256, compute_spec_sha256
from FishBroWFS_V2.portfolio.instruments import load_instruments_config

def create_policy() -> PortfolioPolicyV1:
    """Create a test portfolio policy."""
    # Load instruments config to get SHA256
    instruments_cfg = load_instruments_config(Path("configs/portfolio/instruments.yaml"))
    
    return PortfolioPolicyV1(
        version="PORTFOLIO_POLICY_V1",
        base_currency="TWD",
        instruments_config_sha256=instruments_cfg.sha256,
        max_slots_total=4,
        max_margin_ratio=0.35,  # 35%
        max_notional_ratio=None,
        max_slots_by_instrument={
            "CME.MNQ": 2,
            "TWF.MXF": 2,
        },
        strategy_priority={
            "sma_cross": 10,
            "mean_revert_zscore": 20,
        },
        signal_strength_field="signal_strength",
        allow_force_kill=False,
        allow_queue=False,
    )

def create_spec(policy_sha256: str) -> PortfolioSpecV1:
    """Create a test portfolio spec."""
    spec = PortfolioSpecV1(
        version="PORTFOLIO_SPEC_V1",
        seasons=["2026Q1"],
        strategy_ids=["sma_cross", "mean_revert_zscore"],
        instrument_ids=["CME.MNQ", "TWF.MXF"],
        start_date=None,
        end_date=None,
        policy_sha256=policy_sha256,
        spec_sha256="",  # Will be computed
    )
    
    # Compute spec SHA256
    spec_sha256 = compute_spec_sha256(spec)
    spec.spec_sha256 = spec_sha256
    
    return spec

def main():
    """Create and save portfolio spec and policy."""
    # Create policy
    policy = create_policy()
    policy_sha256 = compute_policy_sha256(policy)
    
    print(f"Policy SHA256: {policy_sha256}")
    
    # Create spec
    spec = create_spec(policy_sha256)
    
    print(f"Spec SHA256: {spec.spec_sha256}")
    
    # Save policy
    policy_dict = policy.dict()
    policy_path = Path("configs/portfolio/portfolio_policy_v1.json")
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(policy_dict, indent=2), encoding="utf-8")
    print(f"Saved policy to: {policy_path}")
    
    # Save spec
    spec_dict = spec.dict()
    spec_path = Path("configs/portfolio/portfolio_spec_v1.json")
    spec_path.write_text(json.dumps(spec_dict, indent=2), encoding="utf-8")
    print(f"Saved spec to: {spec_path}")
    
    # Also save as YAML for easier reading
    import yaml
    spec_yaml_path = Path("configs/portfolio/portfolio_spec_v1.yaml")
    spec_yaml_path.write_text(yaml.dump(spec_dict, default_flow_style=False), encoding="utf-8")
    print(f"Saved spec (YAML) to: {spec_yaml_path}")
    
    print("\nTo validate:")
    print(f"  python -m FishBroWFS_V2.portfolio.cli validate --spec {spec_path} --outputs-root outputs")
    
    print("\nTo run:")
    print(f"  python -m FishBroWFS_V2.portfolio.cli run --spec {spec_path} --equity 1000000 --outputs-root outputs")

if __name__ == "__main__":
    main()
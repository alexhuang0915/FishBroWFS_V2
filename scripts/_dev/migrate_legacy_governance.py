"""
One-time migration script to convert legacy governance_params.json to YAML.
"""

from pathlib import Path
from typing import Optional

import json
import yaml

from src.config.portfolio import PortfolioConfig, load_portfolio_config, get_portfolio_path


def migrate_governance_params_json_to_yaml(
    json_path: Path,
    yaml_path: Optional[Path] = None
) -> PortfolioConfig:
    """
    Migrate legacy governance_params.json to YAML format.

    Args:
        json_path: Path to legacy governance_params.json
        yaml_path: Optional path for output YAML file.
                   Defaults to configs/portfolio/governance.yaml

    Returns:
        PortfolioConfig instance created from migrated data
    """
    if yaml_path is None:
        yaml_path = get_portfolio_path("governance.yaml")

    # Load legacy JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        legacy_data = json.load(f)

    # Transform to new schema
    migrated_data = {
        "version": "2.0",
        "risk_model": legacy_data.get("risk_model", "vol_target"),
        "allowed_risk_models": legacy_data.get("allowed_risk_models", ["vol_target", "risk_parity"]),
        "bucket_slots": legacy_data.get("bucket_slots", {}),
        "correlation_policy": {
            "method": "pearson",
            "member_hard_limit": legacy_data.get("corr_member_hard_limit", 0.8),
            "portfolio_hard_limit": legacy_data.get("corr_portfolio_hard_limit", 0.7),
            "max_pairwise_correlation": legacy_data.get("max_pairwise_correlation", 0.6),
            "rolling_days": legacy_data.get("corr_rolling_days", 30),
            "min_samples": legacy_data.get("corr_min_samples", 20),
        },
        "drawdown_policy": {
            "portfolio_dd_cap": legacy_data.get("portfolio_dd_cap", 0.2),
            "dd_absolute_cap": legacy_data.get("dd_absolute_cap", 0.35),
            "dd_k_multiplier": legacy_data.get("dd_k_multiplier", 1.0),
        },
        "risk_budget_policy": {
            "portfolio_risk_budget_max": legacy_data.get("portfolio_risk_budget_max", 1.0),
            "portfolio_vol_target": legacy_data.get("portfolio_vol_target", 0.1),
            "vol_floor": legacy_data.get("vol_floor", 0.02),
            "w_max": legacy_data.get("w_max", 0.35),
            "w_min": legacy_data.get("w_min", 0.0),
        },
        "breaker_policy": {
            "exposure_reduction_on_breaker": legacy_data.get("exposure_reduction_on_breaker", 0.5),
        },
        "notes": "Migrated from legacy governance_params.json",
    }

    # Convert bucket_slots dict to list of BucketSlot objects
    bucket_slots = {}
    for bucket_name, slots in migrated_data["bucket_slots"].items():
        bucket_slots[bucket_name] = {"bucket_name": bucket_name, "slots": slots}
    migrated_data["bucket_slots"] = bucket_slots

    # Write YAML
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(migrated_data, f, default_flow_style=False, sort_keys=False)

    # Load and return the migrated config
    return load_portfolio_config(path=yaml_path)


if __name__ == '__main__':
    # Example usage:
    # python scripts/_dev/migrate_legacy_governance.py path/to/governance_params.json
    import sys
    if len(sys.argv) != 2:
        print("Usage: python scripts/_dev/migrate_legacy_governance.py <path_to_governance_params.json>")
        sys.exit(1)

    json_file = Path(sys.argv[1])
    if not json_file.exists():
        print(f"Error: {json_file} not found.")
        sys.exit(1)

    print(f"Migrating {json_file}...")
    migrated_config = migrate_governance_params_json_to_yaml(json_file)
    print("Migration successful. New config:")
    print(migrated_config.model_dump_json(indent=2))

#!/usr/bin/env python3
"""
Baseline Experiment Runner CLI Wrapper

Unified runner command for baseline experiments with S1/S2/S3 strategies.
Loads baseline YAML config from configs/strategies/{strategy}/baseline.yaml,
validates config fields and feature availability in shared cache,
executes research run using existing research_runner entrypoints.

Usage:
    python scripts/run_baseline.py --strategy S1 [--season 2026Q1] [--dataset CME.MNQ] [--tf 60] [--allow-build]

Exit codes:
    0 - Success
    1 - CLI argument error
    2 - Config loading/validation error
    3 - Feature cache verification error
    4 - Research runner error
"""

import argparse
import sys
import yaml
import numpy as np
from pathlib import Path
from typing import Dict, Any, List

# Ensure src importable even when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from control.research_runner import run_research, ResearchRunError
from control.features_store import load_features_npz
from control.shared_build import load_shared_manifest
from strategy.registry import load_builtin_strategies
from contracts.strategy_features import (
    StrategyFeatureRequirements,
    FeatureRef,
    save_requirements_to_json,
    load_requirements_from_json,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run baseline experiment for a strategy",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--season",
        type=str,
        default="2026Q1",
        help="Season identifier (e.g., 2026Q1)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="CME.MNQ",
        help="Dataset ID (e.g., CME.MNQ)",
    )
    parser.add_argument(
        "--tf",
        type=int,
        default=60,
        help="Timeframe in minutes",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        choices=["S1", "S2", "S3"],
        help="Strategy ID (S1, S2, or S3)",
    )
    parser.add_argument(
        "--allow-build",
        action="store_true",
        default=False,
        help="Allow building missing features (default: False)",
    )
    return parser.parse_args()


def load_baseline_config(strategy: str) -> Dict[str, Any]:
    """
    Load baseline YAML config from configs/strategies/{strategy}/baseline.yaml.
    
    Args:
        strategy: Strategy ID (S1, S2, S3)
    
    Returns:
        Parsed YAML config as dictionary
    
    Raises:
        FileNotFoundError: Config file not found
        yaml.YAMLError: Invalid YAML format
        ValueError: Missing required fields
    """
    config_path = Path("configs/strategies") / strategy / "baseline.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Baseline config not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # Validate required fields
    required_fields = ["version", "strategy_id", "dataset_id", "timeframe", "features", "params"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required field '{field}' in baseline config")
    
    # Validate features structure
    if "required" not in config["features"]:
        raise ValueError("Missing 'features.required' list in baseline config")
    
    # Ensure strategy_id matches CLI argument
    if config["strategy_id"] != strategy:
        raise ValueError(
            f"Config strategy_id mismatch: expected '{strategy}', got '{config['strategy_id']}'"
        )
    
    return config


def ensure_builtin_strategies_loaded() -> None:
    """Ensure built-in strategies are loaded (idempotent).
    
    This function can be called multiple times without crashing.
    """
    try:
        load_builtin_strategies()
    except ValueError as e:
        # registry is process-local; re-entry may raise duplicate register
        if "already registered" not in str(e):
            raise


def ensure_feature_requirements(strategy: str, config: Dict[str, Any]) -> None:
    """
    Ensure feature requirements JSON exists for the strategy.

    If the JSON file does not exist in outputs/strategies/{strategy}/features.json,
    create it using the baseline config's features list.

    Args:
        strategy: Strategy ID
        config: Baseline config dictionary
    """
    # Check if JSON already exists in outputs/strategies
    outputs_json_path = Path("outputs") / "strategies" / strategy / "features.json"
    if outputs_json_path.exists():
        return

    # Also check configs/strategies (if exists, we can skip)
    configs_json_path = Path("configs/strategies") / strategy / "features.json"
    if configs_json_path.exists():
        return

    # Create outputs directory
    outputs_json_path.parent.mkdir(parents=True, exist_ok=True)

    # Build feature requirements from config with resolved concrete names
    required_features = config["features"]["required"]
    optional_features = config["features"].get("optional", [])
    params = config.get("params", {})

    # Mapping of placeholder to param key
    placeholder_map = {
        "context_feature": "context_feature_name",
        "value_feature": "value_feature_name",
        "filter_feature": "filter_feature_name",
    }

    # Convert to FeatureRef objects with concrete names
    required_refs = []
    for feat in required_features:
        placeholder = feat["name"]
        timeframe = feat.get("timeframe_min", 60)
        
        if placeholder in placeholder_map:
            param_key = placeholder_map[placeholder]
            concrete_name = params.get(param_key, "")
            if concrete_name:
                required_refs.append(FeatureRef(
                    name=concrete_name,
                    timeframe_min=timeframe,
                ))
            else:
                # If param is empty, skip (should not happen for required features)
                continue
        else:
            # Already concrete name (e.g., S1 features)
            required_refs.append(FeatureRef(
                name=placeholder,
                timeframe_min=timeframe,
            ))

    optional_refs = []
    for feat in optional_features:
        placeholder = feat["name"]
        timeframe = feat.get("timeframe_min", 60)
        
        if placeholder in placeholder_map:
            param_key = placeholder_map[placeholder]
            concrete_name = params.get(param_key, "")
            if concrete_name:
                optional_refs.append(FeatureRef(
                    name=concrete_name,
                    timeframe_min=timeframe,
                ))
            # If empty, skip (optional feature not used)
        else:
            # Already concrete name
            optional_refs.append(FeatureRef(
                name=placeholder,
                timeframe_min=timeframe,
            ))

    req = StrategyFeatureRequirements(
        strategy_id=strategy,
        required=required_refs,
        optional=optional_refs,
        min_schema_version="v1",
        notes=f"Auto-generated from baseline config for {strategy}",
    )

    # Save JSON
    save_requirements_to_json(req, str(outputs_json_path))
    print(f"Created feature requirements JSON at {outputs_json_path}")


def resolve_feature_names(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Resolve placeholder feature names to concrete feature names using params.
    
    For S2/S3, the config may contain placeholder names like "context_feature",
    "value_feature", "filter_feature". These are mapped to actual feature names
    from params.context_feature_name, params.value_feature_name, params.filter_feature_name.
    
    Args:
        config: Baseline config dictionary
    
    Returns:
        List of feature dicts with concrete 'name' and 'timeframe_min'
    """
    strategy_id = config["strategy_id"]
    required_features = config["features"]["required"]
    optional_features = config["features"].get("optional", [])
    params = config.get("params", {})
    
    resolved = []
    
    # Mapping of placeholder to param key
    placeholder_map = {
        "context_feature": "context_feature_name",
        "value_feature": "value_feature_name",
        "filter_feature": "filter_feature_name",
    }
    
    # Process required features
    for feat in required_features:
        feat = feat.copy()  # don't modify original
        placeholder = feat["name"]
        if placeholder in placeholder_map:
            param_key = placeholder_map[placeholder]
            concrete_name = params.get(param_key, "")
            if concrete_name:
                feat["name"] = concrete_name
                resolved.append(feat)
            else:
                # If param is empty, skip (e.g., filter_feature_name when filter_mode=NONE)
                continue
        else:
            # Already concrete name (e.g., S1 features)
            resolved.append(feat)
    
    # Process optional features (if they exist)
    for feat in optional_features:
        feat = feat.copy()
        placeholder = feat["name"]
        if placeholder in placeholder_map:
            param_key = placeholder_map[placeholder]
            concrete_name = params.get(param_key, "")
            if concrete_name:
                feat["name"] = concrete_name
                resolved.append(feat)
            # If empty, skip (optional)
        else:
            resolved.append(feat)
    
    return resolved


def verify_feature_cache(
    season: str,
    dataset_id: str,
    tf: int,
    required_features: List[Dict[str, Any]],
) -> None:
    """
    Verify that all required features exist in the shared cache NPZ.
    
    Args:
        season: Season identifier
        dataset_id: Dataset ID
        tf: Timeframe in minutes
        required_features: List of feature dicts with 'name' and 'timeframe_min'
    
    Raises:
        RuntimeError: Missing required features in cache
        FileNotFoundError: Features NPZ file not found
    """
    # Construct features NPZ path
    features_path = Path("outputs") / "shared" / season / dataset_id / "features" / f"features_{tf}m.npz"
    if not features_path.exists():
        raise FileNotFoundError(f"Features cache not found: {features_path}")
    
    # Load NPZ keys
    try:
        data = load_features_npz(features_path)
        available_keys = set(data.keys())
    except Exception as e:
        raise RuntimeError(f"Failed to load features NPZ: {e}")
    
    # Check each required feature
    missing = []
    for feat in required_features:
        feat_name = feat["name"]
        feat_tf = feat.get("timeframe_min", tf)
        # Only check features with matching timeframe
        if feat_tf != tf:
            continue
        if feat_name not in available_keys:
            missing.append(feat_name)
    
    if missing:
        raise RuntimeError(
            f"Missing required features in cache: {missing}\n"
            f"Available keys: {sorted(available_keys)}"
        )


def run_baseline_experiment(
    season: str,
    dataset_id: str,
    tf: int,
    strategy: str,
    allow_build: bool,
) -> Dict[str, Any]:
    """
    Execute baseline experiment using research runner.
    
    Args:
        season: Season identifier
        dataset_id: Dataset ID
        tf: Timeframe in minutes
        strategy: Strategy ID
        allow_build: Whether to allow building missing features
    
    Returns:
        Research run report
    
    Raises:
        ResearchRunError: Research execution failed
    """
    # Ensure built-in strategies are loaded
    ensure_builtin_strategies_loaded()
    
    # Load baseline config
    config = load_baseline_config(strategy)
    
    # Ensure feature requirements JSON exists
    ensure_feature_requirements(strategy, config)
    
    # Resolve feature names (placeholder -> concrete)
    resolved_features = resolve_feature_names(config)
    
    # Verify feature cache (skip if allow_build=True?)
    # According to spec, we must validate feature availability before running research
    # even if allow_build=True, we should still check cache first
    try:
        verify_feature_cache(season, dataset_id, tf, resolved_features)
    except (FileNotFoundError, RuntimeError) as e:
        if not allow_build:
            raise
        # If allow_build=True, we can proceed and let research runner handle missing features
        print(f"Warning: Feature cache verification failed: {e}")
        print("Proceeding with allow_build=True...")
    
    # Execute research run
    report = run_research(
        season=season,
        dataset_id=dataset_id,
        strategy_id=strategy,
        outputs_root=Path("outputs"),
        allow_build=allow_build,
        build_ctx=None,  # Not needed if allow_build=False
        wfs_config=None,
        enable_slippage_stress=False,
        slippage_policy=None,
        commission_config=None,
        tick_size_map=None,
    )
    
    return report


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    try:
        # Load config for validation and feature list
        config = load_baseline_config(args.strategy)
        
        # Resolve feature names (placeholder -> concrete)
        resolved_features = resolve_feature_names(config)
        
        # Print startup info
        print(f"Baseline Experiment Runner")
        print(f"  Strategy: {args.strategy}")
        print(f"  Season: {args.season}")
        print(f"  Dataset: {args.dataset}")
        print(f"  Timeframe: {args.tf}m")
        print(f"  Allow build: {args.allow_build}")
        print()
        
        # Verify feature cache
        print("Verifying feature cache...")
        verify_feature_cache(
            args.season,
            args.dataset,
            args.tf,
            resolved_features,
        )
        print(f"✓ All required features available in cache")
        
        # Run research
        print(f"\nExecuting research run...")
        report = run_baseline_experiment(
            season=args.season,
            dataset_id=args.dataset,
            tf=args.tf,
            strategy=args.strategy,
            allow_build=args.allow_build,
        )
        
        # Print success summary
        print(f"\n✅ Research completed successfully")
        print(f"   Strategy ID: {report['strategy_id']}")
        print(f"   Dataset ID: {report['dataset_id']}")
        print(f"   Season: {report['season']}")
        print(f"   Used features count: {len(report['used_features'])}")
        print(f"   Build performed: {report['build_performed']}")
        
        # Print path to generated artifacts if available
        if "wfs_summary" in report and "artifact_path" in report["wfs_summary"]:
            print(f"   Artifact path: {report['wfs_summary']['artifact_path']}")
        
        return 0
        
    except FileNotFoundError as e:
        print(f"❌ Config or cache file not found: {e}", file=sys.stderr)
        return 2
    except yaml.YAMLError as e:
        print(f"❌ Invalid YAML format: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"❌ Config validation error: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"❌ Feature cache verification error: {e}", file=sys.stderr)
        return 3
    except ResearchRunError as e:
        print(f"❌ Research runner error: {e}", file=sys.stderr)
        return 4
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
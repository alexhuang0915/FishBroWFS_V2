#!/usr/bin/env python3
"""
Run Launcher Service – launch a local run (offline‑capable).

This service creates a run directory, writes intent.json, derives derived.json,
and creates a canonical run_record.json. It works without backend connectivity.
"""

import json
import logging
import uuid
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from ..models.intent_models import IntentDocument, IntentIdentity, MarketUniverse, StrategySpace, ComputeIntent, ProductRiskAssumptions, RunMode, ComputeLevel
from ..models.derived_models import DerivedDocument
from .intent_service import write_intent
from .derive_service import derive_from_intent, write_derived

logger = logging.getLogger(__name__)


def list_experiment_yamls() -> List[str]:
    """
    List available experiment YAML files from configs/experiments/baseline_no_flip/*.yaml.
    
    Returns:
        List of YAML file paths relative to project root.
    """
    base_dir = Path("configs/experiments/baseline_no_flip")
    if not base_dir.exists():
        logger.warning(f"Experiment directory not found: {base_dir}")
        return []
    
    yaml_files = []
    for path in base_dir.glob("*.yaml"):
        yaml_files.append(str(path))
    
    # Sort alphabetically
    yaml_files.sort()
    return yaml_files


@dataclass
class LaunchResult:
    """Result of a launch attempt."""
    ok: bool
    run_id: Optional[str] = None
    run_dir: Optional[Path] = None
    message: str = ""


def launch_run_from_experiment_yaml(experiment_yaml_path: str, season: str) -> LaunchResult:
    """
    Launch a run from an experiment YAML configuration.
    
    Steps:
        1. Validate YAML exists, allow_build == False, strategy in {S1,S2,S3}
        2. Parse YAML and convert to IntentDocument
        3. Generate run_id and create run directory
        4. Write intent.json and derived.json
        5. Create canonical run_record.json
        6. Return LaunchResult
    
    Args:
        experiment_yaml_path: Path to experiment YAML file
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        LaunchResult with success/failure details
    """
    yaml_path = Path(experiment_yaml_path)
    if not yaml_path.exists():
        return LaunchResult(ok=False, message=f"YAML file not found: {experiment_yaml_path}")
    
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        return LaunchResult(ok=False, message=f"Failed to parse YAML: {e}")
    
    # Validate allow_build == False (hard)
    if config.get("allow_build", True):
        return LaunchResult(ok=False, message="Experiment YAML must have allow_build: false")
    
    # Validate strategy_id in {S1,S2,S3}
    strategy_id = config.get("strategy_id")
    if strategy_id not in {"S1", "S2", "S3"}:
        return LaunchResult(ok=False, message=f"Strategy must be S1, S2, or S3, got {strategy_id}")
    
    # Convert YAML to IntentDocument
    try:
        intent = _experiment_yaml_to_intent(config, season)
    except Exception as e:
        return LaunchResult(ok=False, message=f"Failed to convert YAML to intent: {e}")
    
    # Launch the run
    return _launch_run_from_intent(intent, season)


def _experiment_yaml_to_intent(config: Dict[str, Any], season: str) -> IntentDocument:
    """
    Convert experiment YAML configuration to IntentDocument.
    
    The YAML contains:
        strategy_id: "S1"
        dataset_id: "CME.MNQ"
        timeframe: 60
        features: {required: [...], optional: []}
        params: {}
        allow_build: false
    
    We need to map to IntentDocument fields:
        identity: season, run_mode (default SMOKE)
        market_universe: instrument, timeframe, regime_filters=[]
        strategy_space: long=[strategy_id], short=[]
        compute_intent: compute_level=LOW, max_combinations=1000
        product_risk_assumptions: default values
    """
    # Extract instrument from dataset_id (e.g., "CME.MNQ" -> "MNQ")
    dataset_id = config.get("dataset_id", "CME.MNQ")
    instrument = dataset_id.split(".")[-1] if "." in dataset_id else dataset_id
    
    # Timeframe: convert integer to string with 'm' suffix
    timeframe_val = config.get("timeframe", 60)
    timeframe = f"{timeframe_val}m"
    
    # Strategy ID
    strategy_id = config.get("strategy_id", "S1")
    
    # Create intent components
    identity = IntentIdentity(season=season, run_mode=RunMode.SMOKE)
    market_universe = MarketUniverse(instrument=instrument, timeframe=timeframe, regime_filters=[])
    strategy_space = StrategySpace(long=[strategy_id], short=[])
    compute_intent = ComputeIntent(compute_level=ComputeLevel.LOW, max_combinations=1000)
    product_risk_assumptions = ProductRiskAssumptions(
        margin_model="symbolic",
        contract_specs={},
        risk_budget="medium"
    )
    
    return IntentDocument(
        identity=identity,
        market_universe=market_universe,
        strategy_space=strategy_space,
        compute_intent=compute_intent,
        product_risk_assumptions=product_risk_assumptions
    )


def _launch_run_from_intent(intent: IntentDocument, season: str, run_id: Optional[str] = None) -> LaunchResult:
    """
    Internal helper to launch a run from an IntentDocument.
    
    Creates run directory, writes intent.json, derived.json, and run_record.json.
    """
    if run_id is None:
        # Generate a deterministic but unique run ID
        import hashlib
        import time
        seed = f"{season}_{intent.identity.run_mode}_{time.time()}"
        run_id = f"run_{hashlib.sha256(seed.encode()).hexdigest()[:8]}"
    
    # Write intent.json (intent_service already does this)
    try:
        intent_path = write_intent(intent, outputs_root=Path("outputs"), season=season, run_id=run_id)
        run_dir = intent_path.parent
        logger.info(f"Intent written to {intent_path}")
    except Exception as e:
        return LaunchResult(ok=False, message=f"Failed to write intent: {e}")
    
    # Derive derived.json
    derived_path = None
    try:
        derived = derive_from_intent(intent)
        derived_path = write_derived(derived, outputs_root=Path("outputs"), season=season, run_id=run_id)
        logger.info(f"Derived written to {derived_path}")
    except Exception as e:
        logger.warning(f"Derivation failed (run will continue): {e}")
        # Continue without derived.json
    
    # Create canonical run_record.json
    try:
        run_record = _create_canonical_run_record(run_dir, run_id, season, intent, derived_path)
        run_record_path = run_dir / "run_record.json"
        with open(run_record_path, "w", encoding="utf-8") as f:
            json.dump(run_record, f, indent=2)
        logger.info(f"Run record written to {run_record_path}")
    except Exception as e:
        logger.warning(f"Failed to create run_record.json: {e}")
        # Still continue, run_record is optional for now
    
    # Create a simple log file
    log_path = run_dir / "launch.log"
    if not log_path.exists():
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Run {run_id} launched at {datetime.now().isoformat()}\n")
    
    return LaunchResult(
        ok=True,
        run_id=run_id,
        run_dir=run_dir,
        message=f"Run launched successfully: {run_dir}"
    )


def _create_canonical_run_record(run_dir: Path, run_id: str, season: str, intent: IntentDocument, derived_path: Optional[Path]) -> Dict[str, Any]:
    """
    Create canonical run record JSON matching existing format.
    
    Based on existing manifest.json format and expected fields.
    """
    created_at = datetime.now().isoformat()
    
    # Determine status based on artifacts
    intent_exists = (run_dir / "intent.json").exists()
    derived_exists = derived_path is not None and derived_path.exists()
    
    status = "CREATED"
    if derived_exists:
        status = "RUNNING"
    # Note: COMPLETED status would require results artifacts
    
    return {
        "version": "1.0",
        "run_id": run_id,
        "season": season,
        "status": status,
        "created_at": created_at,
        "intent": {
            "run_mode": intent.identity.run_mode.value,
            "instrument": intent.market_universe.instrument,
            "timeframe": intent.market_universe.timeframe,
            "strategy_ids": intent.strategy_space.long + intent.strategy_space.short,
            "compute_level": intent.compute_intent.compute_level.value,
            "max_combinations": intent.compute_intent.max_combinations,
        },
        "artifacts": {
            "intent": "intent.json",
            "derived": "derived.json" if derived_exists else None,
            "run_record": "run_record.json",
            "launch_log": "launch.log",
        },
        "notes": "Run created from experiment YAML",
    }


# Existing functions (kept for backward compatibility)

def launch_run(
    intent: IntentDocument,
    outputs_root: Path = Path("outputs"),
    season: Optional[str] = None,
    run_id: Optional[str] = None,
    skip_derive: bool = False,
) -> Path:
    """
    Launch a new run (offline‑capable).
    
    Steps:
        1. Determine season and generate run_id if not provided.
        2. Write intent.json using intent_service.
        3. Derive derived.json using derive_service (unless skip_derive).
        4. Create a minimal manifest.json placeholder.
        5. Return the run directory path.
    
    Args:
        intent: Validated intent document.
        outputs_root: Root outputs directory.
        season: Season identifier; defaults to intent.identity.season.
        run_id: Run identifier; defaults to a generated UUID‑based ID.
        skip_derive: If True, skip derived.json creation (for testing).
    
    Returns:
        Path to the created run directory.
    
    Raises:
        ValueError: If intent validation fails.
        IOError: If directory creation or file writing fails.
    """
    if season is None:
        season = intent.identity.season
    if run_id is None:
        # Generate a deterministic but unique run ID
        import hashlib
        import time
        seed = f"{season}_{intent.identity.run_mode}_{time.time()}"
        run_id = f"run_{hashlib.sha256(seed.encode()).hexdigest()[:8]}"
    
    # 1. Write intent.json (intent_service already does this)
    intent_path = write_intent(intent, outputs_root=outputs_root, season=season, run_id=run_id)
    run_dir = intent_path.parent
    logger.info(f"Intent written to {intent_path}")
    
    # 2. Derive derived.json
    derived_path = None
    if not skip_derive:
        try:
            derived = derive_from_intent(intent)
            derived_path = write_derived(derived, outputs_root=outputs_root, season=season, run_id=run_id)
            logger.info(f"Derived written to {derived_path}")
        except Exception as e:
            logger.warning(f"Derivation failed (run will continue): {e}")
            # Continue without derived.json
    
    # 3. Create a minimal manifest.json placeholder
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        manifest = {
            "version": "1.0",
            "run_id": run_id,
            "season": season,
            "status": "CREATED",
            "created_at": intent_path.stat().st_mtime,
            "artifacts": {
                "intent": intent_path.name,
                "derived": derived_path.name if derived_path else None,
            },
            "notes": "Run created by offline launcher",
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        logger.info(f"Manifest placeholder written to {manifest_path}")
    
    # 4. Create a simple log file
    log_path = run_dir / "launch.log"
    if not log_path.exists():
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Run {run_id} launched at {intent_path.stat().st_mtime}\n")
    
    return run_dir


def launch_run_from_dict(
    intent_dict: Dict[str, Any],
    outputs_root: Path = Path("outputs"),
    season: Optional[str] = None,
    run_id: Optional[str] = None,
    skip_derive: bool = False,
) -> Optional[Path]:
    """
    Convenience wrapper that validates intent dict and launches a run.
    
    Returns:
        Run directory path on success, None on validation failure.
    """
    try:
        intent = IntentDocument.model_validate(intent_dict)
        return launch_run(intent, outputs_root, season, run_id, skip_derive)
    except Exception as e:
        logger.error(f"Intent validation failed: {e}")
        return None


def get_run_status(run_dir: Path) -> Dict[str, Any]:
    """
    Get status of a local run (offline).
    
    Returns a dict with keys:
        - run_id
        - season
        - status (CREATED, RUNNING, COMPLETED, FAILED)
        - artifacts present (intent, derived, manifest, logs)
        - start_time
        - duration
    """
    run_id = run_dir.name
    season = run_dir.parent.parent.name if run_dir.parent.parent.name == "seasons" else "unknown"
    
    intent_exists = (run_dir / "intent.json").exists()
    derived_exists = (run_dir / "derived.json").exists()
    manifest_exists = (run_dir / "manifest.json").exists()
    logs_exist = (run_dir / "launch.log").exists()
    
    # Determine status based on artifacts
    if manifest_exists:
        status = "COMPLETED"
    elif derived_exists:
        status = "RUNNING"
    elif intent_exists:
        status = "CREATED"
    else:
        status = "UNKNOWN"
    
    # Start time from directory mtime
    start_time = run_dir.stat().st_mtime if intent_exists else None
    
    return {
        "run_id": run_id,
        "season": season,
        "status": status,
        "artifacts": {
            "intent": intent_exists,
            "derived": derived_exists,
            "manifest": manifest_exists,
            "logs": logs_exist,
        },
        "start_time": start_time,
        "duration": None,  # could compute if completed
        "path": str(run_dir),
    }


def list_local_runs(outputs_root: Path = Path("outputs"), season: str = "2026Q1") -> list[Dict[str, Any]]:
    """
    List all local runs for a given season (offline).
    
    This is a thin wrapper around run_index_service.list_runs.
    """
    from .run_index_service import list_runs
    return list_runs(outputs_root=outputs_root, season=season)


if __name__ == "__main__":
    # Simple CLI for testing
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Create a dummy intent
        identity = IntentIdentity(season="2026Q1", run_mode=RunMode.SMOKE)
        market_universe = MarketUniverse(instrument="MNQ", timeframe="60m", regime_filters=[])
        strategy_space = StrategySpace(long=["S1"], short=[])
        compute_intent = ComputeIntent(compute_level=ComputeLevel.LOW, max_combinations=100)
        product_risk_assumptions = ProductRiskAssumptions(
            margin_model="symbolic",
            contract_specs={},
            risk_budget="medium"
        )
        intent = IntentDocument(
            identity=identity,
            market_universe=market_universe,
            strategy_space=strategy_space,
            compute_intent=compute_intent,
            product_risk_assumptions=product_risk_assumptions,
        )
        run_dir = launch_run(intent, skip_derive=False)
        print(f"Run launched: {run_dir}")
        status = get_run_status(run_dir)
        print(json.dumps(status, indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "from-yaml":
        # Test launching from YAML
        yaml_path = sys.argv[2]
        season = sys.argv[3] if len(sys.argv) > 3 else "2026Q1"
        result = launch_run_from_experiment_yaml(yaml_path, season)
        print(json.dumps({
            "ok": result.ok,
            "run_id": result.run_id,
            "run_dir": str(result.run_dir) if result.run_dir else None,
            "message": result.message
        }, indent=2))
    else:
        print("Usage:")
        print("  python -m gui.nicegui.services.run_launcher_service test")

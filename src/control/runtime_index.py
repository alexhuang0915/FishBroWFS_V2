"""
Runtime Index Updater.

Aggregates individual shared manifests into a consolidated `bar_prepare_index.json`
for efficient UI consumption. This bridges the gap between the Supervisor's artifacts
and the UI's "Prepared" state.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Dict, Any

from core.paths import get_outputs_root, get_runtime_root
from control.control_types import ReasonCode
from control.shared_manifest import read_shared_manifest

logger = logging.getLogger(__name__)

def update_runtime_index(outputs_root: Path | None = None) -> Path:
    """
    Scan all shared manifests and rebuild `runtime/bar_prepare_index.json`.
    
    Returns:
        Path to the written index file.
    """
    if outputs_root is None:
        outputs_root = get_outputs_root()
        params_root = get_runtime_root()
    else:
        # If caller provided a root, we derive runtime from it
        params_root = outputs_root / "runtime"

    runtime_dir = params_root
    runtime_dir.mkdir(parents=True, exist_ok=True)
    index_path = runtime_dir / "bar_prepare_index.json"
    
    # Structure:
    # {
    #   "instruments": {
    #     "CME.MNQ": {
    #       "timeframes": {
    #         "60": { "status": "READY", "manifest_path": "..." },
    #         "D": { ... }
    #       },
    #       "parquet_status": { "path": "..." }
    #     }
    #   },
    #   "updated_at": "..."
    # }
    
    index: Dict[str, Any] = {"instruments": {}}
    
    # Scan outputs/shared/{season}/{dataset_id}/shared_manifest.json
    shared_root = outputs_root / "shared"
    if not shared_root.exists():
        _write_index(index_path, index)
        return index_path
        
    for season_dir in shared_root.iterdir():
        if not season_dir.is_dir():
            continue
        
        season = season_dir.name
        
        for dataset_dir in season_dir.iterdir():
            if not dataset_dir.is_dir():
                continue
                
            dataset_id = dataset_dir.name
            manifest_path = dataset_dir / "shared_manifest.json"
            
            if not manifest_path.exists():
                continue
                
            try:
                manifest = read_shared_manifest(manifest_path)
                _process_manifest(index, manifest, str(manifest_path))
            except Exception as e:
                logger.warning(f"Failed to process manifest {manifest_path}: {e}")
                
    _write_index(index_path, index)
    logger.info(f"Updated runtime index at {index_path}")
    return index_path

def _process_manifest(index: Dict[str, Any], manifest: Dict[str, Any], path: str):
    """Integrate a single manifest into the index."""
    dataset_id = manifest.get("dataset_id")
    if not dataset_id:
        return
        
    # parse dataset_id -> instrument
    # Convention: {Instrument}.{TF}m or {Instrument}.{TF}m.{Season}
    parts = dataset_id.split(".")
    if len(parts) >= 2:
        # Heuristic: First 2 parts are instrument? e.g. CME.MNQ
        # Or just first part?
        # Actually in FishBroWFS, instruments are like "CME.MNQ".
        # So it's "CME.MNQ.60m" -> Instrument="CME.MNQ", TF="60"
        
        # Try to find 'm' suffix
        tf_part = None
        tf_idx = -1
        for i, part in enumerate(parts):
            if part.endswith("m") and part[:-1].isdigit():
                tf_part = part
                tf_idx = i
                break
        
        if tf_part:
            instrument = ".".join(parts[:tf_idx])
            tf = tf_part[:-1] # "60"
            
            if instrument not in index["instruments"]:
                index["instruments"][instrument] = {"timeframes": {}}
                
            # Mark as READY if manifest exists (it implies success usually)
            index["instruments"][instrument]["timeframes"][tf] = {
                "status": "READY",
                "dataset_id": dataset_id,
                "manifest_path": path
            }
            
            # TODO: Add parquet path if available (not in shared manifest yet?)
            # shared_build creates bars/features but maybe not unified parquet
            # Parquet is usually "bars/normalized_bars.npz" -> conversion needed?
            # Or maybe coverage check looks for parquet?
            # OpTabRefactored looks for "parquet_status": {"path": ...}
            # We don't have that yet. Leaving it empty for now.
            # The coverage worker expects a parquet file. 
            # If we don't provide it, coverage will be missing, but 'Run' checks '_is_prepared' via timeframes.
            # So this is enough to unblock "Run".

def _write_index(path: Path, index: Dict[str, Any]):
    from datetime import datetime, timezone
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(index, indent=2))

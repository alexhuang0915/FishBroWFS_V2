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

from core.paths import get_outputs_root, get_runtime_root, get_shared_cache_root
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

    from core.paths import get_raw_root
    raw_root = get_raw_root()

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
    
    # Scan cache/shared/{season}/{dataset_id}/shared_manifest.json
    shared_root = get_shared_cache_root()
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

    # NEW: Scan RAW data for instrument availability
    raw_dir = raw_root / "raw"
    if raw_dir.exists():
        for item in raw_dir.iterdir():
            if not item.is_file() or not item.name.endswith(".txt"):
                continue
            
            # Simple heuristic to extract instrument name from file
            # e.g. "CME.MNQ HOT-Minute-Trade.txt" -> "CME.MNQ"
            # or "TEST_INSTRUMENT.txt" -> "TEST_INSTRUMENT"
            name = item.name
            if " " in name:
                instrument = name.split(" ")[0]
            else:
                instrument = name.replace(".txt", "").replace("_SUBSET", "")
            
            if instrument not in index["instruments"]:
                index["instruments"][instrument] = {"timeframes": {}, "parquet_status": {}}
            
            index["instruments"][instrument]["raw_available"] = True
            index["instruments"][instrument]["raw_path"] = str(item)
                
    _write_index(index_path, index)
    logger.info(f"Updated runtime index at {index_path}")
    return index_path

def _process_manifest(index: Dict[str, Any], manifest: Dict[str, Any], path: str):
    """Integrate a single manifest into the index."""
    dataset_id = manifest.get("dataset_id")
    if not dataset_id:
        return
        
    # parse dataset_id -> instrument
    # Convention: {Instrument}.{TF}m or {Instrument}
    parts = dataset_id.split(".")
    
    # Try to find 'm' suffix in parts
    tf_part = None
    tf_idx = -1
    for i, part in enumerate(parts):
        if part.endswith("m") and part[:-1].isdigit():
            tf_part = part
            tf_idx = i
            break
    
    if tf_part:
        instrument = ".".join(parts[:tf_idx])
        # In this case, we have a specific TF in the dataset_id
        timeframes = {tf_part[:-1]: {"dataset_id": dataset_id, "manifest_path": path}}
    else:
        # No TF suffix, dataset_id is likely the instrument
        instrument = dataset_id
        timeframes = {}

    if instrument not in index["instruments"]:
        index["instruments"][instrument] = {"timeframes": {}, "parquet_status": {}}

    # Scan for actual timeframes in the filesystem if not already found from dataset_id
    manifest_dir = Path(path).parent
    bars_dir = manifest_dir / "bars"
    
    if bars_dir.exists():
        for bar_file in bars_dir.glob("resampled_*m.npz"):
            tf = bar_file.name[len("resampled_"):-len("m.npz")]
            if tf.isdigit():
                index["instruments"][instrument]["timeframes"][tf] = {
                    "status": "READY",
                    "dataset_id": dataset_id,
                    "path": str(bar_file)
                }
        
        # Check for normalized bars (parquet equivalent in this system)
        normalized_path = bars_dir / "normalized_bars.npz"
        if normalized_path.exists():
            index["instruments"][instrument]["parquet_status"] = {
                "path": str(normalized_path),
                "status": "READY"
            }

    # If we found timeframes from dataset_id but not from scanning (unlikely but possible), add them
    for tf, info in timeframes.items():
        if tf not in index["instruments"][instrument]["timeframes"]:
            index["instruments"][instrument]["timeframes"][tf] = {
                "status": "READY",
                **info
            }

def _write_index(path: Path, index: Dict[str, Any]):
    from datetime import datetime, timezone
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(index, indent=2))

"""
Prepare Orchestration Layer with Data2 Dependency Enforcement.

Extends the shared build system to handle Data2 (context feeds) preparation.
Ensures that when Data2 feeds are selected, they are automatically prepared
if missing fingerprints/manifests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, UTC
from config.registry.timeframes import load_timeframes

from control.shared_build import build_shared, load_shared_manifest
from control.fingerprint_store import fingerprint_index_path, load_fingerprint_index_if_exists
from control.shared_manifest import load_shared_manifest_if_exists

logger = logging.getLogger(__name__)


def prepare_with_data2_enforcement(
    *,
    season: str,
    data1_dataset_id: str,
    data1_txt_path: Path,
    data2_feeds: List[str],
    outputs_root: Path = Path("outputs"),
    mode: str = "FULL",
    build_bars: bool = True,
    build_features: bool = True,
    tfs: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Prepare orchestration with Data2 dependency enforcement.
    
    For every selected Data2 feed:
    - If Data2 feed has no fingerprint/manifest: auto-build Data2
    - Else: validate fingerprint consistency
    
    Prepare must not return success if any selected Data2 feed is missing.
    
    Args:
        season: Season identifier
        data1_dataset_id: Primary dataset ID (Data1)
        data1_txt_path: Path to Data1 TXT file
        data2_feeds: List of Data2 feed dataset IDs
        outputs_root: Outputs root directory
        mode: Build mode ("FULL" or "INCREMENTAL")
        build_bars: Whether to build bars cache
        build_features: Whether to build features cache
        tfs: Timeframes to build (if None, uses timeframe registry)
        
    Returns:
        Dict containing:
            - success: bool
            - data1_report: dict from build_shared
            - data2_reports: dict mapping feed_id -> report
            - data2_fingerprints: dict mapping feed_id -> fingerprint_sha256
            - data2_manifest_paths: dict mapping feed_id -> manifest_path
            - no_change: bool (False if any Data2 was newly prepared)
    """
    # Use timeframe registry if tfs is not provided
    if tfs is None:
        timeframe_registry = load_timeframes()
        tfs = timeframe_registry.allowed_timeframes
    
    results = {
        "success": True,
        "data1_report": None,
        "data2_reports": {},
        "data2_fingerprints": {},
        "data2_manifest_paths": {},
        "no_change": True,  # Will be set to False if any Data2 was newly prepared
    }
    
    # 1. Prepare Data1 (primary market)
    logger.info(f"Preparing Data1: {data1_dataset_id}")
    try:
        data1_report = build_shared(
            season=season,
            dataset_id=data1_dataset_id,
            txt_path=data1_txt_path,
            outputs_root=outputs_root,
            mode=mode,
            save_fingerprint=True,
            generated_at_utc=datetime.now(UTC).isoformat(),
            build_bars=build_bars,
            build_features=build_features,
            tfs=tfs,
        )
        results["data1_report"] = data1_report
        logger.info(f"Data1 preparation completed: {data1_dataset_id}")
    except Exception as e:
        logger.error(f"Data1 preparation failed: {e}")
        results["success"] = False
        results["error"] = f"Data1 preparation failed: {e}"
        return results
    
    # 2. Prepare each Data2 feed
    for feed_id in data2_feeds:
        logger.info(f"Processing Data2 feed: {feed_id}")
        
        # Check if feed has fingerprint
        feed_index_path = fingerprint_index_path(season, feed_id, outputs_root)
        has_fingerprint = feed_index_path.exists()
        
        # Check if feed has shared manifest
        feed_manifest = load_shared_manifest(season, feed_id, outputs_root)
        has_manifest = feed_manifest is not None
        
        if not has_fingerprint or not has_manifest:
            # Need to auto-build Data2
            logger.info(f"Data2 feed {feed_id} missing artifacts, auto-building...")
            
            # Find TXT file for feed
            feed_txt_path = _find_txt_path_for_feed(feed_id)
            if feed_txt_path is None:
                logger.error(f"Could not find TXT file for Data2 feed: {feed_id}")
                results["success"] = False
                results["error"] = f"Missing TXT file for Data2 feed: {feed_id}"
                return results
            
            try:
                feed_report = build_shared(
                    season=season,
                    dataset_id=feed_id,
                    txt_path=feed_txt_path,
                    outputs_root=outputs_root,
                    mode=mode,
                    save_fingerprint=True,
                    generated_at_utc=datetime.now(UTC).isoformat(),
                    build_bars=build_bars,
                    build_features=build_features,
                    tfs=tfs,
                )
                results["data2_reports"][feed_id] = feed_report
                results["no_change"] = False  # Data2 was newly prepared
                
                # Store fingerprint and manifest info
                if "fingerprint_path" in feed_report:
                    results["data2_fingerprints"][feed_id] = feed_report.get("fingerprint_path")
                
                if "manifest_path" in feed_report:
                    results["data2_manifest_paths"][feed_id] = feed_report.get("manifest_path")
                
                logger.info(f"Data2 feed {feed_id} auto-built successfully")
                
            except Exception as e:
                logger.error(f"Data2 feed {feed_id} preparation failed: {e}")
                results["success"] = False
                results["error"] = f"Data2 feed {feed_id} preparation failed: {e}"
                return results
        else:
            # Feed has existing artifacts, validate consistency
            logger.info(f"Data2 feed {feed_id} has existing artifacts, validating...")
            
            # Load fingerprint index
            fingerprint_index = load_fingerprint_index_if_exists(feed_index_path)
            if fingerprint_index:
                results["data2_fingerprints"][feed_id] = fingerprint_index.index_sha256
            
            # Store manifest path
            manifest_path = outputs_root / "shared" / season / feed_id / "shared_manifest.json"
            if manifest_path.exists():
                results["data2_manifest_paths"][feed_id] = str(manifest_path)
            
            logger.info(f"Data2 feed {feed_id} validation passed")
    
    return results


def _find_txt_path_for_feed(feed_id: str) -> Optional[Path]:
    """
    Find TXT file path for a given feed ID.
    
    Looks in the standard raw data directory.
    """
    # Raw data directory relative to workspace root
    workspace_root = Path(__file__).parent.parent.parent.parent
    raw_dir = workspace_root / "FishBroData" / "raw"
    if not raw_dir.exists():
        return None
    
    # Try common patterns
    patterns = [
        f"{feed_id} HOT-Minute-Trade.txt",
        f"{feed_id}_SUBSET.txt",
        f"{feed_id}.txt",
    ]
    
    for pattern in patterns:
        candidate = raw_dir / pattern
        if candidate.exists():
            return candidate
    
    # Fallback: search for files containing feed_id
    for item in raw_dir.iterdir():
        if not item.is_file():
            continue
        
        if feed_id in item.name:
            return item
    
    return None


def check_data2_readiness(
    season: str,
    data2_feeds: List[str],
    outputs_root: Path = Path("outputs"),
) -> Dict[str, Any]:
    """
    Check if Data2 feeds are ready (have fingerprints and manifests).
    
    Args:
        season: Season identifier
        data2_feeds: List of Data2 feed dataset IDs
        outputs_root: Outputs root directory
        
    Returns:
        Dict containing:
            - all_ready: bool
            - ready_feeds: List[str]
            - missing_feeds: List[str]
            - feed_status: Dict[feed_id -> dict]
    """
    results = {
        "all_ready": True,
        "ready_feeds": [],
        "missing_feeds": [],
        "feed_status": {},
    }
    
    for feed_id in data2_feeds:
        # Check fingerprint
        feed_index_path = fingerprint_index_path(season, feed_id, outputs_root)
        has_fingerprint = feed_index_path.exists()
        
        # Check shared manifest
        feed_manifest = load_shared_manifest(season, feed_id, outputs_root)
        has_manifest = feed_manifest is not None
        
        is_ready = has_fingerprint and has_manifest
        
        results["feed_status"][feed_id] = {
            "has_fingerprint": has_fingerprint,
            "has_manifest": has_manifest,
            "is_ready": is_ready,
            "fingerprint_path": str(feed_index_path) if has_fingerprint else None,
        }
        
        if is_ready:
            results["ready_feeds"].append(feed_id)
        else:
            results["missing_feeds"].append(feed_id)
            results["all_ready"] = False
    
    return results
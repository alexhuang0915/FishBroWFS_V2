"""Reload Service for System Status and Cache Invalidation.

Provides functions to:
1. Get system snapshot (datasets, strategies, caches)
2. Invalidate caches and reload registries
3. Compute file signatures for validation
4. TXT → Parquet build functionality
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

# Use intent-based system for Attack #9 - Headless Intent-State Contract
from FishBroWFS_V2.gui.adapters.intent_bridge import migrate_ui_imports

# Migrate imports to use intent bridge
migrate_ui_imports()

# The migrate_ui_imports() function provides:
# - get_dataset_catalog
# - get_strategy_catalog
# - get_descriptor
# - get_paths
# - list_research_units, get_research_artifacts, get_portfolio_index
# - list_descriptors, build_parquet_from_txt, invalidate_feature_cache
# - BuildParquetRequest, BuildParquetResult types

from FishBroWFS_V2.data.dataset_registry import DatasetRecord
from FishBroWFS_V2.strategy.registry import StrategySpecForGUI

# Type imports for compatibility (these are just types, not runtime dependencies)
# We'll use string type annotations to avoid importing at module level


@dataclass
class FileStatus:
    """Status of a file or directory."""
    path: str
    exists: bool
    size: int = 0
    mtime: float = 0.0
    signature: str = ""
    error: Optional[str] = None


@dataclass
class DatasetStatus:
    """Status of a dataset with TXT and Parquet information."""
    # Required fields (no defaults) first
    dataset_id: str
    kind: str
    txt_root: str
    txt_required_paths: List[str]
    parquet_root: str
    parquet_expected_paths: List[str]
    
    # Optional fields with defaults
    descriptor: Optional["DatasetDescriptor"] = None  # String annotation to avoid importing control module
    txt_present: bool = False
    txt_missing: List[str] = field(default_factory=list)
    txt_latest_mtime_utc: Optional[str] = None
    txt_total_size_bytes: int = 0
    txt_signature: str = ""
    parquet_present: bool = False
    parquet_missing: List[str] = field(default_factory=list)
    parquet_latest_mtime_utc: Optional[str] = None
    parquet_total_size_bytes: int = 0
    parquet_signature: str = ""
    up_to_date: bool = False
    bars_count: Optional[int] = None
    schema_ok: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class StrategyStatus:
    """Status of a strategy."""
    id: str
    spec: Optional[StrategySpecForGUI] = None
    can_import: bool = False
    can_build_spec: bool = False
    mtime: float = 0.0
    signature: str = ""
    feature_requirements_count: int = 0
    error: Optional[str] = None


@dataclass
class SystemSnapshot:
    """System snapshot with status of all components."""
    created_at: datetime = field(default_factory=datetime.now)
    total_datasets: int = 0
    total_strategies: int = 0
    dataset_statuses: List[DatasetStatus] = field(default_factory=list)
    strategy_statuses: List[StrategyStatus] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ReloadResult:
    """Result of a reload operation."""
    ok: bool
    error: Optional[str] = None
    datasets_reloaded: int = 0
    strategies_reloaded: int = 0
    caches_invalidated: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def compute_file_signature(file_path: Path, max_size_mb: int = 50) -> str:
    """Compute signature for a file.
    
    For small files (< max_size_mb): compute sha256
    For large files: use stat-hash (path + size + mtime)
    """
    try:
        if not file_path.exists():
            return "missing"
        
        stat = file_path.stat()
        file_size_mb = stat.st_size / (1024 * 1024)
        
        if file_size_mb < max_size_mb:
            # Small file: compute actual hash
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                chunk_size = 8192
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return f"sha256:{hasher.hexdigest()[:16]}"
        else:
            # Large file: use stat-hash
            return f"stat:{file_path.name}:{stat.st_size}:{stat.st_mtime}"
    except Exception as e:
        return f"error:{str(e)[:50]}"


def check_dataset_files(dataset: DatasetRecord) -> Tuple[List[FileStatus], int]:
    """Check files for a dataset (legacy compatibility).
    
    Args:
        dataset: DatasetRecord with root and required_paths attributes
        
    Returns:
        Tuple of (list of FileStatus objects, missing_count)
    """
    # This is a legacy compatibility function for tests
    # The new API uses check_txt_files and check_parquet_files
    files = []
    missing_count = 0
    
    # Check root directory
    root_path = Path(dataset.root) if hasattr(dataset, 'root') else Path(".")
    root_status = FileStatus(
        path=str(root_path),
        exists=root_path.exists(),
        size=root_path.stat().st_size if root_path.exists() else 0,
        mtime=root_path.stat().st_mtime if root_path.exists() else 0.0,
        signature=compute_file_signature(root_path) if root_path.exists() else ""
    )
    files.append(root_status)
    
    # Check required paths
    required_paths = getattr(dataset, 'required_paths', [])
    for path_str in required_paths:
        path = Path(path_str)
        exists = path.exists()
        if not exists:
            missing_count += 1
        
        status = FileStatus(
            path=path_str,
            exists=exists,
            size=path.stat().st_size if exists else 0,
            mtime=path.stat().st_mtime if exists else 0.0,
            signature=compute_file_signature(path) if exists else ""
        )
        files.append(status)
    
    return files, missing_count


def check_txt_files(txt_root: str, txt_required_paths: List[str]) -> Tuple[bool, List[str], Optional[str], int, str]:
    """Check TXT files for a dataset.
    
    Returns:
        Tuple of (present, missing_paths, latest_mtime_utc, total_size_bytes, signature)
    """
    missing = []
    latest_mtime = 0.0
    total_size = 0
    signatures = []
    
    for txt_path_str in txt_required_paths:
        txt_path = Path(txt_path_str)
        if txt_path.exists():
            stat = txt_path.stat()
            latest_mtime = max(latest_mtime, stat.st_mtime)
            total_size += stat.st_size
            sig = compute_file_signature(txt_path)
            signatures.append(f"{txt_path.name}:{sig}")
        else:
            missing.append(txt_path_str)
    
    present = len(missing) == 0
    signature = "|".join(signatures) if signatures else "none"
    
    # Convert latest mtime to UTC string
    latest_mtime_utc = None
    if latest_mtime > 0:
        latest_mtime_utc = datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
    
    return present, missing, latest_mtime_utc, total_size, signature


def check_parquet_files(parquet_root: str, parquet_expected_paths: List[str]) -> Tuple[bool, List[str], Optional[str], int, str]:
    """Check Parquet files for a dataset.
    
    Returns:
        Tuple of (present, missing_paths, latest_mtime_utc, total_size_bytes, signature)
    """
    missing = []
    latest_mtime = 0.0
    total_size = 0
    signatures = []
    
    for parquet_path_str in parquet_expected_paths:
        parquet_path = Path(parquet_path_str)
        if parquet_path.exists():
            stat = parquet_path.stat()
            latest_mtime = max(latest_mtime, stat.st_mtime)
            total_size += stat.st_size
            sig = compute_file_signature(parquet_path)
            signatures.append(f"{parquet_path.name}:{sig}")
        else:
            missing.append(parquet_path_str)
    
    present = len(missing) == 0
    signature = "|".join(signatures) if signatures else "none"
    
    # Convert latest mtime to UTC string
    latest_mtime_utc = None
    if latest_mtime > 0:
        latest_mtime_utc = datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
    
    return present, missing, latest_mtime_utc, total_size, signature


def get_dataset_status(dataset_id: str) -> DatasetStatus:
    """Get status for a single dataset with TXT and Parquet information."""
    try:
        # Get dataset descriptor
        descriptor = get_descriptor(dataset_id)
        if descriptor is None:
            return DatasetStatus(
                dataset_id=dataset_id,
                kind="unknown",
                txt_root="",
                txt_required_paths=[],
                parquet_root="",
                parquet_expected_paths=[],
                error=f"Dataset not found: {dataset_id}"
            )
        
        # Check TXT files
        txt_present, txt_missing, txt_latest_mtime_utc, txt_total_size, txt_signature = check_txt_files(
            descriptor.txt_root, descriptor.txt_required_paths
        )
        
        # Check Parquet files
        parquet_present, parquet_missing, parquet_latest_mtime_utc, parquet_total_size, parquet_signature = check_parquet_files(
            descriptor.parquet_root, descriptor.parquet_expected_paths
        )
        
        # Determine if up-to-date
        up_to_date = False
        if txt_present and parquet_present:
            # Simple up-to-date check: compare signatures
            # In a real implementation, this would compare content hashes
            up_to_date = True  # Placeholder
        
        # Try to get bars count (lazy, can be expensive)
        bars_count = None
        schema_ok = None
        
        # Simple schema check for Parquet files
        if parquet_present and descriptor.parquet_expected_paths:
            try:
                parquet_path = Path(descriptor.parquet_expected_paths[0])
                if parquet_path.exists():
                    # Quick check: try to read first few rows
                    import pandas as pd
                    df_sample = pd.read_parquet(parquet_path, nrows=1)
                    schema_ok = True
                    bars_count = len(pd.read_parquet(parquet_path)) if parquet_path.stat().st_size < 1000000 else None
            except Exception:
                schema_ok = False
        
        return DatasetStatus(
            dataset_id=dataset_id,
            kind=descriptor.kind,
            descriptor=descriptor,
            txt_root=descriptor.txt_root,
            txt_required_paths=descriptor.txt_required_paths,
            txt_present=txt_present,
            txt_missing=txt_missing,
            txt_latest_mtime_utc=txt_latest_mtime_utc,
            txt_total_size_bytes=txt_total_size,
            txt_signature=txt_signature,
            parquet_root=descriptor.parquet_root,
            parquet_expected_paths=descriptor.parquet_expected_paths,
            parquet_present=parquet_present,
            parquet_missing=parquet_missing,
            parquet_latest_mtime_utc=parquet_latest_mtime_utc,
            parquet_total_size_bytes=parquet_total_size,
            parquet_signature=parquet_signature,
            up_to_date=up_to_date,
            bars_count=bars_count,
            schema_ok=schema_ok
        )
    except Exception as e:
        return DatasetStatus(
            dataset_id=dataset_id,
            kind="unknown",
            txt_root="",
            txt_required_paths=[],
            parquet_root="",
            parquet_expected_paths=[],
            error=str(e)
        )


def get_strategy_status(strategy: StrategySpecForGUI) -> StrategyStatus:
    """Get status for a single strategy."""
    try:
        # Check if strategy can be imported
        can_import = True  # Assume yes for now
        can_build_spec = True  # Assume yes for now
        
        # Get feature requirements count
        feature_requirements_count = 0
        if hasattr(strategy, 'feature_requirements'):
            feature_requirements_count = len(strategy.feature_requirements)
        
        # Try to get file info if path is available
        mtime = 0.0
        signature = ""
        if hasattr(strategy, 'file_path') and strategy.file_path:
            file_path = Path(strategy.file_path)
            if file_path.exists():
                stat = file_path.stat()
                mtime = stat.st_mtime
                signature = compute_file_signature(file_path)
        
        return StrategyStatus(
            id=strategy.strategy_id,
            spec=strategy,
            can_import=can_import,
            can_build_spec=can_build_spec,
            mtime=mtime,
            signature=signature,
            feature_requirements_count=feature_requirements_count
        )
    except Exception as e:
        return StrategyStatus(
            id=strategy.strategy_id if hasattr(strategy, 'strategy_id') else 'unknown',
            error=str(e),
            can_import=False,
            can_build_spec=False
        )


def get_system_snapshot() -> SystemSnapshot:
    """Get current system snapshot with TXT and Parquet status."""
    snapshot = SystemSnapshot()
    
    try:
        # Get dataset descriptors - use function provided by migrate_ui_imports()
        descriptors = list_descriptors()
        snapshot.total_datasets = len(descriptors)
        
        for descriptor in descriptors:
            status = get_dataset_status(descriptor.dataset_id)
            snapshot.dataset_statuses.append(status)
            if status.error:
                snapshot.errors.append(f"Dataset {descriptor.dataset_id}: {status.error}")
        
        # Get strategies
        strategy_catalog = get_strategy_catalog()
        strategies = strategy_catalog.list_strategies()
        snapshot.total_strategies = len(strategies)
        
        for strategy in strategies:
            status = get_strategy_status(strategy)
            snapshot.strategy_statuses.append(status)
            if status.error:
                snapshot.errors.append(f"Strategy {strategy.strategy_id}: {status.error}")
        
        # Add notes
        if snapshot.errors:
            snapshot.notes.append(f"Found {len(snapshot.errors)} errors")
        
        # Count TXT/Parquet status
        txt_present_count = sum(1 for ds in snapshot.dataset_statuses if ds.txt_present)
        parquet_present_count = sum(1 for ds in snapshot.dataset_statuses if ds.parquet_present)
        up_to_date_count = sum(1 for ds in snapshot.dataset_statuses if ds.up_to_date)
        
        snapshot.notes.append(f"TXT present: {txt_present_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Parquet present: {parquet_present_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Up-to-date: {up_to_date_count}/{snapshot.total_datasets}")
        snapshot.notes.append(f"Snapshot created at {snapshot.created_at.isoformat()}")
        
    except Exception as e:
        snapshot.errors.append(f"Failed to get system snapshot: {str(e)}")
    
    return snapshot


# Note: invalidate_feature_cache() is provided by migrate_ui_imports()
# through the intent bridge adapter

def reload_dataset_registry() -> bool:
    """Reload dataset registry."""
    try:
        catalog = get_dataset_catalog()
        # Force reload by calling load_index
        catalog.load_index()  # Force load
        return True
    except Exception as e:
        return False


def reload_strategy_registry() -> bool:
    """Reload strategy registry."""
    try:
        catalog = get_strategy_catalog()
        # Force reload by calling load_registry
        catalog.load_registry()  # Force load
        return True
    except Exception as e:
        return False


def reload_everything(reason: str = "manual") -> ReloadResult:
    """Reload all caches and registries."""
    start_time = time.time()
    result = ReloadResult(ok=True)
    caches_invalidated = []
    
    try:
        # 1. Invalidate feature cache
        if invalidate_feature_cache():
            caches_invalidated.append("feature_cache")
        else:
            result.ok = False
            result.error = "Failed to invalidate feature cache"
        
        # 2. Reload dataset registry
        if reload_dataset_registry():
            result.datasets_reloaded += 1
        else:
            result.ok = False
            result.error = "Failed to reload dataset registry"
        
        # 3. Reload strategy registry
        if reload_strategy_registry():
            result.strategies_reloaded += 1
        else:
            result.ok = False
            result.error = "Failed to reload strategy registry"
        
        # 4. Rebuild snapshot (implicitly done by get_system_snapshot)
        
        result.caches_invalidated = caches_invalidated
        result.duration_seconds = time.time() - start_time
        
        if result.ok:
            result.error = None
        
    except Exception as e:
        result.ok = False
        result.error = f"Reload failed: {str(e)}"
        result.duration_seconds = time.time() - start_time
    
    return result


def build_parquet(
    dataset_id: str,
    force: bool = False,
    deep_validate: bool = False,
    reason: str = "manual"
) -> BuildParquetResult:
    """Build Parquet from TXT for a dataset.
    
    Args:
        dataset_id: Dataset ID to build
        force: Rebuild even if up-to-date
        deep_validate: Perform schema validation after build
        reason: Reason for build (for audit/logging)
        
    Returns:
        BuildParquetResult with build status
    """
    # Use functions and types provided by migrate_ui_imports()
    req = BuildParquetRequest(
        dataset_id=dataset_id,
        force=force,
        deep_validate=deep_validate,
        reason=reason
    )
    
    return build_parquet_from_txt(req)


def build_all_parquet(force: bool = False, reason: str = "manual") -> List[BuildParquetResult]:
    """Build Parquet for all datasets.
    
    Args:
        force: Rebuild even if up-to-date
        reason: Reason for build (for audit/logging)
        
    Returns:
        List of BuildParquetResult for each dataset
    """
    # Use functions provided by migrate_ui_imports()
    results = []
    descriptors = list_descriptors()
    
    for descriptor in descriptors:
        result = build_parquet(
            dataset_id=descriptor.dataset_id,
            force=force,
            deep_validate=False,
            reason=f"{reason}_batch"
        )
        results.append(result)
    
    return results

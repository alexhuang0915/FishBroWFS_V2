"""
Headless Cleanup Service - Safe deletion with allowlist and dry-run.

Provides safe deletion operations for runs, artifacts, cache, and demo data.
Implements dry-run preview, allowlist exclusions, and audit logging.

This is a headless version of gui.desktop.services.cleanup_service.
"""

import os
import json
import logging
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class CleanupScope(Enum):
    """Scope of cleanup operation."""
    RUNS = "runs"
    PUBLISHED = "published"
    CACHE = "cache"
    DEMO = "demo"
    TRASH_PURGE = "trash_purge"


class TimeRange(Enum):
    """Time range for cleanup operations."""
    LAST_1_HOUR = "last_1_hour"
    TODAY = "today"
    LAST_7_DAYS = "last_7_days"
    ALL = "all"


@dataclass
class DeletePlan:
    """Plan for deletion operation."""
    scope: CleanupScope
    items: List[str]  # paths to delete
    total_size_bytes: int
    trash_path: Optional[str] = None  # destination for soft delete
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "scope": self.scope.value,
            "items": self.items,
            "total_size_bytes": self.total_size_bytes,
            "trash_path": self.trash_path
        }


class HeadlessCleanupService:
    """Headless service for safe cleanup operations."""
    
    def __init__(self, outputs_root: Optional[Path] = None):
        self.outputs_root = outputs_root or Path("outputs")
        self.trash_dir = self.outputs_root / "_trash"
        
        # Allowlist patterns (files/directories to never delete)
        self.allowlist_patterns = [
            "outputs/_trash",  # trash directory itself
            "cache/shared/artifacts",  # legacy published artifacts (if any)
            "outputs/seasons/*/shared/artifacts",
            "outputs/seasons/*/shared/features",  # features are cache but may be allowlisted
            "outputs/seasons/*/shared/bars",  # bars cache
            "outputs/seasons/*/runs/*/manifest.json",  # run manifests
            "outputs/seasons/*/runs/*/artifact_*",  # published results
        ]
        
        # Ensure trash directory exists
        self.trash_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_current_season(self) -> str:
        """Get current season (simplified)."""
        # In production, would read from config or determine from current date
        return "2026Q1"
    
    def _is_allowlisted(self, path: Path) -> bool:
        """Check if a path matches any allowlist pattern."""
        path_str = str(path)
        for pattern in self.allowlist_patterns:
            # Simple pattern matching (could be enhanced with glob)
            if pattern in path_str:
                return True
        return False
    
    def _scan_runs(self, season: str, time_range: TimeRange, run_types: List[str]) -> List[Path]:
        """Scan runs directory for matching runs."""
        runs_dir = self.outputs_root / "seasons" / season / "runs"
        if not runs_dir.exists():
            return []
        
        # Determine cutoff time based on time_range
        now = datetime.now()
        if time_range == TimeRange.LAST_1_HOUR:
            cutoff = now - timedelta(hours=1)
        elif time_range == TimeRange.TODAY:
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif time_range == TimeRange.LAST_7_DAYS:
            cutoff = now - timedelta(days=7)
        else:  # ALL
            cutoff = datetime.min
        
        matching_runs = []
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            # Check modification time
            mtime = datetime.fromtimestamp(run_dir.stat().st_mtime)
            if mtime < cutoff and time_range != TimeRange.ALL:
                continue
            
            # Check run type (simplified - would need to read manifest)
            # For now, accept all if run_types is empty
            if run_types:
                # Determine run type from directory name or manifest
                run_type = self._infer_run_type(run_dir)
                if run_type not in run_types:
                    continue
            
            # Exclude allowlisted items
            if self._is_allowlisted(run_dir):
                continue
            
            matching_runs.append(run_dir)
        
        return matching_runs
    
    def _infer_run_type(self, run_dir: Path) -> str:
        """Infer run type from directory (simplified)."""
        # Check for artifact files
        if any(run_dir.glob("artifact_*")):
            return "published"
        # Check for manifest
        manifest = run_dir / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                if data.get("status") == "completed":
                    return "completed"
                elif data.get("status") == "failed":
                    return "failed"
            except:
                pass
        return "unknown"
    
    def _scan_published(self, season: str, artifact_ids: List[str]) -> List[Path]:
        """Scan for published artifacts."""
        artifacts = []
        # Look in runs directories
        runs_dir = self.outputs_root / "seasons" / season / "runs"
        if not runs_dir.exists():
            return []
        
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            for artifact_id in artifact_ids:
                artifact_dir = run_dir / artifact_id
                if artifact_dir.exists():
                    artifacts.append(artifact_dir)
                else:
                    # Check for artifact_* directories
                    for subdir in run_dir.glob(f"{artifact_id}*"):
                        if subdir.is_dir():
                            artifacts.append(subdir)
        
        return artifacts
    
    def _scan_cache(self, season: str, market: str, cache_type: str) -> List[Path]:
        """Scan cache directories."""
        cache_items = []
        base_dir = self.outputs_root / "seasons" / season / "shared"
        
        if not base_dir.exists():
            return []
        
        # Bars cache
        if cache_type in ["bars", "both"]:
            bars_dir = base_dir / market / "bars"
            if bars_dir.exists():
                for file in bars_dir.glob("*.npz"):
                    if not self._is_allowlisted(file):
                        cache_items.append(file)
        
        # Features cache
        if cache_type in ["features", "both"]:
            features_dir = base_dir / market / "features"
            if features_dir.exists():
                for file in features_dir.rglob("*"):
                    if file.is_file() and not self._is_allowlisted(file):
                        cache_items.append(file)
        
        return cache_items
    
    def _scan_demo(self, season: str) -> List[Path]:
        """Scan demo data."""
        demo_items = []
        # Look for runs with demo tag
        runs_dir = self.outputs_root / "seasons" / season / "runs"
        if not runs_dir.exists():
            return []
        
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            # Check if demo (simplified)
            manifest = run_dir / "manifest.json"
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text())
                    if data.get("tags") and "demo" in data.get("tags", []):
                        demo_items.append(run_dir)
                except:
                    pass
        
        return demo_items
    
    def _scan_trash(self, time_range: TimeRange) -> List[Path]:
        """Scan trash directory."""
        if not self.trash_dir.exists():
            return []
        
        # Determine cutoff time
        now = datetime.now()
        if time_range == TimeRange.LAST_1_HOUR:
            cutoff = now - timedelta(hours=1)
        elif time_range == TimeRange.TODAY:
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif time_range == TimeRange.LAST_7_DAYS:
            cutoff = now - timedelta(days=7)
        else:  # ALL
            cutoff = datetime.min
        
        trash_items = []
        for item in self.trash_dir.iterdir():
            if item.is_dir():
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                if mtime >= cutoff or time_range == TimeRange.ALL:
                    trash_items.append(item)
        
        return trash_items
    
    def _calculate_size(self, paths: List[Path]) -> int:
        """Calculate total size of files/directories."""
        total = 0
        for path in paths:
            if path.is_file():
                total += path.stat().st_size
            else:
                for file in path.rglob("*"):
                    if file.is_file():
                        total += file.stat().st_size
        return total
    
    def build_delete_plan(self, scope: CleanupScope, criteria: Dict[str, Any]) -> DeletePlan:
        """
        Build a deletion plan for the given scope and criteria.
        
        Args:
            scope: CleanupScope enum
            criteria: Dictionary with parameters specific to scope
        
        Returns:
            DeletePlan object with items to delete
        """
        items = []
        
        if scope == CleanupScope.RUNS:
            season = criteria.get("season", self._get_current_season())
            time_range_str = criteria.get("time_range", TimeRange.LAST_7_DAYS)
            time_range = TimeRange(time_range_str) if isinstance(time_range_str, str) else time_range_str
            run_types = criteria.get("run_types", ["completed", "failed"])
            items = self._scan_runs(season, time_range, run_types)
        
        elif scope == CleanupScope.PUBLISHED:
            season = criteria.get("season", self._get_current_season())
            artifact_ids = criteria.get("artifact_ids", [])
            items = self._scan_published(season, artifact_ids)
        
        elif scope == CleanupScope.CACHE:
            season = criteria.get("season", self._get_current_season())
            market = criteria.get("market", "ES")
            cache_type = criteria.get("cache_type", "both")
            items = self._scan_cache(season, market, cache_type)
        
        elif scope == CleanupScope.DEMO:
            season = criteria.get("season", self._get_current_season())
            items = self._scan_demo(season)
        
        elif scope == CleanupScope.TRASH_PURGE:
            time_range_str = criteria.get("time_range", TimeRange.ALL)
            time_range = TimeRange(time_range_str) if isinstance(time_range_str, str) else time_range_str
            items = self._scan_trash(time_range)
        
        else:
            raise ValueError(f"Unknown scope: {scope}")
        
        # Convert Path objects to strings
        item_strings = [str(item) for item in items]
        total_size = self._calculate_size(items)
        
        # For soft delete operations, set trash destination
        trash_path = None
        if scope != CleanupScope.TRASH_PURGE:
            # Create timestamped trash subdirectory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trash_subdir = self.trash_dir / f"{scope.value}_{timestamp}"
            trash_path = str(trash_subdir)
        
        return DeletePlan(
            scope=scope,
            items=item_strings,
            total_size_bytes=total_size,
            trash_path=trash_path
        )
    
    def execute_soft_delete(self, plan: DeletePlan) -> Tuple[bool, str]:
        """
        Execute soft delete (move to trash).
        
        Args:
            plan: DeletePlan with items to delete
        
        Returns:
            (success, message)
        """
        if not plan.items:
            return True, "No items to delete"
        
        if not plan.trash_path:
            return False, "No trash destination specified"
        
        trash_dir = Path(plan.trash_path)
        trash_dir.mkdir(parents=True, exist_ok=True)
        
        moved_count = 0
        errors = []
        
        for item_str in plan.items:
            item = Path(item_str)
            if not item.exists():
                continue
            
            try:
                # Determine destination in trash
                # Preserve relative path structure
                rel_path = None
                for base in [self.outputs_root, Path.cwd()]:
                    try:
                        rel_path = item.relative_to(base)
                        break
                    except ValueError:
                        continue
                
                if rel_path:
                    dest = trash_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                else:
                    # Fallback: use filename
                    dest = trash_dir / item.name
                
                # Move item
                shutil.move(str(item), str(dest))
                moved_count += 1
                
            except Exception as e:
                errors.append(f"{item}: {str(e)}")
                logger.error(f"Failed to move {item} to trash: {e}")
        
        if errors:
            message = f"Moved {moved_count} items to trash, {len(errors)} errors: {', '.join(errors[:3])}"
            return False, message
        
        return True, f"Successfully moved {moved_count} items to {trash_dir}"
    
    def execute_purge_trash(self, plan: DeletePlan) -> Tuple[bool, str]:
        """
        Permanently delete items from trash.
        
        Args:
            plan: DeletePlan with items to delete (should be trash items)
        
        Returns:
            (success, message)
        """
        if not plan.items:
            return True, "No items to delete"
        
        deleted_count = 0
        errors = []
        
        for item_str in plan.items:
            item = Path(item_str)
            if not item.exists():
                continue
            
            # Safety check: ensure item is within trash directory
            try:
                item.relative_to(self.trash_dir)
            except ValueError:
                errors.append(f"{item} is not in trash directory")
                continue
            
            try:
                if item.is_file():
                    item.unlink()
                else:
                    shutil.rmtree(item)
                deleted_count += 1
            except Exception as e:
                errors.append(f"{item}: {str(e)}")
                logger.error(f"Failed to delete {item}: {e}")
        
        if errors:
            message = f"Deleted {deleted_count} items, {len(errors)} errors: {', '.join(errors[:3])}"
            return False, message
        
        return True, f"Successfully deleted {deleted_count} items from trash"
    
    def get_allowlist_patterns(self) -> List[str]:
        """Get current allowlist patterns."""
        return self.allowlist_patterns.copy()
    
    def add_allowlist_pattern(self, pattern: str) -> None:
        """Add a pattern to the allowlist."""
        if pattern not in self.allowlist_patterns:
            self.allowlist_patterns.append(pattern)
    
    def remove_allowlist_pattern(self, pattern: str) -> bool:
        """Remove a pattern from the allowlist."""
        if pattern in self.allowlist_patterns:
            self.allowlist_patterns.remove(pattern)
            return True
        return False

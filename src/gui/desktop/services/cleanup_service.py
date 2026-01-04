"""
Cleanup Service - Safe deletion tools for runs, artifacts, cache, and demo data.

Provides guardrails for safe cleanup operations with dry-run preview,
soft delete to outputs/_trash, and audit logging.
"""

import os
import shutil
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class CleanupScope(Enum):
    """Types of cleanup operations."""
    RUNS = "runs"
    PUBLISHED = "published"
    CACHE = "cache"
    DEMO = "demo"
    TRASH_PURGE = "trash_purge"


class TimeRange(Enum):
    """Time ranges for cleanup selection."""
    LAST_1_HOUR = "1h"
    TODAY = "today"
    LAST_7_DAYS = "7d"
    ALL = "all"


@dataclass
class DeletePlan:
    """Plan for deletion operations."""
    scope: CleanupScope
    criteria: Dict[str, Any]
    items: List[Path]
    total_size_bytes: int
    trash_path: Optional[Path] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for audit logging."""
        # Convert criteria values, handling enums
        serializable_criteria = {}
        for key, value in self.criteria.items():
            if isinstance(value, Enum):
                serializable_criteria[key] = value.value
            else:
                serializable_criteria[key] = value
        
        return {
            "scope": self.scope.value,
            "criteria": serializable_criteria,
            "item_count": len(self.items),
            "total_size_bytes": self.total_size_bytes,
            "trash_path": str(self.trash_path) if self.trash_path else None,
            "sample_items": [str(item) for item in self.items[:10]] if self.items else []
        }


class CleanupService:
    """Service for safe cleanup operations."""
    
    def __init__(self, outputs_root: Path = Path("outputs")):
        self.outputs_root = outputs_root
        self.trash_root = outputs_root / "_trash"
        
        # Ensure trash directory exists
        self.trash_root.mkdir(exist_ok=True)
    
    def build_delete_plan(self, scope: CleanupScope, criteria: Dict[str, Any]) -> DeletePlan:
        """
        Build a delete plan for dry-run preview.
        
        Args:
            scope: Type of cleanup operation
            criteria: Selection criteria
            
        Returns:
            DeletePlan with items to delete
        """
        if scope == CleanupScope.RUNS:
            return self._build_runs_plan(criteria)
        elif scope == CleanupScope.PUBLISHED:
            return self._build_published_plan(criteria)
        elif scope == CleanupScope.CACHE:
            return self._build_cache_plan(criteria)
        elif scope == CleanupScope.DEMO:
            return self._build_demo_plan(criteria)
        elif scope == CleanupScope.TRASH_PURGE:
            return self._build_trash_purge_plan(criteria)
        else:
            raise ValueError(f"Unknown cleanup scope: {scope}")
    
    def _build_runs_plan(self, criteria: Dict[str, Any]) -> DeletePlan:
        """Build plan for deleting runs."""
        season = criteria.get("season", self._get_current_season())
        time_range = TimeRange(criteria.get("time_range", "7d"))
        run_types = criteria.get("run_types", ["completed", "failed", "unpublished"])
        
        runs_dir = self.outputs_root / "seasons" / season / "runs"
        if not runs_dir.exists():
            return DeletePlan(
                scope=CleanupScope.RUNS,
                criteria=criteria,
                items=[],
                total_size_bytes=0
            )
        
        items = []
        total_size = 0
        
        # Find runs matching criteria
        for item in runs_dir.iterdir():
            if not item.is_dir():
                continue
            
            item_name = item.name
            
            # Skip artifact directories unless explicitly included
            if item_name.startswith("artifact_") and "published" not in run_types:
                continue
            
            # Check time range
            if not self._matches_time_range(item, time_range):
                continue
            
            # Check run type (simplified - would need actual run status)
            # For now, include all matching directories
            items.append(item)
            total_size += self._get_directory_size(item)
        
        return DeletePlan(
            scope=CleanupScope.RUNS,
            criteria=criteria,
            items=items,
            total_size_bytes=total_size
        )
    
    def _build_published_plan(self, criteria: Dict[str, Any]) -> DeletePlan:
        """Build plan for deleting published results."""
        season = criteria.get("season", self._get_current_season())
        artifact_ids = criteria.get("artifact_ids", [])
        
        runs_dir = self.outputs_root / "seasons" / season / "runs"
        if not runs_dir.exists():
            return DeletePlan(
                scope=CleanupScope.PUBLISHED,
                criteria=criteria,
                items=[],
                total_size_bytes=0
            )
        
        items = []
        total_size = 0
        
        for item in runs_dir.iterdir():
            if not item.is_dir():
                continue
            
            item_name = item.name
            if not item_name.startswith("artifact_"):
                continue
            
            # If specific artifact IDs are specified, check if this one matches
            if artifact_ids and item_name not in artifact_ids:
                continue
            
            items.append(item)
            total_size += self._get_directory_size(item)
        
        return DeletePlan(
            scope=CleanupScope.PUBLISHED,
            criteria=criteria,
            items=items,
            total_size_bytes=total_size
        )
    
    def _build_cache_plan(self, criteria: Dict[str, Any]) -> DeletePlan:
        """Build plan for deleting cache data."""
        season = criteria.get("season", self._get_current_season())
        market = criteria.get("market")
        cache_type = criteria.get("cache_type", "both")  # "bars", "features", "both"
        
        if not market:
            return DeletePlan(
                scope=CleanupScope.CACHE,
                criteria=criteria,
                items=[],
                total_size_bytes=0
            )
        
        shared_dir = self.outputs_root / "seasons" / season / "shared" / market
        if not shared_dir.exists():
            return DeletePlan(
                scope=CleanupScope.CACHE,
                criteria=criteria,
                items=[],
                total_size_bytes=0
            )
        
        items = []
        total_size = 0
        
        # Bars cache
        if cache_type in ["bars", "both"]:
            for bar_file in shared_dir.glob("*.npz"):
                items.append(bar_file)
                total_size += bar_file.stat().st_size
        
        # Features cache
        if cache_type in ["features", "both"]:
            features_dir = shared_dir / "features"
            if features_dir.exists():
                for feature_file in features_dir.rglob("*"):
                    if feature_file.is_file():
                        items.append(feature_file)
                        total_size += feature_file.stat().st_size
        
        return DeletePlan(
            scope=CleanupScope.CACHE,
            criteria=criteria,
            items=items,
            total_size_bytes=total_size
        )
    
    def _build_demo_plan(self, criteria: Dict[str, Any]) -> DeletePlan:
        """Build plan for deleting demo data."""
        # Demo data is tagged with "demo" in run directories
        season = criteria.get("season", self._get_current_season())
        
        runs_dir = self.outputs_root / "seasons" / season / "runs"
        if not runs_dir.exists():
            return DeletePlan(
                scope=CleanupScope.DEMO,
                criteria=criteria,
                items=[],
                total_size_bytes=0
            )
        
        items = []
        total_size = 0
        
        for item in runs_dir.iterdir():
            if not item.is_dir():
                continue
            
            # Check if this is a demo run (simplified check)
            # In practice, would check metadata
            item_name = item.name
            if "demo" in item_name.lower():
                items.append(item)
                total_size += self._get_directory_size(item)
        
        return DeletePlan(
            scope=CleanupScope.DEMO,
            criteria=criteria,
            items=items,
            total_size_bytes=total_size
        )
    
    def _build_trash_purge_plan(self, criteria: Dict[str, Any]) -> DeletePlan:
        """Build plan for permanently deleting trash."""
        time_range = TimeRange(criteria.get("time_range", "all"))
        
        items = []
        total_size = 0
        
        for trash_item in self.trash_root.iterdir():
            if not trash_item.is_dir():
                continue
            
            # Check time range
            if not self._matches_time_range(trash_item, time_range):
                continue
            
            items.append(trash_item)
            total_size += self._get_directory_size(trash_item)
        
        return DeletePlan(
            scope=CleanupScope.TRASH_PURGE,
            criteria=criteria,
            items=items,
            total_size_bytes=total_size
        )
    
    def execute_soft_delete(self, plan: DeletePlan) -> Tuple[bool, str]:
        """
        Execute soft delete (move to trash).
        
        Args:
            plan: Delete plan to execute
            
        Returns:
            Tuple of (success, message)
        """
        if not plan.items:
            return True, "No items to delete"
        
        # Create timestamped trash directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_dir = self.trash_root / f"{plan.scope.value}_{timestamp}"
        trash_dir.mkdir(parents=True, exist_ok=True)
        
        plan.trash_path = trash_dir
        
        moved_count = 0
        failed_items = []
        
        for item in plan.items:
            try:
                # Ensure item is under outputs directory (safety check)
                if not self._is_under_outputs(item):
                    logger.warning(f"Skipping item outside outputs: {item}")
                    failed_items.append(str(item))
                    continue
                
                # Move to trash
                dest = trash_dir / item.relative_to(self.outputs_root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(dest))
                moved_count += 1
                
            except Exception as e:
                logger.error(f"Failed to move {item}: {e}")
                failed_items.append(str(item))
        
        # Create audit log
        self._log_cleanup_action(plan, moved_count, failed_items)
        
        if failed_items:
            return False, f"Moved {moved_count} items, failed: {len(failed_items)}"
        else:
            return True, f"Successfully moved {moved_count} items to trash"
    
    def execute_purge_trash(self, plan: DeletePlan) -> Tuple[bool, str]:
        """
        Permanently delete items from trash.
        
        Args:
            plan: Delete plan for trash purge
            
        Returns:
            Tuple of (success, message)
        """
        if not plan.items:
            return True, "No items to purge"
        
        deleted_count = 0
        failed_items = []
        
        for item in plan.items:
            try:
                # Double-check this is in trash directory
                if not self._is_under_trash(item):
                    logger.warning(f"Skipping item not in trash: {item}")
                    failed_items.append(str(item))
                    continue
                
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                
                deleted_count += 1
                
            except Exception as e:
                logger.error(f"Failed to delete {item}: {e}")
                failed_items.append(str(item))
        
        # Create audit log
        self._log_cleanup_action(plan, deleted_count, failed_items, permanent=True)
        
        if failed_items:
            return False, f"Deleted {deleted_count} items, failed: {len(failed_items)}"
        else:
            return True, f"Successfully permanently deleted {deleted_count} items"
    
    def _get_current_season(self) -> str:
        """Get current season identifier."""
        # Simplified - would need actual season detection
        return "2026Q1"
    
    def _matches_time_range(self, path: Path, time_range: TimeRange) -> bool:
        """Check if path matches time range criteria."""
        if time_range == TimeRange.ALL:
            return True
        
        try:
            mtime = path.stat().st_mtime
            now = datetime.now().timestamp()
            age_seconds = now - mtime
            
            if time_range == TimeRange.LAST_1_HOUR:
                return age_seconds <= 3600
            elif time_range == TimeRange.TODAY:
                # Check if modified today
                mod_date = datetime.fromtimestamp(mtime).date()
                today = datetime.now().date()
                return mod_date == today
            elif time_range == TimeRange.LAST_7_DAYS:
                return age_seconds <= 7 * 24 * 3600
            else:
                return True
        except:
            return False
    
    def _get_directory_size(self, path: Path) -> int:
        """Calculate total size of directory in bytes."""
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except:
            pass
        return total
    
    def _is_under_outputs(self, path: Path) -> bool:
        """Check if path is under outputs directory (safety guardrail)."""
        try:
            return self.outputs_root in path.resolve().parents
        except:
            return False
    
    def _is_under_trash(self, path: Path) -> bool:
        """Check if path is under trash directory."""
        try:
            return self.trash_root in path.resolve().parents
        except:
            return False
    
    def _log_cleanup_action(self, plan: DeletePlan, item_count: int, 
                           failed_items: List[str], permanent: bool = False):
        """Log cleanup action for audit trail."""
        audit_event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "cleanup_trash_purge" if permanent else f"cleanup_{plan.scope.value}",
            "actor": "desktop_cleanup_service",
            "details": {
                "plan": plan.to_dict(),
                "item_count": item_count,
                "failed_items": failed_items[:10],  # Truncate for logging
                "permanent": permanent
            }
        }
        
        # Write to audit log file
        audit_log = self.outputs_root / "_dp_evidence" / "cleanup_audit.jsonl"
        audit_log.parent.mkdir(parents=True, exist_ok=True)
        
        with open(audit_log, "a") as f:
            f.write(json.dumps(audit_event) + "\n")
        
        logger.info(f"Cleanup action logged: {audit_event['event_type']}")


# Convenience functions for common cleanup operations
def cleanup_recent_runs(season: str = None, time_range: str = "7d") -> Tuple[bool, str]:
    """Convenience function to cleanup recent runs."""
    service = CleanupService()
    criteria = {
        "season": season or service._get_current_season(),
        "time_range": time_range,
        "run_types": ["completed", "failed"]
    }
    
    plan = service.build_delete_plan(CleanupScope.RUNS, criteria)
    return service.execute_soft_delete(plan)


def cleanup_cache(market: str, season: str = None, cache_type: str = "both") -> Tuple[bool, str]:
    """Convenience function to cleanup cache."""
    service = CleanupService()
    criteria = {
        "season": season or service._get_current_season(),
        "market": market,
        "cache_type": cache_type
    }
    
    plan = service.build_delete_plan(CleanupScope.CACHE, criteria)
    return service.execute_soft_delete(plan)
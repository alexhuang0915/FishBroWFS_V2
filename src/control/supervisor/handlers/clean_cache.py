from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from ..job_handler import BaseJobHandler, JobContext
from control.artifacts import write_json_atomic
from control.cleanup_service import HeadlessCleanupService, CleanupScope

logger = logging.getLogger(__name__)


class CleanCacheHandler(BaseJobHandler):
    """CLEAN_CACHE handler for cleaning cache data."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate CLEAN_CACHE parameters."""
        # Required: scope
        if "scope" not in params:
            raise ValueError("scope is required")
        
        scope = params["scope"]
        if scope not in ["all", "season", "dataset"]:
            raise ValueError("scope must be one of: 'all', 'season', 'dataset'")
        
        # Validate season parameter when scope is "season"
        if scope == "season":
            if "season" not in params:
                raise ValueError("season is required when scope='season'")
            if not isinstance(params["season"], str):
                raise ValueError("season must be a string")
        
        # Validate dataset_id parameter when scope is "dataset"
        if scope == "dataset":
            if "dataset_id" not in params:
                raise ValueError("dataset_id is required when scope='dataset'")
            if not isinstance(params["dataset_id"], str):
                raise ValueError("dataset_id must be a string")
        
        # Validate dry_run parameter
        if "dry_run" in params:
            if not isinstance(params["dry_run"], bool):
                raise ValueError("dry_run must be a boolean")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute CLEAN_CACHE job."""
        scope = params["scope"]
        dry_run = params.get("dry_run", False)
        season = params.get("season")
        dataset_id = params.get("dataset_id")
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "CLEAN_CACHE",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "dry_run": dry_run,
                "deleted_count": 0
            }
        
        # Use headless cleanup service
        service = HeadlessCleanupService()
        
        # Map scope to cleanup parameters
        if scope == "all":
            # For "all" scope, we need to clean all caches
            # This is more complex - we'll implement a simplified version
            return self._clean_all_caches(context, dry_run)
        elif scope == "season":
            if not season:
                raise ValueError("season is required for scope='season'")
            return self._clean_season_cache(context, season, dry_run)
        elif scope == "dataset":
            if not dataset_id:
                raise ValueError("dataset_id is required for scope='dataset'")
            # Map dataset_id to market (simplified)
            market = self._dataset_to_market(dataset_id)
            return self._clean_market_cache(context, market, season, dry_run, service)
        else:
            raise ValueError(f"Unknown scope: {scope}")
    
    def _clean_all_caches(self, context: JobContext, dry_run: bool) -> Dict[str, Any]:
        """Clean all caches (simplified implementation)."""
        # This is a simplified implementation
        # In production, would need to scan all seasons and markets
        outputs_root = Path("outputs")
        shared_dir = outputs_root / "shared"
        
        if not shared_dir.exists():
            return {
                "ok": True,
                "job_type": "CLEAN_CACHE",
                "dry_run": dry_run,
                "legacy_invocation": "clean_all_caches_fallback",
                "stdout_path": None,
                "stderr_path": None,
                "deleted_count": 0,
                "message": "No shared directory found"
            }
        
        # Count files that would be deleted
        cache_files = list(shared_dir.rglob("*.npz"))
        feature_dirs = list(shared_dir.rglob("features/*"))
        
        total_count = len(cache_files) + len(feature_dirs)
        
        if dry_run:
            return {
                "ok": True,
                "job_type": "CLEAN_CACHE",
                "dry_run": dry_run,
                "legacy_invocation": "clean_all_caches_fallback_dry",
                "stdout_path": None,
                "stderr_path": None,
                "deleted_count": total_count,
                "message": f"Dry run: would delete {total_count} cache items"
            }
        
        # Actually delete (simplified - would need proper error handling)
        deleted = 0
        for file in cache_files:
            try:
                file.unlink()
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete {file}: {e}")
        
        for feature_dir in feature_dirs:
            try:
                if feature_dir.is_dir():
                    import shutil
                    shutil.rmtree(feature_dir)
                    deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete {feature_dir}: {e}")
        
        return {
            "ok": True,
            "job_type": "CLEAN_CACHE",
            "dry_run": dry_run,
            "legacy_invocation": "clean_all_caches_fallback",
            "stdout_path": None,
            "stderr_path": None,
            "deleted_count": deleted,
            "message": f"Deleted {deleted} cache items"
        }
    
    def _clean_season_cache(self, context: JobContext, season: str, dry_run: bool) -> Dict[str, Any]:
        """Clean cache for a specific season."""
        # Simplified implementation
        # In production, would use CleanupService
        outputs_root = Path("outputs")
        season_dir = outputs_root / "seasons" / season / "shared"
        
        if not season_dir.exists():
            return {
                "ok": True,
                "job_type": "CLEAN_CACHE",
                "dry_run": dry_run,
                "legacy_invocation": f"clean_season_cache_{season}",
                "stdout_path": None,
                "stderr_path": None,
                "deleted_count": 0,
                "message": f"No cache found for season {season}"
            }
        
        # Count files
        cache_files = list(season_dir.rglob("*.npz"))
        feature_dirs = list(season_dir.rglob("features/*"))
        total_count = len(cache_files) + len(feature_dirs)
        
        if dry_run:
            return {
                "ok": True,
                "job_type": "CLEAN_CACHE",
                "dry_run": dry_run,
                "legacy_invocation": f"clean_season_cache_{season}_dry",
                "stdout_path": None,
                "stderr_path": None,
                "deleted_count": total_count,
                "message": f"Dry run: would delete {total_count} cache items for season {season}"
            }
        
        # Actually delete
        deleted = 0
        for file in cache_files:
            try:
                file.unlink()
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete {file}: {e}")
        
        for feature_dir in feature_dirs:
            try:
                if feature_dir.is_dir():
                    import shutil
                    shutil.rmtree(feature_dir)
                    deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete {feature_dir}: {e}")
        
        return {
            "ok": True,
            "job_type": "CLEAN_CACHE",
            "dry_run": dry_run,
            "legacy_invocation": f"clean_season_cache_{season}",
            "stdout_path": None,
            "stderr_path": None,
            "deleted_count": deleted,
            "message": f"Deleted {deleted} cache items for season {season}"
        }
    
    def _clean_market_cache(self, context: JobContext, market: str, season: Optional[str], dry_run: bool, service: HeadlessCleanupService) -> Dict[str, Any]:
        """Clean cache for a specific market using headless cleanup service."""
        # Determine season
        if not season:
            season = service._get_current_season()
        
        # Build criteria
        criteria = {
            "season": season,
            "market": market,
            "cache_type": "both"
        }
        
        # Build plan
        plan = service.build_delete_plan(CleanupScope.CACHE, criteria)
        
        if dry_run:
            # Write plan to artifacts for inspection
            plan_json = json.dumps(plan.to_dict(), indent=2)
            plan_path = Path(context.artifacts_dir) / "clean_cache_plan.json"
            plan_path.write_text(plan_json)
            
            return {
                "ok": True,
                "job_type": "CLEAN_CACHE",
                "dry_run": dry_run,
                "legacy_invocation": f"HeadlessCleanupService.cleanup_cache(market={market}, season={season})",
                "stdout_path": str(plan_path),
                "stderr_path": None,
                "deleted_count": len(plan.items),
                "message": f"Dry run: would delete {len(plan.items)} cache items for market {market}, season {season}"
            }
        else:
            # Execute soft delete
            success, message = service.execute_soft_delete(plan)
            
            # Write result to artifacts
            result_path = Path(context.artifacts_dir) / "clean_cache_result.json"
            result_data = {
                "success": success,
                "message": message,
                "plan": plan.to_dict() if plan else None
            }
            write_json_atomic(result_path, result_data)
            
            return {
                "ok": success,
                "job_type": "CLEAN_CACHE",
                "dry_run": dry_run,
                "legacy_invocation": f"HeadlessCleanupService.cleanup_cache(market={market}, season={season})",
                "stdout_path": str(result_path),
                "stderr_path": None,
                "deleted_count": len(plan.items) if plan else 0,
                "message": message
            }
    
    def _clean_market_cache_fallback(self, context: JobContext, market: str, season: Optional[str], dry_run: bool) -> Dict[str, Any]:
        """Fallback implementation for market cache cleaning."""
        outputs_root = Path("outputs")
        
        # Determine season
        if not season:
            season = "2026Q1"  # Default
        
        market_dir = outputs_root / "seasons" / season / "shared" / market
        
        if not market_dir.exists():
            return {
                "ok": True,
                "job_type": "CLEAN_CACHE",
                "dry_run": dry_run,
                "legacy_invocation": f"clean_market_cache_fallback(market={market}, season={season})",
                "stdout_path": None,
                "stderr_path": None,
                "deleted_count": 0,
                "message": f"No cache found for market {market}, season {season}"
            }
        
        # Count files
        cache_files = list(market_dir.glob("*.npz"))
        feature_dir = market_dir / "features"
        feature_files = list(feature_dir.rglob("*")) if feature_dir.exists() else []
        total_count = len(cache_files) + len(feature_files)
        
        if dry_run:
            return {
                "ok": True,
                "job_type": "CLEAN_CACHE",
                "dry_run": dry_run,
                "legacy_invocation": f"clean_market_cache_fallback_dry(market={market}, season={season})",
                "stdout_path": None,
                "stderr_path": None,
                "deleted_count": total_count,
                "message": f"Dry run: would delete {total_count} cache items for market {market}, season {season}"
            }
        
        # Actually delete
        deleted = 0
        for file in cache_files:
            try:
                file.unlink()
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete {file}: {e}")
        
        if feature_dir.exists():
            try:
                import shutil
                shutil.rmtree(feature_dir)
                deleted += 1  # Count as one item
            except Exception as e:
                logger.error(f"Failed to delete feature directory {feature_dir}: {e}")
        
        return {
            "ok": True,
            "job_type": "CLEAN_CACHE",
            "dry_run": dry_run,
            "legacy_invocation": f"clean_market_cache_fallback(market={market}, season={season})",
            "stdout_path": None,
            "stderr_path": None,
            "deleted_count": deleted,
            "message": f"Deleted {deleted} cache items for market {market}, season {season}"
        }
    
    def _dataset_to_market(self, dataset_id: str) -> str:
        """Map dataset_id to market symbol (simplified)."""
        # This is a simplified mapping
        # In production, would need proper mapping from dataset_id to market
        if "ES" in dataset_id or "SPX" in dataset_id:
            return "ES"
        elif "NQ" in dataset_id or "MNQ" in dataset_id:
            return "NQ"
        elif "RTY" in dataset_id:
            return "RTY"
        elif "CL" in dataset_id:
            return "CL"
        else:
            # Default to first part of dataset_id
            return dataset_id.split("_")[0] if "_" in dataset_id else dataset_id
    


# Register handler
clean_cache_handler = CleanCacheHandler()
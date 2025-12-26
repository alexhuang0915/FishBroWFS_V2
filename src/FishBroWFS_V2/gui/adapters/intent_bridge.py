"""IntentBridge - UI adapter for Attack #9 – Headless Intent-State Contract.

UI → Intent ONLY (no logic). This is the only way UI should interact with backend.
UI components must use this bridge to create UserIntent objects and submit them
to the ActionQueue. No business logic should be in UI components.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional, Union, Callable
from functools import wraps

from FishBroWFS_V2.core.intents import (
    Intent, UserIntent, IntentType, IntentStatus,
    CreateJobIntent, CalculateUnitsIntent, CheckSeasonIntent,
    GetJobStatusIntent, ListJobsIntent, GetJobLogsIntent,
    SubmitBatchIntent, ValidatePayloadIntent, BuildParquetIntent,
    FreezeSeasonIntent, ExportSeasonIntent, CompareSeasonsIntent,
    DataSpecIntent
)
from FishBroWFS_V2.control.action_queue import get_action_queue, IntentSubmitter
from FishBroWFS_V2.core.processor import get_processor, start_processor, stop_processor
from FishBroWFS_V2.core.state import SystemState

# Import SeasonFrozenError and ValidationError from job_api for compatibility
try:
    from FishBroWFS_V2.control.job_api import SeasonFrozenError, ValidationError
except ImportError:
    # Fallback definitions if job_api doesn't have them
    class SeasonFrozenError(RuntimeError):
        """Raised when an operation would mutate a frozen season."""
        pass
    
    class ValidationError(Exception):
        """Raised when job validation fails."""
        pass


class IntentBridge:
    """Bridge between UI and intent-based backend.
    
    UI components must use this bridge to interact with backend.
    All methods return intent IDs or results, but never execute business logic.
    """
    
    def __init__(self):
        self.action_queue = get_action_queue()
        self.processor = get_processor()
        self.submitter = IntentSubmitter(self.action_queue)
        self._state_listeners: List[Callable[[SystemState], None]] = []
    
    # -----------------------------------------------------------------
    # Intent creation methods (UI calls these)
    # -----------------------------------------------------------------
    
    def create_data_spec_intent(
        self,
        dataset_id: str,
        symbols: List[str],
        timeframes: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> DataSpecIntent:
        """Create a DataSpecIntent for use in other intents."""
        return DataSpecIntent(
            dataset_id=dataset_id,
            symbols=symbols,
            timeframes=timeframes,
            start_date=start_date,
            end_date=end_date
        )
    
    def create_job_intent(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any],
        wfs: Optional[Dict[str, Any]] = None
    ) -> CreateJobIntent:
        """Create intent to submit a job."""
        if wfs is None:
            wfs = {
                "stage0_subsample": 0.1,
                "top_k": 20,
                "mem_limit_mb": 8192,
                "allow_auto_downsample": True
            }
        
        return CreateJobIntent(
            season=season,
            data1=data1,
            data2=data2,
            strategy_id=strategy_id,
            params=params,
            wfs=wfs
        )
    
    def calculate_units_intent(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any]
    ) -> CalculateUnitsIntent:
        """Create intent to calculate units."""
        return CalculateUnitsIntent(
            season=season,
            data1=data1,
            data2=data2,
            strategy_id=strategy_id,
            params=params
        )
    
    def check_season_intent(
        self,
        season: str,
        action: str = "submit_job"
    ) -> CheckSeasonIntent:
        """Create intent to check if season is frozen."""
        return CheckSeasonIntent(
            season=season,
            action=action
        )
    
    def get_job_status_intent(self, job_id: str) -> GetJobStatusIntent:
        """Create intent to get job status."""
        return GetJobStatusIntent(job_id=job_id)
    
    def list_jobs_intent(self, limit: int = 50) -> ListJobsIntent:
        """Create intent to list jobs."""
        return ListJobsIntent(limit=limit)
    
    def get_job_logs_intent(self, job_id: str, lines: int = 50) -> GetJobLogsIntent:
        """Create intent to get job logs."""
        return GetJobLogsIntent(job_id=job_id, lines=lines)
    
    def validate_payload_intent(self, payload: Dict[str, Any]) -> ValidatePayloadIntent:
        """Create intent to validate wizard payload."""
        return ValidatePayloadIntent(payload=payload)
    
    def build_parquet_intent(self, dataset_id: str) -> BuildParquetIntent:
        """Create intent to build Parquet files."""
        return BuildParquetIntent(dataset_id=dataset_id)
    
    def freeze_season_intent(self, season: str, reason: Optional[str] = None) -> FreezeSeasonIntent:
        """Create intent to freeze a season."""
        return FreezeSeasonIntent(season=season, reason=reason)
    
    def export_season_intent(self, season: str, format: str = "json") -> ExportSeasonIntent:
        """Create intent to export season data."""
        return ExportSeasonIntent(season=season, format=format)
    
    def compare_seasons_intent(
        self,
        season_a: str,
        season_b: str,
        metrics: Optional[List[str]] = None
    ) -> CompareSeasonsIntent:
        """Create intent to compare two seasons."""
        if metrics is None:
            metrics = ["sharpe", "max_dd", "win_rate"]
        return CompareSeasonsIntent(
            season_a=season_a,
            season_b=season_b,
            metrics=metrics
        )
    
    # -----------------------------------------------------------------
    # Intent submission methods (UI calls these)
    # -----------------------------------------------------------------
    
    def submit_intent(self, intent: UserIntent) -> str:
        """Submit an intent to the action queue.
        
        Returns intent ID for tracking.
        """
        return self.action_queue.submit(intent)
    
    def submit_and_wait(
        self,
        intent: UserIntent,
        timeout: Optional[float] = 30.0
    ) -> Optional[UserIntent]:
        """Submit intent and wait for completion.
        
        Returns completed intent with result, or None on timeout.
        """
        return self.submitter.submit_and_wait(intent, timeout)
    
    async def submit_and_wait_async(
        self,
        intent: UserIntent,
        timeout: Optional[float] = 30.0
    ) -> Optional[UserIntent]:
        """Async version of submit_and_wait."""
        return await self.submitter.submit_and_wait_async(intent, timeout)
    
    def get_intent_status(self, intent_id: str) -> Optional[UserIntent]:
        """Get intent status by ID."""
        return self.action_queue.get_intent(intent_id)
    
    async def wait_for_intent(
        self,
        intent_id: str,
        timeout: Optional[float] = 30.0
    ) -> Optional[UserIntent]:
        """Wait for intent completion."""
        return await self.action_queue.wait_for_intent_async(intent_id, timeout)
    
    # -----------------------------------------------------------------
    # State observation methods (UI calls these)
    # -----------------------------------------------------------------
    
    def get_current_state(self) -> SystemState:
        """Get current system state snapshot."""
        return self.processor.get_state()
    
    def add_state_listener(self, callback: Callable[[SystemState], None]) -> None:
        """Add a listener for state changes.
        
        UI components can register callbacks to be notified when state changes.
        """
        self._state_listeners.append(callback)
    
    def remove_state_listener(self, callback: Callable[[SystemState], None]) -> None:
        """Remove a state listener."""
        if callback in self._state_listeners:
            self._state_listeners.remove(callback)
    
    def notify_state_listeners(self, state: SystemState) -> None:
        """Notify all state listeners (called by processor)."""
        for listener in self._state_listeners:
            try:
                listener(state)
            except Exception as e:
                print(f"Error in state listener: {e}")
    
    # -----------------------------------------------------------------
    # System control methods
    # -----------------------------------------------------------------
    
    async def start_processor(self) -> None:
        """Start the StateProcessor."""
        await start_processor()
    
    async def stop_processor(self) -> None:
        """Stop the StateProcessor."""
        await stop_processor()
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get action queue status."""
        metrics = self.action_queue.get_metrics()
        queue_size = self.action_queue.get_queue_size()
        
        return {
            "queue_size": queue_size,
            "metrics": metrics,
            "is_processor_running": self.processor.is_running if hasattr(self.processor, 'is_running') else False
        }
    
    # -----------------------------------------------------------------
    # Convenience methods for common UI patterns
    # -----------------------------------------------------------------
    
    def create_and_submit_job(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any],
        wfs: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """Convenience method: create and submit job intent, wait for result."""
        intent = self.create_job_intent(season, data1, data2, strategy_id, params, wfs)
        completed = self.submit_and_wait(intent, timeout)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result
        return None
    
    async def create_and_submit_job_async(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any],
        wfs: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """Async version of create_and_submit_job."""
        intent = self.create_job_intent(season, data1, data2, strategy_id, params, wfs)
        completed = await self.submit_and_wait_async(intent, timeout)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result
        return None
    
    def calculate_units(
        self,
        season: str,
        data1: DataSpecIntent,
        data2: Optional[DataSpecIntent],
        strategy_id: str,
        params: Dict[str, Any],
        timeout: float = 5.0
    ) -> Optional[int]:
        """Convenience method: calculate units and return result."""
        intent = self.calculate_units_intent(season, data1, data2, strategy_id, params)
        completed = self.submit_and_wait(intent, timeout)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result.get("units") if completed.result else None
        return None


# Singleton instance for application use
_intent_bridge_instance: Optional[IntentBridge] = None


def get_intent_bridge() -> IntentBridge:
    """Get the singleton IntentBridge instance."""
    global _intent_bridge_instance
    if _intent_bridge_instance is None:
        _intent_bridge_instance = IntentBridge()
    return _intent_bridge_instance


# -----------------------------------------------------------------
# Decorators for enforcing UI contract
# -----------------------------------------------------------------

def ui_intent_only(func: Callable) -> Callable:
    """Decorator to enforce that UI methods only create intents.
    
    This is a runtime check to ensure UI components don't accidentally
    call backend logic directly.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check that we're in a UI context (heuristic)
        import inspect
        frame = inspect.currentframe()
        
        # Walk up the call stack looking for UI modules
        while frame:
            module_name = frame.f_globals.get('__name__', '')
            if 'gui' in module_name or 'ui' in module_name:
                # This is called from UI code
                # Check that function name contains 'intent'
                if 'intent' not in func.__name__.lower():
                    print(f"WARNING: UI function {func.__name__} doesn't follow intent-only pattern")
            frame = frame.f_back
        
        return func(*args, **kwargs)
    
    return wrapper


def no_backend_imports() -> None:
    """Check that UI modules don't import backend logic directly.
    
    This should be called at module import time in UI modules.
    """
    import sys
    import inspect
    
    # Get calling module
    frame = inspect.currentframe().f_back
    module_name = frame.f_globals.get('__name__', '')
    
    # Check for forbidden imports in UI modules
    if 'gui' in module_name or 'ui' in module_name:
        forbidden_prefixes = [
            'FishBroWFS_V2.control.job_api',
            'FishBroWFS_V2.control.jobs_db',
            'FishBroWFS_V2.core.processor',  # Except through intent_bridge
        ]
        
        for name, module in sys.modules.items():
            if any(name.startswith(prefix) for prefix in forbidden_prefixes):
                # Check if this module imported it
                for var_name, var_val in frame.f_globals.items():
                    if hasattr(var_val, '__module__') and var_val.__module__ == name:
                        print(f"WARNING: UI module {module_name} imported backend module {name}")
                        break


# -----------------------------------------------------------------
# Compatibility layer for existing UI code
# -----------------------------------------------------------------

class IntentBackendAdapter:
    """Adapter to make intent-based backend compatible with existing UI code.
    
    This provides the same interface as the old job_api.py but uses intents.
    """
    
    def __init__(self, bridge: Optional[IntentBridge] = None):
        self.bridge = bridge or get_intent_bridge()
    
    def create_job_from_wizard(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility method for existing UI code."""
        # Convert payload to DataSpecIntent
        data1 = payload.get("data1", {})
        data2 = payload.get("data2")
        
        data1_intent = self.bridge.create_data_spec_intent(
            dataset_id=data1.get("dataset_id", ""),
            symbols=data1.get("symbols", []),
            timeframes=data1.get("timeframes", []),
            start_date=data1.get("start_date"),
            end_date=data1.get("end_date")
        )
        
        data2_intent = None
        if data2:
            data2_intent = self.bridge.create_data_spec_intent(
                dataset_id=data2.get("dataset_id", ""),
                symbols=[],  # DATA2 doesn't use symbols
                timeframes=[],  # DATA2 doesn't use timeframes
            )
            # Note: DATA2 might have filters, but DataSpecIntent doesn't support them
            # This is a simplification for compatibility
        
        # Create and submit intent
        result = self.bridge.create_and_submit_job(
            season=payload.get("season", ""),
            data1=data1_intent,
            data2=data2_intent,
            strategy_id=payload.get("strategy_id", ""),
            params=payload.get("params", {}),
            wfs=payload.get("wfs")
        )
        
        if result:
            return result
        else:
            raise Exception("Job creation failed")
    
    def calculate_units(self, payload: Dict[str, Any]) -> int:
        """Compatibility method for existing UI code."""
        data1 = payload.get("data1", {})
        data2 = payload.get("data2")
        
        data1_intent = self.bridge.create_data_spec_intent(
            dataset_id=data1.get("dataset_id", ""),
            symbols=data1.get("symbols", []),
            timeframes=data1.get("timeframes", []),
            start_date=data1.get("start_date"),
            end_date=data1.get("end_date")
        )
        
        data2_intent = None
        if data2:
            data2_intent = self.bridge.create_data_spec_intent(
                dataset_id=data2.get("dataset_id", ""),
                symbols=[],
                timeframes=[],
            )
        
        units = self.bridge.calculate_units(
            season=payload.get("season", ""),
            data1=data1_intent,
            data2=data2_intent,
            strategy_id=payload.get("strategy_id", ""),
            params=payload.get("params", {})
        )
        
        if units is not None:
            return units
        else:
            raise Exception("Units calculation failed")
    
    def check_season_not_frozen(self, season: str, action: str = "submit_job") -> None:
        """Compatibility method for existing UI code."""
        intent = self.bridge.check_season_intent(season, action)
        completed = self.bridge.submit_and_wait(intent, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            result = completed.result
            if result and result.get("is_frozen", False):
                from FishBroWFS_V2.control.job_api import SeasonFrozenError
                raise SeasonFrozenError(f"Season {season} is frozen")
        else:
            # If check fails, assume not frozen (fail-open for compatibility)
            pass
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Compatibility method for existing UI code."""
        intent = self.bridge.get_job_status_intent(job_id)
        completed = self.bridge.submit_and_wait(intent, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result or {}
        else:
            raise Exception(f"Failed to get job status: {job_id}")
    
    def list_jobs_with_progress(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Compatibility method for existing UI code."""
        intent = self.bridge.list_jobs_intent(limit)
        completed = self.bridge.submit_and_wait(intent, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            return completed.result.get("jobs", []) if completed.result else []
        else:
            raise Exception("Failed to list jobs")
    
    def get_job_logs_tail(self, job_id: str, lines: int = 50) -> List[str]:
        """Compatibility method for existing UI code."""
        intent = self.bridge.get_job_logs_intent(job_id, lines)
        completed = self.bridge.submit_and_wait(intent, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            # TODO: Convert result to log lines format
            return completed.result.get("logs", []) if completed.result else []
        else:
            raise Exception(f"Failed to get job logs: {job_id}")
    
    def submit_wizard_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility method for existing UI code."""
        return self.create_job_from_wizard(payload)
    
    def get_job_summary(self, job_id: str) -> Dict[str, Any]:
        """Compatibility method for existing UI code."""
        # Combine status and logs
        status = self.get_job_status(job_id)
        logs = self.get_job_logs_tail(job_id, lines=20)
        
        return {
            **status,
            "logs": logs,
            "log_tail": "\n".join(logs[-10:]) if logs else "No logs available"
        }
    
    # -----------------------------------------------------------------
    # Catalog and artifacts API methods
    # -----------------------------------------------------------------
    
    def list_research_units(self, season: str, job_id: str) -> List[Dict[str, Any]]:
        """List research units for a job (artifacts API compatibility)."""
        # For now, directly import and call artifacts_api
        # TODO: Create proper intent for this read-only operation
        from FishBroWFS_V2.control.artifacts_api import list_research_units as _list_research_units
        return _list_research_units(season, job_id)
    
    def get_research_artifacts(self, season: str, job_id: str, unit_key: Dict[str, Any]) -> Dict[str, Any]:
        """Get artifacts for a research unit (artifacts API compatibility)."""
        from FishBroWFS_V2.control.artifacts_api import get_research_artifacts as _get_research_artifacts
        return _get_research_artifacts(season, job_id, unit_key)
    
    def get_portfolio_index(self, season: str, job_id: str) -> Dict[str, Any]:
        """Get portfolio index for a job (artifacts API compatibility)."""
        from FishBroWFS_V2.control.artifacts_api import get_portfolio_index as _get_portfolio_index
        return _get_portfolio_index(season, job_id)
    
    def get_dataset_catalog(self):
        """Get dataset catalog instance (catalog compatibility)."""
        from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog as _get_dataset_catalog
        return _get_dataset_catalog()
    
    def get_strategy_catalog(self):
        """Get strategy catalog instance (catalog compatibility)."""
        from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog as _get_strategy_catalog
        return _get_strategy_catalog()
    
    def get_descriptor(self, dataset_id: str):
        """Get dataset descriptor (dataset_descriptor compatibility)."""
        from FishBroWFS_V2.control.dataset_descriptor import get_descriptor as _get_descriptor
        return _get_descriptor(dataset_id)
    
    def get_paths(self):
        """Get paths module (paths compatibility)."""
        from FishBroWFS_V2.control.paths import get_paths as _get_paths
        return _get_paths()

    def list_descriptors(self):
        """List all dataset descriptors (dataset_descriptor compatibility)."""
        from FishBroWFS_V2.control.dataset_descriptor import list_descriptors as _list_descriptors
        return _list_descriptors()

    def invalidate_feature_cache(self) -> bool:
        """Invalidate feature resolver cache (feature_resolver compatibility)."""
        from FishBroWFS_V2.control.feature_resolver import invalidate_feature_cache as _invalidate_feature_cache
        return _invalidate_feature_cache()

    def build_parquet_from_txt(self, request):
        """Build Parquet from TXT (data_build compatibility)."""
        from FishBroWFS_V2.control.data_build import build_parquet_from_txt as _build_parquet_from_txt
        return _build_parquet_from_txt(request)

    def get_build_parquet_types(self):
        """Get BuildParquetRequest and BuildParquetResult types (data_build compatibility)."""
        from FishBroWFS_V2.control.data_build import BuildParquetRequest, BuildParquetResult
        return BuildParquetRequest, BuildParquetResult


# Create a default adapter instance for easy import
default_adapter = IntentBackendAdapter()


# -----------------------------------------------------------------
# Migration helper for existing UI code
# -----------------------------------------------------------------

def migrate_ui_imports() -> None:
    """Helper to migrate existing UI imports to intent-based system.
    
    Call this in UI modules to replace direct job_api imports with intent bridge.
    """
    import sys
    import inspect
    
    # Get calling module
    frame = inspect.currentframe().f_back
    module = frame.f_globals
    
    # Create adapter instance (always available)
    adapter = IntentBackendAdapter()
    
    # Replace job_api functions with adapter methods
    if 'FishBroWFS_V2.control.job_api' in sys.modules:
        job_api = sys.modules['FishBroWFS_V2.control.job_api']
        
        # Replace functions in calling module's namespace
        module['create_job_from_wizard'] = adapter.create_job_from_wizard
        module['calculate_units'] = adapter.calculate_units
        module['check_season_not_frozen'] = adapter.check_season_not_frozen
        module['get_job_status'] = adapter.get_job_status
        module['list_jobs_with_progress'] = adapter.list_jobs_with_progress
        module['get_job_logs_tail'] = adapter.get_job_logs_tail
        module['submit_wizard_job'] = adapter.submit_wizard_job
        module['get_job_summary'] = adapter.get_job_summary
        
        # Also import exception classes for compatibility
        module['SeasonFrozenError'] = getattr(job_api, 'SeasonFrozenError', Exception)
        module['ValidationError'] = getattr(job_api, 'ValidationError', Exception)
        module['JobAPIError'] = getattr(job_api, 'JobAPIError', Exception)
        
        print(f"Migrated UI module {module.get('__name__', 'unknown')} to intent-based system")
    else:
        # Still provide the adapter methods even if job_api isn't imported
        module['create_job_from_wizard'] = adapter.create_job_from_wizard
        module['calculate_units'] = adapter.calculate_units
        module['check_season_not_frozen'] = adapter.check_season_not_frozen
        module['get_job_status'] = adapter.get_job_status
        module['list_jobs_with_progress'] = adapter.list_jobs_with_progress
        module['get_job_logs_tail'] = adapter.get_job_logs_tail
        module['submit_wizard_job'] = adapter.submit_wizard_job
        module['get_job_summary'] = adapter.get_job_summary
        module['SeasonFrozenError'] = Exception
        module['ValidationError'] = Exception
        module['JobAPIError'] = Exception
    
    # Also provide catalog and artifacts API methods through the adapter
    module['list_research_units'] = adapter.list_research_units
    module['get_research_artifacts'] = adapter.get_research_artifacts
    module['get_portfolio_index'] = adapter.get_portfolio_index
    module['get_dataset_catalog'] = adapter.get_dataset_catalog
    module['get_strategy_catalog'] = adapter.get_strategy_catalog
    module['get_descriptor'] = adapter.get_descriptor
    module['get_paths'] = adapter.get_paths
    module['list_descriptors'] = adapter.list_descriptors
    module['invalidate_feature_cache'] = adapter.invalidate_feature_cache
    module['build_parquet_from_txt'] = adapter.build_parquet_from_txt
    # Also provide type constructors
    BuildParquetRequest, BuildParquetResult = adapter.get_build_parquet_types()
    module['BuildParquetRequest'] = BuildParquetRequest
    module['BuildParquetResult'] = BuildParquetResult
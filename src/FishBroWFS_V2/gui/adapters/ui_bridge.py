"""UI Bridge - HTTP-based adapter for Zero-Violation Split-Brain Architecture.

Replaces Intent Bridge for UI runtime, uses Control API HTTP client.
UI must communicate with Control API only via HTTP, zero direct references to DB/spawn symbols.

This bridge provides the same interface as IntentBackendAdapter but uses HTTP calls.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Union
from datetime import date
from pathlib import Path

from FishBroWFS_V2.gui.adapters.control_client import (
    ControlAPIClient,
    ControlAPIError,
    get_control_client,
)


# Exception classes for compatibility
class SeasonFrozenError(RuntimeError):
    """Raised when an operation would mutate a frozen season."""
    pass


class ValidationError(Exception):
    """Raised when job validation fails."""
    pass


class JobAPIError(Exception):
    """Generic job API error."""
    pass


class WorkerUnavailableError(JobAPIError):
    """Raised when worker is unavailable (HTTP 503)."""
    def __init__(self, detail: str):
        super().__init__(f"Worker unavailable: {detail}")
        self.detail = detail


class DatasetRecord:
    """Simplified dataset record for UI compatibility."""
    
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id", "")
        self.dataset_id = self.id  # alias for compatibility
        self.symbol = data.get("symbol", "")
        self.timeframe = data.get("timeframe", "")
        self.exchange = data.get("exchange", "")
        self.start_date = data.get("start_date", "")
        self.end_date = data.get("end_date", "")
        self.parquet_expected_paths = data.get("parquet_expected_paths", [])
        self.fingerprint = data.get("fingerprint", {})
        # Additional fields required by reload_service tests
        self.kind = data.get("kind", "")
        self.txt_root = data.get("txt_root", "")
        self.txt_required_paths = data.get("txt_required_paths", [])
        self.parquet_root = data.get("parquet_root", "")
    
    def __repr__(self):
        return f"DatasetRecord(id={self.id}, symbol={self.symbol}, timeframe={self.timeframe})"


class StrategySpecForGUI:
    """Simplified strategy spec for UI compatibility."""
    
    def __init__(self, data: Dict[str, Any]):
        self.strategy_id = data.get("strategy_id", "")
        self.params = data.get("params", [])
    
    def __repr__(self):
        return f"StrategySpecForGUI(strategy_id={self.strategy_id}, params={len(self.params)})"


class DatasetCatalog:
    """HTTP-based dataset catalog."""
    
    def __init__(self, client: Optional[ControlAPIClient] = None):
        self.client = client or get_control_client()
        self._datasets: Optional[List[DatasetRecord]] = None
    
    async def _load_datasets(self) -> List[DatasetRecord]:
        """Load datasets from Control API."""
        try:
            response = await self.client.meta_datasets()
            datasets = response.get("datasets", [])
            return [DatasetRecord(d) for d in datasets]
        except ControlAPIError as e:
            # Fallback to empty list
            print(f"Failed to load datasets: {e}")
            return []
    
    async def list_datasets(self) -> List[DatasetRecord]:
        """List all available datasets."""
        if self._datasets is None:
            self._datasets = await self._load_datasets()
        return self._datasets
    
    async def get_dataset(self, dataset_id: str) -> Optional[DatasetRecord]:
        """Get dataset by ID."""
        datasets = await self.list_datasets()
        for dataset in datasets:
            if dataset.id == dataset_id:
                return dataset
        return None
    
    async def list_dataset_ids(self) -> List[str]:
        """Get list of all dataset IDs."""
        datasets = await self.list_datasets()
        return sorted([d.id for d in datasets])
    
    async def describe_dataset(self, dataset_id: str) -> Optional[DatasetRecord]:
        """Get dataset descriptor by ID."""
        return await self.get_dataset(dataset_id)


class StrategyCatalog:
    """HTTP-based strategy catalog."""
    
    def __init__(self, client: Optional[ControlAPIClient] = None):
        self.client = client or get_control_client()
        self._strategies: Optional[List[StrategySpecForGUI]] = None
    
    async def _load_strategies(self) -> List[StrategySpecForGUI]:
        """Load strategies from Control API."""
        try:
            response = await self.client.meta_strategies()
            strategies = response.get("strategies", [])
            return [StrategySpecForGUI(s) for s in strategies]
        except ControlAPIError as e:
            # Fallback to empty list
            print(f"Failed to load strategies: {e}")
            return []
    
    async def list_strategies(self) -> List[StrategySpecForGUI]:
        """List all available strategies for GUI."""
        if self._strategies is None:
            self._strategies = await self._load_strategies()
        return self._strategies
    
    async def get_strategy(self, strategy_id: str) -> Optional[StrategySpecForGUI]:
        """Get strategy by ID for GUI."""
        strategies = await self.list_strategies()
        for strategy in strategies:
            if strategy.strategy_id == strategy_id:
                return strategy
        return None
    
    async def list_strategy_ids(self) -> List[str]:
        """Get list of all strategy IDs."""
        strategies = await self.list_strategies()
        return sorted([s.strategy_id for s in strategies])
    
    async def get_strategy_spec_public(self, strategy_id: str) -> Optional[StrategySpecForGUI]:
        """Public API: Get strategy spec by ID."""
        return await self.get_strategy(strategy_id)


class UIBridge:
    """HTTP-based UI bridge (replaces IntentBackendAdapter)."""
    
    def __init__(self, client: Optional[ControlAPIClient] = None):
        self.client = client or get_control_client()
        self._dataset_catalog: Optional[DatasetCatalog] = None
        self._strategy_catalog: Optional[StrategyCatalog] = None
    
    @property
    def dataset_catalog(self) -> DatasetCatalog:
        """Get dataset catalog instance."""
        if self._dataset_catalog is None:
            self._dataset_catalog = DatasetCatalog(self.client)
        return self._dataset_catalog
    
    @property
    def strategy_catalog(self) -> StrategyCatalog:
        """Get strategy catalog instance."""
        if self._strategy_catalog is None:
            self._strategy_catalog = StrategyCatalog(self.client)
        return self._strategy_catalog
    
    # -----------------------------------------------------------------
    # Core job operations
    # -----------------------------------------------------------------
    
    async def create_job_from_wizard(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a job from wizard payload."""
        # Convert payload to JobSpec format expected by Control API
        spec = self._convert_wizard_payload_to_spec(payload)
        
        try:
            response = await self.client.submit_job(spec)
            job_id = response.get("job_id")
            if not job_id:
                raise JobAPIError("No job_id in response")
            
            # Get job details to return full result
            job = await self.client.get_job(job_id)
            return {
                "job_id": job_id,
                "season": payload.get("season", ""),
                "units": payload.get("units", 0),  # TODO: calculate units
                **job
            }
        except ControlAPIError as e:
            if e.status_code == 422:
                raise ValidationError(f"Invalid payload: {e.detail}")
            elif e.status_code == 403:
                raise SeasonFrozenError(f"Season frozen: {e.detail}")
            elif e.status_code == 503:
                raise WorkerUnavailableError(e.detail)
            else:
                raise JobAPIError(f"Job creation failed: {e.detail}")
    
    async def calculate_units(self, payload: Dict[str, Any]) -> int:
        """Calculate units for wizard payload."""
        # For now, implement simple calculation based on payload
        # This should match the backend's units calculation
        data1 = payload.get("data1", {})
        symbols = data1.get("symbols", [])
        timeframes = data1.get("timeframes", [])
        data2 = payload.get("data2")
        
        symbol_count = len(symbols) if isinstance(symbols, list) else 1
        timeframe_count = len(timeframes) if isinstance(timeframes, list) else 1
        strategy_count = 1  # single strategy
        filter_count = 1 if data2 else 1  # DATA2 filter count
        
        units = symbol_count * timeframe_count * strategy_count * filter_count
        return units
    
    async def check_season_not_frozen(self, season: str, action: str = "submit_job") -> None:
        """Check if season is frozen."""
        try:
            meta = await self.client.get_season_metadata(season)
            if meta.get("frozen", False):
                raise SeasonFrozenError(f"Season {season} is frozen")
        except ControlAPIError as e:
            if e.status_code == 404:
                # Season not found, assume not frozen
                pass
            else:
                raise JobAPIError(f"Failed to check season: {e.detail}")
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get job status."""
        try:
            return await self.client.get_job(job_id)
        except ControlAPIError as e:
            if e.status_code == 404:
                raise JobAPIError(f"Job {job_id} not found")
            raise JobAPIError(f"Failed to get job status: {e.detail}")
    
    async def list_jobs_with_progress(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List jobs with progress information."""
        try:
            jobs = await self.client.list_jobs()
            # Sort by created_at descending (most recent first)
            sorted_jobs = sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)
            return sorted_jobs[:limit]
        except ControlAPIError as e:
            raise JobAPIError(f"Failed to list jobs: {e.detail}")
    
    async def get_job_logs_tail(self, job_id: str, lines: int = 50) -> List[str]:
        """Get job logs tail."""
        try:
            response = await self.client.log_tail(job_id, n=lines)
            return response.get("lines", [])
        except ControlAPIError as e:
            raise JobAPIError(f"Failed to get job logs: {e.detail}")
    
    async def submit_wizard_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit wizard job (alias for create_job_from_wizard)."""
        return await self.create_job_from_wizard(payload)
    
    async def get_job_summary(self, job_id: str) -> Dict[str, Any]:
        """Get job summary (status + logs)."""
        status = await self.get_job_status(job_id)
        logs = await self.get_job_logs_tail(job_id, lines=20)
        
        return {
            **status,
            "logs": logs,
            "log_tail": "\n".join(logs[-10:]) if logs else "No logs available"
        }
    
    # -----------------------------------------------------------------
    # Catalog and artifacts API methods
    # -----------------------------------------------------------------
    
    async def list_research_units(self, season: str, job_id: str) -> List[Dict[str, Any]]:
        """List research units for a job."""
        # TODO: Implement via Control API when endpoint exists
        # For now, return empty list
        return []
    
    async def get_research_artifacts(self, season: str, job_id: str, unit_key: Dict[str, Any]) -> Dict[str, Any]:
        """Get artifacts for a research unit."""
        # TODO: Implement via Control API when endpoint exists
        # For now, return empty dict
        return {}
    
    async def get_portfolio_index(self, season: str, job_id: str) -> Dict[str, Any]:
        """Get portfolio index for a job."""
        # TODO: Implement via Control API when endpoint exists
        # For now, return empty dict
        return {}
    
    async def get_dataset_catalog(self) -> DatasetCatalog:
        """Get dataset catalog instance."""
        return self.dataset_catalog
    
    async def get_strategy_catalog(self) -> StrategyCatalog:
        """Get strategy catalog instance."""
        return self.strategy_catalog
    
    async def get_descriptor(self, dataset_id: str) -> Optional[DatasetRecord]:
        """Get dataset descriptor."""
        catalog = await self.get_dataset_catalog()
        return await catalog.get_dataset(dataset_id)
    
    async def get_paths(self):
        """Get paths module (stub)."""
        # Return a mock object with required attributes
        class MockPaths:
            outputs_root = "outputs"
            artifacts_root = "outputs/artifacts"
            datasets_root = "outputs/datasets"
        
        return MockPaths()
    
    async def list_descriptors(self):
        """List all dataset descriptors."""
        catalog = await self.get_dataset_catalog()
        return await catalog.list_datasets()
    
    async def invalidate_feature_cache(self) -> bool:
        """Invalidate feature resolver cache (stub)."""
        return True
    
    async def build_parquet_from_txt(self, request):
        """Build Parquet from TXT (stub)."""
        # TODO: Implement via Control API when endpoint exists
        raise NotImplementedError("build_parquet_from_txt not implemented in HTTP bridge")
    
    async def get_build_parquet_types(self):
        """Get BuildParquetRequest and BuildParquetResult types (stub)."""
        # Return proper classes with required attributes
        class BuildParquetRequest:
            def __init__(self, dataset_id: str, force: bool = False, deep_validate: bool = False, reason: str = ""):
                self.dataset_id = dataset_id
                self.force = force
                self.deep_validate = deep_validate
                self.reason = reason
        
        class BuildParquetResult:
            def __init__(self, success: bool = True, error: str = None):
                self.success = success
                self.error = error
        
        return BuildParquetRequest, BuildParquetResult
    
    # -----------------------------------------------------------------
    # Helper methods
    # -----------------------------------------------------------------
    
    def _convert_wizard_payload_to_spec(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convert wizard payload to JobSpec format."""
        # This is a simplified conversion; should match the actual JobSpec schema
        data1 = payload.get("data1", {})
        data2 = payload.get("data2")
        
        spec = {
            "season": payload.get("season", ""),
            "data1": {
                "dataset_id": data1.get("dataset_id", ""),
                "symbols": data1.get("symbols", []),
                "timeframes": data1.get("timeframes", []),
                "start_date": data1.get("start_date", ""),
                "end_date": data1.get("end_date", "")
            },
            "strategy_id": payload.get("strategy_id", ""),
            "params": payload.get("params", {}),
            "wfs": payload.get("wfs", {
                "stage0_subsample": 0.1,
                "top_k": 20,
                "mem_limit_mb": 8192,
                "allow_auto_downsample": True
            })
        }
        
        if data2:
            spec["data2"] = {
                "dataset_id": data2.get("dataset_id", ""),
                "filters": data2.get("filters", [])
            }
        
        return spec


# Singleton instance
_ui_bridge_instance: Optional[UIBridge] = None


def get_ui_bridge() -> UIBridge:
    """Get singleton UIBridge instance."""
    global _ui_bridge_instance
    if _ui_bridge_instance is None:
        _ui_bridge_instance = UIBridge()
    return _ui_bridge_instance


# -----------------------------------------------------------------
# Migration helper for existing UI code
# -----------------------------------------------------------------

async def _migrate_ui_imports_async(module_globals=None) -> None:
    """Async helper to migrate existing UI imports to HTTP-based system.
    
    Call this in UI modules to replace direct job_api imports with HTTP bridge.
    
    Args:
        module_globals: The globals() dict of the module to migrate.
                        If None, uses the caller's globals.
    """
    import sys
    import inspect
    
    # Determine target module
    if module_globals is None:
        frame = inspect.currentframe().f_back
        module_globals = frame.f_globals
    module_name = module_globals.get('__name__', 'unknown')
    module_file = module_globals.get('__file__', 'no file')
    print(f"DEBUG: Migrating module {module_name} from {module_file}")
    
    # Create bridge instance
    bridge = get_ui_bridge()
    
    # Replace functions in calling module's namespace
    # Note: UI functions need to be async, but existing UI code expects sync functions.
    # We'll create async wrappers that run in event loop.
    # For simplicity, we'll provide sync versions that run async functions.
    # This is a temporary compatibility layer.
    
    # Create sync wrappers that run async functions in event loop
    import asyncio
    
    def run_async(coro):
        """Run async coroutine in existing event loop or create new one."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            # We're in async context, can't run sync
            # Return a coroutine that the caller must await
            async def wrapper():
                return await coro
            return wrapper()
        else:
            return loop.run_until_complete(coro)
    
    # Sync wrapper functions
    def create_job_from_wizard_sync(payload: Dict[str, Any]) -> Dict[str, Any]:
        return run_async(bridge.create_job_from_wizard(payload))
    
    def calculate_units_sync(payload: Dict[str, Any]) -> int:
        return run_async(bridge.calculate_units(payload))
    
    def check_season_not_frozen_sync(season: str, action: str = "submit_job") -> None:
        return run_async(bridge.check_season_not_frozen(season, action))
    
    def get_job_status_sync(job_id: str) -> Dict[str, Any]:
        return run_async(bridge.get_job_status(job_id))
    
    def list_jobs_with_progress_sync(limit: int = 50) -> List[Dict[str, Any]]:
        return run_async(bridge.list_jobs_with_progress(limit))
    
    def get_job_logs_tail_sync(job_id: str, lines: int = 50) -> List[str]:
        return run_async(bridge.get_job_logs_tail(job_id, lines))
    
    def submit_wizard_job_sync(payload: Dict[str, Any]) -> Dict[str, Any]:
        return run_async(bridge.submit_wizard_job(payload))
    
    def get_job_summary_sync(job_id: str) -> Dict[str, Any]:
        return run_async(bridge.get_job_summary(job_id))
    
    # Catalog sync wrappers
    def get_dataset_catalog_sync():
        return run_async(bridge.get_dataset_catalog())
    
    def get_strategy_catalog_sync():
        return run_async(bridge.get_strategy_catalog())
    
    def get_descriptor_sync(dataset_id: str):
        return run_async(bridge.get_descriptor(dataset_id))
    
    def list_descriptors_sync():
        return run_async(bridge.list_descriptors())
    
    # Replace module functions
    module_globals['create_job_from_wizard'] = create_job_from_wizard_sync
    module_globals['calculate_units'] = calculate_units_sync
    module_globals['check_season_not_frozen'] = check_season_not_frozen_sync
    module_globals['get_job_status'] = get_job_status_sync
    module_globals['list_jobs_with_progress'] = list_jobs_with_progress_sync
    module_globals['get_job_logs_tail'] = get_job_logs_tail_sync
    module_globals['submit_wizard_job'] = submit_wizard_job_sync
    module_globals['get_job_summary'] = get_job_summary_sync
    module_globals['get_dataset_catalog'] = get_dataset_catalog_sync
    module_globals['get_strategy_catalog'] = get_strategy_catalog_sync
    module_globals['get_descriptor'] = get_descriptor_sync
    module_globals['list_descriptors'] = list_descriptors_sync
    
    # Exception classes
    module_globals['SeasonFrozenError'] = SeasonFrozenError
    module_globals['ValidationError'] = ValidationError
    module_globals['JobAPIError'] = JobAPIError
    
    # Also provide catalog and artifacts API methods (stubs)
    module_globals['list_research_units'] = lambda season, job_id: []
    module_globals['get_research_artifacts'] = lambda season, job_id, unit_key: {}
    module_globals['get_portfolio_index'] = lambda season, job_id: {}
    module_globals['invalidate_feature_cache'] = lambda: True
    module_globals['build_parquet_from_txt'] = lambda request: None
    # Define MockPaths class for get_paths
    class MockPaths:
        outputs_root = "outputs"
        artifacts_root = "outputs/artifacts"
        datasets_root = "outputs/datasets"
    module_globals['get_paths'] = lambda: MockPaths()
    
    # Type constructors
    BuildParquetRequest, BuildParquetResult = await bridge.get_build_parquet_types()
    module_globals['BuildParquetRequest'] = BuildParquetRequest
    module_globals['BuildParquetResult'] = BuildParquetResult
    
    print(f"Migrated UI module {module_globals.get('__name__', 'unknown')} to HTTP-based system")


# Sync version for compatibility with existing UI code
def migrate_ui_imports_sync(module_globals=None) -> None:
    """Sync version of migrate_ui_imports."""
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # Can't run sync in async context, schedule async migration
        async def async_migrate():
            await _migrate_ui_imports_async(module_globals)
        # This will cause issues but we'll try to run anyway
        loop.create_task(async_migrate())
    else:
        loop.run_until_complete(_migrate_ui_imports_async(module_globals))


# Default export for backward compatibility
def migrate_ui_imports(module_globals=None):
    """Migrate UI imports to HTTP-based system.
    
    This is the main entry point for UI modules.
    """
    return migrate_ui_imports_sync(module_globals)
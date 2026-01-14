"""
Registry Surface Defensive Adapter.

Provides a single adapter layer (UI-side) that wraps SupervisorClient calls for Registry Surface.
The UI must never call SupervisorClient raw methods directly for Registry Surface.

Adapter responsibilities:
- Provide a method: fetch_registry_surface() (or similarly named)
- Internally:
  - Prefer known canonical method name if exists.
  - If method missing: return a typed failure result (NOT throw).
  - Catch AttributeError, TypeError, and network errors.
  - Return GateStatus(level="FAIL" or "WARNING", title="Registry Surface", detail="Unknown: client method missing")
- Ensure callers never crash.

UI mapping:
- Registry Surface panel:
  - When adapter returns unknown/unavailable => show grey/unknown state, not crash.
- Overall gates summary can still mark FAIL, but app continues.
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

from gui.services.supervisor_client import SupervisorClient, SupervisorClientError
from gui.services.gate_summary_service import GateStatus as GateStatusEnum, GateResult

logger = logging.getLogger(__name__)


class RegistryStatus(str, Enum):
    """Status of registry surface."""
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegistrySurfaceResult:
    """Result of registry surface check."""
    status: RegistryStatus
    timeframes: List[str]
    datasets: List[str]
    strategies: List[str]
    instruments: List[str]
    error: Optional[str] = None
    missing_methods: List[str] = None
    
    def __post_init__(self):
        if self.missing_methods is None:
            self.missing_methods = []


class RegistrySurfaceAdapter:
    """Defensive adapter for registry surface calls."""
    
    def __init__(self, client: Optional[SupervisorClient] = None):
        self.client = client or SupervisorClient()
    
    def fetch_registry_surface(self) -> RegistrySurfaceResult:
        """
        Fetch registry surface data with defensive error handling.
        
        Returns:
            RegistrySurfaceResult with status and data (or error)
        """
        missing_methods = []
        timeframes = []
        datasets = []
        strategies = []
        instruments = []
        
        # Try to fetch timeframes with defensive check
        try:
            if hasattr(self.client, 'get_registry_timeframes'):
                timeframes = self.client.get_registry_timeframes()
            else:
                missing_methods.append('get_registry_timeframes')
                # Try direct endpoint as fallback
                try:
                    timeframes = self.client._get("/api/v1/registry/timeframes")
                except Exception as e:
                    logger.warning(f"Failed to fetch timeframes via direct endpoint: {e}")
        except (AttributeError, SupervisorClientError, Exception) as e:
            logger.warning(f"Failed to fetch timeframes: {e}")
            missing_methods.append('get_registry_timeframes')
        
        # Try to fetch datasets
        try:
            if hasattr(self.client, 'get_registry_datasets'):
                datasets = self.client.get_registry_datasets()
            else:
                missing_methods.append('get_registry_datasets')
        except (AttributeError, SupervisorClientError, Exception) as e:
            logger.warning(f"Failed to fetch datasets: {e}")
            missing_methods.append('get_registry_datasets')
        
        # Try to fetch strategies
        try:
            if hasattr(self.client, 'get_registry_strategies'):
                strategies_raw = self.client.get_registry_strategies()
                # Convert to list of IDs if needed
                if strategies_raw and isinstance(strategies_raw, list):
                    if isinstance(strategies_raw[0], dict):
                        strategies = [s.get('id', str(s)) for s in strategies_raw]
                    else:
                        strategies = [str(s) for s in strategies_raw]
            else:
                missing_methods.append('get_registry_strategies')
        except (AttributeError, SupervisorClientError, Exception) as e:
            logger.warning(f"Failed to fetch strategies: {e}")
            missing_methods.append('get_registry_strategies')
        
        # Try to fetch instruments
        try:
            if hasattr(self.client, 'get_registry_instruments'):
                instruments = self.client.get_registry_instruments()
            else:
                missing_methods.append('get_registry_instruments')
        except (AttributeError, SupervisorClientError, Exception) as e:
            logger.warning(f"Failed to fetch instruments: {e}")
            missing_methods.append('get_registry_instruments')
        
        # Determine overall status
        if missing_methods:
            if len(missing_methods) == 4:  # All methods missing
                status = RegistryStatus.UNAVAILABLE
                error = f"Registry surface unavailable: missing methods {missing_methods}"
            else:
                status = RegistryStatus.PARTIAL
                error = f"Registry surface partially available: missing {missing_methods}"
        else:
            # Check if any registry is empty (might indicate issues)
            if not any([timeframes, datasets, strategies, instruments]):
                status = RegistryStatus.PARTIAL  # Empty registry is partial/warning
                error = "Registry surface endpoints returned empty data"
            else:
                status = RegistryStatus.AVAILABLE
                error = None
        
        return RegistrySurfaceResult(
            status=status,
            timeframes=timeframes if isinstance(timeframes, list) else [],
            datasets=datasets if isinstance(datasets, list) else [],
            strategies=strategies if isinstance(strategies, list) else [],
            instruments=instruments if isinstance(instruments, list) else [],
            error=error,
            missing_methods=missing_methods
        )
    
    def to_gate_result(self, result: RegistrySurfaceResult) -> GateResult:
        """
        Convert RegistrySurfaceResult to GateResult for gate summary.
        
        This ensures the gate summary service can use the adapter's result
        without crashing due to missing methods.
        """
        from datetime import datetime, timezone
        
        if result.status == RegistryStatus.AVAILABLE:
            # Count total items
            total_items = len(result.timeframes) + len(result.datasets) + len(result.strategies) + len(result.instruments)
            return GateResult(
                gate_id="registry_surface",
                gate_name="Registry Surface",
                status=GateStatusEnum.PASS,
                message=f"Registry surface accessible with {total_items} total items.",
                details={
                    "timeframes_count": len(result.timeframes),
                    "datasets_count": len(result.datasets),
                    "strategies_count": len(result.strategies),
                    "instruments_count": len(result.instruments),
                    "status": result.status.value
                },
                actions=[{"label": "View Registry", "url": "/api/v1/registry/timeframes"}],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        elif result.status == RegistryStatus.PARTIAL:
            # Check if it's partial due to empty data vs missing methods
            if result.error and "empty" in result.error.lower():
                return GateResult(
                    gate_id="registry_surface",
                    gate_name="Registry Surface",
                    status=GateStatusEnum.WARN,
                    message="Registry surface accessible but empty (no timeframes).",
                    details={
                        "timeframes_count": len(result.timeframes),
                        "datasets_count": len(result.datasets),
                        "strategies_count": len(result.strategies),
                        "instruments_count": len(result.instruments),
                        "status": result.status.value,
                        "error": result.error
                    },
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return GateResult(
                    gate_id="registry_surface",
                    gate_name="Registry Surface",
                    status=GateStatusEnum.WARN,
                    message=f"Registry surface partially available: missing {result.missing_methods}",
                    details={
                        "missing_methods": result.missing_methods,
                        "error": result.error,
                        "status": result.status.value
                    },
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        else:  # UNAVAILABLE or UNKNOWN
            return GateResult(
                gate_id="registry_surface",
                gate_name="Registry Surface",
                status=GateStatusEnum.FAIL,
                message=f"Registry surface unavailable: {result.error or 'Unknown error'}",
                details={
                    "missing_methods": result.missing_methods,
                    "error": result.error,
                    "status": result.status.value
                },
                timestamp=datetime.now(timezone.utc).isoformat(),
            )


# Singleton instance for convenience
_registry_adapter = RegistrySurfaceAdapter()


def get_registry_adapter() -> RegistrySurfaceAdapter:
    """Return the singleton registry surface adapter instance."""
    return _registry_adapter


def fetch_registry_surface() -> RegistrySurfaceResult:
    """Convenience function to fetch registry surface using the singleton."""
    return _registry_adapter.fetch_registry_surface()


def fetch_registry_gate_result() -> GateResult:
    """Convenience function to get gate result for registry surface."""
    result = fetch_registry_surface()
    return _registry_adapter.to_gate_result(result)
"""
Dataset Resolver for Derived Field Mapping.

Implements the dataset derivation contract: users do NOT manually select datasets;
UI MUST show the derived mapping transparently ("Mapped to: …").

This resolver accepts (strategy_id, instrument_id, timeframe_id, mode, season)
and returns DerivedDatasets with DATA1/DATA2 IDs, statuses, and mapping reason.

Rules:
- Users do not select dataset IDs; only derived.
- Derivation must be transparent: return mapping_reason string.
- If no mapping found: dataset_id = None, status=UNKNOWN/MISSING.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Literal
from datetime import datetime
import logging

from config.registry.strategy_catalog import load_strategy_catalog, StrategyCatalogEntry
from config.registry.datasets import load_datasets, DatasetSpec
from config.registry.timeframes import load_timeframes

logger = logging.getLogger(__name__)


class DatasetStatus(str, Enum):
    """Status of a dataset."""
    READY = "READY"
    MISSING = "MISSING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DerivedDatasets:
    """Output model for dataset derivation."""
    data1_id: Optional[str]
    data2_id: Optional[str]
    mapping_reason: str  # e.g., "Mapped by instrument+timeframe+mode"
    data1_status: DatasetStatus
    data2_status: DatasetStatus
    data1_min_date: Optional[str] = None  # ISO date
    data1_max_date: Optional[str] = None
    data2_min_date: Optional[str] = None
    data2_max_date: Optional[str] = None


@dataclass(frozen=True)
class GateStatus:
    """UI gate evaluation structure."""
    level: Literal["PASS", "WARNING", "FAIL"]
    title: str
    detail: str


class DatasetResolver:
    """Resolves datasets from instrument/timeframe/mode/strategy."""
    
    def __init__(self):
        self.strategy_catalog = load_strategy_catalog()
        self.dataset_registry = load_datasets()
        self.timeframe_registry = load_timeframes()
    
    def resolve(
        self,
        strategy_id: str,
        instrument_id: str,
        timeframe_id: str,
        mode: str,
        season: Optional[str] = None
    ) -> DerivedDatasets:
        """
        Resolve DATA1 and DATA2 dataset IDs based on repository registry rules.
        
        Args:
            strategy_id: Strategy identifier
            instrument_id: Instrument identifier (e.g., "CME.MNQ")
            timeframe_id: Timeframe identifier (e.g., "60")
            mode: Run mode (e.g., "research", "production")
            season: Optional season identifier
            
        Returns:
            DerivedDatasets with resolved IDs and statuses
        """
        # Get strategy metadata
        strategy_entry = self.strategy_catalog.get_strategy_by_id(strategy_id)
        
        # Default mapping reason
        mapping_reason = f"Mapped by instrument={instrument_id}, timeframe={timeframe_id}, mode={mode}"
        if season:
            mapping_reason += f", season={season}"
        
        # Resolve DATA1 (primary dataset)
        data1_id = self._resolve_data1(instrument_id, timeframe_id, mode, season)
        data1_status = self._check_dataset_status(data1_id)
        
        # Resolve DATA2 (secondary dataset) - may be None
        data2_id = self._resolve_data2(strategy_entry, instrument_id, timeframe_id, mode, season)
        data2_status = self._check_dataset_status(data2_id)
        
        # Get date ranges if dataset exists
        data1_min_date, data1_max_date = self._get_dataset_date_range(data1_id) if data1_id else (None, None)
        data2_min_date, data2_max_date = self._get_dataset_date_range(data2_id) if data2_id else (None, None)
        
        return DerivedDatasets(
            data1_id=data1_id,
            data2_id=data2_id,
            mapping_reason=mapping_reason,
            data1_status=data1_status,
            data2_status=data2_status,
            data1_min_date=data1_min_date,
            data1_max_date=data1_max_date,
            data2_min_date=data2_min_date,
            data2_max_date=data2_max_date,
        )
    
    def _resolve_data1(
        self,
        instrument_id: str,
        timeframe_id: str,
        mode: str,
        season: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve DATA1 dataset ID.
        
        Implementation logic:
        1. Look for dataset registry entry matching instrument+timeframe
        2. Fallback to pattern: f"{instrument_id}.{timeframe_id}m"
        3. If season provided, incorporate season into pattern
        """
        # Convert timeframe_id to int for comparison
        try:
            timeframe_int = int(timeframe_id)
        except ValueError:
            timeframe_int = 60  # default
        
        # Try to find dataset in registry
        for dataset in self.dataset_registry.datasets:
            if (dataset.instrument_id == instrument_id and
                dataset.timeframe == timeframe_int):
                return dataset.id
        
        # Fallback pattern
        if season:
            return f"{instrument_id}.{timeframe_id}m.{season}"
        else:
            return f"{instrument_id}.{timeframe_id}m"
    
    def _resolve_data2(
        self,
        strategy_entry: Optional[StrategyCatalogEntry],
        instrument_id: str,
        timeframe_id: str,
        mode: str,
        season: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve DATA2 dataset ID.
        
        Rules:
        - If strategy requires DATA2, try to find a secondary dataset
        - If strategy doesn't require DATA2, return None
        - If strategy entry is None (unknown), assume requires DATA2 (safe default)
        """
        # Determine if strategy requires DATA2
        requires_data2 = True  # safe default
        if strategy_entry:
            requires_data2 = strategy_entry.requires_secondary_data
        
        if not requires_data2:
            return None
        
        # Convert timeframe_id to int for comparison
        try:
            timeframe_int = int(timeframe_id)
        except ValueError:
            timeframe_int = 60  # default
        
        # Try to find a secondary dataset (e.g., correlated instrument)
        # This is a simplified implementation - in production would use correlation mapping
        secondary_instrument = self._get_secondary_instrument(instrument_id)
        if secondary_instrument:
            # Try to find dataset in registry
            for dataset in self.dataset_registry.datasets:
                if (dataset.instrument_id == secondary_instrument and
                    dataset.timeframe == timeframe_int):
                    return dataset.id
            
            # Fallback pattern
            if season:
                return f"{secondary_instrument}.{timeframe_id}m.{season}"
            else:
                return f"{secondary_instrument}.{timeframe_id}m"
        
        return None
    
    def _get_secondary_instrument(self, primary_instrument: str) -> Optional[str]:
        """
        Map primary instrument to secondary (correlated) instrument.
        Simplified mapping for demonstration.
        """
        mapping = {
            "CME.MNQ": "CME.ES",  # NQ to ES correlation
            "CME.ES": "CME.NQ",
            "TWF.MXF": "CME.MNQ",  # Taiwan futures to MNQ
        }
        return mapping.get(primary_instrument)
    
    def _check_dataset_status(self, dataset_id: Optional[str]) -> DatasetStatus:
        """Check status of a dataset."""
        if dataset_id is None:
            return DatasetStatus.UNKNOWN
        
        # Check if dataset exists in registry
        dataset_exists = any(d.id == dataset_id for d in self.dataset_registry.datasets)
        if not dataset_exists:
            return DatasetStatus.MISSING
        
        # Simplified status check - in production would check freshness, etc.
        # For now, assume READY if exists
        return DatasetStatus.READY
    
    def _get_dataset_date_range(self, dataset_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Get date range for a dataset."""
        if dataset_id is None:
            return None, None
        
        # Look up dataset in registry
        for dataset in self.dataset_registry.datasets:
            if dataset.id == dataset_id:
                # DatasetSpec has date_range as string like "2020-2024"
                # For simplicity, return the date_range string as both min and max
                # In a real implementation, we would parse the string
                return dataset.date_range, dataset.date_range
        
        return None, None
    
    def evaluate_data2_gate(
        self,
        strategy_id: str,
        instrument_id: str,
        timeframe_id: str,
        mode: str,
        season: Optional[str] = None
    ) -> GateStatus:
        """
        Evaluate DATA2 gate according to Red Team Option C (AUTO/strategy-dependent).
        
        Rules:
        - IF requires_secondary_data is True:
            - DATA2 status == READY => PASS
            - DATA2 status == STALE => WARNING
            - DATA2 status in (MISSING, UNKNOWN) => FAIL
        - IF requires_secondary_data is False:
            - PASS regardless of DATA2 status
        - IF dependency not declared (cannot determine):
            - treat as requires=True (safe default), apply above.
        """
        # Get strategy metadata
        strategy_entry = self.strategy_catalog.get_strategy_by_id(strategy_id)
        
        # Determine dependency
        requires_data2 = True  # safe default
        if strategy_entry:
            requires_data2 = strategy_entry.requires_secondary_data
        
        # Resolve datasets
        derived = self.resolve(strategy_id, instrument_id, timeframe_id, mode, season)
        
        # Apply gate logic
        if not requires_data2:
            return GateStatus(
                level="PASS",
                title="DATA2 Gate",
                detail=f"Strategy {strategy_id} does not require DATA2. Gate passes regardless of DATA2 status."
            )
        
        # Strategy requires DATA2
        if derived.data2_status == DatasetStatus.READY:
            return GateStatus(
                level="PASS",
                title="DATA2 Gate",
                detail=f"DATA2 required and ready: {derived.data2_id}"
            )
        elif derived.data2_status == DatasetStatus.STALE:
            return GateStatus(
                level="WARNING",
                title="DATA2 Gate",
                detail=f"DATA2 required but stale: {derived.data2_id}"
            )
        elif derived.data2_status in (DatasetStatus.MISSING, DatasetStatus.UNKNOWN):
            return GateStatus(
                level="FAIL",
                title="DATA2 Gate",
                detail=f"DATA2 required but missing/unknown: {derived.data2_id or 'No dataset found'}"
            )
        else:
            # Should not happen
            return GateStatus(
                level="FAIL",
                title="DATA2 Gate",
                detail=f"Unexpected DATA2 status: {derived.data2_status}"
            )
    
    def evaluate_run_readiness(
        self,
        strategy_id: str,
        instrument_id: str,
        timeframe_id: str,
        mode: str,
        season: Optional[str] = None
    ) -> GateStatus:
        """
        Evaluate overall run readiness considering both DATA1 and DATA2.
        
        Rules (Route 4):
        1. DATA1 must be READY (FAIL if not)
        2. DATA2 evaluated per Option C rules (evaluate_data2_gate)
        3. Overall status is the worst of the two evaluations
        
        Returns:
            GateStatus with overall readiness assessment
        """
        # Resolve datasets
        derived = self.resolve(strategy_id, instrument_id, timeframe_id, mode, season)
        
        # Evaluate DATA1
        data1_gate = self._evaluate_data1_gate(derived)
        
        # Evaluate DATA2
        data2_gate = self.evaluate_data2_gate(strategy_id, instrument_id, timeframe_id, mode, season)
        
        # Determine overall status (worst of the two)
        gate_levels = {"PASS": 0, "WARNING": 1, "FAIL": 2}
        data1_level = gate_levels[data1_gate.level]
        data2_level = gate_levels[data2_gate.level]
        overall_level = max(data1_level, data2_level)
        
        # Map back to level string
        level_map = {0: "PASS", 1: "WARNING", 2: "FAIL"}
        overall_level_str = level_map[overall_level]
        
        # Build combined detail
        detail = f"DATA1: {data1_gate.detail}\nDATA2: {data2_gate.detail}"
        
        return GateStatus(
            level=overall_level_str,
            title="Run Readiness Gate",
            detail=detail
        )
    
    def evaluate_run_readiness_with_prepare_status(
        self,
        strategy_id: str,
        instrument_id: str,
        timeframe_id: str,
        mode: str,
        season: Optional[str] = None
    ) -> GateStatus:
        """
        Evaluate run readiness considering both dataset status AND prepare status.
        
        This is the final gate that should be used to enable/disable Run button.
        
        Additional rules:
        - If any dataset is PREPARING: FAIL (cannot run while preparing)
        - If any dataset is FAILED: FAIL (must retry or clear failed status)
        - Otherwise use normal run readiness evaluation
        """
        # Import here to avoid circular imports
        from gui.services.data_prepare_service import get_data_prepare_service, PrepareStatus
        
        # Resolve datasets
        derived = self.resolve(strategy_id, instrument_id, timeframe_id, mode, season)
        
        # Check prepare status for DATA1 and DATA2
        data_prepare_service = get_data_prepare_service()
        
        # Check DATA1 prepare status
        data1_prepare_status = data_prepare_service.get_prepare_status("DATA1")
        data2_prepare_status = data_prepare_service.get_prepare_status("DATA2")
        
        # Build prepare status details
        prepare_details = []
        
        # Check DATA1 prepare status
        if data1_prepare_status == PrepareStatus.PREPARING:
            return GateStatus(
                level="FAIL",
                title="Run Readiness Gate",
                detail=f"DATA1 is currently being prepared. Wait for preparation to complete or cancel it."
            )
        elif data1_prepare_status == PrepareStatus.FAILED:
            return GateStatus(
                level="FAIL",
                title="Run Readiness Gate",
                detail=f"DATA1 preparation failed. Click 'Retry' in Data Prepare panel."
            )
        elif data1_prepare_status:
            prepare_details.append(f"DATA1 prepare status: {data1_prepare_status.value}")
        
        # Check DATA2 prepare status (if dataset exists)
        if derived.data2_id:
            if data2_prepare_status == PrepareStatus.PREPARING:
                return GateStatus(
                    level="FAIL",
                    title="Run Readiness Gate",
                    detail=f"DATA2 is currently being prepared. Wait for preparation to complete or cancel it."
                )
            elif data2_prepare_status == PrepareStatus.FAILED:
                return GateStatus(
                    level="FAIL",
                    title="Run Readiness Gate",
                    detail=f"DATA2 preparation failed. Click 'Retry' in Data Prepare panel."
                )
            elif data2_prepare_status:
                prepare_details.append(f"DATA2 prepare status: {data2_prepare_status.value}")
        
        # If no prepare issues, evaluate normal run readiness
        base_gate = self.evaluate_run_readiness(strategy_id, instrument_id, timeframe_id, mode, season)
        
        # Add prepare status details if any
        if prepare_details:
            detail = f"{base_gate.detail}\nPrepare Status: {'; '.join(prepare_details)}"
            return GateStatus(
                level=base_gate.level,
                title=base_gate.title,
                detail=detail
            )
        
        return base_gate
    
    def _evaluate_data1_gate(self, derived: DerivedDatasets) -> GateStatus:
        """Evaluate DATA1 gate (must be READY)."""
        if derived.data1_status == DatasetStatus.READY:
            return GateStatus(
                level="PASS",
                title="DATA1 Gate",
                detail=f"DATA1 ready: {derived.data1_id}"
            )
        elif derived.data1_status == DatasetStatus.STALE:
            return GateStatus(
                level="FAIL",  # DATA1 STALE is FAIL (not WARNING like DATA2)
                title="DATA1 Gate",
                detail=f"DATA1 stale: {derived.data1_id}"
            )
        elif derived.data1_status in (DatasetStatus.MISSING, DatasetStatus.UNKNOWN):
            return GateStatus(
                level="FAIL",
                title="DATA1 Gate",
                detail=f"DATA1 missing/unknown: {derived.data1_id or 'No dataset found'}"
            )
        else:
            return GateStatus(
                level="FAIL",
                title="DATA1 Gate",
                detail=f"Unexpected DATA1 status: {derived.data1_status}"
            )


# Singleton instance for convenience
_dataset_resolver = DatasetResolver()


def get_dataset_resolver() -> DatasetResolver:
    """Return the singleton dataset resolver instance."""
    return _dataset_resolver


def resolve_datasets(
    strategy_id: str,
    instrument_id: str,
    timeframe_id: str,
    mode: str,
    season: Optional[str] = None
) -> DerivedDatasets:
    """Convenience function to resolve datasets using the singleton."""
    return _dataset_resolver.resolve(strategy_id, instrument_id, timeframe_id, mode, season)


def evaluate_data2_gate(
    strategy_id: str,
    instrument_id: str,
    timeframe_id: str,
    mode: str,
    season: Optional[str] = None
) -> GateStatus:
    """Convenience function to evaluate DATA2 gate using the singleton."""
    return _dataset_resolver.evaluate_data2_gate(strategy_id, instrument_id, timeframe_id, mode, season)


def evaluate_run_readiness(
    strategy_id: str,
    instrument_id: str,
    timeframe_id: str,
    mode: str,
    season: Optional[str] = None
) -> GateStatus:
    """Convenience function to evaluate overall run readiness using the singleton."""
    return _dataset_resolver.evaluate_run_readiness(strategy_id, instrument_id, timeframe_id, mode, season)


def evaluate_run_readiness_with_prepare_status(
    strategy_id: str,
    instrument_id: str,
    timeframe_id: str,
    mode: str,
    season: Optional[str] = None
) -> GateStatus:
    """Convenience function to evaluate run readiness with prepare status using the singleton."""
    return _dataset_resolver.evaluate_run_readiness_with_prepare_status(
        strategy_id, instrument_id, timeframe_id, mode, season
    )
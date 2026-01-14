"""
Consolidated Gate Summary Service v1.

Fetches gates from multiple sources and presents a unified GateSummaryV1
that complies with Hybrid BC v1.1 (no performance metrics in Layer1/Layer2).

Sources:
1. System Health Gates (from gate_summary_service.py)
2. Gatekeeper Gates (from evidence aggregator / job artifacts)
3. Portfolio Admission Gates (from admission decision artifacts)

The service provides:
- Single consolidated summary with counts
- Deterministic ordering (sorted by gate_id)
- Expandable drill-down with evidence references
- No performance metrics (Hybrid BC v1.1 compliant)
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

from gui.services.gate_summary_service import (
    GateSummaryService, GateSummary, GateResult, GateStatus as SystemGateStatus
)
from contracts.portfolio.gate_summary_schemas import (
    GateSummaryV1, GateItemV1, GateStatus, create_gate_summary_from_gates
)
from core.paths import get_outputs_root

logger = logging.getLogger(__name__)


class ConsolidatedGateSummaryService:
    """Service that consolidates gates from multiple sources."""
    
    def __init__(
        self,
        system_gate_service: Optional[GateSummaryService] = None,
        jobs_root: Optional[Path] = None,
    ):
        self.system_gate_service = system_gate_service or GateSummaryService()
        self.jobs_root = jobs_root or get_outputs_root() / "jobs"
    
    def fetch_system_health_gates(self) -> List[GateItemV1]:
        """Fetch system health gates and convert to GateItemV1."""
        try:
            system_summary = self.system_gate_service.fetch()
            return self._convert_system_gates_to_v1(system_summary.gates)
        except Exception as e:
            logger.error(f"Failed to fetch system health gates: {e}")
            # Return a single error gate
            return [
                GateItemV1(
                    gate_id="system_gates_error",
                    gate_name="System Gates",
                    status=GateStatus.UNKNOWN,
                    message=f"Failed to fetch system gates: {e}",
                    reason_codes=["FETCH_ERROR"],
                    evidence_refs=[],
                    evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
                    evaluator="consolidated_gate_summary_service",
                )
            ]
    
    def _convert_system_gates_to_v1(self, system_gates: List[GateResult]) -> List[GateItemV1]:
        """Convert system GateResult to GateItemV1."""
        v1_gates = []
        
        for gate in system_gates:
            # Map system GateStatus to consolidated GateStatus
            status_map = {
                SystemGateStatus.PASS: GateStatus.PASS,
                SystemGateStatus.WARN: GateStatus.WARN,
                SystemGateStatus.FAIL: GateStatus.REJECT,  # FAIL -> REJECT
                SystemGateStatus.UNKNOWN: GateStatus.UNKNOWN,
            }
            status = status_map.get(gate.status, GateStatus.UNKNOWN)
            
            # Build evidence references from details/actions
            evidence_refs = []
            if gate.details:
                # Add reference to details
                evidence_refs.append(f"details:{gate.gate_id}")
            if gate.actions:
                for action in gate.actions:
                    url = action.get("url")
                    if url:
                        evidence_refs.append(f"action:{url}")
            
            v1_gate = GateItemV1(
                gate_id=gate.gate_id,
                gate_name=gate.gate_name,
                status=status,
                message=gate.message,
                reason_codes=[],  # System gates don't have reason codes
                evidence_refs=evidence_refs,
                evaluated_at_utc=gate.timestamp or datetime.now(timezone.utc).isoformat(),
                evaluator="gate_summary_service",
            )
            v1_gates.append(v1_gate)
        
        return v1_gates
    
    def fetch_gatekeeper_gates(self) -> List[GateItemV1]:
        """Fetch gatekeeper gates from job artifacts."""
        try:
            # Try to import evidence aggregator
            from core.portfolio.evidence_aggregator import EvidenceAggregator, GateStatus as EvidenceGateStatus
            
            aggregator = EvidenceAggregator(jobs_root=self.jobs_root)
            index = aggregator.build_index(include_warn=True, include_fail=True)
            
            v1_gates = []
            for job_id, job_summary in index.jobs.items():
                # Create a gate for each job's gate status
                gate_id = f"gatekeeper_job_{job_id}"
                gate_name = f"Gatekeeper: {job_summary.strategy_id or job_id}"
                
                # Map evidence GateStatus to consolidated GateStatus
                status_map = {
                    EvidenceGateStatus.PASS: GateStatus.PASS,
                    EvidenceGateStatus.WARN: GateStatus.WARN,
                    EvidenceGateStatus.FAIL: GateStatus.REJECT,
                    EvidenceGateStatus.UNKNOWN: GateStatus.UNKNOWN,
                }
                status = status_map.get(job_summary.gate_status, GateStatus.UNKNOWN)
                
                # Build message from gate summary
                gate_summary = job_summary.gate_summary
                if gate_summary.total_permutations is not None:
                    message = f"Job {job_id}: {gate_summary.valid_candidates or 0}/{gate_summary.total_permutations} valid"
                else:
                    message = f"Job {job_id}: {job_summary.gate_status.value}"
                
                # Evidence references
                evidence_refs = []
                for artifact in job_summary.artifacts_present:
                    if artifact.endswith(".json"):
                        evidence_refs.append(f"job:{job_id}/{artifact}")
                
                v1_gate = GateItemV1(
                    gate_id=gate_id,
                    gate_name=gate_name,
                    status=status,
                    message=message,
                    reason_codes=[],  # Gatekeeper doesn't have reason codes
                    evidence_refs=evidence_refs,
                    evaluated_at_utc=job_summary.created_at or datetime.now(timezone.utc).isoformat(),
                    evaluator="evidence_aggregator",
                )
                v1_gates.append(v1_gate)
            
            return v1_gates
            
        except ImportError as e:
            logger.warning(f"Evidence aggregator not available: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch gatekeeper gates: {e}")
            return []
    
    def fetch_portfolio_admission_gates(self) -> List[GateItemV1]:
        """Fetch portfolio admission gates from admission decisions."""
        # This is a placeholder - would need to scan admission directories
        # For now, return empty list
        return []
    
    def fetch_all_gates(self) -> List[GateItemV1]:
        """Fetch gates from all sources."""
        all_gates = []
        
        # System health gates
        system_gates = self.fetch_system_health_gates()
        all_gates.extend(system_gates)
        
        # Gatekeeper gates
        gatekeeper_gates = self.fetch_gatekeeper_gates()
        all_gates.extend(gatekeeper_gates)
        
        # Portfolio admission gates
        admission_gates = self.fetch_portfolio_admission_gates()
        all_gates.extend(admission_gates)
        
        return all_gates
    
    def fetch_consolidated_summary(self) -> GateSummaryV1:
        """Fetch all gates and return consolidated GateSummaryV1."""
        gates = self.fetch_all_gates()
        
        # Add source prefixes to gate_ids to avoid collisions
        for gate in gates:
            # Ensure gate_id is unique across sources
            if not gate.gate_id.startswith(("system_", "gatekeeper_", "admission_")):
                # Determine source based on evaluator
                if gate.evaluator == "gate_summary_service":
                    gate.gate_id = f"system_{gate.gate_id}"
                elif gate.evaluator == "evidence_aggregator":
                    gate.gate_id = f"gatekeeper_{gate.gate_id}"
                elif gate.evaluator == "portfolio_admission":
                    gate.gate_id = f"admission_{gate.gate_id}"
        
        return create_gate_summary_from_gates(
            gates=gates,
            source="consolidated",
            evaluator="consolidated_gate_summary_service",
        )


# Singleton instance for convenience
_consolidated_gate_summary_service = ConsolidatedGateSummaryService()


def get_consolidated_gate_summary_service() -> ConsolidatedGateSummaryService:
    """Return the singleton consolidated gate summary service instance."""
    return _consolidated_gate_summary_service


def fetch_consolidated_gate_summary() -> GateSummaryV1:
    """Convenience function to fetch consolidated gate summary using the singleton."""
    return _consolidated_gate_summary_service.fetch_consolidated_summary()
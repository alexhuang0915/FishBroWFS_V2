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
from contracts.ranking_explain import RankingExplainReasonCode, RankingExplainSeverity
from contracts.ranking_explain_gate_policy import (
    GateImpact,
    ranking_explain_gate_impact,
    get_gate_status_from_impact,
    get_gate_impact_message,
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
                
                # Build message from gatekeeper metrics
                gatekeeper_metrics = job_summary.gatekeeper_metrics
                if gatekeeper_metrics.total_permutations is not None:
                    message = f"Job {job_id}: {gatekeeper_metrics.valid_candidates or 0}/{gatekeeper_metrics.total_permutations} valid"
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
    
    def fetch_ranking_explain_gates(self) -> List[GateItemV1]:
        """Fetch ranking explain gates from ranking_explain_report.json artifact.
        
        Returns:
            List of GateItemV1 with section_id "ranking_explain" and appropriate status.
            
        Rules:
            - Read ranking_explain_report.json artifact
            - Apply mapping policy to reason codes
            - Determine overall section status (PASS/WARN/FAIL)
            - Return single gate representing the ranking explain section
            - If artifact missing: return WARN gate
            - If no mapped impacts: return PASS gate
        """
        try:
            # Try to import explain service to read ranking explain artifact
            # Note: We must NOT import ranking_explain_builder.py (no recompute)
            from control.explain_service import _get_ranking_explain
            
            ranking_explain = _get_ranking_explain("dummy_job_id")  # Will be replaced with actual job_id
            # Actually we need job_id context - this method needs job_id parameter
            # We'll implement a different approach: create a helper that takes job_id
            logger.warning("fetch_ranking_explain_gates needs job_id parameter - returning empty for now")
            return []
            
        except ImportError as e:
            logger.warning(f"Explain service not available: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch ranking explain gates: {e}")
            return []
    
    def build_ranking_explain_gate_section(self, job_id: str) -> GateItemV1:
        """Build ranking explain gate section for a specific job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            GateItemV1 representing ranking explain section
            
        Implementation follows Phase III requirements:
            - Read ranking_explain_report.json artifact
            - Apply mapping policy to reason codes
            - Determine section status (PASS/WARN/FAIL)
            - Return gate with appropriate message and evidence
        """
        try:
            # Try to read ranking explain artifact using existing explain service
            from control.explain_service import _get_ranking_explain
            
            ranking_explain = _get_ranking_explain(job_id)
            
            if not ranking_explain.get("available", False):
                # Artifact missing - return WARN gate (Option A policy)
                return GateItemV1(
                    gate_id="ranking_explain_missing",
                    gate_name="Ranking Explain",
                    status=GateStatus.WARN,
                    message="Ranking explain artifact missing (ranking_explain_report.json not found)",
                    reason_codes=["RANKING_EXPLAIN_REPORT_MISSING"],
                    evidence_refs=[],
                    evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
                    evaluator="consolidated_gate_summary_service",
                )
            
            artifact_data = ranking_explain.get("artifact", {})
            reasons = artifact_data.get("reasons", [])
            
            # Track impacts for determining overall status
            has_block = False
            has_warn = False
            gate_items = []
            
            for reason in reasons:
                code_str = reason.get("code", "")
                severity_str = reason.get("severity", "INFO")
                
                try:
                    # Parse reason code
                    code = RankingExplainReasonCode(code_str)
                    severity = RankingExplainSeverity(severity_str)
                except (ValueError, KeyError):
                    # Unknown code or severity - skip
                    continue
                
                # Apply mapping policy
                impact = ranking_explain_gate_impact(code)
                
                # Determine gate status for this item
                if impact == GateImpact.BLOCK:
                    has_block = True
                elif impact == GateImpact.WARN_ONLY:
                    has_warn = True
                
                # Only include items with impact (BLOCK or WARN_ONLY)
                if impact != GateImpact.NONE:
                    gate_items.append({
                        "code": code.value,
                        "severity": severity.value,
                        "impact": impact.value,
                        "message": get_gate_impact_message(code, severity.value),
                    })
            
            # Determine overall section status
            if has_block:
                section_status = GateStatus.REJECT  # FAIL
            elif has_warn:
                section_status = GateStatus.WARN
            else:
                section_status = GateStatus.PASS
            
            # Build message based on status
            if section_status == GateStatus.REJECT:
                message = "Ranking explain has BLOCK reasons (governance redline)"
            elif section_status == GateStatus.WARN:
                message = "Ranking explain has WARN reasons (risk advisory)"
            else:
                message = "Ranking explain PASS (no risk findings)"
            
            # Add count of items if any
            if gate_items:
                message += f" ({len(gate_items)} findings)"
            
            # Build evidence references
            evidence_refs = []
            if ranking_explain.get("available"):
                evidence_refs.append(f"job:{job_id}/ranking_explain_report.json")
            
            return GateItemV1(
                gate_id="ranking_explain",
                gate_name="Ranking Explain",
                status=section_status,
                message=message,
                reason_codes=[item["code"] for item in gate_items],
                evidence_refs=evidence_refs,
                evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
                evaluator="consolidated_gate_summary_service",
            )
            
        except Exception as e:
            logger.error(f"Failed to build ranking explain gate section for job {job_id}: {e}")
            # Return error gate
            return GateItemV1(
                gate_id="ranking_explain_error",
                gate_name="Ranking Explain",
                status=GateStatus.UNKNOWN,
                message=f"Error processing ranking explain: {e}",
                reason_codes=["PROCESSING_ERROR"],
                evidence_refs=[],
                evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
                evaluator="consolidated_gate_summary_service",
            )
    
    def fetch_all_gates(self, job_id: Optional[str] = None) -> List[GateItemV1]:
        """Fetch gates from all sources.
        
        Args:
            job_id: Optional job identifier for context-specific gates
                   (e.g., ranking explain gates for a specific job)
        """
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
        
        # Ranking explain gates (if job_id provided)
        if job_id:
            ranking_explain_gate = self.build_ranking_explain_gate_section(job_id)
            if ranking_explain_gate:
                all_gates.append(ranking_explain_gate)
        
        return all_gates
    
    def _with_prefixed_gate_id(self, gate: GateItemV1) -> GateItemV1:
        """Return gate with source prefix on gate_id without mutating the original."""
        prefix_candidates = ("system_", "gatekeeper_", "admission_", "ranking_explain")

        if gate.gate_id.startswith(prefix_candidates):
            return gate

        prefix_map = {
            "gate_summary_service": "system_",
            "evidence_aggregator": "gatekeeper_",
            "portfolio_admission": "admission_",
        }
        prefix = prefix_map.get(gate.evaluator)
        if not prefix:
            return gate

        # Use model_copy to respect the frozen contract
        return gate.model_copy(update={"gate_id": f"{prefix}{gate.gate_id}"})

    def fetch_consolidated_summary(self, job_id: Optional[str] = None) -> GateSummaryV1:
        """Fetch all gates and return consolidated GateSummaryV1.
        
        Args:
            job_id: Optional job identifier for context-specific gates
                   (e.g., ranking explain gates for a specific job)
        """
        gates = self.fetch_all_gates(job_id=job_id)
        prefixed_gates = [self._with_prefixed_gate_id(gate) for gate in gates]

        return create_gate_summary_from_gates(
            gates=prefixed_gates,
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
"""
Gate Reason Cards Registry (DP5).

Provides a single SSOT for building deterministic ReasonCard lists for all gates.
Each gate's reason cards are built using SSOT status resolvers only (no UI recompute).

Gate keys must match those used in GateSummary service.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging

from gui.services.reason_cards import ReasonCard
from gui.services.data_alignment_status import (
    resolve_data_alignment_status,
    build_data_alignment_reason_cards,
    DATA_ALIGNMENT_MISSING,
    DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO,
    DATA_ALIGNMENT_DROPPED_ROWS,
    DEFAULT_FORWARD_FILL_WARN_THRESHOLD,
    ARTIFACT_NAME,
)
from gui.services.resource_status import (
    resolve_resource_status,
    build_resource_reason_cards,
    RESOURCE_MISSING_ARTIFACT,
    RESOURCE_MEMORY_EXCEEDED,
    RESOURCE_WORKER_CRASH,
    DEFAULT_MEMORY_WARN_THRESHOLD_MB,
)
from gui.services.portfolio_admission_status import (
    resolve_portfolio_admission_status,
    build_portfolio_admission_reason_cards,
    PORTFOLIO_MISSING_ARTIFACT,
    PORTFOLIO_CORRELATION_TOO_HIGH,
    PORTFOLIO_MDD_EXCEEDED,
    PORTFOLIO_INSUFFICIENT_HISTORY,
    DEFAULT_CORRELATION_THRESHOLD,
    DEFAULT_MDD_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Gate key constants (must match GateSummary service)
GATE_API_HEALTH = "api_health"
GATE_API_READINESS = "api_readiness"
GATE_SUPERVISOR_DB_SSOT = "supervisor_db_ssot"
GATE_WORKER_EXECUTION_REALITY = "worker_execution_reality"
GATE_REGISTRY_SURFACE = "registry_surface"
GATE_POLICY_ENFORCEMENT = "policy_enforcement"
GATE_DATA_ALIGNMENT = "data_alignment"
GATE_RESOURCE = "resource"
GATE_PORTFOLIO_ADMISSION = "portfolio_admission"
GATE_SLIPPAGE_STRESS = "slippage_stress"
GATE_CONTROL_ACTIONS = "control_actions"
GATE_SHARED_BUILD = "shared_build"

# Reason card codes for new gates
SLIPPAGE_STRESS_EXCEEDED = "SLIPPAGE_STRESS_EXCEEDED"
SLIPPAGE_STRESS_ARTIFACT_MISSING = "SLIPPAGE_STRESS_ARTIFACT_MISSING"
READINESS_DATA2_NOT_PREPARED = "READINESS_DATA2_NOT_PREPARED"
READINESS_DATA_COVERAGE_INSUFFICIENT = "READINESS_DATA_COVERAGE_INSUFFICIENT"
READINESS_ARTIFACT_MISSING = "READINESS_ARTIFACT_MISSING"
POLICY_VIOLATION = "POLICY_VIOLATION"
POLICY_ARTIFACT_MISSING = "POLICY_ARTIFACT_MISSING"
CONTROL_ACTION_EVIDENCE_MISSING = "CONTROL_ACTION_EVIDENCE_MISSING"
CONTROL_ACTION_DISCLOSURE_INCOMPLETE = "CONTROL_ACTION_DISCLOSURE_INCOMPLETE"
SHARED_BUILD_GATE_FAILED = "SHARED_BUILD_GATE_FAILED"
SHARED_BUILD_GATE_WARN = "SHARED_BUILD_GATE_WARN"
SHARED_BUILD_ARTIFACT_MISSING = "SHARED_BUILD_ARTIFACT_MISSING"

# Default thresholds
DEFAULT_SLIPPAGE_STRESS_THRESHOLD = 0.0  # S3 net profit must be > 0


def build_reason_cards_for_gate(gate_key: str, job_id: str) -> List[ReasonCard]:
    """
    Dispatch to the correct builder using SSOT status resolvers only.
    
    Args:
        gate_key: Stable gate identifier (e.g., "api_health", "slippage_stress")
        job_id: Job ID for job-specific gates; for system gates, can be empty string
    
    Returns:
        List of ReasonCard objects for the gate, deterministically ordered.
        Empty list for PASS gates with no issues.
    """
    # Map gate keys to builder functions
    builders = {
        GATE_DATA_ALIGNMENT: _build_data_alignment_reason_cards,
        GATE_RESOURCE: _build_resource_reason_cards,
        GATE_PORTFOLIO_ADMISSION: _build_portfolio_admission_reason_cards,
        GATE_SLIPPAGE_STRESS: _build_slippage_stress_reason_cards,
        GATE_API_READINESS: _build_readiness_reason_cards,
        GATE_POLICY_ENFORCEMENT: _build_policy_enforcement_reason_cards,
        GATE_CONTROL_ACTIONS: _build_control_actions_reason_cards,
        GATE_SHARED_BUILD: _build_shared_build_reason_cards,
        # System health gates (api_health, supervisor_db_ssot, etc.) have no reason cards
        GATE_API_HEALTH: _build_empty_reason_cards,
        GATE_SUPERVISOR_DB_SSOT: _build_empty_reason_cards,
        GATE_WORKER_EXECUTION_REALITY: _build_empty_reason_cards,
        GATE_REGISTRY_SURFACE: _build_empty_reason_cards,
    }
    
    builder = builders.get(gate_key)
    if builder is None:
        logger.warning(f"No reason card builder for gate key: {gate_key}")
        return []
    
    return builder(job_id)


def _build_empty_reason_cards(job_id: str) -> List[ReasonCard]:
    """Return empty list for gates that don't have reason cards."""
    return []


def _build_data_alignment_reason_cards(job_id: str) -> List[ReasonCard]:
    """Build reason cards for Data Alignment gate."""
    if not job_id:
        # Return missing artifact card for empty job_id
        return [
            ReasonCard(
                code=DATA_ALIGNMENT_MISSING,
                title="Data Alignment Report Missing",
                severity="WARN",
                why="No recent job found to evaluate data alignment",
                impact="Alignment quality cannot be audited; downstream metrics may be less trustworthy",
                recommended_action="Run a job with BUILD_DATA to generate data_alignment_report.json",
                evidence_artifact=ARTIFACT_NAME,
                evidence_path="$",
                action_target="",
            )
        ]
    
    try:
        status = resolve_data_alignment_status(job_id)
    except ValueError:
        # Invalid job_id format
        return [
            ReasonCard(
                code=DATA_ALIGNMENT_MISSING,
                title="Data Alignment Report Missing",
                severity="WARN",
                why=f"Invalid job_id format: {job_id}",
                impact="Alignment quality cannot be audited; downstream metrics may be less trustworthy",
                recommended_action="Check job_id format and ensure job exists",
                evidence_artifact=ARTIFACT_NAME,
                evidence_path="$",
                action_target="",
            )
        ]
    
    return build_data_alignment_reason_cards(
        job_id=job_id,
        status=status,
        warn_forward_fill_ratio=DEFAULT_FORWARD_FILL_WARN_THRESHOLD,
    )


def _build_resource_reason_cards(job_id: str) -> List[ReasonCard]:
    """Build reason cards for Resource/OOM gate."""
    if not job_id:
        # Return empty list for empty job_id
        return []
    
    try:
        status = resolve_resource_status(job_id)
    except ValueError:
        # Invalid job_id format
        return []
    
    return build_resource_reason_cards(
        job_id=job_id,
        status=status,
        warn_memory_threshold_mb=DEFAULT_MEMORY_WARN_THRESHOLD_MB,
    )


def _build_portfolio_admission_reason_cards(job_id: str) -> List[ReasonCard]:
    """Build reason cards for Portfolio Admission gate."""
    if not job_id:
        # Return empty list for empty job_id
        return []
    
    try:
        status = resolve_portfolio_admission_status(job_id)
    except ValueError:
        # Invalid job_id format
        return []
    
    return build_portfolio_admission_reason_cards(
        job_id=job_id,
        status=status,
        correlation_threshold=DEFAULT_CORRELATION_THRESHOLD,
        mdd_threshold=DEFAULT_MDD_THRESHOLD,
    )


def _build_slippage_stress_reason_cards(job_id: str) -> List[ReasonCard]:
    """
    Build reason cards for Slippage Stress gate.
    
    Cards:
    - SLIPPAGE_STRESS_ARTIFACT_MISSING: if slippage_stress.json missing
    - SLIPPAGE_STRESS_EXCEEDED: if S3 net profit <= threshold
    """
    if not job_id:
        # Return empty list for empty job_id
        return []
    
    from control.reporting.io import read_job_artifact
    from control.supervisor.models import get_job_artifact_dir
    from core.paths import get_outputs_root
    from pathlib import Path
    
    artifact_name = "slippage_stress.json"
    outputs_root = get_outputs_root()
    
    try:
        artifact_dir_str = get_job_artifact_dir(outputs_root, job_id)
        artifact_dir = Path(artifact_dir_str)
        artifact_path = artifact_dir / artifact_name
    except ValueError:
        # Invalid job_id format
        return []
    
    cards: List[ReasonCard] = []
    
    # 1. Check if artifact exists
    if not artifact_path.exists():
        cards.append(ReasonCard(
            code=SLIPPAGE_STRESS_ARTIFACT_MISSING,
            title="Slippage Stress Artifact Missing",
            severity="WARN",
            why="slippage_stress.json not produced by research job",
            impact="Slippage stress cannot be evaluated; live performance risk unknown",
            recommended_action="Ensure research job includes slippage stress test or re-run with enable_slippage_stress=True",
            evidence_artifact=artifact_name,
            evidence_path="$",
            action_target=str(artifact_path),
        ))
        return cards
    
    # 2. Read and evaluate stress matrix
    data = read_job_artifact(job_id, artifact_name)
    if not isinstance(data, dict):
        # Malformed artifact
        cards.append(ReasonCard(
            code=SLIPPAGE_STRESS_ARTIFACT_MISSING,
            title="Slippage Stress Artifact Malformed",
            severity="WARN",
            why="slippage_stress.json exists but cannot be parsed",
            impact="Slippage stress evaluation unavailable",
            recommended_action="Inspect artifact for corruption and re-run research job",
            evidence_artifact=artifact_name,
            evidence_path="$",
            action_target=str(artifact_path),
        ))
        return cards
    
    # Check stress test passed flag
    stress_test_passed = data.get("stress_test_passed", False)
    if not stress_test_passed:
        # Get S3 net profit for context
        stress_matrix = data.get("stress_matrix", {})
        s3_result = stress_matrix.get("S3", {})
        net_after_cost = s3_result.get("net_after_cost", 0.0)
        
        cards.append(ReasonCard(
            code=SLIPPAGE_STRESS_EXCEEDED,
            title="Slippage Stress Test Failed",
            severity="FAIL",
            why=f"S3 net profit {net_after_cost:.2f} <= threshold {DEFAULT_SLIPPAGE_STRESS_THRESHOLD}",
            impact="PnL may be overstated; live performance risk increases under stressed slippage",
            recommended_action="Reduce turnover/entries, widen stops, adjust fill assumptions, or raise slippage config",
            evidence_artifact=artifact_name,
            evidence_path="$.stress_test_passed",
            action_target=str(artifact_path),
        ))
    
    return cards


def _build_readiness_reason_cards(job_id: str) -> List[ReasonCard]:
    """
    Build reason cards for Readiness gate (Data2 readiness / data coverage).
    
    Cards:
    - READINESS_ARTIFACT_MISSING: if readiness artifact missing
    - READINESS_DATA2_NOT_PREPARED: if Data2 not prepared
    - READINESS_DATA_COVERAGE_INSUFFICIENT: if data coverage insufficient
    """
    # Try to read readiness artifact
    from control.reporting.io import read_job_artifact
    
    artifact_name = "readiness_report.json"
    data = read_job_artifact(job_id, artifact_name)
    
    cards: List[ReasonCard] = []
    
    if not isinstance(data, dict):
        # Artifact missing or malformed
        cards.append(ReasonCard(
            code=READINESS_ARTIFACT_MISSING,
            title="Readiness Artifact Missing",
            severity="WARN",
            why="readiness_report.json not produced by job",
            impact="Data readiness cannot be evaluated; job may fail due to missing data",
            recommended_action="Ensure job produces readiness_report.json or check data preparation pipeline",
            evidence_artifact=artifact_name,
            evidence_path="$",
            action_target=f"job:{job_id}/{artifact_name}",
        ))
        return cards
    
    # Check Data2 preparation status
    data2_prepared = data.get("data2_prepared", False)
    if not data2_prepared:
        cards.append(ReasonCard(
            code=READINESS_DATA2_NOT_PREPARED,
            title="Data2 Not Prepared",
            severity="FAIL",
            why="Data2 (context feeds) not prepared for requested season/dataset",
            impact="Job cannot proceed; Data2-dependent features will be unavailable",
            recommended_action="Run shared build for Data2 or select different data source",
            evidence_artifact=artifact_name,
            evidence_path="$.data2_prepared",
            action_target=f"job:{job_id}/{artifact_name}",
        ))
    
    # Check data coverage
    coverage_sufficient = data.get("coverage_sufficient", True)
    if not coverage_sufficient:
        missing_periods = data.get("missing_periods", [])
        cards.append(ReasonCard(
            code=READINESS_DATA_COVERAGE_INSUFFICIENT,
            title="Data Coverage Insufficient",
            severity="WARN",
            why=f"Data missing for periods: {missing_periods[:3]}{'...' if len(missing_periods) > 3 else ''}",
            impact="Analysis may have gaps; results may not be representative",
            recommended_action="Extend data collection or adjust analysis timeframe",
            evidence_artifact=artifact_name,
            evidence_path="$.coverage_sufficient",
            action_target=f"job:{job_id}/{artifact_name}",
        ))
    
    return cards


def _build_policy_enforcement_reason_cards(job_id: str) -> List[ReasonCard]:
    """
    Build reason cards for Policy Enforcement gate.
    
    Cards:
    - POLICY_ARTIFACT_MISSING: if policy_check.json missing
    - POLICY_VIOLATION: if policy violation detected
    """
    from control.reporting.io import read_job_artifact
    
    artifact_name = "policy_check.json"
    data = read_job_artifact(job_id, artifact_name)
    
    cards: List[ReasonCard] = []
    
    if not isinstance(data, dict):
        # Artifact missing
        cards.append(ReasonCard(
            code=POLICY_ARTIFACT_MISSING,
            title="Policy Check Artifact Missing",
            severity="WARN",
            why="policy_check.json not produced by job",
            impact="Policy compliance cannot be verified; governance risk unknown",
            recommended_action="Ensure job produces policy_check.json or check policy evaluation pipeline",
            evidence_artifact=artifact_name,
            evidence_path="$",
            action_target=f"job:{job_id}/{artifact_name}",
        ))
        return cards
    
    # Check for policy violations
    overall_status = data.get("overall_status", "").upper()
    if overall_status in ("REJECTED", "FAILED"):
        failure_code = data.get("failure_code", "UNKNOWN")
        policy_stage = data.get("policy_stage", "unknown")
        
        cards.append(ReasonCard(
            code=POLICY_VIOLATION,
            title="Policy Violation",
            severity="FAIL",
            why=f"Policy {policy_stage} violation: {failure_code}",
            impact="Job rejected / blocked by governance",
            recommended_action="Fix config / inputs to comply with policy requirements",
            evidence_artifact=artifact_name,
            evidence_path="$.overall_status",
            action_target=f"job:{job_id}/{artifact_name}",
        ))
    
    return cards


def _build_control_actions_reason_cards(job_id: str) -> List[ReasonCard]:
    """
    Build reason cards for Control Actions gate.
    
    Cards:
    - CONTROL_ACTION_EVIDENCE_MISSING: if action has no evidence pointer
    - CONTROL_ACTION_DISCLOSURE_INCOMPLETE: if required fields missing
    """
    # For now, control actions gate is environment-based, not job-based
    # We'll check if control actions are enabled and if evidence exists
    import os
    
    cards: List[ReasonCard] = []
    
    # Check if control actions are enabled
    enabled = os.environ.get("FISHBRO_ENABLE_CONTROL_ACTIONS", "").strip() == "1"
    if not enabled:
        # This is not a failure, just informational
        return cards
    
    # Check for evidence of recent control actions
    # For DP5, we'll implement a simple check
    from control.reporting.io import read_job_artifact
    from control.supervisor.models import get_job_artifact_dir
    from core.paths import get_outputs_root
    from pathlib import Path
    
    outputs_root = get_outputs_root()
    artifact_dir_str = get_job_artifact_dir(outputs_root, job_id)
    artifact_dir = Path(artifact_dir_str)
    
    # Look for abort evidence files
    abort_evidence_files = list(artifact_dir.glob("*abort*evidence*.json"))
    
    if not abort_evidence_files:
        cards.append(ReasonCard(
            code=CONTROL_ACTION_EVIDENCE_MISSING,
            title="Control Action Evidence Missing",
            severity="WARN",
            why="No evidence file found for control actions (e.g., abort)",
            impact="Audit trail incomplete; action attribution unclear",
            recommended_action="Ensure control actions write evidence artifacts",
            evidence_artifact="*abort*evidence*.json",
            evidence_path="$",
            action_target=str(artifact_dir),
        ))
    
    # Check disclosure completeness (simplified)
    # In a real implementation, would check specific fields
    
    return cards


def _build_shared_build_reason_cards(job_id: str) -> List[ReasonCard]:
    """
    Build reason cards for Shared Build gate.
    
    Cards:
    - SHARED_BUILD_ARTIFACT_MISSING: if shared build manifest missing
    - SHARED_BUILD_GATE_FAILED: if shared build failed
    - SHARED_BUILD_GATE_WARN: if shared build has warnings
    """
    from control.reporting.io import read_job_artifact
    from control.supervisor.models import get_job_artifact_dir
    from core.paths import get_outputs_root
    from pathlib import Path
    
    artifact_name = "shared_build_manifest.json"
    outputs_root = get_outputs_root()
    artifact_dir_str = get_job_artifact_dir(outputs_root, job_id)
    artifact_dir = Path(artifact_dir_str)
    artifact_path = artifact_dir / artifact_name
    
    cards: List[ReasonCard] = []
    
    # 1. Check if artifact exists
    if not artifact_path.exists():
        cards.append(ReasonCard(
            code=SHARED_BUILD_ARTIFACT_MISSING,
            title="Shared Build Manifest Missing",
            severity="WARN",
            why="shared_build_manifest.json not produced by shared build",
            impact="Shared data dependencies unknown; job may fail due to missing bars/features",
            recommended_action="Run shared build for required season/dataset or check build logs",
            evidence_artifact=artifact_name,
            evidence_path="$",
            action_target=str(artifact_path),
        ))
        return cards
    
    # 2. Read and evaluate manifest
    data = read_job_artifact(job_id, artifact_name)
    if not isinstance(data, dict):
        # Malformed artifact
        cards.append(ReasonCard(
            code=SHARED_BUILD_ARTIFACT_MISSING,
            title="Shared Build Manifest Malformed",
            severity="WARN",
            why="shared_build_manifest.json exists but cannot be parsed",
            impact="Shared build status unknown",
            recommended_action="Inspect artifact for corruption and re-run shared build",
            evidence_artifact=artifact_name,
            evidence_path="$",
            action_target=str(artifact_path),
        ))
        return cards
    
    # 3. Check build status
    build_status = data.get("build_status", "UNKNOWN")
    if build_status == "FAILED":
        failure_reason = data.get("failure_reason", "Unknown reason")
        cards.append(ReasonCard(
            code=SHARED_BUILD_GATE_FAILED,
            title="Shared Build Failed",
            severity="FAIL",
            why=f"Shared build failed: {failure_reason}",
            impact="Required bars/features unavailable; dependent jobs will fail",
            recommended_action="Fix shared build configuration and re-run",
            evidence_artifact=artifact_name,
            evidence_path="$.build_status",
            action_target=str(artifact_path),
        ))
    elif build_status == "WARN":
        warnings = data.get("warnings", [])
        warning_summary = ", ".join(warnings[:2]) + ("..." if len(warnings) > 2 else "")
        cards.append(ReasonCard(
            code=SHARED_BUILD_GATE_WARN,
            title="Shared Build Warnings",
            severity="WARN",
            why=f"Shared build completed with warnings: {warning_summary}",
            impact="Some data may be incomplete or suboptimal",
            recommended_action="Review shared build warnings and adjust as needed",
            evidence_artifact=artifact_name,
            evidence_path="$.build_status",
            action_target=str(artifact_path),
        ))
    
    return cards
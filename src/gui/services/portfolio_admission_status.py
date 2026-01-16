from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from control.reporting.io import read_job_artifact
from control.supervisor.models import get_job_artifact_dir
from core.paths import get_outputs_root
from gui.services.reason_cards import ReasonCard

# Artifact names (from contracts)
ADMISSION_DECISION_FILE = "admission_decision.json"
CORRELATION_MATRIX_FILE = "correlation_matrix.json"
CORRELATION_VIOLATIONS_FILE = "correlation_violations.json"
RISK_BUDGET_SNAPSHOT_FILE = "risk_budget_snapshot.json"

# Reason card codes
PORTFOLIO_CORRELATION_TOO_HIGH = "PORTFOLIO_CORRELATION_TOO_HIGH"
PORTFOLIO_MDD_EXCEEDED = "PORTFOLIO_MDD_EXCEEDED"
PORTFOLIO_INSUFFICIENT_HISTORY = "PORTFOLIO_INSUFFICIENT_HISTORY"
PORTFOLIO_MISSING_ARTIFACT = "PORTFOLIO_MISSING_ARTIFACT"

# Default thresholds (should match governance params)
DEFAULT_CORRELATION_THRESHOLD = 0.7
DEFAULT_MDD_THRESHOLD = 0.25  # 25%


@dataclass(frozen=True)
class AdmissionStatus:
    status: Literal["OK", "MISSING", "WARN", "FAIL"]
    artifact_relpath: str
    artifact_abspath: str
    message: str
    metrics: Dict[str, Any]


def resolve_portfolio_admission_status(job_id: str) -> AdmissionStatus:
    """Resolve portfolio admission status from job artifacts."""
    outputs_root = get_outputs_root()
    artifact_dir = get_job_artifact_dir(outputs_root, job_id)
    
    # Look for admission_decision.json
    artifact_path = artifact_dir / ADMISSION_DECISION_FILE
    artifact_abspath = str(artifact_path)
    if not artifact_path.exists():
        return AdmissionStatus(
            status="MISSING",
            artifact_relpath=ADMISSION_DECISION_FILE,
            artifact_abspath=artifact_abspath,
            message="Portfolio admission decision artifact not found",
            metrics={},
        )
    
    data = read_job_artifact(job_id, ADMISSION_DECISION_FILE)
    if not isinstance(data, dict):
        return AdmissionStatus(
            status="MISSING",
            artifact_relpath=ADMISSION_DECISION_FILE,
            artifact_abspath=artifact_abspath,
            message="Portfolio admission decision artifact malformed",
            metrics={},
        )
    
    verdict = data.get("verdict")
    reasons = data.get("reasons", {})
    correlation_violations = data.get("correlation_violations")
    risk_budget_steps = data.get("risk_budget_steps")
    
    if verdict == "REJECTED":
        status = "FAIL"
        message = "Portfolio admission rejected"
    elif verdict == "ADMITTED":
        status = "OK"
        message = "Portfolio admission passed"
    else:
        status = "WARN"
        message = "Portfolio admission unknown verdict"
    
    metrics = {
        "verdict": verdict,
        "reasons": reasons,
        "correlation_violations": correlation_violations,
        "risk_budget_steps": risk_budget_steps,
    }
    
    return AdmissionStatus(
        status=status,
        artifact_relpath=ADMISSION_DECISION_FILE,
        artifact_abspath=artifact_abspath,
        message=message,
        metrics=metrics,
    )


def build_portfolio_admission_reason_cards(
    job_id: str,
    status: AdmissionStatus,
    *,
    correlation_threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    mdd_threshold: float = DEFAULT_MDD_THRESHOLD,
) -> List[ReasonCard]:
    """
    Build reason cards for Portfolio Admission WARNs/FAILs.
    
    Returns deterministic ordering of cards:
    1. MISSING (if any)
    2. CORRELATION_TOO_HIGH (if triggered)
    3. MDD_EXCEEDED (if triggered)
    4. INSUFFICIENT_HISTORY (if triggered)
    """
    cards: List[ReasonCard] = []
    
    # 1. Missing artifact
    if status.status == "MISSING":
        cards.append(ReasonCard(
            code=PORTFOLIO_MISSING_ARTIFACT,
            title="Portfolio Admission Artifact Missing",
            severity="WARN",
            why="admission_decision.json not produced by BUILD_PORTFOLIO",
            impact="Portfolio admission cannot be audited; downstream allocation may be risky",
            recommended_action="Re-run BUILD_PORTFOLIO for this job or inspect runner logs",
            evidence_artifact=status.artifact_relpath,
            evidence_path="$",
            action_target=status.artifact_abspath,
        ))
        return cards
    
    # 2. Correlation too high
    correlation_violations = status.metrics.get("correlation_violations")
    if correlation_violations:
        # For simplicity, we'll create a generic card
        cards.append(ReasonCard(
            code=PORTFOLIO_CORRELATION_TOO_HIGH,
            title="Correlation Too High",
            severity="FAIL" if status.status == "FAIL" else "WARN",
            why=f"Correlation exceeded threshold {correlation_threshold:.2f}",
            impact="Portfolio diversification is reduced; drawdowns may amplify",
            recommended_action="Remove or replace highly correlated strategies",
            evidence_artifact=status.artifact_relpath,
            evidence_path="$.correlation_violations",
            action_target=status.artifact_abspath,
        ))
    
    # 3. MDD exceeded (simplified)
    risk_budget_steps = status.metrics.get("risk_budget_steps")
    if risk_budget_steps:
        cards.append(ReasonCard(
            code=PORTFOLIO_MDD_EXCEEDED,
            title="Maximum Drawdown Exceeded",
            severity="FAIL" if status.status == "FAIL" else "WARN",
            why=f"Maximum drawdown exceeded threshold {mdd_threshold:.0%}",
            impact="Portfolio risk exceeds budget; potential for large losses",
            recommended_action="Reduce position sizes, increase diversification, or adjust risk budget",
            evidence_artifact=status.artifact_relpath,
            evidence_path="$.risk_budget_steps",
            action_target=status.artifact_abspath,
        ))
    
    # 4. Insufficient history (if reasons indicate)
    reasons = status.metrics.get("reasons", {})
    for reason in reasons.values():
        if "insufficient" in reason.lower() or "history" in reason.lower():
            cards.append(ReasonCard(
                code=PORTFOLIO_INSUFFICIENT_HISTORY,
                title="Insufficient History",
                severity="WARN",
                why="Strategy lacks sufficient historical data for reliable admission",
                impact="Admission decision may be based on limited sample; increased uncertainty",
                recommended_action="Collect more historical data or adjust admission thresholds",
                evidence_artifact=status.artifact_relpath,
                evidence_path="$.reasons",
                action_target=status.artifact_abspath,
            ))
            break
    
    return cards
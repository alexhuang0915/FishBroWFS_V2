from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal

from control.reporting.io import read_job_artifact
from control.supervisor.models import get_job_artifact_dir
from core.paths import get_outputs_root
from gui.services.reason_cards import ReasonCard

MISSING_MESSAGE = "data_alignment_report.json not produced by BUILD_DATA"
ARTIFACT_NAME = "data_alignment_report.json"
REQUIRED_KEYS = {"forward_fill_ratio", "dropped_rows", "forward_filled_rows"}

# Reason card codes
DATA_ALIGNMENT_MISSING = "DATA_ALIGNMENT_MISSING"
DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO = "DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO"
DATA_ALIGNMENT_DROPPED_ROWS = "DATA_ALIGNMENT_DROPPED_ROWS"

# Default threshold for forward-fill ratio warning (same as gate_summary_service)
DEFAULT_FORWARD_FILL_WARN_THRESHOLD = 0.5


@dataclass(frozen=True)
class DataAlignmentStatus:
    status: Literal["OK", "MISSING"]
    artifact_relpath: str
    artifact_abspath: str
    message: str
    metrics: Dict[str, Any]


def resolve_data_alignment_status(job_id: str) -> DataAlignmentStatus:
    outputs_root = get_outputs_root()
    artifact_dir = get_job_artifact_dir(outputs_root, job_id)
    artifact_path = artifact_dir / ARTIFACT_NAME
    artifact_abspath = str(artifact_path)
    if not artifact_path.exists():
        return DataAlignmentStatus(
            status="MISSING",
            artifact_relpath=ARTIFACT_NAME,
            artifact_abspath=artifact_abspath,
            message=MISSING_MESSAGE,
            metrics={},
        )

    data = read_job_artifact(job_id, ARTIFACT_NAME)
    if not isinstance(data, dict):
        return DataAlignmentStatus(
            status="MISSING",
            artifact_relpath=ARTIFACT_NAME,
            artifact_abspath=artifact_abspath,
            message=MISSING_MESSAGE,
            metrics={},
        )

    if not REQUIRED_KEYS.issubset(data.keys()):
        return DataAlignmentStatus(
            status="MISSING",
            artifact_relpath=ARTIFACT_NAME,
            artifact_abspath=artifact_abspath,
            message=MISSING_MESSAGE,
            metrics={},
        )

    metrics = {key: data[key] for key in REQUIRED_KEYS}
    return DataAlignmentStatus(
        status="OK",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath=artifact_abspath,
        message="data_alignment_report.json is available",
        metrics=metrics,
    )


def build_data_alignment_reason_cards(
    job_id: str,
    status: DataAlignmentStatus,
    *,
    warn_forward_fill_ratio: float = DEFAULT_FORWARD_FILL_WARN_THRESHOLD,
) -> List[ReasonCard]:
    """
    Build reason cards for Data Alignment WARNs/FAILs.
    
    Returns deterministic ordering of cards:
    1. MISSING (if any)
    2. HIGH_FF_RATIO (if triggered)
    3. DROPPED_ROWS (if triggered)
    """
    cards: List[ReasonCard] = []
    
    # 1. Missing artifact
    if status.status == "MISSING":
        cards.append(ReasonCard(
            code=DATA_ALIGNMENT_MISSING,
            title="Data Alignment Report Missing",
            severity="WARN",
            why="data_alignment_report.json not produced by BUILD_DATA",
            impact="Alignment quality cannot be audited; downstream metrics may be less trustworthy",
            recommended_action="Re-run BUILD_DATA for this job or inspect runner logs to confirm artifact generation",
            evidence_artifact=ARTIFACT_NAME,
            evidence_path="$",
            action_target=status.artifact_abspath,
        ))
        # If missing, we cannot evaluate other conditions
        return cards
    
    # 2. High forward-fill ratio
    forward_fill_ratio = status.metrics.get("forward_fill_ratio")
    if isinstance(forward_fill_ratio, (int, float)) and forward_fill_ratio > warn_forward_fill_ratio:
        cards.append(ReasonCard(
            code=DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO,
            title="High Forward-Fill Ratio",
            severity="WARN",
            why=f"Forward-fill ratio {forward_fill_ratio:.1%} exceeds warning threshold {warn_forward_fill_ratio:.0%}",
            impact="Data2 contains gaps; model inputs may be biased by forward-filled values",
            recommended_action="Inspect data_alignment_report.json and consider adjusting Data2 source/coverage or excluding affected windows",
            evidence_artifact=ARTIFACT_NAME,
            evidence_path="$.forward_fill_ratio",
            action_target=status.artifact_abspath,
        ))
    
    # 3. Dropped rows non-zero
    dropped_rows = status.metrics.get("dropped_rows", 0)
    if isinstance(dropped_rows, (int, float)) and dropped_rows > 0:
        cards.append(ReasonCard(
            code=DATA_ALIGNMENT_DROPPED_ROWS,
            title="Dropped Rows in Alignment",
            severity="WARN",
            why=f"Dropped {dropped_rows} row(s) during alignment",
            impact="Some input rows could not be aligned; sample size reduced",
            recommended_action="Inspect data_alignment_report.json and consider adjusting Data1/Data2 coverage or timeframe",
            evidence_artifact=ARTIFACT_NAME,
            evidence_path="$.dropped_rows",
            action_target=status.artifact_abspath,
        ))
    
    return cards

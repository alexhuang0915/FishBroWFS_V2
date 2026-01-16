from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal

from control.reporting.io import read_job_artifact
from control.supervisor.models import get_job_artifact_dir
from core.paths import get_outputs_root

MISSING_MESSAGE = "data_alignment_report.json not produced by BUILD_DATA"
ARTIFACT_NAME = "data_alignment_report.json"
REQUIRED_KEYS = {"forward_fill_ratio", "dropped_rows", "forward_filled_rows"}


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

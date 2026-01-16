from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from control.reporting.io import read_job_artifact
from control.supervisor.models import get_job_artifact_dir
from core.paths import get_outputs_root
from gui.services.reason_cards import ReasonCard

# Artifact names
RESOURCE_USAGE_ARTIFACT = "resource_usage.json"
OOM_GATE_DECISION_ARTIFACT = "oom_gate_decision.json"

# Reason card codes
RESOURCE_MEMORY_EXCEEDED = "RESOURCE_MEMORY_EXCEEDED"
RESOURCE_WORKER_CRASH = "RESOURCE_WORKER_CRASH"
RESOURCE_MISSING_ARTIFACT = "RESOURCE_MISSING_ARTIFACT"

# Default thresholds (MB)
DEFAULT_MEMORY_WARN_THRESHOLD_MB = 6000  # 6GB


@dataclass(frozen=True)
class ResourceStatus:
    status: Literal["OK", "MISSING", "WARN", "FAIL"]
    artifact_relpath: str
    artifact_abspath: str
    message: str
    metrics: Dict[str, Any]


def resolve_resource_status(job_id: str) -> ResourceStatus:
    """Resolve resource usage status from job artifacts."""
    outputs_root = get_outputs_root()
    artifact_dir = get_job_artifact_dir(outputs_root, job_id)
    
    # First try resource_usage.json
    artifact_path = artifact_dir / RESOURCE_USAGE_ARTIFACT
    artifact_abspath = str(artifact_path)
    if artifact_path.exists():
        data = read_job_artifact(job_id, RESOURCE_USAGE_ARTIFACT)
        if isinstance(data, dict):
            peak_memory_mb = data.get("peak_memory_mb")
            limit_mb = data.get("limit_mb")
            worker_crash = data.get("worker_crash", False)
            if worker_crash:
                return ResourceStatus(
                    status="FAIL",
                    artifact_relpath=RESOURCE_USAGE_ARTIFACT,
                    artifact_abspath=artifact_abspath,
                    message="Worker crashed due to resource exhaustion",
                    metrics=data,
                )
            elif peak_memory_mb is not None and limit_mb is not None and peak_memory_mb > limit_mb:
                return ResourceStatus(
                    status="WARN",
                    artifact_relpath=RESOURCE_USAGE_ARTIFACT,
                    artifact_abspath=artifact_abspath,
                    message=f"Peak memory {peak_memory_mb}MB exceeded limit {limit_mb}MB",
                    metrics=data,
                )
            else:
                return ResourceStatus(
                    status="OK",
                    artifact_relpath=RESOURCE_USAGE_ARTIFACT,
                    artifact_abspath=artifact_abspath,
                    message="Resource usage within limits",
                    metrics=data,
                )
    
    # Fallback to oom_gate_decision.json
    oom_path = artifact_dir / OOM_GATE_DECISION_ARTIFACT
    if oom_path.exists():
        data = read_job_artifact(job_id, OOM_GATE_DECISION_ARTIFACT)
        if isinstance(data, dict) and data.get("decision") in ("BLOCK", "AUTO_DOWNSAMPLE"):
            return ResourceStatus(
                status="WARN",
                artifact_relpath=OOM_GATE_DECISION_ARTIFACT,
                artifact_abspath=str(oom_path),
                message="OOM gate triggered",
                metrics=data,
            )
        else:
            return ResourceStatus(
                status="OK",
                artifact_relpath=OOM_GATE_DECISION_ARTIFACT,
                artifact_abspath=str(oom_path),
                message="OOM gate passed",
                metrics=data if isinstance(data, dict) else {},
            )
    
    # No artifact found
    return ResourceStatus(
        status="MISSING",
        artifact_relpath=RESOURCE_USAGE_ARTIFACT,
        artifact_abspath=artifact_abspath,
        message="Resource usage artifact not found",
        metrics={},
    )


def build_resource_reason_cards(
    job_id: str,
    status: ResourceStatus,
    *,
    warn_memory_threshold_mb: float = DEFAULT_MEMORY_WARN_THRESHOLD_MB,
) -> List[ReasonCard]:
    """
    Build reason cards for Resource/OOM WARNs/FAILs.
    
    Returns deterministic ordering of cards:
    1. MISSING (if any)
    2. MEMORY_EXCEEDED (if triggered)
    3. WORKER_CRASH (if triggered)
    """
    cards: List[ReasonCard] = []
    
    # 1. Missing artifact
    if status.status == "MISSING":
        cards.append(ReasonCard(
            code=RESOURCE_MISSING_ARTIFACT,
            title="Resource Usage Artifact Missing",
            severity="WARN",
            why="Resource usage artifact not produced by job",
            impact="Resource consumption cannot be audited; potential OOM risks unknown",
            recommended_action="Ensure job produces resource_usage.json or oom_gate_decision.json",
            evidence_artifact=status.artifact_relpath,
            evidence_path="$",
            action_target=status.artifact_abspath,
        ))
        return cards
    
    # 2. Memory exceeded
    peak_memory_mb = status.metrics.get("peak_memory_mb")
    limit_mb = status.metrics.get("limit_mb")
    if peak_memory_mb is not None and limit_mb is not None and peak_memory_mb > limit_mb:
        cards.append(ReasonCard(
            code=RESOURCE_MEMORY_EXCEEDED,
            title="Memory Exceeded",
            severity="FAIL" if status.status == "FAIL" else "WARN",
            why=f"Peak memory usage {peak_memory_mb}MB exceeded limit {limit_mb}MB",
            impact="Job execution may terminate early or produce incomplete artifacts",
            recommended_action="Reduce batch size, limit features/timeframes, or increase worker memory",
            evidence_artifact=status.artifact_relpath,
            evidence_path="$.peak_memory_mb",
            action_target=status.artifact_abspath,
        ))
    
    # 3. Worker crash
    worker_crash = status.metrics.get("worker_crash", False)
    if worker_crash:
        cards.append(ReasonCard(
            code=RESOURCE_WORKER_CRASH,
            title="Worker Crash (OOM-related)",
            severity="FAIL",
            why="Worker process crashed due to resource exhaustion",
            impact="Job execution terminated abruptly; results may be incomplete",
            recommended_action="Increase memory limits, reduce workload, or investigate memory leaks",
            evidence_artifact=status.artifact_relpath,
            evidence_path="$.worker_crash",
            action_target=status.artifact_abspath,
        ))
    
    return cards
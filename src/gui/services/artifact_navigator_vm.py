from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List

from control.supervisor.models import get_job_artifact_dir
from core.paths import get_outputs_root

from gui.desktop.services.supervisor_client import get_artifacts
from gui.services.data_alignment_status import ARTIFACT_NAME, resolve_data_alignment_status, DataAlignmentStatus
from gui.services.explain_adapter import ExplainAdapter, JobReason
from gui.services.gate_summary_service import fetch_gate_summary, GateSummary

logger = logging.getLogger(__name__)

GATE_SUMMARY_TARGET = "gate_summary"
EXPLAIN_TARGET_PREFIX = "explain://"

# Provider type definitions
GateProvider = Callable[[], GateSummary]
ExplainProvider = Callable[[str], JobReason]
ArtifactIndexProvider = Callable[[str], Dict[str, Any]]


@dataclass(frozen=True)
class Action:
    label: str
    target: str


def default_gate_provider() -> GateSummary:
    """Default gate provider bound to SSOT helper."""
    return fetch_gate_summary()


def default_explain_provider(job_id: str) -> JobReason:
    """Default explain provider bound to SSOT helper."""
    adapter = ExplainAdapter()
    return adapter.get_job_reason(job_id)


def default_artifact_index_provider(job_id: str) -> Dict[str, Any]:
    """Default artifact index provider bound to SSOT helper."""
    return get_artifacts(job_id)


@dataclass
class ArtifactNavigatorVM:
    """ViewModel that aggregates gate, explain, and artifact metadata for a job."""

    job_id: str = ""
    gate: Dict[str, Any] = field(default_factory=dict)
    explain: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    gate_provider: GateProvider = field(default_factory=lambda: default_gate_provider)
    explain_provider: ExplainProvider = field(default_factory=lambda: default_explain_provider)
    artifact_index_provider: ArtifactIndexProvider = field(default_factory=lambda: default_artifact_index_provider)

    def __post_init__(self):
        # Ensure providers are callable (they already are via defaults)
        pass

    def load_for_job(self, job_id: str) -> None:
        """Load gate summary, explain context, and artifact index for a job."""
        object.__setattr__(self, "job_id", job_id)
        self.gate = self._load_gate_summary()
        alignment = self._resolve_alignment(job_id)
        self.explain = self._build_explain_context(job_id, alignment)
        self.artifacts = self._build_artifact_rows(job_id)

    def _load_gate_summary(self) -> Dict[str, Any]:
        try:
            summary = self.gate_provider()
            status = summary.overall_status.value if getattr(summary, "overall_status", None) else "UNKNOWN"
            message = getattr(summary, "overall_message", "Gate summary unavailable.")
            return {
                "status": status,
                "message": message,
                "actions": [Action(label="Open Gate Summary", target=GATE_SUMMARY_TARGET)],
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Failed to load gate summary for %s", self.job_id)
            return {
                "status": "UNKNOWN",
                "message": f"Unable to load gate summary: {exc}",
                "actions": [Action(label="Open Gate Summary", target=GATE_SUMMARY_TARGET)],
            }

    def _resolve_alignment(self, job_id: str) -> DataAlignmentStatus:
        try:
            return resolve_data_alignment_status(job_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Data alignment check failed for %s", job_id)
            # Fallback to missing status
            return DataAlignmentStatus(
                status="MISSING",
                artifact_relpath=ARTIFACT_NAME,
                artifact_abspath=str(get_job_artifact_dir(get_outputs_root(), job_id) / ARTIFACT_NAME),
                message="Data alignment status unavailable.",
                metrics={},
            )

    def _build_explain_context(self, job_id: str, alignment: DataAlignmentStatus) -> Dict[str, Any]:
        try:
            reason = self.explain_provider(job_id)
            summary = reason.summary
        except Exception:  # pragma: no cover - best effort
            logger.exception("Failed to load explain context for %s", job_id)
            reason = JobReason(
                job_id=job_id,
                summary="Explain unavailable.",
                action_hint="",
                decision_layer="UNKNOWN",
                human_tag="UNKNOWN",
                recoverable=False,
                evidence_urls={},
                fallback=True,
            )
            summary = reason.summary

        return {
            "data_alignment_status": alignment.status,
            "message": alignment.message if alignment.status == "MISSING" else summary,
            "actions": [Action(label="Open Explain", target=f"{EXPLAIN_TARGET_PREFIX}{job_id}")],
        }

    def _build_artifact_rows(self, job_id: str) -> List[Dict[str, Any]]:
        artifact_index = self._fetch_artifact_index(job_id)
        files = self._normalize_files(artifact_index)
        artifact_dir = get_job_artifact_dir(get_outputs_root(), job_id)
        expected_names = {ARTIFACT_NAME} | {entry["filename"] for entry in files if "filename" in entry}
        rows = []
        for name in sorted(expected_names):
            path = artifact_dir / name
            present = path.exists()
            entry = next((item for item in files if item.get("filename") == name), {})
            url_or_path = entry.get("url") or str(path)
            rows.append({
                "name": name,
                "status": "PRESENT" if present else "MISSING",
                "url_or_path": url_or_path,
                "action": Action(
                    label="Open" if present else "Locate",
                    target=str(path),
                ),
            })
        return rows

    def _fetch_artifact_index(self, job_id: str) -> Dict[str, Any]:
        try:
            index = self.artifact_index_provider(job_id)
            if isinstance(index, dict):
                return index
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed to fetch artifact index for %s", job_id)
        return {}

    @staticmethod
    def _normalize_files(index: Dict[str, Any]) -> List[Dict[str, Any]]:
        files = index.get("files", [])
        if isinstance(files, list):
            return [entry for entry in files if isinstance(entry, dict)]
        if isinstance(index, list):
            return [entry for entry in index if isinstance(entry, dict)]
        return []

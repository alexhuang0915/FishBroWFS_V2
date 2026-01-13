"""
Job Reason Service – Human‑readable failure reasons + next‑action recommendations.

Extracts failure reasons from job artifacts (policy_check.json, runtime_metrics.json, etc.)
and maps them to actionable next steps.

Design principles:
- Human‑readable, not raw logs.
- Actionable: each reason must have a clear next step.
- Prioritized: most severe issues first.
- Non‑blocking: if mapping fails, fallback to generic explanation.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FailureReason:
    """Structured failure reason with next‑action recommendation."""
    summary: str                     # Short human‑readable summary (1‑2 lines)
    detailed_reason: str             # Detailed explanation (paragraph)
    next_action: str                 # Concrete next step for the user
    severity: str                    # "info", "warning", "error", "critical"
    artifact_source: str             # Which artifact provided this (e.g., "policy_check")
    raw_data: Optional[Dict[str, Any]] = None  # Original raw data for debugging


class JobReasonService:
    """Service that extracts failure reasons from job artifacts."""
    
    # Mapping from policy gate names to human‑readable summaries and next actions
    POLICY_GATE_MAPPINGS = {
        "data_availability": {
            "summary": "Required market data is missing",
            "detailed": "The job cannot start because the required bar data for the selected instrument/timeframe is not available in the data store.",
            "next_action": "Check data readiness via the Data tab, or run data preparation for this instrument/timeframe.",
            "severity": "error",
        },
        "feature_availability": {
            "summary": "Required feature vectors are missing",
            "detailed": "The job cannot start because the required feature vectors for the selected strategy are not pre‑computed.",
            "next_action": "Run feature pre‑computation for the selected strategy family, or switch to a strategy that uses available features.",
            "severity": "error",
        },
        "registry_consistency": {
            "summary": "Strategy registry inconsistency",
            "detailed": "The selected strategy is not present in the registry, or its parameters are invalid.",
            "next_action": "Refresh the strategy registry, or select a different strategy.",
            "severity": "error",
        },
        "resource_limits": {
            "summary": "Resource limits exceeded",
            "detailed": "The job was rejected because it would exceed available CPU/memory limits.",
            "next_action": "Reduce job concurrency, wait for other jobs to finish, or adjust resource limits in supervisor config.",
            "severity": "warning",
        },
        "duplicate_prevention": {
            "summary": "Duplicate job prevention",
            "detailed": "A similar job with identical parameters already succeeded recently.",
            "next_action": "If you intend to re‑run, confirm the duplicate warning and proceed.",
            "severity": "info",
        },
    }
    
    # Mapping from runtime error patterns to human‑readable summaries
    RUNTIME_ERROR_MAPPINGS = [
        {
            "pattern": "out of memory",
            "summary": "Job ran out of memory",
            "detailed": "The job exceeded the allocated memory limit and was terminated by the OS.",
            "next_action": "Reduce memory usage by selecting a smaller dataset, shorter timeframe, or increase memory limits.",
            "severity": "critical",
        },
        {
            "pattern": "timeout",
            "summary": "Job timed out",
            "detailed": "The job exceeded the maximum allowed runtime and was terminated.",
            "next_action": "Increase timeout limit, or split the job into smaller chunks.",
            "severity": "warning",
        },
        {
            "pattern": "segmentation fault",
            "summary": "Segmentation fault (crash)",
            "detailed": "The job crashed due to a memory access violation, likely a bug in the strategy or engine.",
            "next_action": "Report the crash to developers with the job logs and artifacts.",
            "severity": "critical",
        },
        {
            "pattern": "import error",
            "summary": "Module import failed",
            "detailed": "The job failed because a required Python module could not be imported.",
            "next_action": "Check that all dependencies are installed in the supervisor environment.",
            "severity": "error",
        },
    ]
    
    @staticmethod
    def extract_from_artifacts(artifacts: Dict[str, Any]) -> List[FailureReason]:
        """Extract failure reasons from job artifacts.
        
        Args:
            artifacts: Dictionary of artifacts as returned by supervisor API.
        
        Returns:
            List of FailureReason objects, sorted by severity (critical first).
        """
        reasons = list()
        
        # 1. Policy check failures
        policy_reasons = JobReasonService._extract_from_policy_check(artifacts)
        reasons.extend(policy_reasons)
        
        # 2. Runtime metrics failures
        runtime_reasons = JobReasonService._extract_from_runtime_metrics(artifacts)
        reasons.extend(runtime_reasons)
        
        # 3. Manifest failures (if any)
        manifest_reasons = JobReasonService._extract_from_manifest(artifacts)
        reasons.extend(manifest_reasons)
        
        # 4. Generic fallback if no specific reasons found
        if not reasons:
            reasons.append(JobReasonService._generic_failure_reason(artifacts))
        
        # Sort by severity order
        severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        reasons.sort(key=lambda r: severity_order.get(r.severity, 99))
        
        return reasons
    
    @staticmethod
    def _extract_from_policy_check(artifacts: Dict[str, Any]) -> List[FailureReason]:
        """Extract reasons from policy_check.json artifact."""
        reasons = list()
        policy_check = artifacts.get("policy_check")
        if not policy_check or not isinstance(policy_check, dict):
            return reasons
        
        status = policy_check.get("status")
        if status != "FAILED":
            return reasons
        
        gates = policy_check.get("gates", list())
        for gate in gates:
            gate_name = gate.get("name", "")
            gate_status = gate.get("status", "")
            gate_reason = gate.get("reason", "")
            
            if gate_status != "FAILED":
                continue
            
            # Look up mapping
            mapping = JobReasonService.POLICY_GATE_MAPPINGS.get(gate_name)
            if mapping:
                summary = mapping["summary"]
                detailed = mapping["detailed"]
                next_action = mapping["next_action"]
                severity = mapping["severity"]
            else:
                # Generic mapping
                summary = f"Policy gate '{gate_name}' failed"
                detailed = f"The policy gate '{gate_name}' rejected the job. Reason: {gate_reason}"
                next_action = "Check the policy configuration and ensure prerequisites are satisfied."
                severity = "error"
            
            reasons.append(FailureReason(
                summary=summary,
                detailed_reason=detailed,
                next_action=next_action,
                severity=severity,
                artifact_source="policy_check",
                raw_data=gate,
            ))
        
        return reasons
    
    @staticmethod
    def _extract_from_runtime_metrics(artifacts: Dict[str, Any]) -> List[FailureReason]:
        """Extract reasons from runtime_metrics.json artifact."""
        reasons = list()
        runtime_metrics = artifacts.get("runtime_metrics")
        if not runtime_metrics or not isinstance(runtime_metrics, dict):
            return reasons
        
        error = runtime_metrics.get("error", "")
        exit_code = runtime_metrics.get("exit_code")
        signal = runtime_metrics.get("signal")
        
        # Check for error message patterns
        if error:
            error_lower = error.lower()
            for mapping in JobReasonService.RUNTIME_ERROR_MAPPINGS:
                if mapping["pattern"] in error_lower:
                    reasons.append(FailureReason(
                        summary=mapping["summary"],
                        detailed_reason=mapping["detailed"],
                        next_action=mapping["next_action"],
                        severity=mapping["severity"],
                        artifact_source="runtime_metrics",
                        raw_data={"error": error, "exit_code": exit_code, "signal": signal},
                    ))
                    break
            else:
                # No pattern matched, generic error
                reasons.append(FailureReason(
                    summary="Runtime error",
                    detailed_reason=f"The job failed with error: {error}",
                    next_action="Examine the job logs for more details.",
                    severity="error",
                    artifact_source="runtime_metrics",
                    raw_data={"error": error, "exit_code": exit_code, "signal": signal},
                ))
        
        # Check exit code and signal
        if exit_code is not None and exit_code != 0:
            # Map common exit codes
            exit_map = {
                137: ("Job killed (SIGKILL)", "The job was terminated by the system, likely due to out‑of‑memory.", "Increase memory limits or reduce job memory usage.", "critical"),
                143: ("Job terminated (SIGTERM)", "The job received a termination signal, possibly due to a timeout.", "Increase timeout limit or optimize job runtime.", "warning"),
            }
            if exit_code in exit_map:
                summary, detailed, next_action, severity = exit_map[exit_code]
                reasons.append(FailureReason(
                    summary=summary,
                    detailed_reason=detailed,
                    next_action=next_action,
                    severity=severity,
                    artifact_source="runtime_metrics",
                    raw_data={"exit_code": exit_code, "signal": signal},
                ))
        
        if signal:
            signal_map = {
                "SIGSEGV": ("Segmentation fault", "The job crashed due to invalid memory access.", "Report the crash to developers with logs.", "critical"),
                "SIGABRT": ("Abort signal", "The job aborted, possibly due to an assertion failure.", "Check the job logs for assertion errors.", "error"),
            }
            if signal in signal_map:
                summary, detailed, next_action, severity = signal_map[signal]
                reasons.append(FailureReason(
                    summary=summary,
                    detailed_reason=detailed,
                    next_action=next_action,
                    severity=severity,
                    artifact_source="runtime_metrics",
                    raw_data={"signal": signal, "exit_code": exit_code},
                ))
        
        return reasons
    
    @staticmethod
    def _extract_from_manifest(artifacts: Dict[str, Any]) -> List[FailureReason]:
        """Extract reasons from manifest.json artifact (if present)."""
        # Currently not implemented; manifest failures are rare.
        return list()
    
    @staticmethod
    def _generic_failure_reason(artifacts: Dict[str, Any]) -> FailureReason:
        """Fallback generic failure reason."""
        return FailureReason(
            summary="Job failed",
            detailed_reason="No detailed failure information available in artifacts.",
            next_action="Check the job logs for more details.",
            severity="info",
            artifact_source="generic",
            raw_data=artifacts,
        )
    
    @staticmethod
    def format_reasons_for_display(reasons: List[FailureReason]) -> str:
        """Format failure reasons into a human‑readable multi‑line string."""
        if not reasons:
            return "No failure reasons identified."
        
        lines = list()
        for i, reason in enumerate(reasons, 1):
            lines.append(f"{i}. {reason.summary} ({reason.severity.upper()})")
            lines.append(f"   Reason: {reason.detailed_reason}")
            lines.append(f"   Next action: {reason.next_action}")
            lines.append("")
        
        return "\n".join(lines).strip()
    
    @staticmethod
    def get_primary_reason(reasons: List[FailureReason]) -> Optional[FailureReason]:
        """Return the most severe (primary) failure reason."""
        if not reasons:
            return None
        severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        return min(reasons, key=lambda r: severity_order.get(r.severity, 99))


# Convenience function for easy import
def explain_failure(artifacts: Dict[str, Any]) -> str:
    """One‑liner: get formatted failure explanation from artifacts."""
    reasons = JobReasonService.extract_from_artifacts(artifacts)
    return JobReasonService.format_reasons_for_display(reasons)


def get_failure_reasons(artifacts: Dict[str, Any]) -> List[FailureReason]:
    """Get structured failure reasons."""
    return JobReasonService.extract_from_artifacts(artifacts)
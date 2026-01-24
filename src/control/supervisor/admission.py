"""
AdmissionController - Pre-flight policy gate for job submission.
"""
from __future__ import annotations
import json
from typing import Dict, Any, List, Optional
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .db import SupervisorDB
from .models import JobSpec, JobStatus
from contracts.supervisor.evidence_schemas import (
    PolicyCheck,
    PolicyCheckBundle,
    stable_params_hash,
    now_iso,
)
from control.rejection_artifact import create_policy_rejection, write_rejection_artifact
from control.policy_enforcement import PolicyResult, write_policy_check_artifact


class AdmissionController:
    """Pre-flight policy gate that may REJECT jobs before they are queued."""
    
    def __init__(self, db: SupervisorDB):
        self.db = db
    
    def check(self, job_type: str, payload: Dict[str, Any]) -> PolicyCheckBundle:
        """
        Run all pre-flight policies and return a PolicyCheckBundle.
        
        If any policy fails, downstream_admissible will be False.
        """
        bundle = PolicyCheckBundle()
        
        # Policy 1: check_duplicate_fingerprint
        check1 = self._check_duplicate_fingerprint(job_type, payload)
        bundle.pre_flight_checks.append(check1)
        
        # Policy 2: check_timeframe_allowed
        check2 = self._check_timeframe_allowed(job_type, payload)
        bundle.pre_flight_checks.append(check2)
        
        # Policy 3: check_season_format
        check3 = self._check_season_format(job_type, payload)
        bundle.pre_flight_checks.append(check3)
        
        # Determine if all checks passed
        all_passed = all(check.passed for check in bundle.pre_flight_checks)
        bundle.downstream_admissible = all_passed
        
        return bundle
    
    def _check_duplicate_fingerprint(self, job_type: str, payload: Dict[str, Any]) -> PolicyCheck:
        """Check for duplicate job with same params_hash."""
        params_hash = stable_params_hash(payload)
        
        with self.db._connect() as conn:
            cursor = conn.execute("""
                SELECT job_id FROM jobs
                WHERE job_type = ?
                AND params_hash = ?
                AND state IN (?, ?, ?)
            """, (job_type, params_hash, JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED))
            duplicate = cursor.fetchone()
        
        if duplicate:
            return PolicyCheck(
                policy_name="check_duplicate_fingerprint",
                passed=False,
                message=f"Duplicate job found with same params_hash: {params_hash[:16]}...",
                checked_at=now_iso()
            )
        
        return PolicyCheck(
            policy_name="check_duplicate_fingerprint",
            passed=True,
            message=f"No duplicate found for params_hash: {params_hash[:16]}...",
            checked_at=now_iso()
        )
    
    def _check_timeframe_allowed(self, job_type: str, payload: Dict[str, Any]) -> PolicyCheck:
        """Check if timeframe parameter is allowed (15, 30, 60, 120, 240)."""
        # Only apply to job types that have timeframe parameter
        if job_type not in ["RUN_RESEARCH_WFS"]:
            return PolicyCheck(
                policy_name="check_timeframe_allowed",
                passed=True,
                message=f"Job type {job_type} does not require timeframe check",
                checked_at=now_iso()
            )
        
        timeframe = payload.get("timeframe")
        if timeframe is None:
            return PolicyCheck(
                policy_name="check_timeframe_allowed",
                passed=True,
                message="No timeframe parameter present",
                checked_at=now_iso()
            )
        
        allowed = {15, 30, 60, 120, 240}
        if timeframe in allowed:
            return PolicyCheck(
                policy_name="check_timeframe_allowed",
                passed=True,
                message=f"Timeframe {timeframe} is allowed",
                checked_at=now_iso()
            )
        else:
            return PolicyCheck(
                policy_name="check_timeframe_allowed",
                passed=False,
                message=f"Timeframe {timeframe} is not allowed. Allowed values: {sorted(allowed)}",
                checked_at=now_iso()
            )
    
    def _check_season_format(self, job_type: str, payload: Dict[str, Any]) -> PolicyCheck:
        """Validate YYYYQ# format if season exists."""
        # Only apply to job types that have season parameter
        if job_type not in ["BUILD_PORTFOLIO_V2"]:
            return PolicyCheck(
                policy_name="check_season_format",
                passed=True,
                message=f"Job type {job_type} does not require season check",
                checked_at=now_iso()
            )
        
        season = payload.get("season")
        if season is None:
            return PolicyCheck(
                policy_name="check_season_format",
                passed=True,
                message="No season parameter present",
                checked_at=now_iso()
            )
        
        # Check format: YYYYQ# where # is 1-4
        import re
        pattern = r'^\d{4}Q[1-4]$'
        if re.match(pattern, season):
            return PolicyCheck(
                policy_name="check_season_format",
                passed=True,
                message=f"Season {season} has valid format",
                checked_at=now_iso()
            )
        else:
            return PolicyCheck(
                policy_name="check_season_format",
                passed=False,
                message=f"Season {season} must be in format YYYYQ# (e.g., 2024Q1)",
                checked_at=now_iso()
            )


def submit_with_admission(
    db: SupervisorDB,
    spec: JobSpec,
    evidence_dir: str
) -> tuple[str, str, PolicyCheckBundle]:
    """
    Submit a job with admission control.
    
    Returns:
        tuple of (job_id, state, policy_check_bundle)
    """
    from pathlib import Path
    import os
    
    # Run admission check
    controller = AdmissionController(db)
    bundle = controller.check(spec.job_type, spec.params)
    
    params_hash = stable_params_hash(spec.params)
    
    def _preflight_results() -> list[PolicyResult]:
        return [
            PolicyResult(
                allowed=check.passed,
                code=check.policy_name,
                message=check.message,
                details={"checked_at": check.checked_at},
                stage="preflight",
            )
            for check in bundle.pre_flight_checks
        ]

    if not bundle.downstream_admissible:
        # Job should be REJECTED
        rejection_reason = "Failed pre-flight policies"
        job_id = db.submit_rejected_job(spec, params_hash, rejection_reason)
        
        # Write evidence bundle
        job_evidence_dir = Path(evidence_dir) / job_id
        job_evidence_dir.mkdir(parents=True, exist_ok=True)
        
        failed_policies = [check.policy_name for check in bundle.pre_flight_checks if not check.passed]
        write_policy_check_artifact(
            job_id,
            spec.job_type,
            preflight_results=_preflight_results(),
            final_reason={
                "policy_stage": "preflight",
                "failure_code": "POLICY_REJECT_PRE_FLIGHT",
                "failure_message": rejection_reason,
                "failure_details": {"failed_policies": failed_policies},
            },
            extra_paths=(job_evidence_dir,),
        )
        # Write inputs_fingerprint.json
        inputs_fingerprint = {
            "params_hash": params_hash,
            "dependencies": {},  # TODO: Get actual dependencies
            "code_fingerprint": "unknown",  # TODO: Get git commit hash
            "hash_version": "v1"
        }
        fingerprint_path = job_evidence_dir / "inputs_fingerprint.json"
        with open(fingerprint_path, 'w') as f:
            json.dump(inputs_fingerprint, f, indent=2)
        
        # Write manifest.json
        manifest = {
            "job_id": job_id,
            "job_type": spec.job_type,
            "submitted_at": now_iso(),
            "state": JobStatus.REJECTED,
            "rejection_reason": rejection_reason
        }
        manifest_path = job_evidence_dir / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        # Write standardized rejection artifact
        rejection_artifact = create_policy_rejection(
            policy_name="pre_flight_policies",
            failure_message=f"Failed pre-flight policies: {', '.join(failed_policies)}",
            job_id=job_id,
            additional_context={
                "failed_policies": failed_policies,
                "policy_check_bundle": asdict(bundle)
            }
        )
        rejection_path = job_evidence_dir / "rejection.json"
        rejection_artifact.write(rejection_path)
        
        return job_id, JobStatus.REJECTED, bundle
    else:
        # Job is admissible, submit as QUEUED with params_hash
        job_id = db.submit_job(spec, params_hash=params_hash, state=JobStatus.QUEUED)
        
        # Still write initial evidence (optional)
        job_evidence_dir = Path(evidence_dir) / job_id
        job_evidence_dir.mkdir(parents=True, exist_ok=True)
        
        write_policy_check_artifact(
            job_id,
            spec.job_type,
            preflight_results=_preflight_results(),
            final_reason={
                "policy_stage": "",
                "failure_code": "",
                "failure_message": "",
                "failure_details": {},
            },
            extra_paths=(job_evidence_dir,),
        )
        return job_id, JobStatus.QUEUED, bundle

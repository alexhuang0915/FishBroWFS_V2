"""
QualityGate - Post-flight result admission control.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import asdict

from src.contracts.supervisor.evidence_schemas import PolicyCheck, now_iso


class QualityGate:
    """Post-flight quality gate checks."""
    
    def check(
        self,
        job_id: str,
        handler_name: str,
        result: Dict[str, Any],
        evidence_dir: Path
    ) -> List[PolicyCheck]:
        """Run all post-flight checks."""
        checks = []
        
        # Check 1: manifest_present
        checks.append(self._check_manifest_present(evidence_dir))
        
        # Check 2: required_outputs_exist
        checks.append(self._check_required_outputs_exist(job_id, handler_name, evidence_dir))
        
        # Additional checks can be added here
        
        return checks
    
    def _check_manifest_present(self, evidence_dir: Path) -> PolicyCheck:
        """Check that manifest.json exists and is valid."""
        manifest_path = evidence_dir / "manifest.json"
        
        if not manifest_path.exists():
            return PolicyCheck(
                policy_name="check_manifest_present",
                passed=False,
                message="manifest.json does not exist",
                checked_at=now_iso()
            )
        
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            required_fields = ["job_id", "job_type", "state", "start_time", "end_time"]
            missing = [field for field in required_fields if field not in manifest]
            
            if missing:
                return PolicyCheck(
                    policy_name="check_manifest_present",
                    passed=False,
                    message=f"manifest.json missing fields: {missing}",
                    checked_at=now_iso()
                )
            
            return PolicyCheck(
                policy_name="check_manifest_present",
                passed=True,
                message="manifest.json exists and is valid",
                checked_at=now_iso()
            )
            
        except json.JSONDecodeError as e:
            return PolicyCheck(
                policy_name="check_manifest_present",
                passed=False,
                message=f"manifest.json is invalid JSON: {e}",
                checked_at=now_iso()
            )
    
    def _check_required_outputs_exist(
        self,
        job_id: str,
        handler_name: str,
        evidence_dir: Path
    ) -> PolicyCheck:
        """Check that required outputs exist (job-type aware)."""
        # Define required outputs per job type
        required_outputs = {
            "RUN_RESEARCH_V2": ["manifest.json", "policy_check.json", "inputs_fingerprint.json"],
            "RUN_PLATEAU_V2": ["manifest.json", "policy_check.json", "inputs_fingerprint.json"],
            "RUN_FREEZE_V2": ["manifest.json", "policy_check.json", "inputs_fingerprint.json"],
            "RUN_COMPILE_V2": ["manifest.json", "policy_check.json", "inputs_fingerprint.json"],
            "BUILD_PORTFOLIO_V2": ["manifest.json", "policy_check.json", "inputs_fingerprint.json"],
        }
        
        # Get job type from handler name or evidence
        job_type = self._infer_job_type(handler_name)
        
        if job_type not in required_outputs:
            return PolicyCheck(
                policy_name="check_required_outputs_exist",
                passed=True,
                message=f"No output requirements defined for job type {job_type}",
                checked_at=now_iso()
            )
        
        missing = []
        for output_file in required_outputs[job_type]:
            if not (evidence_dir / output_file).exists():
                missing.append(output_file)
        
        if missing:
            return PolicyCheck(
                policy_name="check_required_outputs_exist",
                passed=False,
                message=f"Missing required outputs: {missing}",
                checked_at=now_iso()
            )
        
        return PolicyCheck(
            policy_name="check_required_outputs_exist",
            passed=True,
            message="All required outputs exist",
            checked_at=now_iso()
        )
    
    def _infer_job_type(self, handler_name: str) -> str:
        """Infer job type from handler name."""
        # Map handler class names to job types
        mapping = {
            "RunResearchV2Handler": "RUN_RESEARCH_V2",
            "RunPlateauV2Handler": "RUN_PLATEAU_V2",
            "RunFreezeV2Handler": "RUN_FREEZE_V2",
            "RunCompileV2Handler": "RUN_COMPILE_V2",
            "BuildPortfolioV2Handler": "BUILD_PORTFOLIO_V2",
        }
        
        # Try exact match
        if handler_name in mapping:
            return mapping[handler_name]
        
        # Try partial match
        for key, value in mapping.items():
            if key in handler_name:
                return value
        
        # Default fallback
        return "UNKNOWN"
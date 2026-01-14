"""
Replay/Audit Resolver for Route 6 Closed Loop.

Verifies deployment chain integrity by replaying evidence → portfolio → deployment flow.
Validates hash chains, artifact integrity, and audit trail completeness.

Hybrid BC v1.1 compliant: No portfolio math changes, no backend API changes.
"""

from __future__ import annotations

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from pydantic import BaseModel, Field

from core.portfolio.evidence_aggregator import EvidenceIndexV1, EvidenceAggregator
from core.portfolio.portfolio_orchestrator import PortfolioRunRecordV1
from core.deployment.deployment_bundle_builder import DeploymentManifestV1, DeploymentBundleBuilder

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class AuditResultV1(BaseModel):
    """Result of an audit/replay verification."""
    audit_id: str
    audit_type: str  # "evidence", "portfolio", "deployment", "full_chain"
    target_path: str
    passed: bool
    checks: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        frozen = True


class ReplayResultV1(BaseModel):
    """Result of replaying the full evidence → portfolio → deployment chain."""
    replay_id: str
    evidence_audit: Optional[AuditResultV1] = None
    portfolio_audit: Optional[AuditResultV1] = None
    deployment_audit: Optional[AuditResultV1] = None
    chain_integrity: bool = False
    chain_checks: List[str] = Field(default_factory=list)
    chain_warnings: List[str] = Field(default_factory=list)
    chain_errors: List[str] = Field(default_factory=list)
    summary: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        frozen = True


# ============================================================================
# Replay/Audit Resolver
# ============================================================================

class ReplayResolver:
    """Resolves and verifies deployment chain integrity."""
    
    def __init__(
        self,
        outputs_root: Path,
    ):
        self.outputs_root = outputs_root.resolve()
        # Create evidence aggregator with a dummy jobs root (won't be used for scanning)
        self.evidence_aggregator = EvidenceAggregator(jobs_root=Path("."))
        self.deployment_builder = DeploymentBundleBuilder(outputs_root=outputs_root)
        
        logger.info(f"ReplayResolver initialized with outputs_root: {self.outputs_root}")
    
    def compute_sha256(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def compute_string_sha256(self, content: str) -> str:
        """Compute SHA256 hash of a string."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def audit_evidence_index(self, evidence_index_path: Path) -> AuditResultV1:
        """Audit evidence index integrity."""
        audit_id = f"evidence_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        checks = []
        warnings = []
        errors = []
        details = {}
        
        try:
            # Check if file exists
            if not evidence_index_path.exists():
                errors.append(f"Evidence index not found: {evidence_index_path}")
                return AuditResultV1(
                    audit_id=audit_id,
                    audit_type="evidence",
                    target_path=str(evidence_index_path),
                    passed=False,
                    checks=checks,
                    warnings=warnings,
                    errors=errors,
                    details=details,
                )
            
            checks.append("Evidence index file exists")
            
            # Load and validate JSON
            try:
                with open(evidence_index_path, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                checks.append("Evidence index is valid JSON")
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in evidence index: {e}")
                return AuditResultV1(
                    audit_id=audit_id,
                    audit_type="evidence",
                    target_path=str(evidence_index_path),
                    passed=False,
                    checks=checks,
                    warnings=warnings,
                    errors=errors,
                    details=details,
                )
            
            # Validate schema version
            schema_version = index_data.get("schema_version")
            if schema_version != "v1":
                warnings.append(f"Unexpected schema version: {schema_version} (expected: v1)")
            else:
                checks.append(f"Schema version is {schema_version}")
            
            # Check job count matches jobs dict
            job_count = index_data.get("job_count", 0)
            jobs = index_data.get("jobs", {})
            actual_job_count = len(jobs)
            
            if job_count != actual_job_count:
                warnings.append(f"Job count mismatch: declared={job_count}, actual={actual_job_count}")
            else:
                checks.append(f"Job count matches: {job_count}")
            
            # Check hash file if exists
            hash_path = evidence_index_path.parent / "evidence_index_v1.sha256"
            if hash_path.exists():
                try:
                    with open(hash_path, 'r', encoding='utf-8') as f:
                        hash_line = f.read().strip()
                    
                    # Parse hash line (format: "hash  filename")
                    if "  " in hash_line:
                        expected_hash = hash_line.split("  ")[0]
                        
                        # Compute actual hash
                        actual_hash = self.compute_sha256(evidence_index_path)
                        
                        if expected_hash == actual_hash:
                            checks.append("Hash verification passed")
                        else:
                            errors.append(f"Hash mismatch: expected={expected_hash[:16]}..., actual={actual_hash[:16]}...")
                except Exception as e:
                    warnings.append(f"Failed to verify hash: {e}")
            else:
                warnings.append("No hash file found for evidence index")
            
            # Sample job validation
            if jobs:
                sample_job_id = list(jobs.keys())[0]
                sample_job = jobs[sample_job_id]
                
                details["sample_job_id"] = sample_job_id
                details["sample_job_gate_status"] = sample_job.get("gate_status", "UNKNOWN")
                details["sample_job_lifecycle"] = sample_job.get("lifecycle", "UNKNOWN")
                
                # Check if job directory exists
                job_dir = self.outputs_root / "jobs" / sample_job_id
                if job_dir.exists():
                    checks.append(f"Sample job directory exists: {sample_job_id}")
                else:
                    warnings.append(f"Sample job directory not found: {sample_job_id}")
            
            details["total_jobs"] = actual_job_count
            details["schema_version"] = schema_version
            
            passed = len(errors) == 0
            
            return AuditResultV1(
                audit_id=audit_id,
                audit_type="evidence",
                target_path=str(evidence_index_path),
                passed=passed,
                checks=checks,
                warnings=warnings,
                errors=errors,
                details=details,
            )
            
        except Exception as e:
            errors.append(f"Unexpected error during evidence audit: {e}")
            return AuditResultV1(
                audit_id=audit_id,
                audit_type="evidence",
                target_path=str(evidence_index_path),
                passed=False,
                checks=checks,
                warnings=warnings,
                errors=errors,
                details=details,
            )
    
    def audit_portfolio_run(self, portfolio_run_record_path: Path) -> AuditResultV1:
        """Audit portfolio run record integrity."""
        audit_id = f"portfolio_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        checks = []
        warnings = []
        errors = []
        details = {}
        
        try:
            # Check if file exists
            if not portfolio_run_record_path.exists():
                errors.append(f"Portfolio run record not found: {portfolio_run_record_path}")
                return AuditResultV1(
                    audit_id=audit_id,
                    audit_type="portfolio",
                    target_path=str(portfolio_run_record_path),
                    passed=False,
                    checks=checks,
                    warnings=warnings,
                    errors=errors,
                    details=details,
                )
            
            checks.append("Portfolio run record file exists")
            
            # Load and validate JSON
            try:
                with open(portfolio_run_record_path, 'r', encoding='utf-8') as f:
                    record_data = json.load(f)
                checks.append("Portfolio run record is valid JSON")
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in portfolio run record: {e}")
                return AuditResultV1(
                    audit_id=audit_id,
                    audit_type="portfolio",
                    target_path=str(portfolio_run_record_path),
                    passed=False,
                    checks=checks,
                    warnings=warnings,
                    errors=errors,
                    details=details,
                )
            
            # Validate required fields
            required_fields = ["portfolio_run_id", "portfolio_id", "selected_job_ids"]
            missing_fields = [field for field in required_fields if field not in record_data]
            
            if missing_fields:
                errors.append(f"Missing required fields: {missing_fields}")
            else:
                checks.append("All required fields present")
            
            portfolio_run_id = record_data.get("portfolio_run_id")
            portfolio_id = record_data.get("portfolio_id")
            selected_job_ids = record_data.get("selected_job_ids", [])
            submitted_job_id = record_data.get("submitted_job_id")
            
            details["portfolio_run_id"] = portfolio_run_id
            details["portfolio_id"] = portfolio_id
            details["selected_job_count"] = len(selected_job_ids)
            details["submitted_job_id"] = submitted_job_id
            
            # Check hash file if exists
            hash_path = portfolio_run_record_path.parent / "portfolio_run_record_v1.sha256"
            if hash_path.exists():
                try:
                    with open(hash_path, 'r', encoding='utf-8') as f:
                        hash_line = f.read().strip()
                    
                    if "  " in hash_line:
                        expected_hash = hash_line.split("  ")[0]
                        actual_hash = self.compute_sha256(portfolio_run_record_path)
                        
                        if expected_hash == actual_hash:
                            checks.append("Hash verification passed")
                        else:
                            errors.append(f"Hash mismatch: expected={expected_hash[:16]}..., actual={actual_hash[:16]}...")
                except Exception as e:
                    warnings.append(f"Failed to verify hash: {e}")
            else:
                warnings.append("No hash file found for portfolio run record")
            
            # Check if submitted job exists
            if submitted_job_id:
                job_dir = self.outputs_root / "jobs" / submitted_job_id
                if job_dir.exists():
                    checks.append(f"Submitted job directory exists: {submitted_job_id}")
                    
                    # Check for admission artifacts
                    admission_artifacts = [
                        "portfolio_config.json",
                        "admission_decision.json",
                        "admission_report.json",
                    ]
                    
                    found_artifacts = []
                    for artifact in admission_artifacts:
                        if (job_dir / artifact).exists():
                            found_artifacts.append(artifact)
                    
                    if found_artifacts:
                        checks.append(f"Found admission artifacts: {len(found_artifacts)}")
                        details["admission_artifacts_found"] = found_artifacts
                    else:
                        warnings.append("No admission artifacts found in job directory")
                else:
                    warnings.append(f"Submitted job directory not found: {submitted_job_id}")
            
            # Check if selected job directories exist
            missing_job_dirs = []
            for job_id in selected_job_ids[:5]:  # Check first 5 to avoid excessive I/O
                job_dir = self.outputs_root / "jobs" / job_id
                if not job_dir.exists():
                    missing_job_dirs.append(job_id)
            
            if missing_job_dirs:
                warnings.append(f"Some selected job directories not found: {len(missing_job_dirs)}")
                details["missing_job_dirs_sample"] = missing_job_dirs[:3]
            else:
                checks.append("Selected job directories exist (sampled)")
            
            # Check if evidence index exists in run directory
            evidence_index_path = portfolio_run_record_path.parent / "evidence_index_v1.json"
            if evidence_index_path.exists():
                checks.append("Evidence index exists in run directory")
            else:
                warnings.append("Evidence index not found in run directory")
            
            passed = len(errors) == 0
            
            return AuditResultV1(
                audit_id=audit_id,
                audit_type="portfolio",
                target_path=str(portfolio_run_record_path),
                passed=passed,
                checks=checks,
                warnings=warnings,
                errors=errors,
                details=details,
            )
            
        except Exception as e:
            errors.append(f"Unexpected error during portfolio audit: {e}")
            return AuditResultV1(
                audit_id=audit_id,
                audit_type="portfolio",
                target_path=str(portfolio_run_record_path),
                passed=False,
                checks=checks,
                warnings=warnings,
                errors=errors,
                details=details,
            )
    
    def audit_deployment_bundle(self, deployment_manifest_path: Path) -> AuditResultV1:
        """Audit deployment bundle integrity."""
        audit_id = f"deployment_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        checks = []
        warnings = []
        errors = []
        details = {}
        
        try:
            # Check if file exists
            if not deployment_manifest_path.exists():
                errors.append(f"Deployment manifest not found: {deployment_manifest_path}")
                return AuditResultV1(
                    audit_id=audit_id,
                    audit_type="deployment",
                    target_path=str(deployment_manifest_path),
                    passed=False,
                    checks=checks,
                    warnings=warnings,
                    errors=errors,
                    details=details,
                )
            
            checks.append("Deployment manifest file exists")
            
            # Load and validate JSON
            try:
                with open(deployment_manifest_path, 'r', encoding='utf-8') as f:
                    manifest_data = json.load(f)
                checks.append("Deployment manifest is valid JSON")
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in deployment manifest: {e}")
                return AuditResultV1(
                    audit_id=audit_id,
                    audit_type="deployment",
                    target_path=str(deployment_manifest_path),
                    passed=False,
                    checks=checks,
                    warnings=warnings,
                    errors=errors,
                    details=details,
                )
            
            # Validate required fields
            required_fields = ["deployment_id", "portfolio_run_id", "portfolio_id", "manifest_hash", "bundle_hash"]
            missing_fields = [field for field in required_fields if field not in manifest_data]
            
            if missing_fields:
                errors.append(f"Missing required fields: {missing_fields}")
            else:
                checks.append("All required fields present")
            
            deployment_id = manifest_data.get("deployment_id")
            portfolio_run_id = manifest_data.get("portfolio_run_id")
            portfolio_id = manifest_data.get("portfolio_id")
            manifest_hash = manifest_data.get("manifest_hash")
            bundle_hash = manifest_data.get("bundle_hash")
            
            details["deployment_id"] = deployment_id
            details["portfolio_run_id"] = portfolio_run_id
            details["portfolio_id"] = portfolio_id
            
            # Verify manifest hash
            try:
                # Compute hash of manifest (excluding hash fields)
                manifest_dict = manifest_data.copy()
                manifest_dict["manifest_hash"] = ""
                manifest_dict["bundle_hash"] = ""
                
                manifest_json = json.dumps(manifest_dict, sort_keys=True, indent=2)
                computed_manifest_hash = self.compute_string_sha256(manifest_json)
                
                if manifest_hash == computed_manifest_hash:
                    checks.append("Manifest hash verification passed")
                else:
                    errors.append(f"Manifest hash mismatch: expected={manifest_hash[:16]}..., computed={computed_manifest_hash[:16]}...")
            except Exception as e:
                errors.append(f"Failed to verify manifest hash: {e}")
            
            # Check if bundle exists
            deployment_dir = deployment_manifest_path.parent
            bundle_path = deployment_dir.parent / f"{deployment_id}.zip"
            
            if bundle_path.exists():
                checks.append(f"Deployment bundle exists: {bundle_path.name}")
                
                # Verify bundle hash
                try:
                    computed_bundle_hash = self.compute_sha256(bundle_path)
                    
                    if bundle_hash == computed_bundle_hash:
                        checks.append("Bundle hash verification passed")
                    else:
                        errors.append(f"Bundle hash mismatch: expected={bundle_hash[:16]}..., computed={computed_bundle_hash[:16]}...")
                except Exception as e:
                    errors.append(f"Failed to verify bundle hash: {e}")
            else:
                warnings.append(f"Deployment bundle not found: {bundle_path}")
            
            # Check artifacts
            artifacts = manifest_data.get("artifacts", [])
            artifact_count = manifest_data.get("artifact_count", 0)
            
            if len(artifacts) != artifact_count:
                warnings.append(f"Artifact count mismatch: declared={artifact_count}, actual={len(artifacts)}")
            else:
                checks.append(f"Artifact count matches: {artifact_count}")
            
            # Sample artifact verification
            if artifacts:
                sample_artifact = artifacts[0]
                artifact_id = sample_artifact.get("artifact_id")
                checksum = sample_artifact.get("checksum_sha256")
                target_path = sample_artifact.get("target_path")
                
                # Check if artifact exists in deployment directory
                artifact_path = deployment_dir / target_path
                if artifact_path.exists():
                    checks.append(f"Sample artifact exists: {target_path}")
                    
                    # Verify artifact checksum
                    try:
                        computed_checksum = self.compute_sha256(artifact_path)
                        
                        if checksum == computed_checksum:
                            checks.append("Sample artifact checksum verification passed")
                        else:
                            warnings.append(f"Sample artifact checksum mismatch: expected={checksum[:16]}..., computed={computed_checksum[:16]}...")
                    except Exception as e:
                        warnings.append(f"Failed to verify sample artifact checksum: {e}")
                else:
                    warnings.append(f"Sample artifact not found: {target_path}")
                
                details["sample_artifact_id"] = artifact_id
                details["sample_artifact_type"] = sample_artifact.get("artifact_type")
            
            # Check previous deployment hash chain
            previous_deployment_hash = manifest_data.get("previous_deployment_hash")
            if previous_deployment_hash:
                checks.append("Previous deployment hash present (chain of custody)")
                details["previous_deployment_hash"] = previous_deployment_hash[:16] + "..."
            else:
                warnings.append("No previous deployment hash (first deployment in chain)")
            
            passed = len(errors) == 0
            
            return AuditResultV1(
                audit_id=audit_id,
                audit_type="deployment",
                target_path=str(deployment_manifest_path),
                passed=passed,
                checks=checks,
                warnings=warnings,
                errors=errors,
                details=details,
            )
            
        except Exception as e:
            errors.append(f"Unexpected error during deployment audit: {e}")
            return AuditResultV1(
                audit_id=audit_id,
                audit_type="deployment",
                target_path=str(deployment_manifest_path),
                passed=False,
                checks=checks,
                warnings=warnings,
                errors=errors,
                details=details,
            )
    
    def replay_full_chain(
        self,
        evidence_index_path: Optional[Path] = None,
        portfolio_run_record_path: Optional[Path] = None,
        deployment_manifest_path: Optional[Path] = None,
    ) -> ReplayResultV1:
        """
        Replay and verify the full evidence → portfolio → deployment chain.
        
        Args:
            evidence_index_path: Path to evidence_index_v1.json (optional, will search)
            portfolio_run_record_path: Path to portfolio_run_record_v1.json (optional, will search)
            deployment_manifest_path: Path to deployment_manifest_v1.json (optional, will search)
        
        Returns:
            ReplayResultV1 with full chain verification results
        """
        replay_id = f"replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        chain_checks = []
        chain_warnings = []
        chain_errors = []
        
        # Find files if not provided
        if evidence_index_path is None:
            # Look for evidence index in default location
            default_path = self.outputs_root / "portfolio" / "evidence_index_v1.json"
            if default_path.exists():
                evidence_index_path = default_path
                chain_checks.append(f"Found evidence index at default location: {default_path}")
            else:
                chain_warnings.append("Evidence index not found at default location")
        
        if portfolio_run_record_path is None:
            # Look for portfolio run records
            portfolio_runs_dir = self.outputs_root / "portfolio" / "runs"
            if portfolio_runs_dir.exists():
                # Find most recent portfolio run record
                portfolio_run_dirs = []
                for item in portfolio_runs_dir.iterdir():
                    if item.is_dir():
                        record_path = item / "portfolio_run_record_v1.json"
                        if record_path.exists():
                            portfolio_run_dirs.append((item.stat().st_mtime, record_path))
                
                if portfolio_run_dirs:
                    # Sort by modification time (newest first)
                    portfolio_run_dirs.sort(key=lambda x: x[0], reverse=True)
                    portfolio_run_record_path = portfolio_run_dirs[0][1]
                    chain_checks.append(f"Found most recent portfolio run record: {portfolio_run_record_path}")
                else:
                    chain_warnings.append("No portfolio run records found")
            else:
                chain_warnings.append("Portfolio runs directory not found")
        
        if deployment_manifest_path is None:
            # Look for deployment manifests
            deployments_dir = self.outputs_root / "deployments"
            if deployments_dir.exists():
                # Find most recent deployment manifest
                deployment_dirs = []
                for item in deployments_dir.iterdir():
                    if item.is_dir():
                        manifest_path = item / "deployment_manifest_v1.json"
                        if manifest_path.exists():
                            deployment_dirs.append((item.stat().st_mtime, manifest_path))
                
                if deployment_dirs:
                    # Sort by modification time (newest first)
                    deployment_dirs.sort(key=lambda x: x[0], reverse=True)
                    deployment_manifest_path = deployment_dirs[0][1]
                    chain_checks.append(f"Found most recent deployment manifest: {deployment_manifest_path}")
                else:
                    chain_warnings.append("No deployment manifests found")
            else:
                chain_warnings.append("Deployments directory not found")
        
        # Perform audits
        evidence_audit = None
        portfolio_audit = None
        deployment_audit = None
        
        if evidence_index_path and evidence_index_path.exists():
            chain_checks.append("Starting evidence audit...")
            evidence_audit = self.audit_evidence_index(evidence_index_path)
            
            if evidence_audit.passed:
                chain_checks.append("Evidence audit passed")
            else:
                chain_errors.append("Evidence audit failed")
                chain_errors.extend(evidence_audit.errors)
        else:
            chain_warnings.append("Skipping evidence audit (file not found)")
        
        if portfolio_run_record_path and portfolio_run_record_path.exists():
            chain_checks.append("Starting portfolio audit...")
            portfolio_audit = self.audit_portfolio_run(portfolio_run_record_path)
            
            if portfolio_audit.passed:
                chain_checks.append("Portfolio audit passed")
            else:
                chain_errors.append("Portfolio audit failed")
                chain_errors.extend(portfolio_audit.errors)
        else:
            chain_warnings.append("Skipping portfolio audit (file not found)")
        
        if deployment_manifest_path and deployment_manifest_path.exists():
            chain_checks.append("Starting deployment audit...")
            deployment_audit = self.audit_deployment_bundle(deployment_manifest_path)
            
            if deployment_audit.passed:
                chain_checks.append("Deployment audit passed")
            else:
                chain_errors.append("Deployment audit failed")
                chain_errors.extend(deployment_audit.errors)
        else:
            chain_warnings.append("Skipping deployment audit (file not found)")
        
        # Check chain integrity
        chain_integrity = True
        
        # Verify portfolio run references evidence index
        if portfolio_audit and evidence_audit:
            portfolio_details = portfolio_audit.details
            evidence_details = evidence_audit.details
            
            # Check if portfolio run directory contains evidence index
            portfolio_run_dir = Path(portfolio_run_record_path).parent
            evidence_index_in_run = portfolio_run_dir / "evidence_index_v1.json"
            
            if evidence_index_in_run.exists():
                chain_checks.append("Portfolio run contains evidence index (provenance)")
            else:
                chain_warnings.append("Portfolio run does not contain evidence index")
        
        # Verify deployment references portfolio run
        if deployment_audit and portfolio_audit:
            deployment_details = deployment_audit.details
            portfolio_details = portfolio_audit.details
            
            deployment_portfolio_run_id = deployment_details.get("portfolio_run_id")
            portfolio_run_id = portfolio_details.get("portfolio_run_id")
            
            if deployment_portfolio_run_id and portfolio_run_id:
                if deployment_portfolio_run_id == portfolio_run_id:
                    chain_checks.append("Deployment references correct portfolio run")
                else:
                    chain_errors.append(f"Deployment references different portfolio run: {deployment_portfolio_run_id} != {portfolio_run_id}")
                    chain_integrity = False
            else:
                chain_warnings.append("Cannot verify deployment-portfolio run reference (missing IDs)")
        
        # Determine overall chain integrity
        chain_integrity = chain_integrity and len(chain_errors) == 0
        
        # Create summary
        summary_parts = []
        
        if evidence_audit:
            summary_parts.append(f"Evidence: {'✓' if evidence_audit.passed else '✗'} ({evidence_audit.details.get('total_jobs', 0)} jobs)")
        
        if portfolio_audit:
            summary_parts.append(f"Portfolio: {'✓' if portfolio_audit.passed else '✗'} ({portfolio_audit.details.get('selected_job_count', 0)} candidates)")
        
        if deployment_audit:
            summary_parts.append(f"Deployment: {'✓' if deployment_audit.passed else '✗'} ({deployment_audit.details.get('artifact_count', 0)} artifacts)")
        
        summary = f"Chain integrity: {'✓ PASS' if chain_integrity else '✗ FAIL'} | " + " | ".join(summary_parts)
        
        return ReplayResultV1(
            replay_id=replay_id,
            evidence_audit=evidence_audit,
            portfolio_audit=portfolio_audit,
            deployment_audit=deployment_audit,
            chain_integrity=chain_integrity,
            chain_checks=chain_checks,
            chain_warnings=chain_warnings,
            chain_errors=chain_errors,
            summary=summary,
        )


# ============================================================================
# CLI Interface
# ============================================================================

def main_cli():
    """Command-line interface for replay/audit resolver."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Replay and verify evidence → portfolio → deployment chain integrity"
    )
    parser.add_argument(
        "command",
        choices=["audit", "replay"],
        help="Command to execute"
    )
    parser.add_argument(
        "--evidence-index",
        type=Path,
        help="Path to evidence_index_v1.json"
    )
    parser.add_argument(
        "--portfolio-run-record",
        type=Path,
        help="Path to portfolio_run_record_v1.json"
    )
    parser.add_argument(
        "--deployment-manifest",
        type=Path,
        help="Path to deployment_manifest_v1.json"
    )
    parser.add_argument(
        "--audit-type",
        type=str,
        choices=["evidence", "portfolio", "deployment"],
        help="Type of audit to perform (for audit command)"
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        required=True,
        help="Root outputs directory"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    resolver = ReplayResolver(outputs_root=args.outputs_root)
    
    if args.command == "audit":
        if not args.audit_type:
            print("✗ --audit-type is required for audit command")
            return 1
        
        print(f"Performing {args.audit_type} audit...")
        
        try:
            if args.audit_type == "evidence":
                if not args.evidence_index:
                    print("✗ --evidence-index is required for evidence audit")
                    return 1
                
                result = resolver.audit_evidence_index(args.evidence_index)
                
            elif args.audit_type == "portfolio":
                if not args.portfolio_run_record:
                    print("✗ --portfolio-run-record is required for portfolio audit")
                    return 1
                
                result = resolver.audit_portfolio_run(args.portfolio_run_record)
                
            elif args.audit_type == "deployment":
                if not args.deployment_manifest:
                    print("✗ --deployment-manifest is required for deployment audit")
                    return 1
                
                result = resolver.audit_deployment_bundle(args.deployment_manifest)
            
            else:
                print(f"✗ Unknown audit type: {args.audit_type}")
                return 1
            
            # Print results
            print(f"\n{'='*60}")
            print(f"AUDIT RESULT: {'✓ PASSED' if result.passed else '✗ FAILED'}")
            print(f"Audit ID: {result.audit_id}")
            print(f"Target: {result.target_path}")
            print(f"Type: {result.audit_type}")
            print(f"{'='*60}")
            
            if result.checks:
                print(f"\nChecks ({len(result.checks)}):")
                for check in result.checks:
                    print(f"  ✓ {check}")
            
            if result.warnings:
                print(f"\nWarnings ({len(result.warnings)}):")
                for warning in result.warnings:
                    print(f"  ⚠️  {warning}")
            
            if result.errors:
                print(f"\nErrors ({len(result.errors)}):")
                for error in result.errors:
                    print(f"  ✗ {error}")
            
            if result.details:
                print(f"\nDetails:")
                for key, value in result.details.items():
                    print(f"  {key}: {value}")
            
            return 0 if result.passed else 1
            
        except Exception as e:
            print(f"✗ Audit failed: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    elif args.command == "replay":
        print("Replaying full evidence → portfolio → deployment chain...")
        
        try:
            result = resolver.replay_full_chain(
                evidence_index_path=args.evidence_index,
                portfolio_run_record_path=args.portfolio_run_record,
                deployment_manifest_path=args.deployment_manifest,
            )
            
            # Print results
            print(f"\n{'='*60}")
            print(f"REPLAY RESULT: {'✓ CHAIN INTEGRITY PASSED' if result.chain_integrity else '✗ CHAIN INTEGRITY FAILED'}")
            print(f"Replay ID: {result.replay_id}")
            print(f"Summary: {result.summary}")
            print(f"{'='*60}")
            
            # Print component results
            if result.evidence_audit:
                print(f"\nEvidence Audit: {'✓ PASSED' if result.evidence_audit.passed else '✗ FAILED'}")
                print(f"  Jobs: {result.evidence_audit.details.get('total_jobs', 'N/A')}")
                print(f"  Checks: {len(result.evidence_audit.checks)}, Warnings: {len(result.evidence_audit.warnings)}, Errors: {len(result.evidence_audit.errors)}")
            
            if result.portfolio_audit:
                print(f"\nPortfolio Audit: {'✓ PASSED' if result.portfolio_audit.passed else '✗ FAILED'}")
                print(f"  Candidates: {result.portfolio_audit.details.get('selected_job_count', 'N/A')}")
                print(f"  Checks: {len(result.portfolio_audit.checks)}, Warnings: {len(result.portfolio_audit.warnings)}, Errors: {len(result.portfolio_audit.errors)}")
            
            if result.deployment_audit:
                print(f"\nDeployment Audit: {'✓ PASSED' if result.deployment_audit.passed else '✗ FAILED'}")
                print(f"  Artifacts: {result.deployment_audit.details.get('artifact_count', 'N/A')}")
                print(f"  Checks: {len(result.deployment_audit.checks)}, Warnings: {len(result.deployment_audit.warnings)}, Errors: {len(result.deployment_audit.errors)}")
            
            # Print chain checks
            if result.chain_checks:
                print(f"\nChain Checks ({len(result.chain_checks)}):")
                for check in result.chain_checks:
                    print(f"  ✓ {check}")
            
            if result.chain_warnings:
                print(f"\nChain Warnings ({len(result.chain_warnings)}):")
                for warning in result.chain_warnings:
                    print(f"  ⚠️  {warning}")
            
            if result.chain_errors:
                print(f"\nChain Errors ({len(result.chain_errors)}):")
                for error in result.chain_errors:
                    print(f"  ✗ {error}")
            
            print(f"\n{'='*60}")
            print(f"FINAL VERDICT: {'✓ CHAIN INTEGRITY VERIFIED' if result.chain_integrity else '✗ CHAIN INTEGRITY BROKEN'}")
            print(f"{'='*60}")
            
            return 0 if result.chain_integrity else 1
            
        except Exception as e:
            print(f"✗ Replay failed: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    import sys
    sys.exit(main_cli())

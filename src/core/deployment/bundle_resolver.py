"""
Bundle Resolver for Replay/Compare UX v1 (Read-only Audit Diff for Deployment Bundles).

Reads deployment bundles from SSOT paths and provides structured access to bundle contents.
Hybrid BC v1.1 compliant: Read-only, no metrics leakage, deterministic output.

Key features:
- SSOT path resolution using get_outputs_root()
- Manifest validation with hash verification
- Artifact loading with lazy evaluation
- Deterministic ordering for diff comparison
- No writes to outputs/ (except evidence)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime

from pydantic import BaseModel, Field, ValidationError

from ..paths import get_outputs_root
from control.artifacts import canonical_json_bytes, compute_sha256
from contracts.portfolio.gate_summary_schemas import GateSummaryV1

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models for Bundle Resolution
# ============================================================================

class BundleArtifactV1(BaseModel):
    """Resolved artifact from deployment bundle."""
    artifact_id: str
    artifact_type: str
    file_path: Path
    checksum_sha256: str
    content: Optional[Dict[str, Any]] = None  # Lazy-loaded JSON content
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True


class BundleManifestV1(BaseModel):
    """Resolved manifest from deployment bundle."""
    schema_version: str
    deployment_id: str
    job_id: str
    created_at: str
    created_by: str
    artifacts: List[BundleArtifactV1]
    artifact_count: int
    manifest_hash: str
    bundle_hash: str
    deployment_target: str
    deployment_notes: str
    
    # Derived fields
    gate_summary: Optional[GateSummaryV1] = None
    strategy_report: Optional[Dict[str, Any]] = None
    portfolio_config: Optional[Dict[str, Any]] = None
    admission_report: Optional[Dict[str, Any]] = None
    config_snapshot: Optional[Dict[str, Any]] = None
    input_manifest: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True


class BundleResolutionV1(BaseModel):
    """Complete bundle resolution result."""
    bundle_path: Path
    manifest: BundleManifestV1
    resolution_time: str
    is_valid: bool
    validation_errors: List[str] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


# ============================================================================
# Bundle Resolver
# ============================================================================

class BundleResolver:
    """Resolves deployment bundles from SSOT paths for read-only audit diff."""
    
    def __init__(
        self,
        outputs_root: Optional[Path] = None,
    ):
        self.outputs_root = (outputs_root or get_outputs_root()).resolve()
        logger.info(f"BundleResolver initialized with outputs_root: {self.outputs_root}")
    
    def compute_file_sha256(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        import hashlib
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def find_deployment_bundles(self, job_id: str) -> List[Path]:
        """Find all deployment bundles for a job ID."""
        deployments_dir = self.outputs_root / "jobs" / job_id / "deployments"
        if not deployments_dir.exists():
            return []
        
        deployment_dirs = []
        for item in deployments_dir.iterdir():
            if item.is_dir() and item.name.startswith("deployment_"):
                deployment_dirs.append(item)
        
        # Sort by creation time (newest first)
        deployment_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return deployment_dirs
    
    def find_latest_deployment_bundle(self, job_id: str) -> Optional[Path]:
        """Find the most recent deployment bundle for a job ID."""
        deployment_dirs = self.find_deployment_bundles(job_id)
        return deployment_dirs[0] if deployment_dirs else None
    
    def load_manifest(self, deployment_dir: Path) -> Optional[Dict[str, Any]]:
        """Load deployment manifest from directory."""
        manifest_path = deployment_dir / "deployment_manifest_v1.json"
        if not manifest_path.exists():
            logger.error(f"Deployment manifest not found: {manifest_path}")
            return None
        
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
            return manifest_data
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load manifest from {manifest_path}: {e}")
            return None
    
    def verify_manifest_hash(self, manifest_data: Dict[str, Any]) -> bool:
        """Verify manifest hash integrity."""
        try:
            # Create a copy without hash fields
            manifest_dict = manifest_data.copy()
            manifest_hash = manifest_dict.get("manifest_hash", "")
            bundle_hash = manifest_dict.get("bundle_hash", "")
            
            # Remove hash fields for verification
            manifest_dict["manifest_hash"] = ""
            manifest_dict["bundle_hash"] = ""
            
            # Compute hash of canonical JSON
            canonical_bytes = canonical_json_bytes(manifest_dict)
            computed_hash = compute_sha256(canonical_bytes)
            
            return manifest_hash == computed_hash
        except Exception as e:
            logger.error(f"Manifest hash verification failed: {e}")
            return False
    
    def load_artifact_content(self, artifact_path: Path) -> Optional[Dict[str, Any]]:
        """Load artifact content as JSON."""
        if not artifact_path.exists():
            logger.error(f"Artifact not found: {artifact_path}")
            return None
        
        try:
            with open(artifact_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            return content
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load artifact from {artifact_path}: {e}")
            return None
    
    def resolve_artifact(
        self,
        deployment_dir: Path,
        artifact_data: Dict[str, Any],
    ) -> Optional[BundleArtifactV1]:
        """Resolve a single artifact from manifest data."""
        try:
            target_path = artifact_data.get("target_path")
            if not target_path:
                logger.error(f"Artifact missing target_path: {artifact_data}")
                return None
            
            artifact_path = deployment_dir / target_path
            if not artifact_path.exists():
                logger.error(f"Artifact file not found: {artifact_path}")
                return None
            
            # Verify checksum if provided
            expected_checksum = artifact_data.get("checksum_sha256")
            if expected_checksum:
                actual_checksum = self.compute_file_sha256(artifact_path)
                if expected_checksum != actual_checksum:
                    logger.warning(f"Artifact checksum mismatch: {artifact_path}")
            
            return BundleArtifactV1(
                artifact_id=artifact_data.get("artifact_id", ""),
                artifact_type=artifact_data.get("artifact_type", ""),
                file_path=artifact_path,
                checksum_sha256=artifact_data.get("checksum_sha256", ""),
                metadata=artifact_data.get("metadata", {}),
            )
        except Exception as e:
            logger.error(f"Failed to resolve artifact: {e}")
            return None
    
    def resolve_bundle(self, deployment_dir: Path) -> BundleResolutionV1:
        """
        Resolve a deployment bundle for read-only audit diff.
        
        Args:
            deployment_dir: Path to deployment directory
            
        Returns:
            BundleResolutionV1 with resolved bundle contents
        """
        resolution_time = datetime.now().isoformat()
        validation_errors = []
        
        # Load manifest
        manifest_data = self.load_manifest(deployment_dir)
        if not manifest_data:
            return BundleResolutionV1(
                bundle_path=deployment_dir,
                manifest=None,
                resolution_time=resolution_time,
                is_valid=False,
                validation_errors=["Failed to load manifest"],
            )
        
        # Verify manifest hash
        if not self.verify_manifest_hash(manifest_data):
            validation_errors.append("Manifest hash verification failed")
        
        # Resolve artifacts
        artifacts_data = manifest_data.get("artifacts", [])
        resolved_artifacts = []
        
        for artifact_data in artifacts_data:
            artifact = self.resolve_artifact(deployment_dir, artifact_data)
            if artifact:
                resolved_artifacts.append(artifact)
            else:
                validation_errors.append(f"Failed to resolve artifact: {artifact_data.get('artifact_id', 'unknown')}")
        
        # Create manifest model
        try:
            manifest = BundleManifestV1(
                schema_version=manifest_data.get("schema_version", "v1"),
                deployment_id=manifest_data.get("deployment_id", ""),
                job_id=manifest_data.get("job_id", ""),
                created_at=manifest_data.get("created_at", ""),
                created_by=manifest_data.get("created_by", ""),
                artifacts=resolved_artifacts,
                artifact_count=manifest_data.get("artifact_count", 0),
                manifest_hash=manifest_data.get("manifest_hash", ""),
                bundle_hash=manifest_data.get("bundle_hash", ""),
                deployment_target=manifest_data.get("deployment_target", ""),
                deployment_notes=manifest_data.get("deployment_notes", ""),
            )
        except ValidationError as e:
            validation_errors.append(f"Manifest validation failed: {e}")
            return BundleResolutionV1(
                bundle_path=deployment_dir,
                manifest=None,
                resolution_time=resolution_time,
                is_valid=False,
                validation_errors=validation_errors,
            )
        
        # Load key artifacts for easy access
        self._load_key_artifacts(manifest, deployment_dir, resolved_artifacts)
        
        is_valid = len(validation_errors) == 0
        
        return BundleResolutionV1(
            bundle_path=deployment_dir,
            manifest=manifest,
            resolution_time=resolution_time,
            is_valid=is_valid,
            validation_errors=validation_errors,
        )
    
    def _load_key_artifacts(
        self,
        manifest: BundleManifestV1,
        deployment_dir: Path,
        artifacts: List[BundleArtifactV1],
    ) -> None:
        """Load key artifacts for easy access."""
        for artifact in artifacts:
            if artifact.content is None:
                artifact.content = self.load_artifact_content(artifact.file_path)
            
            # Store in appropriate manifest field based on artifact type
            if artifact.artifact_type == "gate_summary_v1" and artifact.content:
                try:
                    manifest.gate_summary = GateSummaryV1(**artifact.content)
                except ValidationError as e:
                    logger.warning(f"Failed to parse gate_summary_v1: {e}")
            
            elif artifact.artifact_type == "strategy_report_v1" and artifact.content:
                manifest.strategy_report = artifact.content
            
            elif artifact.artifact_type == "portfolio_config" and artifact.content:
                manifest.portfolio_config = artifact.content
            
            elif artifact.artifact_type == "admission_report" and artifact.content:
                manifest.admission_report = artifact.content
            
            elif artifact.artifact_type == "config_snapshot" and artifact.content:
                manifest.config_snapshot = artifact.content
            
            elif artifact.artifact_type == "input_manifest" and artifact.content:
                manifest.input_manifest = artifact.content
    
    def compare_bundles(
        self,
        bundle_a_dir: Path,
        bundle_b_dir: Path,
    ) -> Dict[str, Any]:
        """
        Compare two deployment bundles (high-level comparison).
        
        Returns deterministic diff suitable for audit trail.
        No metric leakage (Hybrid BC v1.1 Layer1/Layer2).
        """
        # Resolve both bundles
        resolution_a = self.resolve_bundle(bundle_a_dir)
        resolution_b = self.resolve_bundle(bundle_b_dir)
        
        # Basic comparison
        diff = {
            "compared_at": datetime.now().isoformat(),
            "bundle_a": {
                "path": str(bundle_a_dir),
                "deployment_id": resolution_a.manifest.deployment_id if resolution_a.manifest else None,
                "job_id": resolution_a.manifest.job_id if resolution_a.manifest else None,
                "is_valid": resolution_a.is_valid,
            },
            "bundle_b": {
                "path": str(bundle_b_dir),
                "deployment_id": resolution_b.manifest.deployment_id if resolution_b.manifest else None,
                "job_id": resolution_b.manifest.job_id if resolution_b.manifest else None,
                "is_valid": resolution_b.is_valid,
            },
            "comparison": {
                "same_job": False,
                "same_deployment": False,
                "artifact_count_diff": 0,
                "gate_summary_diff": None,
                "validation_status": {
                    "a": resolution_a.is_valid,
                    "b": resolution_b.is_valid,
                },
            },
        }
        
        # Only compare if both bundles are valid
        if resolution_a.is_valid and resolution_b.is_valid:
            manifest_a = resolution_a.manifest
            manifest_b = resolution_b.manifest
            
            # Check if same job
            same_job = manifest_a.job_id == manifest_b.job_id
            diff["comparison"]["same_job"] = same_job
            
            # Check if same deployment
            same_deployment = manifest_a.deployment_id == manifest_b.deployment_id
            diff["comparison"]["same_deployment"] = same_deployment
            
            # Artifact count difference
            artifact_count_diff = manifest_a.artifact_count - manifest_b.artifact_count
            diff["comparison"]["artifact_count_diff"] = artifact_count_diff
            
            # Gate summary comparison (if available)
            if manifest_a.gate_summary and manifest_b.gate_summary:
                gate_diff = self._compare_gate_summaries(
                    manifest_a.gate_summary,
                    manifest_b.gate_summary,
                )
                diff["comparison"]["gate_summary_diff"] = gate_diff
        
        return diff
    
    def _compare_gate_summaries(
        self,
        gate_a: GateSummaryV1,
        gate_b: GateSummaryV1,
    ) -> Dict[str, Any]:
        """Compare two gate summaries (deterministic, no metrics)."""
        diff = {
            "overall_status_changed": gate_a.overall_status != gate_b.overall_status,
            "overall_status_a": gate_a.overall_status.value,
            "overall_status_b": gate_b.overall_status.value,
            "gate_count_diff": len(gate_a.gates) - len(gate_b.gates),
            "gate_status_changes": [],
        }
        
        # Compare gate statuses by gate_id
        gates_a_by_id = {gate.gate_id: gate for gate in gate_a.gates}
        gates_b_by_id = {gate.gate_id: gate for gate in gate_b.gates}
        
        all_gate_ids = set(gates_a_by_id.keys()) | set(gates_b_by_id.keys())
        
        for gate_id in sorted(all_gate_ids):  # Deterministic ordering
            gate_a = gates_a_by_id.get(gate_id)
            gate_b = gates_b_by_id.get(gate_id)
            
            if gate_a and gate_b:
                if gate_a.status != gate_b.status:
                    diff["gate_status_changes"].append({
                        "gate_id": gate_id,
                        "status_a": gate_a.status.value,
                        "status_b": gate_b.status.value,
                        "gate_name": gate_a.gate_name,
                    })
            elif gate_a and not gate_b:
                diff["gate_status_changes"].append({
                    "gate_id": gate_id,
                    "status_a": gate_a.status.value,
                    "status_b": "MISSING",
                    "gate_name": gate_a.gate_name,
                })
            elif not gate_a and gate_b:
                diff["gate_status_changes"].append({
                    "gate_id": gate_id,
                    "status_a": "MISSING",
                    "status_b": gate_b.status.value,
                    "gate_name": gate_b.gate_name,
                })
        
        return diff


# ============================================================================
# CLI Interface
# ============================================================================

def main_cli():
    """Command-line interface for bundle resolver."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Resolve deployment bundles for read-only audit diff"
    )
    parser.add_argument(
        "command",
        choices=["resolve", "compare", "list"],
        help="Command to execute"
    )
    parser.add_argument(
        "--job-id",
        type=str,
        help="Job identifier (for list command)"
    )
    parser.add_argument(
        "--deployment-dir",
        type=Path,
        help="Path to deployment directory (for resolve/compare commands)"
    )
    parser.add_argument(
        "--deployment-dir-b",
        type=Path,
        help="Second deployment directory (for compare command)"
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=get_outputs_root(),
        help="Root outputs directory"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    resolver = BundleResolver(outputs_root=args.outputs_root)
    
    if args.command == "list":
        if not args.job_id:
            print("Error: --job-id required for list command")
            return 1
        
        deployment_dirs = resolver.find_deployment_bundles(args.job_id)
        
        print(f"Deployment bundles for job {args.job_id}:")
        if not deployment_dirs:
            print("  No deployment bundles found")
            return 0
        
        for i, deployment_dir in enumerate(deployment_dirs):
            manifest_data = resolver.load_manifest(deployment_dir)
            if manifest_data:
                deployment_id = manifest_data.get("deployment_id", "unknown")
                created_at = manifest_data.get("created_at", "unknown")
                artifact_count = manifest_data.get("artifact_count", 0)
                print(f"  {i+1}. {deployment_dir.name}")
                print(f"     Deployment ID: {deployment_id}")
                print(f"     Created: {created_at}")
                print(f"     Artifacts: {artifact_count}")
            else:
                print(f"  {i+1}. {deployment_dir.name} (invalid manifest)")
        
        return 0
    
    elif args.command == "resolve":
        if not args.deployment_dir:
            print("Error: --deployment-dir required for resolve command")
            return 1
        
        if not args.deployment_dir.exists():
            print(f"Error: Deployment directory not found: {args.deployment_dir}")
            return 1
        
        resolution = resolver.resolve_bundle(args.deployment_dir)
        
        print(f"Bundle resolution for {args.deployment_dir}:")
        print(f"  Is valid: {resolution.is_valid}")
        print(f"  Resolution time: {resolution.resolution_time}")
        
        if resolution.manifest:
            manifest = resolution.manifest
            print(f"  Deployment ID: {manifest.deployment_id}")
            print(f"  Job ID: {manifest.job_id}")
            print(f"  Artifact count: {manifest.artifact_count}")
            print(f"  Created at: {manifest.created_at}")
            print(f"  Created by: {manifest.created_by}")
            
            # Show key artifacts
            print(f"  Key artifacts loaded:")
            if manifest.gate_summary:
                print(f"    - Gate Summary: {manifest.gate_summary.overall_status.value}")
            if manifest.strategy_report:
                print(f"    - Strategy Report: Yes")
            if manifest.portfolio_config:
                print(f"    - Portfolio Config: Yes")
            if manifest.admission_report:
                print(f"    - Admission Report: Yes")
        
        if resolution.validation_errors:
            print(f"  Validation errors:")
            for error in resolution.validation_errors:
                print(f"    - {error}")
        
        return 0
    
    elif args.command == "compare":
        if not args.deployment_dir or not args.deployment_dir_b:
            print("Error: --deployment-dir and --deployment-dir-b required for compare command")
            return 1
        
        if not args.deployment_dir.exists():
            print(f"Error: Deployment directory A not found: {args.deployment_dir}")
            return 1
        
        if not args.deployment_dir_b.exists():
            print(f"Error: Deployment directory B not found: {args.deployment_dir_b}")
            return 1
        
        diff = resolver.compare_bundles(args.deployment_dir, args.deployment_dir_b)
        
        print(f"Bundle comparison:")
        print(f"  Compared at: {diff['compared_at']}")
        print(f"  Bundle A: {diff['bundle_a']['path']}")
        print(f"    Deployment ID: {diff['bundle_a']['deployment_id']}")
        print(f"    Job ID: {diff['bundle_a']['job_id']}")
        print(f"    Is valid: {diff['bundle_a']['is_valid']}")
        print(f"  Bundle B: {diff['bundle_b']['path']}")
        print(f"    Deployment ID: {diff['bundle_b']['deployment_id']}")
        print(f"    Job ID: {diff['bundle_b']['job_id']}")
        print(f"    Is valid: {diff['bundle_b']['is_valid']}")
        
        comparison = diff['comparison']
        print(f"  Comparison:")
        print(f"    Same job: {comparison['same_job']}")
        print(f"    Same deployment: {comparison['same_deployment']}")
        print(f"    Artifact count difference: {comparison['artifact_count_diff']}")
        
        if comparison['gate_summary_diff']:
            gate_diff = comparison['gate_summary_diff']
            print(f"    Gate summary changes:")
            print(f"      Overall status changed: {gate_diff['overall_status_changed']}")
            print(f"      Overall status A: {gate_diff['overall_status_a']}")
            print(f"      Overall status B: {gate_diff['overall_status_b']}")
            print(f"      Gate count difference: {gate_diff['gate_count_diff']}")
            
            if gate_diff['gate_status_changes']:
                print(f"      Gate status changes:")
                for change in gate_diff['gate_status_changes']:
                    print(f"        - {change['gate_id']}: {change['status_a']} → {change['status_b']}")
        
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main_cli())
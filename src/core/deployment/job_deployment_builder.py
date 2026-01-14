"""
Job Deployment Bundle Builder v1 (Deterministic Deployment Bundle).

Creates deterministic, replayable deployment bundles for individual job IDs.
Packages canonical job artifacts into a self-contained, hash-verified bundle.

Hybrid BC v1.1 compliant: No portfolio math changes, no backend API changes.
"""

from __future__ import annotations

import json
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from ..paths import get_outputs_root
from control.artifacts import canonical_json_bytes, write_json_atomic, compute_sha256

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class JobDeploymentArtifactV1(BaseModel):
    """A single artifact in the job deployment bundle."""
    artifact_id: str
    source_path: str
    target_path: str
    artifact_type: str  # "strategy_report_v1", "portfolio_config", "admission_report", "gate_summary_v1", "config_snapshot", "input_manifest"
    checksum_sha256: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        frozen = True


class JobDeploymentManifestV1(BaseModel):
    """Job deployment manifest with hash chain for audit trail."""
    schema_version: str = "v1"
    deployment_id: str
    job_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    created_by: str = "job_deployment_builder"
    
    # Artifacts included
    artifacts: List[JobDeploymentArtifactV1] = Field(default_factory=list)
    artifact_count: int = 0
    
    # Hash chain
    manifest_hash: str  # SHA256 of this manifest (excluding this field)
    bundle_hash: str  # SHA256 of the entire bundle directory
    
    # Metadata
    deployment_target: str = "production"
    deployment_notes: str = ""
    
    class Config:
        frozen = True


class JobDeploymentBundleV1(BaseModel):
    """Complete job deployment bundle."""
    deployment_id: str
    manifest: JobDeploymentManifestV1
    bundle_path: str
    bundle_size_bytes: int
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        frozen = True


# ============================================================================
# Job Deployment Bundle Builder
# ============================================================================

class JobDeploymentBuilder:
    """Builds deployment bundles for individual job IDs."""
    
    def __init__(
        self,
        outputs_root: Optional[Path] = None,
    ):
        self.outputs_root = (outputs_root or get_outputs_root()).resolve()
        logger.info(f"JobDeploymentBuilder initialized with outputs_root: {self.outputs_root}")
    
    def compute_file_sha256(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def compute_string_sha256(self, content: str) -> str:
        """Compute SHA256 hash of a string."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def find_job_artifacts(self, job_dir: Path) -> List[Tuple[Path, str]]:
        """Find canonical job artifacts in job directory."""
        artifact_patterns = [
            ("strategy_report_v1.json", "strategy_report_v1"),
            ("portfolio_config.json", "portfolio_config"),
            ("admission_report.json", "admission_report"),
            ("gate_summary_v1.json", "gate_summary_v1"),
            ("config_snapshot.json", "config_snapshot"),
            ("input_manifest.json", "input_manifest"),
            ("winners.json", "winners"),
            ("manifest.json", "job_manifest"),
        ]
        
        artifacts = []
        for filename, artifact_type in artifact_patterns:
            artifact_path = job_dir / filename
            if artifact_path.exists():
                artifacts.append((artifact_path, artifact_type))
        
        return artifacts
    
    def create_deployment_artifact(
        self,
        source_path: Path,
        artifact_type: str,
        artifact_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> JobDeploymentArtifactV1:
        """Create deployment artifact record."""
        if artifact_id is None:
            artifact_id = f"{artifact_type}_{source_path.stem}"
        
        checksum = self.compute_file_sha256(source_path)
        
        # Determine target path (flat structure in bundle)
        target_path = f"artifacts/{source_path.name}"
        
        return JobDeploymentArtifactV1(
            artifact_id=artifact_id,
            source_path=str(source_path),
            target_path=target_path,
            artifact_type=artifact_type,
            checksum_sha256=checksum,
            metadata=metadata or {},
        )
    
    def create_deployment_directory(self, job_id: str, deployment_id: str) -> Path:
        """Create directory for deployment artifacts."""
        deployment_dir = self.outputs_root / "jobs" / job_id / "deployments" / deployment_id
        deployment_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (deployment_dir / "artifacts").mkdir(exist_ok=True)
        
        return deployment_dir
    
    def copy_artifacts_to_deployment(
        self,
        deployment_dir: Path,
        artifacts: List[JobDeploymentArtifactV1],
    ) -> None:
        """Copy artifacts to deployment directory."""
        for artifact in artifacts:
            source_path = Path(artifact.source_path)
            target_path = deployment_dir / artifact.target_path
            
            # Ensure target directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(source_path, target_path)
            logger.debug(f"Copied {source_path} to {target_path}")
    
    def compute_bundle_hash(self, deployment_dir: Path) -> str:
        """Compute SHA256 hash of the entire bundle directory."""
        # Collect all files in deployment directory (excluding manifest itself)
        all_files = []
        for file_path in deployment_dir.rglob("*"):
            if file_path.is_file() and file_path.name != "deployment_manifest_v1.json":
                all_files.append(file_path)
        
        # Sort files by path for deterministic ordering
        all_files.sort(key=lambda x: str(x.relative_to(deployment_dir)))
        
        # Compute combined hash of all file hashes
        combined_hash = hashlib.sha256()
        for file_path in all_files:
            file_hash = self.compute_file_sha256(file_path)
            # Include relative path in hash to prevent collisions
            rel_path = str(file_path.relative_to(deployment_dir))
            combined_hash.update(f"{rel_path}:{file_hash}".encode('utf-8'))
        
        return combined_hash.hexdigest()
    
    def compute_manifest_hash(self, manifest: JobDeploymentManifestV1) -> str:
        """Compute hash of manifest (excluding hash fields)."""
        # Create a copy without hash fields
        manifest_dict = manifest.model_dump()
        manifest_dict["manifest_hash"] = ""
        manifest_dict["bundle_hash"] = ""
        
        # Convert to canonical JSON bytes
        canonical_bytes = canonical_json_bytes(manifest_dict)
        return compute_sha256(canonical_bytes)
    
    def write_deployment_manifest(
        self,
        deployment_dir: Path,
        manifest: JobDeploymentManifestV1,
    ) -> Path:
        """Write deployment manifest to JSON file."""
        manifest_path = deployment_dir / "deployment_manifest_v1.json"
        
        # Convert to dict and write using atomic JSON
        manifest_dict = manifest.model_dump()
        write_json_atomic(manifest_path, manifest_dict)
        
        logger.info(f"Deployment manifest written to {manifest_path}")
        logger.info(f"Manifest hash: {manifest.manifest_hash[:16]}...")
        
        return manifest_path
    
    def build(
        self,
        job_id: str,
        deployment_target: str = "production",
        deployment_notes: str = "",
        include_all_artifacts: bool = True,
    ) -> JobDeploymentBundleV1:
        """
        Build deployment bundle for a single job ID.
        
        Args:
            job_id: Job identifier
            deployment_target: Target environment (production, staging, etc.)
            deployment_notes: Notes about this deployment
            include_all_artifacts: Whether to include all found artifacts (default: True)
            
        Returns:
            JobDeploymentBundleV1 with deployment bundle
            
        Raises:
            FileNotFoundError: If job directory doesn't exist
            ValueError: If no artifacts found
        """
        # Find job directory
        job_dir = self.outputs_root / "jobs" / job_id
        if not job_dir.exists():
            raise FileNotFoundError(f"Job directory not found: {job_dir}")
        
        logger.info(f"Building deployment bundle for job: {job_id}")
        logger.info(f"Job directory: {job_dir}")
        
        # Generate deployment ID (deterministic based on timestamp and job_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        deployment_id = f"deployment_{timestamp}_{job_id[:8]}"
        
        # Find job artifacts
        artifact_paths = self.find_job_artifacts(job_dir)
        if not artifact_paths:
            raise ValueError(f"No canonical artifacts found for job: {job_id}")
        
        logger.info(f"Found {len(artifact_paths)} artifacts for job {job_id}")
        
        # Create deployment artifacts
        deployment_artifacts = []
        for artifact_path, artifact_type in artifact_paths:
            artifact = self.create_deployment_artifact(
                source_path=artifact_path,
                artifact_type=artifact_type,
            )
            deployment_artifacts.append(artifact)
            logger.debug(f"Added artifact: {artifact_type} from {artifact_path}")
        
        # Create deployment directory
        deployment_dir = self.create_deployment_directory(job_id, deployment_id)
        
        # Copy artifacts to deployment directory
        self.copy_artifacts_to_deployment(deployment_dir, deployment_artifacts)
        
        # Compute bundle hash (before creating manifest)
        bundle_hash = self.compute_bundle_hash(deployment_dir)
        
        # Build deployment manifest (without final hashes)
        manifest = JobDeploymentManifestV1(
            schema_version="v1",
            deployment_id=deployment_id,
            job_id=job_id,
            created_at=datetime.now().isoformat(),
            created_by="job_deployment_builder",
            artifacts=deployment_artifacts,
            artifact_count=len(deployment_artifacts),
            manifest_hash="",  # Will be computed
            bundle_hash="",  # Will be computed
            deployment_target=deployment_target,
            deployment_notes=deployment_notes,
        )
        
        # Compute manifest hash
        manifest_hash = self.compute_manifest_hash(manifest)
        
        # Create final manifest with hashes
        final_manifest = JobDeploymentManifestV1(
            **{
                **manifest.model_dump(),
                "manifest_hash": manifest_hash,
                "bundle_hash": bundle_hash,
            }
        )
        
        # Write final manifest
        manifest_path = self.write_deployment_manifest(deployment_dir, final_manifest)
        
        # Compute bundle size
        bundle_size = sum(
            file_path.stat().st_size 
            for file_path in deployment_dir.rglob("*") 
            if file_path.is_file()
        )
        
        # Create summary
        summary = (
            f"Job deployment bundle created successfully.\n"
            f"Deployment ID: {deployment_id}\n"
            f"Job ID: {job_id}\n"
            f"Artifacts included: {len(deployment_artifacts)}\n"
            f"Bundle path: {deployment_dir}\n"
            f"Bundle size: {bundle_size} bytes\n"
            f"Bundle hash: {bundle_hash[:16]}...\n"
            f"Manifest hash: {manifest_hash[:16]}..."
        )
        
        logger.info(summary)
        
        # Show artifact breakdown
        artifact_types = {}
        for artifact in deployment_artifacts:
            artifact_types[artifact.artifact_type] = artifact_types.get(artifact.artifact_type, 0) + 1
        
        logger.info("Artifact breakdown:")
        for artifact_type, count in sorted(artifact_types.items()):
            logger.info(f"  - {artifact_type}: {count}")
        
        return JobDeploymentBundleV1(
            deployment_id=deployment_id,
            manifest=final_manifest,
            bundle_path=str(deployment_dir),
            bundle_size_bytes=bundle_size,
            created_at=datetime.now().isoformat(),
        )
    
    def verify_bundle(self, deployment_dir: Path) -> bool:
        """
        Verify deployment bundle integrity.
        
        Args:
            deployment_dir: Path to deployment directory
            
        Returns:
            True if verification passes, False otherwise
        """
        manifest_path = deployment_dir / "deployment_manifest_v1.json"
        
        if not manifest_path.exists():
            logger.error(f"Deployment manifest not found: {manifest_path}")
            return False
        
        try:
            # Load manifest
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
            
            # Verify manifest hash
            manifest_dict = manifest_data.copy()
            manifest_dict["manifest_hash"] = ""
            manifest_dict["bundle_hash"] = ""
            
            canonical_bytes = canonical_json_bytes(manifest_dict)
            computed_manifest_hash = compute_sha256(canonical_bytes)
            
            if manifest_data.get("manifest_hash") != computed_manifest_hash:
                logger.error(f"Manifest hash mismatch")
                return False
            
            # Verify bundle hash
            computed_bundle_hash = self.compute_bundle_hash(deployment_dir)
            if manifest_data.get("bundle_hash") != computed_bundle_hash:
                logger.error(f"Bundle hash mismatch")
                return False
            
            # Verify artifact checksums
            artifacts = manifest_data.get("artifacts", [])
            for artifact in artifacts:
                artifact_path = deployment_dir / artifact["target_path"]
                if not artifact_path.exists():
                    logger.error(f"Artifact not found: {artifact_path}")
                    return False
                
                computed_checksum = self.compute_file_sha256(artifact_path)
                if artifact["checksum_sha256"] != computed_checksum:
                    logger.error(f"Artifact checksum mismatch: {artifact_path}")
                    return False
            
            logger.info(f"Bundle verification passed: {deployment_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Bundle verification failed: {e}")
            return False


# ============================================================================
# CLI Interface
# ============================================================================

def main_cli():
    """Command-line interface for job deployment builder."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Build deterministic deployment bundles for individual job IDs"
    )
    parser.add_argument(
        "command",
        choices=["build", "verify"],
        help="Command to execute"
    )
    parser.add_argument(
        "--job-id",
        type=str,
        required=True,
        help="Job identifier"
    )
    parser.add_argument(
        "--deployment-target",
        type=str,
        default="production",
        help="Target environment (production, staging, etc.)"
    )
    parser.add_argument(
        "--deployment-notes",
        type=str,
        default="",
        help="Notes about this deployment"
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=get_outputs_root(),
        help="Root outputs directory"
    )
    parser.add_argument(
        "--deployment-dir",
        type=Path,
        help="Path to deployment directory (for verify command)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    builder = JobDeploymentBuilder(outputs_root=args.outputs_root)
    
    if args.command == "build":
        print(f"Building deployment bundle for job: {args.job_id}")
        
        try:
            bundle = builder.build(
                job_id=args.job_id,
                deployment_target=args.deployment_target,
                deployment_notes=args.deployment_notes,
            )
            
            print("✓ Job deployment bundle created successfully")
            print(f"  Deployment ID: {bundle.deployment_id}")
            print(f"  Job ID: {bundle.manifest.job_id}")
            print(f"  Artifacts included: {bundle.manifest.artifact_count}")
            print(f"  Bundle path: {bundle.bundle_path}")
            print(f"  Bundle size: {bundle.bundle_size_bytes} bytes")
            print(f"  Bundle hash: {bundle.manifest.bundle_hash[:16]}...")
            print(f"  Manifest hash: {bundle.manifest.manifest_hash[:16]}...")
            
            # Show artifact breakdown
            artifact_types = {}
            for artifact in bundle.manifest.artifacts:
                artifact_types[artifact.artifact_type] = artifact_types.get(artifact.artifact_type, 0) + 1
            
            print(f"  Artifact breakdown:")
            for artifact_type, count in sorted(artifact_types.items()):
                print(f"    - {artifact_type}: {count}")
            
            return 0
            
        except Exception as e:
            print(f"✗ Deployment bundle creation failed: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    elif args.command == "verify":
        print("Verifying deployment bundle...")
        
        # Determine deployment directory
        if args.deployment_dir:
            deployment_dir = args.deployment_dir
        else:
            # Auto-locate most recent deployment for the job
            deployments_root = args.outputs_root / "jobs" / args.job_id / "deployments"
            if not deployments_root.exists():
                print(f"✗ No deployments found for job: {args.job_id}")
                return 1
            
            # Find most recent deployment
            deployment_dirs = []
            for item in deployments_root.iterdir():
                if item.is_dir() and item.name.startswith("deployment_"):
                    deployment_dirs.append((item.stat().st_mtime, item))
            
            if not deployment_dirs:
                print(f"✗ No deployment directories found for job: {args.job_id}")
                return 1
            
            # Sort by modification time (newest first)
            deployment_dirs.sort(key=lambda x: x[0], reverse=True)
            deployment_dir = deployment_dirs[0][1]
            print(f"Found most recent deployment: {deployment_dir}")
        
        try:
            success = builder.verify_bundle(deployment_dir)
            
            if success:
                print("✓ Deployment bundle verification passed")
                return 0
            else:
                print("✗ Deployment bundle verification failed")
                return 1
                
        except Exception as e:
            print(f"✗ Verification failed: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    import sys
    sys.exit(main_cli())
"""
Deployment Bundle Builder for Route 6 Closed Loop.

Builds deployment packages from portfolio admission results.
Creates deployment_manifest_v1.json with hash chain for audit trail.

Hybrid BC v1.1 compliant: No portfolio math changes, no backend API changes.
"""

from __future__ import annotations

import json
import hashlib
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
import uuid

from pydantic import BaseModel, Field
from ..paths import get_outputs_root

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class DeploymentArtifactV1(BaseModel):
    """A single artifact in the deployment bundle."""
    artifact_id: str
    source_path: str
    target_path: str
    artifact_type: str  # "strategy_report", "portfolio_config", "admission_decision", "correlation_analysis", "budget_alerts", "marginal_contribution", "money_sense_mdd"
    checksum_sha256: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        frozen = True


class DeploymentManifestV1(BaseModel):
    """Deployment manifest with hash chain for audit trail."""
    schema_version: str = "v1"
    deployment_id: str
    portfolio_run_id: str
    portfolio_id: str
    admission_job_id: str
    admission_verdict: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    created_by: str = "deployment_bundle_builder"
    
    # Artifacts included
    artifacts: List[DeploymentArtifactV1] = Field(default_factory=list)
    artifact_count: int = 0
    
    # Hash chain
    previous_deployment_hash: Optional[str] = None  # For chain of custody
    manifest_hash: str  # SHA256 of this manifest (excluding this field)
    bundle_hash: str  # SHA256 of the entire bundle
    
    # Metadata
    deployment_target: str = "production"
    deployment_notes: str = ""
    
    class Config:
        frozen = True


class DeploymentBundleV1(BaseModel):
    """Complete deployment bundle."""
    deployment_id: str
    manifest: DeploymentManifestV1
    bundle_path: str
    bundle_size_bytes: int
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        frozen = True


# ============================================================================
# Deployment Bundle Builder
# ============================================================================

class DeploymentBundleBuilder:
    """Builds deployment bundles from portfolio admission results."""
    
    def __init__(
        self,
        outputs_root: Optional[Path] = None,
        deployments_root: Optional[Path] = None,
    ):
        self.outputs_root = (outputs_root or get_outputs_root()).resolve()
        self.deployments_root = deployments_root or (self.outputs_root / "deployments")
        self.deployments_root.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"DeploymentBundleBuilder initialized with outputs_root: {self.outputs_root}")
        logger.info(f"Deployments root: {self.deployments_root}")
    
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
    
    def find_admission_artifacts(self, admission_job_dir: Path) -> List[Tuple[Path, str]]:
        """Find admission artifacts in job directory."""
        artifact_patterns = [
            ("portfolio_config.json", "portfolio_config"),
            ("admission_decision.json", "admission_decision"),
            ("admission_report.json", "admission_report"),
            ("correlation_analysis.json", "correlation_analysis"),
            ("budget_alerts.json", "budget_alerts"),
            ("marginal_contribution.json", "marginal_contribution"),
            ("money_sense_mdd.json", "money_sense_mdd"),
            ("summary.txt", "summary"),
            ("spec.json", "job_spec"),
            ("result.json", "job_result"),
        ]
        
        artifacts = []
        for filename, artifact_type in artifact_patterns:
            artifact_path = admission_job_dir / filename
            if artifact_path.exists():
                artifacts.append((artifact_path, artifact_type))
        
        return artifacts
    
    def find_strategy_artifacts(self, selected_job_ids: List[str]) -> List[Tuple[Path, str]]:
        """Find strategy artifacts for selected job IDs."""
        artifacts = []
        
        for job_id in selected_job_ids:
            job_dir = self.outputs_root / "jobs" / job_id
            
            # Look for strategy_report_v1.json
            strategy_report_path = job_dir / "strategy_report_v1.json"
            if strategy_report_path.exists():
                artifacts.append((strategy_report_path, f"strategy_report_{job_id}"))
            
            # Look for input_manifest.json
            input_manifest_path = job_dir / "input_manifest.json"
            if input_manifest_path.exists():
                artifacts.append((input_manifest_path, f"input_manifest_{job_id}"))
        
        return artifacts
    
    def create_deployment_artifact(
        self,
        source_path: Path,
        artifact_type: str,
        artifact_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DeploymentArtifactV1:
        """Create deployment artifact record."""
        if artifact_id is None:
            artifact_id = f"{artifact_type}_{source_path.stem}"
        
        checksum = self.compute_sha256(source_path)
        
        # Determine target path
        if artifact_type.startswith("strategy_report_"):
            target_path = f"strategies/{source_path.name}"
        elif artifact_type.startswith("input_manifest_"):
            target_path = f"manifests/{source_path.name}"
        else:
            target_path = f"admission/{source_path.name}"
        
        return DeploymentArtifactV1(
            artifact_id=artifact_id,
            source_path=str(source_path),
            target_path=target_path,
            artifact_type=artifact_type,
            checksum_sha256=checksum,
            metadata=metadata or {},
        )
    
    def get_previous_deployment_hash(self, portfolio_id: str) -> Optional[str]:
        """Get hash of previous deployment for this portfolio (for chain of custody)."""
        # Look for previous deployments in deployments directory
        deployment_dirs = []
        for item in self.deployments_root.iterdir():
            if item.is_dir() and item.name.startswith("deployment_"):
                deployment_dirs.append(item)
        
        # Sort by creation time (newest first)
        deployment_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        for deployment_dir in deployment_dirs:
            manifest_path = deployment_dir / "deployment_manifest_v1.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest_data = json.load(f)
                    
                    if manifest_data.get("portfolio_id") == portfolio_id:
                        return manifest_data.get("manifest_hash")
                except (json.JSONDecodeError, KeyError):
                    continue
        
        return None
    
    def build_deployment_manifest(
        self,
        deployment_id: str,
        portfolio_run_id: str,
        portfolio_id: str,
        admission_job_id: str,
        admission_verdict: str,
        artifacts: List[DeploymentArtifactV1],
        deployment_target: str = "production",
        deployment_notes: str = "",
    ) -> DeploymentManifestV1:
        """Build deployment manifest (without final hash)."""
        # Get previous deployment hash for chain of custody
        previous_deployment_hash = self.get_previous_deployment_hash(portfolio_id)
        
        # Create manifest (temporary, without hash fields)
        manifest = DeploymentManifestV1(
            schema_version="v1",
            deployment_id=deployment_id,
            portfolio_run_id=portfolio_run_id,
            portfolio_id=portfolio_id,
            admission_job_id=admission_job_id,
            admission_verdict=admission_verdict,
            created_at=datetime.now().isoformat(),
            created_by="deployment_bundle_builder",
            artifacts=artifacts,
            artifact_count=len(artifacts),
            previous_deployment_hash=previous_deployment_hash,
            manifest_hash="",  # Will be computed
            bundle_hash="",  # Will be computed
            deployment_target=deployment_target,
            deployment_notes=deployment_notes,
        )
        
        return manifest
    
    def compute_manifest_hash(self, manifest: DeploymentManifestV1) -> str:
        """Compute hash of manifest (excluding hash fields)."""
        # Create a copy without hash fields
        manifest_dict = manifest.model_dump()
        manifest_dict["manifest_hash"] = ""
        manifest_dict["bundle_hash"] = ""
        
        # Convert to JSON with stable ordering
        manifest_json = json.dumps(manifest_dict, sort_keys=True, indent=2)
        return self.compute_string_sha256(manifest_json)
    
    def create_deployment_directory(self, deployment_id: str) -> Path:
        """Create directory for deployment artifacts."""
        deployment_dir = self.deployments_root / deployment_id
        deployment_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (deployment_dir / "admission").mkdir(exist_ok=True)
        (deployment_dir / "strategies").mkdir(exist_ok=True)
        (deployment_dir / "manifests").mkdir(exist_ok=True)
        (deployment_dir / "evidence").mkdir(exist_ok=True)
        
        return deployment_dir
    
    def copy_artifacts_to_deployment(
        self,
        deployment_dir: Path,
        artifacts: List[DeploymentArtifactV1],
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
    
    def create_deployment_bundle_zip(
        self,
        deployment_dir: Path,
        deployment_id: str,
    ) -> Path:
        """Create ZIP bundle of deployment directory."""
        zip_path = self.deployments_root / f"{deployment_id}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in deployment_dir.rglob("*"):
                if file_path.is_file():
                    # Get relative path within deployment directory
                    arcname = file_path.relative_to(deployment_dir)
                    zipf.write(file_path, arcname)
        
        bundle_size = zip_path.stat().st_size
        logger.info(f"Created deployment bundle: {zip_path} ({bundle_size} bytes)")
        
        return zip_path
    
    def compute_bundle_hash(self, bundle_path: Path) -> str:
        """Compute SHA256 hash of the entire bundle."""
        return self.compute_sha256(bundle_path)
    
    def write_deployment_manifest(
        self,
        deployment_dir: Path,
        manifest: DeploymentManifestV1,
    ) -> Path:
        """Write deployment manifest to JSON file."""
        manifest_path = deployment_dir / "deployment_manifest_v1.json"
        manifest_json = manifest.model_dump_json(indent=2, sort_keys=True)
        
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write(manifest_json)
        
        # Compute and write hash
        manifest_hash = self.compute_string_sha256(manifest_json)
        hash_path = deployment_dir / "deployment_manifest_v1.sha256"
        with open(hash_path, 'w', encoding='utf-8') as f:
            f.write(f"{manifest_hash}  deployment_manifest_v1.json\n")
        
        logger.info(f"Deployment manifest written to {manifest_path}")
        logger.info(f"Manifest hash: {manifest_hash}")
        
        return manifest_path
    
    def build(
        self,
        portfolio_run_record_path: Path,
        deployment_target: str = "production",
        deployment_notes: str = "",
        include_strategy_artifacts: bool = True,
    ) -> DeploymentBundleV1:
        """
        Build deployment bundle from portfolio run record.
        
        Args:
            portfolio_run_record_path: Path to portfolio_run_record_v1.json
            deployment_target: Target environment (production, staging, etc.)
            deployment_notes: Notes about this deployment
            include_strategy_artifacts: Whether to include strategy artifacts
        
        Returns:
            DeploymentBundleV1 with deployment bundle
        """
        # Load portfolio run record
        logger.info(f"Loading portfolio run record from {portfolio_run_record_path}")
        with open(portfolio_run_record_path, 'r', encoding='utf-8') as f:
            record_data = json.load(f)
        
        portfolio_run_id = record_data["portfolio_run_id"]
        portfolio_id = record_data["portfolio_id"]
        admission_job_id = record_data.get("submitted_job_id")
        admission_verdict = record_data.get("admission_verdict", "UNKNOWN")
        selected_job_ids = record_data.get("selected_job_ids", [])
        
        if not admission_job_id:
            raise ValueError(f"No submitted job ID in portfolio run record: {portfolio_run_id}")
        
        # Generate deployment ID
        deployment_id = f"deployment_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # Find admission artifacts
        admission_job_dir = self.outputs_root / "jobs" / admission_job_id
        if not admission_job_dir.exists():
            raise FileNotFoundError(f"Admission job directory not found: {admission_job_dir}")
        
        admission_artifact_paths = self.find_admission_artifacts(admission_job_dir)
        logger.info(f"Found {len(admission_artifact_paths)} admission artifacts")
        
        # Create deployment artifacts from admission
        deployment_artifacts = []
        for artifact_path, artifact_type in admission_artifact_paths:
            artifact = self.create_deployment_artifact(
                source_path=artifact_path,
                artifact_type=artifact_type,
            )
            deployment_artifacts.append(artifact)
        
        # Include strategy artifacts if requested
        if include_strategy_artifacts and selected_job_ids:
            strategy_artifact_paths = self.find_strategy_artifacts(selected_job_ids)
            logger.info(f"Found {len(strategy_artifact_paths)} strategy artifacts")
            
            for artifact_path, artifact_type in strategy_artifact_paths:
                # Extract job_id from artifact_type
                job_id = artifact_type.split("_")[-1]
                
                artifact = self.create_deployment_artifact(
                    source_path=artifact_path,
                    artifact_type=artifact_type,
                    metadata={"job_id": job_id},
                )
                deployment_artifacts.append(artifact)
        
        # Create deployment directory
        deployment_dir = self.create_deployment_directory(deployment_id)
        
        # Copy artifacts to deployment directory
        self.copy_artifacts_to_deployment(deployment_dir, deployment_artifacts)
        
        # Build deployment manifest (without final hashes)
        manifest = self.build_deployment_manifest(
            deployment_id=deployment_id,
            portfolio_run_id=portfolio_run_id,
            portfolio_id=portfolio_id,
            admission_job_id=admission_job_id,
            admission_verdict=admission_verdict,
            artifacts=deployment_artifacts,
            deployment_target=deployment_target,
            deployment_notes=deployment_notes,
        )
        
        # Create ZIP bundle
        bundle_path = self.create_deployment_bundle_zip(deployment_dir, deployment_id)
        bundle_size = bundle_path.stat().st_size
        bundle_hash = self.compute_bundle_hash(bundle_path)
        
        # Compute manifest hash
        manifest_hash = self.compute_manifest_hash(manifest)
        
        # Create final manifest with hashes
        final_manifest = DeploymentManifestV1(
            **{
                **manifest.model_dump(),
                "manifest_hash": manifest_hash,
                "bundle_hash": bundle_hash,
            }
        )
        
        # Write final manifest
        manifest_path = self.write_deployment_manifest(deployment_dir, final_manifest)
        
        # Copy portfolio run record to deployment evidence
        evidence_dir = deployment_dir / "evidence"
        shutil.copy2(portfolio_run_record_path, evidence_dir / "portfolio_run_record_v1.json")
        
        # Create summary
        summary = (
            f"Deployment bundle created successfully.\n"
            f"Deployment ID: {deployment_id}\n"
            f"Portfolio Run ID: {portfolio_run_id}\n"
            f"Portfolio ID: {portfolio_id}\n"
            f"Admission verdict: {admission_verdict}\n"
            f"Artifacts included: {len(deployment_artifacts)}\n"
            f"Bundle path: {bundle_path}\n"
            f"Bundle size: {bundle_size} bytes\n"
            f"Bundle hash: {bundle_hash[:16]}...\n"
            f"Manifest hash: {manifest_hash[:16]}..."
        )
        
        logger.info(summary)
        
        return DeploymentBundleV1(
            deployment_id=deployment_id,
            manifest=final_manifest,
            bundle_path=str(bundle_path),
            bundle_size_bytes=bundle_size,
            created_at=datetime.now().isoformat(),
        )


# ============================================================================
# CLI Interface
# ============================================================================

def main_cli():
    """Command-line interface for deployment bundle builder."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Build deployment bundles from portfolio admission results"
    )
    parser.add_argument(
        "command",
        choices=["build", "verify"],
        help="Command to execute"
    )
    parser.add_argument(
        "--portfolio-run-record",
        type=Path,
        required=True,
        help="Path to portfolio_run_record_v1.json"
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
        "--include-strategy-artifacts",
        action="store_true",
        default=True,
        help="Include strategy artifacts (default: True)"
    )
    parser.add_argument(
        "--exclude-strategy-artifacts",
        action="store_true",
        help="Exclude strategy artifacts"
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
    
    # Handle exclude strategy artifacts flag
    include_strategy_artifacts = args.include_strategy_artifacts and not args.exclude_strategy_artifacts
    
    builder = DeploymentBundleBuilder(outputs_root=args.outputs_root)
    
    if args.command == "build":
        print("Building deployment bundle...")
        
        try:
            bundle = builder.build(
                portfolio_run_record_path=args.portfolio_run_record,
                deployment_target=args.deployment_target,
                deployment_notes=args.deployment_notes,
                include_strategy_artifacts=include_strategy_artifacts,
            )
            
            print("✓ Deployment bundle created successfully")
            print(f"  Deployment ID: {bundle.deployment_id}")
            print(f"  Portfolio Run ID: {bundle.manifest.portfolio_run_id}")
            print(f"  Portfolio ID: {bundle.manifest.portfolio_id}")
            print(f"  Admission verdict: {bundle.manifest.admission_verdict}")
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
        
        # For now, just verify the portfolio run record exists
        if not args.portfolio_run_record.exists():
            print(f"✗ Portfolio run record not found: {args.portfolio_run_record}")
            return 1
        
        try:
            with open(args.portfolio_run_record, 'r', encoding='utf-8') as f:
                record_data = json.load(f)
            
            print(f"✓ Portfolio run record is valid JSON")
            print(f"  Portfolio Run ID: {record_data.get('portfolio_run_id', 'N/A')}")
            print(f"  Portfolio ID: {record_data.get('portfolio_id', 'N/A')}")
            print(f"  Admission verdict: {record_data.get('admission_verdict', 'N/A')}")
            
            # Check if admission job directory exists
            admission_job_id = record_data.get("submitted_job_id")
            if admission_job_id:
                admission_job_dir = args.outputs_root / "jobs" / admission_job_id
                if admission_job_dir.exists():
                    print(f"✓ Admission job directory exists: {admission_job_dir}")
                    
                    # Count admission artifacts
                    admission_artifacts = builder.find_admission_artifacts(admission_job_dir)
                    print(f"  Admission artifacts found: {len(admission_artifacts)}")
                else:
                    print(f"⚠️  Admission job directory not found: {admission_job_dir}")
            
            return 0
            
        except Exception as e:
            print(f"✗ Verification failed: {e}")
            return 1


if __name__ == "__main__":
    import sys
    sys.exit(main_cli())

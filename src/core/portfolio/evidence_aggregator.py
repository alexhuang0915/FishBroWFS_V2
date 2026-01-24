"""
Evidence Aggregator for Route 6 Closed Loop.

Builds canonical evidence index from job artifacts in outputs/artifacts/jobs/<job_id>/.
Excludes FAIL jobs by default, includes WARN only when requested.
Skips folders starting with '_' or '.' (including _trash).
No performance metrics in index (Hybrid BC v1.1 compliance).
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Literal, Any
from datetime import datetime
from enum import Enum
import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models (Pydantic v2)
# ============================================================================

class JobLifecycle(str, Enum):
    """Job lifecycle states."""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    PURGED = "PURGED"


class GateStatus(str, Enum):
    """Gate status values."""
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class DataStatus(str, Enum):
    """Data readiness status."""
    READY = "READY"
    MISSING = "MISSING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class GatekeeperMetricsV1(BaseModel):
    """Gatekeeper metrics (total permutations, valid candidates, plateau check)."""
    total_permutations: Optional[int] = None
    valid_candidates: Optional[int] = None
    plateau_check: Optional[str] = None  # "Pass", "Fail", "N/A"


class DataStateV1(BaseModel):
    """Data state for DATA1 and DATA2."""
    data1_status: DataStatus = DataStatus.UNKNOWN
    data2_status: DataStatus = DataStatus.UNKNOWN
    data1_dataset_id: Optional[str] = None
    data2_dataset_id: Optional[str] = None


class JobEvidenceSummaryV1(BaseModel):
    """Evidence summary for a single job."""
    # Core identification
    job_id: str
    lifecycle: JobLifecycle = JobLifecycle.ACTIVE
    
    # Job context
    strategy_id: str = ""
    instrument: str = ""
    timeframe: str = ""
    run_mode: str = ""
    
    # Gate status
    gate_status: GateStatus = GateStatus.UNKNOWN
    gatekeeper_metrics: GatekeeperMetricsV1 = Field(default_factory=lambda: GatekeeperMetricsV1())
    
    # Data state
    data_state: DataStateV1 = Field(default_factory=lambda: DataStateV1())
    
    # Artifacts present
    artifacts_present: List[str] = Field(default_factory=list)
    
    # Timestamps
    created_at: Optional[str] = None
    
    # Metadata
    job_type: Optional[str] = None
    season: Optional[str] = None
    
    class Config:
        """Pydantic configuration."""
        frozen = True  # Immutable after creation
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


class EvidenceIndexV1(BaseModel):
    """Canonical evidence index for Route 6."""
    schema_version: str = "v1"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""
    job_count: int = 0
    jobs: Dict[str, JobEvidenceSummaryV1] = Field(default_factory=dict)
    
    class Config:
        """Pydantic configuration."""
        frozen = True


# ============================================================================
# Evidence Aggregator
# ============================================================================

class EvidenceAggregator:
    """Aggregates evidence from job artifacts into a canonical index."""
    
    def __init__(self, jobs_root: Path):
        self.jobs_root = jobs_root.resolve()
        logger.info(f"EvidenceAggregator initialized with jobs_root: {self.jobs_root}")
    
    def scan_job_directories(self) -> List[Path]:
        """Scan for job directories, skipping special folders."""
        job_dirs = []
        
        if not self.jobs_root.exists():
            logger.warning(f"Jobs root does not exist: {self.jobs_root}")
            return job_dirs
        
        for item in self.jobs_root.iterdir():
            if not item.is_dir():
                continue
            
            # Skip folders starting with '_' or '.'
            if item.name.startswith("_") or item.name.startswith("."):
                logger.debug(f"Skipping special directory: {item.name}")
                continue
            
            # Skip _trash explicitly
            if item.name == "_trash":
                logger.debug(f"Skipping trash directory: {item.name}")
                continue
            
            # Validate job_id format (should be UUID-like)
            # We'll accept any directory name that doesn't contain path traversal
            if "/" in item.name or "\\" in item.name or item.name in (".", ".."):
                logger.warning(f"Skipping suspicious directory name: {item.name}")
                continue
            
            job_dirs.append(item)
        
        logger.info(f"Found {len(job_dirs)} job directories")
        return sorted(job_dirs)  # Deterministic order
    
    def infer_lifecycle(self, job_dir: Path) -> JobLifecycle:
        """Infer job lifecycle state from directory location."""
        # Check if in _trash
        if "_trash" in str(job_dir):
            return JobLifecycle.ARCHIVED
        
        # Check if directory exists
        if not job_dir.exists():
            return JobLifecycle.PURGED
        
        # Default to ACTIVE
        return JobLifecycle.ACTIVE
    
    def read_json_if_exists(self, path: Path) -> Optional[Dict[str, Any]]:
        """Read JSON file if it exists, return None otherwise."""
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read JSON from {path}: {e}")
        return None
    
    def extract_gate_status(self, job_dir: Path) -> GateStatus:
        """Extract gate status from job artifacts."""
        # Try to read strategy_report_v1.json
        report_path = job_dir / "strategy_report_v1.json"
        report = self.read_json_if_exists(report_path)
        
        if report:
            # Check for gatekeeper section
            gatekeeper = report.get("gatekeeper", {})
            gate_status = gatekeeper.get("gate_status")
            
            if gate_status:
                gate_status_upper = gate_status.upper()
                if gate_status_upper in ["PASS", "WARN", "FAIL"]:
                    return GateStatus(gate_status_upper)
        
        return GateStatus.UNKNOWN
    
    def extract_gatekeeper_metrics(self, job_dir: Path) -> GatekeeperMetricsV1:
        """Extract gatekeeper metrics from job artifacts."""
        report_path = job_dir / "strategy_report_v1.json"
        report = self.read_json_if_exists(report_path)
        
        if report:
            gatekeeper = report.get("gatekeeper", {})
            return GatekeeperMetricsV1(
                total_permutations=gatekeeper.get("total_permutations"),
                valid_candidates=gatekeeper.get("valid_candidates"),
                plateau_check=gatekeeper.get("plateau_check"),
            )
        
        return GatekeeperMetricsV1()
    
    def extract_data_state(self, job_dir: Path) -> DataStateV1:
        """Extract data state from job artifacts."""
        # Try to read derived_datasets.json or similar
        datasets_path = job_dir / "derived_datasets.json"
        datasets = self.read_json_if_exists(datasets_path)
        
        if datasets:
            return DataStateV1(
                data1_status=DataStatus(datasets.get("data1_status", "UNKNOWN")),
                data2_status=DataStatus(datasets.get("data2_status", "UNKNOWN")),
                data1_dataset_id=datasets.get("data1_id"),
                data2_dataset_id=datasets.get("data2_id"),
            )
        
        return DataStateV1()
    
    def extract_job_context(self, job_dir: Path) -> Dict[str, str]:
        """Extract job context from artifacts."""
        context = {
            "strategy_id": "",
            "instrument": "",
            "timeframe": "",
            "run_mode": "",
            "season": "",
            "job_type": "",
        }
        
        # Try to read input_manifest.json
        manifest_path = job_dir / "input_manifest.json"
        manifest = self.read_json_if_exists(manifest_path)
        
        if manifest:
            context["strategy_id"] = manifest.get("strategy_id", "")
            context["instrument"] = manifest.get("instrument", "")
            context["timeframe"] = manifest.get("timeframe", "")
            context["run_mode"] = manifest.get("run_mode", "")
            context["season"] = manifest.get("season", "")
            context["job_type"] = manifest.get("job_type", "")
        
        return context
    
    def list_artifacts(self, job_dir: Path) -> List[str]:
        """List artifact files present in job directory."""
        artifacts = []
        
        if not job_dir.exists():
            return artifacts
        
        # Common artifact patterns
        common_patterns = [
            "strategy_report_v1.json",
            "input_manifest.json",
            "derived_datasets.json",
            "gatekeeper.json",
            "*.parquet",
            "*.csv",
            "*.json",
        ]
        
        for pattern in common_patterns:
            for path in job_dir.glob(pattern):
                if path.is_file():
                    artifacts.append(path.name)
        
        return sorted(set(artifacts))  # Deterministic order
    
    def extract_created_at(self, job_dir: Path) -> Optional[str]:
        """Extract creation timestamp from job artifacts."""
        # Try to read metadata.json
        metadata_path = job_dir / "metadata.json"
        metadata = self.read_json_if_exists(metadata_path)
        
        if metadata:
            return metadata.get("created_at")
        
        # Fallback: use directory modification time (not ideal)
        try:
            stat = job_dir.stat()
            return datetime.fromtimestamp(stat.st_mtime).isoformat()
        except OSError:
            return None
    
    def build_job_summary(self, job_dir: Path) -> Optional[JobEvidenceSummaryV1]:
        """Build evidence summary for a single job."""
        job_id = job_dir.name
        
        try:
            # Extract all information
            lifecycle = self.infer_lifecycle(job_dir)
            gate_status = self.extract_gate_status(job_dir)
            gatekeeper_metrics = self.extract_gatekeeper_metrics(job_dir)
            data_state = self.extract_data_state(job_dir)
            context = self.extract_job_context(job_dir)
            artifacts = self.list_artifacts(job_dir)
            created_at = self.extract_created_at(job_dir)
            
            return JobEvidenceSummaryV1(
                job_id=job_id,
                lifecycle=lifecycle,
                strategy_id=context["strategy_id"],
                instrument=context["instrument"],
                timeframe=context["timeframe"],
                run_mode=context["run_mode"],
                gate_status=gate_status,
                gatekeeper_metrics=gatekeeper_metrics,
                data_state=data_state,
                artifacts_present=artifacts,
                created_at=created_at,
                job_type=context["job_type"],
                season=context["season"],
            )
            
        except Exception as e:
            logger.error(f"Failed to build summary for job {job_id}: {e}")
            return None
    
    def build_index(
        self,
        include_warn: bool = False,
        include_archived: bool = False,
        include_fail: bool = False,
    ) -> EvidenceIndexV1:
        """
        Build evidence index from all job directories.
        
        Args:
            include_warn: Include jobs with gate_status = WARN
            include_archived: Include jobs in _trash directory
            include_fail: Include jobs with gate_status = FAIL
        
        Returns:
            EvidenceIndexV1 with filtered jobs
        """
        job_dirs = self.scan_job_directories()
        jobs = {}
        
        for job_dir in job_dirs:
            summary = self.build_job_summary(job_dir)
            if not summary:
                continue
            
            # Apply filters
            if summary.lifecycle == JobLifecycle.ARCHIVED and not include_archived:
                logger.debug(f"Skipping archived job: {summary.job_id}")
                continue
            
            if summary.gate_status == GateStatus.FAIL and not include_fail:
                logger.debug(f"Skipping FAIL job: {summary.job_id}")
                continue
            
            if summary.gate_status == GateStatus.WARN and not include_warn:
                logger.debug(f"Skipping WARN job: {summary.job_id}")
                continue
            
            jobs[summary.job_id] = summary
        
        return EvidenceIndexV1(
            job_count=len(jobs),
            jobs=jobs,
        )
    
    def write_index(self, index: EvidenceIndexV1, output_dir: Path) -> Path:
        """
        Write evidence index to JSON file with SHA256 hash.
        
        Args:
            index: EvidenceIndexV1 to write
            output_dir: Directory to write files to
        
        Returns:
            Path to the JSON file
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Write JSON with stable ordering
        json_path = output_dir / "evidence_index_v1.json"
        json_content = index.model_dump_json(indent=2)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write(json_content)
        
        # Compute SHA256 hash
        sha256_hash = hashlib.sha256(json_content.encode('utf-8')).hexdigest()
        
        # Write hash file
        hash_path = output_dir / "evidence_index_v1.sha256"
        with open(hash_path, 'w', encoding='utf-8') as f:
            f.write(f"{sha256_hash}  evidence_index_v1.json\n")
        
        logger.info(f"Evidence index written to {json_path}")
        logger.info(f"SHA256: {sha256_hash}")
        
        return json_path
    
    def load_index(self, json_path: Path) -> EvidenceIndexV1:
        """Load evidence index from JSON file."""
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Convert jobs dict - handle backward compatibility for gate_summary -> gatekeeper_metrics
        jobs = {}
        for job_id, job_data in data.get("jobs", {}).items():
            # If old data has 'gate_summary' field, rename it to 'gatekeeper_metrics'
            if 'gate_summary' in job_data:
                job_data['gatekeeper_metrics'] = job_data.pop('gate_summary')
            jobs[job_id] = JobEvidenceSummaryV1(**job_data)
        
        data["jobs"] = jobs
        return EvidenceIndexV1(**data)


# ============================================================================
# CLI Interface
# ============================================================================

def main_cli():
    """Command-line interface for evidence aggregator."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Build evidence index from job artifacts"
    )
    parser.add_argument(
        "command",
        choices=["build", "validate"],
        help="Command to execute"
    )
    parser.add_argument(
        "--include-warn",
        action="store_true",
        help="Include jobs with gate_status = WARN"
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived jobs (in _trash)"
    )
    parser.add_argument(
        "--include-fail",
        action="store_true",
        help="Include jobs with gate_status = FAIL"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for evidence index"
    )
    parser.add_argument(
        "--jobs-root",
        type=Path,
        required=True,
        help="Root directory containing job directories"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    aggregator = EvidenceAggregator(jobs_root=args.jobs_root)
    
    if args.command == "build":
        print("Building evidence index...")
        index = aggregator.build_index(
            include_warn=args.include_warn,
            include_archived=args.include_archived,
            include_fail=args.include_fail,
        )
        
        json_path = aggregator.write_index(index, args.output_dir)
        print(f"✓ Evidence index built: {json_path}")
        print(f"  Jobs included: {index.job_count}")
        print(f"  Schema version: {index.schema_version}")
        
        # Show breakdown
        status_counts = {}
        for job in index.jobs.values():
            status_counts[job.gate_status] = status_counts.get(job.gate_status, 0) + 1
        
        print("  Gate status breakdown:")
        for status, count in sorted(status_counts.items()):
            print(f"    {status}: {count}")
    
    elif args.command == "validate":
        json_path = args.output_dir / "evidence_index_v1.json"
        if not json_path.exists():
            print(f"✗ Evidence index not found: {json_path}")
            return 1
        
        print(f"Validating evidence index: {json_path}")
        try:
            index = aggregator.load_index(json_path)
            print(f"✓ Evidence index is valid")
            print(f"  Schema version: {index.schema_version}")
            print(f"  Job count: {index.job_count}")
            print(f"  Created at: {index.created_at}")
            return 0
        except Exception as e:
            print(f"✗ Validation failed: {e}")
            return 1


if __name__ == "__main__":
    import sys
    sys.exit(main_cli())

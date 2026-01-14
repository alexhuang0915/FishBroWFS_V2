"""
Portfolio Orchestrator for Route 6 Closed Loop.

Loads evidence index, selects candidate job IDs, submits portfolio admission jobs,
and writes run records to outputs/portfolio/runs/<portfolio_run_id>/.

Hybrid BC v1.1 compliant: No portfolio math changes, no backend API changes.
"""

from __future__ import annotations

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from core.portfolio.evidence_aggregator import (
    EvidenceIndexV1,
    JobEvidenceSummaryV1,
    GateStatus,
    JobLifecycle,
    EvidenceAggregator,
)
from control.supervisor.models import (
    JobType,
    JobSpec,
    JobStatus,
    normalize_job_type,
)
from control.supervisor.db import SupervisorDB, get_default_db_path
from contracts.supervisor.evidence_schemas import stable_params_hash

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class PortfolioRunConfigV1(BaseModel):
    """Configuration for a portfolio run."""
    portfolio_run_id: str
    portfolio_id: str
    name: str = ""
    description: str = ""
    strategy: str = "top_performers"  # "top_performers", "diversified", "manual"
    max_candidates: int = 5
    min_candidates: int = 2
    correlation_threshold: float = 0.7
    include_warn: bool = False
    include_archived: bool = False
    include_fail: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        frozen = True


class PortfolioRunRecordV1(BaseModel):
    """Record of a portfolio run."""
    portfolio_run_id: str
    portfolio_id: str
    config: PortfolioRunConfigV1
    evidence_index_path: str
    selected_job_ids: List[str]
    submitted_job_id: Optional[str] = None
    submitted_at: Optional[str] = None
    admission_result_path: Optional[str] = None
    admission_verdict: Optional[str] = None
    admission_summary: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    class Config:
        frozen = True


class PortfolioOrchestratorResultV1(BaseModel):
    """Result of portfolio orchestration."""
    portfolio_run_id: str
    portfolio_id: str
    selected_job_ids: List[str]
    submitted_job_id: str
    admission_job_spec: Dict[str, Any]
    run_record_path: str
    summary: str
    
    class Config:
        frozen = True


# ============================================================================
# Candidate Selection Strategies
# ============================================================================

class CandidateSelector:
    """Selects candidate job IDs from evidence index."""
    
    @staticmethod
    def select_top_performers(
        index: EvidenceIndexV1,
        max_candidates: int,
        include_warn: bool = False,
    ) -> List[str]:
        """Select top performers based on gate status and artifacts."""
        candidates = []
        
        for job_id, job_summary in index.jobs.items():
            # Filter by lifecycle
            if job_summary.lifecycle != JobLifecycle.ACTIVE:
                continue
            
            # Filter by gate status
            if job_summary.gate_status == GateStatus.FAIL:
                continue
            if job_summary.gate_status == GateStatus.WARN and not include_warn:
                continue
            
            # Must have strategy_report_v1.json artifact
            if "strategy_report_v1.json" not in job_summary.artifacts_present:
                continue
            
            # Must have data ready
            if (job_summary.data_state.data1_status != "READY" or 
                job_summary.data_state.data2_status != "READY"):
                continue
            
            candidates.append(job_id)
        
        # Sort by some heuristic (for now, just take first N)
        # In a real implementation, we might sort by gate_summary.valid_candidates
        # or other performance metrics
        return candidates[:max_candidates]
    
    @staticmethod
    def select_diversified(
        index: EvidenceIndexV1,
        max_candidates: int,
        include_warn: bool = False,
    ) -> List[str]:
        """Select diversified candidates across instruments/timeframes."""
        # Group by instrument and timeframe
        groups: Dict[str, List[str]] = {}
        
        for job_id, job_summary in index.jobs.items():
            # Filter by lifecycle
            if job_summary.lifecycle != JobLifecycle.ACTIVE:
                continue
            
            # Filter by gate status
            if job_summary.gate_status == GateStatus.FAIL:
                continue
            if job_summary.gate_status == GateStatus.WARN and not include_warn:
                continue
            
            # Must have strategy_report_v1.json artifact
            if "strategy_report_v1.json" not in job_summary.artifacts_present:
                continue
            
            # Must have data ready
            if (job_summary.data_state.data1_status != "READY" or 
                job_summary.data_state.data2_status != "READY"):
                continue
            
            # Create group key
            instrument = job_summary.instrument or "unknown"
            timeframe = job_summary.timeframe or "unknown"
            group_key = f"{instrument}_{timeframe}"
            
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(job_id)
        
        # Take at most 1 from each group
        selected = []
        for group_jobs in groups.values():
            if group_jobs and len(selected) < max_candidates:
                selected.append(group_jobs[0])
        
        return selected
    
    @staticmethod
    def select_manual(
        index: EvidenceIndexV1,
        manual_job_ids: List[str],
        include_warn: bool = False,
    ) -> List[str]:
        """Select manually specified job IDs."""
        selected = []
        
        for job_id in manual_job_ids:
            if job_id not in index.jobs:
                logger.warning(f"Manual job ID not found in index: {job_id}")
                continue
            
            job_summary = index.jobs[job_id]
            
            # Filter by lifecycle
            if job_summary.lifecycle != JobLifecycle.ACTIVE:
                logger.warning(f"Manual job ID not active: {job_id}")
                continue
            
            # Filter by gate status
            if job_summary.gate_status == GateStatus.FAIL:
                logger.warning(f"Manual job ID has FAIL status: {job_id}")
                continue
            if job_summary.gate_status == GateStatus.WARN and not include_warn:
                logger.warning(f"Manual job ID has WARN status (excluded): {job_id}")
                continue
            
            # Must have strategy_report_v1.json artifact
            if "strategy_report_v1.json" not in job_summary.artifacts_present:
                logger.warning(f"Manual job ID missing strategy_report_v1.json: {job_id}")
                continue
            
            # Must have data ready
            if (job_summary.data_state.data1_status != "READY" or 
                job_summary.data_state.data2_status != "READY"):
                logger.warning(f"Manual job ID data not ready: {job_id}")
                continue
            
            selected.append(job_id)
        
        return selected


# ============================================================================
# Portfolio Orchestrator
# ============================================================================

class PortfolioOrchestrator:
    """Orchestrates portfolio admission jobs based on evidence."""
    
    def __init__(
        self,
        outputs_root: Path,
        db_path: Optional[Path] = None,
    ):
        self.outputs_root = outputs_root.resolve()
        self.db_path = db_path or get_default_db_path(outputs_root)
        self.portfolio_runs_dir = self.outputs_root / "portfolio" / "runs"
        self.portfolio_runs_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"PortfolioOrchestrator initialized with outputs_root: {self.outputs_root}")
        logger.info(f"DB path: {self.db_path}")
    
    def load_evidence_index(self, index_path: Path) -> EvidenceIndexV1:
        """Load evidence index from JSON file."""
        from core.portfolio.evidence_aggregator import EvidenceAggregator
        # Create a temporary jobs root (won't be used for loading)
        aggregator = EvidenceAggregator(jobs_root=Path("."))
        return aggregator.load_index(index_path)
    
    def select_candidates(
        self,
        index: EvidenceIndexV1,
        config: PortfolioRunConfigV1,
        manual_job_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Select candidate job IDs based on strategy."""
        selector = CandidateSelector()
        
        if config.strategy == "top_performers":
            return selector.select_top_performers(
                index,
                max_candidates=config.max_candidates,
                include_warn=config.include_warn,
            )
        elif config.strategy == "diversified":
            return selector.select_diversified(
                index,
                max_candidates=config.max_candidates,
                include_warn=config.include_warn,
            )
        elif config.strategy == "manual":
            if not manual_job_ids:
                raise ValueError("Manual strategy requires manual_job_ids")
            return selector.select_manual(
                index,
                manual_job_ids=manual_job_ids,
                include_warn=config.include_warn,
            )
        else:
            raise ValueError(f"Unknown strategy: {config.strategy}")
    
    def build_result_paths(self, selected_job_ids: List[str]) -> List[str]:
        """Build result.json paths for selected job IDs."""
        result_paths = []
        
        for job_id in selected_job_ids:
            # Look for result.json in job artifacts
            job_dir = self.outputs_root / "jobs" / job_id
            result_json_path = job_dir / "result.json"
            
            if result_json_path.exists():
                result_paths.append(str(result_json_path))
            else:
                # Try strategy_report_v1.json as fallback
                strategy_report_path = job_dir / "strategy_report_v1.json"
                if strategy_report_path.exists():
                    result_paths.append(str(strategy_report_path))
                else:
                    logger.warning(f"No result.json or strategy_report_v1.json found for job {job_id}")
        
        return result_paths
    
    def build_portfolio_config(
        self,
        portfolio_id: str,
        selected_job_ids: List[str],
        index: EvidenceIndexV1,
    ) -> Dict[str, Any]:
        """Build portfolio configuration for admission job."""
        # Extract common properties from selected jobs
        instruments = set()
        timeframes = set()
        strategies = set()
        
        for job_id in selected_job_ids:
            if job_id in index.jobs:
                job_summary = index.jobs[job_id]
                if job_summary.instrument:
                    instruments.add(job_summary.instrument)
                if job_summary.timeframe:
                    timeframes.add(job_summary.timeframe)
                if job_summary.strategy_id:
                    strategies.add(job_summary.strategy_id)
        
        return {
            "portfolio_id": portfolio_id,
            "name": f"Portfolio {portfolio_id[:8]}",
            "description": f"Auto-generated portfolio from {len(selected_job_ids)} candidates",
            "currency": "USD",  # Default
            "target_volatility": 0.15,
            "max_drawdown_limit_pct": 20.0,
            "max_drawdown_limit_abs": 10000.0,
            "correlation_threshold": 0.7,
            "correlation_threshold_warn": 0.70,
            "correlation_threshold_reject": 0.85,
            "min_lots_per_strategy": 1,
            "max_lots_per_strategy": 10,
            "total_capital": 100000.0,
            "risk_budget_per_strategy": 0.1,
            "rolling_mdd_3m_limit": 12.0,
            "rolling_mdd_6m_limit": 18.0,
            "rolling_mdd_full_limit": 25.0,
            "noise_buffer_sharpe": 0.05,
            "instruments": list(instruments),
            "timeframes": list(timeframes),
            "strategies": list(strategies),
            "created_at": datetime.now().isoformat(),
        }
    
    def create_portfolio_run_dir(self, portfolio_run_id: str) -> Path:
        """Create directory for portfolio run artifacts."""
        run_dir = self.portfolio_runs_dir / portfolio_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    
    def write_run_record(
        self,
        run_dir: Path,
        record: PortfolioRunRecordV1,
    ) -> Path:
        """Write portfolio run record to JSON file."""
        record_path = run_dir / "portfolio_run_record_v1.json"
        record_json = record.model_dump_json(indent=2)
        
        with open(record_path, 'w', encoding='utf-8') as f:
            f.write(record_json)
        
        # Compute SHA256 hash
        sha256_hash = hashlib.sha256(record_json.encode('utf-8')).hexdigest()
        
        # Write hash file
        hash_path = run_dir / "portfolio_run_record_v1.sha256"
        with open(hash_path, 'w', encoding='utf-8') as f:
            f.write(f"{sha256_hash}  portfolio_run_record_v1.json\n")
        
        logger.info(f"Portfolio run record written to {record_path}")
        logger.info(f"SHA256: {sha256_hash}")
        
        return record_path
    
    def submit_portfolio_admission_job(
        self,
        portfolio_id: str,
        result_paths: List[str],
        portfolio_config: Dict[str, Any],
    ) -> str:
        """Submit a RUN_PORTFOLIO_ADMISSION job to supervisor."""
        # Build job spec
        spec = JobSpec(
            job_type=JobType.RUN_PORTFOLIO_ADMISSION,
            params={
                "portfolio_id": portfolio_id,
                "result_paths": result_paths,
                "portfolio_config": portfolio_config,
            },
            metadata={
                "source": "portfolio_orchestrator",
                "submitted_at": datetime.now().isoformat(),
            },
        )
        
        # Compute params hash for duplicate detection
        params_hash = stable_params_hash(spec.params)
        
        # Submit job
        db = SupervisorDB(self.db_path)
        try:
            job_id = db.submit_job(spec, params_hash=params_hash)
            logger.info(f"Submitted portfolio admission job: {job_id}")
            return job_id
        except Exception as e:
            logger.error(f"Failed to submit portfolio admission job: {e}")
            raise
    
    def orchestrate(
        self,
        evidence_index_path: Path,
        portfolio_id: Optional[str] = None,
        strategy: str = "top_performers",
        max_candidates: int = 5,
        min_candidates: int = 2,
        correlation_threshold: float = 0.7,
        include_warn: bool = False,
        include_archived: bool = False,
        include_fail: bool = False,
        manual_job_ids: Optional[List[str]] = None,
    ) -> PortfolioOrchestratorResultV1:
        """
        Orchestrate a portfolio admission job.
        
        Args:
            evidence_index_path: Path to evidence_index_v1.json
            portfolio_id: Optional portfolio ID (generated if None)
            strategy: Selection strategy
            max_candidates: Maximum number of candidates to select
            min_candidates: Minimum number of candidates required
            correlation_threshold: Correlation threshold for portfolio
            include_warn: Include jobs with WARN gate status
            include_archived: Include archived jobs
            include_fail: Include jobs with FAIL gate status
            manual_job_ids: Manual job IDs for manual strategy
        
        Returns:
            PortfolioOrchestratorResultV1 with orchestration results
        """
        # Generate portfolio ID if not provided
        if portfolio_id is None:
            portfolio_id = f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Generate portfolio run ID
        portfolio_run_id = str(uuid.uuid4())
        
        # Load evidence index
        logger.info(f"Loading evidence index from {evidence_index_path}")
        index = self.load_evidence_index(evidence_index_path)
        logger.info(f"Evidence index loaded with {index.job_count} jobs")
        
        # Create portfolio run config
        config = PortfolioRunConfigV1(
            portfolio_run_id=portfolio_run_id,
            portfolio_id=portfolio_id,
            name=f"Portfolio Run {portfolio_run_id[:8]}",
            description=f"Auto-generated portfolio run from evidence index",
            strategy=strategy,
            max_candidates=max_candidates,
            min_candidates=min_candidates,
            correlation_threshold=correlation_threshold,
            include_warn=include_warn,
            include_archived=include_archived,
            include_fail=include_fail,
        )
        
        # Select candidates
        logger.info(f"Selecting candidates with strategy: {strategy}")
        selected_job_ids = self.select_candidates(
            index=index,
            config=config,
            manual_job_ids=manual_job_ids,
        )
        
        if len(selected_job_ids) < min_candidates:
            raise ValueError(
                f"Insufficient candidates selected: {len(selected_job_ids)} < {min_candidates}. "
                f"Try adjusting filters or strategy."
            )
        
        logger.info(f"Selected {len(selected_job_ids)} candidates: {selected_job_ids}")
        
        # Build result paths
        result_paths = self.build_result_paths(selected_job_ids)
        if len(result_paths) < min_candidates:
            raise ValueError(
                f"Insufficient result files found: {len(result_paths)} < {min_candidates}. "
                f"Some jobs may be missing result.json or strategy_report_v1.json"
            )
        
        logger.info(f"Found {len(result_paths)} result files")
        
        # Build portfolio configuration
        portfolio_config = self.build_portfolio_config(
            portfolio_id=portfolio_id,
            selected_job_ids=selected_job_ids,
            index=index,
        )
        
        # Create portfolio run directory
        run_dir = self.create_portfolio_run_dir(portfolio_run_id)
        
        # Submit portfolio admission job
        logger.info(f"Submitting portfolio admission job for portfolio: {portfolio_id}")
        submitted_job_id = self.submit_portfolio_admission_job(
            portfolio_id=portfolio_id,
            result_paths=result_paths,
            portfolio_config=portfolio_config,
        )
        
        # Build admission job spec for record
        admission_job_spec = {
            "job_type": "RUN_PORTFOLIO_ADMISSION",
            "params": {
                "portfolio_id": portfolio_id,
                "result_paths": result_paths,
                "portfolio_config": portfolio_config,
            },
            "metadata": {
                "source": "portfolio_orchestrator",
                "submitted_at": datetime.now().isoformat(),
            },
        }
        
        # Create portfolio run record
        record = PortfolioRunRecordV1(
            portfolio_run_id=portfolio_run_id,
            portfolio_id=portfolio_id,
            config=config,
            evidence_index_path=str(evidence_index_path),
            selected_job_ids=selected_job_ids,
            submitted_job_id=submitted_job_id,
            submitted_at=datetime.now().isoformat(),
            admission_result_path=None,  # Will be updated when job completes
            admission_verdict=None,
            admission_summary=None,
        )
        
        # Write run record
        record_path = self.write_run_record(run_dir, record)
        
        # Copy evidence index to run directory for provenance
        import shutil
        evidence_index_copy_path = run_dir / "evidence_index_v1.json"
        shutil.copy2(evidence_index_path, evidence_index_copy_path)
        
        # Create summary
        summary = (
            f"Portfolio orchestration completed successfully.\n"
            f"Portfolio Run ID: {portfolio_run_id}\n"
            f"Portfolio ID: {portfolio_id}\n"
            f"Selected candidates: {len(selected_job_ids)}\n"
            f"Submitted job ID: {submitted_job_id}\n"
            f"Run record: {record_path}\n"
            f"Strategy: {strategy}\n"
            f"Correlation threshold: {correlation_threshold}"
        )
        
        logger.info(summary)
        
        return PortfolioOrchestratorResultV1(
            portfolio_run_id=portfolio_run_id,
            portfolio_id=portfolio_id,
            selected_job_ids=selected_job_ids,
            submitted_job_id=submitted_job_id,
            admission_job_spec=admission_job_spec,
            run_record_path=str(record_path),
            summary=summary,
        )
    
    def monitor_admission_job(
        self,
        portfolio_run_id: str,
        timeout_seconds: int = 300,
        poll_interval: int = 5,
    ) -> Optional[PortfolioRunRecordV1]:
        """Monitor portfolio admission job completion."""
        import time
        
        # Load run record
        run_dir = self.portfolio_runs_dir / portfolio_run_id
        record_path = run_dir / "portfolio_run_record_v1.json"
        
        if not record_path.exists():
            raise FileNotFoundError(f"Portfolio run record not found: {record_path}")
        
        with open(record_path, 'r', encoding='utf-8') as f:
            record_data = json.load(f)
        
        record = PortfolioRunRecordV1(**record_data)
        
        if not record.submitted_job_id:
            raise ValueError(f"No submitted job ID in record for portfolio run: {portfolio_run_id}")
        
        # Connect to database
        db = SupervisorDB(self.db_path)
        
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            # Get job status
            job_row = db.get_job_row(record.submitted_job_id)
            
            if not job_row:
                logger.warning(f"Job {record.submitted_job_id} not found in database")
                time.sleep(poll_interval)
                continue
            
            # Check if job is terminal
            if job_row.state in ["SUCCEEDED", "FAILED", "ABORTED", "ORPHANED", "REJECTED"]:
                # Update record with admission result
                job_artifact_dir = self.outputs_root / "jobs" / record.submitted_job_id
                
                # Look for admission artifacts
                admission_decision_path = job_artifact_dir / "admission_decision.json"
                admission_report_path = job_artifact_dir / "admission_report.json"
                
                admission_result_path = None
                admission_verdict = None
                admission_summary = None
                
                if admission_decision_path.exists():
                    admission_result_path = str(admission_decision_path)
                    with open(admission_decision_path, 'r', encoding='utf-8') as f:
                        decision_data = json.load(f)
                        admission_verdict = decision_data.get("verdict")
                        admission_summary = f"Admission verdict: {admission_verdict}"
                elif admission_report_path.exists():
                    admission_result_path = str(admission_report_path)
                    with open(admission_report_path, 'r', encoding='utf-8') as f:
                        report_data = json.load(f)
                        admission_verdict = report_data.get("summary", {}).get("verdict")
                        admission_summary = f"Admission report available"
                
                # Update record
                updated_record = PortfolioRunRecordV1(
                    **{
                        **record.model_dump(),
                        "admission_result_path": admission_result_path,
                        "admission_verdict": admission_verdict,
                        "admission_summary": admission_summary,
                        "updated_at": datetime.now().isoformat(),
                    }
                )
                
                # Write updated record
                self.write_run_record(run_dir, updated_record)
                
                logger.info(f"Portfolio admission job completed with state: {job_row.state}")
                logger.info(f"Admission verdict: {admission_verdict}")
                
                return updated_record
            
            # Job still running
            logger.debug(f"Job {record.submitted_job_id} still running (state: {job_row.state})")
            time.sleep(poll_interval)
        
        logger.warning(f"Timeout waiting for portfolio admission job {record.submitted_job_id}")
        return None


# ============================================================================
# CLI Interface
# ============================================================================

def main_cli():
    """Command-line interface for portfolio orchestrator."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Orchestrate portfolio admission jobs based on evidence"
    )
    parser.add_argument(
        "command",
        choices=["orchestrate", "monitor"],
        help="Command to execute"
    )
    parser.add_argument(
        "--evidence-index",
        type=Path,
        required=True,
        help="Path to evidence index JSON file"
    )
    parser.add_argument(
        "--portfolio-id",
        type=str,
        help="Portfolio ID (generated if not provided)"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["top_performers", "diversified", "manual"],
        default="top_performers",
        help="Candidate selection strategy"
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=5,
        help="Maximum number of candidates to select"
    )
    parser.add_argument(
        "--min-candidates",
        type=int,
        default=2,
        help="Minimum number of candidates required"
    )
    parser.add_argument(
        "--correlation-threshold",
        type=float,
        default=0.7,
        help="Correlation threshold for portfolio"
    )
    parser.add_argument(
        "--include-warn",
        action="store_true",
        help="Include jobs with WARN gate status"
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived jobs"
    )
    parser.add_argument(
        "--include-fail",
        action="store_true",
        help="Include jobs with FAIL gate status"
    )
    parser.add_argument(
        "--manual-job-ids",
        type=str,
        help="Comma-separated list of manual job IDs (for manual strategy)"
    )
    parser.add_argument(
        "--portfolio-run-id",
        type=str,
        help="Portfolio run ID (for monitor command)"
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Timeout in seconds for monitoring (default: 300)"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="Poll interval in seconds for monitoring (default: 5)"
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
    
    orchestrator = PortfolioOrchestrator(outputs_root=args.outputs_root)
    
    if args.command == "orchestrate":
        print("Orchestrating portfolio admission job...")
        
        # Parse manual job IDs if provided
        manual_job_ids = None
        if args.manual_job_ids:
            manual_job_ids = [jid.strip() for jid in args.manual_job_ids.split(",")]
        
        try:
            result = orchestrator.orchestrate(
                evidence_index_path=args.evidence_index,
                portfolio_id=args.portfolio_id,
                strategy=args.strategy,
                max_candidates=args.max_candidates,
                min_candidates=args.min_candidates,
                correlation_threshold=args.correlation_threshold,
                include_warn=args.include_warn,
                include_archived=args.include_archived,
                include_fail=args.include_fail,
                manual_job_ids=manual_job_ids,
            )
            
            print("✓ Portfolio orchestration completed successfully")
            print(f"  Portfolio Run ID: {result.portfolio_run_id}")
            print(f"  Portfolio ID: {result.portfolio_id}")
            print(f"  Selected candidates: {len(result.selected_job_ids)}")
            print(f"  Submitted job ID: {result.submitted_job_id}")
            print(f"  Run record: {result.run_record_path}")
            print(f"  Strategy: {args.strategy}")
            
            # Show selected job IDs
            print(f"  Selected job IDs:")
            for job_id in result.selected_job_ids:
                print(f"    - {job_id}")
            
            return 0
            
        except Exception as e:
            print(f"✗ Portfolio orchestration failed: {e}")
            return 1
    
    elif args.command == "monitor":
        if not args.portfolio_run_id:
            print("✗ --portfolio-run-id is required for monitor command")
            return 1
        
        print(f"Monitoring portfolio admission job for run: {args.portfolio_run_id}")
        
        try:
            record = orchestrator.monitor_admission_job(
                portfolio_run_id=args.portfolio_run_id,
                timeout_seconds=args.timeout_seconds,
                poll_interval=args.poll_interval,
            )
            
            if record:
                print("✓ Portfolio admission job completed")
                print(f"  Portfolio Run ID: {record.portfolio_run_id}")
                print(f"  Submitted job ID: {record.submitted_job_id}")
                print(f"  Admission verdict: {record.admission_verdict}")
                print(f"  Admission summary: {record.admission_summary}")
                print(f"  Result path: {record.admission_result_path}")
                return 0
            else:
                print("✗ Timeout waiting for portfolio admission job")
                return 1
                
        except Exception as e:
            print(f"✗ Monitoring failed: {e}")
            return 1


if __name__ == "__main__":
    import sys
    sys.exit(main_cli())
from __future__ import annotations
import json
import logging
import subprocess
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set
import traceback

from ..job_handler import BaseJobHandler, JobContext
from contracts.supervisor.build_portfolio import BuildPortfolioPayload
from core.paths import get_artifacts_root
from control.artifacts import write_json_atomic
from portfolio.governance.params import load_governance_params
from control.portfolio.evidence_reader import RunEvidenceReader
from control.portfolio.admission import PortfolioAdmissionController
from portfolio.research_bridge import load_research_index, read_decisions_log, build_portfolio_from_research
from portfolio.writer import write_portfolio_artifacts
from contracts.portfolio.admission_schemas import AdmissionDecision

logger = logging.getLogger(__name__)


class BuildPortfolioHandler(BaseJobHandler):
    """BUILD_PORTFOLIO_V2 handler for building portfolio from research via Supervisor."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate BUILD_PORTFOLIO_V2 parameters."""
        try:
            payload = BuildPortfolioPayload(**params)
            payload.validate()
        except Exception as e:
            raise ValueError(f"Invalid build_portfolio payload: {e}")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute BUILD_PORTFOLIO_V2 job."""
        # Validate payload
        payload = BuildPortfolioPayload(**params)
        payload.validate()
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "BUILD_PORTFOLIO_V2",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params
            }
        
        # Determine outputs root
        outputs_root = get_artifacts_root()
        if payload.outputs_root:
            outputs_root = Path(payload.outputs_root)
        
        # Create portfolio output directory (within season directory)
        portfolio_dir = outputs_root / "seasons" / payload.season / "portfolio"
        portfolio_dir.mkdir(parents=True, exist_ok=True)
        
        # Write payload to portfolio directory
        payload_path = portfolio_dir / "payload.json"
        write_json_atomic(payload_path, params)
        
        # Update heartbeat with progress
        context.heartbeat(progress=0.1, phase="validating_inputs")
        
        try:
            # Execute portfolio logic
            result = self._execute_portfolio(payload, context, outputs_root, portfolio_dir)
            
            # Generate manifest
            self._generate_manifest(context.job_id, payload, portfolio_dir, outputs_root)
            
            return {
                "ok": True,
                "job_type": "BUILD_PORTFOLIO_V2",
                "payload": params,
                "portfolio_dir": str(portfolio_dir),
                "manifest_path": str(portfolio_dir / "manifest.json"),
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Failed to execute portfolio build: {e}")
            logger.error(traceback.format_exc())
            
            # Write error to artifacts
            error_path = Path(context.artifacts_dir) / "error.txt"
            error_path.write_text(f"{e}\n\n{traceback.format_exc()}")
            
            raise  # Re-raise to mark job as FAILED
    
    def _get_candidate_run_ids(self, payload: BuildPortfolioPayload, outputs_root: Path) -> Set[str]:
        """Get candidate run IDs from either explicit list or research decisions (KEEP decisions)."""
        # If candidate_run_ids is provided in payload, use it
        if payload.candidate_run_ids is not None:
            return set(payload.candidate_run_ids)
        
        # Otherwise, read from research decisions log
        research_root = outputs_root / "seasons" / payload.season / "research"
        decisions_log_path = research_root / "decisions.log"
        if not decisions_log_path.exists():
            raise RuntimeError(f"Decisions log not found at {decisions_log_path}")
        
        decisions = read_decisions_log(decisions_log_path)
        # Get final decision for each run_id (last entry wins)
        final_decisions = {}
        for entry in decisions:
            run_id = entry.get('run_id', '')
            if not run_id:
                continue
            final_decisions[run_id] = entry.get('decision', '').upper()
        
        # Keep only KEEP decisions
        keep_run_ids = {run_id for run_id, decision in final_decisions.items() if decision == 'KEEP'}
        return keep_run_ids
    
    def _run_admission_gate(self, payload: BuildPortfolioPayload, outputs_root: Path, portfolio_dir: Path) -> AdmissionDecision:
        """Run portfolio admission gate; raise RuntimeError if admission fails.
        
        Returns:
            AdmissionDecision if admitted.
        """
        # Load governance params
        params = load_governance_params()
        
        # Apply overrides if provided
        if payload.governance_params_overrides:
            from portfolio.models.governance_models import GovernanceParams
            # Create a copy of params with overrides applied
            params_dict = params.model_dump()
            params_dict.update(payload.governance_params_overrides)
            params = GovernanceParams(**params_dict)
        
        # Initialize evidence reader
        evidence_reader = RunEvidenceReader()
        
        # Get candidate run IDs
        candidate_run_ids = list(self._get_candidate_run_ids(payload, outputs_root))
        if not candidate_run_ids:
            raise RuntimeError("No candidate run IDs found for admission.")
        
        # Use provided portfolio_id or generate provisional portfolio ID
        import hashlib
        if payload.portfolio_id:
            provisional_portfolio_id = payload.portfolio_id
        else:
            sorted_ids = sorted(candidate_run_ids)
            id_string = ",".join(sorted_ids)
            hash_digest = hashlib.sha256(id_string.encode()).hexdigest()[:12]
            provisional_portfolio_id = f"portfolio_{payload.season}_{hash_digest}"
        
        # Create admission controller
        controller = PortfolioAdmissionController(
            governance_params=params,
            evidence_reader=evidence_reader
        )
        
        # Determine evidence directory: outputs/seasons/{season}/portfolios/{portfolio_id}/admission
        portfolios_root = outputs_root / "seasons" / payload.season / "portfolios"
        portfolios_root.mkdir(parents=True, exist_ok=True)
        
        # Evaluate admission and write evidence
        decision = controller.evaluate_and_write_evidence(
            candidate_run_ids=candidate_run_ids,
            portfolio_id=provisional_portfolio_id,
            evidence_dir=portfolios_root
        )
        
        if not decision.admitted:
            # Summarize top reasons
            reasons = []
            for rejected in decision.rejected_run_ids:
                reason = decision.reasons.get(rejected, "unknown")
                reasons.append(f"{rejected}: {reason}")
            summary = "; ".join(reasons[:5])  # top 5
            raise RuntimeError(f"Portfolio admission failed: {summary}")
        
        # Admission passed; we could optionally filter candidate run IDs, but the portfolio builder
        # will use the same KEEP decisions (which are already filtered by admission).
        # The admission evidence is already written to evidence_dir/admission.
        logger.info(f"Portfolio admission passed with {len(decision.admitted_run_ids)} admitted runs.")
        return decision
    
    def _execute_portfolio(self, payload: BuildPortfolioPayload, context: JobContext, outputs_root: Path, portfolio_dir: Path) -> Dict[str, Any]:
        """Execute the actual portfolio build logic."""
        # Update heartbeat
        context.heartbeat(progress=0.3, phase="preparing_portfolio")
        
        # Run admission gate before building portfolio
        decision = self._run_admission_gate(payload, outputs_root, portfolio_dir)
        
        # Update heartbeat
        context.heartbeat(progress=0.5, phase="building_portfolio")
        
        # Prepare symbols allowlist
        symbols_allowlist = set()
        if payload.allowlist:
            symbols_allowlist = {s.strip() for s in payload.allowlist.split(",") if s.strip()}
        else:
            # Default allowlist (maybe from config)
            symbols_allowlist = {"CME.MNQ", "TWF.MXF"}
        
        # Build portfolio using admitted run IDs
        portfolio_id, portfolio_spec, manifest = build_portfolio_from_research(
            season=payload.season,
            outputs_root=outputs_root,
            symbols_allowlist=symbols_allowlist,
            run_ids_allowlist=set(decision.admitted_run_ids)
        )
        
        # Write portfolio artifacts
        out_dir = write_portfolio_artifacts(
            outputs_root=outputs_root,
            season=payload.season,
            spec=portfolio_spec,
            manifest=manifest
        )
        
        # Update heartbeat
        context.heartbeat(progress=0.9, phase="finalizing")
        
        # Capture stdout/stderr for compatibility (empty)
        stdout_path = Path(context.artifacts_dir) / "portfolio_stdout.txt"
        stderr_path = Path(context.artifacts_dir) / "portfolio_stderr.txt"
        stdout_path.write_text(f"Portfolio built via direct call. Portfolio ID: {portfolio_id}\n")
        stderr_path.write_text("")
        
        # Parse output to extract results
        result = self._parse_portfolio_output(stdout_path, portfolio_dir)
        # Admission evidence directory
        admission_evidence_dir = outputs_root / "seasons" / payload.season / "portfolios" / decision.portfolio_id / "admission"
        result.update({
            "portfolio_id": portfolio_id,
            "portfolio_spec_path": str(out_dir / "portfolio_spec.json"),
            "portfolio_manifest_path": str(out_dir / "portfolio_manifest.json"),
            "admitted_run_ids": decision.admitted_run_ids,
            "admission_evidence_dir": str(admission_evidence_dir)
        })
        
        return {
            "ok": True,
            "returncode": 0,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "result": result
        }
    
    def _parse_portfolio_output(self, stdout_path: Path, portfolio_dir: Path) -> Dict[str, Any]:
        """Parse portfolio output to extract results."""
        if not stdout_path.exists():
            return {"note": "No stdout captured"}
        
        content = stdout_path.read_text()
        
        # Look for generated files
        result = {
            "output_files": [],
            "portfolio_dir": str(portfolio_dir),
            "note": "Portfolio build completed"
        }
        
        # Check for generated files in portfolio directory
        for file in portfolio_dir.glob("**/*"):
            if file.is_file():
                result["output_files"].append(str(file.relative_to(portfolio_dir)))
        
        return result
    
    def _generate_manifest(self, job_id: str, payload: BuildPortfolioPayload, portfolio_dir: Path, outputs_root: Path) -> None:
        """Generate manifest.json for the portfolio run."""
        import git
        from datetime import datetime, UTC
        
        # Get git commit hash
        git_commit = "unknown"
        try:
            repo = git.Repo(search_parent_directories=True)
            git_commit = repo.head.commit.hexsha[:8]
        except Exception:
            pass
        
        # Compute input fingerprint
        input_fingerprint = payload.compute_input_fingerprint()
        
        manifest = {
            "job_id": job_id,
            "job_type": "build_portfolio_v2",
            "created_at": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
            "input_fingerprint": {
                "season": payload.season,
                "outputs_root": str(outputs_root),
                "allowlist": payload.allowlist,
                "params_hash": input_fingerprint
            },
            "code_fingerprint": {
                "git_commit": git_commit
            },
            "portfolio_directory": str(portfolio_dir),
            "manifest_version": "1.0"
        }
        
        manifest_path = portfolio_dir / "manifest.json"
        write_json_atomic(manifest_path, manifest)
        
        logger.info(f"Generated manifest at {manifest_path}")


# Register handler
build_portfolio_handler = BuildPortfolioHandler()
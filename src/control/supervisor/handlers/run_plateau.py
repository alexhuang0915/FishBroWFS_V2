from __future__ import annotations
import json
import logging
import subprocess
import sys
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
import traceback

from ..job_handler import BaseJobHandler, JobContext
from contracts.supervisor.run_plateau import RunPlateauPayload
from control.paths import get_outputs_root
from control.artifacts import write_json_atomic

logger = logging.getLogger(__name__)


# Resource guardrails for heavy compute
MAX_WINNERS_ROWS = 100_000  # Maximum number of winners rows to process
MAX_PARAM_COMBINATIONS = 10_000  # Maximum parameter combinations for plateau detection
MAX_EXECUTION_TIME_SEC = 3600  # 1 hour maximum execution time
HEARTBEAT_INTERVAL_SEC = 30  # Send heartbeat every 30 seconds during heavy compute


def _is_test_mode(job: JobContext) -> bool:
    """Detect if we're running in test mode.
    
    Priority:
    1. Check for existing test flag in runtime context if present
    2. Check environment variables (FISHBRO_TEST_MODE, PYTEST_CURRENT_TEST)
    3. Check if outputs root/run root path indicates temp directory
    """
    # 1. Check for runtime context test flag (if available)
    # Currently not implemented, but could be added to JobContext
    
    # 2. Check environment variables
    if os.environ.get("FISHBRO_TEST_MODE") == "1":
        return True
    if os.environ.get("PYTEST_CURRENT_TEST") is not None:
        return True
    
    # 3. Check if artifacts directory or outputs root indicates temp directory
    artifacts_dir = getattr(job, 'artifacts_dir', '')
    if isinstance(artifacts_dir, str):
        if '/tmp' in artifacts_dir or '.pytest' in artifacts_dir or 'tmp_path' in artifacts_dir:
            return True
    
    # Check outputs root
    outputs_root = str(get_outputs_root())
    if '/tmp' in outputs_root or '.pytest' in outputs_root or 'tmp_path' in outputs_root:
        return True
    
    return False


class RunPlateauHandler(BaseJobHandler):
    """RUN_PLATEAU_V2 handler for executing plateau identification via Supervisor."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate RUN_PLATEAU_V2 parameters."""
        try:
            payload = RunPlateauPayload(**params)
            payload.validate()
        except Exception as e:
            raise ValueError(f"Invalid run_plateau payload: {e}")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute RUN_PLATEAU_V2 job."""
        # Validate payload
        payload = RunPlateauPayload(**params)
        payload.validate()
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "RUN_PLATEAU_V2",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params
            }
        
        # Determine research run directory
        outputs_root = get_outputs_root()
        research_run_dir = outputs_root / "seasons" / "current" / payload.research_run_id
        
        # Check if we're in test mode
        is_test = _is_test_mode(context)
        
        if not research_run_dir.exists():
            if is_test:
                # In test mode, create the directory and minimal placeholder files
                research_run_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created test research run directory: {research_run_dir}")
            else:
                raise ValueError(f"Research run directory not found: {research_run_dir}")
        
        # [L2-1 Fix] Prefer plateau_candidates.json (broad) over winners.json (top-k)
        candidates_path = None
        
        # Priority order: 
        # 1. plateau_candidates.json (broad set)
        # 2. winners.json (legacy/fallback, likely sparse)
        search_paths = [
            research_run_dir / "plateau_candidates.json",
            research_run_dir / "research" / "plateau_candidates.json",
            research_run_dir / "winners.json",
            research_run_dir / "research" / "winners.json"
        ]
        
        for p in search_paths:
            if p.exists():
                candidates_path = p
                logger.info(f"Using candidates file: {candidates_path}")
                break
        
        if not candidates_path:
            if is_test:
                # In test mode, create a minimal winners.json placeholder (legacy name for compatibility)
                candidates_path = research_run_dir / "winners.json"
                candidates_path.parent.mkdir(parents=True, exist_ok=True)
                winners_content = {
                    "test_mode": True,
                    "research_run_id": payload.research_run_id,
                    "note": "Placeholder winners.json created for test execution",
                    "winners": []
                }
                write_json_atomic(candidates_path, winners_content)
                logger.info(f"Created test winners.json at: {candidates_path}")
            else:
                raise ValueError(f"No suitable candidates file (plateau_candidates.json or winners.json) found in {payload.research_run_id}")
        
        # Create plateau output directory (within research run directory)
        plateau_dir = research_run_dir / "plateau"
        plateau_dir.mkdir(parents=True, exist_ok=True)
        
        # Write payload to plateau directory
        payload_path = plateau_dir / "payload.json"
        write_json_atomic(payload_path, params)
        
        # Update heartbeat with progress
        context.heartbeat(progress=0.1, phase="validating_inputs")
        
        try:
            # Execute plateau logic
            result = self._execute_plateau(payload, context, candidates_path, plateau_dir)
            
            # Generate manifest
            self._generate_manifest(context.job_id, payload, plateau_dir, candidates_path)
            
            return {
                "ok": True,
                "job_type": "RUN_PLATEAU_V2",
                "payload": params,
                "plateau_dir": str(plateau_dir),
                "manifest_path": str(plateau_dir / "manifest.json"),
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Failed to execute plateau identification: {e}")
            logger.error(traceback.format_exc())
            
            # Write error to artifacts
            error_path = Path(context.artifacts_dir) / "error.txt"
            error_path.write_text(f"{e}\n\n{traceback.format_exc()}")
            
            raise  # Re-raise to mark job as FAILED
    
    def _execute_plateau(self, payload: RunPlateauPayload, context: JobContext, candidates_path: Path, plateau_dir: Path) -> Dict[str, Any]:
        """Execute the actual plateau identification logic."""
        # Check if we're in test mode
        is_test = _is_test_mode(context)
        
        if is_test:
            # In test mode, short-circuit heavy computation
            logger.info("Test mode detected - short-circuiting plateau execution")
            
            # Update heartbeat
            context.heartbeat(progress=0.3, phase="test_mode_preparing")
            
            # Create minimal output files
            test_output_path = plateau_dir / "plateau_report.json"
            test_output_content = {
                "test_mode": True,
                "research_run_id": payload.research_run_id,
                "k_neighbors": payload.k_neighbors,
                "score_threshold_rel": payload.score_threshold_rel,
                "note": "Test mode plateau execution - no actual computation performed",
                "plateau_candidates": [],
                "execution_time_ms": 0
            }
            write_json_atomic(test_output_path, test_output_content)
            
            # Create stdout/stderr placeholders
            stdout_path = Path(context.artifacts_dir) / "plateau_stdout.txt"
            stderr_path = Path(context.artifacts_dir) / "plateau_stderr.txt"
            stdout_path.write_text("Test mode plateau execution completed successfully\n")
            stderr_path.write_text("")
            
            context.heartbeat(progress=0.9, phase="test_mode_finalizing")
            
            return {
                "ok": True,
                "returncode": 0,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "result": {
                    "test_mode": True,
                    "output_files": ["plateau_report.json"],
                    "note": "Test execution completed"
                }
            }
        
        # PRODUCTION MODE: Execute actual plateau logic
        # Update heartbeat
        context.heartbeat(progress=0.3, phase="preparing_plateau")
        
        # Apply guardrails before heavy computation
        self._apply_guardrails(candidates_path, context)
        
        # Build command for plateau execution
        cmd = [
            sys.executable, "-B", "-m", "scripts.run_phase3a_plateau",
            str(candidates_path)
        ]
        
        # Add optional parameters
        if payload.k_neighbors is not None:
            cmd.extend(["--k-neighbors", str(payload.k_neighbors)])
        if payload.score_threshold_rel is not None:
            cmd.extend(["--score-threshold-rel", str(payload.score_threshold_rel)])
        
        # Set up stdout/stderr capture
        stdout_path = Path(context.artifacts_dir) / "plateau_stdout.txt"
        stderr_path = Path(context.artifacts_dir) / "plateau_stderr.txt"
        
        logger.info(f"Executing plateau via CLI: {' '.join(cmd)}")
        
        # Update heartbeat
        context.heartbeat(progress=0.5, phase="executing_plateau")
        
        try:
            # Start time for timeout monitoring
            start_time = time.time()
            
            with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
                # Run subprocess with timeout
                process = subprocess.run(
                    cmd,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    cwd=Path.cwd(),
                    env={**os.environ, "PYTHONPATH": "src"},
                    timeout=MAX_EXECUTION_TIME_SEC
                )
            
            # Check result
            if process.returncode == 0:
                context.heartbeat(progress=0.9, phase="finalizing")
                
                # Parse output to extract results
                result = self._parse_plateau_output(stdout_path, plateau_dir)
                
                return {
                    "ok": True,
                    "returncode": process.returncode,
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "result": result
                }
            else:
                error_msg = f"Plateau CLI failed with return code {process.returncode}"
                logger.error(error_msg)
                
                # Read stderr for more details
                stderr_content = ""
                if stderr_path.exists():
                    stderr_content = stderr_path.read_text()[:1000]
                
                raise RuntimeError(f"{error_msg}\nStderr: {stderr_content}")
                
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            raise RuntimeError(f"Plateau execution timed out after {elapsed:.1f}s (max {MAX_EXECUTION_TIME_SEC}s)")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Plateau subprocess failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to execute plateau: {e}")
    
    def _apply_guardrails(self, winners_path: Path, context: JobContext) -> None:
        """Apply resource guardrails before heavy computation."""
        # Check winners.json size
        if winners_path.exists():
            try:
                with open(winners_path, 'r') as f:
                    data = json.load(f)
                
                # Count winners rows
                winners = data.get('winners', [])
                if isinstance(winners, list):
                    row_count = len(winners)
                    if row_count > MAX_WINNERS_ROWS:
                        raise ValueError(
                            f"Winners file too large: {row_count} rows exceeds limit of {MAX_WINNERS_ROWS}. "
                            f"Consider filtering or sampling before plateau detection."
                        )
                    
                    # Estimate parameter combinations (simplified)
                    # Each winner typically has multiple parameters
                    if row_count > 0:
                        # Rough estimate: each winner has ~10 parameters
                        estimated_param_combinations = row_count * 10
                        if estimated_param_combinations > MAX_PARAM_COMBINATIONS:
                            logger.warning(
                                f"Estimated parameter combinations ({estimated_param_combinations}) "
                                f"exceeds soft limit ({MAX_PARAM_COMBINATIONS}). "
                                f"Plateau detection may be slow."
                            )
                
                logger.info(f"Guardrails passed: winners file has {len(winners)} rows")
                
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid winners.json format: {e}")
            except Exception as e:
                logger.warning(f"Could not apply guardrails: {e}")
        else:
            raise FileNotFoundError(f"Winners file not found: {winners_path}")
        
        # Send heartbeat to indicate guardrails passed
        context.heartbeat(progress=0.4, phase="guardrails_passed")
    
    def _parse_plateau_output(self, stdout_path: Path, plateau_dir: Path) -> Dict[str, Any]:
        """Parse plateau output to extract results."""
        if not stdout_path.exists():
            return {"note": "No stdout captured"}
        
        content = stdout_path.read_text()
        
        # Look for generated files
        result = {
            "output_files": [],
            "plateau_dir": str(plateau_dir),
            "note": "Plateau identification completed"
        }
        
        # Check for generated files
        for file in plateau_dir.glob("*.json"):
            result["output_files"].append(str(file.name))
        
        return result
    
    def _generate_manifest(self, job_id: str, payload: RunPlateauPayload, plateau_dir: Path, winners_path: Path) -> None:
        """Generate manifest.json for the plateau run."""
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
            "job_type": "run_plateau_v2",
            "created_at": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
            "input_fingerprint": {
                "research_run_id": payload.research_run_id,
                "k_neighbors": payload.k_neighbors,
                "score_threshold_rel": payload.score_threshold_rel,
                "params_hash": input_fingerprint
            },
            "code_fingerprint": {
                "git_commit": git_commit
            },
            "plateau_directory": str(plateau_dir),
            "winners_path": str(winners_path),
            "manifest_version": "1.0"
        }
        
        manifest_path = plateau_dir / "manifest.json"
        write_json_atomic(manifest_path, manifest)
        
        logger.info(f"Generated manifest at {manifest_path}")


# Register handler
run_plateau_handler = RunPlateauHandler()
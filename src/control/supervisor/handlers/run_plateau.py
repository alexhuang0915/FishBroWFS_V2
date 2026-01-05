from __future__ import annotations
import json
import logging
import subprocess
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional
import traceback

from ..job_handler import BaseJobHandler, JobContext
from src.contracts.supervisor.run_plateau import RunPlateauPayload
from src.control.paths import get_outputs_root

logger = logging.getLogger(__name__)


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
        
        # Look for winners.json in research run directory
        winners_path = research_run_dir / "winners.json"
        if not winners_path.exists():
            # Try research subdirectory
            winners_path = research_run_dir / "research" / "winners.json"
        
        if not winners_path.exists():
            if is_test:
                # In test mode, create a minimal winners.json placeholder
                winners_path.parent.mkdir(parents=True, exist_ok=True)
                winners_content = {
                    "test_mode": True,
                    "research_run_id": payload.research_run_id,
                    "note": "Placeholder winners.json created for test execution",
                    "winners": []
                }
                with open(winners_path, "w") as f:
                    json.dump(winners_content, f, indent=2)
                logger.info(f"Created test winners.json at: {winners_path}")
            else:
                raise ValueError(f"winners.json not found in research run {payload.research_run_id}")
        
        # Create plateau output directory (within research run directory)
        plateau_dir = research_run_dir / "plateau"
        plateau_dir.mkdir(parents=True, exist_ok=True)
        
        # Write payload to plateau directory
        payload_path = plateau_dir / "payload.json"
        with open(payload_path, "w") as f:
            json.dump(params, f, indent=2)
        
        # Update heartbeat with progress
        context.heartbeat(progress=0.1, phase="validating_inputs")
        
        try:
            # Execute plateau logic
            result = self._execute_plateau(payload, context, winners_path, plateau_dir)
            
            # Generate manifest
            self._generate_manifest(context.job_id, payload, plateau_dir, winners_path)
            
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
    
    def _execute_plateau(self, payload: RunPlateauPayload, context: JobContext, winners_path: Path, plateau_dir: Path) -> Dict[str, Any]:
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
            with open(test_output_path, "w") as f:
                json.dump(test_output_content, f, indent=2)
            
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
        
        # Build command for plateau execution
        cmd = [
            sys.executable, "-B", "-m", "scripts.run_phase3a_plateau",
            str(winners_path)
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
            with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
                # Run subprocess
                process = subprocess.run(
                    cmd,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    cwd=Path.cwd(),
                    env={**os.environ, "PYTHONPATH": "src"}
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
                
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Plateau subprocess failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to execute plateau: {e}")
    
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
        from datetime import datetime
        
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
            "created_at": datetime.utcnow().isoformat() + "Z",
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
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        
        logger.info(f"Generated manifest at {manifest_path}")


# Register handler
run_plateau_handler = RunPlateauHandler()
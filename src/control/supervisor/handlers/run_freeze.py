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
from src.contracts.supervisor.run_freeze import RunFreezePayload
from src.control.paths import get_outputs_root

logger = logging.getLogger(__name__)


class RunFreezeHandler(BaseJobHandler):
    """RUN_FREEZE_V2 handler for executing season freeze via Supervisor."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate RUN_FREEZE_V2 parameters."""
        try:
            payload = RunFreezePayload(**params)
            payload.validate()
        except Exception as e:
            raise ValueError(f"Invalid run_freeze payload: {e}")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute RUN_FREEZE_V2 job."""
        # Validate payload
        payload = RunFreezePayload(**params)
        payload.validate()
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "RUN_FREEZE_V2",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params
            }
        
        # Create freeze output directory (within season directory)
        outputs_root = get_outputs_root()
        season_dir = outputs_root / "seasons" / payload.season
        freeze_dir = season_dir / "freeze"
        freeze_dir.mkdir(parents=True, exist_ok=True)
        
        # Write payload to freeze directory
        payload_path = freeze_dir / "payload.json"
        with open(payload_path, "w") as f:
            json.dump(params, f, indent=2)
        
        # Update heartbeat with progress
        context.heartbeat(progress=0.1, phase="validating_inputs")
        
        try:
            # Execute freeze logic
            result = self._execute_freeze(payload, context, freeze_dir)
            
            # Generate manifest
            self._generate_manifest(context.job_id, payload, freeze_dir)
            
            return {
                "ok": True,
                "job_type": "RUN_FREEZE_V2",
                "payload": params,
                "freeze_dir": str(freeze_dir),
                "manifest_path": str(freeze_dir / "manifest.json"),
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Failed to execute season freeze: {e}")
            logger.error(traceback.format_exc())
            
            # Write error to artifacts
            error_path = Path(context.artifacts_dir) / "error.txt"
            error_path.write_text(f"{e}\n\n{traceback.format_exc()}")
            
            raise  # Re-raise to mark job as FAILED
    
    def _execute_freeze(self, payload: RunFreezePayload, context: JobContext, freeze_dir: Path) -> Dict[str, Any]:
        """Execute the actual freeze logic."""
        # Update heartbeat
        context.heartbeat(progress=0.3, phase="preparing_freeze")
        
        # Build command for freeze execution
        cmd = [
            sys.executable, "-B", "-m", "scripts.freeze_season_with_manifest",
            "--season", payload.season
        ]
        
        # Add optional parameters
        if payload.force:
            cmd.append("--force")
        if payload.engine_version:
            cmd.extend(["--engine-version", payload.engine_version])
        if payload.notes:
            cmd.extend(["--notes", payload.notes])
        
        # Set up stdout/stderr capture
        stdout_path = Path(context.artifacts_dir) / "freeze_stdout.txt"
        stderr_path = Path(context.artifacts_dir) / "freeze_stderr.txt"
        
        logger.info(f"Executing freeze via CLI: {' '.join(cmd)}")
        
        # Update heartbeat
        context.heartbeat(progress=0.5, phase="executing_freeze")
        
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
                result = self._parse_freeze_output(stdout_path, freeze_dir)
                
                return {
                    "ok": True,
                    "returncode": process.returncode,
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "result": result
                }
            else:
                error_msg = f"Freeze CLI failed with return code {process.returncode}"
                logger.error(error_msg)
                
                # Read stderr for more details
                stderr_content = ""
                if stderr_path.exists():
                    stderr_content = stderr_path.read_text()[:1000]
                
                raise RuntimeError(f"{error_msg}\nStderr: {stderr_content}")
                
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Freeze subprocess failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to execute freeze: {e}")
    
    def _parse_freeze_output(self, stdout_path: Path, freeze_dir: Path) -> Dict[str, Any]:
        """Parse freeze output to extract results."""
        if not stdout_path.exists():
            return {"note": "No stdout captured"}
        
        content = stdout_path.read_text()
        
        # Look for generated files
        result = {
            "output_files": [],
            "freeze_dir": str(freeze_dir),
            "note": "Season freeze completed"
        }
        
        # Check for generated files in season directory (manifest etc.)
        season_dir = freeze_dir.parent
        for file in season_dir.glob("**/*.json"):
            if file.is_relative_to(freeze_dir):
                result["output_files"].append(str(file.relative_to(freeze_dir)))
        
        return result
    
    def _generate_manifest(self, job_id: str, payload: RunFreezePayload, freeze_dir: Path) -> None:
        """Generate manifest.json for the freeze run."""
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
            "job_type": "run_freeze_v2",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "input_fingerprint": {
                "season": payload.season,
                "force": payload.force,
                "engine_version": payload.engine_version,
                "notes": payload.notes,
                "params_hash": input_fingerprint
            },
            "code_fingerprint": {
                "git_commit": git_commit
            },
            "freeze_directory": str(freeze_dir),
            "manifest_version": "1.0"
        }
        
        manifest_path = freeze_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        
        logger.info(f"Generated manifest at {manifest_path}")


# Register handler
run_freeze_handler = RunFreezeHandler()
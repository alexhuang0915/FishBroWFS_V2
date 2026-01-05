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
from src.contracts.supervisor.build_portfolio import BuildPortfolioPayload
from src.control.paths import get_outputs_root

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
        outputs_root = get_outputs_root()
        if payload.outputs_root:
            outputs_root = Path(payload.outputs_root)
        
        # Create portfolio output directory (within season directory)
        portfolio_dir = outputs_root / "seasons" / payload.season / "portfolio"
        portfolio_dir.mkdir(parents=True, exist_ok=True)
        
        # Write payload to portfolio directory
        payload_path = portfolio_dir / "payload.json"
        with open(payload_path, "w") as f:
            json.dump(params, f, indent=2)
        
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
    
    def _execute_portfolio(self, payload: BuildPortfolioPayload, context: JobContext, outputs_root: Path, portfolio_dir: Path) -> Dict[str, Any]:
        """Execute the actual portfolio build logic."""
        # Update heartbeat
        context.heartbeat(progress=0.3, phase="preparing_portfolio")
        
        # Build command for portfolio execution
        cmd = [
            sys.executable, "-B", "-m", "scripts.build_portfolio_from_research",
            "--season", payload.season,
            "--outputs-root", str(outputs_root)
        ]
        
        # Add optional parameters
        if payload.allowlist:
            cmd.extend(["--allowlist", payload.allowlist])
        
        # Set up stdout/stderr capture
        stdout_path = Path(context.artifacts_dir) / "portfolio_stdout.txt"
        stderr_path = Path(context.artifacts_dir) / "portfolio_stderr.txt"
        
        logger.info(f"Executing portfolio build via CLI: {' '.join(cmd)}")
        
        # Update heartbeat
        context.heartbeat(progress=0.5, phase="executing_portfolio")
        
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
                result = self._parse_portfolio_output(stdout_path, portfolio_dir)
                
                return {
                    "ok": True,
                    "returncode": process.returncode,
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "result": result
                }
            else:
                error_msg = f"Portfolio CLI failed with return code {process.returncode}"
                logger.error(error_msg)
                
                # Read stderr for more details
                stderr_content = ""
                if stderr_path.exists():
                    stderr_content = stderr_path.read_text()[:1000]
                
                raise RuntimeError(f"{error_msg}\nStderr: {stderr_content}")
                
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Portfolio subprocess failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to execute portfolio build: {e}")
    
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
            "job_type": "build_portfolio_v2",
            "created_at": datetime.utcnow().isoformat() + "Z",
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
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        
        logger.info(f"Generated manifest at {manifest_path}")


# Register handler
build_portfolio_handler = BuildPortfolioHandler()
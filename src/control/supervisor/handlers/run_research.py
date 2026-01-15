from __future__ import annotations
import json
import logging
import subprocess
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional
import traceback
from dataclasses import fields

from ..job_handler import BaseJobHandler, JobContext
from contracts.supervisor.run_research import RunResearchPayload
from control.paths import get_outputs_root
from control.artifacts import write_json_atomic
from config.registry.instruments import load_instruments

logger = logging.getLogger(__name__)


def _normalize_run_research_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure params passed into RunResearchPayload(**params) contain only dataclass fields.
    Any extra keys (instrument/timeframe/season/run_mode/...) are packed into params_override.
    """
    # Guardrail: reject any profile field in payload
    profile_keys = [k for k in raw.keys() if 'profile' in k.lower()]
    if profile_keys:
        raise ValueError(
            "Profile selection via payload is FORBIDDEN. "
            "Please configure 'default_profile' in registry/instruments.yaml."
        )
    
    allowed = {f.name for f in fields(RunResearchPayload)}
    params: Dict[str, Any] = dict(raw)  # shallow copy

    extras = {k: params.pop(k) for k in list(params.keys()) if k not in allowed}
    if extras:
        override = params.get("params_override")
        if override is None:
            override = {}
        # If override is not a dict, normalize to dict to avoid runtime crash
        if not isinstance(override, dict):
            override = {"_raw_params_override": override}
        override.update(extras)
        params["params_override"] = override

    return params


class RunResearchHandler(BaseJobHandler):
    """RUN_RESEARCH_V2 handler for executing research runs via Supervisor."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate RUN_RESEARCH_V2 parameters."""
        try:
            normalized = _normalize_run_research_params(params)
            payload = RunResearchPayload(**normalized)
            payload.validate()
        except Exception as e:
            raise ValueError(f"Invalid run_research payload: {e}")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute RUN_RESEARCH_V2 job."""
        # Validate payload
        normalized = _normalize_run_research_params(params)
        payload = RunResearchPayload(**normalized)
        payload.validate()
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "RUN_RESEARCH_V2",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params
            }
            
        # Create run directory using job_id
        outputs_root = get_outputs_root()
        run_dir = outputs_root / "seasons" / "current" / context.job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Write payload to run directory
        payload_path = run_dir / "payload.json"
        write_json_atomic(payload_path, {"raw_params": params, "normalized_params": normalized})
        
        # Update heartbeat with progress
        context.heartbeat(progress=0.1, phase="validating_inputs")
        
        try:
            # Execute research logic
            result = self._execute_research(payload, context, run_dir)
            
            # Generate manifest
            self._generate_manifest(context.job_id, payload, run_dir)
            
            return {
                "ok": True,
                "job_type": "RUN_RESEARCH_V2",
                "payload": params,
                "run_dir": str(run_dir),
                "manifest_path": str(run_dir / "manifest.json"),
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Failed to execute research: {e}")
            logger.error(traceback.format_exc())
            
            # Write error to artifacts
            error_path = Path(context.artifacts_dir) / "error.txt"
            error_path.write_text(f"{e}\n\n{traceback.format_exc()}")
            
            raise  # Re-raise to mark job as FAILED
    
    def _execute_research(self, payload: RunResearchPayload, context: JobContext, run_dir: Path) -> Dict[str, Any]:
        """Execute the actual research logic."""
        # Update heartbeat
        context.heartbeat(progress=0.3, phase="preparing_research")
        
        # Build command for research execution
        # This should call the actual research engine
        # For now, we'll use a placeholder that calls generate_research.py
        cmd = [
            sys.executable, "-B", "-m", "scripts.generate_research",
            "--outputs-root", str(get_outputs_root()),
            "--season", "current",
            "--verbose"
        ]
        
        # Set up stdout/stderr capture
        stdout_path = Path(context.artifacts_dir) / "research_stdout.txt"
        stderr_path = Path(context.artifacts_dir) / "research_stderr.txt"
        
        logger.info(f"Executing research via CLI: {' '.join(cmd)}")
        
        # Update heartbeat
        context.heartbeat(progress=0.5, phase="executing_research")
        
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
                result = self._parse_research_output(stdout_path, run_dir)
                
                return {
                    "ok": True,
                    "returncode": process.returncode,
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "result": result
                }
            else:
                error_msg = f"Research CLI failed with return code {process.returncode}"
                logger.error(error_msg)
                
                # Read stderr for more details
                stderr_content = ""
                if stderr_path.exists():
                    stderr_content = stderr_path.read_text()[:1000]
                
                raise RuntimeError(f"{error_msg}\nStderr: {stderr_content}")
                
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Research subprocess failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to execute research: {e}")
    
    def _parse_research_output(self, stdout_path: Path, run_dir: Path) -> Dict[str, Any]:
        """Parse research output to extract results."""
        if not stdout_path.exists():
            return {"note": "No stdout captured"}
        
        content = stdout_path.read_text()
        
        # Look for common patterns in research output
        result = {
            "output_files": [],
            "research_dir": str(run_dir / "research"),
            "note": "Research execution completed"
        }
        
        # Check for generated files
        research_dir = run_dir / "research"
        if research_dir.exists():
            for file in research_dir.glob("*.json"):
                result["output_files"].append(str(file.name))
        
        return result
    
    def _get_profile_for_instrument(self, instrument_id: str) -> str:
        """Get default profile for instrument from registry."""
        registry = load_instruments()
        instrument = registry.get_instrument_by_id(instrument_id)
        if instrument is None:
            # Try to find by suffix (e.g., "MNQ" matches "CME.MNQ")
            for inst in registry.instruments:
                if inst.id.endswith(f".{instrument_id}"):
                    instrument = inst
                    break
            if instrument is None:
                raise ValueError(
                    f"Instrument '{instrument_id}' not found in registry. "
                    f"Available instruments: {registry.get_instrument_ids()}"
                )
        return instrument.profile
    
    def _generate_manifest(self, job_id: str, payload: RunResearchPayload, run_dir: Path) -> None:
        """Generate manifest.json for the research run."""
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
        
        # Determine instrument from params_override
        instrument_id = None
        if payload.params_override:
            instrument_id = payload.params_override.get("instrument")
        if not instrument_id:
            raise ValueError("Missing instrument in params_override")
        
        # Get profile from instrument registry
        profile_name = self._get_profile_for_instrument(instrument_id)
        
        manifest = {
            "job_id": job_id,
            "job_type": "run_research_v2",
            "created_at": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
            "input_fingerprint": {
                "strategy_id": payload.strategy_id,
                "profile_name": profile_name,
                "start_date": payload.start_date,
                "end_date": payload.end_date,
                "params_hash": input_fingerprint
            },
            "code_fingerprint": {
                "git_commit": git_commit
            },
            "run_directory": str(run_dir),
            "manifest_version": "1.0"
        }
        
        manifest_path = run_dir / "manifest.json"
        write_json_atomic(manifest_path, manifest)
        
        logger.info(f"Generated manifest at {manifest_path}")


# Register handler
run_research_handler = RunResearchHandler()

from __future__ import annotations
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from ..job_handler import BaseJobHandler, JobContext

logger = logging.getLogger(__name__)


class BuildDataHandler(BaseJobHandler):
    """BUILD_DATA handler for preparing data (bars and features)."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate BUILD_DATA parameters."""
        # Required: dataset_id
        if "dataset_id" not in params:
            raise ValueError("dataset_id is required")
        
        if not isinstance(params["dataset_id"], str):
            raise ValueError("dataset_id must be a string")
        
        # Validate timeframe_min if provided
        if "timeframe_min" in params:
            timeframe = params["timeframe_min"]
            if not isinstance(timeframe, int):
                raise ValueError("timeframe_min must be an integer")
            if timeframe <= 0:
                raise ValueError("timeframe_min must be positive")
        
        # Validate force_rebuild if provided
        if "force_rebuild" in params:
            if not isinstance(params["force_rebuild"], bool):
                raise ValueError("force_rebuild must be a boolean")
        
        # Validate mode if provided
        if "mode" in params:
            mode = params["mode"]
            if mode not in ["BARS_ONLY", "FEATURES_ONLY", "FULL"]:
                raise ValueError("mode must be one of: 'BARS_ONLY', 'FEATURES_ONLY', 'FULL'")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute BUILD_DATA job."""
        dataset_id = params["dataset_id"]
        timeframe_min = params.get("timeframe_min", 60)
        force_rebuild = params.get("force_rebuild", False)
        mode = params.get("mode", "FULL")
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "BUILD_DATA",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "dataset_id": dataset_id,
                "timeframe_min": timeframe_min
            }
        
        # Try to use the legacy prepare_with_data2_enforcement function
        try:
            return self._execute_via_function(params, context)
        except ImportError as e:
            logger.warning(f"Failed to import prepare_with_data2_enforcement: {e}")
            # Fallback to CLI invocation
            return self._execute_via_cli(params, context)
    
    def _execute_via_function(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute BUILD_DATA using the legacy Python function."""
        from control.prepare_orchestration import prepare_with_data2_enforcement
        
        dataset_id = params["dataset_id"]
        timeframe_min = params.get("timeframe_min", 60)
        force_rebuild = params.get("force_rebuild", False)
        mode = params.get("mode", "FULL")
        
        # Map mode to prepare_orchestration parameters
        # Note: prepare_with_data2_enforcement expects different parameters
        # We need to adapt based on actual function signature
        
        # For now, use a simplified call
        # In production, would need to map parameters properly
        try:
            # Call the legacy function
            result = prepare_with_data2_enforcement(
                mode=mode,
                season="2026Q1",  # Default season
                dataset_id=dataset_id,
                timeframe_min=timeframe_min,
                force_rebuild=force_rebuild
            )
            
            # Write result to artifacts
            result_path = Path(context.artifacts_dir) / "build_data_result.json"
            result_path.write_text(json.dumps(result, indent=2))
            
            # Extract produced paths from result
            produced_paths = []
            if "data1_report" in result and "fingerprint_path" in result["data1_report"]:
                produced_paths.append(result["data1_report"]["fingerprint_path"])
            if "data2_reports" in result:
                for feed_id, report in result["data2_reports"].items():
                    if "fingerprint_path" in report:
                        produced_paths.append(report["fingerprint_path"])
            
            return {
                "ok": True,
                "job_type": "BUILD_DATA",
                "dataset_id": dataset_id,
                "timeframe_min": timeframe_min,
                "legacy_invocation": f"prepare_with_data2_enforcement(mode={mode}, dataset_id={dataset_id}, timeframe_min={timeframe_min})",
                "stdout_path": str(result_path),
                "stderr_path": None,
                "produced_paths": produced_paths,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Failed to execute prepare_with_data2_enforcement: {e}")
            # Fallback to CLI
            return self._execute_via_cli(params, context)
    
    def _execute_via_cli(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute BUILD_DATA via CLI subprocess."""
        dataset_id = params["dataset_id"]
        timeframe_min = params.get("timeframe_min", 60)
        force_rebuild = params.get("force_rebuild", False)
        mode = params.get("mode", "FULL")
        
        # Build command based on available CLI tools
        # Try to use shared_cli.py if available
        cmd = [
            sys.executable, "-B", "-m", "src.control.shared_cli",
            "build",
            "--dataset", dataset_id,
            "--timeframe", str(timeframe_min),
            "--mode", mode
        ]
        
        if force_rebuild:
            cmd.append("--force-rebuild")
        
        # Set up stdout/stderr capture
        stdout_path = Path(context.artifacts_dir) / "build_data_stdout.txt"
        stderr_path = Path(context.artifacts_dir) / "build_data_stderr.txt"
        
        logger.info(f"Executing BUILD_DATA via CLI: {' '.join(cmd)}")
        
        try:
            with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
                # Send heartbeat before starting
                context.heartbeat(progress=0.0, phase="starting_cli")
                
                # Run subprocess
                process = subprocess.run(
                    cmd,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    cwd=Path.cwd()
                )
            
            # Check result
            if process.returncode == 0:
                # Try to parse output to get produced paths
                produced_paths = self._extract_produced_paths(stdout_path)
                
                return {
                    "ok": True,
                    "job_type": "BUILD_DATA",
                    "dataset_id": dataset_id,
                    "timeframe_min": timeframe_min,
                    "legacy_invocation": " ".join(cmd),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "produced_paths": produced_paths,
                    "returncode": process.returncode
                }
            else:
                return {
                    "ok": False,
                    "job_type": "BUILD_DATA",
                    "dataset_id": dataset_id,
                    "timeframe_min": timeframe_min,
                    "legacy_invocation": " ".join(cmd),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "produced_paths": [],
                    "returncode": process.returncode,
                    "error": f"CLI failed with return code {process.returncode}"
                }
                
        except Exception as e:
            logger.error(f"Failed to execute CLI command: {e}")
            # Write error to stderr file
            stderr_path.write_text(f"Failed to execute command: {e}\nCommand: {' '.join(cmd)}")
            
            return {
                "ok": False,
                "job_type": "BUILD_DATA",
                "dataset_id": dataset_id,
                "timeframe_min": timeframe_min,
                "legacy_invocation": " ".join(cmd),
                "stdout_path": None,
                "stderr_path": str(stderr_path),
                "produced_paths": [],
                "error": str(e)
            }
    
    def _extract_produced_paths(self, stdout_path: Path) -> list[str]:
        """Extract produced file paths from CLI stdout."""
        try:
            if not stdout_path.exists():
                return []
            
            content = stdout_path.read_text()
            paths = []
            
            # Look for common patterns in build output
            import re
            
            # Look for fingerprint paths
            fingerprint_patterns = [
                r"Fingerprint path: (.+)",
                r"fingerprint_path.*['\"]([^'\"]+)['\"]",
                r"outputs/.*\.json"
            ]
            
            for pattern in fingerprint_patterns:
                matches = re.findall(pattern, content)
                paths.extend(matches)
            
            # Look for manifest paths
            manifest_patterns = [
                r"Manifest path: (.+)",
                r"manifest_path.*['\"]([^'\"]+)['\"]"
            ]
            
            for pattern in manifest_patterns:
                matches = re.findall(pattern, content)
                paths.extend(matches)
            
            # Deduplicate
            return list(set(paths))
            
        except Exception as e:
            logger.warning(f"Failed to extract produced paths: {e}")
            return []
    
    def _check_abort_during_execution(self, context: JobContext) -> bool:
        """Check for abort request during execution."""
        if context.is_abort_requested():
            logger.info("Abort requested during BUILD_DATA execution")
            return True
        return False


# Register handler
build_data_handler = BuildDataHandler()
from __future__ import annotations
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from ..job_handler import BaseJobHandler, JobContext

logger = logging.getLogger(__name__)


class GenerateReportsHandler(BaseJobHandler):
    """GENERATE_REPORTS handler for generating canonical results and research index."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate GENERATE_REPORTS parameters."""
        # Validate outputs_root if provided
        if "outputs_root" in params:
            if not isinstance(params["outputs_root"], str):
                raise ValueError("outputs_root must be a string")
        
        # Validate season if provided
        if "season" in params:
            if not isinstance(params["season"], str):
                raise ValueError("season must be a string")
        
        # Validate strict if provided
        if "strict" in params:
            if not isinstance(params["strict"], bool):
                raise ValueError("strict must be a boolean")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute GENERATE_REPORTS job."""
        outputs_root = params.get("outputs_root", "outputs")
        season = params.get("season")
        strict = params.get("strict", True)
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "GENERATE_REPORTS",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "outputs_root": outputs_root,
                "season": season
            }
        
        # Try to use the legacy generate_research.py script
        return self._execute_via_cli(params, context)
    
    def _execute_via_cli(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute GENERATE_REPORTS via CLI subprocess."""
        outputs_root = params.get("outputs_root", "outputs")
        season = params.get("season")
        strict = params.get("strict", True)
        
        # Build command for generate_research.py
        cmd = [
            sys.executable, "-B",
            "scripts/generate_research.py",
            "--outputs-root", outputs_root
        ]
        
        if season:
            cmd.extend(["--season", season])
        
        # Add strict flag if False (default is True in script)
        if not strict:
            cmd.append("--no-strict")
        
        # Set up stdout/stderr capture
        stdout_path = Path(context.artifacts_dir) / "generate_reports_stdout.txt"
        stderr_path = Path(context.artifacts_dir) / "generate_reports_stderr.txt"
        
        logger.info(f"Executing GENERATE_REPORTS via CLI: {' '.join(cmd)}")
        
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
                # Extract report paths from output
                report_paths = self._extract_report_paths(stdout_path, outputs_root, season)
                
                return {
                    "ok": True,
                    "job_type": "GENERATE_REPORTS",
                    "outputs_root": outputs_root,
                    "season": season,
                    "strict": strict,
                    "legacy_invocation": " ".join(cmd),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "report_paths": report_paths,
                    "returncode": process.returncode
                }
            else:
                # Check if failure is due to strict mode
                error_message = "CLI failed"
                if strict:
                    error_message += " (strict mode enabled)"
                
                return {
                    "ok": False,
                    "job_type": "GENERATE_REPORTS",
                    "outputs_root": outputs_root,
                    "season": season,
                    "strict": strict,
                    "legacy_invocation": " ".join(cmd),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "report_paths": [],
                    "returncode": process.returncode,
                    "error": error_message
                }
                
        except Exception as e:
            logger.error(f"Failed to execute CLI command: {e}")
            # Write error to stderr file
            stderr_path.write_text(f"Failed to execute command: {e}\nCommand: {' '.join(cmd)}")
            
            return {
                "ok": False,
                "job_type": "GENERATE_REPORTS",
                "outputs_root": outputs_root,
                "season": season,
                "strict": strict,
                "legacy_invocation": " ".join(cmd),
                "stdout_path": None,
                "stderr_path": str(stderr_path),
                "report_paths": [],
                "error": str(e)
            }
    
    def _extract_report_paths(self, stdout_path: Path, outputs_root: str, season: Optional[str]) -> list[str]:
        """Extract report file paths from CLI stdout."""
        try:
            if not stdout_path.exists():
                return []
            
            content = stdout_path.read_text()
            paths = []
            
            # Look for canonical_results.json paths
            import re
            
            # Pattern for canonical_results.json
            canonical_pattern = r"canonical_results\.json"
            
            # Also look for explicit paths in output
            path_patterns = [
                r"Writing canonical_results\.json to (.+)",
                r"Saved.*to ['\"]([^'\"]+canonical_results\.json)['\"]",
                r"outputs/.*/research/.*canonical_results\.json"
            ]
            
            for pattern in path_patterns:
                matches = re.findall(pattern, content)
                paths.extend(matches)
            
            # If no paths found, construct default paths
            if not paths:
                base_path = Path(outputs_root)
                if season:
                    # Look in season-specific research directory
                    research_dir = base_path / "seasons" / season / "research"
                    if research_dir.exists():
                        canonical_path = research_dir / "canonical_results.json"
                        if canonical_path.exists():
                            paths.append(str(canonical_path))
                else:
                    # Look in all season research directories
                    seasons_dir = base_path / "seasons"
                    if seasons_dir.exists():
                        for season_dir in seasons_dir.iterdir():
                            if season_dir.is_dir():
                                research_dir = season_dir / "research"
                                if research_dir.exists():
                                    canonical_path = research_dir / "canonical_results.json"
                                    if canonical_path.exists():
                                        paths.append(str(canonical_path))
            
            # Also look for research_index.json
            index_patterns = [
                r"research_index\.json",
                r"Writing research_index\.json to (.+)",
                r"outputs/.*/research/.*research_index\.json"
            ]
            
            for pattern in index_patterns:
                matches = re.findall(pattern, content)
                paths.extend(matches)
            
            # Deduplicate
            return list(set(paths))
            
        except Exception as e:
            logger.warning(f"Failed to extract report paths: {e}")
            return []
    
    def _execute_via_function(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute GENERATE_REPORTS using the legacy Python function."""
        # Try to use generate_canonical_results directly
        try:
            from research.__main__ import generate_canonical_results
            
            outputs_root = params.get("outputs_root", "outputs")
            season = params.get("season")
            strict = params.get("strict", True)
            
            # Determine research directory
            base_path = Path(outputs_root)
            if season:
                research_dir = base_path / "seasons" / season / "research"
            else:
                # Use default research directory
                research_dir = base_path / "research"
            
            # Ensure directory exists
            research_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate canonical results
            canonical_path = generate_canonical_results(base_path, research_dir)
            
            # Also generate research index if available
            index_path = None
            try:
                from research.registry import generate_research_index
                index_path = generate_research_index(base_path, research_dir)
            except ImportError:
                logger.warning("generate_research_index not available")
            
            # Collect report paths
            report_paths = [str(canonical_path)]
            if index_path:
                report_paths.append(str(index_path))
            
            # Write summary to artifacts
            summary_path = Path(context.artifacts_dir) / "generate_reports_summary.json"
            summary = {
                "outputs_root": outputs_root,
                "season": season,
                "strict": strict,
                "canonical_results_path": str(canonical_path),
                "research_index_path": str(index_path) if index_path else None,
                "report_paths": report_paths
            }
            summary_path.write_text(json.dumps(summary, indent=2))
            
            return {
                "ok": True,
                "job_type": "GENERATE_REPORTS",
                "outputs_root": outputs_root,
                "season": season,
                "strict": strict,
                "legacy_invocation": f"generate_canonical_results(outputs_root={outputs_root}, research_dir={research_dir})",
                "stdout_path": str(summary_path),
                "stderr_path": None,
                "report_paths": report_paths
            }
            
        except ImportError as e:
            logger.warning(f"Failed to import generate_canonical_results: {e}")
            # Fallback to CLI
            return self._execute_via_cli(params, context)
        except Exception as e:
            logger.error(f"Failed to execute generate_canonical_results: {e}")
            # Check if failure is due to strict mode
            if params.get("strict", True):
                return {
                    "ok": False,
                    "job_type": "GENERATE_REPORTS",
                    "outputs_root": params.get("outputs_root", "outputs"),
                    "season": params.get("season"),
                    "strict": True,
                    "legacy_invocation": "generate_canonical_results",
                    "stdout_path": None,
                    "stderr_path": None,
                    "report_paths": [],
                    "error": str(e)
                }
            else:
                # In non-strict mode, we might still have partial success
                # For now, return failure
                return {
                    "ok": False,
                    "job_type": "GENERATE_REPORTS",
                    "outputs_root": params.get("outputs_root", "outputs"),
                    "season": params.get("season"),
                    "strict": False,
                    "legacy_invocation": "generate_canonical_results",
                    "stdout_path": None,
                    "stderr_path": None,
                    "report_paths": [],
                    "error": str(e),
                    "partial_success": True
                }


# Register handler
generate_reports_handler = GenerateReportsHandler()
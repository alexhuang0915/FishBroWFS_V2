from __future__ import annotations
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from ..job_handler import BaseJobHandler, JobContext
from control.artifacts import write_json_atomic
from control.supervisor.models import get_job_artifact_dir
from core.paths import get_outputs_root
from core.season_context import current_season
from core.timeframe_aggregator import TimeframeAggregator
from core.data_aligner import DataAligner
from control.bars_store import normalized_bars_path, resampled_bars_path, load_npz
from config.registry.datasets import load_datasets
from config.registry.instruments import load_instruments

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
            write_json_atomic(result_path, result)
            
            # Extract produced paths from result
            alignment_path = _write_data_alignment_report(context.job_id, params, result)

            produced_paths = []
            if "data1_report" in result and "fingerprint_path" in result["data1_report"]:
                produced_paths.append(result["data1_report"]["fingerprint_path"])
            if "data2_reports" in result:
                for feed_id, report in result["data2_reports"].items():
                    if "fingerprint_path" in report:
                        produced_paths.append(report["fingerprint_path"])
            if alignment_path:
                produced_paths.append(alignment_path)
            
            manifest_path = self._write_build_manifest(params, context, result)
            return {
                "ok": True,
                "job_type": "BUILD_DATA",
                "dataset_id": dataset_id,
                "timeframe_min": timeframe_min,
                "legacy_invocation": f"prepare_with_data2_enforcement(mode={mode}, dataset_id={dataset_id}, timeframe_min={timeframe_min})",
                "stdout_path": str(result_path),
                "stderr_path": None,
                "produced_paths": produced_paths,
                "manifest_path": str(manifest_path) if manifest_path else None,
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
                
                manifest_path = self._write_build_manifest(params, context, {"ok": True})
                return {
                    "ok": True,
                    "job_type": "BUILD_DATA",
                    "dataset_id": dataset_id,
                    "timeframe_min": timeframe_min,
                    "legacy_invocation": " ".join(cmd),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "produced_paths": produced_paths,
                    "returncode": process.returncode,
                    "manifest_path": str(manifest_path) if manifest_path else None,
                }
            else:
                manifest_path = self._write_build_manifest(params, context, {"ok": False, "error": "cli_failed"})
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
                    "error": f"CLI failed with return code {process.returncode}",
                    "manifest_path": str(manifest_path) if manifest_path else None,
                }
                
        except Exception as e:
            logger.error(f"Failed to execute CLI command: {e}")
            # Write error to stderr file
            stderr_path.write_text(f"Failed to execute command: {e}\nCommand: {' '.join(cmd)}")
            
            manifest_path = self._write_build_manifest(params, context, {"ok": False, "error": "cli_exception"})
            return {
                "ok": False,
                "job_type": "BUILD_DATA",
                "dataset_id": dataset_id,
                "timeframe_min": timeframe_min,
                "legacy_invocation": " ".join(cmd),
                "stdout_path": None,
                "stderr_path": str(stderr_path),
                "produced_paths": [],
                "error": str(e),
                "manifest_path": str(manifest_path) if manifest_path else None,
            }

    def _write_build_manifest(self, params: Dict[str, Any], context: JobContext, result: Dict[str, Any]) -> Optional[Path]:
        """Write a minimal build manifest into job artifacts."""
        dataset_id = params.get("dataset_id")
        timeframe_min = params.get("timeframe_min", 60)
        season = params.get("season") or current_season()
        outputs_root = get_outputs_root()

        if not dataset_id:
            return None

        produced_bars_path = None
        if dataset_id:
            try:
                candidate_path = resampled_bars_path(outputs_root, season, dataset_id, timeframe_min)  # type: ignore[arg-type]
                produced_bars_path = str(candidate_path)
            except Exception:
                produced_bars_path = None

        manifest = {
            "schema_version": "1.0",
            "job_id": context.job_id,
            "job_type": "BUILD_DATA",
            "dataset_id": dataset_id,
            "timeframe_min": timeframe_min,
            "season": season,
            "outputs_root": str(outputs_root),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "produced_bars_path": produced_bars_path,
            "result": {
                "ok": bool(result.get("ok", False)),
                "error": result.get("error"),
            },
            "inventory_rows": [],
        }

        try:
            bar_path = resampled_bars_path(outputs_root, season, dataset_id, timeframe_min)  # type: ignore[arg-type]
            if bar_path.exists():
                stat = bar_path.stat()
                size_mb = stat.st_size / (1024 * 1024)
                manifest["inventory_rows"].append({
                    "instrument": dataset_id,
                    "timeframe": f"{timeframe_min}m",
                    "date_range": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "size": f"{size_mb:.1f} MB",
                    "status": "READY",
                    "path": str(bar_path),
                })
            else:
                manifest["inventory_rows"].append({
                    "instrument": dataset_id,
                    "timeframe": f"{timeframe_min}m",
                    "date_range": "—",
                    "size": "—",
                    "status": "MISSING",
                    "path": str(bar_path),
                })
        except Exception as exc:
            logger.warning("Failed to build manifest inventory row: %s", exc)

        artifact_dir = Path(context.artifacts_dir)
        manifest_path = artifact_dir / "build_data_manifest.json"
        write_json_atomic(manifest_path, manifest)
        return manifest_path
    
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


def _npz_to_dataframe(npz_data: dict[str, Any]) -> pd.DataFrame:
    columns = ["ts", "open", "high", "low", "close", "volume"]
    missing = [col for col in columns if col not in npz_data]
    if missing:
        raise ValueError(f"bars data missing columns: {missing}")

    data = {col: npz_data[col] for col in columns}
    data["ts"] = pd.to_datetime(data["ts"])
    return pd.DataFrame(data)


def _write_data_alignment_report(job_id: str, params: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
    data2_reports = (result.get("data2_reports") or {})
    if not data2_reports:
        logger.debug("No Data2 reports present; skipping alignment report.")
        return None

    data2_dataset_id = next(iter(data2_reports))
    dataset_id = params.get("dataset_id")
    if not dataset_id:
        logger.warning("BUILD_DATA parameters missing dataset_id; cannot produce alignment report.")
        return None

    timeframe_min = params.get("timeframe_min", 60)
    season = params.get("season", "2026Q1")
    outputs_root = get_outputs_root()

    dataset_registry = load_datasets()
    data1_spec = dataset_registry.get_dataset_by_id(dataset_id)
    if data1_spec is None:
        logger.warning("Unknown Data1 dataset id '%s'; skipping alignment report.", dataset_id)
        return None

    instrument_registry = load_instruments()
    instrument_spec = instrument_registry.get_instrument_by_id(data1_spec.instrument_id)
    if instrument_spec is None:
        logger.warning(
            "Instrument spec not found for '%s'; cannot compute trade-date alignment.",
            data1_spec.instrument_id,
        )
        return None

    try:
        roll_time = datetime.strptime(instrument_spec.trade_date_roll_time_local, "%H:%M").time()
    except ValueError as exc:
        logger.warning(
            "Invalid trade_date_roll_time_local for instrument %s: %s",
            instrument_spec.id,
            exc,
        )
        return None

    timezone_name = instrument_spec.timezone

    normalized_path = normalized_bars_path(outputs_root, season, data2_dataset_id)
    if not normalized_path.exists():
        logger.warning("Normalized bars missing for Data2 '%s'; cannot align.", data2_dataset_id)
        return None

    resampled_path = resampled_bars_path(outputs_root, season, dataset_id, timeframe_min)
    if not resampled_path.exists():
        logger.warning("Resampled bars missing for Data1 '%s'; cannot align.", dataset_id)
        return None

    try:
        data2_norm = load_npz(normalized_path)
        data1_resampled = load_npz(resampled_path)

        data2_df = _npz_to_dataframe(data2_norm).sort_values("ts")
        data1_df = _npz_to_dataframe(data1_resampled).sort_values("ts")
    except Exception as exc:
        logger.warning("Failed to load bars for data alignment: %s", exc)
        return None

    if data2_df.empty:
        logger.warning("Data2 normalized bars empty for '%s'; skipping alignment.", data2_dataset_id)
        return None

    try:
        aggregator = TimeframeAggregator(timeframe_min=timeframe_min, roll_time=roll_time)
        data2_agg = aggregator.aggregate(data2_df)
    except Exception as exc:
        logger.warning("Aggregation failed for Data2 '%s': %s", data2_dataset_id, exc)
        return None

    if data2_agg.empty:
        logger.warning("Aggregated Data2 bars empty after applying timeframe %s.", timeframe_min)
        return None

    try:
        aligner = DataAligner()
        aligned_df, metrics = aligner.align(data1_df, data2_agg)
    except Exception as exc:
        logger.warning("Data alignment failed for job %s: %s", job_id, exc)
        return None

    input_rows = len(data2_agg)
    output_rows = len(aligned_df)
    dropped_rows = max(0, input_rows - output_rows)

    report = {
        "job_id": job_id,
        "instrument": data1_spec.instrument_id,
        "timeframe": f"{timeframe_min}m",
        "trade_date_roll_time_local": instrument_spec.trade_date_roll_time_local,
        "timezone": timezone_name,
        "input_rows": input_rows,
        "output_rows": output_rows,
        "dropped_rows": dropped_rows,
        "forward_filled_rows": metrics.data2_hold_bars_total,
        "forward_fill_ratio": metrics.data2_hold_ratio,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    job_artifacts_dir = get_job_artifact_dir(outputs_root, job_id)
    job_artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_path = job_artifacts_dir / "data_alignment_report.json"
    try:
        write_json_atomic(report_path, report)
    except Exception as exc:
        logger.warning("Failed to write data_alignment_report.json for job %s: %s", job_id, exc)
        return None

    logger.info("Data alignment report written to %s", report_path)
    return str(report_path)


# Register handler
build_data_handler = BuildDataHandler()
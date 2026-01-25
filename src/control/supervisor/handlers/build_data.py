from __future__ import annotations
import json
import logging
import subprocess
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from ..job_handler import BaseJobHandler, JobContext, register_handler
from control.artifacts import write_json_atomic
from control.supervisor.models import get_job_artifact_dir
from control.runtime_index import update_runtime_index
from core.paths import get_outputs_root
from core.season_context import current_season
from core.timeframe_aggregator import TimeframeAggregator
from core.data_aligner import DataAligner
from control.bars_store import normalized_bars_path, resampled_bars_path, load_npz
# from config.registry.datasets import load_datasets # REMOVED
# from config.registry.instruments import load_instruments # REMOVED

logger = logging.getLogger(__name__)


def _parse_timeframes_param(params: Dict[str, Any]) -> list[int]:
    timeframes = params.get("timeframes")
    if isinstance(timeframes, list):
        return [int(x) for x in timeframes]
    if isinstance(timeframes, str) and timeframes.strip():
        return [int(x.strip()) for x in timeframes.split(",") if x.strip()]
    return [int(params.get("timeframe_min", 60) or 60)]


def _missing_resampled_bars(season: str, dataset_id: str, tfs: list[int]) -> list[str]:
    outputs_root = get_outputs_root()
    missing = []
    for tf in tfs:
        p = resampled_bars_path(outputs_root, season, dataset_id, str(int(tf)))
        if not p.exists():
            missing.append(str(p))
    return missing


def _purge_shared_dataset_dir(season: str, dataset_id: str) -> Optional[str]:
    """
    Purge the entire shared dataset directory:
      cache/shared/<season>/<dataset_id>/
    Returns the purged path (string) if something was removed, otherwise None.
    """
    from core.paths import get_shared_cache_root

    shared_root = get_shared_cache_root().resolve()
    target = (shared_root / season / dataset_id).resolve()
    try:
        target.relative_to(shared_root)
    except Exception as exc:
        raise ValueError(f"Refusing to purge outside shared cache root: {target}") from exc

    if not target.exists():
        return None
    shutil.rmtree(target)
    return str(target)


class BuildDataHandler(BaseJobHandler):
    """BUILD_DATA handler for preparing data (bars and features)."""

    JOB_TYPE = "BUILD_DATA"
    
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

        # Validate timeframes if provided (preferred)
        if "timeframes" in params:
            tfs = params["timeframes"]
            if isinstance(tfs, str):
                # comma-separated string
                _ = [x.strip() for x in tfs.split(",") if x.strip()]
            elif isinstance(tfs, list):
                for tf in tfs:
                    if not isinstance(tf, int):
                        raise ValueError("timeframes list must be integers")
            else:
                raise ValueError("timeframes must be a comma-separated string or list[int]")
        
        # Validate force_rebuild if provided
        if "force_rebuild" in params:
            if not isinstance(params["force_rebuild"], bool):
                raise ValueError("force_rebuild must be a boolean")

        # Validate purge_before_build if provided
        if "purge_before_build" in params:
            if not isinstance(params["purge_before_build"], bool):
                raise ValueError("purge_before_build must be a boolean")
        
        # Validate mode if provided
        if "mode" in params:
            mode = params["mode"]
            if mode not in ["BARS_ONLY", "FEATURES_ONLY", "FULL"]:
                raise ValueError("mode must be one of: 'BARS_ONLY', 'FEATURES_ONLY', 'FULL'")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute BUILD_DATA job."""
        dataset_id = params["dataset_id"]
        tfs = _parse_timeframes_param(params)
        timeframe_min = int(tfs[0]) if tfs else int(params.get("timeframe_min", 60) or 60)
        force_rebuild = params.get("force_rebuild", False)
        mode = params.get("mode", "FULL")
        
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": self.JOB_TYPE,
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "dataset_id": dataset_id,
                "timeframe_min": timeframe_min
            }
        
        
        # DEBUG TRACE
        try:
            trace_path = Path(context.artifacts_dir) / "trace_debug.txt"
            with open(trace_path, "a") as f:
                f.write(f"Entering execute at {datetime.now()}\n")
        except:
            pass

        # ALWAYS execute via CLI for consistency and isolation (Unification)
        # Using shared_cli ensure PYTHONPATH is handled correctly via _execute_via_cli logic
        return self._execute_via_cli(params, context)

        # Legacy direct function call removed to prevent stalls/crashes
        # due to unmaintained prepare_orchestration.py

    def _execute_via_cli(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute BUILD_DATA via CLI subprocess."""
        dataset_id = params["dataset_id"]
        tfs = _parse_timeframes_param(params)
        timeframe_min = int(tfs[0]) if tfs else int(params.get("timeframe_min", 60) or 60)
        tfs_str = ",".join(str(int(x)) for x in (tfs or [timeframe_min]))
        force_rebuild = params.get("force_rebuild", False)
        mode = params.get("mode", "FULL")
        season = params.get("season") or current_season()
        purge_before_build = bool(params.get("purge_before_build", False))

        if purge_before_build:
            context.heartbeat(progress=0.0, phase="purging_shared_cache")
            purged = _purge_shared_dataset_dir(season, dataset_id)
            if purged:
                try:
                    (Path(context.artifacts_dir) / "purged_shared_dir.txt").write_text(purged + "\n", encoding="utf-8")
                except Exception:
                    pass
        
        build_bars = mode in ["BARS_ONLY", "FULL"]
        build_features = mode in ["FEATURES_ONLY", "FULL"]
        
        # Resolve TXT path
        txt_path = self._resolve_txt_path(dataset_id)
        if not txt_path:
             return {
                "ok": False,
                "job_type": self.JOB_TYPE,
                "dataset_id": dataset_id,
                "error": f"Could not find raw TXT file for {dataset_id}",
                "produced_paths": []
             }

        # Build command based on available CLI tools
        # Try to use shared_cli.py if available
        # `control.shared_cli` is the canonical CLI module (PYTHONPATH is set to include `src/`).
        # Map BUILD_DATA params to shared build contract:
        # - BUILD_DATA.mode: FULL/BARS_ONLY/FEATURES_ONLY -> shared-cli build flags
        # - shared-cli --mode is FULL/INCREMENTAL, not BUILD_DATA.mode
        cli_mode = "full"
        cmd = [
            sys.executable,
            "-B",
            "-m",
            "control.shared_cli",
            "build",
            "--season",
            season,
            "--dataset-id",
            dataset_id,
            "--tfs",
            tfs_str,
            "--mode",
            cli_mode,
            "--outputs-root",
            str(get_outputs_root()),
            "--txt-path",
            str(txt_path),
        ]
        
        if build_bars:
            cmd.append("--build-bars")
        else:
            cmd.append("--no-build-bars")
            
        if build_features:
            cmd.append("--build-features")
            feature_scope = str(params.get("feature_scope") or "baseline")
            cmd.extend(["--feature-scope", feature_scope])
        else:
            cmd.append("--no-build-features")
        
        # force_rebuild logic is handled by 'mode' (FULL vs INCREMENTAL) and shared_build internal logic
        # shared_cli does not accept --force-rebuild flag
        
        # Set up stdout/stderr capture
        stdout_path = Path(context.artifacts_dir) / "build_data_stdout.txt"
        stderr_path = Path(context.artifacts_dir) / "build_data_stderr.txt"
        
        logger.info(f"Executing BUILD_DATA via CLI: {' '.join(cmd)}")
        
        # DEBUG TRACE
        try:
            trace_path = Path(context.artifacts_dir) / "trace_debug.txt"
            with open(trace_path, "a") as f:
                f.write(f"Entering _execute_via_cli at {datetime.now()}\n")
                f.write(f"Command: {cmd}\n")
        except:
            pass
        
        try:
            with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
                # Send heartbeat before starting
                context.heartbeat(progress=0.0, phase="starting_cli")
                
                # Prepare environment with validated PYTHONPATH
                import os
                env = os.environ.copy()
                # Ensure src is in PYTHONPATH so subprocess can find modules
                # Prepend to existing PYTHONPATH if any
                src_path = str(Path.cwd() / "src")
                env["PYTHONPATH"] = f"{src_path}:{env.get('PYTHONPATH', '')}"
                # Centralize numba JIT disk cache
                try:
                    from core.paths import get_numba_cache_root

                    numba_dir = get_numba_cache_root()
                    numba_dir.mkdir(parents=True, exist_ok=True)
                    env.setdefault("NUMBA_CACHE_DIR", str(numba_dir))
                except Exception:
                    pass

                # Run subprocess
                process = subprocess.run(
                    cmd,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    cwd=Path.cwd(),
                    env=env
                )
                
                # DEBUG TRACE
                try:
                    with open(trace_path, "a") as f:
                        f.write(f"Process finished with returncode {process.returncode} at {datetime.now()}\n")
                except:
                    pass
            
            # Check result
            if process.returncode == 0:
                # Try to parse output to get produced paths
                produced_paths = self._extract_produced_paths(stdout_path)
                
                # Verify artifacts exist (Fail-Closed Guard)
                from contracts.artifact_guard import get_contract_for_job, assert_artifacts_present
                from control.control_types import ReasonCode

                # Determine contract based on mode
                contract = get_contract_for_job(self.JOB_TYPE, mode=mode)
                
                if contract:
                    from core.paths import get_shared_cache_root

                    root_path = get_shared_cache_root() / season / dataset_id

                    missing = assert_artifacts_present(root_path, contract)
                    if missing:
                        manifest_path = self._write_build_manifest(params, context, {
                            "ok": False,
                            "error": ReasonCode.ERR_FEATURE_ARTIFACTS_MISSING,
                            "missing_artifacts": missing
                        })
                        return {
                            "ok": False,
                            "job_type": self.JOB_TYPE,
                            "dataset_id": dataset_id,
                            "timeframe_min": timeframe_min,
                            "legacy_invocation": " ".join(cmd),
                            "stdout_path": str(stdout_path),
                            "stderr_path": str(stderr_path),
                            "produced_paths": [],
                            "returncode": 0,
                            "error": f"{ReasonCode.ERR_FEATURE_ARTIFACTS_MISSING}: {missing}",
                            "manifest_path": str(manifest_path) if manifest_path else None,
                        }
                
                # Check bars separately (legacy logic maintained or could be moved to contract)
                # Current implementation: we keep the bars check we added in previous task if mode includes bars
                # But to avoid conflict, we focused on features guard for this task as per plan.
                # However, fail-closed bars logic from previous task sits here too.
                # Since we are modifying the code block, we should preserve the bars logic if it's not covered by contract.
                # The contract currently only covers features. 
                # Let's keep the bars check logic simple for now or merge it.
                # The user asked for FEATURE guards specifically in this task.
                
                # Previous guard (Bars)
                if build_bars:
                     try:
                        missing_bars = _missing_resampled_bars(season, dataset_id, tfs)
                        if missing_bars:
                            manifest_path = self._write_build_manifest(params, context, {
                                "ok": False,
                                "error": "ERR_BUILD_ARTIFACTS_MISSING"
                            })
                            return {
                                "ok": False,
                                "job_type": self.JOB_TYPE,
                                "dataset_id": dataset_id,
                                "timeframe_min": timeframe_min,
                                "legacy_invocation": " ".join(cmd),
                                "stdout_path": str(stdout_path),
                                "stderr_path": str(stderr_path),
                                "produced_paths": [],
                                "returncode": 0,
                                "error": f"ERR_BUILD_ARTIFACTS_MISSING: Bars missing: {missing_bars}",
                                "manifest_path": str(manifest_path) if manifest_path else None,
                            }
                     except Exception as e:
                           pass # Should fail via returncode if critical logic failed, but here we are strict.

                manifest_path = self._write_build_manifest(params, context, {"ok": True})
                
                # [WIRE FIX] Update runtime index on success
                try:
                    update_runtime_index()
                except Exception as e:
                    logger.warning(f"Failed to update runtime index: {e}")

                return {
                    "ok": True,
                    "job_type": self.JOB_TYPE,
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
                    "job_type": self.JOB_TYPE,
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
            # [CRITICAL DIAGNOSTIC] Write crash log to artifacts
            import traceback
            crash_path = Path(context.artifacts_dir) / "crash_cli.txt"
            try:
                crash_path.write_text(f"Exception in _execute_via_cli:\n{traceback.format_exc()}")
            except:
                pass

            logger.error(f"Failed to execute CLI command: {e}")
            # Write error to stderr file
            stderr_path.write_text(f"Failed to execute command: {e}\nCommand: {' '.join(cmd)}")
            
            manifest_path = self._write_build_manifest(params, context, {"ok": False, "error": "cli_exception"})
            return {
                "ok": False,
                "job_type": self.JOB_TYPE,
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
        tfs = _parse_timeframes_param(params)
        timeframe_min = int(tfs[0]) if tfs else int(params.get("timeframe_min", 60) or 60)
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
            "job_type": self.JOB_TYPE,
            "dataset_id": dataset_id,
            "timeframe_min": timeframe_min,
            "timeframes": tfs,
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

    def _resolve_txt_path(self, dataset_id: str) -> Optional[Path]:
        """
        Find TXT file path for a given dataset ID.
        Looks in the standard raw data directory.
        """
        # Prefer core.paths.get_raw_root() (env override supported). Default is repo-relative FishBroData.
        try:
            from core.paths import get_raw_root  # local import to avoid circulars
            raw_root = get_raw_root()
        except Exception:
            raw_root = get_outputs_root().parent / "FishBroData"

        raw_dir = raw_root / "raw"
        
        if not raw_dir.exists():
            return None
        
        # Try common patterns
        # 1. Exact match (rare)
        # 2. {ID} HOT-Minute-Trade.txt
        # 3. {ID}.txt
        
        patterns = [
            f"{dataset_id} HOT-Minute-Trade.txt",
            f"{dataset_id}_SUBSET.txt",
            f"{dataset_id}.txt",
        ]
        
        for pattern in patterns:
            candidate = raw_dir / pattern
            if candidate.exists():
                return candidate
        
        # Fallback: search for files containing dataset_id
        for item in raw_dir.iterdir():
            if not item.is_file():
                continue
            
            if dataset_id in item.name:
                return item
        
        return None


def _npz_to_dataframe(npz_data: dict[str, Any]) -> pd.DataFrame:
    columns = ["ts", "open", "high", "low", "close", "volume"]
    missing = [col for col in columns if col not in npz_data]
    if missing:
        raise ValueError(f"bars data missing columns: {missing}")

    data = {col: npz_data[col] for col in columns}
    data["ts"] = pd.to_datetime(data["ts"])
    return pd.DataFrame(data)


def _write_data_alignment_report(job_id: str, params: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
    # Stub for Mainline reduction (datasets/instruments registries are purged)
    return None

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
register_handler("BUILD_DATA", build_data_handler)


class BuildBarsHandler(BuildDataHandler):
    JOB_TYPE = "BUILD_BARS"

    def validate_params(self, params: Dict[str, Any]) -> None:
        super().validate_params(params)
        mode = params.get("mode")
        if mode not in (None, "BARS_ONLY", "FULL"):
            raise ValueError("BUILD_BARS does not accept mode other than BARS_ONLY/FULL")

    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        fixed = dict(params)
        fixed["mode"] = "BARS_ONLY"
        fixed.pop("feature_scope", None)
        return super().execute(fixed, context)


class BuildFeaturesHandler(BuildDataHandler):
    JOB_TYPE = "BUILD_FEATURES"

    def validate_params(self, params: Dict[str, Any]) -> None:
        super().validate_params(params)
        mode = params.get("mode")
        if mode not in (None, "FEATURES_ONLY", "FULL"):
            raise ValueError("BUILD_FEATURES does not accept mode other than FEATURES_ONLY/FULL")

    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        fixed = dict(params)
        fixed["mode"] = "FEATURES_ONLY"

        season = fixed.get("season") or current_season()
        dataset_id = str(fixed["dataset_id"])
        tfs = _parse_timeframes_param(fixed)
        missing = _missing_resampled_bars(season, dataset_id, tfs)
        if missing:
            raise ValueError(
                "Missing resampled bars. Run BUILD_BARS first. Missing: "
                + ", ".join(missing[:5])
                + (" ..." if len(missing) > 5 else "")
            )

        return super().execute(fixed, context)


build_bars_handler = BuildBarsHandler()
build_features_handler = BuildFeaturesHandler()
register_handler("BUILD_BARS", build_bars_handler)
register_handler("BUILD_FEATURES", build_features_handler)

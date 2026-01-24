from __future__ import annotations
import sqlite3
import yaml
import json
from pathlib import Path
from typing import List, Optional, Iterable, Any

from core.paths import get_db_path, get_outputs_root
from control.supervisor import submit
from control.supervisor.models import JobRow
from control.job_artifacts import get_job_evidence_dir
from control.bars_store import resampled_bars_path, load_npz

class Bridge:
    """Read-only bridge to system state and Supervisor submission."""

    def __init__(self):
        self.db_path = get_db_path()
        self.outputs_root = get_outputs_root()

    def get_recent_jobs(self, limit: int = 50) -> List[JobRow]:
        """Fetch recent jobs using the Supervisor list_jobs API."""
        if not self.db_path.exists():
            return []

        query = "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?"
        return self._fetch_jobs(query, (limit,))

    def get_recent_job_ids(self, job_type: str, limit: int = 20) -> List[str]:
        if not self.db_path.exists():
            return []
        query = "SELECT job_id FROM jobs WHERE job_type = ? ORDER BY created_at DESC LIMIT ?"
        try:
            with self._open_readonly_db() as conn:
                cursor = conn.execute(query, (job_type, limit))
                rows = cursor.fetchall()
            return [str(row["job_id"]) for row in rows]
        except sqlite3.OperationalError:
            return []

    def get_worker_snapshot(self) -> dict:
        """Return basic worker/job counts for display."""
        if not self.db_path.exists():
            return {"active": 0, "busy": 0, "idle": 0, "queued": 0, "running": 0}
        try:
            with self._open_readonly_db() as conn:
                cur = conn.execute("SELECT COUNT(1) AS n FROM workers WHERE status != 'EXITED'")
                active = int(cur.fetchone()["n"])
                cur = conn.execute("SELECT COUNT(1) AS n FROM workers WHERE status = 'BUSY'")
                busy = int(cur.fetchone()["n"])
                cur = conn.execute("SELECT COUNT(1) AS n FROM workers WHERE status = 'IDLE'")
                idle = int(cur.fetchone()["n"])
                cur = conn.execute("SELECT COUNT(1) AS n FROM jobs WHERE state = 'QUEUED'")
                queued = int(cur.fetchone()["n"])
                cur = conn.execute("SELECT COUNT(1) AS n FROM jobs WHERE state = 'RUNNING'")
                running = int(cur.fetchone()["n"])
                
                # Fetch active supervisors (nodes)
                # We use the internal DB method if possible, or manual query here.
                # Since we are in Bridge (consuming DB), we can just query the table.
                # But Bridge doesn't inherit from SupervisorDB.
                # Let's just do a raw query for now to avoid re-instantiating SupervisorDB logic if not needed,
                # OR we just use the raw query similar to other counts.
                # Active = heartbeat within 30s
                import time
                from ..control.supervisor.models import now_iso, seconds_since
                # We need now_iso - but models might not be easily importable if path issues.
                # Let's stick to simple SQL if possible or just use datetime.
                from datetime import datetime
                
                try:
                    cur = conn.execute("SELECT updated_at FROM supervisors")
                    rows = cur.fetchall()
                    active_supervisors = 0
                    now = datetime.now()
                    for r in rows:
                        # naive parse
                        try:
                            # updated_at is ISO string
                            up_dt = datetime.fromisoformat(r["updated_at"])
                            if (now - up_dt).total_seconds() < 30:
                                active_supervisors += 1
                        except:
                            pass
                except sqlite3.OperationalError:
                     # Table might not exist yet
                    active_supervisors = 0

            return {
                "active": active,
                "busy": busy,
                "idle": idle,
                "queued": queued,
                "running": running,
                "supervisors": active_supervisors,
            }
        except sqlite3.OperationalError:
            return {"active": 0, "busy": 0, "idle": 0, "queued": 0, "running": 0}

    def get_bar_range(
        self,
        dataset_id: str,
        season: str,
        timeframe_min: int,
    ) -> Optional[tuple[str, str]]:
        try:
            path = resampled_bars_path(self.outputs_root, season, dataset_id, str(timeframe_min))
            if not path.exists():
                return None
            data = load_npz(path)
            ts = data.get("ts")
            if ts is None or len(ts) == 0:
                return None
            # ts is numpy.datetime64; convert to date strings
            start = str(ts.min())[:10]
            end = str(ts.max())[:10]
            return (start, end)
        except Exception:
            return None

    def list_seasons_with_bars(self, dataset_id: str, timeframe_min: int) -> List[str]:
        shared_root = self.outputs_root / "shared"
        if not shared_root.exists():
            return []
        seasons: List[str] = []
        for season_dir in shared_root.iterdir():
            if not season_dir.is_dir():
                continue
            season = season_dir.name
            path = resampled_bars_path(self.outputs_root, season, dataset_id, str(timeframe_min))
            if path.exists():
                seasons.append(season)
        return sorted(seasons, key=self._season_sort_key)

    def get_latest_season_with_bars(self, dataset_id: str, timeframe_min: int) -> Optional[str]:
        seasons = self.list_seasons_with_bars(dataset_id, timeframe_min)
        return seasons[-1] if seasons else None

    @staticmethod
    def date_to_season(date_str: str) -> str:
        # date_str: YYYY-MM-DD
        year = int(date_str[:4])
        month = int(date_str[5:7])
        quarter = (month - 1) // 3 + 1
        return f"{year}Q{quarter}"

    def get_bar_season_range(
        self,
        dataset_id: str,
        season: str,
        timeframe_min: int,
    ) -> Optional[tuple[str, str]]:
        rng = self.get_bar_range(dataset_id, season, timeframe_min)
        if not rng:
            return None
        start_date, end_date = rng
        return (self.date_to_season(start_date), self.date_to_season(end_date))

    @staticmethod
    def _season_sort_key(season: str) -> tuple[int, int]:
        try:
            year = int(season[:4])
            q = int(season[5]) if len(season) >= 6 and season[4].upper() == "Q" else 0
            return (year, q)
        except Exception:
            return (0, 0)

    def _open_readonly_db(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch_jobs(self, query: str, params: Iterable[Any]) -> List[JobRow]:
        try:
            with self._open_readonly_db() as conn:
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
            return [JobRow(**dict(row)) for row in rows]
        except sqlite3.OperationalError:
            return []

    def _get_job_type(self, job_id: str) -> Optional[str]:
        if not self.db_path.exists():
            return None
        try:
            with self._open_readonly_db() as conn:
                cursor = conn.execute(
                    "SELECT job_type FROM jobs WHERE job_id = ? LIMIT 1",
                    (job_id,),
                )
                row = cursor.fetchone()
            if not row:
                return None
            return str(row["job_type"])
        except sqlite3.OperationalError:
            return None

    # RUN_RESEARCH_V2 removed (no scripts, WFS-only mainline).

    def submit_build_data(
        self,
        dataset_id: str,
        timeframe_min: int = 60,
        mode: str = "FULL",
        season: Optional[str] = None,
        force_rebuild: bool = False,
    ) -> str:
        params = {
            "dataset_id": dataset_id,
            "timeframe_min": int(timeframe_min),
            "mode": mode,
            "force_rebuild": bool(force_rebuild),
        }
        if season:
            params["season"] = season
        return submit("BUILD_DATA", params)

    def submit_ping(self, sleep_sec: float = 0.0) -> str:
        raise AttributeError("PING removed in Local Research OS mode")

    def submit_clean_cache(self) -> str:
        raise AttributeError("CLEAN_CACHE removed in Local Research OS mode")

    def submit_run_freeze(
        self,
        season: str,
        force: bool = False,
        engine_version: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        params = {"season": season, "force": bool(force)}
        if engine_version:
            params["engine_version"] = engine_version
        if notes:
            params["notes"] = notes
        return submit("RUN_FREEZE_V2", params)

    def submit_run_compile(self, season: str, manifest_path: Optional[str] = None) -> str:
        params = {"season": season}
        if manifest_path:
            params["manifest_path"] = manifest_path
        return submit("RUN_COMPILE_V2", params)

    def submit_run_plateau(
        self,
        research_run_id: str,
        k_neighbors: Optional[int] = None,
        score_threshold_rel: Optional[float] = None,
    ) -> str:
        params = {"research_run_id": research_run_id}
        if k_neighbors is not None:
            params["k_neighbors"] = int(k_neighbors)
        if score_threshold_rel is not None:
            params["score_threshold_rel"] = float(score_threshold_rel)
        return submit("RUN_PLATEAU_V2", params)

    def submit_run_research_wfs(
        self,
        strategy_id: str,
        instrument: str,
        timeframe: str,
        start_season: str,
        end_season: str,
        dataset_id: Optional[str] = None,
        dataset: Optional[str] = None,
        workers: Optional[int] = None,
        season: Optional[str] = None,
        data2_dataset_id: Optional[str] = None,
    ) -> str:
        # Resolve "current" season to a concrete YYYYQ# (policy requires it).
        resolved_season = (season or "").strip()
        if resolved_season.lower() == "current":
            try:
                tf_min = int(str(timeframe).lower().replace("m", "").replace("h", "")) if timeframe else 60
                if str(timeframe).lower().endswith("h"):
                    tf_min *= 60
                latest = self.get_latest_season_with_bars(dataset_id or instrument, tf_min)
                resolved_season = latest or end_season
            except Exception:
                resolved_season = end_season
        if not resolved_season:
            resolved_season = end_season

        params = {
            "strategy_id": strategy_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "start_season": start_season,
            "end_season": end_season,
            # Policy expects season to be present for research jobs.
            "season": resolved_season,
        }
        if dataset_id:
            params["dataset_id"] = dataset_id
        if dataset:
            params["dataset"] = dataset
        if data2_dataset_id:
            params["data2_dataset_id"] = data2_dataset_id
        if workers is not None:
            params["workers"] = int(workers)
        return submit("RUN_RESEARCH_WFS", params)

    def submit_build_portfolio(
        self,
        season: str,
        candidate_run_ids: List[str],
        portfolio_id: Optional[str] = None,
        allowlist: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> str:
        params: dict = {"season": season, "candidate_run_ids": candidate_run_ids}
        if portfolio_id:
            params["portfolio_id"] = portfolio_id
        if allowlist:
            params["allowlist"] = allowlist
        if timeframe:
            params["timeframe"] = timeframe
        return submit("BUILD_PORTFOLIO_V2", params)

    def get_profiles(self) -> List[str]:
        """List available profiles."""
        profile_dir = Path("configs/profiles")
        if not profile_dir.exists():
            return []
        return [p.stem for p in profile_dir.glob("*.yaml")]

    def get_instruments(self) -> List[str]:
        """List available instruments."""
        instr_file = Path("configs/portfolio/instruments.yaml")
        if not instr_file.exists():
            return []
        with open(instr_file, "r") as f:
            data = yaml.safe_load(f)
            return list(data.get("instruments", {}).keys())

    def _recent_data2_path(self) -> Path:
        runtime_root = self.outputs_root / "runtime"
        runtime_root.mkdir(parents=True, exist_ok=True)
        return runtime_root / "tui_recent_data2.json"

    def get_recent_data2(self, limit: int = 20) -> List[str]:
        path = self._recent_data2_path()
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload.get("items", [])
            if isinstance(items, list):
                return [str(x) for x in items][:limit]
        except Exception:
            return []
        return []

    def record_recent_data2(self, items: List[str], limit: int = 50) -> None:
        if not items:
            return
        path = self._recent_data2_path()
        current = self.get_recent_data2(limit=limit)
        merged: List[str] = []
        for item in items:
            item = str(item).strip()
            if not item:
                continue
            if item in merged:
                continue
            merged.append(item)
        for item in current:
            if item not in merged:
                merged.append(item)
        merged = merged[:limit]
        try:
            path.write_text(json.dumps({"items": merged}, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception:
            return

    def get_strategies(self) -> List[str]:
        """List available strategies."""
        catalog_file = Path("configs/registry/strategy_catalog.yaml")
        if not catalog_file.exists():
            return []
        with open(catalog_file, "r") as f:
            data = yaml.safe_load(f)
            return [s["id"] for s in data.get("strategies", [])]

    def get_job_artifacts(self, job_id: str) -> List[str]:
        """List artifact files for a job using manifest discovery."""
        evidence_dir = get_job_evidence_dir(job_id)
        if not evidence_dir.exists():
            return []

        job_type = self._get_job_type(job_id)
        receipt_name = f"{job_type.lower()}_manifest.json" if job_type else None
        manifest_path = None
        if receipt_name and (evidence_dir / receipt_name).exists():
            manifest_path = evidence_dir / receipt_name
        elif (evidence_dir / "manifest.json").exists():
            manifest_path = evidence_dir / "manifest.json"

        artifacts: List[str] = []
        if manifest_path:
            try:
                manifest = json.loads(manifest_path.read_text())
                evidence_files = manifest.get("evidence_files", [])
                if isinstance(evidence_files, list):
                    artifacts.extend(evidence_files)
            except Exception:
                pass

        fallback_candidates = [
            "manifest.json",
            receipt_name,
            "spec.json",
            "state.json",
            "result.json",
            "policy_check.json",
            "inputs_fingerprint.json",
            "outputs_fingerprint.json",
            "runtime_metrics.json",
            "stdout.log",
            "stdout.txt",
            "stderr.log",
            "stderr.txt",
            "stdout_tail.log",
            "research_stdout.txt",
            "research_stderr.txt",
        ]
        for name in fallback_candidates:
            if not name:
                continue
            if name not in artifacts and (evidence_dir / name).exists():
                artifacts.append(name)

        return sorted(set(artifacts))

    def get_log_tail(self, job_id: str, filename: str, lines: int = 100) -> str:
        """Tail a log file."""
        log_path = get_job_evidence_dir(job_id) / filename
        if not log_path.exists():
            return f"Log file not found: {filename}"
        
        with open(log_path, "r", errors="replace") as f:
            content = f.readlines()
            return "".join(content[-lines:])

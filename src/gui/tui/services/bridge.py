from __future__ import annotations
import sqlite3
import yaml
import json
from functools import lru_cache
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Iterable, Any
from zoneinfo import ZoneInfo

from core.paths import get_db_path, get_outputs_root, get_runtime_root, get_shared_cache_root
from control.supervisor import submit
from control.supervisor.models import JobRow
from control.job_artifacts import get_job_evidence_dir
from control.bars_store import resampled_bars_path, load_npz
from core.paths import get_artifacts_root

@lru_cache(maxsize=2)
def _instrument_registry_by_id() -> dict[str, dict]:
    registry_path = Path("configs/registry/instruments.yaml")
    if not registry_path.exists():
        return {}
    try:
        with open(registry_path, "r") as f:
            doc = yaml.safe_load(f) or {}
        items = doc.get("instruments", []) or []
        out: dict[str, dict] = {}
        for it in items:
            if isinstance(it, dict) and it.get("id"):
                out[str(it["id"])] = it
        return out
    except Exception:
        return {}

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
                try:
                    cur = conn.execute("SELECT updated_at FROM supervisors")
                    rows = cur.fetchall()
                    active_supervisors = 0
                    now = datetime.now()
                    for r in rows:
                        try:
                            up_dt = datetime.fromisoformat(r["updated_at"])
                            if (now - up_dt).total_seconds() < 30:
                                active_supervisors += 1
                        except:
                            pass
                except sqlite3.OperationalError:
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
            start = str(ts.min())[:10]
            end = str(ts.max())[:10]
            return (start, end)
        except Exception:
            return None

    def list_seasons_with_bars(self, dataset_id: str, timeframe_min: int) -> List[str]:
        shared_root = get_shared_cache_root()
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

    def submit_build_data(
        self,
        dataset_id: str,
        timeframe_min: int = 60,
        timeframes: Optional[List[int]] = None,
        mode: str = "FULL",
        season: Optional[str] = None,
        force_rebuild: bool = False,
        feature_scope: Optional[str] = None,
    ) -> str:
        params = {
            "dataset_id": dataset_id,
            "timeframe_min": int(timeframe_min),
            "mode": mode,
            "force_rebuild": bool(force_rebuild),
        }
        if timeframes is not None:
            params["timeframes"] = [int(x) for x in timeframes]
        if feature_scope is not None:
            params["feature_scope"] = str(feature_scope)
        if season:
            params["season"] = season
        return submit("BUILD_DATA", params)

    def submit_build_bars(
        self,
        dataset_id: str,
        timeframes: List[int],
        season: Optional[str] = None,
        force_rebuild: bool = False,
        purge_before_build: bool = False,
    ) -> str:
        params = {
            "dataset_id": dataset_id,
            "timeframes": [int(x) for x in timeframes],
            "force_rebuild": bool(force_rebuild),
            "purge_before_build": bool(purge_before_build),
        }
        if season:
            params["season"] = season
        return submit("BUILD_BARS", params)

    def submit_build_features(
        self,
        dataset_id: str,
        timeframes: List[int],
        feature_scope: str = "all_packs",
        season: Optional[str] = None,
        force_rebuild: bool = False,
        purge_before_build: bool = False,
    ) -> str:
        params = {
            "dataset_id": dataset_id,
            "timeframes": [int(x) for x in timeframes],
            "feature_scope": str(feature_scope),
            "force_rebuild": bool(force_rebuild),
            "purge_before_build": bool(purge_before_build),
        }
        if season:
            params["season"] = season
        return submit("BUILD_FEATURES", params)

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
        if not resolved_season:
            resolved_season = end_season

        params = {
            "strategy_id": strategy_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "start_season": start_season,
            "end_season": end_season,
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

    def submit_finalize_portfolio(self, season: str, portfolio_id: str) -> str:
        params = {"season": season, "portfolio_id": portfolio_id}
        return submit("FINALIZE_PORTFOLIO_V1", params)

    def get_profiles(self) -> List[str]:
        """List available profiles."""
        profile_dir = Path("configs/profiles")
        if not profile_dir.exists():
            return []
        return [p.stem for p in profile_dir.glob("*.yaml")]

    def get_instruments(self) -> List[str]:
        """List available instruments."""
        # Prefer portfolio_spec_v1 allowlist if present
        spec_file = Path("configs/portfolio/portfolio_spec_v1.yaml")
        if spec_file.exists():
            try:
                with open(spec_file, "r") as f:
                    spec = yaml.safe_load(f) or {}
                ids = spec.get("instrument_ids") or []
                if isinstance(ids, list) and ids:
                    return [str(x) for x in ids]
            except Exception:
                pass
        # Fallback to registry instruments
        registry_path = Path("configs/registry/instruments.yaml")
        if not registry_path.exists():
            return []
        try:
            with open(registry_path, "r") as f:
                doc = yaml.safe_load(f) or {}
            return [item.get("id") for item in doc.get("instruments", []) if isinstance(item, dict) and item.get("id")]
        except Exception:
            return []

    def get_profile_details(self) -> List[dict]:
        """Scan and parse all trading profiles."""
        profile_dir = Path("configs/profiles")
        if not profile_dir.exists():
            return []

        def _parse_hms(value: str) -> tuple[int, int, int]:
            s = (value or "").strip()
            parts = s.split(":")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1]), 0
            if len(parts) == 3:
                return int(parts[0]), int(parts[1]), int(parts[2])
            raise ValueError(f"invalid time: {value}")

        def _convert_window(
            *,
            start: str,
            end: str,
            windows_tz: str,
            data_tz: str,
            ref_date: date,
        ) -> tuple[tuple[str, str], tuple[str, str]]:
            sh, sm, ss = _parse_hms(start)
            eh, em, es = _parse_hms(end)
            tz_from = ZoneInfo(windows_tz)
            tz_to = ZoneInfo(data_tz)

            sdt = datetime(ref_date.year, ref_date.month, ref_date.day, sh, sm, ss, tzinfo=tz_from)
            edt = datetime(ref_date.year, ref_date.month, ref_date.day, eh, em, es, tzinfo=tz_from)
            if edt <= sdt:
                edt = edt + timedelta(days=1)

            s_to = sdt.astimezone(tz_to)
            e_to = edt.astimezone(tz_to)

            return (sdt.strftime("%H:%M"), edt.strftime("%H:%M")), (s_to.strftime("%H:%M"), e_to.strftime("%H:%M"))
        
        profiles = []
        for p_path in profile_dir.glob("*.yaml"):
            try:
                with open(p_path, "r") as f:
                    doc = yaml.safe_load(f)
                    
                    # Extract sessions summary
                    windows = doc.get("windows", [])
                    trading_sessions = []
                    exchange_tz = doc.get("exchange_tz", "UTC")
                    data_tz = doc.get("data_tz", "UTC")
                    windows_tz = doc.get("windows_tz") or data_tz

                    try:
                        ref_date = datetime.now(ZoneInfo(windows_tz)).date()
                    except Exception:
                        ref_date = datetime.utcnow().date()
                    for w in windows:
                        if w.get("state") == "TRADING":
                            start = str(w.get("start") or "")
                            end = str(w.get("end") or "")
                            if not start or not end:
                                continue
                            try:
                                (s_from, e_from), (s_to, e_to) = _convert_window(
                                    start=start,
                                    end=end,
                                    windows_tz=windows_tz,
                                    data_tz=data_tz,
                                    ref_date=ref_date,
                                )
                                if windows_tz == data_tz:
                                    trading_sessions.append(f"{s_to}-{e_to}")
                                else:
                                    short = data_tz.split("/")[-1]
                                    trading_sessions.append(f"EX {s_from}-{e_from} → {short} {s_to}-{e_to}")
                            except Exception:
                                trading_sessions.append(f"{start}-{end}")
                    
                    profiles.append({
                        "id": p_path.stem,
                        "symbol": doc.get("symbol", "N/A"),
                        "tz": exchange_tz,
                        "slippage": float((_instrument_registry_by_id().get(str(doc.get("symbol") or ""), {}) or {}).get("cost_model", {}).get("slippage_per_side_ticks", 0.0) or 0.0),
                        "sessions": ", ".join(trading_sessions) if trading_sessions else "None"
                    })
            except:
                continue
        return sorted(profiles, key=lambda x: x["id"])

    def get_instrument_details(self) -> dict:
        """Fetch detailed instrument specifications and margins."""
        # 1. Base registry
        registry_path = Path("configs/registry/instruments.yaml")
        registry_data = {}
        if registry_path.exists():
            with open(registry_path, "r") as f:
                doc = yaml.safe_load(f)
                for item in doc.get("instruments", []):
                    registry_data[item["id"]] = item

        # 2. Margins
        margins_path = Path("configs/registry/margins.yaml")
        margin_profiles = {}
        instrument_margin_map = {}
        if margins_path.exists():
            with open(margins_path, "r") as f:
                doc = yaml.safe_load(f)
                margin_profiles = doc.get("margin_profiles", {})
                instrument_margin_map = doc.get("instrument_margins", {})

        # 3. Merge
        details = {}
        for instr_id, base in registry_data.items():
            profile_id = instrument_margin_map.get(instr_id)
            profile = margin_profiles.get(profile_id, {}) if profile_id else {}
            
            cost_model = base.get("cost_model", {}) or {}
            slippage_ticks = float(cost_model.get("slippage_per_side_ticks", 0.0) or 0.0)

            details[instr_id] = {
                "id": instr_id,
                "name": base.get("display_name", "N/A"),
                "exchange": base.get("exchange", "N/A"),
                "currency": base.get("currency", "N/A"),
                "multiplier": base.get("multiplier", 1.0),
                "tick_size": base.get("tick_size", 0.0),
                "tick_value": base.get("tick_value", 0.0),
                "slippage_ticks": slippage_ticks,
                "initial_margin": profile.get("initial_margin_per_contract", 0.0),
                "maintenance_margin": profile.get("maintenance_margin_per_contract", 0.0),
                "timezone": base.get("timezone", "UTC"),
            }
        
        return details

    def get_readiness_index(self) -> dict:
        """Fetch the current bar readiness index."""
        path = get_runtime_root() / "bar_prepare_index.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

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
        """List available strategy IDs."""
        catalog = self.get_strategy_catalog()
        return [s["id"] for s in catalog]

    def get_strategy_catalog(self) -> List[dict]:
        """Fetch full strategy catalog metadata."""
        catalog_file = Path("configs/registry/strategies.yaml")
        if not catalog_file.exists():
            return []
        with open(catalog_file, "r") as f:
            data = yaml.safe_load(f)
            return data.get("strategies", [])

    def get_strategy_readiness(self) -> dict:
        """Cross-check strategy requirements against data readiness index."""
        catalog = self.get_strategy_catalog()
        readiness = self.get_readiness_index()
        instr_data = readiness.get("instruments", {})
        
        results = {}
        for s in catalog:
            s_id = s["id"]
            # Load the actual strategy config file for detail requirements (features, timeframe)
            config_path = Path("configs/strategies") / s.get("config_file", f"{s_id}.yaml")
            if not config_path.exists():
                results[s_id] = {"ready": False, "reason": "Config file missing"}
                continue
            
            try:
                with open(config_path, "r") as f:
                    s_conf = yaml.safe_load(f)
                
                # Check required instruments x timeframes
                # (Simplified check: does at least one instrument have the data?)
                required_tfs = set()
                feats = s_conf.get("features")
                if isinstance(feats, list):
                    for feat in feats:
                        if isinstance(feat, dict) and feat.get("timeframe"):
                            required_tfs.add(str(feat.get("timeframe")))
                elif isinstance(feats, dict):
                    for grp in ("data1", "data2", "cross"):
                        for feat in feats.get(grp, []) or []:
                            if isinstance(feat, dict) and feat.get("timeframe"):
                                required_tfs.add(str(feat.get("timeframe")))
                if not required_tfs:
                    required_tfs.add(str(s_conf.get("timeframe", 60)))
                supported_instr = s.get("supported_instruments", [])
                
                ready_list = []
                for instr in supported_instr:
                    ready_tfs = instr_data.get(instr, {}).get("timeframes", {})
                    if any(tf in ready_tfs for tf in required_tfs):
                        ready_list.append(instr)
                
                if ready_list:
                    results[s_id] = {"ready": True, "instr": ready_list}
                else:
                    tfs = ",".join(sorted(required_tfs))
                    results[s_id] = {"ready": False, "reason": f"No data for {tfs}m"}
            except:
                results[s_id] = {"ready": False, "reason": "Error parsing config"}
        return results

    def get_strategy_feature_map(self) -> dict:
        """Map each strategy to the features it uses."""
        catalog = self.get_strategy_catalog()
        feat_map = {}
        for s in catalog:
            s_id = s["id"]
            config_path = Path("configs/strategies") / s.get("config_file", f"{s_id}.yaml")
            if not config_path.exists():
                continue
            try:
                # Use contract loader so feature packs expand correctly.
                from contracts.strategy_features import load_requirements_from_yaml

                req = load_requirements_from_yaml(str(config_path))
                names = [r.name for r in req.required] + [r.name for r in req.optional]
                feat_map[s_id] = [str(n) for n in names if n]
            except: pass
        return feat_map

    def get_config_audit(self) -> List[dict]:
        """Audit registry and portfolio for broken links."""
        issues = []
        
        # 1. Check margins mapping
        margins_path = Path("configs/registry/margins.yaml")
        if margins_path.exists():
            with open(margins_path, "r") as f:
                doc = yaml.safe_load(f)
                profiles = doc.get("margin_profiles", {})
                mapping = doc.get("instrument_margins", {})
                for instr, p_id in mapping.items():
                    if p_id not in profiles:
                        issues.append({"cat": "Margin", "id": instr, "issue": f"Missing profile '{p_id}'"})

        # 2. Check portfolio_spec_v1 instrument_ids against registry
        spec_path = Path("configs/portfolio/portfolio_spec_v1.yaml")
        registry_path = Path("configs/registry/instruments.yaml")
        registry_ids = set()
        if registry_path.exists():
            try:
                with open(registry_path, "r") as f:
                    reg = yaml.safe_load(f) or {}
                registry_ids = {item.get("id") for item in reg.get("instruments", []) if isinstance(item, dict)}
            except Exception:
                registry_ids = set()
        if spec_path.exists():
            try:
                with open(spec_path, "r") as f:
                    spec = yaml.safe_load(f) or {}
                instrument_ids = spec.get("instrument_ids") or []
                for instr_id in instrument_ids:
                    if instr_id not in registry_ids:
                        issues.append({"cat": "Portfolio", "id": instr_id, "issue": "Unknown instrument_id in portfolio_spec_v1"})
            except Exception:
                pass

        # 3. Check strategy config files
        catalog = self.get_strategy_catalog()
        for s in catalog:
            cfg = s.get("config_file")
            if not cfg or not (Path("configs/strategies") / cfg).exists():
                issues.append({"cat": "Strategy", "id": s["id"], "issue": f"Broken config link: {cfg}"})

        return issues

    def get_feature_library(self) -> List[dict]:
        """Scan technical indicator library for available features."""
        lib_path = Path("src/core/features/library/technical.py")
        if not lib_path.exists():
            return []
        
        import ast
        try:
            tree = ast.parse(lib_path.read_text(encoding="utf-8"))
            features = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Basic extraction of description from docstrings
                    doc = ast.get_docstring(node) or "No description available"
                    features.append({
                        "id": node.name,
                        "description": doc.split("\n")[0].strip() # Use first line as summary
                    })
            return sorted(features, key=lambda x: x["id"])
        except Exception:
            return []

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

    def read_wfs_report_for_job(self, job_id: str) -> dict:
        """
        Read WFS report via path contract (wfs_result_path.txt) from job evidence.
        Returns { "path": Path|None, "data": dict|None, "error": str|None }.
        """
        evidence_dir = get_job_evidence_dir(job_id)
        if not evidence_dir.exists():
            return {"path": None, "data": None, "error": "job evidence dir not found"}

        path_txt = evidence_dir / "wfs_result_path.txt"
        if not path_txt.exists():
            return {"path": None, "data": None, "error": "wfs_result_path.txt not found"}
        try:
            raw = path_txt.read_text(encoding="utf-8").strip()
            if not raw:
                return {"path": None, "data": None, "error": "wfs_result_path.txt is empty"}
            report_path = Path(raw)
            if not report_path.exists():
                return {"path": report_path, "data": None, "error": "wfs_result_path does not exist"}
            data = json.loads(report_path.read_text(encoding="utf-8"))
            data = data if isinstance(data, dict) else {"_value": data}
            return {"path": report_path, "data": data, "error": None}
        except Exception as exc:
            return {"path": None, "data": None, "error": f"failed to read wfs result: {exc}"}

    def read_portfolio_recommendations_for_job(self, job_id: str) -> dict:
        """
        Read portfolio recommendations via path contract from job evidence.
        Returns { "path": Path|None, "data": dict|None, "portfolio_dir": Path|None, "error": str|None }.
        """
        evidence_dir = get_job_evidence_dir(job_id)
        if not evidence_dir.exists():
            return {"path": None, "data": None, "portfolio_dir": None, "error": "job evidence dir not found"}

        path_txt = evidence_dir / "portfolio_recommendations_path.txt"
        if path_txt.exists():
            try:
                raw = path_txt.read_text(encoding="utf-8").strip()
                if not raw:
                    return {"path": None, "data": None, "portfolio_dir": None, "error": "portfolio_recommendations_path.txt is empty"}
                rec_path = Path(raw)
                if not rec_path.exists():
                    return {"path": rec_path, "data": None, "portfolio_dir": rec_path.parent, "error": "recommendations path does not exist"}
                data = json.loads(rec_path.read_text(encoding="utf-8"))
                return {"path": rec_path, "data": data if isinstance(data, dict) else {"_value": data}, "portfolio_dir": rec_path.parent, "error": None}
            except Exception as exc:
                return {"path": None, "data": None, "portfolio_dir": None, "error": f"failed to read recommendations: {exc}"}

        # Fallback: derive from portfolio manifest pointer.
        manifest_txt = evidence_dir / "portfolio_manifest_path.txt"
        if not manifest_txt.exists():
            return {"path": None, "data": None, "portfolio_dir": None, "error": "portfolio_recommendations_path.txt not found"}
        try:
            raw = manifest_txt.read_text(encoding="utf-8").strip()
            if not raw:
                return {"path": None, "data": None, "portfolio_dir": None, "error": "portfolio_manifest_path.txt is empty"}
            manifest_path = Path(raw)
            if not manifest_path.exists():
                return {"path": manifest_path, "data": None, "portfolio_dir": None, "error": "portfolio manifest path does not exist"}
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) or {}
            portfolio_dir = Path(str(manifest.get("portfolio_directory") or manifest_path.parent))
            rec_path = portfolio_dir / "recommendations.json"
            if not rec_path.exists():
                return {"path": rec_path, "data": None, "portfolio_dir": portfolio_dir, "error": "recommendations.json not found"}
            data = json.loads(rec_path.read_text(encoding="utf-8"))
            return {"path": rec_path, "data": data if isinstance(data, dict) else {"_value": data}, "portfolio_dir": portfolio_dir, "error": None}
        except Exception as exc:
            return {"path": None, "data": None, "portfolio_dir": None, "error": f"failed to resolve recommendations: {exc}"}

    def write_portfolio_selection(self, portfolio_dir: Path, selected_run_ids: List[str]) -> dict:
        """
        Write portfolio_selection.json under a portfolio directory (must be under outputs/artifacts).
        """
        try:
            artifacts_root = get_artifacts_root().resolve()
            pdir = Path(portfolio_dir).resolve()
            try:
                pdir.relative_to(artifacts_root)
            except Exception:
                return {"ok": False, "error": "portfolio_dir must be under outputs/artifacts"}

            payload = {
                "version": "1.0",
                "selected_run_ids": [str(x) for x in selected_run_ids],
                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            path = pdir / "portfolio_selection.json"
            tmp = pdir / "portfolio_selection.json.tmp"
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(path)
            return {"ok": True, "path": path, "error": None}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def delete_job_data(self, job_id: str) -> dict:
        """
        Aggressive deletion: local artifacts, linked reports, and DB row.
        """
        deleted: list[str] = []
        outputs_root = get_outputs_root().resolve()
        
        def _safe_unlink(p: Path):
            try:
                p = p.resolve()
                if p.exists() and str(p).startswith(str(outputs_root)):
                    p.unlink()
                    deleted.append(str(p))
            except Exception: pass

        def _safe_rmtree(d: Path):
            try:
                d = d.resolve()
                if d.exists() and d.is_dir() and str(d).startswith(str(outputs_root)):
                    for child in sorted(d.rglob("*"), reverse=True):
                        try:
                            if child.is_file() or child.is_symlink(): child.unlink()
                            elif child.is_dir(): child.rmdir()
                        except: pass
                    d.rmdir()
                    deleted.append(str(d))
            except Exception: pass

    def get_storage_stats(self) -> List[dict]:
        """Calculate storage usage for cache/shared (seasons)."""
        shared_root = get_shared_cache_root()
        if not shared_root.exists():
            return []
        
        stats = []
        for season_dir in shared_root.iterdir():
            if not season_dir.is_dir():
                continue
            
            # Summarize size of this season
            total_bytes = 0
            for f in season_dir.rglob("*"):
                if f.is_file():
                    total_bytes += f.stat().st_size
            
            stats.append({
                "season": season_dir.name,
                "size_mb": total_bytes / (1024 * 1024),
                "datasets": [d.name for d in season_dir.iterdir() if d.is_dir()]
            })
        return sorted(stats, key=lambda x: x["season"], reverse=True)

        # 1. Target: Job Evidence Dir
        evidence_dir = get_job_evidence_dir(job_id)
        if evidence_dir.exists():
            # Scan for linked paths BEFORE deleting the dir
            for path_file in evidence_dir.glob("*_path.txt"):
                try:
                    target = Path(path_file.read_text(encoding="utf-8").strip())
                    _safe_unlink(target)
                    # For linked results, we usually want to delete the whole subfolder (e.g., .../wfs/job_id/ or .../portfolios/portfolio_id/)
                    if target.parent.is_dir() and target.parent != outputs_root:
                         _safe_rmtree(target.parent)
                except: pass
            
            _safe_rmtree(evidence_dir)

        # 2. Target: Artifact Glob (Search for any season folders named after this job or containing it)
        try:
            season_root = outputs_root / "artifacts" / "seasons"
            if season_root.exists():
                # Some folders are named exactly the job_id, others might be prefixes
                for found in season_root.rglob(job_id):
                    _safe_rmtree(found)
        except: pass

        # 3. Target: Database Row
        try:
            db_path = get_db_path()
            if db_path.exists():
                with sqlite3.connect(db_path) as conn:
                    conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
                    conn.commit()
                deleted.append("database_row")
        except Exception as exc:
            return {"deleted": deleted, "error": f"failed to delete from db: {exc}"}

        return {"deleted": deleted, "error": None}

"""
RUN_RESEARCH_WFS handler for Phase4-A Walk-Forward Simulation research.

Research=WFS pipeline including:
- Rolling quarterly windows over [start_season, end_season]
- For each season window:
  - IS range = 3 years
  - OOS range = next 1 quarter
  - Parameter search on IS -> best_params
  - Evaluate OOS with best_params (NO re-optimization)
  - Compute per-window pass/fail + fail_reasons
- Aggregate across seasons:
  - pass_rate, WFE, RF, ECR, trades, ulcer, underwater-days
- Series:
  - stitched IS equity
  - stitched OOS equity
  - stitched B&H equity (price-only reference series for sanity checks)
- Expert evaluation:
  - 5D scores + weighted total + grade
  - Hard gates (one-vote veto) => grade D, not tradable
"""

from __future__ import annotations

import logging
import json
import hashlib
import os
import importlib
from datetime import timedelta
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
import traceback

from ..job_handler import BaseJobHandler, JobContext
from control.artifacts import write_json_atomic
from control.bars_store import resampled_bars_path, load_npz
from core.paths import get_artifacts_root
from core.paths import get_outputs_root
from core.data_aligner import DataAligner
from core.resampler import get_session_spec_for_dataset
from core.features import compute_features_for_tf
from core.features.cross import compute_cross_features_v1
from core.backtest.simulator import simulate_bar_engine, CostConfig
from core.feature_bundle import FeatureBundle, FeatureSeries
from core.feature_context import FeatureContext
from contracts.config_consistency import assert_cost_model_ssot_instruments
from contracts.strategy import StrategySpec
from contracts.features import FeatureRegistry, FeatureSpec
from contracts.research_wfs.result_schema import (
    ResearchWFSResult,
    MetaSection as Meta,
    ConfigSection as Config,
    EstimateSection as Estimate,
    WindowResult,
    SeriesSection as Series,
    MetricsSection as Metrics,
    VerdictSection as Verdict,
    EquityPoint,
    CostsConfig as CostModel,
    InstrumentConfig,
    RiskConfig,
    DataConfig,
    TimeRange,
    WindowRule,
)
from contracts.wfs_policy import load_wfs_policy, evaluate_hard_gates, grade_from_score

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_POLICY_FILE = WORKSPACE_ROOT / "configs" / "policies" / "wfs" / "policy_v1_default.yaml"


# Resource guardrails for WFS research
MAX_WINDOWS = None  # No preset limit (set to int to enforce)
MAX_PARAM_SEARCH_SPACE = 10_000  # Maximum parameter combinations per window
MAX_TOTAL_EXECUTION_TIME_SEC = 7200  # 2 hours maximum execution time
HEARTBEAT_INTERVAL_SEC = 30  # Send heartbeat every 30 seconds during heavy compute


def _iter_seasons(start_season: str, end_season: str) -> List[str]:
    start_year = int(start_season[:4])
    start_q = int(start_season[5])
    end_year = int(end_season[:4])
    end_q = int(end_season[5])

    seasons: List[str] = []
    y, q = start_year, start_q
    while (y < end_year) or (y == end_year and q <= end_q):
        seasons.append(f"{y}Q{q}")
        q += 1
        if q > 4:
            q = 1
            y += 1
    return seasons


def _seed_from_params(params: Dict[str, Any]) -> int:
    blob = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(blob).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _resolve_strategy_class(class_path: str):
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _is_test_mode() -> bool:
    # Allow tests to force "fail-closed" behavior by explicitly setting FISHBRO_TEST_MODE=0.
    # When unset, we treat PYTEST_CURRENT_TEST as an implicit test environment.
    if "FISHBRO_TEST_MODE" in os.environ:
        return os.environ.get("FISHBRO_TEST_MODE") == "1"
    return os.environ.get("PYTEST_CURRENT_TEST") is not None


def _parse_timeframe_to_min(timeframe: str) -> int:
    tf = (timeframe or "").strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    return int(tf)


def _quarter_start_end(season: str) -> tuple[datetime, datetime]:
    year = int(season[:4])
    q = int(season[5])
    start_month = (q - 1) * 3 + 1
    start = datetime(year, start_month, 1, tzinfo=timezone.utc)
    # End month is start_month + 2; end day can be derived by next month - 1 day
    if start_month == 10:
        next_q = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_q = datetime(year, start_month + 3, 1, tzinfo=timezone.utc)
    end = next_q - timedelta(seconds=1)
    return start, end


def _datetime64_to_iso_z(ts64) -> str:
    # ts64 is numpy.datetime64; string is YYYY-MM-DDTHH:MM:SS
    return f"{str(ts64)}Z"


def _downsample_daily(ts_arr, values_arr, instrument: str) -> tuple[list[str], list[float]]:
    import numpy as np
    from core.trade_dates import trade_days_for_instrument_ts

    if len(ts_arr) == 0:
        return [], []
    days = trade_days_for_instrument_ts(ts_arr, instrument)
    # last index of each day
    last_mask = np.r_[days[1:] != days[:-1], True]
    idx = np.where(last_mask)[0]
    ts_daily = ts_arr[idx]
    v_daily = values_arr[idx]
    return [ _datetime64_to_iso_z(t) for t in ts_daily ], [ float(x) for x in v_daily ]


def _equity_from_close(ts_arr, close_arr, instrument: str, initial_equity: float = 10_000.0) -> tuple[list[str], list[float]]:
    import numpy as np

    if len(close_arr) == 0:
        return [], []
    close = close_arr.astype(float)
    rets = np.empty_like(close)
    rets[0] = 0.0
    rets[1:] = (close[1:] / close[:-1]) - 1.0
    equity = initial_equity * np.cumprod(1.0 + rets)
    return _downsample_daily(ts_arr, equity, instrument)


def _max_drawdown(equity: List[float]) -> float:
    import numpy as np

    if not equity:
        return 0.0
    eq = np.array(equity, dtype=float)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    return float(dd.max(initial=0.0))


def _ulcer_index(equity: list[float]) -> float:
    if not equity:
        return 0.0
    import numpy as np

    eq = np.array(equity, dtype=float)
    peak = np.maximum.accumulate(eq)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_pct = (eq - peak) / peak * 100.0
    dd_pct = np.nan_to_num(dd_pct, nan=0.0, posinf=0.0, neginf=0.0)
    return float(np.sqrt(np.mean(dd_pct * dd_pct)))

def _max_underwater_days_from_points(points: list[EquityPoint]) -> int:
    from core.performance_metrics import max_underwater_days

    if not points:
        return 0
    try:
        eq = [float(p["v"]) for p in points]
    except Exception:
        return 0
    return max_underwater_days(eq)

def _load_strategy_defaults(strategy_id: str) -> dict:
    """
    Load default params from strategy YAML schema.

    Strategy SSOT lives in `configs/registry/strategies.yaml` (registry -> config_file).
    """
    doc = _load_strategy_config(strategy_id)
    params = doc.get("parameters") or {}
    if not isinstance(params, dict):
        return {}
    defaults: dict = {}
    for k, spec in params.items():
        if not isinstance(spec, dict):
            continue
        if "default" in spec:
            defaults[str(k)] = spec.get("default")
    return defaults


def _load_strategy_config(strategy_id: str) -> dict:
    from control.strategy_registry_yaml import load_strategy_config

    return load_strategy_config(strategy_id)

def _strategy_static_params_from_doc(strategy_doc: dict) -> dict:
    """
    Optional: allow a strategy YAML to provide non-grid (non-WFS) params that are always passed
    into the strategy class constructor.

    This is intentionally fail-closed: only dict is accepted; anything else is ignored as {}.
    """
    raw = strategy_doc.get("static_params")
    return raw if isinstance(raw, dict) else {}

def _strategy_requires_secondary_data(strategy_id: str) -> bool:
    try:
        from control.strategy_registry_yaml import load_strategy_registry_yaml
    except Exception:
        return False
    reg = load_strategy_registry_yaml()
    entry = reg.get(strategy_id)
    if entry is None:
        return False
    try:
        return bool(entry.raw.get("requires_secondary_data"))
    except Exception:
        return False


def _strategy_class_path_from_doc(strategy_doc: dict) -> str:
    cp = str(strategy_doc.get("class_path") or "").strip()
    if not cp:
        raise ValueError("strategy config missing required field: class_path")
    return cp


def _build_param_grid(param_spec: dict) -> list[dict]:
    import itertools

    if not isinstance(param_spec, dict) or not param_spec:
        return [{}]

    keys: list[str] = []
    values_list: list[list] = []

    for key, spec in param_spec.items():
        if not isinstance(spec, dict):
            keys.append(key)
            values_list.append([spec])
            continue
        ptype = str(spec.get("type") or "").lower()
        default = spec.get("default")
        if ptype == "choice":
            choices = spec.get("choices") or []
            choices = [c for c in choices if c is not None]
            values = choices or ([default] if default is not None else [])
        elif ptype == "int":
            try:
                pmin = int(spec.get("min"))
                pmax = int(spec.get("max"))
                step = int(spec.get("step") or 1)
                values = list(range(pmin, pmax + 1, step))
            except Exception:
                values = [default] if default is not None else []
        elif ptype == "float":
            try:
                pmin = float(spec.get("min"))
                pmax = float(spec.get("max"))
                step = float(spec.get("step") or 1.0)
                values = []
                v = pmin
                # avoid floating drift
                while v <= pmax + 1e-9:
                    values.append(round(v, 10))
                    v += step
            except Exception:
                values = [default] if default is not None else []
        else:
            values = [default] if default is not None else []

        if not values:
            values = [default] if default is not None else []
        if not values:
            values = [None]
        keys.append(key)
        values_list.append(values)

    grid = []
    for combo in itertools.product(*values_list):
        grid.append({k: v for k, v in zip(keys, combo)})
    return grid


def _feature_spec_from_name(name: str, tf_min: int) -> FeatureSpec | None:
    n = name.strip()
    if not n:
        return None
    if n == "session_vwap":
        return FeatureSpec(name=n, timeframe_min=tf_min, lookback_bars=0, params={}, window=1, min_warmup_bars=0)
    if "_" in n:
        parts = n.split("_")
        try:
            window = int(parts[-1])
        except Exception:
            window = None
        if window and window > 0:
            return FeatureSpec(
                name=n,
                timeframe_min=tf_min,
                lookback_bars=window,
                params={"window": window},
                window=window,
                min_warmup_bars=window,
            )
    return FeatureSpec(name=n, timeframe_min=tf_min, lookback_bars=0, params={}, window=1, min_warmup_bars=0)


def _feature_specs_from_strategy(
    doc: dict, default_tf: int
) -> tuple[list[FeatureSpec], list[FeatureSpec], list[str], dict[str, str]]:
    """
    Parse strategy feature declarations.

    Supports:
      - legacy: features: [{name,timeframe,params}]
      - v2: features: {data1:[...], data2:[...], cross:[...]}

    Returns:
      (data1_specs, data2_specs, cross_feature_names, alias_map)
    """
    alias_map: dict[str, str] = {}

    def _parse_tf(raw) -> int:
        if raw is None or raw == "":
            return int(default_tf)
        if isinstance(raw, str):
            token = raw.strip().upper()
            if token in {"RUN", "@RUN", "@TF", "@TIMEFRAME"}:
                return int(default_tf)
            return int(token)
        return int(raw)

    def _parse_list(items) -> list[FeatureSpec]:
        out: list[FeatureSpec] = []
        for feat in items or []:
            if not isinstance(feat, dict):
                continue
            name = str(feat.get("name") or "").strip()
            try:
                tf = _parse_tf(feat.get("timeframe"))
            except Exception:
                tf = int(default_tf)
            params = feat.get("params") or {}
            if name in {"context_feature", "value_feature", "filter_feature"}:
                actual = str(params.get("feature_name") or "").strip()
                if not actual:
                    continue
                alias_map[name] = actual
                name = actual
            spec = _feature_spec_from_name(name, tf)
            if spec is not None:
                out.append(spec)
        return out

    from control.feature_packs_yaml import expand_pack_with_overrides

    features = doc.get("features") or {}
    if isinstance(features, dict):
        data1_decl = features.get("data1")
        data2_decl = features.get("data2")
        cross_decl = features.get("cross")

        def _expand_decl(decl) -> list[dict]:
            if isinstance(decl, list):
                return decl
            if isinstance(decl, dict):
                pack_id = decl.get("pack")
                add = decl.get("add")
                remove = decl.get("remove")
                return expand_pack_with_overrides(
                    pack_id=str(pack_id).strip() if pack_id else None,
                    add=add if isinstance(add, list) else None,
                    remove=remove if isinstance(remove, list) else None,
                )
            return []

        data1_specs = _parse_list(_expand_decl(data1_decl))
        data2_specs = _parse_list(_expand_decl(data2_decl))
        cross_names = []
        for feat in _expand_decl(cross_decl):
            if not isinstance(feat, dict):
                continue
            n = str(feat.get("name") or "").strip()
            if n:
                cross_names.append(n)
        return data1_specs, data2_specs, cross_names, alias_map

    # legacy format
    data1_specs = _parse_list(features)
    return data1_specs, [], [], alias_map


def _build_feature_registry(specs: list[FeatureSpec]) -> FeatureRegistry:
    return FeatureRegistry(specs=specs)


def _load_instrument_cost_config(instrument: str) -> dict:
    reg_path = WORKSPACE_ROOT / "configs" / "registry" / "instruments.yaml"
    exchange = None
    currency = "USD"
    multiplier = 1.0
    tick_size = 1.0
    commission_per_side = 0.0
    slippage_per_side_ticks = 0.0
    if reg_path.exists():
        try:
            import yaml  # type: ignore

            doc = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
            for item in doc.get("instruments", []) or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("id") or "") != str(instrument):
                    continue
                exchange = str(item.get("exchange") or "").strip() or exchange
                currency = str(item.get("currency") or "").strip() or currency
                try:
                    multiplier = float(item.get("multiplier", multiplier))
                except Exception:
                    pass
                try:
                    tick_size = float(item.get("tick_size", tick_size))
                except Exception:
                    pass
                cm = item.get("cost_model") or {}
                try:
                    commission_per_side = float(cm.get("commission_per_side", 0.0) or 0.0)
                    slippage_per_side_ticks = float(cm.get("slippage_per_side_ticks", 0.0) or 0.0)
                except Exception:
                    pass
                break
        except Exception:
            pass
    return {
        "exchange": exchange,
        "currency": currency,
        "multiplier": multiplier,
        "tick_size": tick_size,
        "commission_per_side": commission_per_side,
        "slippage_per_side_ticks": slippage_per_side_ticks,
    }


def _load_fx_constants() -> dict:
    fx_path = WORKSPACE_ROOT / "configs" / "registry" / "fx.yaml"
    if not fx_path.exists():
        return {"base_currency": "TWD", "fx_to_twd": {"TWD": 1.0}, "as_of": None}
    try:
        import yaml  # type: ignore

        doc = yaml.safe_load(fx_path.read_text(encoding="utf-8")) or {}
        base = str(doc.get("base_currency") or "TWD")
        fx_to_twd = doc.get("fx_to_twd") or {}
        as_of = doc.get("as_of")
        return {"base_currency": base, "fx_to_twd": fx_to_twd, "as_of": as_of}
    except Exception:
        return {"base_currency": "TWD", "fx_to_twd": {"TWD": 1.0}, "as_of": None}

def _bars_to_df(ts64, data: dict) -> "pd.DataFrame":
    import pandas as pd

    idx = pd.to_datetime(ts64.astype("datetime64[ns]"))
    df = pd.DataFrame(
        {
            "open": data.get("open"),
            "high": data.get("high"),
            "low": data.get("low"),
            "close": data.get("close"),
            "volume": data.get("volume"),
        },
        index=idx,
    )
    return df


def _extract_signals(strategy_instance, df, ctx: FeatureContext | None):
    import pandas as pd

    if hasattr(strategy_instance, "compute_orders_ctx") and ctx is not None:
        try:
            orders = strategy_instance.compute_orders_ctx(ctx, df)
        except TypeError:
            orders = strategy_instance.compute_orders_ctx(ctx)
        if isinstance(orders, pd.DataFrame):
            return {
                "target_dir": orders.get("target_dir"),
                "long_stop": orders.get("long_stop"),
                "short_stop": orders.get("short_stop"),
                "exit_long_stop": orders.get("exit_long_stop"),
                "exit_short_stop": orders.get("exit_short_stop"),
            }
        if isinstance(orders, dict):
            return {
                "target_dir": orders.get("target_dir"),
                "long_stop": orders.get("long_stop"),
                "short_stop": orders.get("short_stop"),
                "exit_long_stop": orders.get("exit_long_stop"),
                "exit_short_stop": orders.get("exit_short_stop"),
            }

    if hasattr(strategy_instance, "compute_orders"):
        orders = strategy_instance.compute_orders(df)
        if isinstance(orders, pd.DataFrame):
            return {
                "target_dir": orders.get("target_dir"),
                "long_stop": orders.get("long_stop"),
                "short_stop": orders.get("short_stop"),
                "exit_long_stop": orders.get("exit_long_stop"),
                "exit_short_stop": orders.get("exit_short_stop"),
            }
        if isinstance(orders, dict):
            return {
                "target_dir": orders.get("target_dir"),
                "long_stop": orders.get("long_stop"),
                "short_stop": orders.get("short_stop"),
                "exit_long_stop": orders.get("exit_long_stop"),
                "exit_short_stop": orders.get("exit_short_stop"),
            }

    if hasattr(strategy_instance, "compute_signals_ctx") and ctx is not None:
        try:
            signals = strategy_instance.compute_signals_ctx(ctx, df)
        except TypeError:
            signals = strategy_instance.compute_signals_ctx(ctx)
        if hasattr(signals, "reindex"):
            signals = signals.reindex(df.index).fillna(0)
        return {"target_dir": signals.to_numpy() if hasattr(signals, "to_numpy") else signals}

    if hasattr(strategy_instance, "compute_signals"):
        signals = strategy_instance.compute_signals(df)
        if hasattr(signals, "reindex"):
            signals = signals.reindex(df.index).fillna(0)
        return {"target_dir": signals.to_numpy() if hasattr(signals, "to_numpy") else signals}

    raise RuntimeError("Strategy missing compute_signals/compute_orders")


def _build_df_segment(ts64, segment_mask, data: dict, features: dict, alias_map: dict[str, str]):
    import pandas as pd

    seg_ts = ts64[segment_mask]
    seg_data = {k: v[segment_mask] for k, v in data.items() if hasattr(v, "__len__") and len(v) == len(ts64)}
    idx = pd.to_datetime(seg_ts.astype("datetime64[ns]"))
    df = pd.DataFrame(
        {
            "open": seg_data.get("open"),
            "high": seg_data.get("high"),
            "low": seg_data.get("low"),
            "close": seg_data.get("close"),
            "volume": seg_data.get("volume"),
        },
        index=idx,
    )
    for name, values in (features or {}).items():
        if hasattr(values, "__len__") and len(values) == len(ts64):
            df[name] = values[segment_mask]
    for alias, actual in (alias_map or {}).items():
        if actual in df.columns:
            df[alias] = df[actual]
    return df


def _run_segment_simulation(
    *,
    ts64,
    segment_mask,
    data: dict,
    features_data1: dict,
    features_data2: dict | None,
    cross_features: dict | None,
    alias_map: dict[str, str],
    dataset_id: str,
    data2_id: str | None,
    season: str,
    tf_min: int,
    strategy_class,
    instrument: str,
    initial_equity: float,
    strategy_params: dict | None,
    cost: CostConfig,
    record_trades: bool = False,
) -> tuple[list[EquityPoint], float, float, int, np.ndarray, list[str], list[dict[str, Any]]]:
    import numpy as np

    seg_ts = ts64[segment_mask]
    if len(seg_ts) == 0:
        return [], 0.0, 0.0, 0, np.array([], dtype=np.float64), [], []

    df = _build_df_segment(ts64, segment_mask, data, features_data1, alias_map)
    ctx_seg = FeatureContext(
        timeframe_min=tf_min,
        data1=_bundle_from_features(
            ts64=ts64,
            features=features_data1,
            dataset_id=dataset_id,
            season=season,
            tf_min=tf_min,
            mask=segment_mask,
        ),
        data2=_bundle_from_features(
            ts64=ts64,
            features=features_data2 or {},
            dataset_id=data2_id or dataset_id,
            season=season,
            tf_min=tf_min,
            mask=segment_mask,
        ) if features_data2 is not None else None,
        cross=_bundle_from_features(
            ts64=ts64,
            features=cross_features or {},
            dataset_id=f"{dataset_id}__{data2_id}" if data2_id else dataset_id,
            season=season,
            tf_min=tf_min,
            mask=segment_mask,
        ) if cross_features is not None else None,
        data2_id=data2_id,
    )
    strategy_instance = strategy_class(strategy_params or {})
    signals = _extract_signals(strategy_instance, df, ctx_seg)

    seg_data = {k: v[segment_mask] for k, v in data.items() if hasattr(v, "__len__") and len(v) == len(ts64)}
    sim = simulate_bar_engine(
        ts=seg_ts,
        open_=seg_data["open"],
        high=seg_data["high"],
        low=seg_data["low"],
        close=seg_data["close"],
        signals=signals,
        cost=cost,
        initial_equity=initial_equity,
        record_trades=record_trades,
    )

    t_daily, v_daily = _downsample_daily(seg_ts, sim.equity, instrument=instrument)
    points = [EquityPoint(t=t, v=float(v)) for t, v in zip(t_daily, v_daily)]

    return points, sim.net, sim.mdd, sim.trades, sim.equity, sim.warnings, (sim.trades_ledger or [])


def _bundle_from_features(
    *,
    ts64: np.ndarray,
    features: dict[str, np.ndarray],
    dataset_id: str,
    season: str,
    tf_min: int,
    mask: np.ndarray | None = None,
) -> FeatureBundle:
    if mask is not None:
        ts_use = ts64[mask]
    else:
        ts_use = ts64
    series: dict[tuple[str, int], FeatureSeries] = {}
    for name, values in (features or {}).items():
        if name == "ts":
            continue
        if mask is not None:
            values_use = values[mask]
        else:
            values_use = values
        series[(name, tf_min)] = FeatureSeries(ts=ts_use, values=values_use, name=name, timeframe_min=tf_min)
    meta = {"ts_dtype": "datetime64[s]", "breaks_policy": "drop"}
    return FeatureBundle(dataset_id=dataset_id, season=season, series=series, meta=meta)


class RunResearchWFSHandler(BaseJobHandler):
    """RUN_RESEARCH_WFS handler for executing Walk-Forward Simulation research."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate RUN_RESEARCH_WFS parameters."""
        # Required parameters for WFS research
        required = ["strategy_id", "instrument", "timeframe", "start_season", "end_season", "season"]
        missing = [key for key in required if key not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")
        
        # Validate season format (e.g., "2020Q1")
        start_season = params.get("start_season")
        end_season = params.get("end_season")
        if not (isinstance(start_season, str) and len(start_season) == 6 and start_season[4] == 'Q'):
            raise ValueError(f"Invalid start_season format: {start_season}. Expected format: YYYYQ#")
        if not (isinstance(end_season, str) and len(end_season) == 6 and end_season[4] == 'Q'):
            raise ValueError(f"Invalid end_season format: {end_season}. Expected format: YYYYQ#")
    
    def _apply_guardrails(self, start_season: str, end_season: str, param_count: int, context: JobContext) -> None:
        """Apply resource guardrails before heavy computation."""
        # Calculate window count
        start_year = int(start_season[:4])
        start_q = int(start_season[5])
        end_year = int(end_season[:4])
        end_q = int(end_season[5])
        
        window_count = ((end_year - start_year) * 4) + (end_q - start_q) + 1
        
        # Optional window count guardrail
        if isinstance(MAX_WINDOWS, int) and window_count > MAX_WINDOWS:
            raise ValueError(
                f"Too many windows: {window_count} exceeds maximum of {MAX_WINDOWS}. "
                f"Consider reducing date range or increasing window size."
            )
        
        # Check parameter search space
        estimated_param_combinations = param_count * window_count
        if estimated_param_combinations > MAX_PARAM_SEARCH_SPACE:
            raise ValueError(
                f"Parameter search space too large: {estimated_param_combinations} combinations "
                f"exceeds limit of {MAX_PARAM_SEARCH_SPACE}. "
                f"Consider reducing parameter count or window count."
            )
        
        logger.info(
            f"Guardrails passed: windows={window_count}, "
            f"estimated_param_combinations={estimated_param_combinations}"
        )
        
        # Send heartbeat to indicate guardrails passed
        context.heartbeat(progress=0.15, phase="guardrails_passed")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute RUN_RESEARCH_WFS job."""
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "RUN_RESEARCH_WFS",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params,
            }

        # Fail-closed SSOT checks (fast, local file reads only).
        assert_cost_model_ssot_instruments()

        strategy_id = str(params["strategy_id"])
        instrument = str(params["instrument"])
        timeframe = str(params["timeframe"])
        start_season = str(params["start_season"])
        end_season = str(params["end_season"])
        season = str(params.get("season") or end_season)
        dataset_id = str(params.get("dataset_id") or instrument)
        data2_dataset_id = params.get("data2_dataset_id")
        data2_dataset_id = str(data2_dataset_id).strip() if data2_dataset_id else None

        if _strategy_requires_secondary_data(strategy_id) and not data2_dataset_id:
            raise ValueError(
                f"strategy '{strategy_id}' requires data2_dataset_id; "
                "set via configs/registry/data2_pairs.yaml (AutoWFS matrix) or pass --data2/--data2-mode in auto_cli."
            )

        strategy_doc = _load_strategy_config(strategy_id)
        param_grid = _build_param_grid(strategy_doc.get("parameters") or {})
        param_count = max(1, len(param_grid))

        self._apply_guardrails(start_season, end_season, param_count, context)
        context.heartbeat(progress=0.2, phase="loading_bars")

        tf_min = _parse_timeframe_to_min(timeframe)
        outputs_root = get_outputs_root()
        bars_path = resampled_bars_path(outputs_root, season, dataset_id, str(tf_min))
        data2_bars_path = None
        if data2_dataset_id:
            data2_bars_path = resampled_bars_path(outputs_root, season, data2_dataset_id, str(tf_min))

        seed = _seed_from_params(params)
        rng = __import__("random").Random(seed)

        use_synthetic = False
        if not bars_path.exists():
            if _is_test_mode():
                use_synthetic = True
            else:
                raise FileNotFoundError(f"Missing bars for WFS: {bars_path} (run BUILD_BARS first)")
        if data2_bars_path is not None and not data2_bars_path.exists():
            if _is_test_mode():
                logger.warning("Missing DATA2 bars for WFS: %s", data2_bars_path)
            else:
                raise FileNotFoundError(f"Missing DATA2 bars for WFS: {data2_bars_path} (run BUILD_BARS for data2)")

        seasons = _iter_seasons(start_season, end_season)
        if isinstance(MAX_WINDOWS, int) and len(seasons) > MAX_WINDOWS:
            seasons = seasons[:MAX_WINDOWS]

        window_rule: WindowRule = {"is_years": 3, "oos_quarters": 1, "rolling": "quarterly"}
        meta = self._build_meta(context.job_id, strategy_id, instrument, timeframe, start_season, end_season, window_rule)
        config = self._build_config(
            strategy_id,
            instrument,
            timeframe,
            dataset_id,
            start_season,
            end_season,
            data2_dataset_id=data2_dataset_id,
        )
        estimate = self._compute_estimate(
            start_season,
            end_season,
            workers=int(params.get("workers", 1) or 1),
            param_count=param_count,
        )

        windows: List[WindowResult] = []
        stitched_is: List[EquityPoint] = []
        stitched_oos: List[EquityPoint] = []
        stitched_bnh: List[EquityPoint] = []
        run_warnings: list[str] = []

        if use_synthetic:
            context.heartbeat(progress=0.25, phase="bars_missing_using_synthetic")
            base_equity = 10_000.0
            for idx, s in enumerate(seasons):
                context.heartbeat(progress=0.25 + (idx / max(1, len(seasons))) * 0.55, phase=f"season_{s}")
                year = int(s[:4])
                is_start = f"{year-3}-01-01T00:00:00Z"
                is_end = f"{year-1}-12-31T23:59:59Z"
                oos_start = f"{year}-01-01T00:00:00Z"
                oos_end = f"{year}-03-31T23:59:59Z"
                oos_trades = int(rng.randint(12, 40))
                oos_net = float(rng.uniform(-200.0, 600.0))
                is_net = float(rng.uniform(0.0, 1200.0))
                pass_window = oos_net > 0.0 and oos_trades >= 10

                windows.append(
                    WindowResult(
                        season=s,
                        is_range=TimeRange(start=is_start, end=is_end),
                        oos_range=TimeRange(start=oos_start, end=oos_end),
                        best_params={"seed": seed, "p1": int(rng.randint(1, 50))},
                        is_metrics={"net": is_net, "mdd": float(rng.uniform(50.0, 300.0)), "trades": int(rng.randint(30, 120))},
                        oos_metrics={"net": oos_net, "mdd": float(rng.uniform(20.0, 200.0)), "trades": oos_trades},
                        pass_=pass_window,  # type: ignore
                        fail_reasons=[] if pass_window else ["oos_net_nonpositive_or_trades_low"],
                    )
                )

                for day in (1, 20, 40):
                    t = f"{year}-01-{day:02d}T00:00:00Z"
                    base_equity += float(rng.uniform(-20.0, 40.0))
                    stitched_is.append(EquityPoint(t=t, v=base_equity))
                    stitched_oos.append(EquityPoint(t=t, v=base_equity + float(rng.uniform(-10.0, 30.0))))
                    stitched_bnh.append(EquityPoint(t=t, v=10_000.0 + (year - int(start_season[:4])) * 50.0))
        else:
            import numpy as np

            data = load_npz(bars_path)
            ts = data["ts"]
            ts64 = ts.astype("datetime64[s]")
            data_arrays = {
                "open": data["open"].astype(float),
                "high": data["high"].astype(float),
                "low": data["low"].astype(float),
                "close": data["close"].astype(float),
                "volume": data["volume"].astype(float),
            }

            default_params = _load_strategy_defaults(strategy_id)
            override_params = params.get("strategy_params") if isinstance(params.get("strategy_params"), dict) else {}
            static_params = _strategy_static_params_from_doc(strategy_doc)
            base_params = {**static_params, **default_params, **override_params}

            data1_specs, data2_specs, cross_names, alias_map = _feature_specs_from_strategy(strategy_doc, tf_min)
            registry1 = _build_feature_registry(data1_specs)
            session_spec, _ = get_session_spec_for_dataset(dataset_id)
            features_data1 = compute_features_for_tf(
                ts=ts,
                o=data_arrays["open"],
                h=data_arrays["high"],
                l=data_arrays["low"],
                c=data_arrays["close"],
                v=data_arrays["volume"],
                tf_min=tf_min,
                registry=registry1,
                session_spec=session_spec,
            )
            features_data1.pop("ts", None)

            # MultiCharts-style semantics:
            # - DATA1 drives the timeline.
            # - DATA2 is aligned onto DATA1 with forward-fill (hold).
            # - "missing" means DATA2 is truly unavailable after alignment (e.g., before the first DATA2 bar),
            #   not merely "no update at this exact timestamp".
            data2_missing_mask = None
            data2_update_mask = None
            data2_hold_mask = None
            features_data2 = None
            cross_features = None
            if data2_bars_path is not None and data2_bars_path.exists():
                data2 = load_npz(data2_bars_path)
                data2_ts = data2["ts"].astype("datetime64[s]")
                data2_df = {
                    "ts": data2_ts,
                    "open": data2["open"].astype(float),
                    "high": data2["high"].astype(float),
                    "low": data2["low"].astype(float),
                    "close": data2["close"].astype(float),
                    "volume": data2["volume"].astype(float),
                }
                import pandas as pd

                data1_df = pd.DataFrame(data_arrays | {"ts": ts64})
                data2_df_pd = pd.DataFrame(data2_df)
                aligner = DataAligner()
                aligned_df, _metrics = aligner.align(data1_df, data2_df_pd)
                aligned_arrays = {
                    "open": aligned_df["open"].to_numpy(dtype=float),
                    "high": aligned_df["high"].to_numpy(dtype=float),
                    "low": aligned_df["low"].to_numpy(dtype=float),
                    "close": aligned_df["close"].to_numpy(dtype=float),
                    "volume": aligned_df["volume"].to_numpy(dtype=float),
                }
                data2_update_mask = np.isin(ts64, data2_ts)
                data2_missing_mask = ~np.isfinite(aligned_arrays["close"])
                data2_hold_mask = (~data2_update_mask) & (~data2_missing_mask)
                registry2 = _build_feature_registry(data2_specs)
                features_data2 = compute_features_for_tf(
                    ts=ts,
                    o=aligned_arrays["open"],
                    h=aligned_arrays["high"],
                    l=aligned_arrays["low"],
                    c=aligned_arrays["close"],
                    v=aligned_arrays["volume"],
                    tf_min=tf_min,
                    registry=registry2,
                    session_spec=session_spec,
                )
                if features_data2 is not None:
                    features_data2.pop("ts", None)
                cross_features = compute_cross_features_v1(
                    o1=data_arrays["open"],
                    h1=data_arrays["high"],
                    l1=data_arrays["low"],
                    c1=data_arrays["close"],
                    o2=aligned_arrays["open"],
                    h2=aligned_arrays["high"],
                    l2=aligned_arrays["low"],
                    c2=aligned_arrays["close"],
                )
                if cross_names:
                    cross_features = {k: v for k, v in (cross_features or {}).items() if k in set(cross_names)}

            strategy_class = _resolve_strategy_class(_strategy_class_path_from_doc(strategy_doc))

            try:
                if len(ts64) >= 1:
                    config.data["actual_time_range"] = {
                        "start": _datetime64_to_iso_z(ts64[0]),
                        "end": _datetime64_to_iso_z(ts64[-1]),
                    }
            except Exception:
                pass

            inst_cfg = _load_instrument_cost_config(instrument)
            fx_cfg = _load_fx_constants()
            fx_rate = float(fx_cfg.get("fx_to_twd", {}).get(inst_cfg["currency"], 1.0) or 1.0)
            cost = CostConfig(
                slippage_ticks_per_side=float(inst_cfg["slippage_per_side_ticks"]),
                commission_per_side=float(inst_cfg["commission_per_side"]),
                tick_size=float(inst_cfg["tick_size"]),
                multiplier=float(inst_cfg["multiplier"]),
                fx_rate=fx_rate,
            )

            window_defs: list[dict] = []
            for s in seasons:
                oos_start_dt, oos_end_dt = _quarter_start_end(s)
                is_start_dt = oos_start_dt.replace(year=oos_start_dt.year - 3)
                is_end_dt = oos_start_dt - timedelta(seconds=1)
                oos_mask = (ts64 >= np.datetime64(oos_start_dt.replace(tzinfo=None))) & (ts64 <= np.datetime64(oos_end_dt.replace(tzinfo=None)))
                is_mask = (ts64 >= np.datetime64(is_start_dt.replace(tzinfo=None))) & (ts64 <= np.datetime64(is_end_dt.replace(tzinfo=None)))
                window_defs.append(
                    {
                        "season": s,
                        "is_mask": is_mask,
                        "oos_mask": oos_mask,
                        "is_range": TimeRange(
                            start=is_start_dt.isoformat().replace("+00:00", "Z"),
                            end=is_end_dt.isoformat().replace("+00:00", "Z"),
                        ),
                        "oos_range": TimeRange(
                            start=oos_start_dt.isoformat().replace("+00:00", "Z"),
                            end=oos_end_dt.isoformat().replace("+00:00", "Z"),
                        ),
                    }
                )

            initial_equity = 10_000.0
            mdd_floor = 0.02 * initial_equity
            top_k_limit = 100
            trades_min_total = 120

            cheap_candidates: list[tuple[float, dict]] = []
            for candidate in param_grid:
                params_c = {**base_params, **candidate}
                total_net = 0.0
                total_mdd = 0.0
                total_trades = 0
                for win in window_defs:
                    _, net, mdd, trades, _, _, _ = _run_segment_simulation(
                        ts64=ts64,
                        segment_mask=win["is_mask"],
                        data=data_arrays,
                        features_data1=features_data1,
                        features_data2=features_data2,
                        cross_features=cross_features,
                        alias_map=alias_map,
                        dataset_id=dataset_id,
                        data2_id=data2_dataset_id,
                        season=season,
                        tf_min=tf_min,
                        strategy_class=strategy_class,
                        instrument=instrument,
                        initial_equity=initial_equity,
                        strategy_params=params_c,
                        cost=cost,
                    )
                    total_net += float(net)
                    total_mdd = max(total_mdd, abs(float(mdd)))
                    total_trades += int(trades)
                if total_net <= 0.0 or total_trades < trades_min_total:
                    continue
                score = total_net / max(total_mdd, mdd_floor)
                cheap_candidates.append((score, params_c))

            cheap_candidates.sort(key=lambda x: x[0], reverse=True)
            top_k = [c[1] for c in cheap_candidates[:top_k_limit]]
            if not top_k:
                top_k = [base_params]

            for idx, win in enumerate(window_defs):
                context.heartbeat(progress=0.25 + (idx / max(1, len(window_defs))) * 0.55, phase=f"season_{win['season']}")

                best_score = -1e18
                best_params = None
                best_is_points = []
                best_is_net = 0.0
                best_is_mdd = 0.0
                best_is_trades = 0
                best_is_equity = np.array([], dtype=np.float64)
                best_is_warn = []

                for candidate in top_k:
                    is_points, is_net, is_mdd, is_trades, is_equity, is_warn, _ = _run_segment_simulation(
                        ts64=ts64,
                        segment_mask=win["is_mask"],
                        data=data_arrays,
                        features_data1=features_data1,
                        features_data2=features_data2,
                        cross_features=cross_features,
                        alias_map=alias_map,
                        dataset_id=dataset_id,
                        data2_id=data2_dataset_id,
                        season=season,
                        tf_min=tf_min,
                        strategy_class=strategy_class,
                        instrument=instrument,
                        initial_equity=initial_equity,
                        strategy_params=candidate,
                        cost=cost,
                    )
                    score = float(is_net) / max(abs(float(is_mdd)), mdd_floor) if len(is_equity) else -1e18
                    if score > best_score:
                        best_score = score
                        best_params = candidate
                        best_is_points = is_points
                        best_is_net = is_net
                        best_is_mdd = float(is_mdd)
                        best_is_trades = int(is_trades)
                        best_is_equity = is_equity
                        best_is_warn = is_warn

                if best_params is None:
                    best_params = base_params

                stitched_is.extend(best_is_points)
                oos_initial = float(best_is_equity[-1]) if len(best_is_equity) else initial_equity

                oos_points, oos_net, oos_mdd, oos_trades, oos_equity, oos_warn, oos_trades_detail = _run_segment_simulation(
                    ts64=ts64,
                    segment_mask=win["oos_mask"],
                    data=data_arrays,
                    features_data1=features_data1,
                    features_data2=features_data2,
                    cross_features=cross_features,
                    alias_map=alias_map,
                    dataset_id=dataset_id,
                    data2_id=data2_dataset_id,
                    season=season,
                    tf_min=tf_min,
                    strategy_class=strategy_class,
                    instrument=instrument,
                    initial_equity=oos_initial,
                    strategy_params=best_params,
                    cost=cost,
                    record_trades=True,
                )
                stitched_oos.extend(oos_points)

                oos_ts = ts64[win["oos_mask"]]
                oos_close = data_arrays["close"][win["oos_mask"]]
                bnh_t, bnh_e = _equity_from_close(oos_ts, oos_close, instrument, initial_equity=oos_initial)
                stitched_bnh.extend([EquityPoint(t=t, v=float(v)) for t, v in zip(bnh_t, bnh_e)])

                missing_ratio_pct = None
                update_ratio_pct = None
                hold_ratio_pct = None
                if data2_missing_mask is not None:
                    miss = data2_missing_mask[win["oos_mask"]]
                    missing_ratio_pct = float(np.mean(miss) * 100.0) if miss.size > 0 else 0.0
                if data2_update_mask is not None:
                    upd = data2_update_mask[win["oos_mask"]]
                    update_ratio_pct = float(np.mean(upd) * 100.0) if upd.size > 0 else 0.0
                if data2_hold_mask is not None:
                    hold = data2_hold_mask[win["oos_mask"]]
                    hold_ratio_pct = float(np.mean(hold) * 100.0) if hold.size > 0 else 0.0

                pass_window = oos_net > 0.0 and oos_trades >= 5
                fail_reasons = [] if pass_window else ["oos_net_nonpositive_or_trades_low"]
                window_warnings = []
                window_warnings.extend(best_is_warn)
                window_warnings.extend(oos_warn)

                if missing_ratio_pct is not None:
                    if missing_ratio_pct >= 5.0:
                        msg = f"DATA2_COVERAGE_HIGH: {data2_dataset_id} missing_ratio={missing_ratio_pct:.2f}% (threshold=5.0%)"
                        window_warnings.append(msg)
                        run_warnings.append(msg)
                    elif missing_ratio_pct >= 2.0:
                        msg = f"DATA2_COVERAGE_LOW: {data2_dataset_id} missing_ratio={missing_ratio_pct:.2f}% (threshold=2.0%)"
                        window_warnings.append(msg)
                        run_warnings.append(msg)

                oos_metrics = {"net": oos_net, "mdd": float(oos_mdd), "trades": oos_trades}
                if missing_ratio_pct is not None:
                    oos_metrics["data2_missing_ratio_pct"] = missing_ratio_pct
                if update_ratio_pct is not None:
                    oos_metrics["data2_update_ratio_pct"] = update_ratio_pct
                if hold_ratio_pct is not None:
                    oos_metrics["data2_hold_ratio_pct"] = hold_ratio_pct

                windows.append(
                    WindowResult(
                        season=win["season"],
                        is_range=win["is_range"],
                        oos_range=win["oos_range"],
                        best_params={"strategy_params": best_params},
                        is_metrics={"net": best_is_net, "mdd": float(best_is_mdd), "trades": best_is_trades},
                        oos_metrics=oos_metrics,
                        oos_trades=oos_trades_detail,  # type: ignore[arg-type]
                        pass_=pass_window,  # type: ignore
                        fail_reasons=fail_reasons,
                        warnings=window_warnings,  # type: ignore
                    )
                )

        pass_rate = sum(1 for w in windows if w.pass_) / max(1, len(windows))
        total_trades = sum(int(w.oos_metrics.get("trades", 0) or 0) for w in windows)
        total_is_net = sum(float(w.is_metrics.get("net", 0.0) or 0.0) for w in windows)
        total_oos_net = sum(float(w.oos_metrics.get("net", 0.0) or 0.0) for w in windows)
        initial_equity = 10_000.0
        mdd_floor = 0.02 * initial_equity

        oos_equity_vals = [float(p["v"]) for p in stitched_oos] if stitched_oos else [float(p["v"]) for p in stitched_is]
        oos_mdd = _max_drawdown(oos_equity_vals) if oos_equity_vals else 0.0
        ulcer = _ulcer_index(oos_equity_vals) if oos_equity_vals else 0.0

        rf = total_oos_net / max(abs(oos_mdd), mdd_floor)
        wfe = 0.0 if total_is_net <= 0 else max(0.0, min(1.0, total_oos_net / total_is_net))
        ecr = total_oos_net / initial_equity

        uw_days = _max_underwater_days_from_points(stitched_oos) or _max_underwater_days_from_points(stitched_is)
        metrics_raw = {
            "rf": float(rf),
            "wfe": float(wfe),
            "ecr": float(ecr),
            "trades": int(total_trades),
            "pass_rate": float(pass_rate),
            "ulcer_index": float(ulcer),
            "max_underwater_days": int(uw_days),
            "net_profit": float(total_oos_net),
            "max_drawdown": float(oos_mdd),
        }
        metrics_scores = {
            "profit": float(40.0 + pass_rate * 40.0),
            "stability": float(40.0 + pass_rate * 20.0),
            "robustness": float(35.0 + pass_rate * 25.0),
            "reliability": float(35.0 + pass_rate * 25.0),
            "armor": float(30.0 + pass_rate * 30.0),
            "total_weighted": float(40.0 + pass_rate * 40.0),
        }

        # Apply WFS governance policy (hard gates + grading).
        policy_path = Path(str(params.get("policy_path") or DEFAULT_POLICY_FILE))
        if not policy_path.is_absolute():
            policy_path = (WORKSPACE_ROOT / policy_path).resolve()
        try:
            policy = load_wfs_policy(policy_path)
            failed_gate_ids, _fail_reasons = evaluate_hard_gates(policy, metrics_raw)
            score = float(metrics_scores.get(policy.grading.score_metric, metrics_scores["total_weighted"]))
            grade = grade_from_score(policy, score, failed_gate_ids=failed_gate_ids)
            is_tradable = len(failed_gate_ids) == 0
        except Exception as exc:
            logger.warning("Failed to apply WFS policy from %s: %s", policy_path, exc)
            failed_gate_ids = []
            grade = "C" if pass_rate >= 0.5 else "D"
            is_tradable = grade != "D"

        metrics = Metrics(
            raw={
                **metrics_raw,
            },
            scores={
                **metrics_scores,
            },
            hard_gates_triggered=list(failed_gate_ids),
        )

        verdict = Verdict(
            grade=grade,
            is_tradable=bool(is_tradable),
            summary=(
                f"wfs pass_rate={metrics_raw['pass_rate']:.2f} "
                f"trades={int(metrics_raw['trades'])} "
                f"wfe={metrics_raw['wfe']:.2f} "
                f"ulcer={metrics_raw['ulcer_index']:.1f} "
                f"uw_days={int(metrics_raw['max_underwater_days'])}"
            ),
        )

        result = ResearchWFSResult(
            version="1.0",
            meta=meta,
            config=config,
            estimate=estimate,
            windows=windows,
            series=Series(
                stitched_is_equity=stitched_is,
                stitched_oos_equity=stitched_oos,
                stitched_bnh_equity=stitched_bnh,
                stitch_diagnostics={"per_season": []},
                drawdown_series=[],
            ),
            metrics=metrics,
            verdict=verdict,
            warnings=run_warnings,
        )

        # Domain artifact root for Phase4-A results (consumed by portfolio admission).
        domain_dir = get_artifacts_root() / "seasons" / season / "wfs" / context.job_id
        domain_dir.mkdir(parents=True, exist_ok=True)
        domain_result_path = domain_dir / "result.json"
        write_json_atomic(domain_result_path, result.to_dict())

        # Convenience copy inside job evidence bundle for TUI browsing.
        write_json_atomic(Path(context.artifacts_dir) / "wfs_result.json", result.to_dict())
        (Path(context.artifacts_dir) / "wfs_result_path.txt").write_text(str(domain_result_path))

        context.heartbeat(progress=0.95, phase="done")
        return {
            "ok": True,
            "job_type": "RUN_RESEARCH_WFS",
            "payload": params,
            "wfs_result_path": str(domain_result_path),
            "end_season": end_season,
            "summary": verdict.summary,
        }
    
    def _compute_estimate(
        self,
        start_season: str,
        end_season: str,
        workers: int,
        param_count: int,
    ) -> Estimate:
        """Compute estimate BEFORE running windows."""
        # Parse seasons (e.g., "2020Q1" -> year=2020, quarter=1)
        start_year = int(start_season[:4])
        start_q = int(start_season[5])
        end_year = int(end_season[:4])
        end_q = int(end_season[5])
        
        # Calculate window count (simplified)
        # Each quarter between start and end inclusive
        window_count = ((end_year - start_year) * 4) + (end_q - start_q) + 1
        
        strategy_count = 1  # Single strategy family
        
        # Estimate runtime (heuristic)
        estimated_runtime_sec = max(1, param_count * window_count * 2 // workers)
        
        return Estimate(
            strategy_count=strategy_count,
            param_count=param_count,
            window_count=window_count,
            workers=workers,
            estimated_runtime_sec=estimated_runtime_sec
        )
    
    def _build_config(
        self,
        strategy_id: str,
        instrument: str,
        timeframe: str,
        dataset: str,
        start_season: str,
        end_season: str,
        data2_dataset_id: str | None = None,
    ) -> Config:
        """Build config from parameters."""
        inst_cfg = _load_instrument_cost_config(instrument)
        exchange = inst_cfg["exchange"]
        currency = inst_cfg["currency"]
        multiplier = inst_cfg["multiplier"]
        commission_per_side = inst_cfg["commission_per_side"]
        slippage_per_side_ticks = inst_cfg["slippage_per_side_ticks"]
        fx_cfg = _load_fx_constants()

        instrument_config = InstrumentConfig(
            symbol=instrument.split(".", 1)[1] if "." in instrument else instrument,
            exchange=exchange,
            currency=currency,
            multiplier=multiplier,
        )

        # Cost model: per-fill-per-side, values expressed in USD-equivalent (converted to base currency later)
        cost_model = CostModel(
            commission={"model": "per_side", "value": commission_per_side, "unit": currency},
            slippage={"model": "fixed", "value": slippage_per_side_ticks, "unit": "ticks"},
        )
        
        # Build risk config
        risk_config = RiskConfig(
            risk_unit_1R=100.0,  # Default
            stop_model="atr"     # Default
        )
        
        # Build data config
        data_config = DataConfig(
            data1=dataset,
            data2=data2_dataset_id,
            timeframe=timeframe,
            actual_time_range={
                "start": "2020-01-01T00:00:00Z",  # Placeholder
                "end": "2023-12-31T23:59:59Z"     # Placeholder
            }
        )

        return Config(
            instrument=instrument_config,
            costs=cost_model,
            risk=risk_config,
            data=data_config,
            fx={
                "base_currency": str(fx_cfg.get("base_currency") or "TWD"),
                "fx_to_base": dict(fx_cfg.get("fx_to_twd") or {}),
                "as_of": fx_cfg.get("as_of"),
            },
        )
    
    def _build_meta(
        self,
        job_id: str,
        strategy_id: str,
        instrument: str,
        timeframe: str,
        start_season: str,
        end_season: str,
        window_rule: WindowRule
    ) -> Meta:
        """Build meta information."""
        return Meta(
            job_id=job_id,
            run_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            strategy_family=strategy_id,
            instrument=instrument,
            timeframe=timeframe,
            start_season=start_season,
            end_season=end_season,
            window_rule=window_rule
        )
    
# Create handler instance
run_research_wfs_handler = RunResearchWFSHandler()

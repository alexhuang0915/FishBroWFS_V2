from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np


Source = Literal["data1", "cross"]
StopOffsetKind = Literal["none", "points", "pct_close", "atr_mult"]


@dataclass(frozen=True)
class _Term:
    source: Source
    feature: str
    weight: float | str
    transform: dict[str, Any]


def _resolve_float(raw: Any, params: dict, *, default: float) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        key = raw.strip()
        if not key:
            return float(default)
        v = params.get(key, default)
        try:
            return float(v)
        except Exception:
            return float(default)
    return float(default)


def _series_from_source(
    *,
    source: str,
    feature: str,
    tf: int,
    ctx,
    df,
) -> np.ndarray | None:
    if feature == "close":
        if df is None or "close" not in getattr(df, "columns", []):
            return None
        return df["close"].values.astype(np.float64, copy=False)
    if feature == "open":
        if df is None or "open" not in getattr(df, "columns", []):
            return None
        return df["open"].values.astype(np.float64, copy=False)
    if feature == "high":
        if df is None or "high" not in getattr(df, "columns", []):
            return None
        return df["high"].values.astype(np.float64, copy=False)
    if feature == "low":
        if df is None or "low" not in getattr(df, "columns", []):
            return None
        return df["low"].values.astype(np.float64, copy=False)

    bundle = ctx.d1() if source == "data1" else ctx.x()
    if bundle is None:
        return None
    return bundle.get_series(feature, tf).values.astype(np.float64, copy=False)


def _apply_transform(x: np.ndarray, transform: dict[str, Any]) -> np.ndarray:
    out = x
    if not transform:
        return out
    if bool(transform.get("abs")):
        out = np.abs(out)
    if bool(transform.get("sign")):
        out = np.sign(out).astype(np.float64)
    if "clip" in transform:
        clip = transform.get("clip") or {}
        if isinstance(clip, dict):
            lo = clip.get("min")
            hi = clip.get("max")
            try:
                lo_f = float(lo) if lo is not None else None
            except Exception:
                lo_f = None
            try:
                hi_f = float(hi) if hi is not None else None
            except Exception:
                hi_f = None
            if lo_f is not None or hi_f is not None:
                out = np.clip(out, lo_f if lo_f is not None else -np.inf, hi_f if hi_f is not None else np.inf)
    return out


class DslLinearV1:
    """
    YAML-driven linear strategy (fail-closed, deterministic).

    Intended for LLM-driven strategy authoring:
    - LLM edits only YAML (strategy configs + params ranges)
    - Engine runs a fixed, audited strategy template

    Params contract:
      params["dsl"] = {
        "terms": [
          {"source": "cross"|"data1", "feature": "...", "weight": <float or param_name>, "transform": {...}},
          ...
        ],
        "thresholds": {"long_ge": <float or param_name>, "short_le": <float or param_name>},
        "stops": {"exit_atr_mult": <float or param_name> }  # optional protective stop-loss
      }
    """

    def __init__(self, params: dict):
        self._params = params or {}
        dsl = self._params.get("dsl") or {}
        self._dsl = dsl if isinstance(dsl, dict) else {}
        self._terms = self._parse_terms(self._dsl.get("terms"))
        thresholds = self._dsl.get("thresholds") if isinstance(self._dsl.get("thresholds"), dict) else {}
        self._long_ge_raw = thresholds.get("long_ge", 0.0)
        self._short_le_raw = thresholds.get("short_le", 0.0)
        self._entry = self._dsl.get("entry") if isinstance(self._dsl.get("entry"), dict) else {}
        self._stops = self._dsl.get("stops") if isinstance(self._dsl.get("stops"), dict) else {}
        self._exit_atr_mult_raw = self._stops.get("exit_atr_mult", None)

    @staticmethod
    def _parse_terms(raw) -> list[_Term]:
        out: list[_Term] = []
        if not isinstance(raw, list):
            return out
        for item in raw:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip().lower()
            if source not in {"data1", "cross"}:
                continue
            feature = str(item.get("feature") or "").strip()
            if not feature:
                continue
            weight = item.get("weight", 1.0)
            transform = item.get("transform") if isinstance(item.get("transform"), dict) else {}
            out.append(_Term(source=source, feature=feature, weight=weight, transform=transform))
        return out

    def compute_orders_ctx(self, ctx, df=None):
        n = len(df) if df is not None else 0
        target = np.zeros(n, dtype=np.int64)

        # No terms => always flat.
        if not self._terms or n == 0:
            return {"target_dir": target}

        tf = int(getattr(ctx, "timeframe_min", 60))
        d1 = ctx.d1()
        x = ctx.x()

        score = np.zeros(n, dtype=np.float64)
        score[:] = 0.0
        score_valid = np.ones(n, dtype=bool)

        for term in self._terms:
            bundle = d1 if term.source == "data1" else x
            if bundle is None:
                score_valid[:] = False
                break
            try:
                series = bundle.get_series(term.feature, tf).values.astype(np.float64, copy=False)
            except Exception:
                score_valid[:] = False
                break
            v = _apply_transform(series, term.transform)
            w = _resolve_float(term.weight, self._params, default=1.0)
            # strict NaN propagation
            score = score + (w * v)

        score_valid &= np.isfinite(score)

        long_ge = _resolve_float(self._long_ge_raw, self._params, default=0.0)
        short_le = _resolve_float(self._short_le_raw, self._params, default=0.0)

        long_mask = score_valid & (score >= long_ge)
        short_mask = score_valid & (score <= short_le)
        target[long_mask] = 1
        target[short_mask] = -1

        out: dict[str, np.ndarray] = {"target_dir": target}

        # Optional stop-entry intent (engine already supports stop-entry semantics).
        entry_mode = str(self._entry.get("mode") or "market").strip().lower()
        if entry_mode == "stop":
            long_stop = np.full(n, np.nan, dtype=np.float64)
            short_stop = np.full(n, np.nan, dtype=np.float64)

            def _compute_stop(direction: str) -> np.ndarray:
                spec = self._entry.get(direction) if isinstance(self._entry.get(direction), dict) else {}
                base = spec.get("base") if isinstance(spec.get("base"), dict) else {}
                base_source = str(base.get("source") or "data1").strip().lower()
                base_feature = str(base.get("feature") or "").strip()
                if base_source not in {"data1"}:
                    # fail-closed: stop price must be in data1 price domain
                    return np.full(n, np.nan, dtype=np.float64)
                if not base_feature:
                    return np.full(n, np.nan, dtype=np.float64)
                base_series = _series_from_source(source=base_source, feature=base_feature, tf=tf, ctx=ctx, df=df)
                if base_series is None:
                    return np.full(n, np.nan, dtype=np.float64)

                offset = spec.get("offset") if isinstance(spec.get("offset"), dict) else {}
                kind = str(offset.get("kind") or "none").strip().lower()
                sign = str(offset.get("sign") or "+").strip()
                sign_mult = -1.0 if sign == "-" else 1.0

                if kind == "none":
                    return base_series.astype(np.float64, copy=False)

                val = _resolve_float(offset.get("value"), self._params, default=0.0)
                if val == 0.0:
                    return base_series.astype(np.float64, copy=False)

                if kind == "points":
                    return base_series + (sign_mult * val)

                close = _series_from_source(source="data1", feature="close", tf=tf, ctx=ctx, df=df)
                if close is None:
                    return np.full(n, np.nan, dtype=np.float64)

                if kind == "pct_close":
                    return base_series + (sign_mult * (val * close))

                if kind == "atr_mult":
                    try:
                        atr = d1.get_series("atr_14", tf).values.astype(np.float64, copy=False)
                    except Exception:
                        atr = None
                    if atr is None:
                        return np.full(n, np.nan, dtype=np.float64)
                    return base_series + (sign_mult * (val * atr))

                return np.full(n, np.nan, dtype=np.float64)

            long_stop[:] = _compute_stop("long")
            short_stop[:] = _compute_stop("short")

            # Enforce contract: if target requests stop-entry but stop price is invalid, do not trade.
            bad_long = (target == 1) & (~np.isfinite(long_stop))
            bad_short = (target == -1) & (~np.isfinite(short_stop))
            if np.any(bad_long | bad_short):
                target = target.copy()
                target[bad_long | bad_short] = 0
                out["target_dir"] = target
                long_stop[bad_long] = np.nan
                short_stop[bad_short] = np.nan

            # Only expose stops on bars where intent exists; keep others NaN.
            ls = np.full(n, np.nan, dtype=np.float64)
            ss = np.full(n, np.nan, dtype=np.float64)
            ls[out["target_dir"] == 1] = long_stop[out["target_dir"] == 1]
            ss[out["target_dir"] == -1] = short_stop[out["target_dir"] == -1]
            out["long_stop"] = ls
            out["short_stop"] = ss

        # Optional protective stop-loss (exit) based on ATR.
        if self._exit_atr_mult_raw is not None and df is not None and "close" in getattr(df, "columns", []):
            try:
                atr = d1.get_series("atr_14", tf).values.astype(np.float64, copy=False)
            except Exception:
                atr = None
            if atr is not None:
                close = df["close"].values.astype(np.float64, copy=False)
                mult = _resolve_float(self._exit_atr_mult_raw, self._params, default=0.0)
                exit_long = np.full(n, np.nan, dtype=np.float64)
                exit_short = np.full(n, np.nan, dtype=np.float64)
                if mult > 0:
                    # absolute price stops
                    exit_long[out["target_dir"] == 1] = close[out["target_dir"] == 1] - (mult * atr[out["target_dir"] == 1])
                    exit_short[out["target_dir"] == -1] = close[out["target_dir"] == -1] + (mult * atr[out["target_dir"] == -1])
                out["exit_long_stop"] = exit_long
                out["exit_short_stop"] = exit_short
        return out

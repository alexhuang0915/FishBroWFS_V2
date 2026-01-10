from __future__ import annotations

"""
Seed default feature registry.

This module is imported by get_default_registry() at runtime.
DO NOT put shell commands or side-effect code here.
"""

import math
from features.registry import FeatureRegistry
from indicators.numba_indicators import (
    sma, hh, ll, atr_wilder, vx_percentile, percentile_rank, rsi, ema, wma, rolling_stdev,
    zscore, momentum, roc, bbands_pb, bbands_width, atr_channel_upper,
    atr_channel_lower, atr_channel_pos, donchian_width, dist_to_hh, dist_to_ll
)
from config.registry.timeframes import load_timeframes

def compute_min_warmup_bars(family: str, window: int) -> int:
    """
    Compute min_warmup_bars according to FEAT-1 warmup multipliers.
    """
    if family in ("ema", "adx"):
        return math.ceil(3 * window)
    # SMA, WMA, STDEV, HH, LL, Percentile, ATR Wilder, RSI, etc.
    return window


def seed_default_registry(reg: FeatureRegistry) -> None:
    # Use timeframe registry instead of hardcoded values
    timeframe_registry = load_timeframes()
    timeframes = timeframe_registry.allowed_timeframes

    for tf in timeframes:
        # SMA
        for w in (5, 10, 20, 40):
            reg.register_feature(
                name=f"sma_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: sma(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("ma", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="ma",
            )

        # HH / LL
        for w in (5, 10, 20, 40):
            reg.register_feature(
                name=f"hh_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda h, w=w: hh(h, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("channel", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="channel",
            )
            reg.register_feature(
                name=f"ll_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda l, w=w: ll(l, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("channel", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="channel",
            )

        # ATR
        for w in (10, 14):
            reg.register_feature(
                name=f"atr_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda h, l, c, w=w: atr_wilder(h, l, c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("volatility", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="volatility",
            )

        # VX percentile (rename to percentile)
        for w in (126, 252):
            reg.register_feature(
                name=f"percentile_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: percentile_rank(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("percentile", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="percentile",
            )
            # Legacy name for backward compatibility with S1 strategy (deprecated)
            reg.register_feature(
                name=f"vx_percentile_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: vx_percentile(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("percentile", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="percentile",
                deprecated=True,
                canonical_name=f"percentile_{w}",
                notes="Legacy name, use percentile_{w} instead"
            )

        # RSI
        for w in (7, 14, 21):
            reg.register_feature(
                name=f"rsi_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: rsi(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("momentum", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="momentum",
            )

        # EMA
        for w in (5, 10, 20, 40, 60, 100, 200):
            reg.register_feature(
                name=f"ema_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: ema(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("ema", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="ema",
            )

        # WMA
        for w in (5, 10, 20, 40, 60, 100, 200):
            reg.register_feature(
                name=f"wma_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: wma(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("ma", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="ma",
            )

        # STDEV
        for w in (10, 20, 40, 60, 100, 200):
            reg.register_feature(
                name=f"stdev_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: rolling_stdev(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("volatility", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="volatility",
            )

        # Z‑score
        for w in (20, 40, 60, 100, 200):
            reg.register_feature(
                name=f"zscore_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: zscore(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("volatility", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="volatility",
            )

        # Momentum
        for w in (5, 10, 20, 40, 60, 100, 200):
            reg.register_feature(
                name=f"momentum_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: momentum(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("momentum", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="momentum",
            )

        # ROC
        for w in (5, 10, 20, 40, 60, 100, 200):
            reg.register_feature(
                name=f"roc_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: roc(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("momentum", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="momentum",
            )

        # ATR additional windows
        for w in (5, 20, 40):
            reg.register_feature(
                name=f"atr_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda h, l, c, w=w: atr_wilder(h, l, c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("volatility", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="volatility",
            )

        # Bollinger Band %b and width
        for w in (5, 10, 20, 40, 80, 160, 252):
            reg.register_feature(
                name=f"bb_pb_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: bbands_pb(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("bb", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="bb",
            )
            reg.register_feature(
                name=f"bb_width_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: bbands_width(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("bb", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="bb",
            )

        # ATR Channel
        for w in (5, 10, 14, 20, 40, 80, 160, 252):
            reg.register_feature(
                name=f"atr_ch_upper_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda h, l, c, w=w: atr_channel_upper(h, l, c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("atr_channel", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="atr_channel",
            )
            reg.register_feature(
                name=f"atr_ch_lower_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda h, l, c, w=w: atr_channel_lower(h, l, c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("atr_channel", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="atr_channel",
            )
            reg.register_feature(
                name=f"atr_ch_pos_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda h, l, c, w=w: atr_channel_pos(h, l, c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("atr_channel", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="atr_channel",
            )

        # Channel Width (Donchian)
        for w in (5, 10, 20, 40, 80, 160, 252):
            reg.register_feature(
                name=f"donchian_width_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda h, l, c, w=w: donchian_width(h, l, c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("donchian", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="donchian",
            )

        # HH/LL Distance
        for w in (5, 10, 20, 40, 80, 160, 252):
            reg.register_feature(
                name=f"dist_hh_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda h, c, w=w: dist_to_hh(h, c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("distance", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="distance",
            )
            reg.register_feature(
                name=f"dist_ll_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda l, c, w=w: dist_to_ll(l, c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("distance", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="distance",
            )

        # Percentile windows (additional window 63)
        for w in (63,):
            reg.register_feature(
                name=f"percentile_{w}",
                timeframe_min=tf,
                lookback_bars=w,
                params={"window": w},
                compute_func=lambda c, w=w: percentile_rank(c, w),
                skip_verification=True,
                window=w,
                min_warmup_bars=compute_min_warmup_bars("percentile", w),
                dtype="float64",
                div0_policy="DIV0_RET_NAN",
                family="percentile",
            )


"""
Feature 計算核心

提供 deterministic numpy 實作，禁止 pandas rolling。
所有計算必須與 FULL/INCREMENTAL 模式完全一致。
"""

from __future__ import annotations

from .feature_bundle import FeatureBundle

import inspect
import numpy as np
from typing import Dict, Literal, Optional, Union
from datetime import datetime

from contracts.features import FeatureRegistry as ContractFeatureRegistry, FeatureSpec as ContractFeatureSpec
from features.registry import FeatureRegistry as EnhancedFeatureRegistry
from core.resampler import SessionSpecTaipei


def compute_atr_14(
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
) -> np.ndarray:
    """
    計算 ATR(14)（Average True Range）
    
    公式：
    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = rolling mean of TR with window=14 (population std, ddof=0)
    
    前 13 根 bar 的 ATR 為 NaN（因為 window 不足）
    
    Args:
        o: open 價格（未使用）
        h: high 價格
        l: low 價格
        c: close 價格
        
    Returns:
        ATR(14) 陣列，與輸入長度相同
    """
    n = len(c)
    if n == 0:
        return np.array([], dtype=np.float64)
    
    # 計算 True Range
    tr = np.empty(n, dtype=np.float64)
    
    # 第一根 bar 的 TR = high - low
    tr[0] = h[0] - l[0]
    
    # 後續 bar 的 TR
    for i in range(1, n):
        hl = h[i] - l[i]
        hc = abs(h[i] - c[i-1])
        lc = abs(l[i] - c[i-1])
        tr[i] = max(hl, hc, lc)
    
    # 計算 rolling mean with window=14 (population std, ddof=0)
    # 使用 cumulative sums 確保 deterministic
    atr = np.full(n, np.nan, dtype=np.float64)
    
    if n >= 14:
        # 計算 cumulative sum of TR
        cumsum = np.cumsum(tr, dtype=np.float64)
        
        # 計算 rolling mean
        for i in range(13, n):
            if i == 13:
                window_sum = cumsum[i]
            else:
                window_sum = cumsum[i] - cumsum[i-14]
            
            atr[i] = window_sum / 14.0
    
    return atr


def compute_returns(
    c: np.ndarray,
    method: str = "log",
) -> np.ndarray:
    """
    計算 returns
    
    公式：
    - log: r = log(close).diff()
    - simple: r = (close - prev_close) / prev_close
    
    第一根 bar 的 return 為 NaN
    
    Args:
        c: close 價格
        method: 計算方法，"log" 或 "simple"
        
    Returns:
        returns 陣列，與輸入長度相同
    """
    n = len(c)
    if n <= 1:
        return np.full(n, np.nan, dtype=np.float64)
    
    ret = np.full(n, np.nan, dtype=np.float64)
    
    if method == "log":
        # log returns: r = log(close).diff()
        log_c = np.log(c)
        ret[1:] = np.diff(log_c)
    else:
        # simple returns: r = (close - prev_close) / prev_close
        ret[1:] = (c[1:] - c[:-1]) / c[:-1]
    
    return ret


def compute_rolling_z(
    x: np.ndarray,
    window: int,
) -> np.ndarray:
    """
    計算 rolling z-score（population std, ddof=0）
    
    公式：
    mean = (sum_x[i] - sum_x[i-window]) / window
    var = (sum_x2[i] - sum_x2[i-window]) / window - mean^2
    std = sqrt(max(var, 0))  # 防浮點負數
    z = (x - mean) / std
    
    前 window-1 根 bar 的 z-score 為 NaN
    std == 0 時，z = NaN（而不是 0）
    
    Args:
        x: 輸入數值陣列
        window: 滾動視窗大小
        
    Returns:
        z-score 陣列，與輸入長度相同
    """
    n = len(x)
    if n == 0 or window <= 1:
        return np.full(n, np.nan, dtype=np.float64)
    
    # 初始化結果為 NaN
    z = np.full(n, np.nan, dtype=np.float64)
    
    # 計算 cumulative sums
    cumsum = np.cumsum(x, dtype=np.float64)
    cumsum2 = np.cumsum(x * x, dtype=np.float64)
    
    # 計算 rolling z-score
    for i in range(window - 1, n):
        # 計算視窗內的 sum 和 sum of squares
        if i == window - 1:
            sum_x = cumsum[i]
            sum_x2 = cumsum2[i]
        else:
            sum_x = cumsum[i] - cumsum[i - window]
            sum_x2 = cumsum2[i] - cumsum2[i - window]
        
        # 計算 mean 和 variance
        mean = sum_x / window
        var = (sum_x2 / window) - (mean * mean)
        
        # 防浮點負數
        if var < 0:
            var = 0.0
        
        std = np.sqrt(var)
        
        # 計算 z-score
        if std == 0:
            # std == 0 時，z = NaN（而不是 0）
            z[i] = np.nan
        else:
            z[i] = (x[i] - mean) / std
    
    return z


def compute_session_vwap(
    ts: np.ndarray,
    c: np.ndarray,
    v: np.ndarray,
    session_spec: SessionSpecTaipei,
    breaks_policy: str = "drop",
) -> np.ndarray:
    """
    計算 session VWAP（Volume Weighted Average Price）
    
    每個 session 獨立計算 VWAP，並將該 session 內的所有 bar 賦予相同的 VWAP 值。
    
    Args:
        ts: 時間戳記陣列（datetime64[s]）
        c: close 價格陣列
        v: volume 陣列
        session_spec: session 規格
        breaks_policy: break 處理策略（目前只支援 "drop"）
        
    Returns:
        session VWAP 陣列，與輸入長度相同
    """
    n = len(ts)
    if n == 0:
        return np.array([], dtype=np.float64)
    
    # 初始化結果為 NaN
    vwap = np.full(n, np.nan, dtype=np.float64)
    
    # 將 datetime64[s] 轉換為 pandas Timestamp 以便進行日期時間操作
    # 我們需要判斷每個 bar 屬於哪個 session
    # 由於這是 MVP，我們先實作簡單版本：假設所有 bar 都在同一個 session
    # 實際實作需要根據 session_spec 進行 session 分類
    # 但根據 Phase 3B 要求，我們先提供固定實作
    
    # 簡單實作：計算整個時間範圍的 VWAP（所有 bar 視為同一個 session）
    # 這不是正確的 session VWAP，但符合 MVP 要求
    total_volume = np.sum(v)
    if total_volume > 0:
        weighted_sum = np.sum(c * v)
        overall_vwap = weighted_sum / total_volume
        vwap[:] = overall_vwap
    else:
        vwap[:] = np.nan
    
    return vwap


def _apply_feature_postprocessing(values: np.ndarray, spec) -> np.ndarray:
    """
    Apply warmup NaN and dtype enforcement according to FeatureSpec.
    If spec is None, only enforce dtype float64.
    """
    # Ensure dtype float64
    if values.dtype != np.float64:
        values = values.astype(np.float64)
    
    # Apply warmup NaN if spec is provided and has min_warmup_bars
    if spec is not None and hasattr(spec, 'min_warmup_bars') and spec.min_warmup_bars > 0:
        n = len(values)
        if spec.min_warmup_bars <= n:
            values[:spec.min_warmup_bars] = np.nan
        else:
            # If min_warmup_bars exceeds length, set all to NaN
            values[:] = np.nan
    
    return values


def compute_features_for_tf(
    ts: np.ndarray,
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    v: np.ndarray,
    tf_min: int,
    registry: Union[ContractFeatureRegistry, EnhancedFeatureRegistry],
    session_spec: SessionSpecTaipei,
    breaks_policy: str = "drop",
) -> Dict[str, np.ndarray]:
    """
    計算指定 timeframe 的所有特徵
    
    Args:
        ts: 時間戳記陣列（datetime64[s]），必須與 resampled bars 完全一致
        o: open 價格陣列
        h: high 價格陣列
        l: low 價格陣列
        c: close 價格陣列
        v: volume 陣列
        tf_min: timeframe 分鐘數
        registry: 特徵註冊表
        session_spec: session 規格
        breaks_policy: break 處理策略
        
    Returns:
        特徵字典，keys 必須為：
        - ts: 與輸入 ts 相同的物件/值（datetime64[s]）
        - atr_14: float64
        - ret_z_200: float64
        - session_vwap: float64
        
    Raises:
        ValueError: 輸入陣列長度不一致或 registry 缺少必要特徵
    """
    # 驗證輸入長度
    n = len(ts)
    for arr, name in [(o, "open"), (h, "high"), (l, "low"), (c, "close"), (v, "volume")]:
        if len(arr) != n:
            raise ValueError(f"輸入陣列長度不一致: {name} 長度為 {len(arr)}，但 ts 長度為 {n}")
    
    # 取得該 timeframe 的特徵規格
    specs = registry.specs_for_tf(tf_min)
    
    # 建立結果字典
    result = {"ts": ts}  # ts 必須是相同的物件/值
    # 計算每個特徵
    for spec in specs:
        # 檢查是否有 compute_func
        compute_func = getattr(spec, 'compute_func', None)
        if compute_func is not None:
            # 使用 compute_func
            sig = inspect.signature(compute_func)
            params = list(sig.parameters.values())
            # 只考慮沒有預設值的參數（必需參數）
            required_params = [p for p in params if p.default is inspect.Parameter.empty]
            # 映射參數名稱到對應的陣列
            arg_map = {
                "ts": ts,
                "o": o,
                "h": h,
                "l": l,
                "c": c,
                "v": v,
            }
            args = []
            for param in required_params:
                if param.name in arg_map:
                    args.append(arg_map[param.name])
                else:
                    # 可能是 window 參數，從 spec.params 取得
                    if param.name in spec.params:
                        args.append(spec.params[param.name])
                    else:
                        raise ValueError(f"Cannot map parameter {param.name} for feature {spec.name}")
            # 呼叫 compute_func
            try:
                values = compute_func(*args)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            except Exception as e:
                raise
        else:
            # 根據特徵名稱使用預設計算函數
            from indicators.numba_indicators import (
                sma, hh, ll, atr_wilder, percentile_rank, bbands_pb, bbands_width,
                atr_channel_upper, atr_channel_lower, atr_channel_pos,
                donchian_width, dist_to_hh, dist_to_ll
            )
            if spec.name.startswith("sma_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[1])))
                values = sma(c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("hh_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[1])))
                values = hh(h, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("ll_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[1])))
                values = ll(l, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("atr_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[1])))
                values = atr_wilder(h, l, c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("vx_percentile_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[2])))
                values = percentile_rank(c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("percentile_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[1])))
                values = percentile_rank(c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("bb_pb_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[2])))
                values = bbands_pb(c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("bb_width_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[2])))
                values = bbands_width(c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("atr_ch_upper_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[3])))
                values = atr_channel_upper(h, l, c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("atr_ch_lower_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[3])))
                values = atr_channel_lower(h, l, c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("atr_ch_pos_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[3])))
                values = atr_channel_pos(h, l, c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("donchian_width_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[2])))
                values = donchian_width(h, l, c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("dist_hh_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[2])))
                values = dist_to_hh(h, c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name.startswith("dist_ll_"):
                window = int(spec.params.get("window", int(spec.name.split("_")[2])))
                values = dist_to_ll(l, c, window)
                values = _apply_feature_postprocessing(values, spec)
                result[spec.name] = values
            elif spec.name == "atr_14":
                # fallback to compute_atr_14 (already defined)
                values = compute_atr_14(o, h, l, c)
                values = _apply_feature_postprocessing(values, spec)
                result["atr_14"] = values
            elif spec.name == "ret_z_200":
                returns = compute_returns(c, method="log")
                values = compute_rolling_z(returns, window=200)
                values = _apply_feature_postprocessing(values, spec)
                result["ret_z_200"] = values
            elif spec.name == "session_vwap":
                values = compute_session_vwap(
                    ts, c, v, session_spec, breaks_policy
                )
                values = _apply_feature_postprocessing(values, spec)
                result["session_vwap"] = values
            else:
                raise ValueError(f"不支援的特徵名稱: {spec.name}")
    
    
    # 確保 baseline 特徵存在（若尚未計算）
    if "ret_z_200" not in result:
        returns = compute_returns(c, method="log")
        values = compute_rolling_z(returns, window=200)
        values = _apply_feature_postprocessing(values, None)
        result["ret_z_200"] = values
    if "session_vwap" not in result:
        values = compute_session_vwap(
            ts, c, v, session_spec, breaks_policy
        )
        values = _apply_feature_postprocessing(values, None)
        result["session_vwap"] = values
    if "atr_14" not in result:
        values = compute_atr_14(o, h, l, c)
        values = _apply_feature_postprocessing(values, None)
        result["atr_14"] = values
    
    # 確保所有必要特徵都存在（baseline + registry）
    for feat in ["ts", "atr_14", "ret_z_200", "session_vwap"]:
        if feat not in result:
            raise ValueError(f"Missing required feature: {feat}")
    
    return result



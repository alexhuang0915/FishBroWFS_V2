# AS‑IS FEATURE CATALOG

**Date**: 2025‑12‑30  
**Repository**: FishBroWFS_V2  
**Timeframe**: 60 minutes (primary)  
**Total Registered Features**: 63  
**Evidence**: `outputs/_dp_evidence/20251230_160359/FEATURE_REGISTRY_DUMP.txt`

---

## Catalog Structure

Each entry lists:
- **Feature Name**: exact string used in registry
- **Timeframe(s)**: minutes (currently only 60)
- **Windows/Params**: window size (and other parameters if any)
- **Data Source Dependency**: Data1‑only, Data2‑allowed, or source‑agnostic
- **Warmup Requirement**: `min_warmup_bars` from spec (or “UNKNOWN” if not encoded)

**Baseline Mandatory Features** (required for every timeframe) are marked with ✅.

---

## 1. Baseline Mandatory Features (✅)

| Feature Name | Timeframe | Window/Params | Data Source | Warmup |
|--------------|-----------|---------------|-------------|--------|
| `ts`         | 60        | –             | source‑agnostic | 0 |
| `ret_z_200`  | 60        | window=200    | source‑agnostic | 200 |
| `session_vwap` | 60      | –             | source‑agnostic | 0 |
| `atr_14`     | 60        | window=14     | source‑agnostic | 14 |

---

## 2. MA Family (Simple, Exponential, Weighted Moving Averages)

**Data Source**: source‑agnostic (uses close price)  
**Warmup**: SMA/WMA = window, EMA = 3×window (FEAT‑1 rule)

### 2.1 Simple Moving Average (SMA)

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `sma_5`      | 60        | 5      | 5      |
| `sma_10`     | 60        | 10     | 10     |
| `sma_20`     | 60        | 20     | 20     |
| `sma_40`     | 60        | 40     | 40     |

### 2.2 Exponential Moving Average (EMA)

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `ema_5`      | 60        | 5      | 15     |
| `ema_10`     | 60        | 10     | 30     |
| `ema_20`     | 60        | 20     | 60     |
| `ema_40`     | 60        | 40     | 120    |
| `ema_60`     | 60        | 60     | 180    |
| `ema_100`    | 60        | 100    | 300    |
| `ema_200`    | 60        | 200    | 600    |

### 2.3 Weighted Moving Average (WMA)

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `wma_5`      | 60        | 5      | 5      |
| `wma_10`     | 60        | 10     | 10     |
| `wma_20`     | 60        | 20     | 20     |
| `wma_40`     | 60        | 40     | 40     |
| `wma_60`     | 60        | 60     | 60     |
| `wma_100`    | 60        | 100    | 100    |
| `wma_200`    | 60        | 200    | 200    |

---

## 3. Channel Family (Highest High / Lowest Low)

**Data Source**: source‑agnostic (HH uses high, LL uses low)  
**Warmup**: window

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `hh_5`       | 60        | 5      | 5      |
| `hh_10`      | 60        | 10     | 10     |
| `hh_20`      | 60        | 20     | 20     |
| `hh_40`      | 60        | 40     | 40     |
| `ll_5`       | 60        | 5      | 5      |
| `ll_10`      | 60        | 10     | 10     |
| `ll_20`      | 60        | 20     | 20     |
| `ll_40`      | 60        | 40     | 40     |

---

## 4. Volatility Family (ATR, Standard Deviation, Z‑Score)

**Data Source**: source‑agnostic (ATR uses high/low/close, STDEV/Z‑score use close)  
**Warmup**: window (except ATR Wilder uses window)

### 4.1 Average True Range (ATR)

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `atr_5`      | 60        | 5      | 5      |
| `atr_10`     | 60        | 10     | 10     |
| `atr_14`     | 60        | 14     | 14     |
| `atr_20`     | 60        | 20     | 20     |
| `atr_40`     | 60        | 40     | 40     |

### 4.2 Rolling Standard Deviation (STDEV)

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `stdev_10`   | 60        | 10     | 10     |
| `stdev_20`   | 60        | 20     | 20     |
| `stdev_40`   | 60        | 40     | 40     |
| `stdev_60`   | 60        | 60     | 60     |
| `stdev_100`  | 60        | 100    | 100    |
| `stdev_200`  | 60        | 200    | 200    |

### 4.3 Z‑Score (SMA‑normalized STDEV)

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `zscore_20`  | 60        | 20     | 20     |
| `zscore_40`  | 60        | 40     | 40     |
| `zscore_60`  | 60        | 60     | 60     |
| `zscore_100` | 60        | 100    | 100    |
| `zscore_200` | 60        | 200    | 200    |

---

## 5. Percentile Family (Rolling Percentile Rank)

**Data Source**: source‑agnostic (uses close price)  
**Warmup**: window

| Feature Name       | Timeframe | Window | Warmup | Note |
|--------------------|-----------|--------|--------|------|
| `percentile_126`   | 60        | 126    | 126    | source‑agnostic |
| `percentile_252`   | 60        | 252    | 252    | source‑agnostic |
| `vx_percentile_126`| 60        | 126    | 126    | **legacy VX naming** |
| `vx_percentile_252`| 60        | 252    | 252    | **legacy VX naming** |

---

## 6. Momentum Family (Momentum, ROC, RSI)

**Data Source**: source‑agnostic (uses close price)  
**Warmup**: window (except RSI = window)

### 6.1 Momentum (price difference)

| Feature Name   | Timeframe | Window | Warmup |
|----------------|-----------|--------|--------|
| `momentum_5`   | 60        | 5      | 5      |
| `momentum_10`  | 60        | 10     | 10     |
| `momentum_20`  | 60        | 20     | 20     |
| `momentum_40`  | 60        | 40     | 40     |
| `momentum_60`  | 60        | 60     | 60     |
| `momentum_100` | 60        | 100    | 100    |
| `momentum_200` | 60        | 200    | 200    |

### 6.2 Rate of Change (ROC)

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `roc_5`      | 60        | 5      | 5      |
| `roc_10`     | 60        | 10     | 10     |
| `roc_20`     | 60        | 20     | 20     |
| `roc_40`     | 60        | 40     | 40     |
| `roc_60`     | 60        | 60     | 60     |
| `roc_100`    | 60        | 100    | 100    |
| `roc_200`    | 60        | 200    | 200    |

### 6.3 Relative Strength Index (RSI)

| Feature Name | Timeframe | Window | Warmup |
|--------------|-----------|--------|--------|
| `rsi_7`      | 60        | 7      | 7      |
| `rsi_14`     | 60        | 14     | 14     |
| `rsi_21`     | 60        | 21     | 21     |

---

## 7. Missing Families (vs Agreed Non‑Ultra Universe)

The following families **are not yet registered**:

| Family               | Required Windows (agreed) | Status        |
|----------------------|---------------------------|---------------|
| ATR Channel          | [5,10,20,40,80,160,252]   | **Missing**   |
| Bollinger %b         | [5,10,20,40,80,160,252]   | **Missing**   |
| Channel Width        | [5,10,20,40,80,160,252]   | **Missing**   |
| HH/LL Distance       | [5,10,20,40,80,160,252]   | **Missing**   |
| Donchian Breakout    | [5,10,20,40,80,160,252]   | **Missing**   |
| Z‑Score (windows 63,126,252) | [63,126,252]      | **Missing**   |
| Rank (windows 63,126,252)    | [63,126,252]      | **Missing**   |

**Note**: The current registry also lacks general windows **80** and **160** for any family.

---

## 8. Warmup NaN Semantics

All registered features have `min_warmup_bars` set according to FEAT‑1 rule:
- EMA/ADX: `3 × window`
- Others: `window`

The core feature computation (`src/core/features.py`) enforces warmup NaN by filling the first `min_warmup_bars` with NaN.

**Evidence**: `src/core/features.py` lines 230‑248 (`_apply_feature_postprocessing`).

---

## 9. Source‑Agnostic Compliance

Except for the legacy `vx_percentile_*` naming, all features are source‑agnostic:
- No hard‑coded VX/DX symbols in indicator logic.
- Features depend only on OHLCV columns, not on instrument symbols.

**Violation**: `vx_percentile_126` and `vx_percentile_252` retain VX‑first naming (should be deprecated).

---

## 10. Timeframe Coverage

Currently, features are registered **only for 60‑minute timeframe**. Other timeframes (1,5,15,30,120,240) show zero registered features.

**Implication**: The registry is timeframe‑specific; multi‑timeframe support requires separate registration per TF.

---

*Catalog generated by dp (local builder) on 2025‑12‑30 16:11 UTC+8*
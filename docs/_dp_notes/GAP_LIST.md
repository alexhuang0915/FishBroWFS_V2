# GAP LIST – Missing Feature Expansions vs Agreed Non‑Ultra Universe

**Date**: 2025‑12‑30  
**Repository**: FishBroWFS_V2  
**Commit**: `0e20c8f63de870145787e6a2cf3e1380f4ed164c`  
**Based on**: AS‑IS verification (see `AS_IS_STATUS_REPORT.md` and `AS_IS_FEATURE_CATALOG.md`)

---

## 1. Summary

The current feature bank contains **63 registered features** for TF=60, covering MA, Channel, Volatility, Percentile, and Momentum families. However, compared to the **agreed non‑ultra universe**, the following expansions are missing:

1. **Missing families** (ATR channel, Bollinger %b, channel width, HH/LL distance, Donchian breakout).
2. **Missing windows** (80, 160 for general families; 63 for stat windows).
3. **Missing Z‑score / rank windows** (63,126,252).
4. **Legacy VX‑first naming** (`vx_percentile_*`).

This document lists each gap with concrete feature names and provides a **minimal plan for the next implementation wave** (15–30 features).

---

## 2. Missing Feature Families

### 2.1 ATR Channel (Keltner‑like)

**Description**: Channel formed by ATR‑based bands around a moving average.  
**Formula**: `upper = MA + multiplier × ATR`, `lower = MA - multiplier × ATR`.  
**Required windows**: `[5,10,20,40,80,160,252]` (general windows).  
**Missing features** (example naming):
- `atr_channel_upper_5`, `atr_channel_lower_5`
- `atr_channel_upper_10`, `atr_channel_lower_10`
- … (14 features total for two sides × 7 windows)

**Priority**: High (commonly used channel indicator).

### 2.2 Bollinger %b

**Description**: Percentile position of price within Bollinger Bands.  
**Formula**: `%b = (price - lower_band) / (upper_band - lower_band)`.  
**Required windows**: `[5,10,20,40,80,160,252]`.  
**Missing features**:
- `bb_pb_5`, `bb_pb_10`, `bb_pb_20`, `bb_pb_40`, `bb_pb_80`, `bb_pb_160`, `bb_pb_252`

**Priority**: High (standard volatility‑normalized oscillator).

### 2.3 Channel Width

**Description**: Difference between HH and LL (channel width).  
**Formula**: `width = hh - ll`.  
**Required windows**: `[5,10,20,40,80,160,252]`.  
**Missing features**:
- `channel_width_5`, `channel_width_10`, …, `channel_width_252`

**Priority**: Medium (derived from existing HH/LL).

### 2.4 HH/LL Distance

**Description**: Distance from current price to HH (or LL).  
**Formula**: `dist_to_hh = (hh - price) / price`, `dist_to_ll = (price - ll) / price`.  
**Required windows**: same as HH/LL windows.  
**Missing features** (two series):
- `dist_to_hh_5`, `dist_to_hh_10`, …
- `dist_to_ll_5`, `dist_to_ll_10`, …

**Priority**: Medium (useful for breakout detection).

### 2.5 Donchian Breakout Signals

**Description**: Binary signals indicating price broke above HH (breakout up) or below LL (breakout down) in previous bar.  
**Formula**: `breakout_up = price > hh_prev`, `breakout_dn = price < ll_prev`.  
**Required windows**: same as HH/LL windows.  
**Missing features** (two series):
- `donchian_breakout_up_5`, `donchian_breakout_up_10`, …
- `donchian_breakout_dn_5`, `donchian_breakout_dn_10`, …

**Priority**: Low (can be derived from HH/LL and lagged price).

---

## 3. Missing Windows

### 3.1 General Windows `[80, 160]`

**Agreed fixed window set**: `[5,10,20,40,80,160,252]`.  
**Currently implemented**: `[5,10,20,40,60,100,200,126,252]`.  
**Missing windows**: **80**, **160**.

**Affected families**:
- MA (SMA, EMA, WMA)
- Channel (HH, LL)
- Volatility (ATR, STDEV, Z‑score)
- Momentum (Momentum, ROC)
- Percentile

**Gap**: No feature uses window 80 or 160.

### 3.2 Stat Windows `[63]`

**Agreed stat window set**: `[63,126,252]`.  
**Currently implemented**: `[126,252]` (percentile), `[20,40,60,100,200]` (Z‑score).  
**Missing window**: **63**.

**Affected families**:
- Z‑score (`zscore_63`)
- Rank / percentile (`percentile_63`, `rank_63`)

---

## 4. Missing Z‑Score / Rank Windows

**Agreed windows for Z‑score / rank**: `[63,126,252]`.  
**Currently implemented**:
- Z‑score: `[20,40,60,100,200]` (missing 63,126,252)
- Percentile (rank): `[126,252]` (missing 63)

**Missing features**:
- `zscore_63`, `zscore_126`, `zscore_252`
- `percentile_63` (or `rank_63`)

---

## 5. Legacy VX‑First Naming

**Violation**: Feature names `vx_percentile_126` and `vx_percentile_252` contain hard‑coded `vx_` prefix.  
**Impact**: Naming violates source‑agnostic principle (though computation is generic).  
**Action**: Deprecate and keep only `percentile_*` variants.

---

## 6. Minimal Plan for Next Implementation Wave (15–30 Features)

**Goal**: Fill the most critical gaps with a manageable batch.

### 6.1 Priority Selection

| Family               | Features (windows)                  | Count | Priority |
|----------------------|-------------------------------------|-------|----------|
| ATR Channel          | `atr_channel_upper_*`, `atr_channel_lower_*` (5,10,20,40,80,160,252) | 14 | High |
| Bollinger %b         | `bb_pb_*` (5,10,20,40,80,160,252)  | 7  | High |
| Z‑score missing windows | `zscore_63`, `zscore_126`, `zscore_252` | 3  | High |
| Channel Width        | `channel_width_*` (5,10,20,40)     | 4  | Medium |
| **Total**            |                                     | **28** | |

### 6.2 Proposed Implementation List (28 features)

1. **ATR Channel** (14)
   - `atr_channel_upper_5`, `atr_channel_lower_5`
   - `atr_channel_upper_10`, `atr_channel_lower_10`
   - `atr_channel_upper_20`, `atr_channel_lower_20`
   - `atr_channel_upper_40`, `atr_channel_lower_40`
   - `atr_channel_upper_80`, `atr_channel_lower_80`
   - `atr_channel_upper_160`, `atr_channel_lower_160`
   - `atr_channel_upper_252`, `atr_channel_lower_252`

2. **Bollinger %b** (7)
   - `bb_pb_5`, `bb_pb_10`, `bb_pb_20`, `bb_pb_40`, `bb_pb_80`, `bb_pb_160`, `bb_pb_252`

3. **Z‑score missing windows** (3)
   - `zscore_63`, `zscore_126`, `zscore_252`

4. **Channel Width** (4)
   - `channel_width_5`, `channel_width_10`, `channel_width_20`, `channel_width_40`

### 6.3 Implementation Notes

- **Source‑agnostic**: All features must be computed on whichever Data2 column is bound (close price by default).
- **Warmup NaN**: Follow FEAT‑1 rule (EMA/ADX 3×window, others window).
- **Safe division**: Use `DIV0_RET_NAN` policy (already implemented in `safe_div`).
- **Dtype**: `float64`.
- **Registry registration**: Use `register_feature` with appropriate `family`, `min_warmup_bars`, `div0_policy`, `dtype`.

---

## 7. Non‑Feature Gaps

### 7.1 Strategy Slots (Trigger Semantics)

- **LEVEL trigger**: persistent stop/limit – not yet implemented.
- **CROSS trigger**: one‑shot cross – not yet implemented.
- **NONE**: already implemented (next bar open market).

### 7.2 S2 / S3 Strategies

- **S2**: Not found in registry.
- **S3**: Not found in registry.

**Action**: Decide whether S2/S3 are required; if yes, define their specs and register.

---

## 8. Next Steps

1. **Clean up legacy naming**: Remove `vx_percentile_*` from registry (or keep as alias with deprecation warning).
2. **Implement missing windows 80,160**: Extend existing families (MA, Channel, Volatility, Momentum) with these windows.
3. **Implement high‑priority families**: ATR channel, Bollinger %b, missing Z‑score windows (28 features total).
4. **Verify warmup NaN and dtype uniformity** after additions.
5. **Run full test suite** (`make check`) to ensure no regressions.

---

**地端現在做到哪裡？還缺哪些？**

**已達成**：特徵庫基礎建設完成，63 個特徵註冊，測試全過。

**尚缺**：
1. 缺少 5 個家族（ATR 通道、布林 %b、通道寬度、距離、唐奇安突破）。
2. 缺少視窗 80、160、63。
3. 缺少 Z‑score 視窗 63,126,252。
4. 殘留 VX 命名。

**建議下一步**：實作上述 28 個特徵（ATR 通道 14 + 布林 %b 7 + Z‑score 3 + 通道寬度 4），並清理 VX 命名。

---
*Gap list generated by dp (local builder) on 2025‑12‑30 16:14 UTC+8*
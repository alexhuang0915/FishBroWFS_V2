# AS‑IS STATUS REPORT – Feature Universe + Strategy Universe

**Date**: 2025‑12‑30  
**Repository**: FishBroWFS_V2  
**Commit**: `0e20c8f63de870145787e6a2cf3e1380f4ed164c`  
**Evidence Directory**: `outputs/_dp_evidence/20251230_160359/`

---

## Executive Summary

- ✅ **PYTEST LOCKDOWN PASSED**: 985 passed, 37 skipped, 1 xfailed – no regressions.
- ✅ **Feature Registry**: 63 source‑agnostic features registered for TF=60, covering MA, Channel, Volatility, Percentile, Momentum families.
- ⚠️ **Source‑Agnostic Audit**: Core logic is source‑agnostic, but legacy `vx_percentile_*` names remain in registry (violates naming principle).
- ✅ **Strategy Registry**: 7 built‑in strategies registered (S1, sma_cross, breakout_channel, mean_revert_zscore, rsi_reversal, bollinger_breakout, atr_trailing_stop).
- ✅ **Shared Build**: NPZ cache contains 24 keys (baseline + subset of registered features) – build pipeline functional.
- 📋 **Gap Decision**: Missing ~15‑30 features vs agreed non‑ultra universe (ATR channel, Bollinger %b, channel width, distance, Donchian breakout, windows 63/80/160). **Next Wave** list proposed.

---

## 1. PYTEST Result

**Command**: `make check`  
**Outcome**: **PASS**  
**Statistics**: 985 passed, 37 skipped, 1 xfailed, 249 warnings (mostly deprecation).  
**Evidence**: `outputs/_dp_evidence/20251230_160359/PYTEST_SUMMARY.txt`

No test failures → system is stable and ready for verification.

---

## 2. Feature Universe – What Exists Now

### 2.1 Registry Ground Truth

**Timeframe**: 60 minutes (primary)  
**Total Registered Features**: 63  
**Verification Enabled**: Yes (causality verification active)  
**Evidence**: `outputs/_dp_evidence/20251230_160359/FEATURE_REGISTRY_DUMP.txt`

**Families & Counts**:

| Family       | Feature Examples (windows)                          | Count |
|--------------|-----------------------------------------------------|-------|
| MA           | sma_{5,10,20,40}, wma_{5,10,20,40,60,100,200}, ema_{5,10,20,40,60,100,200} | 19 |
| Channel      | hh_{5,10,20,40}, ll_{5,10,20,40}                   | 8  |
| Volatility   | atr_{5,10,14,20,40}, stdev_{10,20,40,60,100,200}, zscore_{20,40,60,100,200} | 15 |
| Percentile   | percentile_{126,252}, vx_percentile_{126,252}       | 4  |
| Momentum     | momentum_{5,10,20,40,60,100,200}, roc_{5,10,20,40,60,100,200}, rsi_{7,14,21} | 15 |
| Baseline     | ts, ret_z_200, session_vwap, atr_14                | 4  |

**Total**: 63 features (including baseline).

### 2.2 Shared Build NPZ Evidence

**Latest NPZ**: `outputs/shared/2026Q1/CME.MNQ/features/features_60m.npz`  
**Keys Count**: 24  
**Keys Excerpt**:
```
atr_10, atr_14, hh_5, hh_10, hh_20, hh_40, ll_5, ll_10, ll_20, ll_40,
percentile_126, percentile_252, ret_z_200, rsi_7, rsi_14, rsi_21,
session_vwap, sma_5, sma_10, sma_20, sma_40, ts,
vx_percentile_126, vx_percentile_252
```

**Observation**: The built cache contains a **subset** of the registered features (24 vs 63). This is expected because the shared build currently only includes features required by the active strategy (S1). The registry, however, holds the full set.

**Evidence**: `outputs/_dp_evidence/20251230_160359/FEATURE_NPZ_KEYS_SAMPLE.txt`

---

## 3. Source‑Agnostic Audit (NO VX‑FIRST)

**Requirement**: Core feature bank must not contain hard‑coded VX/DX symbols; features must be source‑agnostic.

**Scan Command**: `rg -n "vx_|dx_|zn_|vix" src/features src/core src/control src/contracts -S`  
**Findings**:

1. **Legacy naming**: `vx_percentile_126`, `vx_percentile_252` appear in registry and NPZ cache.
2. **Core logic**: `src/core/features.py` contains a special case for `spec.name.startswith("vx_percentile_")` (line 357).
3. **Indicator function**: `vx_percentile` in `src/indicators/numba_indicators.py` is generic (computes percentile rank on any column).

**Conclusion**: **Partial violation**. The core computation is source‑agnostic (works on any Data2 column), but the naming convention `vx_*` violates the “no VX‑first baked names” principle. The parallel `percentile_*` features exist, indicating a transition.

**Evidence**: `outputs/_dp_evidence/20251230_160359/SOURCE_HARDCODE_SCAN.txt`

---

## 4. Strategy Universe – What Exists Now

**Registry Dump**: `outputs/_dp_evidence/20251230_160359/STRATEGY_REGISTRY_DUMP.txt`

### 4.1 Built‑in Strategies (7 total)

| Strategy ID           | Version | Slots (Direction/Filter/Trigger) | NONE Support |
|-----------------------|---------|----------------------------------|--------------|
| S1                    | v1      | Direction only                   | Yes (default) |
| sma_cross             | v1      | Direction only                   | Yes          |
| breakout_channel      | v1      | Direction only                   | Yes          |
| mean_revert_zscore    | v1      | Direction only                   | Yes          |
| rsi_reversal          | v1      | Direction only                   | Yes          |
| bollinger_breakout    | v1      | Direction only                   | Yes          |
| atr_trailing_stop     | v1      | Direction only                   | Yes          |

**S1/S2/S3 Availability**:
- **S1**: Present (`S1`).
- **S2**: Not found in registry.
- **S3**: Not found in registry.

### 4.2 Trigger Semantics (from code inspection)

- **NONE**: Next bar open market (confirmed in `src/strategy/builtin/s1_v1.py`).
- **LEVEL**: Persistent stop/limit (not yet implemented).
- **CROSS**: One‑shot cross (not yet implemented).

**Evidence**: `src/strategy/builtin/s1_v1.py` lines 45‑55.

---

## 5. Gap Decision vs Agreed Non‑Ultra Universe

**Agreed Fixed Window Sets**:
- General windows: `[5, 10, 20, 40, 80, 160, 252]`
- Stat windows (z/rank): `[63, 126, 252]`

**Agreed Feature Families** (non‑ultra):
- ATR channel (atr_channel / keltner‑like)
- Bollinger %b (bb_pb)
- More MA variants (sma/ema/wma – already satisfied)
- Channel width, HH/LL distance, Donchian hi/lo, breakout up/dn
- Z‑score / rank windows in `[63,126,252]`

### 5.1 What Is Already Implemented

From the registry (Section 2.1) we have:
- MA variants: SMA, EMA, WMA across windows `[5,10,20,40,60,100,200]`
- Channel: HH/LL across `[5,10,20,40]`
- Volatility: ATR, STDEV, Z‑score across windows `[5,10,14,20,40,60,100,200]`
- Percentile: windows `[126,252]`
- Momentum: Momentum, ROC, RSI across various windows

### 5.2 Missing vs Agreement

| Missing Item                     | Required Windows      | Notes |
|----------------------------------|-----------------------|-------|
| General window 80, 160           | [80,160]              | No features use these windows. |
| Stat window 63                   | [63]                  | Missing z‑score_63, percentile_63, rank_63. |
| ATR channel (Keltner)            | any                   | Not implemented. |
| Bollinger %b                     | any                   | Not implemented. |
| Channel width (hh‑ll)            | same as HH/LL windows | Not implemented. |
| HH/LL distance (price‑hh, price‑ll) | same windows        | Not implemented. |
| Donchian breakout up/dn signals  | same windows          | Not implemented. |
| Z‑score windows 63,126,252       | [63,126,252]          | Currently only 20,40,60,100,200. |
| Rank windows 63,126,252          | [63,126,252]          | Currently only 126,252 (percentile). |

### 5.3 Proposed “Next Wave” Implementation List (15–30 features)

**Family‑based expansion** (windows fixed as agreed):

1. **ATR Channel** (`atr_channel_*`)
   - Windows: 5,10,20,40,80,160,252 → 7 features
2. **Bollinger %b** (`bb_pb_*`)
   - Windows: 5,10,20,40,80,160,252 → 7 features
3. **Channel Width** (`channel_width_*`)
   - Windows: 5,10,20,40,80,160,252 → 7 features
4. **HH/LL Distance** (`dist_to_hh_*`, `dist_to_ll_*`)
   - Windows: 5,10,20,40,80,160,252 → 14 features (two series)
5. **Donchian Breakout** (`donchian_breakout_up_*`, `donchian_breakout_dn_*`)
   - Windows: 5,10,20,40,80,160,252 → 14 features (two series)
6. **Z‑score** (`zscore_63`, `zscore_126`, `zscore_252`) → 3 features
7. **Rank** (`rank_63`, `rank_126`, `rank_252`) → 3 features

**Total**: 55 features (too many). **Priority selection** (max 30):

- **Must‑have** (15): ATR channel (7), Bollinger %b (7), Z‑score 63/126/252 (3).
- **Nice‑to‑have** (15): Channel width (7), HH/LL distance (8 selected windows).

**Recommended Next Wave (20 features)**:
1. `atr_channel_{5,10,20,40,80,160,252}` (7)
2. `bb_pb_{5,10,20,40,80,160,252}` (7)
3. `zscore_{63,126,252}` (3)
4. `channel_width_{5,10,20,40}` (4) – limited to first four windows.

**Total**: 21 features.

---

## 6. Actionable Recommendations

1. **Remove VX‑first naming**: Deprecate `vx_percentile_*` entries; keep only `percentile_*`.
2. **Implement missing windows**: Add window 63 for percentile/z‑score; add windows 80,160 for general families.
3. **Implement missing families**: Start with ATR channel, Bollinger %b, channel width (as per Next Wave list).
4. **Strategy slots**: Confirm LEVEL/CROSS trigger semantics (currently not implemented).
5. **S2/S3 strategies**: Not yet present; decide if they are required.

---

## 7. Evidence Files

All evidence logs are stored in `outputs/_dp_evidence/20251230_160359/`:

- `REPO_GIT.txt` – git status, commit hash, author info.
- `PYTEST_SUMMARY.txt` – full `make check` output.
- `FEATURE_REGISTRY_DUMP.txt` – complete registry dump for TF=60.
- `SOURCE_HARDCODE_SCAN.txt` – rg scan for VX/DX hardcoding.
- `STRATEGY_REGISTRY_DUMP.txt` – strategy registry contents.
- `FEATURE_NPZ_KEYS_SAMPLE.txt` – keys from latest shared‑build NPZ.

---

**地端現在做到哪裡？還缺哪些？**

**已達成**：
- 測試全過 (985 passed)，功能穩定。
- 特徵庫已註冊 63 個特徵，涵蓋 MA、通道、波動率、百分位、動量五大類。
- 策略庫有 7 個內建策略，包含 S1。
- 共享建置管道正常，NPZ 快取可讀。

**尚缺**：
1. 源碼中仍殘留 `vx_` 前綴命名（違反 source‑agnostic 原則）。
2. 缺少約 15‑30 個特徵（ATR 通道、布林 %b、通道寬度、距離、唐奇安突破、視窗 63/80/160）。
3. 策略觸發語意 LEVEL/CROSS 未實作。
4. S2、S3 策略尚未註冊。

**建議下一步**：實作「Next Wave」清單（約 20 個特徵），並清理 VX 命名殘留。

---
*Report generated by dp (local builder) on 2025‑12‑30 16:09 UTC+8*
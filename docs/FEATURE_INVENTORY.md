# Feature Inventory (SSOT-Friendly)

Purpose: give strategy authors (human + AI) a **single place** to see what features exist and how to reference them.

SSOT sources:
- Feature packs: `configs/registry/feature_packs.yaml`
- Data1 feature execution: `src/core/features/compute.py` (dispatch by feature name)
- Cross feature execution: `src/core/features/cross.py` (`compute_cross_features_v1`)

---

## How strategies “use” features

Strategy configs should reference **packs** (and optional `add/remove`) rather than listing every feature:

- `features.data1.pack`: selects a Data1 feature pack.
- `features.data1.add/remove`: small overrides (keep configs small).

At runtime, strategy code should consume bundles via the FeatureContext helpers:
- `ctx.d1()` → data1 bundle
- `ctx.d2()` → data2 bundle (optional in V1)
- `ctx.x()` → cross bundle (data1 vs data2, optional in V1)

Notes:
- **Cross features are not cached** in `cache/shared/.../features_*.npz` (they require a `(data1,data2)` pair).
- Cross features are computed on-the-fly for the run/window once `data2` is configured.
- Strategy YAML may optionally include `static_params` (not part of the WFS parameter grid) which are always
  passed into the strategy class. This is the recommended place for LLM-authored DSL blocks.
 - `dsl_linear_v1` currently supports these order intents via YAML:
   - Market (via `target_dir`)
   - Stop-entry (via `entry.mode: stop` + `long_stop/short_stop`)
   - Protective stop-exit (via `stops.exit_atr_mult` + `exit_long_stop/exit_short_stop`)

---

## Data1 Packs

### `data1_v1_basic`
Minimal pack (cheap + stable):
- `atr_14`

### `data1_v1_full`
Finite, window-locked “full” pack (WFS-ready). See `configs/registry/feature_packs.yaml` for canonical list.

Families (by naming convention):
- Trend / level:
  - `sma_{5,10,20,40,60,120,240}`
  - `ema_{5,10,20,40,60,120,240}`
  - `hh_{20,60,120}`
  - `ll_{20,60,120}`
- Volatility:
  - `atr_{10,14,20}`
  - `donchian_width_20`
  - `bb_width_20`
  - `atr_ch_upper_14`, `atr_ch_lower_14`, `atr_ch_pos_14`
- Return / rank:
  - `ret_z_200`
  - `zscore_200`
  - `percentile_126`, `percentile_252`
- Band position / distances:
  - `bb_pb_20`
  - `dist_hh_20`, `dist_ll_20`
- Session:
  - `session_vwap`
- Momentum (V1.1):
  - `rsi_{7,14,28}`: RSI with Wilder's (RMA) smoothing. Range 0-100.
  - `adx_14`, `di_plus_14`, `di_minus_14`: Standard Wilder's ADX/DMI.
  - `macd_hist_12_26_9`: MACD Histogram (differences between MACD Line and Signal Line).
  - `roc_{5,20,60}`: Price Rate of Change (Percentage).
  - `atr_pct_14`: Normalized ATR (ATR/Close).
  - `atr_pct_z_{20,60,120}`: Volatility regime (Rolling Z-score of `atr_pct_14`).

### `data1_v1_momentum`
Data1 momentum pack (RSI, ADX, MACD, ROC, ATR%).

Warmup rules (V1):
- For most `*_N` features, warmup is `N` bars (and output is `NaN` before that).
- `atr_pct_14` warmup = `14`
- `atr_pct_z_N` warmup = `14 + N` (because it depends on `atr_pct_14` then z-score over `N`)
- `macd_hist_fast_slow_signal` warmup = `slow + signal` (conservative, deterministic)

---

## Cross Pack (Data1 vs Data2)

### `cross_v1_full`
Deterministic cross feature set (V1). Canonical list is in `configs/registry/feature_packs.yaml`.

- `spread_*`
  - `spread_log`
  - `spread_log_z_{5,20,60,120}`
- `rel_*`
  - `rel_ret_1`
  - `rel_mom_{5,20,60,120}`
  - `rel_vol_ratio`
  - `rel_vol_z_{20,60,120}`
- `corr_*`
  - `corr_{5,20,60,120}`
  - `corr_abs_{20,60,120}`
- `beta_*`
  - `beta_{20,60,120}`
  - `beta_z_{60,120}`: Rolling Z-score of Beta (regime normalization).
  - `alpha_{60,120}`
  - `r2_{60,120}`
  - `resid_std_{60,120}`
- `vol_*`
  - `vol_atr1_14_pct`, `vol_atr2_14_pct`
  - `vol_atr_pct_spread`
  - `vol_atr_pct_spread_z_{20,60,120}`

---

## “Is this feature supported?”

Quick rule of thumb:
- If it’s listed in `configs/registry/feature_packs.yaml`, it should be supported and test-locked.
- If you add a new feature name to a pack, you must:
  1) implement/dispatch it in `src/core/features/compute.py` (data1) or `src/core/features/cross.py` (cross)
  2) ensure `BUILD_FEATURES feature_scope=all_packs` can cache it (update `src/control/shared_build.py:_feature_registry_from_all_packs()` if needed)
  3) add a unit test asserting the pack remains executable

# Strategy & Feature Map (Generated)

This is a **generated** reference snapshot for humans and AIs.
Authoritative semantics live in `docs/SPEC_ENGINE_V1.md`.

Regenerate:
```bash
PYTHONPATH=src python3 scripts/dev/generate_strategy_feature_map.py
```

## Summary
- Active strategies: **1**
- Feature packs: **3**

## Strategy Catalog

| Strategy ID | Config | Status | Packs (data1/cross) | Data2 Required |
| --- | --- | --- | --- | --- |
| `regime_filter_v1` | `configs/strategies/regime_filter_v1.yaml` | `active` | `data1_v1_basic` / `cross_v1_full` | YES |

## Feature Packs

### `cross_v1_full`
- Features: **34**
- Timeframes: 60m

```
alpha_120
alpha_60
beta_120
beta_20
beta_60
corr_120
corr_20
corr_60
corr_abs_120
corr_abs_20
corr_abs_60
r2_120
r2_60
rel_mom_120
rel_mom_20
rel_mom_5
rel_mom_60
rel_ret_1
rel_vol_ratio
rel_vol_z_120
rel_vol_z_20
rel_vol_z_60
resid_std_120
resid_std_60
spread_log
spread_log_z_120
spread_log_z_20
spread_log_z_60
vol_atr1_14
vol_atr2_14
vol_atr_spread
vol_atr_spread_z_120
vol_atr_spread_z_20
vol_atr_spread_z_60
```

### `data1_v1_basic`
- Features: **1**
- Timeframes: 60m

```
atr_14
```

### `data1_v1_full`
- Features: **36**
- Timeframes: 60m

```
atr_10
atr_14
atr_20
atr_ch_lower_14
atr_ch_pos_14
atr_ch_upper_14
bb_pb_20
bb_width_20
dist_hh_20
dist_ll_20
donchian_width_20
ema_10
ema_120
ema_20
ema_240
ema_40
ema_5
ema_60
hh_120
hh_20
hh_60
ll_120
ll_20
ll_60
percentile_126
percentile_252
ret_z_200
session_vwap
sma_10
sma_120
sma_20
sma_240
sma_40
sma_5
sma_60
zscore_200
```


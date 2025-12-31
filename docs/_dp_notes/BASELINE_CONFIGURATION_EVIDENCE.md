# Baseline Configuration Evidence

## Overview
Created baseline YAML configuration files for S1, S2, and S3 strategies according to specification.

## Files Created
1. `configs/strategies/S1/baseline.yaml`
2. `configs/strategies/S2/baseline.yaml`
3. `configs/strategies/S3/baseline.yaml`

## Feature Availability Verification
- Verified against shared cache: `outputs/shared/2026Q1/CME.MNQ/features/features_60m.npz`
- Total features in cache: 126
- All referenced features exist in cache

## S1 Baseline Configuration

### Strategy Details
- **Strategy ID**: S1
- **Dataset**: CME.MNQ
- **Timeframe**: 60 minutes
- **Version**: v1

### Feature Choices
S1 requires 18 features from its `feature_requirements()` method. Used canonical feature names where possible:

| Original Requirement | Canonical Name Used | Available in Cache | Rationale |
|----------------------|---------------------|-------------------|-----------|
| vx_percentile_126 | percentile_126 | Yes | Use canonical name without vx_ prefix |
| vx_percentile_252 | percentile_252 | Yes | Use canonical name without vx_ prefix |
| All other features | Same as original | Yes | Already canonical names |

**Complete feature list**: sma_5, sma_10, sma_20, sma_40, hh_5, hh_10, hh_20, hh_40, ll_5, ll_10, ll_20, ll_40, atr_10, atr_14, percentile_126, percentile_252, ret_z_200, session_vwap

### Parameter Schema
- S1 has no parameters (empty param_schema)
- `params: {}` in YAML

### Validation
- YAML parses correctly
- All 18 features exist in shared cache
- Follows S1's feature_requirements() specification

## S2 Baseline Configuration (Pullback Continuation)

### Strategy Details
- **Strategy ID**: S2
- **Dataset**: CME.MNQ
- **Timeframe**: 60 minutes
- **Version**: v1

### Feature Choices
S2 is feature-agnostic; feature names are provided via parameters:

| Parameter | Feature Chosen | Available in Cache | Rationale |
|-----------|----------------|-------------------|-----------|
| context_feature_name | ema_40 | Yes | Trend-ish feature (exponential moving average) |
| value_feature_name | bb_pb_20 | Yes | Pullback indicator (Bollinger %b) |
| filter_feature_name | (empty) | N/A | filter_mode="NONE" so no filter needed |

### Parameter Settings
- **filter_mode**: "NONE" (no additional filtering)
- **trigger_mode**: "NONE" (market next open entry)
- **value_threshold**: 0.2 (near lower band for pullback continuation)
- **context_threshold**: 0.0 (default)
- **order_qty**: 1.0

### Rationale
- **ema_40**: Represents medium-term trend direction
- **bb_pb_20**: Measures position within Bollinger Bands; values near 0.2 indicate near lower band (oversold)
- **Threshold 0.2**: Expect bounce from oversold condition for pullback continuation

### Validation
- YAML parses correctly
- Both ema_40 and bb_pb_20 exist in shared cache
- Parameters match S2's param_schema requirements

## S3 Baseline Configuration (Extreme Reversion)

### Strategy Details
- **Strategy ID**: S3
- **Dataset**: CME.MNQ
- **Timeframe**: 60 minutes
- **Version**: v1

### Feature Choices
S3 is feature-agnostic; feature names are provided via parameters:

| Parameter | Feature Chosen | Available in Cache | Rationale |
|-----------|----------------|-------------------|-----------|
| context_feature_name | atr_14 | Yes | Regime check (volatility) |
| value_feature_name | bb_pb_20 | Yes | Oversold indicator (Bollinger %b) |
| filter_feature_name | (empty) | N/A | filter_mode="NONE" so no filter needed |

### Parameter Settings
- **filter_mode**: "NONE" (no additional filtering)
- **trigger_mode**: "NONE" (market next open entry)
- **value_threshold**: 0.1 (very low, extreme oversold for reversion)
- **context_threshold**: 0.0 (default)
- **order_qty**: 1.0

### Rationale
- **atr_14**: Measures volatility; can indicate regime (high/low volatility)
- **bb_pb_20**: Measures position within Bollinger Bands; values near 0.1 indicate extreme oversold
- **Threshold 0.1**: Extreme lower band for reversion play
- **Note**: For S3, value_feature < value_threshold triggers (oversold condition)

### Validation
- YAML parses correctly
- Both atr_14 and bb_pb_20 exist in shared cache
- Parameters match S3's param_schema requirements

## YAML Schema Compliance
All files follow the specified YAML schema:
- `version`: "v1"
- `strategy_id`: matches strategy
- `dataset_id`: "CME.MNQ"
- `timeframe`: 60
- `features`: with `required` and `optional` lists
- `params`: strategy-specific parameters

## Canonical Feature Names
- Used canonical feature names only (no vx_/dx_/zn_ prefixes)
- For S1: replaced vx_percentile_* with percentile_*
- All feature names match those in shared cache

## Verification Results
1. **YAML Parsing**: All three files parse successfully (valid YAML syntax)
2. **Feature Availability**: All referenced features exist in shared cache
3. **Schema Compliance**: All files include required fields
4. **Parameter Validation**: Parameters match each strategy's param_schema

## Constraints Satisfied
- ✓ Must create 3 files in correct locations
- ✓ Must use canonical feature names only
- ✓ Must reference features that exist in shared cache
- ✓ Must follow specified YAML schema exactly
- ✓ Must validate against strategy parameter schemas

## Next Steps
These baseline configurations are ready for use in research runs. They provide sensible starting points for each strategy while ensuring all feature dependencies are satisfied by the existing shared cache.
# No-Flip WFS Baseline Experiment

## Overview

This directory contains configuration files for the "No-Flip" Wide-Feature-Set (WFS) baseline experiment. The experiment establishes a directionally-neutral foundation for strategy evaluation by excluding all momentum, trend, and regime-based features, focusing exclusively on non-directional feature families.

## Experiment Design

### Core Principles

1. **Directional Neutrality**: Exclude features with inherent directional bias
2. **Structural Focus**: Emphasize channel, volatility, reversion, and structure features
3. **Robustness Through Diversity**: Include multiple feature families and window lengths
4. **Research Readiness**: Configurations are ready to run with `allow_build=False`

### Feature Families Included

| Family | Description | Example Features |
|--------|-------------|------------------|
| **Channel** | Price position within ranges | `bb_pb_{w}`, `bb_width_{w}`, `atr_ch_*_{w}`, `donchian_width_{w}`, `dist_hh_{w}`, `dist_ll_{w}` |
| **Volatility** | Market dispersion measures | `atr_{w}`, `stdev_{w}`, `zscore_{w}` |
| **Reversion** | Statistical extreme identification | `percentile_{w}`, `zscore_{w}` |
| **Structure** | Session-based patterns | `session_vwap` |
| **Time** | Temporal patterns | `hour_of_day`, `day_of_week`, `month_of_year` (future) |

### Feature Families Excluded

| Family | Reason for Exclusion | Example Features |
|--------|----------------------|------------------|
| **Moving Averages** | Inherent directional smoothing | `sma_{w}`, `ema_{w}`, `wma_{w}` |
| **Momentum** | Direct price acceleration measurement | `rsi_{w}`, `momentum_{w}`, `roc_{w}` |
| **Trend** | Market direction identification | `adx_{w}`, `cci_{w}` |
| **Regime** | Market state classification | Any regime classification features |

### Window Sets

- **General Windows**: [5, 10, 20, 40, 80, 160, 252]
- **Statistical Windows**: [63, 126, 252]

## Configuration Files

### 1. S1_no_flip.yaml

**Purpose**: Comprehensive feature baseline using all eligible No-Flip features

**Key Characteristics**:
- Includes ~50+ features across all non-directional families
- Uses fixed window sets for consistency
- Maximum lookback: 252 bars
- Warmup period: 252 bars for `percentile_252` feature

**Feature Coverage**:
- Channel: Bollinger Bands, ATR Channel, Donchian, HH/LL Distance
- Volatility: ATR, Standard Deviation, Z-score
- Reversion: Percentile
- Structure: Session VWAP

### 2. S2_no_flip.yaml

**Purpose**: Pullback continuation adapted to non-directional features

**Adaptation**:
- **Original Context**: `ema_40` (trend) → **Replaced with** `atr_14` (volatility)
- **Original Value**: `bb_pb_20` (channel) → **Unchanged**
- **Logic**: Trigger when `bb_pb_20 < 0.2` during volatile periods (`atr_14 > 0`)

**Parameters**:
- `context_feature_name: "atr_14"`
- `value_feature_name: "bb_pb_20"`
- `value_threshold: 0.2`

### 3. S3_no_flip.yaml

**Purpose**: Extreme reversion (already uses non-directional features)

**Note**: S3 baseline already uses non-directional features (`atr_14` and `bb_pb_20`), so no adaptation needed.

**Parameters**:
- `context_feature_name: "atr_14"`
- `value_feature_name: "bb_pb_20"`
- `value_threshold: 0.1` (more extreme than S2)

## Execution Instructions

### Prerequisites

1. Feature cache must contain all required features
2. Dataset: CME.MNQ
3. Timeframe: 60 minutes

### Basic Execution

```bash
# Run S1 No-Flip experiment
python scripts/run_baseline.py \
  --strategy S1 \
  --config configs/experiments/baseline_no_flip/S1_no_flip.yaml \
  --allow_build False

# Run S2 No-Flip experiment  
python scripts/run_baseline.py \
  --strategy S2 \
  --config configs/experiments/baseline_no_flip/S2_no_flip.yaml \
  --allow_build False

# Run S3 No-Flip experiment
python scripts/run_baseline.py \
  --strategy S3 \
  --config configs/experiments/baseline_no_flip/S3_no_flip.yaml \
  --allow_build False
```

### Batch Execution

```bash
# Run all No-Flip experiments
for strategy in S1 S2 S3; do
  python scripts/run_baseline.py \
    --strategy $strategy \
    --config configs/experiments/baseline_no_flip/${strategy}_no_flip.yaml \
    --allow_build False
done
```

### Expected Outputs

Each experiment will produce:
- Strategy artifacts in `outputs/shared/{season}/{dataset}/strategies/{strategy_id}/`
- Performance metrics (Sharpe ratio, max drawdown, win rate)
- Execution logs for debugging

## Feature Verification

### Required Features

All configurations require the following features to be available in the feature registry and cache:

**S1 Requirements**:
- All channel features with windows [5,10,20,40,80,160,252]
- Volatility features: `atr_{5,10,14,20,40}`, `stdev_{10,20,40,60,100,200}`, `zscore_{20,40,60,100,200}`
- Reversion features: `percentile_{63,126,252}`
- Structure feature: `session_vwap`

**S2/S3 Requirements**:
- `atr_14` (volatility)
- `bb_pb_20` (Bollinger %b)

### Verification Script

To verify feature availability:

```python
from features.registry import get_default_registry

registry = get_default_registry()
tf = 60

# Check S2/S3 features
required = ["atr_14", "bb_pb_20"]
for feature in required:
    specs = [s for s in registry.specs_for_tf(tf) if s.name == feature]
    if specs:
        print(f"✓ {feature} available")
    else:
        print(f"✗ {feature} NOT available")
```

## Success Criteria

### Technical Success
- All configurations load without errors
- All required features are available in cache
- Strategies execute to completion without runtime errors
- Results are saved to appropriate output directories

### Performance Benchmarks
- No-Flip strategies demonstrate measurable performance
- Performance is comparable to or more stable than directional variants
- Feature importance aligns with non-directional design principles

### Research Value
- Provides clear baseline for directional vs non-directional comparison
- Identifies strengths/weaknesses of structural features
- Informs future feature development priorities

## Risk Assessment

### Potential Issues

| Risk | Mitigation |
|------|------------|
| Missing features | Verify registry before execution; provide fallback features |
| Insufficient signal | Include diverse feature families; multiple window lengths |
| Overfitting | Use fixed window sets; avoid parameter optimization |
| Performance degradation | Expected - establishes directional feature contribution baseline |

### Contingency Plans

1. **Feature Availability**: Substitute missing features with similar features from same family
2. **Performance Floor**: Establish minimum acceptable performance metrics
3. **Execution Failures**: Log detailed error information; provide reduced feature set fallbacks

## Results Interpretation

### Key Questions

1. **Performance Attribution**: How much performance is attributable to directional vs non-directional features?
2. **Feature Importance**: Which non-directional feature families provide the most predictive power?
3. **Stability**: How stable are non-directional features across different market regimes?
4. **Risk-Adjusted Returns**: Can non-directional features provide better risk-adjusted returns during turbulent periods?

### Comparative Analysis

Compare No-Flip results with:
- Original S1/S2/S3 baseline configurations
- Other feature set variations
- Different market regimes and time periods

## Next Steps

### Immediate Actions
1. Execute baseline experiments to establish performance metrics
2. Document results in experiment log
3. Compare with directional feature performance

### Future Development
1. Add time features (`hour_of_day`, `day_of_week`, `month_of_year`) when available
2. Expand to additional non-directional feature families
3. Adapt additional strategies to No-Flip paradigm
4. Integrate with machine learning models

## References

1. **Blueprint Document**: `docs/_dp_notes/WFS_BLUEPRINT_NO_FLIP_V1.md`
2. **Feature Registry**: `src/features/registry.py`
3. **Seed Default Features**: `src/features/seed_default.py`
4. **Strategy Configurations**: `configs/strategies/`

## Changelog

### v1.0 (2025-12-30)
- Initial release of No-Flip experiment configurations
- S1: Comprehensive non-directional feature baseline
- S2: Pullback continuation adapted to volatility context
- S3: Extreme reversion (already non-directional)
- All configurations research-ready with `allow_build=False`
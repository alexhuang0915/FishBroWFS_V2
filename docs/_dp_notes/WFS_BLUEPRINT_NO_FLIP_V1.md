# No-Flip WFS Research Blueprint

## Executive Summary

The "No-Flip" Wide-Feature-Set (WFS) baseline experiment is designed to establish a robust, directionally-neutral foundation for strategy evaluation. By excluding all momentum, trend, and regime-based features, this experiment focuses exclusively on **non-directional feature families** that provide structural, volatility, and channel-based market context without introducing directional bias.

**Primary Goals:**
1. Establish a baseline performance metric for strategies using only non-directional features
2. Isolate the contribution of structural market features from directional signals
3. Create a more robust foundation for strategy evaluation that is less susceptible to regime shifts
4. Provide a clean experimental control for comparing against directional feature sets

**Key Characteristics:**
- **Feature Scope**: Channel, volatility, reversion, structure, and time families only
- **Exclusions**: All MA variants, momentum indicators, trend indicators, regime features
- **Window Sets**: Fixed windows [5, 10, 20, 40, 80, 160, 252] for general features, [63, 126, 252] for statistical features
- **Source Agnostic**: No VX/DX hardcoding, using canonical feature names
- **Research Ready**: `allow_build=False` configuration for immediate execution

## Design Principles

### 1. Directional Neutrality
The core principle of "No-Flip" is to eliminate features that inherently contain directional bias. This includes:
- **Momentum indicators** (ROC, RSI, MACD) that measure price acceleration
- **Trend indicators** (ADX, CCI) that identify market direction
- **Moving averages** (SMA, EMA, WMA) that smooth price data with directional implications
- **Regime features** that classify market states based on directional patterns

### 2. Structural Focus
The experiment emphasizes features that describe market structure without implying direction:
- **Channel features**: Describe price position within ranges (BB %b, ATR channels, Donchian)
- **Volatility features**: Measure market dispersion (ATR, STDDEV, z-score)
- **Reversion features**: Identify statistical extremes (percentile, rank)
- **Structure features**: Capture session-based patterns (VWAP, session highs/lows)
- **Time features**: Encode temporal patterns (hour, day, month)

### 3. Robustness Through Diversity
By including multiple feature families and window lengths, the experiment:
- Reduces overfitting to specific market conditions
- Provides redundant signals for key market characteristics
- Creates a more stable feature representation across regimes

### 4. Practical Implementation
- **Fixed window sets**: Consistent across all strategies for comparability
- **Source-agnostic naming**: Uses canonical feature names (e.g., `percentile_126` not `vx_percentile_126`)
- **Research-ready**: Configurations can be run immediately with existing feature cache
- **Pytest compatible**: Maintains lockdown compatibility with existing test suite

## Feature Selection Methodology

### Eligible Feature Families

| Family | Description | Example Features | Inclusion Rationale |
|--------|-------------|------------------|---------------------|
| **Channel** | Price position within ranges | `bb_pb_{w}`, `bb_width_{w}`, `atr_ch_*_{w}`, `donchian_width_{w}`, `dist_hh_{w}`, `dist_ll_{w}` | Describes market boundaries without directional bias |
| **Volatility** | Market dispersion measures | `atr_{w}`, `stdev_{w}`, `zscore_{w}` | Captures market uncertainty and range expansion |
| **Reversion** | Statistical extreme identification | `percentile_{w}`, `zscore_{w}` | Identifies overextended conditions for mean reversion |
| **Structure** | Session-based patterns | `session_vwap`, `session_high`, `session_low`, `session_range` | Captures intraday market microstructure |
| **Time** | Temporal patterns | `hour_of_day`, `day_of_week`, `month_of_year` | Encodes calendar-based market behaviors |

### Exclusion Criteria

The following feature families are **excluded** from the No-Flip experiment:

| Family | Reason for Exclusion | Example Features |
|--------|----------------------|------------------|
| **Moving Averages** | Inherent directional smoothing | `sma_{w}`, `ema_{w}`, `wma_{w}` |
| **Momentum** | Direct price acceleration measurement | `rsi_{w}`, `momentum_{w}`, `roc_{w}` |
| **Trend** | Market direction identification | `adx_{w}`, `cci_{w}` (if implemented) |
| **Regime** | Market state classification | Any regime classification features |

### Window Selection Strategy

Two fixed window sets are used consistently across all features:

1. **General Windows**: [5, 10, 20, 40, 80, 160, 252]
   - Used for channel, volatility, and structure features
   - Provides multi-timeframe perspective from short-term to annual

2. **Statistical Windows**: [63, 126, 252]
   - Used for percentile and statistical features
   - Aligns with quarterly, semi-annual, and annual periods
   - Consistent with existing percentile feature windows

### Feature Verification Process

All selected features are verified against the current feature registry to ensure:
1. **Existence**: Feature is registered in the default registry
2. **Causality**: Feature has passed causality verification (if enabled)
3. **Timeframe Support**: Feature is available for 60-minute timeframe (primary strategy TF)
4. **Naming Convention**: Uses canonical (non-deprecated) names

## Strategy Configurations

### S1: Comprehensive Feature Baseline

**Design Philosophy**: S1 serves as a comprehensive feature baseline using all eligible No-Flip features across multiple window lengths.

**Feature Selection**:
- **Channel Features**: All channel features across general windows
- **Volatility Features**: ATR and STDDEV across general windows
- **Reversion Features**: Percentile across statistical windows
- **Structure Features**: Session VWAP
- **Time Features**: Hour, day, month temporal encoding

**Configuration Highlights**:
- **Timeframe**: 60 minutes (consistent with baseline)
- **Dataset**: CME.MNQ (standard test instrument)
- **Feature Count**: ~50+ features across all families
- **Warmup Requirements**: Maximum lookback of 252 bars
- **NaN Handling**: Standard warmup period with NaN propagation

**Expected Behavior**: S1 will produce a dense feature matrix suitable for machine learning applications, providing comprehensive market structure representation without directional signals.

### S2: Pullback Continuation (No-Flip Adaptation)

**Design Philosophy**: Adapt S2's pullback continuation logic to use non-directional context features.

**Original Configuration**:
- Context: `ema_40` (trend indicator) → **REPLACED**
- Value: `bb_pb_20` (pullback indicator) → **RETAINED**

**No-Flip Adaptation**:
- **Context Feature**: `atr_14` (volatility regime)
  - Rationale: Volatility provides non-directional context for pullback significance
  - Threshold: `context_threshold: 0.0` (no filtering by default)
- **Value Feature**: `bb_pb_20` (Bollinger %b)
  - Rationale: Channel position is directionally neutral
  - Threshold: `value_threshold: 0.2` (near lower band for pullback)
- **Filter Feature**: None (maintains NONE filter mode)

**Parameter Adjustments**:
- `context_feature_name: "atr_14"`
- `value_feature_name: "bb_pb_20"`
- `context_threshold: 0.0` (volatility above zero - always true)
- Other parameters unchanged from baseline

**Expected Behavior**: S2 will trigger on Bollinger %b pullbacks (value < 0.2) during periods of measurable volatility, providing a volatility-conditioned channel-based entry signal.

### S3: Extreme Reversion (No-Flip Adaptation)

**Design Philosophy**: Adapt S3's extreme reversion logic to use non-directional context features.

**Original Configuration**:
- Context: `atr_14` (volatility regime) → **RETAINED**
- Value: `bb_pb_20` (oversold indicator) → **RETAINED**

**No-Flip Adaptation**:
- **Context Feature**: `atr_14` (volatility regime) → **UNCHANGED**
  - Rationale: Volatility is already non-directional
  - Threshold: `context_threshold: 0.0` (no filtering)
- **Value Feature**: `bb_pb_20` (Bollinger %b) → **UNCHANGED**
  - Rationale: Channel position is directionally neutral
  - Threshold: `value_threshold: 0.1` (extreme lower band)
- **Filter Feature**: None (maintains NONE filter mode)

**Parameter Adjustments**:
- No changes needed from baseline (already uses non-directional features)
- Verify `atr_14` is available and causality-verified

**Expected Behavior**: S3 will trigger on extreme Bollinger %b readings (value < 0.1) during volatile periods, providing a volatility-conditioned extreme reversion signal.

## Experimental Protocol

### 1. Directory Structure
```
configs/experiments/baseline_no_flip/
├── S1_no_flip.yaml
├── S2_no_flip.yaml
├── S3_no_flip.yaml
└── README.md
```

### 2. Execution Commands

**Basic Execution**:
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

**Batch Execution**:
```bash
# Run all No-Flip experiments
for strategy in S1 S2 S3; do
  python scripts/run_baseline.py \
    --strategy $strategy \
    --config configs/experiments/baseline_no_flip/${strategy}_no_flip.yaml \
    --allow_build False
done
```

### 3. Expected Outputs

Each experiment should produce:
- **Strategy artifacts** in `outputs/shared/{season}/{dataset}/strategies/{strategy_id}/`
- **Performance metrics** including Sharpe ratio, max drawdown, win rate
- **Feature importance** analysis (if supported by strategy)
- **Execution logs** for debugging and verification

### 4. Success Criteria

The experiment will be considered successful if:

1. **Technical Success**:
   - All configurations load without errors
   - All required features are available in cache
   - Strategies execute to completion without runtime errors
   - Results are saved to appropriate output directories

2. **Performance Benchmarks**:
   - No-Flip strategies demonstrate measurable performance
   - Performance is comparable to or more stable than directional variants
   - Feature importance aligns with non-directional design principles

3. **Research Value**:
   - Provides clear baseline for directional vs non-directional comparison
   - Identifies strengths/weaknesses of structural features
   - Informs future feature development priorities

## Risk Assessment

### Potential Issues and Mitigations

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| **Missing Features** | Medium | High | Verify all features exist in registry before execution; provide fallback features |
| **Insufficient Signal** | High | Medium | Include diverse feature families; use multiple window lengths for redundancy |
| **Overfitting** | Medium | Medium | Use fixed window sets; avoid parameter optimization in baseline |
| **Performance Degradation** | High | Low | Expected outcome - establishes directional feature contribution baseline |
| **Warmup Issues** | Low | Medium | Calculate maximum lookback (252 bars); ensure sufficient warmup period |
| **Cache Inconsistency** | Low | High | Use `allow_build=False` to rely on existing cache; verify cache completeness |

### Contingency Plans

1. **Feature Availability**:
   - If specific features are missing, substitute with similar features from same family
   - Maintain list of alternative features for each primary selection

2. **Performance Floor**:
   - Establish minimum acceptable performance metrics
   - If performance is below floor, analyze feature contributions individually

3. **Execution Failures**:
   - Log detailed error information
   - Provide fallback configurations with reduced feature sets

## Next Steps

### Immediate Actions
1. **Create configuration files** in `configs/experiments/baseline_no_flip/`
2. **Verify feature availability** against current registry
3. **Execute baseline experiments** to establish performance metrics
4. **Document results** in experiment README

### Future Development
1. **Comparative Analysis**: Compare No-Flip vs directional feature performance
2. **Feature Expansion**: Add additional non-directional features as they become available
3. **Strategy Adaptation**: Adapt additional strategies to No-Flip paradigm
4. **Machine Learning Integration**: Use No-Flip features as input for ML models

### Research Questions
1. How much performance is attributable to directional vs non-directional features?
2. Which non-directional feature families provide the most predictive power?
3. How stable are non-directional features across different market regimes?
4. Can non-directional features provide better risk-adjusted returns during turbulent periods?

## Appendix A: Feature Matrix

### Channel Features
| Feature | Windows | Description | Lookback |
|---------|---------|-------------|----------|
| `bb_pb_{w}` | [5,10,20,40,80,160,252] | Bollinger Band %b position | w |
| `bb_width_{w}` | [5,10,20,40,80,160,252] | Bollinger Band width | w |
| `atr_ch_upper_{w}` | [5,10,14,20,40,80,160,252] | ATR Channel upper band | max(w,14) |
| `atr_ch_lower_{w}` | [5,10,14,20,40,80,160,252] | ATR Channel lower band | max(w,14) |
| `atr_ch_pos_{w}` | [5,10,14,20,40,80,160,252] | ATR Channel position | max(w,14) |
| `donchian_width_{w}` | [5,10,20,40,80,160,252] | Donchian channel width | w |
| `dist_hh_{w}` | [5,10,20,40,80,160,252] | Distance to highest high | w |
| `dist_ll_{w}` | [5,10,20,40,80,160,252] | Distance to lowest low | w |

### Volatility Features
| Feature | Windows | Description | Lookback |
|---------|---------|-------------|----------|
| `atr_{w}` | [5,10,14,20,40] | Average True Range | w |
| `stdev_{w}` | [10,20,40,60,100,200] | Standard deviation | w |
| `zscore_{w}` | [20,40,60,100,200] | Z-score of returns | w |

### Reversion Features
| Feature | Windows | Description | Lookback |
|---------|---------|-------------|----------|
| `percentile_{w}` | [63,126,252] | Percentile rank | w |

### Structure Features
| Feature | Windows | Description | Lookback |
|---------|---------|-------------|----------|
| `session_vwap` | 1 | Session Volume Weighted Average Price | 0 |

### Time Features
| Feature | Windows | Description | Lookback |
|---------|---------|-------------|----------|
| `hour_of_day` | 1 | Hour of day (0-23) | 0 |
| `day_of_week` | 1 | Day of week (0-6) | 0 |
| `month_of_year` | 1 | Month of year (1-12) | 0 |

## Appendix B: Configuration Templates

### S1 Configuration Template
```yaml
version: "v1"
strategy_id: "S1"
dataset_id: "CME.MNQ"
timeframe: 60
features:
  required:
    # Channel features
    - name: "bb_pb_5"
      timeframe_min: 60
    - name: "bb_pb_10"
      timeframe_min: 60
    # ... additional features as per matrix
  optional: []
params: {}
allow_build: false
notes: "S1 No-Flip configuration using only non-directional features"
```

### S2 Configuration Template
```yaml
version: "v1"
strategy_id: "S2"
dataset_id: "CME.MNQ"
timeframe: 60
features:
  required:
    - name: "context_feature"
      timeframe_min: 60
    - name: "value_feature"
      timeframe_min: 60
  optional:
    - name: "filter_feature"
      timeframe_min: 60
params:
  filter_mode: "NONE"
  trigger_mode: "NONE"
  entry_mode: "MARKET_NEXT_OPEN"
  context_threshold: 0.0
  value_threshold: 0.2
  filter_threshold: 0.0
  context_feature_name: "atr_14"
  value_feature_name: "bb_pb_20"
  filter_feature_name: ""
  order_qty: 1.0
allow_build: false
notes: "S2 No-Flip adaptation using volatility context and channel value"
```

### S3 Configuration Template
```yaml
version: "v1"
strategy_id: "S3"
dataset_id: "CME.MNQ"
timeframe: 60
features:
  required:
    -
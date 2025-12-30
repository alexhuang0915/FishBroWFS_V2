# Feature Registry Expansion and Deprecation Strategy Design

## 1. Overview

This document outlines the design for expanding the FishBroWFS_V2 feature universe with new feature families while implementing a source-agnostic naming convention and deprecation strategy for legacy VX-first names.

## 2. Current State Analysis

### 2.1 FeatureSpec Models
- **Contract FeatureSpec** (`src/contracts/features.py`): Base model with minimal fields
- **Enhanced FeatureSpec** (`src/features/models.py`): Extended with causality verification fields
- **Current fields**: `name`, `timeframe_min`, `lookback_bars`, `params`, `window`, `min_warmup_bars`, `dtype`, `div0_policy`, `family`, `compute_func`, `window_honest`, `causality_verified`, `verification_timestamp`

### 2.2 Feature Registry
- **Thread-safe registration** with causality verification gates
- **Global registry** pattern via `get_default_registry()`
- **Seed registration** in `src/features/seed_default.py` for TF=60
- **Warmup rules**: EMA/ADX = 3×window, others = window

### 2.3 Existing Legacy Names
- `vx_percentile_126` → canonical `percentile_126`
- `vx_percentile_252` → canonical `percentile_252`
- Currently registered as separate features with same compute function

## 3. Design Changes

### 3.1 FeatureSpec Schema Extension

#### 3.1.1 Contract FeatureSpec Changes
```python
# In src/contracts/features.py
class FeatureSpec(BaseModel):
    # ... existing fields ...
    deprecated: bool = Field(default=False)
    notes: Optional[str] = Field(default=None)  # For deprecation notes
```

#### 3.1.2 Enhanced FeatureSpec Changes
```python
# In src/features/models.py
class FeatureSpec(BaseModel):
    # ... existing fields ...
    deprecated: bool = Field(default=False)
    notes: Optional[str] = Field(default=None)
    canonical_name: Optional[str] = Field(default=None)  # For deprecated aliases
```

### 3.2 Registry Registration API Changes

#### 3.2.1 New Parameters for `register_feature()`
```python
def register_feature(
    self,
    name: str,
    timeframe_min: int,
    lookback_bars: int,
    params: Dict[str, str | int | float],
    compute_func: Optional[Callable[..., np.ndarray]] = None,
    skip_verification: bool = False,
    window: int = 1,
    min_warmup_bars: int = 0,
    dtype: Literal["float64"] = "float64",
    div0_policy: Literal["DIV0_RET_NAN"] = "DIV0_RET_NAN",
    family: Optional[str] = None,
    deprecated: bool = False,  # NEW
    notes: Optional[str] = None,  # NEW
    canonical_name: Optional[str] = None  # NEW (for deprecated aliases)
) -> FeatureSpec:
```

#### 3.2.2 Duplicate Registration Policy
- Allow duplicate `(name, timeframe)` if one is deprecated and one is not
- Prevent duplicate non-deprecated features
- Deprecated features can reference canonical features via `canonical_name`

### 3.3 Deprecation Alias Mechanism

#### 3.3.1 Implementation Approach
1. **Separate registry entries** with `deprecated=True`
2. **Same compute function** as canonical feature
3. **Canonical reference** via `canonical_name` field
4. **Filtering** in UI/selection lists to exclude deprecated features

#### 3.3.2 Example: Percentile Features
```python
# Canonical feature
register_feature(
    name="percentile_126",
    timeframe_min=60,
    lookback_bars=126,
    params={"window": 126},
    compute_func=vx_percentile,
    family="percentile",
    deprecated=False
)

# Deprecated alias
register_feature(
    name="vx_percentile_126",
    timeframe_min=60,
    lookback_bars=126,
    params={"window": 126},
    compute_func=vx_percentile,
    family="percentile",
    deprecated=True,
    notes="Legacy VX-first name. Use 'percentile_126' instead.",
    canonical_name="percentile_126"
)
```

### 3.4 Warmup Rules for New Families

| Family | Warmup Multiplier | Formula | Notes |
|--------|-------------------|---------|-------|
| bb (Bollinger Bands) | 1× | `window` | Uses SMA + STDEV |
| atr_channel | 1× | `window` | Based on ATR Wilder |
| donchian | 1× | `window` | Channel width |
| distance | 1× | `window` | HH/LL distance |
| percentile | 1× | `window` | Existing family |
| ema | 3× | `3 × window` | Existing multiplier |
| adx | 3× | `3 × window` | Future consideration |

**Implementation**: Update `compute_min_warmup_bars()` in `src/features/seed_default.py`

### 3.5 Family Categorization for New Features

| Feature Type | Family | Description |
|--------------|--------|-------------|
| `bb_pb_{w}` | `bb` | Bollinger Band %b |
| `bb_width_{w}` | `bb` | Bollinger Band width |
| `atr_ch_upper_{w}` | `atr_channel` | ATR Channel upper band |
| `atr_ch_lower_{w}` | `atr_channel` | ATR Channel lower band |
| `atr_ch_pos_{w}` | `atr_channel` | ATR Channel position |
| `donchian_width_{w}` | `donchian` | Donchian channel width |
| `dist_hh_{w}` | `distance` | Distance to highest high |
| `dist_ll_{w}` | `distance` | Distance to lowest low |
| `percentile_{w}` | `percentile` | Percentile rank (existing) |

### 3.6 Parameter Conventions

#### 3.6.1 Bollinger Bands (`bb_pb_{w}`, `bb_width_{w}`)
```python
params = {
    "window": w,
    "multiplier": 2.0,  # Standard deviation multiplier
    "method": "sma"     # Base method (sma for standard BB)
}
```

#### 3.6.2 ATR Channel (`atr_ch_upper_{w}`, `atr_ch_lower_{w}`, `atr_ch_pos_{w}`)
```python
params = {
    "window": w,
    "multiplier": 2.0,  # ATR multiplier for channel width
    "atr_window": 14    # ATR calculation window (could match w)
}
```

#### 3.6.3 Donchian Channel Width (`donchian_width_{w}`)
```python
params = {
    "window": w
}
```

#### 3.6.4 HH/LL Distance (`dist_hh_{w}`, `dist_ll_{w}`)
```python
params = {
    "window": w,
    "normalize": True   # Whether to normalize by price
}
```

#### 3.6.5 Percentile (`percentile_{w}`)
```python
params = {
    "window": w
}
```

### 3.7 New Feature Specifications

#### 3.7.1 Bollinger Bands
- **Windows**: [5, 10, 20, 40, 80, 160, 252]
- **Compute functions**: `bb_percent_b()` and `bb_width()` (to be implemented)
- **Lookback**: `window` bars
- **Warmup**: `window` bars

#### 3.7.2 ATR Channel
- **Windows**: [5, 10, 14, 20, 40, 80, 160, 252]
- **Compute functions**: `atr_channel_upper()`, `atr_channel_lower()`, `atr_channel_position()`
- **Lookback**: `max(window, atr_window)` bars
- **Warmup**: `window` bars

#### 3.7.3 Donchian Channel Width
- **Windows**: [5, 10, 20, 40, 80, 160, 252]
- **Compute function**: `donchian_width()` (HH - LL)
- **Lookback**: `window` bars
- **Warmup**: `window` bars

#### 3.7.4 HH/LL Distance
- **Windows**: [5, 10, 20, 40, 80, 160, 252]
- **Compute functions**: `distance_to_hh()`, `distance_to_ll()`
- **Lookback**: `window` bars
- **Warmup**: `window` bars

#### 3.7.5 Percentile Windows Expansion
- **New windows**: [63] (adds to existing [126, 252])
- **Compute function**: Existing `vx_percentile()`
- **Lookback**: `window` bars
- **Warmup**: `window` bars

## 4. Migration Plan

### 4.1 Phase 1: Schema Updates
1. Add `deprecated`, `notes`, `canonical_name` fields to both FeatureSpec models
2. Update `register_feature()` API to accept new parameters
3. Update `to_contract_spec()` and `from_contract_spec()` methods

### 4.2 Phase 2: Registry Enhancements
1. Modify duplicate detection to allow deprecated duplicates
2. Add filtering methods: `get_non_deprecated_features()`, `get_deprecated_features()`
3. Update `specs_for_tf()` to optionally exclude deprecated features

### 4.3 Phase 3: Deprecation Implementation
1. Mark existing `vx_percentile_*` features as deprecated
2. Add `canonical_name` references to point to `percentile_*` features
3. Verify backward compatibility with existing strategies

### 4.4 Phase 4: New Feature Registration
1. Implement new indicator functions in `numba_indicators.py`
2. Register new features for all timeframes (15, 30, 60, 120, 240)
3. Apply appropriate warmup rules and family assignments

### 4.5 Phase 5: Testing and Validation
1. Ensure all existing tests pass
2. Add tests for deprecation functionality
3. Verify causality verification for new features
4. Test backward compatibility with S1 strategy

## 5. Implementation Details

### 5.1 File Changes Required

#### 5.1.1 `src/contracts/features.py`
- Add `deprecated: bool = Field(default=False)`
- Add `notes: Optional[str] = Field(default=None)`

#### 5.1.2 `src/features/models.py`
- Add `deprecated: bool = Field(default=False)`
- Add `notes: Optional[str] = Field(default=None)`
- Add `canonical_name: Optional[str] = Field(default=None)`
- Update `to_contract_spec()` and `from_contract_spec()` methods

#### 5.1.3 `src/features/registry.py`
- Extend `register_feature()` signature with new parameters
- Modify duplicate detection logic
- Add filtering methods for deprecated features
- Update `specs_for_tf()` with `include_deprecated` parameter

#### 5.1.4 `src/features/seed_default.py`
- Update `compute_min_warmup_bars()` for new families
- Register new features with appropriate parameters
- Mark legacy features as deprecated
- Support all timeframes (15, 30, 60, 120, 240)

#### 5.1.5 `src/indicators/numba_indicators.py`
- Implement new indicator functions:
  - `bb_percent_b()`, `bb_width()`
  - `atr_channel_upper()`, `atr_channel_lower()`, `atr_channel_position()`
  - `donchian_width()`
  - `distance_to_hh()`, `distance_to_ll()`

### 5.2 Backward Compatibility

#### 5.2.1 Strategy S1 Compatibility
- S1 strategy uses `vx_percentile_126` and `vx_percentile_252`
- Deprecated aliases will continue to work
- No code changes required for existing strategies

#### 5.2.2 Feature Lookup Compatibility
- Existing code looking up features by name will continue to work
- Deprecated features remain in registry for lookup
- New code should use canonical names

#### 5.2.3 UI/Selection Lists
- Default to exclude deprecated features
- Option to show deprecated features for migration purposes
- Clear indication of deprecated status

## 6. Constraints and Considerations

### 6.1 Thread Safety
- Registry modifications must remain thread-safe
- Deprecation marking should not break concurrent lookups

### 6.2 Causality Verification
- All new features must pass causality verification
- Deprecated aliases inherit verification status from canonical features

### 6.3 Performance
- Additional fields have minimal memory impact
- Filtering logic should be efficient for large registries

### 6.4 Testing Requirements
- Existing tests must pass without modification
- New tests for deprecation functionality
- Integration tests for new feature families

## 7. Deliverables

1. **Updated FeatureSpec schema** with deprecation support
2. **Enhanced registry API** with deprecation parameters
3. **Deprecation alias mechanism** for backward compatibility
4. **Warmup rules table** for all feature families
5. **Family categorization table** for new features
6. **Parameter conventions** for each feature type
7. **Migration plan** from VX-first to source-agnostic names
8. **Implementation roadmap** with phased approach

## 8. Next Steps

1. **Review this design** for completeness and accuracy
2. **Switch to Code mode** for implementation
3. **Implement schema changes** (Phase 1)
4. **Add deprecation support** (Phase 2-3)
5. **Implement new features** (Phase 4)
6. **Test and validate** (Phase 5)

## Appendix A: Feature Matrix

| Feature | Windows | Family | Deprecated | Canonical Name |
|---------|---------|--------|------------|----------------|
| `bb_pb_{w}` | [5,10,20,40,80,160,252] | `bb` | No | - |
| `bb_width_{w}` | [5,10,20,40,80,160,252] | `bb` | No | - |
| `atr_ch_upper_{w}` | [5,10,14,20,40,80,160,252] | `atr_channel` | No | - |
| `atr_ch_lower_{w}` | [5,10,14,20,40,80,160,252] | `atr_channel` | No | - |
| `atr_ch_pos_{w}` | [5,10,14,20,40,80,160,252] | `atr_channel` | No | - |
| `donchian_width_{w}` | [5,10,20,40,80,160,252] | `donchian` | No | - |
| `dist_hh_{w}` | [5,10,20,40,80,160,252] | `distance` | No | - |
| `dist_ll_{w}` | [5,10,20,40,80,160,252] | `distance` | No | - |
| `percentile_{w}` | [63,126,252] | `percentile` | No | - |
| `vx_percentile_126` | [126] | `percentile` | Yes | `percentile_126` |
| `vx_percentile_252` | [252] | `percentile` | Yes | `percentile_252` |

## Appendix B: Warmup Rules Implementation

```python
def compute_min_warmup_bars(family: str, window: int) -> int:
    """Compute min_warmup_bars according to FEAT-1 warmup multipliers."""
    if family in ("ema", "adx"):
        return math.ceil(3 * window)
    # New families with 3× multiplier (if any)
    # elif family in ("new_family_with_3x", ...):
    #     return math.ceil(3 * window)
    # Standard 1× multiplier for all other families
    return window
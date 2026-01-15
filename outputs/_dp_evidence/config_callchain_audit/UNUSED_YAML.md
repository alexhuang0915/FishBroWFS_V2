# Unused/Legacy YAML Files

## Summary

This document lists YAML configuration files that are not loaded at runtime or are legacy/placeholder files. Each entry includes proof of non-usage and a recommendation.

## Unused Strategy YAMLs

### 1. `configs/strategies/sma_cross_v1.yaml`
- **Size**: 1261 bytes
- **Proof of Non-Usage**:
  - `rg -n "sma_cross_v1\\.yaml" src tests scripts` returns no matches
  - Not referenced in `strategy_catalog.yaml`
  - No `load_strategy("sma_cross_v1")` calls in source code
- **Dynamic Loading Check**: No glob patterns scan `configs/strategies/*.yaml`
- **Recommendation**: **DELETE** - Appears to be a placeholder/example file

### 2. `configs/strategies/S2.yaml`
- **Size**: 2537 bytes
- **Content**: Complete S2 strategy configuration with parameters, features, determinism
- **Proof of Non-Usage**:
  - `rg -n "S2\\.yaml" src tests scripts` returns no matches (except in configs directory)
  - Not listed in `strategy_catalog.yaml` (only `s1_v1` is listed)
  - No `load_strategy("S2")` calls in source code
  - S2 strategy implementation exists (`src/strategy/builtin/s2_v1.py`) but doesn't load this YAML
- **Dynamic Loading Check**: No dynamic scanning of strategy YAMLs
- **Recommendation**: **ARCHIVE or DELETE** - Orphaned despite complete configuration. Could be added to catalog if needed.

### 3. `configs/strategies/S3.yaml`
- **Size**: 2651 bytes
- **Content**: Complete S3 strategy configuration with parameters, features, determinism
- **Proof of Non-Usage**:
  - `rg -n "S3\\.yaml" src tests scripts` returns no matches (except in configs directory)
  - Not listed in `strategy_catalog.yaml`
  - No `load_strategy("S3")` calls in source code
  - S3 strategy implementation exists (`src/strategy/builtin/s3_v1.py`) but doesn't load this YAML
- **Dynamic Loading Check**: No dynamic scanning of strategy YAMLs
- **Recommendation**: **ARCHIVE or DELETE** - Orphaned despite complete configuration.

## Legacy Baseline YAMLs (Migrated)

### 4. `configs/strategies/S1/baseline.yaml`
- **Size**: 1323 bytes
- **Proof**: Appears to be migrated to `configs/strategies/s1_v1.yaml`
- **Evidence**: `tests/hygiene/test_configs_hygiene.py:45` mentions migration
- **Recommendation**: **DELETE** - Migrated legacy file

### 5. `configs/strategies/S2/baseline.yaml`
- **Size**: 1462 bytes
- **Proof**: Migration note in `S2.yaml:2`: "Migrated from configs/strategies/S2/baseline.yaml"
- **Recommendation**: **DELETE** - Migrated legacy file

### 6. `configs/strategies/S3/baseline.yaml`
- **Size**: 1557 bytes
- **Proof**: Migration note in `S3.yaml:2`: "Migrated from configs/strategies/S3/baseline.yaml"
- **Recommendation**: **DELETE** - Migrated legacy file

## Potentially Unused Portfolio YAML

### 7. `configs/portfolio/instruments.yaml`
- **Size**: 531 bytes (very small)
- **Usage Status**: **USED** but minimal
- **Proof of Usage**: Loaded by `src/portfolio/instruments.py:load_instrument_spec()` (line 53)
- **Recommendation**: **KEEP** - Actively used despite small size

## Empty/Near-Empty YAML Candidates

Check of files smaller than 16 bytes:
```bash
find configs -type f \( -name "*.yaml" -o -name "*.yml" \) -size -16c -print
```

**Result**: No empty YAML files found.

## Verification Methodology

1. **Reference Search**: Used `ripgrep` to search for each YAML filename in `src/`, `tests/`, `scripts/`
2. **Catalog Check**: Verified against `strategy_catalog.yaml` for strategy inclusion
3. **Loader Inspection**: Checked all `load_*` functions in `src/config/` and related modules
4. **Dynamic Pattern Search**: Searched for glob/scan patterns that might load files dynamically

## Recommendations Summary

| File | Status | Recommendation | Reason |
|------|--------|----------------|--------|
| `sma_cross_v1.yaml` | Unused placeholder | **DELETE** | No references, not in catalog |
| `S2.yaml` | Orphaned complete config | **ARCHIVE or DELETE** | Not in catalog, no references |
| `S3.yaml` | Orphaned complete config | **ARCHIVE or DELETE** | Not in catalog, no references |
| `S1/baseline.yaml` | Migrated legacy | **DELETE** | Superseded by `s1_v1.yaml` |
| `S2/baseline.yaml` | Migrated legacy | **DELETE** | Superseded by `S2.yaml` |
| `S3/baseline.yaml` | Migrated legacy | **DELETE** | Superseded by `S3.yaml` |

## Risk Assessment

- **Low Risk**: Deleting unused YAMLs won't affect runtime behavior
- **Medium Risk**: `S2.yaml` and `S3.yaml` contain complete configurations that might be intended for future use
- **Mitigation**: Archive rather than delete if uncertain, or add to `strategy_catalog.yaml` to activate them

## Action Plan

1. **Immediate Cleanup**:
   - Delete `sma_cross_v1.yaml`
   - Delete `S1/baseline.yaml`, `S2/baseline.yaml`, `S3/baseline.yaml`

2. **Decision Required**:
   - Decide fate of `S2.yaml` and `S3.yaml`:
     - Option A: Add to `strategy_catalog.yaml` to activate them
     - Option B: Archive to `configs/_legacy/` 
     - Option C: Delete (if never intended for use)

3. **Validation**:
   - Run `make check` after deletions to ensure no tests break
   - Verify UI still works (strategy dropdowns, research jobs)
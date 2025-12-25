# Stage0 Test Rationalization Analysis

**Date:** 2025-12-25  
**Operation:** OP-07 (Stage0 test rationalization)  
**Phase:** B-2 Execution  

## Current State

### Stage0 Test Files (5 files, 949 total lines)

1. **`test_stage0_contract.py`** (52 lines)
   - Core contract tests for Stage0 functionality
   - Tests basic Stage0 contract compliance
   - Low consolidation potential (essential)

2. **`test_stage0_ma_proxy.py`** (42 lines)
   - Tests MA proxy specific functionality
   - Proxy-specific validation
   - Medium consolidation potential (could merge with proxies.py)

3. **`test_stage0_no_pnl_contract.py`** (150 lines)
   - Tests that Stage0 doesn't compute PnL
   - Contract enforcement for proxy-only behavior
   - Low consolidation potential (core contract)

4. **`test_stage0_proxies.py`** (233 lines)
   - Tests multiple proxy implementations
   - Proxy comparison and validation
   - Medium consolidation potential

5. **`test_stage0_proxy_rank_corr.py`** (472 lines)
   - Tests proxy ranking correlation
   - Large, complex test with many scenarios
   - High consolidation potential (could be split or refactored)

## Consolidation Opportunities

### High Priority
1. **`test_stage0_proxy_rank_corr.py`** (472 lines)
   - Too large and complex
   - Could be split into:
     - `test_stage0_proxy_ranking.py` (core ranking logic)
     - `test_stage0_correlation.py` (correlation tests)
     - `test_stage0_performance.py` (performance tests)

2. **Merge proxy-related tests**
   - `test_stage0_ma_proxy.py` → `test_stage0_proxies.py`
   - Reduces file count while maintaining organization

### Medium Priority
1. **Consolidate contract tests**
   - `test_stage0_contract.py` and `test_stage0_no_pnl_contract.py` could potentially be merged
   - But they test different aspects (general contracts vs PnL prohibition)

### Low Priority
1. **Current organization is reasonable**
   - 5 files is manageable
   - Each has clear responsibility

## Recommended Actions

### Phase B-2 (Immediate)
1. **Merge `test_stage0_ma_proxy.py` into `test_stage0_proxies.py`**
   - Simple file merge
   - Reduces file count from 5 to 4
   - Maintains test coverage

2. **Create consolidation plan for `test_stage0_proxy_rank_corr.py`**
   - Document splitting strategy
   - Schedule for Phase C implementation

### Phase C (Future)
1. **Split `test_stage0_proxy_rank_corr.py`** into 2-3 smaller files
2. **Review test duplication** across all stage0 tests
3. **Optimize test execution time** if needed

## Risk Assessment

- **Low risk**: Merging `ma_proxy.py` into `proxies.py`
- **Medium risk**: Splitting large test file (requires careful refactoring)
- **High risk**: Merging contract tests (could lose test granularity)

## Decision

For Phase B-2, execute **Action 1 only** (merge `test_stage0_ma_proxy.py` into `test_stage0_proxies.py`).

## Verification

- Run `make check` after merge to ensure no test regressions
- Verify test count remains the same (all tests preserved)
- Ensure `test_stage0_ma_proxy.py` functionality is fully covered in merged file

## Next Steps

1. Execute the merge operation
2. Update test references if any
3. Run verification tests
4. Document results in Phase B-2 report
# Route 6 Governance Completion Patch - Summary

## Overview
This patch addresses three governance issues identified in Route 6 (Evidence → Portfolio → Deployment Closed Loop):
1. **Hardcoded "outputs/" paths** - Fixed by using SSOT `get_outputs_root()` from `core.paths`
2. **Pydantic v2 `Field(default_factory=Class)` violations** - Verified none exist (tests pass)
3. **Hash SSOT drift** - Consolidated `stable_config_hash` to match `stable_params_hash` canonicalization

## Changes Made

### Patch A: Remove Hardcoded Outputs Paths
**Files Modified:**
1. `src/control/supervisor/db.py`
   - Changed import from `from ..core.paths import get_outputs_root` to `from core.paths import get_outputs_root`
   - Updated `get_default_db_path` to use `get_outputs_root()` as default
2. `src/control/supervisor/bootstrap.py`
   - Added import `from core.paths import get_outputs_root`
   - Changed `args.artifacts_root = Path("outputs")` to `args.artifacts_root = get_outputs_root()`
3. `src/core/deployment/deployment_bundle_builder.py`
   - Added import `from ..paths import get_outputs_root`
   - Updated `__init__` method default: `outputs_root: Optional[Path] = None` with fallback to `get_outputs_root()`
   - Updated CLI argument default: `default=get_outputs_root()`

**SSOT Source:** `src/core/paths.py` - `get_outputs_root()` function

### Patch B: Pydantic v2 Default Factory Violations
**Discovery:** No violations found. The test `tests/hardening/test_qt_pydantic_pylance_guard.py::test_no_pydantic_default_factory_class` passes.

**Verification:** All Route 6 Pydantic models use correct syntax:
- `Field(default_factory=lambda: Class())` ✓
- `Field(default_factory=dict)` ✓
- `Field(default_factory=list)` ✓
- `Field(default_factory=lambda: datetime.now().isoformat())` ✓

### Patch C: Hash SSOT Decision
**Issue:** Two hash functions with different canonicalization:
1. `stable_params_hash` (in `src/contracts/supervisor/evidence_schemas.py`) - has full canonicalization
2. `stable_config_hash` (in `src/core/config_hash.py`) - simpler, missing `allow_nan=False` and canonicalization

**Solution:** Updated `stable_config_hash` to match `stable_params_hash` canonicalization.

**Files Modified:**
1. `src/core/config_hash.py`
   - Added `_canonicalize_for_json` function (same as in evidence_schemas)
   - Added `allow_nan=False` parameter to `json.dumps`
   - Ensures identical hashes for same input

**Verification:** Test confirms hashes match:
```python
test_dict = {'a': 1, 'b': 2, 'c': [3, 4, 5]}
hash1 = stable_config_hash(test_dict)    # da35805d1f41c0a1...
hash2 = stable_params_hash(test_dict)    # da35805d1f41c0a1...
# Hashes match: True
```

## Test Results

### Before Patch
- `make check` passed (1497 tests)
- Hardcoded outputs paths existed in 3 files
- Pydantic test passed (no violations)
- Hash functions produced different results for numpy/Decimal inputs

### After Patch
- `make check` passes (1497 tests) ✓
- Hardcoded outputs paths eliminated ✓
- Pydantic test passes ✓
- Hash functions produce identical results ✓
- All governance tests pass:
  - `test_no_outputs_hardcode.py` ✓
  - `test_qt_pydantic_pylance_guard.py` ✓
  - `test_params_hash_stability.py` ✓

## Evidence Files
1. `00_env.txt` - Environment capture
2. `01_rg_outputs_literal.txt` - Discovery of hardcoded outputs paths
3. `02_rg_pydantic_default_factory.txt` - Pydantic violations search
4. `03_rg_params_hash.txt` - Hash function usage analysis
5. `04_rg_outputs_path_providers.txt` - SSOT outputs path discovery
6. `05_pydantic_test_after.txt` - Pydantic test after patch
7. `06_pydantic_test_final.txt` - Pydantic test final
8. `07_hash_stability_test.txt` - Hash stability test
9. `08_outputs_hardcode_test.txt` - Outputs hardcode test
10. `09_make_check_after.txt` - Make check after initial changes
11. `10_make_check_final.txt` - Make check final (1497 passed)

## Compliance with Governance Constraints

### Hybrid BC v1.1 Compliance
- ✅ No backend API changes
- ✅ No portfolio math changes
- ✅ No UI behavior changes
- ✅ No new repo-root files

### Route 6 Closed Loop Integrity
- ✅ Evidence Aggregator unchanged
- ✅ Portfolio Orchestrator unchanged
- ✅ Deployment Bundle Builder updated (SSOT paths)
- ✅ Replay/Resolver unchanged

### Test Coverage
- ✅ All existing tests pass
- ✅ Hardening tests pass
- ✅ Governance tests pass
- ✅ No test weakening

## Conclusion
The Route 6 Governance Completion Patch successfully addresses all three governance issues while maintaining full backward compatibility and test coverage. The closed-loop system remains fully functional with improved governance hygiene.

**Status:** COMPLETE
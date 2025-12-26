# SYSTEM FULL SNAPSHOT - Phase G: Architectural Integrity

## Summary
Completed Phase G: Architectural Integrity (Rewire + Unify + Harden) with Policy Guillotine enforcement. All architectural boundaries between UI and backend are now strictly enforced with string-level bans.

## Key Achievements

### 1. Operation Rewire (UI must not bypass IntentBridge)
- **G1.1**: Created/updated policy test `test_gui_string_bans.py` to enforce no forbidden imports
- **G1.2**: Extended IntentBridge with required capabilities:
  - `list_descriptors()` - lists dataset descriptors
  - `invalidate_feature_cache()` - invalidates feature cache
  - `build_parquet_from_txt()` - builds parquet from text files
  - `get_build_parquet_types()` - returns build parquet types
- **G1.3**: Fixed `artifacts.py` to use bridge instead of direct imports
- **G1.4**: Fixed other GUI pages with forbidden imports
- **G1.5**: Fixed `reload_service.py` to use bridge/adapter pattern

### 2. Operation Unify (profiles move OUT of src/)
- **G2.1**: Created `configs/profiles/` directory
- **G2.2**: Moved profile YAMLs from `src/FishBroWFS_V2/data/profiles/` to `configs/profiles/`
- **G2.3**: Updated loader to resolve `configs/profiles/` first
- **G2.4**: Updated portfolio validation to use new profile paths
- **G2.5**: Updated portfolio examples with new profile paths

### 3. Operation Harden (tests must not break on file moves)
- **G3.1**: Added standard fixtures in `tests/conftest.py`:
  - `profiles_root` fixture pointing to `configs/profiles/`
  - `project_root` fixture
- **G3.2**: Refactored tests with fragile src-path hacks
- **G3.3**: Created `test_profiles_exist_in_configs.py`
- **G3.4**: Fixed manual tests with `sys.path.insert` patterns
- **G3.5**: Fixed policy tests using src paths

### 4. Policy Guillotine (String-level bans)
- **H++-1**: Created `test_gui_string_bans.py` with string-level bans for:
  - `FishBroWFS_V2.control.*` references in GUI files
  - `from FishBroWFS_V2.control` imports
  - `import FishBroWFS_V2.control` statements
  - `FishBroWFS_V2.outputs.jobs_db` references
  - `importlib.import_module("FishBroWFS_V2.control` patterns
- **H++-2**: Created `test_no_legacy_profiles_path_stringban.py` banning:
  - `FishBroWFS_V2/data/profiles` paths
  - `"src" / "FishBroWFS_V2" / "data" / "profiles"` patterns
- **H++-3**: Created `test_no_fragile_src_path_hacks.py` banning:
  - `Path(__file__).parent.parent / "src"` patterns
  - `sys.path.insert(0` hacks
  - `PYTHONPATH=src` patterns
- **H++-4**: Policy tests run in default test suite (46 policy tests)
- **H++-5**: Fixed all violations in `reload_service.py`
- **H++-6**: Verified all policy tests pass

## Technical Details

### IntentBridge Extension
The IntentBridge now provides all necessary functionality for UI components:
```python
class IntentBackendAdapter:
    # Existing methods...
    def list_descriptors(self) -> List[DatasetDescriptor]: ...
    def invalidate_feature_cache(self) -> bool: ...
    def build_parquet_from_txt(self, dataset_id: str) -> bool: ...
    def get_build_parquet_types(self) -> List[str]: ...
```

### Profile Resolution Order
1. `configs/profiles/` (new location)
2. `src/FishBroWFS_V2/data/profiles/` (old location, fallback)

### Test Fixtures
```python
# tests/conftest.py
@pytest.fixture
def profiles_root() -> Path:
    """Return path to configs/profiles directory."""
    return Path("configs/profiles")

@pytest.fixture
def project_root() -> Path:
    """Return project root directory."""
    return Path(__file__).parent.parent
```

## Verification Results

### Test Suite Status
- **Total tests**: 1017 passed, 23 skipped
- **Policy tests**: 46/46 passed
- **GUI tests**: All passing
- **Reload service tests**: 28/28 passing

### Architectural Boundaries
- ✅ Zero forbidden imports in GUI files
- ✅ Zero fragile test path patterns
- ✅ Profile loader prefers configs first
- ✅ IntentBridge provides all required functionality
- ✅ String-level bans prevent regression

### Files Modified/Created
1. `src/FishBroWFS_V2/gui/adapters/intent_bridge.py` - Extended with new methods
2. `src/FishBroWFS_V2/gui/services/reload_service.py` - Fixed to use bridge
3. `src/FishBroWFS_V2/portfolio/examples/portfolio_mvp_2026Q1.yaml` - Updated profile paths
4. `tests/policy/test_gui_string_bans.py` - Created
5. `tests/policy/test_no_legacy_profiles_path_stringban.py` - Created
6. `tests/policy/test_no_fragile_src_path_hacks.py` - Created
7. `tests/policy/test_profiles_exist_in_configs.py` - Created
8. `tests/conftest.py` - Added fixtures
9. Multiple test files updated to use fixtures

## Impact
- **Architectural Integrity**: UI can no longer bypass IntentBridge
- **Test Robustness**: Tests no longer break on file moves
- **Profile Management**: Profiles moved out of source code directory
- **Policy Enforcement**: String-level bans make it impossible to reintroduce violations
- **Maintainability**: Clear separation between UI and backend layers

## Next Steps
The architectural boundaries are now strictly enforced. Future development must:
1. Use IntentBridge for all UI→backend communication
2. Store profiles in `configs/profiles/`
3. Use test fixtures instead of fragile path hacks
4. Run policy tests to catch violations early

---
**Generated**: 2025-12-25T19:20:22Z  
**Phase**: G - Architectural Integrity  
**Status**: COMPLETED ✅
# DISCOVERY - Governance Cleanup: Bars Gates + OpenAPI Snapshot

## Discovery Queries and Results

### Query 1: Hardcoded path in `src/` (`"/tmp"` and `"test_bars.npz"` and `"hardcoded_paths"`)

**Results:**
- Found hardcoded path in `src/core/bars_contract.py:701-707`:
  ```python
  with tempfile.TemporaryDirectory() as tmpdir:
      test_file = Path(tmpdir) / "test_bars.npz"
      result = validate_bars(test_file)
      print(f"\nTest 1 - Non-existent file:")
      print(f"  Gate A: {'PASS' if result.gate_a_passed else 'FAIL'} - {result.gate_a_error}")
      print(f"  Gate B: {'PASS' if result.gate_b_passed else 'FAIL'} - {result.gate_b_error}")
      print(f"  Gate C: {'PASS' if result.gate_c_passed else 'FAIL'} - {result.gate_c_error}")
  ```
- This is in the `__main__` section of the module, used for demo/debug purposes
- The test uses `tempfile.TemporaryDirectory()` which is acceptable, but the pattern `/tmp/test_bars.npz` appears in the code
- The actual hardcoded `/tmp/` path was previously at line 700 but was already fixed to use `tempfile.TemporaryDirectory()`

**Key Finding:** The hardcoded path issue has already been partially addressed, but the `__main__` section contains demo code that should be removed from production `src/` files.

### Query 2: OpenAPI snapshot lock test and expected snapshot file (`"openapi_snapshot_lock"` and `"contract_snapshots/openapi.json"` and `"api-snapshot"`)

**Results:**
- Found test file: `tests/test_openapi_snapshot_lock.py`
- Snapshot path: `tests/contract_snapshots/openapi.json`
- Test failure indicates JSON decode error: `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
- This suggests the file is empty or corrupted
- Test instructions for updating snapshot:
  ```python
  python -c "from src.control.api import app; import json; import sys; json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)" > tests/contract_snapshots/openapi.json
  ```

### Query 3: Project's intended "update snapshot" mechanism (`"make api-snapshot"`)

**Results:**
- Found `api-snapshot` target in `Makefile` (lines 138-141):
  ```makefile
  api-snapshot:
      @mkdir -p tests/policy/api_contract
      @$(PYTHON) -c "import json; from pathlib import Path; from control.api import app; out = Path('tests/policy/api_contract/openapi.json'); out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True), encoding='utf-8'); print(f'[api-snapshot] wrote: {out} ({out.stat().st_size} bytes)')"
  ```
- **Important Note:** The Makefile target writes to `tests/policy/api_contract/openapi.json` but the failing test expects `tests/contract_snapshots/openapi.json`
- There are two different snapshot locations:
  1. `tests/policy/api_contract/openapi.json` (used by `tests/policy/test_api_contract.py`)
  2. `tests/contract_snapshots/openapi.json` (used by `tests/test_openapi_snapshot_lock.py`)

**Key Finding:** There are two different OpenAPI snapshot files with different paths. The failing test uses `tests/contract_snapshots/openapi.json` which appears to be empty/corrupted.

## Analysis

### Issue 1: Hardcoded Paths
- The `src/core/bars_contract.py` `__main__` section contains demo/test code that should not be in production `src/` files
- The code uses `tempfile.TemporaryDirectory()` which is acceptable, but demo code in `src/` violates governance rules
- **Solution:** Remove the `__main__` section entirely from `src/core/bars_contract.py`

### Issue 2: OpenAPI Snapshot Corruption
- `tests/contract_snapshots/openapi.json` is empty/corrupted (0 bytes or invalid JSON)
- The test expects this file to contain valid OpenAPI JSON schema
- **Solution:** Regenerate the snapshot using the correct import path (`control.api` not `src.control.api`) with proper PYTHONPATH

## Implementation Plan

### For Issue 1:
1. Remove the entire `__main__` section from `src/core/bars_contract.py`
2. Ensure no other hardcoded `/tmp` paths exist in `src/`

### For Issue 2:
1. Check if `tests/contract_snapshots/openapi.json` exists and is valid JSON
2. If corrupted/empty, regenerate using:
   ```bash
   PYTHONPATH=src python3 -c "from control.api import app; import json,sys; json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)" > tests/contract_snapshots/openapi.json
   ```
3. Verify the generated file is valid JSON

## Verification Commands

After fixes:
1. `rg -n '"/tmp"|/tmp/test_bars\.npz' src/` should return no matches
2. `python -c "import json; json.load(open('tests/contract_snapshots/openapi.json','r',encoding='utf-8')); print('openapi.json OK')"` should succeed
3. `pytest -q tests/test_openapi_snapshot_lock.py` should pass
4. `make check` should pass with 0 failures
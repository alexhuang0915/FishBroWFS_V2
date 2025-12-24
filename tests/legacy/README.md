# Legacy/Integration Tests

This directory contains legacy and integration tests that were originally in the `tools/` directory. These tests have been converted to proper pytest tests with appropriate markers and environment variable gating.

## Test Files

- `test_api.py` - Tests for API endpoints (requires running Control API server)
- `test_app_start.py` - Tests for GUI application startup and structure
- `test_gui_integration.py` - Tests for GUI service integrations
- `test_nicegui.py` - Tests for NiceGUI application imports
- `test_nicegui_submit.py` - Tests for NiceGUI job submission API
- `test_p0_completion.py` - Validation tests for P0 task completion

## Running These Tests

These tests are marked with `@pytest.mark.integration` and are skipped by default. To run them, you must:

1. Set the environment variable:
   ```bash
   export FISHBRO_RUN_INTEGRATION=1
   ```

2. Run pytest with the integration marker:
   ```bash
   pytest tests/legacy/ -m integration -v
   ```

Or run all tests (including integration tests):
```bash
FISHBRO_RUN_INTEGRATION=1 pytest tests/legacy/ -v
```

## Why They Are Skipped By Default

These tests require:
- External services (API servers, GUI applications)
- Specific system state (running servers on specific ports)
- Potentially long execution times
- Network connectivity

By skipping them by default, we ensure:
- Fast CI/CD pipeline execution
- No false failures due to missing external dependencies
- Clear separation between unit tests and integration tests

## Test Characteristics

### API Tests (`test_api.py`)
- Requires Control API server running on `127.0.0.1:8000`
- Tests endpoints: `/batches/test/status`, `/batches/test/summary`, `/batches/frozenbatch/retry`
- Validates response structure and status codes

### GUI Application Tests (`test_app_start.py`)
- Tests GUI application imports and structure
- Validates theme injection, layout functions, navigation structure
- Requires NiceGUI and related dependencies

### GUI Integration Tests (`test_gui_integration.py`)
- Tests GUI service modules (runs_index, archive, clone, etc.)
- Validates service functionality and imports
- May require specific directory structures

### NiceGUI Tests (`test_nicegui.py`, `test_nicegui_submit.py`)
- Tests NiceGUI application imports and API
- Validates job submission request structure
- May require NiceGUI server running on `localhost:8080`

### P0 Completion Tests (`test_p0_completion.py`)
- Validates P0 task completion by checking file existence
- Tests navigation structure matches requirements
- Ensures GUI services are properly implemented

## Adding New Integration Tests

When adding new integration tests:

1. Use the `@pytest.mark.integration` decorator
2. Add environment variable check at the beginning of each test function:
   ```python
   if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":
       pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1")
   ```
3. Provide clear error messages for failures
4. Document any external dependencies in this README

## Maintenance Notes

These tests were migrated from `tools/` directory and converted from scripts returning `True/False` to proper pytest tests using `assert` statements. The conversion ensures:
- Proper test discovery by pytest
- No `PytestReturnNotNoneWarning` warnings
- Clear pass/fail reporting
- Integration with existing test infrastructure
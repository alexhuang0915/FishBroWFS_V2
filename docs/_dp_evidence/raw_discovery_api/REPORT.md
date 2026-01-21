# REPORT - RAW Discovery API Implementation

## Executive Summary
**STATUS**: ✅ COMPLETE

The RAW Discovery API has been successfully implemented and wired to the BarPrepare RAW INPUT Dialog. The implementation follows the governance pattern of registry endpoints, provides path traversal protection, and eliminates direct filesystem scanning from Qt widgets.

## Implementation Details

### 1. Backend API Endpoint (`/api/v1/registry/raw`)
**Location**: `src/control/api.py` (lines added: ~50-150)

**Features**:
- **Cache-based**: Uses `_RAW_FILES` cache variable, loaded at supervisor startup via `_try_prime_registries()`
- **Path traversal protection**: Uses `_load_raw_files_from_fs()` with `FishBroData/raw/` as root directory
- **File filtering**: Returns only `.txt` files (matching raw data format)
- **Error handling**: Returns 503 if cache not preloaded (consistent with other registry endpoints)
- **Consistent pattern**: Follows same structure as `/api/v1/registry/datasets`, `/api/v1/registry/strategies`, etc.

**Code Highlights**:
```python
# Cache variable
_RAW_FILES: list[str] | None = None

# Load function with path traversal protection
def _load_raw_files_from_fs() -> list[str]:
    raw_dir = Path(__file__).parent.parent.parent.parent / "FishBroData" / "raw"
    if not raw_dir.exists():
        return []
    files = []
    for path in raw_dir.iterdir():
        if path.is_file() and path.suffix.lower() == ".txt":
            files.append(path.name)
    return sorted(files)

# Endpoint
@router.get("/registry/raw", summary="Registry Raw")
def registry_raw() -> list[str]:
    if _RAW_FILES is None:
        raise HTTPException(status_code=503, detail="Raw files cache not loaded")
    return _RAW_FILES
```

### 2. Supervisor Client (`get_raw_files()`)
**Location**: `src/gui/desktop/services/supervisor_client.py`

**Features**:
- **Method added**: `get_raw_files() -> List[str]` in `SupervisorClient` class
- **Public API**: Added `get_raw_files()` public function
- **Error classification**: Inherits existing error handling (network, validation, server errors)
- **__all__ export**: Added to module exports for proper import

**Code Highlights**:
```python
def get_raw_files(self) -> List[str]:
    """Return list of raw file names from FishBroData/raw/."""
    return self._get("/api/v1/registry/raw")
```

### 3. UI Wiring (`RawInputDialog._discover_raw_files()`)
**Location**: `src/gui/desktop/dialogs/raw_input_dialog.py`

**Changes**:
- **Removed**: Local filesystem scanning of `data/raw`, `data/raw_inputs`, `outputs/raw_inputs`
- **Added**: API call to `get_raw_files()` with error handling
- **Graceful degradation**: Returns empty list on API failure (UI shows "No raw inputs discovered")
- **Import**: Added `from ..services.supervisor_client import get_raw_files, SupervisorClientError`

**Code Highlights**:
```python
def _discover_raw_files(self) -> List[str]:
    """Discover raw input files via Supervisor API."""
    try:
        files = get_raw_files()
        logger.debug(f"Retrieved {len(files)} raw files from supervisor API")
        return sorted(files)
    except SupervisorClientError as e:
        logger.warning(f"Failed to fetch raw files from supervisor API: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching raw files: {e}")
        return []
```

## Testing & Verification

### 1. API Contract Test
- **Test**: `tests/policy/test_api_contract.py`
- **Result**: ✅ PASSED (after updating snapshot with `make api-snapshot`)
- **Evidence**: OpenAPI schema now includes `/api/v1/registry/raw` endpoint with proper documentation

### 2. General Test Suite
- **Command**: `make check`
- **Result**: ✅ PASSED (2080 selected, 0 failures after snapshot update)
- **Note**: One test failure was expected due to new endpoint; resolved by updating API snapshot

### 3. Import Verification
- All modified files import correctly
- No circular dependencies introduced
- Qt dependencies remain unchanged

## Compliance Checklist

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Supervisor/API-provided RAW inventory discovery | ✅ | `/api/v1/registry/raw` endpoint implemented |
| No direct filesystem scanning from Qt widgets | ✅ | `RawInputDialog._discover_raw_files()` uses API |
| Path traversal protection | ✅ | `_load_raw_files_from_fs()` uses fixed root directory |
| Cache priming at supervisor startup | ✅ | `_try_prime_registries()` calls `load_raw_files()` |
| Error handling in UI | ✅ | Try/except with graceful fallback to empty list |
| Follows registry endpoint pattern | ✅ | Same structure as other `/api/v1/registry/*` endpoints |
| No backend API changes (only addition) | ✅ | Only new endpoint added, no modifications to existing |
| No evidence storage semantics changes | ✅ | Raw file listing only, no evidence path changes |
| All tests pass | ✅ | `make check` passes after API snapshot update |

## Root Hygiene
- ✅ No new files created in repo root
- ✅ Evidence files only under `outputs/_dp_evidence/raw_discovery_api/`
- ✅ Working tree clean except for evidence files

## Risks & Follow-ups

### None Identified
- The implementation is minimal and follows established patterns
- Error handling is robust (graceful degradation)
- API endpoint is read-only and has path traversal protection
- Cache ensures no filesystem access during request handling

### Potential Enhancements (Optional)
1. **UI Feedback**: Could show error message to user when API fails (currently silent fallback)
2. **Refresh Button**: Could add manual refresh button in dialog
3. **File Metadata**: Could extend API to return file sizes/modification dates

## Conclusion
The RAW Discovery API implementation successfully delivers:
1. **Offline discovery** via Supervisor API endpoint
2. **Secure path traversal protection**
3. **Consistent registry pattern** integration
4. **UI wiring** that eliminates direct filesystem access
5. **Full test compliance** with existing test suite

The solution is production-ready and maintains all governance constraints.
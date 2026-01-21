# DISCOVERY - RAW Discovery API Implementation

## Codebase Search Logs

### Query 1: "RawInputDialog class definition"
**Purpose**: Find the RAW INPUT dialog implementation
**Results**:
- File: `src/gui/desktop/dialogs/raw_input_dialog.py`
- Key finding: Dialog uses `_discover_raw_files()` method that scans local directories
- Current implementation scans `data/raw`, `data/raw_inputs`, `outputs/raw_inputs`
- Needs to be replaced with API call

### Query 2: "supervisor_client import"
**Purpose**: Find how other dialogs import and use supervisor client
**Results**:
- File: `src/gui/desktop/dialogs/run_intent_dialog.py`
- Pattern: `from gui.desktop.services.supervisor_client import (get_registry_strategies, ...)`
- Error handling: Uses `SupervisorClientError`
- This establishes the import pattern to follow

### Query 3: "registry endpoints"
**Purpose**: Find existing registry endpoint patterns
**Results**:
- File: `src/control/api.py`
- Endpoints: `/api/v1/registry/datasets`, `/api/v1/registry/strategies`, `/api/v1/registry/instruments`, `/api/v1/registry/timeframes`
- Pattern: Simple GET endpoints returning list of strings
- Cache variables: `_DATASETS`, `_STRATEGIES`, etc.
- 503 response if cache not loaded
- No filesystem access during request handling

### Query 4: "FishBroData/raw path"
**Purpose**: Find where raw data directory is referenced
**Results**:
- File: `src/control/prepare_orchestration.py`
- Function: `_find_txt_path_for_feed`
- Path: `FishBroData/raw/` relative to workspace root
- Confirms raw data location

### Query 5: "cache priming"
**Purpose**: Find how registry caches are loaded
**Results**:
- File: `src/control/api.py`
- Function: `_try_prime_registries()`
- Calls: `load_datasets()`, `load_strategies()`, `load_instruments()`, `load_timeframes()`
- Pattern: Cache loading at supervisor startup
- Need to add `load_raw_files()` to this function

### Query 6: "get_raw_files mock"
**Purpose**: Check if any tests mock raw files discovery
**Results**:
- No existing `get_raw_files` function found (confirms this is new functionality)
- Tests for raw input dialog likely use mocked filesystem

## Key Discoveries

### 1. Architecture Pattern
- **Registry endpoints**: Simple GET → list of strings
- **Cache priming**: At supervisor startup via `_try_prime_registries()`
- **Error handling**: 503 if cache not loaded
- **UI integration**: Supervisor client methods with error classification

### 2. Current RAW Input Implementation
- **Location**: `src/gui/desktop/dialogs/raw_input_dialog.py`
- **Method**: `_discover_raw_files()` scans multiple directories
- **File types**: Looks for `.csv`, `.parquet`, `.json` (but raw data is `.txt`)
- **Issue**: Direct filesystem access violates "no Qt widget filesystem scanning" requirement

### 3. Supervisor Client Pattern
- **Location**: `src/gui/desktop/services/supervisor_client.py`
- **Methods**: `get_datasets()`, `get_strategies()`, `get_instruments()`, `get_timeframes()`
- **Error types**: `SupervisorClientError` with classification (network, validation, server)
- **Public API**: Functions exported in `__all__` list

### 4. Path Structure
- **Raw data root**: `FishBroData/raw/` (relative to workspace)
- **Workspace root**: Can be derived from `Path(__file__).parent.parent.parent.parent`
- **Security**: Need path traversal protection

## Implementation Decisions Based on Discovery

### 1. API Endpoint Design
- **Path**: `/api/v1/registry/raw` (consistent with registry pattern)
- **Response**: `List[str]` of `.txt` filenames only
- **Cache**: `_RAW_FILES` variable, loaded via `load_raw_files()`
- **Error**: 503 if cache not loaded

### 2. Cache Loading
- **Add to**: `_try_prime_registries()` and `_prime_registries_with_feedback()`
- **Function**: `load_raw_files()` that calls `_load_raw_files_from_fs()`
- **Path traversal**: Use fixed `FishBroData/raw/` directory

### 3. Supervisor Client
- **Add method**: `get_raw_files()` returning `List[str]`
- **Add to __all__**: Export for public use
- **Error handling**: Inherit existing error classification

### 4. UI Integration
- **Replace**: `_discover_raw_files()` with API call
- **Import**: `from ..services.supervisor_client import get_raw_files, SupervisorClientError`
- **Error handling**: Try/except with graceful fallback to empty list
- **Logging**: Log warnings on API failure

## Evidence of Compliance

### No Direct Filesystem Scanning
- ✅ Removed `Path("data/raw")`, `Path("data/raw_inputs")`, `get_outputs_root() / "raw_inputs"` scanning
- ✅ Replaced with `get_raw_files()` API call

### Path Traversal Protection
- ✅ API uses fixed `FishBroData/raw/` directory
- ✅ No user input in path construction
- ✅ `Path.iterdir()` only lists files in designated directory

### Cache Safety
- ✅ No filesystem access in endpoint handler
- ✅ Returns cached `_RAW_FILES` only
- ✅ 503 if cache not loaded

### Consistent Pattern
- ✅ Follows same structure as other registry endpoints
- ✅ Same error handling (503 for unloaded cache)
- ✅ Same supervisor client method pattern

## Search Queries Executed
1. `RawInputDialog class definition`
2. `supervisor_client import`  
3. `registry endpoints`
4. `FishBroData/raw path`
5. `cache priming`
6. `get_raw_files mock`

All discoveries informed the implementation design and ensured compliance with existing patterns.
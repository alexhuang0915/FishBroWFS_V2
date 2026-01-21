# DISCOVERY.md - RAW Root Resolution Bug Patch

## Query 1: `/api/v1/registry/raw` endpoint definition
**File**: `src/control/api.py`
**Lines**: 770-791
**Code**:
```python
@api_v1.get("/registry/raw")
async def registry_raw() -> list[str]:
    """
    Return list of raw file names (simple strings) from FishBroData/raw/.
    
    Contract:
    - Returns simple array of strings, e.g., ["MNQ HOT-Minute-Trade.txt", ...]
    - If raw files cache not loaded, returns 503.
    - Must not access filesystem during request handling.
    """
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_raw_files")

    # Enforce no filesystem access during request handling
    if _RAW_FILES is None and current is _LOAD_RAW_FILES_ORIGINAL:
        raise HTTPException(status_code=503, detail="Raw files registry not preloaded")

    files = load_raw_files()
    # Return sorted file names for consistency
    return sorted(files)
```

## Query 2: `_load_raw_files_from_fs()` implementation
**File**: `src/control/api.py`
**Lines**: 376-387
**Code**:
```python
def _load_raw_files_from_fs() -> list[str]:
    """Private implementation: scan FishBroData/raw directory for .txt files."""
    workspace_root = Path(__file__).parent.parent.parent.parent
    raw_dir = workspace_root / "FishBroData" / "raw"
    if not raw_dir.exists():
        return []
    files = []
    for entry in raw_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".txt":
            files.append(entry.name)
    return sorted(files)
```

## Query 3: `_RAW_FILES` cache and related functions
**File**: `src/control/api.py`
**Lines**: 178, 389-420
**Code**:
```python
_RAW_FILES: list[str] | None = None  # Raw file names from FishBroData/raw/

def _get_raw_files() -> list[str]:
    """Return cached raw files, loading if necessary."""
    global _RAW_FILES
    if _RAW_FILES is None:
        _RAW_FILES = _load_raw_files_from_fs()
    return _RAW_FILES

def _reload_raw_files() -> list[str]:
    """Force rescan raw directory and update cache."""
    global _RAW_FILES
    _RAW_FILES = _load_raw_files_from_fs()
    return _RAW_FILES

def load_raw_files() -> list[str]:
    """Load raw files. Supports monkeypatching."""
    import sys
    module = sys.modules[__name__]
    current = getattr(module, "load_raw_files")

    # If monkeypatched, call patched function
    if current is not _LOAD_RAW_FILES_ORIGINAL:
        return current()

    # If cache is available, return it
    if _RAW_FILES is not None:
        return _RAW_FILES

    # Fallback for CLI/unit-test paths (may touch filesystem)
    return _load_raw_files_from_fs()
```

## Query 4: Cache priming in supervisor startup
**File**: `src/control/api.py`
**Lines**: 430-454, 516-523
**Code**:
```python
def _try_prime_registries() -> None:
    """Prime cache on startup (per‑load tolerance)."""
    global _DATASET_INDEX, _STRATEGY_REGISTRY, _INSTRUMENTS_CONFIG, _TIMEFRAME_REGISTRY, _RAW_FILES
    # Try each load independently; if one fails, set its cache to None but continue.
    try:
        _DATASET_INDEX = load_dataset_index()
    except Exception:
        _DATASET_INDEX = None
    try:
        _STRATEGY_REGISTRY = load_strategy_registry()
    except Exception:
        _STRATEGY_REGISTRY = None
    try:
        _INSTRUMENTS_CONFIG = load_instruments_config()
    except Exception:
        _INSTRUMENTS_CONFIG = None
    try:
        _TIMEFRAME_REGISTRY = load_timeframe_registry()
    except Exception:
        _TIMEFRAME_REGISTRY = None
    try:
        _RAW_FILES = load_raw_files()
    except Exception:
        _RAW_FILES = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # startup
    # No DB initialization - supervisor owns the DB
    # Phase 12: Prime registries cache
    _try_prime_registries()

    yield
    # shutdown (currently empty)
```

## Query 5: Path resolution comparison with other endpoints
**File**: `src/control/api.py`
**Lines**: 798-801 (WFS policies endpoint)
**Code**:
```python
@api_v1.get("/wfs/policies", response_model=WfsPolicyRegistryResponse)
async def list_wfs_policies_endpoint() -> WfsPolicyRegistryResponse:
    """
    Enumerate available WFS policy YAMLs.
    """
    repo_root = Path(__file__).resolve().parents[2]
    entries = list_wfs_policies(repo_root=repo_root)
    serialized = [asdict(entry) for entry in entries]
    return WfsPolicyRegistryResponse(entries=serialized)
```

## Analysis of the Bug

### Root Cause
The bug is in `_load_raw_files_from_fs()` at line 378:
```python
workspace_root = Path(__file__).parent.parent.parent.parent
```

Given the file location `src/control/api.py`, this resolves to:
- `Path(__file__)` = `/home/fishbro/FishBroWFS_V2/src/control/api.py`
- `.parent` = `/home/fishbro/FishBroWFS_V2/src/control/`
- `.parent.parent` = `/home/fishbro/FishBroWFS_V2/src/`
- `.parent.parent.parent` = `/home/fishbro/FishBroWFS_V2/`
- `.parent.parent.parent.parent` = `/home/fishbro/` ← **INCORRECT!**

The correct computation should be `Path(__file__).resolve().parents[2]` (go up 2 levels from resolved path).

### Comparison with Working Endpoint
The WFS policies endpoint at line 798 uses:
```python
repo_root = Path(__file__).resolve().parents[2]
```
This correctly computes the repo root as `/home/fishbro/FishBroWFS_V2/`.

### Impact
The raw directory path becomes:
- Incorrect: `/home/fishbro/FishBroData/raw/` (doesn't exist or empty)
- Correct: `/home/fishbro/FishBroWFS_V2/FishBroData/raw/` (contains actual .txt files)

This explains why the API returns empty array `[]`.

## Required Fix
1. Change line 378 from `Path(__file__).parent.parent.parent.parent` to `Path(__file__).resolve().parents[2]`
2. Add a helper function `_get_repo_root()` for consistency and testability
3. Add defensive assertion to verify the raw directory exists under repo root
4. Add unit test with monkeypatching capability

## Related Code Patterns
The codebase uses similar patterns for other registry loading functions:
- `_load_dataset_index_from_file()` uses `Path("outputs/datasets/datasets_index.json")` (relative to CWD)
- `_load_instruments_config_from_file()` uses `Path("configs/portfolio/instruments.yaml")` (relative to CWD)
- `_load_timeframe_registry_from_file()` imports from `config.registry.timeframes`

The raw files loading is unique in needing to compute repo root to find `FishBroData/raw/`.
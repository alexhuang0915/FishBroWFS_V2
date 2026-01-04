# SUPERVISOR_PHASE2_MIGRATION_MAP

## Phase 2 Migration Analysis
**Date**: 2026-01-04  
**Phase**: 2 (Strangler Migration of Real Jobs to Supervisor)  
**Goal**: Migrate real job entrypoints to Supervisor handlers one-by-one

## 1. CLEAN_CACHE

### Legacy Makefile Target(s)
- `clean-cache` (declared in .PHONY line 34, but no implementation found)
- `clean-caches` (declared in .PHONY line 34, but no implementation found)
- `clean-caches-dry` (declared in .PHONY line 34, but no implementation found)

### Legacy Python Entrypoint(s)
1. **`CleanupService`** in `src/gui/desktop/services/cleanup_service.py`
   - `_build_cache_plan()` method (lines 185-231): Builds plan for deleting cache data
   - `cleanup_cache()` convenience function (lines 478-488): Public interface for cache cleanup
   - Scope: `CleanupScope.CACHE`

2. **`cleanup_cache()`** function (line 478): Convenience function that calls `CleanupService.cleanup_cache()`

### Observed Inputs/Outputs
**Inputs** (from `_build_cache_plan`):
- `season`: str (default: current season)
- `market`: str (required, e.g., "ES", "NQ", "RTY", "CL")
- `cache_type`: str (default: "both", options: "bars", "features", "both")

**Outputs**:
- Returns `Tuple[bool, str]`: (success, message)
- Moves cache files to `outputs/_trash` (soft delete)
- Creates audit log in `outputs/_dp_evidence/cleanup_audit.jsonl`

### Notes
The cache cleaning logic is implemented in the Qt Desktop UI cleanup service. It deletes:
1. Bars cache: `*.npz` files in `outputs/seasons/{season}/shared/{market}/`
2. Features cache: All files in `outputs/seasons/{season}/shared/{market}/features/`

## 2. BUILD_DATA

### Legacy Makefile Target(s)
**NOT FOUND**: No `build-data` target found in Makefile.

### Legacy Python Entrypoint(s)
1. **`prepare_with_data2_enforcement`** in `src/control/prepare_orchestration.py`
   - Called from Qt Desktop UI (`src/gui/desktop/worker.py:255`)
   - Used for "Prepare data" operations
   - Returns results with `data1_report` and `data2_reports`

2. **`build_shared`** function (likely from `src/control/shared_build.py`)
   - Called by `prepare_with_data2_enforcement`
   - Builds bars and features caches

### Observed Inputs/Outputs
**Inputs** (from `prepare_with_data2_enforcement`):
- `mode`: str (e.g., "BARS_ONLY", "FEATURES_ONLY", "FULL")
- `season`: str
- `dataset_id`: str
- `timeframe_min`: int
- `force_rebuild`: bool (default False)

**Outputs**:
- `data1_report`: dict from `build_shared`
- `data2_reports`: dict mapping feed_id -> report
- `data2_fingerprints`: dict mapping feed_id -> fingerprint path
- `data2_manifest_paths`: dict mapping feed_id -> manifest path

### Notes
The BUILD_DATA operation appears to be the "prepare data" functionality in Qt Desktop UI. It uses the shared build pipeline.

## 3. GENERATE_REPORTS

### Legacy Makefile Target(s)
**NOT FOUND**: No `generate-reports` target found in Makefile.

### Legacy Python Entrypoint(s)
1. **`scripts/generate_research.py`**
   - Main script for generating research artifacts
   - Generates `canonical_results.json` and `research_index.json`
   - Calls `generate_canonical_results` from `research.__main__`

2. **`generate_canonical_results`** in `src/research/__main__.py`
   - Scans outputs directory for research runs
   - Extracts metrics using `extract_canonical_metrics`
   - Writes `canonical_results.json`

3. **`extract_canonical_metrics`** in `src/research/extract.py`
   - Extracts canonical metrics from a run directory

### Observed Inputs/Outputs
**Inputs**:
- `outputs_root`: Path to outputs directory (default: "outputs")
- `season`: Optional season filter

**Outputs**:
- `canonical_results.json`: List of all CanonicalMetrics as dicts
- `research_index.json`: Index of research runs

### Notes
This appears to be the canonical reporting pipeline that generates research artifacts for analysis.

## 4. RUN_RESEARCH (Deferred - Do NOT touch in Phase 2)

### Legacy Makefile Target(s)
- `run-research` (line 146): Calls `scripts/run_research_v3.py`

### Legacy Python Entrypoint(s)
1. **`scripts/run_research_v3.py`**
   - Main research runner script

### Observed Inputs/Outputs
**Deferred**: Will be addressed in later phase.

## Migration Strategy

### CLEAN_CACHE Handler
**Implementation Plan**:
1. Create handler that calls `CleanupService.cleanup_cache()` or uses `CleanupService` directly
2. Map Supervisor parameters to cache cleaning parameters:
   - `scope`: Map to "season", "dataset", or "all"
   - `season`: Use when scope == "season"
   - `dataset_id`: Map to market when scope == "dataset"
   - `dry_run`: Use `build_delete_plan` for preview, `execute_soft_delete` for actual
3. Capture results and return standardized output
4. Support dry-run as specified in contract

### BUILD_DATA Handler
**Implementation Plan**:
1. Create handler that calls `prepare_with_data2_enforcement`
2. Capture stdout/stderr via subprocess or direct function call
3. Map parameters from Supervisor job to function arguments
4. Return standardized result dict

### GENERATE_REPORTS Handler
**Implementation Plan**:
1. Create handler that calls `scripts/generate_research.py` via subprocess
2. Or call `generate_canonical_results` directly
3. Capture stdout/stderr
4. Return standardized result dict with report paths

## Next Steps
1. ~~Investigate CLEAN_CACHE actual implementation~~ **COMPLETED**
2. Create handler files in `src/control/supervisor/handlers/`
3. Update `src/control/supervisor/handlers/__init__.py`
4. Update Makefile with strangler targets
5. Add contract tests
6. Run evidence collection

## Evidence Files Created
- `outputs/_dp_evidence/phase2_step0_make_check_before.txt`
- `outputs/_dp_evidence/phase2_step0_entrypoints_before_rg.txt`
- `outputs/_dp_evidence/phase2_step1_clean_cache_rg.txt`
- `outputs/_dp_evidence/phase2_step1_build_data_rg.txt`
- `outputs/_dp_evidence/phase2_step1_generate_reports_rg.txt`
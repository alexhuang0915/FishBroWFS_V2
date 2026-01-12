# FINAL-P0-B-INTEGRATION: Make contracts.api the real SSOT

## Summary
Successfully turned `src/contracts/api.py` into the effective single source of truth for API payload models, removing inline Pydantic models from `src/control/api.py`.

## Changes Made

### 1. Fixed mutable defaults in `src/contracts/api.py`
- Added `from pydantic import Field`
- Changed `BatchSummaryResponse` fields:
  - `strategies: list = []` → `strategies: list = Field(default_factory=list)`
  - `metadata: dict = {}` → `metadata: dict = Field(default_factory=dict)`
- Ensures Pydantic v2 safe mutable defaults.

### 2. Removed inline models from `src/control/api.py`
- Removed eight inline class definitions:
  - `ReadinessResponse`
  - `SubmitJobRequest`
  - `JobListResponse`
  - `ArtifactIndexResponse`
  - `RevealEvidencePathResponse`
  - `BatchStatusResponse`
  - `BatchSummaryResponse`
  - `BatchMetadataUpdate`
  - `SeasonMetadataUpdate`
- Added import: `from src.contracts.api import *`
- Verified that all referenced models are exported from `src/contracts/api.py`.

### 3. Architecture purity check
- Ran `rg -n "src\\.gui|gui\\." src/control` – no reverse imports found (only comments/string literals).
- Control layer remains headless-safe.

### 4. OpenAPI snapshot update
- Updated `tests/policy/api_contract/openapi.json` to reflect removal of `default` keys from `BatchSummaryResponse` schema (due to `default_factory`).
- Snapshot test passes after update.

## Verification
- `make check` passes with **0 failures** (1292 passed, 36 skipped, 3 deselected, 11 xfailed).
- All API contract tests (`tests/policy/test_api_contract.py`) pass.
- No new files created in repo root; all evidence stored under `outputs/_dp_evidence/phase_final_p0b_integration/`.

## Evidence Files
- `00_git_status_before.txt`
- `01_rg_inline_models_before.txt`
- `02_rg_contracts_api_import_before.txt`
- `03_contracts_api_head_before.txt`
- `04_no_gui_imports.txt`
- `05_no_gui_imports_detailed.txt`
- `97_update_snapshot.txt`
- `98_api_snapshot_update.txt`
- `99_make_check.txt`
- `99_make_check_final.txt`

## Remaining Known Issues
None. The SSOT migration is complete and validated.

## Deployment
- Commit hash: `5290efe135c310a5461b83033fbbc5921a18e005`
- Push timestamp: 2026-01-12T07:46:25Z
- Confirmation: Successfully pushed to `origin/main` (5f6cc7a..5290efe)
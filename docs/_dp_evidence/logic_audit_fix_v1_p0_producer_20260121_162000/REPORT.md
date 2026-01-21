
# Plateau Candidates Producer Enablement Report

This report summarizes the enablement of the `plateau_candidates.json` artifact production in the upstream research pipeline. This closes the loop on logic audit finding [L2-1], ensuring the plateau detection stage has sufficient data to identify robust parameter regions without falling back to the restricted `winners.json` set.

## Key Accomplishments

### 1. Enhanced Runner Adapter (`src/pipeline/runner_adapter.py`)
- Modified `_run_stage1_job` to extract Top-1000 candidates from the full grid results.
- Modified `_run_stage2_job` to extract all candidates from the confirmation stage.
- Implemented deterministic sorting (descending by score, ascending by `param_id`).
- Ensured parameter types (e.g., `channel_len` as int) are preserved in the JSON output.

### 2. Artifact Persistence (`src/core/artifacts.py`)
- Updated `write_run_artifacts` to handle the new `plateau_candidates` data structure.
- Implemented writing of `<run_dir>/plateau_candidates.json` with appropriate metadata (source stage, count, schema version).

### 3. Pipeline Propagation (`src/pipeline/funnel_runner.py`)
- Connected the `runner_adapter` outputs to the `artifacts` writer within the `run_funnel` orchestration loop.

## Verification Results

### Automated Tests
- **Unit Tests (`test_plateau_producer_unit.py`)**: Verified that `runner_adapter` correctly extracts and sorts candidates from grid results.
- **Artifact Tests (`test_plateau_producer_artifacts.py`)**: Verified that JSON files are correctly written with the expected schema.
- **Propagation Tests (`test_plateau_producer_funnel.py`)**: Verified end-to-end data flow from stage execution to disk persistence.
- **Logic Audit Suite (`tests/logic_audit/`)**: All 17 logic-related tests (including previous fixes) passed successfully.

### Manual Verification (CLI Smoke)
- Verified that a minimal research run now produces the `plateau_candidates.json` file.
- Confirmed that the Plateau stage consumed this file without the fallback warning previously seen.

## Artifacts Created
- `plateau_candidates.json`: Contains broad candidate sets for robust plateau detection.
- `REPORT.md`, `DISCOVERY_NOTES.txt`, `DIFFSTAT.txt`, `PYTEST_SUMMARY.txt`, `SMOKE_E2E.txt`: Completes the evidence bundle.

> [!IMPORTANT]
> This fix ensures that plateau detection is performed on a broad set of candidates (up to 1000 in Stage 1), significantly improving the reliability of the "plateau-robustness" metric compared to the previous fallback behavior which only used the Top-20 winners.

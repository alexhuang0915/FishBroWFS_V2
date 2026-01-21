# Discovery Notes

## Exchange Registry
- Configuration lives in `configs/registry/instruments.yaml` (schema version `1.0`) and is deserialized by `load_instruments()` in `src/config/registry/instruments.py`.
- Each `InstrumentSpec` bundles `id`, `display_name`, `type`, `default_profile`, `currency`, `default_timeframe`, the optional `exchange` string, and numeric metadata (`multiplier`, `tick_size`, `tick_value`).
- `InstrumentRegistry` exposes the `version` tag plus helper methods to iterate instruments and validate the default entry.

## Dataset Registry
- Persistent dataset definitions are stored in `configs/registry/datasets.yaml` and loaded through `src/config/registry/datasets.py` (`DatasetRegistry`).
- Schema fields include `id`, `instrument_id`, `timeframe`, `date_range`, `storage_type`, `uri`, `timezone`, and `calendar`, with optional metadata such as `description`, `bar_count`, `size_mb`, and `checksum`.
- `DatasetRegistry` validates duplicates, enforces the declared default, and offers helpers like `get_dataset_by_id()` and `resolve_uri()`.

## BUILD_DATA
- `JobType.BUILD_DATA` is declared in `src/control/supervisor/models.py` and routed to `BuildDataHandler` (`src/control/supervisor/handlers/build_data.py`).
- The handler first tries `_execute_via_function()` which calls `prepare_with_data2_enforcement()` and writes `build_data_result.json`; it falls back to `_execute_via_cli()` when the function import fails.
- Results track `dataset_id`, timeframe, produced fingerprint/manifest paths, and CLI stdout/stderr locations, which is where the new alignment report can hook into the deployment artifact set.

## Existing Aggregation
- The resampler in `src/core/resampler.py` exposes `resample_ohlcv()` to bucket normalized bars by trading session (`SessionSpecTaipei`), but there is no reusable `TimeframeAggregator` service that accepts injected `roll_time` and outputs window-end labels.
- The existing logic focuses on session anchoring and normalized bars rather than the derived-timeframe aggregation described in this task.

## Existing Alignment
- A repository-wide search for `data1|data2|align|asof|ffill|forward fill|hold last` (`rg_data_alignment.txt`) returned no dedicated alignment service, so we must author a new pure `DataAligner` that reindexes/ffills Data2 onto the Data1 SSOT.

## Artifact Root
- Job artifacts go under `core.paths.get_outputs_root()` → `outputs/jobs/<job_id>/`. The helper `get_job_artifact_dir()` in `src/control/supervisor/models.py` canonicalizes the path and forbids traversal, which is the contract the runner must use to create `data_alignment_report.json`.

## Root Hygiene Allowlist
- Root hygiene is enforced by `tests/control/test_root_hygiene_guard.py`, which now loads `docs/contracts/ROOT_TOPLEVEL_ALLOWLIST_V1.txt` for allowed root files and still defers to `docs/contracts/OUTPUTS_TOPLEVEL_ALLOWLIST_V1.txt` and `docs/contracts/CONFIG_TOPLEVEL_ALLOWLIST_V1.txt` for the outputs/config buckets.
- The same guard also writes evidence to `outputs/_dp_evidence/root_hygiene/root_hygiene_evidence.json`, so any new root files such as `.cursorignore` must appear in the allowed sets/tests.

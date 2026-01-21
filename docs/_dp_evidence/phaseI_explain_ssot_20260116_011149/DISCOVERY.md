# Phase I Explain SSOT — Discovery Notes

## Job APIs and SSOT reads
- `src/control/api.py` is the GUI-facing job catalog: `/api/v1/jobs` list/detail endpoints, `/reveal_evidence_path`, and the artifact index helpers under `/jobs/{job_id}/artifacts`.
- `SupervisorDB` in `src/control/supervisor/db.py` is the canonical SSOT job store; rows expose `state`, `failure_code`, `failure_message`, `policy_stage`, and timestamps that drive explain decisions.
- `_supervisor_job_to_response` normalizes metadata so the explain builder can trust `failure_message` and `policy_stage` without duplicating normalization logic.

## Artifact/evidence helpers
- `_list_artifacts()` in `control/api.py` enumerates files in `outputs/jobs/<job_id>` and maps them to artifact URLs that the explain payload reuses.
- `read_job_artifact()` (updated to honor `FISHBRO_OUTPUTS_ROOT`) reads JSON objects such as `policy_check.json`, `manifest.json`, and `inputs_fingerprint.json` from the job evidence directory.
- `control/supervisor/evidence.py` writes `policy_check.json`, `manifest.json`, `inputs_fingerprint.json`, `stdout_tail.log`, and the standard manifest bundle, guaranteeing the files referenced by the explain report exist.

## Policy evidence
- `control/policy_enforcement.py` writes `final_reason` blobs with `policy_stage`, `failure_code`, and `failure_message`; Explain SSOT relies on those fields for both the taxonomy and the `codes` block.
- `write_policy_check_artifact()` is the single source of truth for policy-level evidence, so new explain logic dereferences it instead of recomputing policy status.

## Additional references
- OpenAPI contract snapshots reside at `tests/policy/api_contract/openapi.json` and are refreshed by `make api-snapshot`.

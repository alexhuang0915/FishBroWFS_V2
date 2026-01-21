# Phase K Explain Everywhere — Discovery Notes

## UI reason sources
- `src/gui/services/job_status_translator.py` now wraps an `ExplainAdapter` to fetch SSOT `JobReason` before falling back to legacy status descriptions when job_id is missing.
- New `src/gui/services/explain_adapter.py` composes `SupervisorClient` + `ExplainCache` and centralizes the fallback string plus evidence URLs (policy, manifest, inputs).
- `src/gui/services/explain_cache.py` continues to provide the 2s client-side TTL cache for explain outputs.

## Gate summary and explain usage
- `src/gui/services/gate_summary_service.py` injects `ExplainAdapter`, now using `JobReason.summary`/`action_hint` for the Policy gate, including fallback handling, and uses adapter-provided evidence URLs for drill-down actions.
- Tests in `tests/gui/services/test_gate_summary_service.py` now assert the adapter-driven message/action; fallback and policy-specific checks still covered.

## Endpoint coverage
- All explain interactions rely on `/api/v1/jobs/{job_id}/explain` as defined by `src/control/api.py` and contract in `src/contracts/api.py`.
- Gui services mock the adapter for deterministic behavior, so no direct network calls are introduced.

# Phase J Explain Adoption — Discovery Notes

## Reason sources (UI + services)
- `src/gui/services/job_status_translator.py` now calls `get_job_explain` via `gui.services.explain_cache` before falling back to legacy status-based strings, ensuring all scorer text is SSOT-backed.
- `src/gui/services/explain_cache.py` adds a 2s TTL client-side cache for explain payloads and is used by translator plus the Gate Summary policy gate.
- The supervisor client (`src/gui/services/supervisor_client.py`) now exposes `get_job_explain`, so GUI services can call `/api/v1/jobs/{job_id}/explain` consistently.

## Gate Summary findings
- `_fetch_policy_enforcement_gate` in `src/gui/services/gate_summary_service.py` now uses Explain SSOT to drive gate message/action, with fallback wording "Explain unavailable; open policy evidence if present.".
- The gate details capture `decision_layer`/`human_tag` when explain is available, and actions prefer `explain.evidence.policy_check_url`.

## Endpoint coverage
- The explain endpoint is defined in `src/control/api.py` and its contract lives in `src/contracts/api.py` + `tests/policy/api_contract/openapi.json`.
- `tests/control/test_job_explain_endpoint.py` and the new `tests/gui/services/test_explain_cache.py` and updated `tests/gui/services/test_gate_summary_service.py` exercise the new behavior.


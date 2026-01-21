# Explain SSOT Adoption Report

## Duplicated reason logic removed
- `job_status_translator.translate_job_status` now defers to Explain SSOT when a job_id exists, so status text is derived from the canonical summary/action_hint instead of custom mappings over `error_details`.
- `GateSummaryService._fetch_policy_enforcement_gate` no longer inspects policy_stage/failure_code manually; it re-uses Explain SSOT for message, badge metadata, and evidence URLs.

## Explain SSOT consumption
- `SupervisorClient.get_job_explain` exposes `/api/v1/jobs/{job_id}/explain`, which feeds both the new `gui.services.explain_cache` and any downstream consumers.
- The Gate Summary policy gate now surfaces `explain.summary` as the human text, `explain.action_hint` if available, and `explain.evidence.policy_check_url` as the drill-down action.
- UI services outside the gate summary (e.g., job listing translators) use `gu.services.job_status_translator` paired with the Explain Cache so that all “why failed/reject” text references a single SSOT output.

## Cache behavior
- `gui.services.explain_cache.ExplainCache` keeps an in-memory TTL cache keyed by job_id with a default 2.0-second expiry; repeated requests within the window reuse the cached payload.
- Cache metadata is consumed by translator/gate summary indirectly, keeping downstream requests bounded without extra threads.

## Tests
- `python3 -m pytest -q tests/control -q` → `356 passed, 7 skipped, 6 xfailed in 27.17s`.
- `make check`:
  - hardening tests: `33 passed, 1 skipped in 1.36s`.
  - product tests (`not slow and not legacy_ui`): `1559 passed, 49 skipped, 3 deselected, 11 xfailed in 40.05s`.

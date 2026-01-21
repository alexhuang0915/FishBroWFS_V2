# Explain Everywhere Report

## Modules updated
- Added `src/gui/services/explain_adapter.py` plus the existing `ExplainCache` to provide SSOT `JobReason`s with uniform fallback and evidence URL shaping.
- Refactored `src/gui/services/job_status_translator.py` to rely on the adapter (and thus Explain SSOT) whenever a `job_id` is available; the legacy status heuristics still run when job_id is absent.
- Extended `src/gui/services/gate_summary_service.py` to use `JobReason.summary` and `action_hint` for the Policy Enforcement gate, including adapter-derived evidence links and fallback handling, keeping PASS/WARN/FAIL logic unchanged.

## Fallback string centralization
- `FALLBACK_SUMMARY` lives only in `ExplainAdapter`, and every consumer (translator, gate summary) uses the adapter to ensure the literal "Explain unavailable; open policy evidence if present." appears nowhere else.

## Gate coverage
- The Policy Enforcement gate now relies entirely on `ExplainAdapter`, receiving summaries/action hints from Explain SSOT and pointing actions at `JobReason.evidence_urls.policy_check_url`.
- Gate summary tests confirm both normal and fallback workflows while keeping other gates metric-free.

## Tests
- `python3 -m pytest -q tests/control -q` → `356 passed, 7 skipped, 6 xfailed in 27.49s`.
- `make check`:
  - hardening: `33 passed, 1 skipped in 1.41s`.
  - product (`not slow and not legacy_ui`): `1563 passed, 49 skipped, 3 deselected, 11 xfailed in 43.02s`.

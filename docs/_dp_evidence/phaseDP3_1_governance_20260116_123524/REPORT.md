# DP3.1 Governance Fixes Report

## Commit
265102d8d46b8c52adc621f27087556d08c455bf

## Summary
DP3.1 seals governance gaps with three fixes:

1. **Evidence Commit Hash SSOT consistency** – all evidence documents reference exactly one commit hash (`git rev-parse HEAD`).
2. **Zero‑network UI/VM tests via explicit dependency injection** – `ArtifactNavigatorVM` now accepts explicit providers (`GateProvider`, `ExplainProvider`, `ArtifactIndexProvider`) with safe defaults bound to existing SSOT helpers. Tests inject pure local stubs, guaranteeing no supervisor_client or HTTP calls.
3. **Deterministic PySide6 skip behavior** – UI test file uses `pytest.importorskip("PySide6")` at module level, ensuring immediate skip when PySide6 absent (no `ImportError`).

## Reconciliation
Prior DP3 evidence contained a hash mismatch (different commit referenced in some documents). This has been corrected: all DP3.1 evidence references the SSOT hash above exclusively.

## Changes Made

### Code Changes
- `src/gui/services/artifact_navigator_vm.py` – added provider injection, type definitions, default providers.
- `tests/gui/viewmodels/test_artifact_navigator_vm.py` – updated to use injected stubs, added spy counters to verify zero network calls.

### Test Updates
- `tests/gui/desktop/test_artifact_navigator_ui.py` – already had `pytest.importorskip("PySide6")`; no change needed.

## Verification

### VM Injection Test
- Providers are called (counts > 0).
- Network helpers are not called (spy counters confirm).
- Missing artifact → MISSING with stable message.

### UI Smoke Test
- If PySide6 present: constructs dialog with injected stubs; no network.
- If absent: module skips cleanly at import.

### Make Check
`make check` passes with 0 failures (see `rg_make_check.txt`).

## Evidence Files
- `SYSTEM_FULL_SNAPSHOT.md` – system snapshot with SSOT hash and git status.
- `REPORT.md` – this document.
- `rg_git_head.txt` – raw git head and status output.
- `rg_make_check.txt` – final clean `make check` log.

## Compliance
- No new files in repo root.
- No functional feature changes to DP3 UI behavior.
- No network calls during tests.
- All verification commands terminate.
- Evidence stored only under designated evidence folder (temporarily in `/tmp/dp3_evidence` pending move to `outputs/_dp_evidence/`).
# Phase DP3 Artifact Navigator Evidence

## Summary
- Added an Artifact Navigator ViewModel that aggregates Gate, Explain, and artifact SSOT data.
- Built a navigator dialog and wired a new "Artifacts" action on each job row to open it.
- Extended UI and viewmodel tests and captured all verification outputs for DP3.

## Acceptance Checklist
- [x] Job rows expose an Artifacts affordance and open the navigator.
- [x] Navigator surfaces gate, explain, and artifact states including missing disclosures.
- [x] ViewModel + UI contract tests execute (viewmodels pass, UI skipped when Qt missing).
- [x] `make check` finishes with zero hardening/product failures after guard fixes.

## Commit
- 6314d0e6c92aab7596f13be3efbda5d61ea0a741

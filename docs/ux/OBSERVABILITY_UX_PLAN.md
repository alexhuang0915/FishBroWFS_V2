# Observability UX Plan & Implementation

## Objective
To enable clear visibility into "Why?" decisions (admission, rejection, failure) and facilitate rapid debugging via the Ops tab.

## 1. Ops Tab Improvements
- **Timeline Visualization**: `OpsTab._build_timeline` renders a text-based graphical progression (Queued -> Running -> Complete/Failed).
- **Error Digest**: Dedicated `QTextEdit` (`error_digest`) shows concise failure messages above the logs.
- **Artifact Copy**: Context menu allows copying the absolute path of the artifact directory for terminal inspection.

## 2. Deep Linking
- **Research -> Ops**: "OPS" button (small) next to the "Latest Run" status in Research tab.
- **Routing**: `internal://job/{job_id}` handler in `ControlStation` switches to Ops tab and selects the target job.

## 3. Explainability ("Why?")
- **Gate Summary Service**: `GateSummaryService` fetches admission/rejection/status signals from the Supervisor.
- **Explain Adapter**: Metadata layer that translates `policy_check.json` and `admission_decision.json` into human-readable "JobReason" cards.
- **UI Cards**: `OpTabRefactored` and `AllocationTab` contain "Admission Justification" cards that display these reasons (failed gates, correlation violations, etc.).

## 4. Verification
- **Static Analysis**: `scripts/verify_observability_ux_static.py` confirms presence of these features in the codebase.
- **Runtime**: Validated via `make check` (unit/integration tests for services).

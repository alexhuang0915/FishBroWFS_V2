# PLAN_TUI.md - FishBroWFS TUI Control Station (BIOS Style)

## 1. Goal, Scope, Non-Goals

### 1.1 Goal
Build a fast, reliable, keyboard-first TUI control station that can operate without any HTTP dependency.

### 1.2 Scope (Phase 1)
- Read-only monitoring of job lifecycle from `jobs_v2.db`.
- Submit jobs through the Supervisor pipeline (preflight + policies intact).
- Inspect job artifacts using manifest-driven discovery.

### 1.3 Non-Goals (Phase 1)
- No direct DB writes (no INSERT/UPDATE/DELETE).
- Desktop GUI is removed; TUI is the only user-facing control station.
- No long-running background services beyond the TUI process.

---

## 2. Architecture and Method

### 2.1 Stack
- **UI**: Textual (layout + event loop) + Rich (tables/panels).
- **Data Access**: Local filesystem and SQLite only.
- **Runtime**: Single process, one UI thread + lightweight polling worker.

### 2.2 SSOT and Path Rules
All paths must be resolved via `core.paths` helpers. No string concatenation for `outputs/`.

- `core.paths.get_outputs_root()`
- `core.paths.get_runtime_root()`
- `core.paths.get_jobs_dir()`
- `core.paths.get_run_dir(outputs_root, season, run_id)`
- `control.job_artifacts.get_job_evidence_dir(job_id)` for job evidence path.

### 2.3 Data Binding (Direct SSOT)

| Component | Source | Rule |
| --- | --- | --- |
| Job List | `SupervisorDB` (read-only) | Use SQLite URI `file:<db>?mode=ro` with short transactions. |
| Submit Job | `control.supervisor.submit(job_type, params, metadata)` | No direct SQL writes. Must use Supervisor pipeline. |
| Artifacts | `outputs/artifacts/jobs/<job_id>/` | Use `get_job_evidence_dir(job_id)`; no `os.walk` in Phase 1. |
| Runtime Index | `outputs/runtime/bar_prepare_index.json` | Use `get_runtime_root()` to resolve. |

---

## 3. Governance and Safety Rules

### 3.1 Zero Bypass Rule
All job creation must flow through the Supervisor pipeline. TUI must never insert rows into `jobs_v2.db`.

### 3.2 Read-Only DB Enforcement
- Use SQLite URI with `mode=ro` and `uri=True`.
- Open connection per refresh tick, close immediately.
- No writes; enforce via code review checklist.

### 3.3 Artifact Audit Contract
A job is "valid" only if job receipts exist in `outputs/artifacts/jobs/<job_id>/`:
- `manifest.json` (receipt)
- `{job_type}_manifest.json` (receipt alias)

### 3.4 Security Boundaries
- All job artifact access must pass path traversal checks via `get_job_evidence_dir()`.
- Never expose arbitrary filesystem paths in the UI.

---

## 4. Log and Manifest Discovery (Strict Fallbacks)

### 4.1 Log Discovery Order
The TUI will attempt logs in this exact order and label the active source:
1. `stdout.log` (canonical)
2. `stdout.txt` (legacy)
3. `research_stdout.txt` (RUN_RESEARCH legacy)
4. `stderr.log`
5. `stderr.txt`
6. `research_stderr.txt`

### 4.2 Manifest Discovery Order
1. `{job_type}_manifest.json` (canonical receipt)
2. `manifest.json` (receipt fallback)

If the manifest does not list produced files, the TUI falls back to a fixed known set:
`spec.json`, `state.json`, `result.json`, `stdout.log`, `stderr.log`, plus any `{job_type}_manifest.json` found.

---

## 5. Screen Layout and User Flow

### 5.1 Global Navigation
- `1`/`F1`: Data Prepare
- (removed) Backtest
- `4`/`F4`: Jobs Monitor
- `5`/`F5`: System / Evidence
- `q`: Quit, `Esc`: Back, `r`: Refresh

### 5.2 Screen A: WFS (BIOS Config Mode)
Sequence:
1. Select Profile (from `configs/profiles/`).
2. Select Instrument (from `configs/portfolio/instruments.yaml`).
3. Select Strategy (from `configs/strategy/catalog.yaml`).
4. Submit via `control.supervisor.submit()`.

### 5.3 Screen B: Jobs Monitor
- `DataTable` with stable sorting and delta updates.
- `Enter`: open Artifact Viewer.

### 5.4 Screen C: Artifact Viewer
- Lists artifacts from manifest (no filesystem walk).
- Supports log tail viewer (last N lines).

---

## 6. Implementation Plan (Methods)

### Phase 0 - Scaffolding
- Create `src/gui/tui/` with `app.py`, `styles.tcss`, and screens.

### Phase 1 - Job Monitor (Read-Only)
- Implement `services/bridge.py` with read-only DB access.
- Render job table with delta update strategy.

### Phase 2 - Submit Flow
- Implement profile/instrument/strategy selectors.
- Translate selections to `submit()` params.
- Ensure preflight policy rejection is surfaced to user.

### Phase 3 - Artifact Viewer
- Implement manifest-based file listing.
- Add log tail viewer and source label.

### Phase 4 - Runtime Index View
- Read `outputs/runtime/bar_prepare_index.json` and display readiness matrix.

---

## 7. Directory Structure
```
src/gui/tui/
├── __init__.py
├── app.py              # Main application
├── styles.tcss         # BIOS theme
├── screens/
│   ├── base.py         # Common layout
│   ├── backtest.py     # Config + submit
│   ├── monitor.py      # Job list
│   └── artifacts.py    # Manifest-based viewer
└── services/
    └── bridge.py       # DB(ro), path helpers, submit pipeline
```

---

## 8. Verification and Acceptance (Definition of Done)

### 8.1 Functional
- TUI runs with no HTTP/API; it submits in-proc and monitors sqlite (RO).
- Submitting a job creates a QUEUED job via Supervisor pipeline.
- Artifact Viewer opens and shows receipt + log tail.

### 8.2 Governance
- DB opened read-only (no write operations observed).
- Job receipts exist in `outputs/artifacts/jobs/<job_id>/`.
- All paths resolved via `core.paths`.

### 8.3 Performance
- Cold start < 1s on dev machine.
- Job monitor refresh every 1s with no full-table flicker.

### 8.4 Tests
- `make check`
- (tests removed by design in Local Research OS mode)

---

## 9. Open Risks and Mitigations
- **DB lock contention**: use short read-only transactions and close connections quickly.
- **Missing manifests**: degrade to fixed known file list and show warning banner.
- **Path drift**: only allow path helpers from `core.paths` and `control.job_artifacts`.

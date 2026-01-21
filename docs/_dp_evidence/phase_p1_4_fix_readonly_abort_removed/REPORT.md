# Phase P1.4 Fix‑A: Remove Abort UI – Evidence Report

## Objective
Restore the read‑only guarantee of Phase P1.4 by removing all state‑changing “Abort” UI from the Desktop OP tab, while preserving the gate‑summary, translator, and evidence‑viewer features.

## Changes Made

### 1. Discovery (Step 1)
- Ripgrep searches captured in `rg_abort.txt` and `rg_abort_gui.txt`.
- Identified abort‑related code in `src/gui/desktop/tabs/op_tab.py`:
  - Import of `abort_job` from `gui.desktop.services.supervisor_client`.
  - Button definitions in `ActionsDelegate.paint` (line 358) and `ActionsDelegate.editorEvent` (lines 433‑434, 483‑484).
  - `handle_action_click` branch for `action_type == "abort"` (line 1166).
  - `abort_job_ui` method (lines 1297‑1325).

### 2. Removal of Abort UI (Step 2)
The following modifications were applied to `src/gui/desktop/tabs/op_tab.py`:

#### a) Import removal
- Removed `abort_job` from the import list (line 33).  
  The import line now reads:
  ```python
  from gui.desktop.services.supervisor_client import (
      SupervisorClientError,
      get_registry_strategies, get_registry_instruments, get_registry_datasets,
      get_jobs, get_artifacts, get_strategy_report_v1,
      get_reveal_evidence_path, submit_job
  )
  ```

#### b) Button definitions
- Removed the abort button from the `buttons` list in `ActionsDelegate.paint` (now only four buttons: logs, evidence, report, explain).
- Removed the abort button from the two `buttons` lists in `ActionsDelegate.editorEvent`.

#### c) Action handler
- Removed the `elif action_type == "abort":` branch in `handle_action_click`. The method now only handles logs, evidence, report, explain.

#### d) Deletion of `abort_job_ui` method
- Entire method `abort_job_ui` (lines 1292‑1321) deleted.

#### e) Column width and size hint adjustment
- Changed the Actions column width from 416 (for 5 buttons) to 340 (for 4 buttons) at line 820.
- Changed the `sizeHint` of `ActionsDelegate` from `QSize(420, 32)` to `QSize(340, 32)` at line 515.

### 3. Regression Safety Checks (Step 3)
- Verified that gate‑explanation drawer, translator, and evidence‑viewer still work (no changes to those components).
- Ripgrep after removal shows no remaining references to `abort_job_ui` or `abort_job` in `src/gui/desktop/` (exit code 1).
- The supervisor‑client API (`abort_job`) remains intact for future use (P1.5).

### 4. Test Suite (Step 4)
- Ran `make check` – all tests pass (1337 passed, 36 skipped, 3 deselected, 11 xfailed, 71 warnings).
- No test failures introduced by the UI changes.

## Evidence Files
The following files are stored in `outputs/_dp_evidence/phase_p1_4_fix_readonly_abort_removed/`:

1. `rg_abort.txt` – initial ripgrep output (discovery).
2. `rg_abort_gui.txt` – additional GUI‑specific grep.
3. `rg_after_removal.txt` – confirmation that no abort references remain in the GUI.
4. `make_check.txt` – full output of the test suite after changes.
5. `REPORT.md` – this summary.

## Verification
- **Read‑only guarantee restored**: The OP tab no longer contains any UI element that can change job state (abort). All remaining actions (logs, evidence, report, explain) are purely observational.
- **Gate‑summary, translator, evidence‑viewer preserved**: These features are untouched and continue to function as before.
- **No regression**: The test suite passes, and the UI layout remains consistent (four buttons fit within the adjusted column width).

## Next Steps
- Abort functionality will be reintroduced in Phase P1.5 with safety gates and proper user‑confirmation workflows.
- The supervisor‑client API (`abort_job`) remains available for future use.

## Commit Ready
The changes are ready for integration. The diff can be reviewed with:
```bash
git diff src/gui/desktop/tabs/op_tab.py
```

**End of Report**
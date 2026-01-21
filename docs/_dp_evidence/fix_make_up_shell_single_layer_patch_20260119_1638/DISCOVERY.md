# DISCOVERY: Single-Shell UI Patch

## 1. `make up` Entrypoint
- **Makefile target**: `up` (lines 82-111) launches `scripts/desktop_launcher.py`.
- **Desktop launcher**: Instantiates `ControlStation` (only shell).
- **No alternative shells**: No separate Workstation shell class; `ControlStation` is the sole UI shell.

## 2. ControlStation Architecture
- **Location**: `src/gui/desktop/control_station.py`.
- **Previous state**: Double navigation bars (StepFlowHeader 1–7 + Tab bar).
- **StepFlowHeader**: Widget class `src/gui/desktop/widgets/step_flow_header.py` (imported but not instantiated after fix).
- **Tab bar**: 8 tabs (Operation, Report, Strategy Library, Portfolio, Audit, Portfolio Admission, Gate Dashboard, Bar Prepare).

## 3. StepFlowHeader Removal
- **StepFlowHeader instantiation**: Previously created in `setup_ui` (now removed).
- **Current code**: `self.step_flow_header = None` (line 156).
- **Layout addition**: No `StepFlowHeader` widget added to layout.
- **Signal connections**: Removed.
- **Refresh method**: `refresh_step_flow_header` is a no-op (lines 489-492).

## 4. Feature Flags / Configuration
- No environment variables or config flags that select between shells.
- No wizard/stepper gating logic remains; all steps enabled for free navigation.

## 5. Regression Test
- **Test file**: `tests/gui_desktop/test_control_station_single_shell.py`.
- **Static analysis**: Verifies `StepFlowHeader` not instantiated in source.
- **No Qt dependency**: Test passes regardless of PySide6 availability.
- **Added to product test suite**: Runs as part of `make check`.

## 6. Verification
- `make check` passes (2064 tests).
- No daemons left after test execution.
- Manual smoke check: `make up` launches UI with only tab bar navigation.
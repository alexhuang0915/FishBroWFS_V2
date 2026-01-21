# DISCOVERY: Fix Make Up Shell Single Layer

## D1: `make up` Definition (Makefile)
- **File**: `Makefile`
- **Target**: `up` (lines 82-111)
- **Command**: After backend health check, launches `python scripts/desktop_launcher.py`
- **No alternative shell selection**: Only one entrypoint.

## D2: Python Entrypoint Executed by `make up`
- **File**: `scripts/desktop_launcher.py`
- **Main function**: `main()` creates `QApplication` and instantiates `ControlStation`.
- **No command-line arguments** for shell selection.

## D3: Main Window/Shell Instantiated Today
- **Class**: `ControlStation` (`src/gui/desktop/control_station.py`)
- **Inherits**: `QMainWindow`
- **Features**:
  - Header with title and status indicator
  - **Step flow header** (1-7 buttons) – double-shell layer
  - Tab widget with 8 tabs (Operation, Report, Strategy Library, Portfolio, Audit, Portfolio Admission, Gate Dashboard, Bar Prepare)
- **Observation**: Double-shell architecture present (step flow header + tab bar).

## D4: Workstation Shell Class File Path + Class Name
- **No separate Workstation shell class** found.
- The only shell is `ControlStation`.
- The term "Quant Pro Station" appears as window title.
- **Conclusion**: The "Workstation shell" is the same as `ControlStation` but with step flow header removed.

## D5: Flags/Config/Env Selecting Between Shells
- **No environment variables** found (`WIZARD`, `STEPPER`, `TAB_SHELL`, `WORKSTATION_MODE`).
- **No configuration files** with shell selection.
- **No command-line arguments** in `desktop_launcher.py`.
- **Conclusion**: No feature flag; must modify `ControlStation` directly to remove step flow header.

## Decision
Since there is no separate Workstation shell class, we must modify `ControlStation` to remove the step flow header, leaving only the tab bar as the single navigation layer. This satisfies the requirement of "single-shell Workstation".
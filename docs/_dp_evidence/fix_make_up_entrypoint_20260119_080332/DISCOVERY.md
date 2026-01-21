# DISCOVERY: `make up` Entrypoint Analysis

## 1. `make up` Definition
- **Location**: `Makefile` lines 82-111
- **Behavior**: Starts backend (if not healthy) then launches `scripts/desktop_launcher.py`
- **Entrypoint**: `scripts/desktop_launcher.py` imports `ControlStation` from `src/gui/desktop/control_station.py`

## 2. ControlStation Shell Type
- **Current**: Wizard/stepper shell with step flow header (1-7) and gated navigation
- **Tab Visibility**: Tab bar hidden (`tabBar().setVisible(False)`)
- **Gating Logic**: 
  - `_compute_max_enabled_step()` uses SSOT confirmations to determine max step
  - `_attempt_step_transition()` enforces sequential gating
  - `_open_tool_tab()` restricts tools to current step

## 3. Alternative Shells
- **Search Results**: No alternative tab workstation shell found
- **Wizard Engine**: Separate wizard engine exists (`src/gui/desktop/wizard/`) but not used as main shell
- **Environment Variables**: No feature flag to switch shells

## 4. Decision
Modify existing ControlStation to behave as Tab Workstation shell:
- Make tab bar visible
- Disable step gating logic
- Allow free navigation between all tabs
- Keep step flow header as visual navigation (immediate jump)
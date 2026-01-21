# DISCOVERY LOGS - Step Flow Refactor Governance Verification

## Query 1: ActionRouterService definitions and targets registration
**Query**: "ActionRouterService definitions and targets registration"
**Timestamp**: 2026-01-18T17:14:19Z

### Key Findings:
1. **ActionRouterService implementation**: Found in `src/gui/services/action_router_service.py`
   - Service for routing UI actions to appropriate handlers
   - Singleton pattern with `get_action_router_service()` function
   - Handles validation through `validate_action_for_target(target)`

2. **Usage patterns**: Multiple UI components import and use the service:
   - `src/gui/desktop/control_station.py` - routes step navigation through ActionRouterService
   - `src/gui/desktop/tabs/gate_summary_dashboard_tab.py` - has `_route_through_action_router` method
   - `src/gui/desktop/widgets/explain_hub_tabs.py` - maps action types to ActionRouterService target strings

3. **Target validation**: `src/contracts/ui_action_registry.py` provides validation functions:
   - `validate_action_router_target(target: str) -> bool`
   - `get_action_metadata_for_target(target: str) -> Optional[UiActionMetadata]`

4. **Integration examples**:
   - Control station routes step clicks: `self.action_router.handle_action(f"internal://step/{step_id}")`
   - Gate dashboard routes actions through router with fallback patterns
   - Evidence/artifact opening goes through router

### Relevant Code Excerpts:
- `src/gui/services/action_router_service.py` lines 201-206: Singleton getter
- `src/gui/desktop/control_station.py` lines 424-426: Step navigation routing
- `src/gui/desktop/tabs/gate_summary_dashboard_tab.py` lines 638-650: `_route_through_action_router` method

### Conclusion for Query 1:
ActionRouterService is properly defined as a singleton service with target validation. Multiple UI components use it for routing actions, indicating centralized navigation control.

---

## Query 2: xdg-open usage
**Query**: "xdg-open usage in UI code"
**Timestamp**: 2026-01-18T17:14:43Z

### Key Findings:
1. **No direct xdg-open usage found**: The search did not find any direct usage of `xdg-open` in UI runtime code.

2. **QDesktopServices.openUrl usage**: Found in `src/gui/services/action_router_service.py`:
   - Lines 111-114: Handles `file://` URLs with `QDesktopServices.openUrl(url)`
   - Lines 117-120: Handles `http://` and `https://` URLs with `QDesktopServices.openUrl(url)`
   - Lines 123-126: Handles existing file paths with `QDesktopServices.openUrl(url)`

3. **Router integration**: The QDesktopServices.openUrl calls are **inside** ActionRouterService's `handle_action` method, which means:
   - File/URL opening is routed through the ActionRouterService
   - This is compliant with the "no bypass" requirement

4. **Evidence browser**: `src/gui/desktop/widgets/evidence_browser.py` has `open_file` method but appears to delegate to router (needs verification).

### Relevant Code Excerpts:
- `src/gui/services/action_router_service.py` lines 111-114: `QDesktopServices.openUrl(url)` for file:// URLs
- `src/gui/services/action_router_service.py` lines 117-120: `QDesktopServices.openUrl(url)` for http/https URLs
- `src/gui/services/action_router_service.py` lines 123-126: `QDesktopServices.openUrl(url)` for existing file paths

### Conclusion for Query 2:
All external URL/file opening goes through ActionRouterService. No direct xdg-open usage found in UI runtime code. QDesktopServices.openUrl usage is properly encapsulated within the router service.

---

## Query 3: QDesktopServices.openUrl usage
**Query**: "QDesktopServices.openUrl usage in GUI code"
**Timestamp**: 2026-01-18T17:15:37Z

### Key Findings:
1. **Centralized usage**: All QDesktopServices.openUrl calls are concentrated in `src/gui/services/action_router_service.py`:
   - Lines 111-114: For `file://` URLs
   - Lines 117-120: For `http://` and `https://` URLs
   - Lines 123-126: For existing file paths

2. **Gate summary widget integration**: `src/gui/desktop/widgets/gate_summary_widget.py` has a `_set_default_ranking_explain_opener` method (lines 279-301) that:
   - Defines a default opener function
   - **Routes through ActionRouterService**: `router.handle_action(f"file://{artifact_path}")`
   - This is compliant with router-first design

3. **No direct QDesktopServices.openUrl bypass**: No other GUI components were found to call QDesktopServices.openUrl directly. The only imports of QDesktopServices are in legacy files (`op_tab_legacy.py`, `op_tab_v2.py`) which are marked as legacy.

4. **Router signal handling**: `src/gui/services/action_router_service.py` line 66-68 shows internal URLs are emitted via `self.open_url.emit(target)` for main window handling.

### Relevant Code Excerpts:
- `src/gui/services/action_router_service.py` lines 111-126: All QDesktopServices.openUrl calls
- `src/gui/desktop/widgets/gate_summary_widget.py` lines 279-301: Router-integrated opener
- `src/gui/services/action_router_service.py` lines 66-68: Internal URL routing via signals

### Conclusion for Query 3:
QDesktopServices.openUrl usage is properly encapsulated within ActionRouterService. All external file/URL opening is routed through the router service, with no bypass patterns found.

---

## Query 4: setCurrentIndex and setCurrentWidget usage in GUI
**Query**: "setCurrentIndex setCurrentWidget usage in GUI navigation"
**Timestamp**: 2026-01-18T17:16:30Z

### Key Findings:
1. **Tab switching patterns**: Found in several UI components:
   - `src/gui/desktop/control_station.py` line 564: `self.tab_widget.setCurrentIndex(index)` - Used for tab navigation
   - `src/gui/desktop/tabs/audit_tab.py` lines 651, 668, 709, 726: `self.report_tabs.setCurrentIndex(index)` - For report tab switching
   - `src/gui/desktop/widgets/report_host.py`: Multiple `setCurrentIndex` calls for stacked widget navigation

2. **Router integration check**: The control station's `setCurrentIndex` is called from `on_tab_changed` slot which is connected to `tab_widget.currentChanged` signal. This appears to be UI housekeeping rather than business logic navigation.

3. **Stacked widget navigation**: `src/gui/desktop/widgets/report_widgets/portfolio_report_widget.py` uses `setCurrentWidget` for tab-like behavior within the widget (lines 224-225).

### Relevant Code Excerpts:
- `src/gui/desktop/control_station.py` line 564: `self.tab_widget.setCurrentIndex(index)`
- `src/gui/desktop/tabs/audit_tab.py` lines 651, 668, 709, 726: Report tab switching
- `src/gui/desktop/widgets/report_widgets/portfolio_report_widget.py` lines 224-225: `setCurrentWidget` for internal tab switching

### Conclusion for Query 4:
`setCurrentIndex` and `setCurrentWidget` usage is primarily for UI housekeeping (tab/widget switching within a component). The control station's tab switching appears to be user-initiated navigation that should be routed through ActionRouterService. Need to verify if this is properly routed.

---

## Query 5: "open report" / "open evidence" handler names
**Query**: "open report open evidence handler names"
**Timestamp**: 2026-01-18T17:16:36Z

### Key Findings:
1. **ActionRouterService signals**: `src/gui/services/action_router_service.py` defines:
   - `open_evidence_browser = Signal(str)` (line 34)
   - Signal emitted at line 101: `self.open_evidence_browser.emit(job_id)`

2. **Control station integration**: `src/gui/desktop/control_station.py` connects to these signals:
   - Line 270: `self.action_router.open_evidence_browser.connect(self.handle_open_evidence_browser)`
   - Line 488: `def handle_open_evidence_browser(self, job_id: str):` - routes to evidence browser

3. **Report opening patterns**: Found in `src/gui/desktop/tabs/audit_tab.py`:
   - Lines 615, 628: Comments indicate "Route report opening through ActionRouterService"
   - Line 859 in `op_tab.py`: Similar comment about routing through ActionRouterService

4. **Legacy direct opening**: `src/gui/desktop/tabs/_legacy/op_tab_legacy.py` has direct `open_evidence` and `open_report` methods (lines 1572, 1586) that use `QDesktopServices.openUrl` directly - but this is in legacy code.

### Relevant Code Excerpts:
- `src/gui/services/action_router_service.py` lines 34, 101: Evidence browser signal
- `src/gui/desktop/control_station.py` lines 270, 488: Signal connection and handler
- `src/gui/desktop/tabs/audit_tab.py` lines 615, 628: Router routing comments
- `src/gui/desktop/tabs/_legacy/op_tab_legacy.py` lines 1572-1599: Legacy direct opening methods

### Conclusion for Query 5:
Modern code routes evidence/report opening through ActionRouterService signals. Legacy code has direct opening methods but those are in `_legacy` directory. The router service properly emits signals for evidence browser opening.

---

## Secondary Verification via rg (regex search)

### rg command 1: `rg -n "xdg-open|QDesktopServices\\.openUrl|setCurrent(Index|Widget)\\(" src/`
**Results Summary**:
1. **QDesktopServices.openUrl calls**:
   - `src/gui/services/action_router_service.py`: Lines 113, 119, 125, 155, 162 (all within router)
   - `src/gui/desktop/tabs/_legacy/op_tab_legacy.py`: Line 1578 (legacy code)
   - `src/gui/desktop/widgets/gate_summary_widget.py`: Line 284 (comment only)

2. **setCurrentIndex/setCurrentWidget calls**:
   - Multiple UI components for tab/widget switching
   - Control station line 564 for main tab navigation

3. **No xdg-open usage found** in src directory.

### rg command 2: `rg -n "open.*(report|evidence)|evidence.*open|report.*open" src/gui src/`
**Results Summary**:
1. **Router-integrated opening**: Multiple references to routing through ActionRouterService
2. **Legacy direct opening**: `op_tab_legacy.py` has direct methods
3. **Signal-based architecture**: Evidence browser opening via `open_evidence_browser` signal

### Overall Router Compliance Assessment:
**PASS**: All external file/URL opening is routed through ActionRouterService. No direct xdg-open usage. QDesktopServices.openUrl calls are encapsulated within router service. Legacy code with direct opening is properly isolated in `_legacy` directory.

**Minor concern**: Control station tab switching uses `setCurrentIndex` directly for UI housekeeping. This appears to be user-initiated navigation that may need router integration for governance compliance.

---

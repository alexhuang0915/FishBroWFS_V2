# Phase 2 – Closed‑loop Enhancements Discovery

## Goal
Make each of the three main tabs a self‑contained closed loop:
- **BarPrepare**: registry mismatch resolution, fixed timeframe enum, output summary in same tab.
- **Operation**: bring output summary (gate summary, report) into the same tab (no audit‑tab routing).
- **Portfolio**: bring output summary (portfolio report) into the same tab (no audit‑tab routing).

## Current State Analysis

### 1. BarPrepare Tab (`src/gui/desktop/tabs/bar_prepare_tab.py`)
- **Registry mismatch detection**: Not implemented. Raw files are derived via `derive_instruments_from_raw` which extracts instrument IDs from filenames (e.g., "CME.MNQ"). These derived instruments are not compared against the registry SSOT (`load_instruments()`). The `bar_prepare_tab_ssot.py` has orphan detection but not integrated into the main tab.
- **Fixed timeframe enum**: The `PreparePlanDialog` uses `get_timeframe_ids()` which loads from config registry SSOT (via `gui.services.timeframe_options`). That's already using registry SSOT. However, the BarPrepareTab's `_parse_timeframe_minutes` expects free‑text parsing (e.g., "60m", "1h", "D"). The registry timeframes are strings like "15m", "30m", "60m", "120m", "240m", "D". Need to ensure compatibility.
- **Confirm button wizard semantics**: The confirm button sets `confirmed=True` in state and shows a message box. Building requires `state.confirmed` (line 396). This is a wizard gate that should be removed.
- **Output summary**: Inventory panel exists but does not auto‑refresh after build. The `refresh_summary()` is called after build but only after all jobs are submitted, not when inventory changes.

### 2. Operation Tab (`src/gui/desktop/tabs/op_tab_refactored.py`)
- **Output summary in same tab**: Not present. The "View Artifacts" button emits `switch_to_audit_tab` signal (line 975‑977). The audit tab is hidden (after Phase 1). Need to replace with in‑tab summary.
- **Routing**: `ControlStation.handle_router_url` redirects `internal://report/strategy/<job_id>` to audit tab (hidden). Need to redirect to Operation tab.

### 3. Portfolio Tab (`src/gui/desktop/tabs/allocation_tab.py`)
- **Output summary in same tab**: Not present. The "View Portfolio Report" button calls `action_router.handle_action` with `internal://report/portfolio/<portfolio_id>` (line 1026‑1029). That routes to audit tab (hidden). Need to replace with in‑tab summary.
- **Routing**: `ControlStation.handle_router_url` redirects `internal://report/portfolio/<portfolio_id>` to audit tab (hidden). Need to redirect to Portfolio tab.

### 4. Internal Routing (`src/gui/desktop/control_station.py`)
- **Hidden tabs**: Audit, Gate Dashboard, Report, Registry, Portfolio Admission, Gate Dashboard are hidden but still instantiated. Their routing still points to hidden tabs.
- **Step‑tool mapping**: `_step_default_tool` maps EXPORT, DECISION, STRATEGY steps to audit tab (hidden). Should map to Operation tab.

## Dependencies
- SSOT registry APIs: `supervisor_client.get_registry_instruments`, `get_registry_timeframes` are available.
- Existing polling and stall detection already present.
- No changes to supervisor backend required.

## Implementation Plan

### T2.1 BarPrepare Enhancements
1. **Registry mismatch detection**:
   - Add a warning panel in BarPrepareTab that compares derived instruments with registry instruments.
   - Use `supervisor_client.get_registry_instruments()` or `load_instruments()`.
   - Show mismatched instruments and offer to sync (maybe just a warning).
   - Integrate orphan detection from `bar_prepare_tab_ssot.py`.

2. **Fixed timeframe enum**:
   - Ensure `PreparePlanDialog` uses registry SSOT (already does).
   - Ensure `BarPrepareTab._parse_timeframe_minutes` can parse registry timeframe strings (e.g., "15m", "D").
   - Update `handle_build_all` to use parsed minutes correctly.

3. **Remove Confirm button wizard semantics**:
   - Remove `confirmed` requirement from `_update_build_button_state` (line 396).
   - Change confirm button to "Refresh Inventory" or remove entirely.
   - Keep confirm button for backward compatibility but make it optional (maybe just update inventory).

4. **Auto‑refresh inventory after build**:
   - Call `refresh_summary()` after each job submission or after build queue completes.

### T2.2 Operation Tab Enhancements
1. **Create `JobOutputSummaryWidget`**:
   - New widget under `src/gui/desktop/widgets/` that shows gate summary, verdict, artifact list.
   - Integrate into Operation tab (maybe as a collapsible panel below live status).

2. **Replace `switch_to_audit_tab` signal**:
   - Modify `on_view_artifacts` to show summary in same tab.
   - Update `ControlStation.handle_router_url` to route `internal://report/strategy/` to Operation tab.

3. **Update `handle_open_report_request`**:
   - Redirect to Operation tab's summary.

### T2.3 Portfolio Tab Enhancements
1. **Create `PortfolioOutputSummaryWidget`**:
   - New widget for portfolio report metrics, equity curve.
   - Integrate into Portfolio tab.

2. **Replace routing to audit tab**:
   - Modify `view_portfolio_report` to show summary in same tab.
   - Update `ControlStation.handle_router_url` for portfolio reports.

### T2.4 Internal Routing Adjustments
1. **Update `_step_default_tool` mapping**:
   - Map EXPORT, DECISION, STRATEGY steps to Operation tab.
   - Map PORTFOLIO step to Portfolio tab.

2. **Redirect hidden tool IDs**:
   - Ensure `audit`, `gate_dashboard`, `report` tool IDs redirect to visible tabs.

### T2.5 Smoke Test
1. **Create `test_phase2_closed_loop_smoke.py`**:
   - Lightweight test that verifies three tabs exist.
   - Mock supervisor client to simulate jobs.
   - Verify output summaries appear in same tabs.

## Next Steps
Start with BarPrepare enhancements as they are prerequisite for Operation and Portfolio.
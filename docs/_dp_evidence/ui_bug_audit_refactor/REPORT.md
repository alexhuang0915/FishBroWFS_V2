# UI Bug Audit & Refactor Report

## Scope
- Desktop UI (PySide6/Qt6) primary CTAs and action feedback.
- No backend or contract changes.

## Issues Found
1. **BAR PREPARE Confirm provided weak feedback**
   - Confirm had no inline status trace, and disabled state provided no reason.
2. **RUN STRATEGY lacked clear action trace in the refactored OP tab**
   - No explicit action state or job_id trace after submit; cancel path had no feedback.
3. **BUILD PORTFOLIO had no inline progress or blocked reason**
   - Build button always enabled, and no progress bar/trace while polling.
4. **Export JSON action lacked visible confirmation**
   - Export wrote to Advanced panel but no direct status feedback.

## Fixes Applied
- **BAR PREPARE**: Added inline status panel, disabled reason text, and confirm state trace.
- **OP (RUN STRATEGY)**: Added action status panel with busy indicator and job ID trace. Deferred submission to allow immediate UI feedback and added explicit blocked/canceled feedback.
- **Allocation (BUILD PORTFOLIO)**: Added disabled reason, progress bar, and status updates tied to polling lifecycle; build button now reflects selection state.
- **Audit (Export JSON)**: Added status/log feedback when JSON is prepared in the Advanced panel.

## Constraints Respected
- No backend API/endpoint semantics changed.
- Governance/step flow remains enforced.
- No evidence storage changes.

## Files Modified
- `src/gui/desktop/tabs/bar_prepare_tab.py`
- `src/gui/desktop/tabs/op_tab_refactored.py`
- `src/gui/desktop/tabs/allocation_tab.py`
- `src/gui/desktop/tabs/audit_tab.py`


# Manual UI Acceptance Checklist

This checklist is for human verification of Desktop UI functionality.
The automated acceptance harness has validated backend API contracts.

## Desktop UI Launch
- [ ] Launch Desktop UI via `make desktop` or `make desktop-xcb`
- [ ] Verify window appears with title bar
- [ ] Verify no immediate crash or protocol errors

## Operations (OP) Tab
- [ ] Navigate to OP tab
- [ ] Select a strategy from dropdown (should be populated)
- [ ] Select a dataset from dropdown (should be populated)
- [ ] Set date range (start/end)
- [ ] Click "Run" button
- [ ] Verify job submission (status changes to RUNNING/SUCCEEDED)
- [ ] Open report/logs/evidence via UI buttons

## Allocation (Portfolio) Tab
- [ ] Navigate to Allocation tab
- [ ] Build a portfolio with selected candidates
- [ ] Open decision desk to review portfolio weights
- [ ] Verify portfolio artifacts generation

## Audit (Explorer) Tab
- [ ] Navigate to Audit tab
- [ ] Search/filter existing jobs
- [ ] Open advanced artifacts view
- [ ] Open report for a completed job

## General UI Health
- [ ] No console errors (check terminal output)
- [ ] Responsive layout at different window sizes
- [ ] Tooltips appear on hover where expected
- [ ] All tabs load without freezing

## Notes
- This checklist is informational only; automated tests cover backend contracts.
- UI verification remains manual per product release standards.

=== Fixes Applied ===
1. Added @property jobs to JobsTableModel class in src/gui/desktop/tabs/op_tab.py
2. Fixed allocation_tab.py line 164: replaced QSizePolicy with QSpacerItem in form_layout.addItem
3. Added missing signals to OpTab: progress_signal and artifact_state_changed
4. Added missing signal to AllocationTab: allocation_changed

# DISCOVERY LOG - BarPrepare Auto Instruments

## PART 0 — DISCOVERY FINDINGS

### 1. BarPrepare Page + SSOT State Object

**Key Files Found:**
- `src/gui/desktop/state/bar_prepare_state.py` - Contains `BarPrepareState` and `BarPrepareStateHolder`
- `src/gui/desktop/tabs/bar_prepare_tab.py` - Main BarPrepare tab implementation
- `src/gui/desktop/dialogs/raw_input_dialog.py` - RAW INPUT dialog
- `src/gui/desktop/dialogs/prepare_plan_dialog.py` - PREPARE PLAN dialog

**BarPrepareState Structure:**
```python
class BarPrepareState(BaseModel):
    raw_inputs: List[str] = Field(default_factory=list, description="Selected raw data files")
    prepare_plan: PreparePlan = Field(default_factory=PreparePlan, description="Prepare plan configuration")
    bar_inventory_summary: Optional[Dict[str, Any]] = Field(default=None, description="Read-only BAR inventory summary")
    confirmed: bool = Field(default=False, description="Whether the step was confirmed")
    last_updated: datetime = Field(default_factory=datetime.now, description="When state was last updated")
```

**PreparePlan Structure:**
```python
class PreparePlan(BaseModel):
    instruments: List[str] = Field(default_factory=list, description="Selected instruments")
    timeframes: List[str] = Field(default_factory=list, description="Selected timeframes")
    artifacts_preview: List[str] = Field(default_factory=list, description="Preview of planned artifacts (display-only)")
```

**SSOT Access Pattern:**
- Singleton `bar_prepare_state` instance imported from `src/gui/desktop/state/bar_prepare_state`
- Used via `bar_prepare_state.get_state()` and `bar_prepare_state.update_state()`

### 2. Prepare Plan Dialog Implementation

**File:** `src/gui/desktop/dialogs/prepare_plan_dialog.py`

**Key Findings:**
- Dialog title: `"PREPARE PLAN - Define Instrument × Timeframe Combinations"`
- Has two multi-select groups:
  1. **Instruments (multi-select)** - Currently user-selectable via checkbox list
  2. **Timeframes (multi-select)** - User-selectable via checkbox list
- Uses `MultiSelectListWidget` for both instruments and timeframes
- Current instruments are loaded from SSOT: `state.prepare_plan.instruments`
- Current timeframes are loaded from SSOT: `state.prepare_plan.timeframes`

**Current UI Flow:**
1. User selects instruments (checkboxes)
2. User selects timeframes (checkboxes)
3. Artifact preview shows `instruments × timeframes` combinations
4. Confirm commits `instruments` and `timeframes` to SSOT

**Accept Handler (lines 280-304):**
```python
def accept(self):
    # Generate artifacts preview list
    artifacts_preview = []
    for instr in sorted(self.selected_instruments):
        for tf in sorted(self.selected_timeframes):
            artifacts_preview.append(f"{instr} {tf} .PARSET")
    
    # Commit to SSOT
    bar_prepare_state.update_state(
        prepare_plan={
            "instruments": list(self.selected_instruments),
            "timeframes": list(self.selected_timeframes),
            "artifacts_preview": artifacts_preview
        },
        confirmed=False,
    )
```

### 3. RAW Input Dialog + SSOT Storage

**File:** `src/gui/desktop/dialogs/raw_input_dialog.py`

**Key Findings:**
- Dialog title: `"RAW INPUT - Select Raw Data Files"`
- Shows list of raw files discovered via `_discover_raw_files()` method
- User selects files via checkboxes
- Confirm commits `raw_inputs` to SSOT

**Accept Handler (lines 185-201):**
```python
def accept(self):
    # Update dialog-local selection from checkboxes
    self.selected_files.clear()
    for i in range(self.file_list.count()):
        item = self.file_list.item(i)
        if item.checkState() == Qt.CheckState.Checked:
            self.selected_files.add(item.text())
    
    # Commit to SSOT
    bar_prepare_state.update_state(
        raw_inputs=list(self.selected_files),
        confirmed=False,
    )
```

**RAW File Discovery:**
- Uses `_discover_raw_files()` method (lines 153-181)
- Scans `data/raw/` directory for `.txt` files
- Returns filenames like `CME.MNQ HOT-TOUCHANCE-CME-Futures-Minute-Trade.txt`

### 4. Existing "Instrument-From-RAW" Logic

**Search Results:**
- No existing dedicated function for parsing instruments from raw filenames
- Found pattern in `src/contracts/dimensions.py` (lines 64-92) that extracts instrument from dataset ID:
  ```python
  # Simple derivation: take first two parts (e.g., "CME.MNQ.60m.2020-2024" -> "CME.MNQ")
  parts = dataset_id.split(".")
  if len(parts) >= 2:
      derived_symbol = f"{parts[0]}.{parts[1]}"
  ```

**RAW Filename Pattern:**
From discovered files, pattern appears to be:
- `CME.MNQ HOT-TOUCHANCE-CME-Futures-Minute-Trade.txt`
- `TWF.MXF HOT-TOUCHANCE-TWF-Futures-Minute-Trade.txt`
- `OSE.NK225M HOT-TOUCHANCE-OSE-Futures-Minute-Trade.txt`

**Instrument Extraction Rule:**
- First whitespace-delimited token before space
- Format: `EXCHANGE.SYMBOL` (e.g., `CME.MNQ`, `TWF.MXF`, `OSE.NK225M`)
- Pattern: `[A-Z0-9]+\.[A-Z0-9]+`

### 5. Current Data Flow Issues

**Problem: Double-Define Instrument**
1. User selects RAW files (which contain instrument in filename)
2. User must also manually select instruments in Prepare Plan dialog
3. This creates redundancy and potential mismatch

**Goal:** Remove instrument selection UI, derive instruments automatically from selected RAW files.

### 6. BarPrepare Tab Summary Display

**File:** `src/gui/desktop/tabs/bar_prepare_tab.py`

**Current Summary Logic (lines 216-221):**
```python
if instr_count == 0 or tf_count == 0:
    self.prepare_plan_panel.update_status("○", "EMPTY", "No instruments or timeframes selected")
else:
    artifact_count = len(state.prepare_plan.artifacts_preview)
    summary = f"{instr_count} instruments × {tf_count} timeframes → {artifact_count} artifacts"
    self.prepare_plan_panel.update_status("✓", "CONFIGURED", summary)
```

**Confirm Button Logic (lines 233-240):**
```python
def update_confirm_button(self):
    state = bar_prepare_state.get_state()
    raw_selected = len(state.raw_inputs) > 0
    plan_configured = (len(state.prepare_plan.instruments) > 0 and 
                      len(state.prepare_plan.timeframes) > 0)
    
    self.confirm_btn.setEnabled(raw_selected and plan_configured)
```

### 7. Bars Build Algorithm Integration

**Need to Discover:**
- Where bars build pipeline uses `bar_prepare_state.prepare_plan.instruments`
- Likely in `src/control/supervisor/handlers/build_data.py` or similar
- Will need to update to use derived instruments instead of user-selected

## NEXT STEPS

Based on discovery, implementation plan:

1. **PART 1:** Create `derive_instruments_from_raw()` function in appropriate module
2. **PART 2:** Update `BarPrepareState` to include `derived_instruments` field
3. **PART 3:** Refactor `prepare_plan_dialog.py` to remove instrument selection UI
4. **PART 4:** Update data flow: RAW confirm → derive instruments → Prepare Plan shows derived instruments
5. **PART 5:** Update bars build pipeline to use derived instruments
6. **PART 6:** Create/update tests
7. **PART 7:** Verification
8. **PART 8:** Evidence bundle
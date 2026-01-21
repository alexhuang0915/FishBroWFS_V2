# OP Tab Layout Discovery

## Current Layout Hierarchy (as of 2026-01-18)

The refactored OP tab (`OpTabRefactored` in `src/gui/desktop/tabs/op_tab_refactored.py`) follows a vertical layout structure with three main sections:

### 1. System Context Section (Top)
- **System Gates Widget**: `GateSummaryWidget` instance showing system-wide gate status
- Positioned at the very top of the layout (lines 58-61)

### 2. Main Content Area (Middle)
- **Full-width Banner**: "OPERATION CONSOLE" title with blue background (lines 64-74)
- **Description Label**: Subtitle explaining the modal dialog approach (lines 77-83)
- **Horizontal Splitter**: Divides left and right panels (lines 86-255)

#### Left Panel (Summary Panels)
Contains three equal-weight summary panels, each with:
- **Title**: GroupBox with colored border (RUN INTENT: blue, DATA READINESS: green, JOB TRACKER: purple)
- **Description**: Brief explanation of the panel's purpose
- **Content Area**: Dynamic summary text showing current state
- **Edit Button**: Primary-colored "Edit..." button that opens respective modal dialog

#### Right Panel (Execute Panel)
Contains the execution controls:
- **RUN STRATEGY Button**: Large red primary action button (lines 163-189)
- **Disabled Reason Frame**: GroupBox showing why RUN button is disabled (lines 192-216)
- **Status Summary Frame**: GroupBox showing system status (lines 219-242)

### 3. Status Bar (Bottom)
- **Refactored Indicator**: "[REFACTORED] Ready - OP tab with 3 summary panels & modal dialogs" (lines 260-270)
- Green badge-style label indicating the refactored implementation is active

## Key Observations

1. **Visual Hierarchy Issues**:
   - Large "OPERATION CONSOLE" banner occupies significant vertical space
   - Three summary panels are visually equal, not representing a step-wise flow
   - All panels use identical "Edit..." buttons regardless of their function

2. **Execute Panel Concerns**:
   - Disabled reason shows all reasons (up to 3) by default, creating visual noise
   - Status summary shows full bullet list instead of compact indicators
   - No collapsible sections for detailed information

3. **Refactored Badge Placement**:
   - The "[OP REFACTORED ACTIVE]" badge is in the main UI flow (added by `op_tab.py` adapter)
   - Competes visually with user workflow elements

## Layout Structure Summary

```
OpTabRefactored (QVBoxLayout)
├── GateSummaryWidget (System Gates)
├── "OPERATION CONSOLE" Banner (full-width)
├── Description Label
├── QSplitter (horizontal)
│   ├── Left Widget (QVBoxLayout)
│   │   ├── RUN INTENT Panel (QGroupBox)
│   │   │   ├── Description
│   │   │   ├── Content Label
│   │   │   └── "Edit..." Button
│   │   ├── DATA READINESS Panel (QGroupBox)
│   │   │   ├── Description
│   │   │   ├── Content Label
│   │   │   └── "Edit..." Button
│   │   └── JOB TRACKER Panel (QGroupBox)
│   │       ├── Description
│   │       ├── Content Label
│   │       └── "Edit..." Button
│   └── Right Widget (QVBoxLayout)
│       └── EXECUTE GroupBox
│           ├── RUN STRATEGY Button
│           ├── Disabled Reason GroupBox
│           │   └── Reason Label
│           └── Status Summary GroupBox
│               └── Status Label
└── Status Label ("[REFACTORED] Ready...")
```

This discovery provides the baseline for implementing the UX refinements specified in the task requirements.
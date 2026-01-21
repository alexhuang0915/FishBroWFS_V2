# UI UX Baseline Contract V1

## Objective
Improve basic usability of the desktop GUI without changing business logic or domain features.
Focus on standard interaction affordances: Selection, Copy, Context Menus, Keyboard Shortcuts.

## 1. Text Interaction & Selection
**Requirement**: Key information fields must be selectable and copyable. Users must be able to copy IDs, paths, and error messages.

**Target Widgets**:
- **Job IDs**: Any QLabel or cell displaying a Job ID (UUID).
- **Paths**: Any QLabel or cell displaying a file path (e.g., artifact paths).
- **Log/Reasoning**: Any text area displaying execution logs, error traces, or admission reasoning.

**Implementation Standard**:
- `QLabel`: `setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)`
- `QLineEdit`: Read-only, but valid selection.
- `QTextEdit`: Read-only, but valid selection.

## 2. Context Menus
**Requirement**: Right-click on key entities should provide copy actions.

**Standard Actions**:
- `Copy`: Copy selected text.
- `Copy ID`: Copy full UUID (if truncated or context-specific).
- `Copy Path`: Copy full absolute path.

**Target Surfaces**:
- **Ops Tab > Job List**: Right-click on row -> `Copy Job ID`, `Copy Output Path`.
- **Research Tab > Top-K Table**: Right-click on row -> `Copy Strategy ID`, `Copy Params`.
- **Portfolio Tab > Admission Cards**: Right-click -> `Copy Reason`, `Copy Component ID`.

## 3. Keyboard Shortcuts
**Requirement**: Standard shortcuts should work where expected.

**Shortcuts**:
- `Ctrl+A` (Select All):
    - Must work in Log/Console views.
    - Must work in `QTableView` (select all rows) if multi-selection is relevant.
- `Ctrl+C` (Copy):
    - Must work on selected text/rows.

## 4. Accessibility & Consistency
- **Tooltips**: Truncated fields (e.g., paths, hashes) must show full text in Tooltip.
- **Visual Feedback**: Selection highlight color should be visible (default OS style).

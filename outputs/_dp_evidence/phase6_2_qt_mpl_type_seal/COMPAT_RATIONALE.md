# Compatibility Rationale

## Why Centralize?

Scattered `# type: ignore` comments, ad‑hoc `Optional` assertions, and duplicated Qt6 enum references make the codebase fragile and hard to maintain. A single change in PySide6 stubs or Matplotlib backend would require editing dozens of files.

By moving these patterns into a dedicated `_compat` package:

1. **Single source of truth** for Qt6+Matplotlib imports.
2. **Isolated type ignores** – only one place needs updating when stubs improve.
3. **Consistent naming** – all desktop modules use the same aliases.
4. **Easier testing** – compatibility logic can be unit‑tested independently.

## What Was Moved

### 1. `typing.py`
- `IndexLike` union for model‑index parameters.
- `assert_not_none` helper for optional widget attributes.
- `option_rect` helper for `QStyleOptionViewItem.rect` with a single type ignore.

### 2. `mpl_qt.py`
- `FigureCanvas` and `NavigationToolbar` imports with fallback from `backend_qtagg` to `backend_qt5agg`.
- Ensures runtime compatibility across Matplotlib versions.

### 3. `qt_enums.py`
- Short‑hand constants for commonly used Qt6 enum values (e.g., `AlignLeft`, `DisplayRole`).
- Reduces verbosity and prevents accidental use of Qt5‑style constants.

## How to Use

### Before
```python
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from typing import Union
from PySide6.QtCore import QModelIndex, QPersistentModelIndex

IndexLike = Union[QModelIndex, QPersistentModelIndex, int]

assert self.tab_widget is not None
self.tab_widget.addTab(...)

rect = option.rect  # type: ignore
```

### After
```python
from gui.desktop._compat.mpl_qt import FigureCanvas, NavigationToolbar
from gui.desktop._compat.typing import IndexLike, assert_not_none, option_rect

self.tab_widget = assert_not_none(self.tab_widget)
self.tab_widget.addTab(...)

rect = option_rect(option)
```

## Impact on Existing Code

- No functional changes; only import paths and typing patterns are updated.
- All existing `# type: ignore` comments related to Qt6/Matplotlib can be removed from desktop modules.
- The `make check` suite must continue to pass with zero failures.

## Future Maintenance

When PySide6 stubs improve:
1. Remove the `# type: ignore` inside `option_rect`.
2. Update `mpl_qt.py` if Matplotlib backend naming changes.

When Qt7 arrives:
1. Update `qt_enums.py` to reflect new enum paths.
2. Adjust `mpl_qt.py` for Qt7 backend.

The rest of the desktop UI code remains unchanged.
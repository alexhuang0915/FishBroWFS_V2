#!/usr/bin/env python3
"""
Desktop launcher for FishBroWFS Control Station.
Wayland-safe, XCB-independent, governance-clean.
"""

# =========================
# CRITICAL: Qt platform selection
# MUST be before ANY PySide6 / Qt import
# =========================
import os
import sys
from pathlib import Path

# Force Wayland when available to avoid xcb dependency issues
# This must happen BEFORE Qt is imported
if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "wayland"

# Optional debug (can remove later)
print("QT_QPA_PLATFORM =", os.environ.get("QT_QPA_PLATFORM"))

# =========================
# Path bootstrap
# =========================
# Add src to PYTHONPATH
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

# =========================
# Qt imports (SAFE NOW)
# =========================
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFile, QTextStream, QTimer
from PySide6.QtGui import QFont

from gui.desktop.control_station import ControlStation


def load_stylesheet(app: QApplication) -> bool:
    """Load and apply QSS stylesheet."""
    style_path = (
        Path(__file__).parent.parent
        / "src"
        / "gui"
        / "desktop"
        / "styles"
        / "pro_dark.qss"
    )

    if not style_path.exists():
        fallback = (
            Path(__file__).parent.parent
            / "src"
            / "gui"
            / "desktop"
            / "style.qss"
        )
        print(f"WARNING: Pro dark stylesheet not found, falling back to {fallback}")
        style_path = fallback

    if not style_path.exists():
        print(f"WARNING: Stylesheet not found at {style_path}")
        return False

    try:
        file = QFile(str(style_path))
        if file.open(QFile.ReadOnly | QFile.Text):
            stream = QTextStream(file)
            app.setStyleSheet(stream.readAll())
            file.close()
            print(f"Loaded stylesheet from {style_path}")
            return True
        else:
            print(f"ERROR: Could not open stylesheet file {style_path}")
            return False
    except Exception as e:
        print(f"ERROR: Failed to load stylesheet: {e}")
        return False


def main() -> None:
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("FishBroWFS Control Station")
    app.setOrganizationName("FishBroWFS")

    # Global font (safe)
    app.setFont(QFont("Segoe UI", 10))

    # Load stylesheet
    load_stylesheet(app)

    # Create main window
    window = ControlStation()
    
    # 1. 先以一般模式顯示 (讓 Wayland 正確初始化標題欄 Buffer)
    window.show()
    
    # 2. 延遲 200 毫秒後再最大化，這能避開啟動時的 Buffer 協議衝突
    QTimer.singleShot(200, window.showMaximized)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

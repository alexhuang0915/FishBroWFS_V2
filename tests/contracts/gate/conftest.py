import pytest
import sys

@pytest.fixture(scope="session", autouse=True)
def qapp_session():
    """Ensure QApplication exists for UI tests."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            # argv=[] avoids side effects from sys.argv
            app = QApplication([])
        yield app
    except ImportError:
        yield None

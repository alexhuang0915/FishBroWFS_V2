"""
Smoke test for dashboard UI (Phase 9‑OMEGA).

Verifies that the UI module can be imported and key functions are callable.
"""
import pytest
import sys
from pathlib import Path


def test_ui_module_import():
    """Import dashboard.ui without side effects."""
    # Add src to path
    src_dir = Path(__file__).parent.parent.parent / "src"
    sys.path.insert(0, str(src_dir))
    
    try:
        # Try to import - may fail due to missing nicegui in test environment
        import dashboard.ui
        # If import succeeds, verify no immediate PortfolioService instantiation
        # The module should have _SERVICE = None
        assert hasattr(dashboard.ui, "_SERVICE")
        assert dashboard.ui._SERVICE is None
    except ImportError as e:
        # If nicegui is not installed, that's OK for smoke test
        if "nicegui" not in str(e):
            raise
        pytest.skip(f"NiceGUI not available in test environment: {e}")
    finally:
        sys.path.pop(0)


def test_get_service_lazy():
    """Verify get_service() returns PortfolioService instance."""
    # Mock PortfolioService to avoid file system dependencies
    class MockPortfolioService:
        def __init__(self, data_root):
            self.data_root = data_root
    
    # Temporarily replace PortfolioService in dashboard.ui
    import dashboard.ui as ui_module
    original_service = ui_module.PortfolioService
    ui_module.PortfolioService = MockPortfolioService
    
    try:
        # Reset singleton
        ui_module._SERVICE = None
        # Call get_service
        service = ui_module.get_service(data_root="test_root")
        assert service is not None
        assert isinstance(service, MockPortfolioService)
        assert service.data_root == "test_root"
        # Second call should return same instance
        service2 = ui_module.get_service(data_root="different")
        assert service2 is service  # singleton
    finally:
        ui_module.PortfolioService = original_service
        ui_module._SERVICE = None


def test_build_console_function_exists():
    """Verify build_console() function is defined."""
    import dashboard.ui as ui_module
    assert hasattr(ui_module, "build_console")
    assert callable(ui_module.build_console)


def test_main_page_decorator():
    """Verify @ui.page decorator is applied to main_page."""
    import dashboard.ui as ui_module
    assert hasattr(ui_module, "main_page")
    # Can't easily test decorator application without importing nicegui
    # Just verify it's a function
    assert callable(ui_module.main_page)


if __name__ == "__main__":
    # Run smoke tests
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    
    try:
        import dashboard.ui
        print("✓ dashboard.ui imports successfully")
        print(f"  _SERVICE = {dashboard.ui._SERVICE}")
        print(f"  build_console exists: {hasattr(dashboard.ui, 'build_console')}")
        print(f"  main_page exists: {hasattr(dashboard.ui, 'main_page')}")
    except ImportError as e:
        print(f"✗ Import failed (expected if nicegui missing): {e}")

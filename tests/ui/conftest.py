"""Pytest fixtures for UI contract tests."""
import os
import pytest
from ._ui_server import start_ui_server, wait_for_http_ok, stop_process


def pytest_configure(config):
    """Register ui_contract marker."""
    config.addinivalue_line(
        "markers",
        "ui_contract: UI style contract tests requiring Playwright and UI server"
    )


@pytest.fixture(scope="session")
def ui_server():
    """Start UI server as a session-scoped fixture.
    
    This fixture is automatically skipped unless FISHBRO_UI_CONTRACT=1.
    """
    if os.getenv("FISHBRO_UI_CONTRACT") != "1":
        pytest.skip("UI contract tests require FISHBRO_UI_CONTRACT=1")
    
    # Check Playwright availability
    try:
        import playwright
    except ImportError:
        pytest.skip("Playwright not installed")
    
    port = 8080
    proc = start_ui_server(port=port)
    try:
        wait_for_http_ok(f"http://localhost:{port}", timeout_s=30)
        yield f"http://localhost:{port}"
    finally:
        stop_process(proc)


@pytest.fixture
def page(ui_server, page):
    """Provide a Playwright page fixture configured for UI contract tests.
    
    This fixture depends on pytest-playwright's `page` fixture.
    """
    # Navigate to the UI server root
    page.goto(ui_server)
    yield page
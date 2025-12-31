"""Basic UI contract test to verify Playwright infrastructure."""
import os
import pytest

# Gating: UI contract tests require FISHBRO_UI_CONTRACT=1
if os.getenv("FISHBRO_UI_CONTRACT") != "1":
    pytest.skip("UI contract tests require FISHBRO_UI_CONTRACT=1", allow_module_level=True)


@pytest.mark.ui_contract
def test_ui_server_root(page):
    """Verify that the UI server serves the root page with expected title."""
    # The page fixture already navigates to ui_server root
    assert page.url.startswith("http://localhost:8080")
    # Check page title
    title = page.title()
    assert "FishBro War Room" in title or "Nexus UI" in title


@pytest.mark.ui_contract
def test_ui_theme_applied(page):
    """Verify that the dark theme CSS class is present."""
    # The UI constitution enforces dark theme
    body = page.locator("body")
    class_list = body.get_attribute("class") or ""
    # Should have 'dark' class or similar
    assert "dark" in class_list.lower()


@pytest.mark.ui_contract
def test_header_present(page):
    """Verify that the global header is rendered."""
    header = page.locator("header")
    assert header.count() >= 1
    # Header should contain some text
    header_text = header.text_content()
    assert len(header_text.strip()) > 0
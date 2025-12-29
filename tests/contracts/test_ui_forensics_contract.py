"""
UI Forensic Dump Contract Tests.

Validates invariants of the UI forensic dump system.
"""
import json
import tempfile
import os
from pathlib import Path

from gui.nicegui.services.forensics_service import generate_ui_forensics, write_forensics_files


def test_forensics_generate_deploy_page_not_empty():
    """Deploy page must have at least one UI element (non‑zero dynamic count)."""
    snapshot = generate_ui_forensics()
    # Check dynamic counts for deploy page
    pages_dynamic = snapshot.get("pages_dynamic", {})
    deploy_info = pages_dynamic.get("deploy")
    assert deploy_info is not None, "Deploy page missing from dynamic diagnostics"
    assert deploy_info.get("render_attempted", False), "Deploy page render not attempted"
    registry_snapshot = deploy_info.get("registry_snapshot", {})
    # Sum of all element counts must be > 0
    total_elements = sum(registry_snapshot.values())
    assert total_elements > 0, f"Deploy page is dynamically empty (counts: {registry_snapshot})"
    # At least one of buttons, inputs, selects, checkboxes, cards, tables, logs should be >0
    # (optional) but we can log
    print(f"Deploy page dynamic counts: {registry_snapshot}")


def test_forensics_ui_registry_non_empty():
    """UI registry must contain non‑zero global counts for at least one element type."""
    snapshot = generate_ui_forensics()
    ui_registry = snapshot.get("ui_registry", {})
    global_counts = ui_registry.get("global", {})
    # At least one element type should have been registered
    total_global = sum(global_counts.values())
    assert total_global > 0, f"UI registry global counts empty: {global_counts}"
    # Ensure by_page entries exist for all contract pages
    by_page = ui_registry.get("by_page", {})
    contract_pages = ["dashboard", "wizard", "history", "candidates", "portfolio", "deploy", "settings"]
    for page in contract_pages:
        assert page in by_page, f"Page {page} missing from UI registry by_page"
        # Not required to have non-zero counts (some pages may be empty)
    print(f"UI registry global counts: {global_counts}")


def test_forensics_write_files():
    """Forensic file writing must produce valid JSON and text files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot = generate_ui_forensics()
        paths = write_forensics_files(snapshot, outputs_dir=tmpdir)
        json_path = paths["json_path"]
        txt_path = paths["txt_path"]
        assert Path(json_path).exists()
        assert Path(txt_path).exists()
        # Validate JSON can be loaded
        with open(json_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["meta"]["timestamp_iso"]
        # Ensure the loaded snapshot matches the original (ignoring meta timestamps)
        # We'll just check that pages_dynamic exists
        assert "pages_dynamic" in loaded
        print(f"Forensic files written: {json_path}, {txt_path}")


if __name__ == "__main__":
    # Quick local run
    test_forensics_generate_deploy_page_not_empty()
    test_forensics_ui_registry_non_empty()
    test_forensics_write_files()
    print("All UI forensic contract tests passed.")
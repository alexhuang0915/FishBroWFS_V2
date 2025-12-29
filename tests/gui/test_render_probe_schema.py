"""
Test render probe schema and basic invariants.
"""
import pytest
from gui.nicegui.services.render_probe_service import (
    probe_all_pages,
    probe_page,
    build_render_diff_report,
)
from gui.nicegui.contract.ui_contract import PAGE_IDS


def test_probe_all_pages_returns_all_page_ids():
    """probe_all_pages() returns entries for all PAGE_IDS."""
    results = probe_all_pages()
    assert isinstance(results, dict)
    assert set(results.keys()) == set(PAGE_IDS)


def test_each_entry_has_required_keys():
    """Each entry contains required keys and deterministic types."""
    results = probe_all_pages()
    required_keys = {
        "page_id",
        "module",
        "render_ok",
        "errors",
        "traceback",
        "counts",
        "markers",
    }
    for page_id, entry in results.items():
        assert isinstance(entry, dict)
        missing = required_keys - set(entry.keys())
        assert not missing, f"{page_id} missing keys: {missing}"
        # Type checks
        assert entry["page_id"] == page_id
        assert entry["module"] is None or isinstance(entry["module"], str)
        assert isinstance(entry["render_ok"], bool)
        assert isinstance(entry["errors"], list)
        assert entry["traceback"] is None or isinstance(entry["traceback"], str)
        assert isinstance(entry["counts"], dict)
        assert isinstance(entry["markers"], list)
        # Counts dict keys
        for key in ["buttons", "inputs", "selects", "checkboxes", "cards", "tables", "logs"]:
            assert key in entry["counts"], f"{page_id} missing count key {key}"
            assert isinstance(entry["counts"][key], int)


def test_build_render_diff_report_stable_schema():
    """build_render_diff_report() produces a stable schema."""
    results = probe_all_pages()
    report = build_render_diff_report(results)
    assert isinstance(report, dict)
    required_keys = {"anomalies", "per_page", "summary"}
    assert set(report.keys()) == required_keys
    # anomalies list
    anomalies = report["anomalies"]
    assert isinstance(anomalies, list)
    for a in anomalies:
        assert isinstance(a, dict)
        assert "page_id" in a
        assert "severity" in a
        assert "reason" in a
        assert "suggestion" in a
    # per_page dict
    per_page = report["per_page"]
    assert isinstance(per_page, dict)
    for page_id, info in per_page.items():
        assert isinstance(info, dict)
        assert "render_ok" in info
        assert "total_elements" in info
        assert "errors" in info
        assert "diff" in info
    # summary dict
    summary = report["summary"]
    assert isinstance(summary, dict)
    for key in ("passed", "failed", "total"):
        assert key in summary
        assert isinstance(summary[key], int)
    assert summary["total"] == len(PAGE_IDS)
    assert summary["passed"] + summary["failed"] == summary["total"]


def test_probe_page_with_invalid_page_id():
    """probe_page with invalid page_id returns errors."""
    result = probe_page("invalid_page")
    assert result["page_id"] == "invalid_page"
    assert result["render_ok"] is False
    assert result["errors"]
    assert result["module"] is None or result["module"] is None
    # counts empty
    assert all(v == 0 for v in result["counts"].values())
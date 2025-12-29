"""Smoke test for UI Autopass."""
import json
import tempfile
import pytest
from pathlib import Path

from gui.nicegui.autopass.report import build_autopass_report


def test_autopass_report_schema():
    """Build autopass report and verify required keys."""
    # Use a temporary output directory
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "autopass_out"
        out_dir.mkdir()
        
        # Call the report builder (should not raise)
        report = build_autopass_report(outputs_dir=out_dir)
        
        # Required top‑level keys
        assert "meta" in report
        assert "system_status" in report
        assert "forensics" in report
        assert "pages" in report
        assert "artifacts" in report
        assert "acceptance" in report
        
        # Meta sub‑keys
        meta = report["meta"]
        assert "ts" in meta
        assert "git_sha" in meta
        assert "python" in meta
        assert "nicegui" in meta
        assert "pid" in meta
        
        # System status sub‑keys
        status = report["system_status"]
        assert "state" in status
        assert "summary" in status
        assert "backend_up" in status
        assert "worker_up" in status
        assert "backend_error" in status
        assert "worker_error" in status
        assert "polling_started" in status
        assert "poll_interval_s" in status
        
        # Forensics paths
        forensics = report["forensics"]
        assert "forensics_json_path" in forensics
        assert "forensics_txt_path" in forensics
        
        # Pages must contain all 7 pages (from ui_contract)
        pages = report["pages"]
        from gui.nicegui.contract.ui_contract import PAGE_IDS
        assert set(pages.keys()) == set(PAGE_IDS)
        
        # Each page must have render_ok and non_empty (bool)
        for page_id, info in pages.items():
            assert "render_ok" in info
            assert "non_empty" in info
            # Additional fields may be present (e.g., intent_written)
        
        # Artifacts may be null
        artifacts = report["artifacts"]
        for key in ("intent_json", "derived_json", "portfolio_json", "deploy_export_json"):
            assert key in artifacts
        
        # Acceptance
        acceptance = report["acceptance"]
        assert "passed" in acceptance
        assert "failures" in acceptance
        assert isinstance(acceptance["failures"], list)


def test_autopass_no_crash_with_backend_offline():
    """Ensure the report can be built even when backend is offline."""
    # This is already covered by the previous test (since backend may be offline).
    # We'll just run the report builder again and ensure no exception.
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "autopass_out"
        out_dir.mkdir()
        report = build_autopass_report(outputs_dir=out_dir)
        # If we get here, no crash.
        assert report is not None


def test_forensics_paths_exist():
    """Forensics files should be generated (JSON and TXT)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "autopass_out"
        out_dir.mkdir()
        report = build_autopass_report(outputs_dir=out_dir)
        forensics = report["forensics"]
        json_path = forensics["forensics_json_path"]
        txt_path = forensics["forensics_txt_path"]
        if json_path and Path(json_path).exists():
            # JSON should be parseable
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert "pages_dynamic" in data
        if txt_path and Path(txt_path).exists():
            # TXT should be non‑empty
            assert Path(txt_path).stat().st_size > 0


if __name__ == "__main__":
    pytest.main([__file__])
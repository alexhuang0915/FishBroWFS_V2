"""Test that UI forensics summary is not UNKNOWN.

This test enforces the Evidence Guarantee from the UI Constitution:
UI forensics must produce a meaningful summary, not just "UNKNOWN".

The test runs the UI forensics service and verifies that the generated
summary contains actual system state information.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from gui.nicegui.services.forensics_service import (
    generate_ui_forensics,
    write_forensics_files,
)


class TestUIForensicsSummaryNotUnknown:
    """Test that UI forensics produces meaningful summaries."""
    
    def test_forensics_summary_not_unknown(self):
        """Generate UI forensics and verify summary is not UNKNOWN."""
        # Create temporary output directory
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            
            # Generate forensics snapshot
            snapshot = generate_ui_forensics(outputs_dir=str(out_dir))
            
            # Check that snapshot has required structure
            assert "system_status" in snapshot, "Forensics snapshot missing 'system_status' key"
            status = snapshot["system_status"]
            
            # Check for state field
            assert "state" in status, "Status missing 'state' field"
            state = status["state"]
            
            # The state must not be "UNKNOWN"
            assert state != "UNKNOWN", (
                f"UI forensics state is UNKNOWN. "
                f"Full status: {status}"
            )
            
            # State should be one of the expected values
            expected_states = ["ONLINE", "DEGRADED", "OFFLINE"]
            assert state in expected_states, (
                f"UI forensics state '{state}' not in expected values {expected_states}. "
                f"Full status: {status}"
            )
            
            # Check for summary field
            assert "summary" in status, "Status missing 'summary' field"
            summary = status["summary"]
            
            # Summary must not be empty or placeholder
            assert summary, "UI forensics summary is empty"
            assert summary != "No summary", f"UI forensics summary is placeholder: {summary}"
            assert "UNKNOWN" not in summary.upper(), f"UI forensics summary contains UNKNOWN: {summary}"
    
    def test_forensics_files_created(self):
        """Test that UI forensics creates both JSON and text files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            
            # Generate forensics snapshot
            snapshot = generate_ui_forensics(outputs_dir=str(out_dir))
            
            # Write files
            result = write_forensics_files(snapshot, outputs_dir=str(out_dir))
            
            # Check result contains file paths
            assert "json_path" in result, "Result missing 'json_path'"
            assert "txt_path" in result, "Result missing 'txt_path'"
            
            json_path = Path(result["json_path"])
            txt_path = Path(result["txt_path"])
            
            # Verify files exist
            assert json_path.exists(), f"JSON file not created: {json_path}"
            assert txt_path.exists(), f"Text file not created: {txt_path}"
            
            # Verify files have content
            assert json_path.stat().st_size > 0, f"JSON file is empty: {json_path}"
            assert txt_path.stat().st_size > 0, f"Text file is empty: {txt_path}"
            
            # Verify JSON can be parsed and contains state
            with open(json_path, "r", encoding="utf-8") as f:
                json_content = json.load(f)
            
            assert "system_status" in json_content, "JSON missing 'system_status' key"
            assert "state" in json_content["system_status"], "JSON status missing 'state'"
            assert json_content["system_status"]["state"] != "UNKNOWN", (
                f"JSON file contains UNKNOWN state: {json_content['system_status']}"
            )
    
    def test_cli_forensics_summary_not_unknown(self):
        """Test that the CLI script produces non-UNKNOWN summary."""
        # Run the UI forensics CLI script
        cmd = [sys.executable, "-m", "scripts.ui_forensics_dump"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
                timeout=30,
            )
            
            # Check command succeeded
            assert result.returncode == 0, (
                f"UI forensics CLI failed with exit code {result.returncode}. "
                f"Stderr: {result.stderr}"
            )
            
            # Parse output to find summary line
            output_lines = result.stdout.split("\n")
            summary_line = None
            for line in output_lines:
                if "[SUMMARY]" in line:
                    summary_line = line
                    break
            
            assert summary_line is not None, "No [SUMMARY] line in CLI output"
            
            # Extract state from summary line
            # Format: [SUMMARY] System state: ONLINE (System fully operational)
            if "System state:" in summary_line:
                # Get the part after "System state:"
                state_part = summary_line.split("System state:")[1].strip()
                # Extract the state (first word before space or parenthesis)
                state = state_part.split()[0].strip("()")
                
                # Verify state is not UNKNOWN
                assert state != "UNKNOWN", (
                    f"CLI summary state is UNKNOWN. "
                    f"Full summary line: {summary_line}"
                )
                
                # State should be one of expected values
                expected_states = ["ONLINE", "DEGRADED", "OFFLINE"]
                assert state in expected_states, (
                    f"CLI summary state '{state}' not in {expected_states}. "
                    f"Full summary line: {summary_line}"
                )
            
        except subprocess.TimeoutExpired:
            pytest.fail("UI forensics CLI timed out after 30 seconds")
    
    def test_forensics_contains_required_sections(self):
        """Test that forensics snapshot contains all required sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            
            # Generate forensics snapshot
            snapshot = generate_ui_forensics(outputs_dir=str(out_dir))
            
            # Required top-level sections (updated for new structure)
            required_sections = [
                "meta",
                "system_status",
                "pages_static",
                "ui_registry",
                "summary",
                "state_snapshot",
            ]
            
            for section in required_sections:
                assert section in snapshot, f"Forensics snapshot missing '{section}' section"
            
            # System status section must have state and summary
            status = snapshot["system_status"]
            assert "state" in status, "Status missing 'state'"
            assert "summary" in status, "Status missing 'summary'"
            
            # Meta section must have basic info
            meta = snapshot["meta"]
            assert "python_version" in meta, "Meta missing 'python_version'"
            assert "timestamp_iso" in meta, "Meta missing 'timestamp_iso'"
            
            # Pages static must contain all pages
            pages_static = snapshot["pages_static"]
            assert isinstance(pages_static, dict), "pages_static should be a dict"
            assert len(pages_static) > 0, "pages_static should not be empty"
            
            # UI registry must have global counts
            ui_registry = snapshot["ui_registry"]
            assert "global" in ui_registry, "UI registry missing 'global'"
            assert "pages" in ui_registry, "UI registry missing 'pages'"
            
            # Summary must exist
            summary = snapshot["summary"]
            assert summary, "Summary should not be empty"
            
            # State snapshot must have wizard state
            state_snapshot = snapshot["state_snapshot"]
            assert "wizard_state" in state_snapshot, "State snapshot missing 'wizard_state'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
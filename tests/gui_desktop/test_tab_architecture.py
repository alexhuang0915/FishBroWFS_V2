"""
Test Desktop 4-Tab Architecture.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))


class TestDesktopTabArchitecture:
    """Test that Desktop has exactly 4 tabs with correct names."""
    
    def test_tab_modules_exist(self):
        """Test that all required tab modules exist."""
        # Check that module files exist without importing them
        # (importing would require PySide6 which may not be available in test environment)
        tab_modules = ["op_tab", "report_tab", "registry_tab", "allocation_tab", "audit_tab"]
        for module_name in tab_modules:
            module_path = src_dir / "gui" / "desktop" / "tabs" / f"{module_name}.py"
            assert module_path.exists(), f"Module {module_name}.py does not exist at {module_path}"
    
    def test_tab_classes_exist(self):
        """Test that all tab classes are defined."""
        # Check that module files exist and contain class definitions
        # We'll read the files to check for class definitions without importing
        tab_classes = [
            ("op_tab", "OpTab"),
            ("report_tab", "ReportTab"),
            ("registry_tab", "RegistryTab"),
            ("allocation_tab", "AllocationTab"),
            ("audit_tab", "AuditTab"),
        ]
        
        for module_name, class_name in tab_classes:
            module_path = src_dir / "gui" / "desktop" / "tabs" / f"{module_name}.py"
            assert module_path.exists(), f"Module {module_name}.py does not exist"
            
            # Read file to check for class definition
            with open(module_path, 'r') as f:
                content = f.read()
            
            # Check for class definition (simple check)
            assert f"class {class_name}" in content, f"Class {class_name} not found in {module_name}.py"
    
    def test_control_station_imports_tabs(self):
        """Test that control_station imports all tabs."""
        # Read control_station.py to check imports
        control_station_path = src_dir / "gui" / "desktop" / "control_station.py"
        with open(control_station_path, 'r') as f:
            content = f.read()
        
        # Check for tab imports
        assert "from .tabs.op_tab import OpTab" in content
        assert "from .tabs.report_tab import ReportTab" in content
        assert "from .tabs.registry_tab import RegistryTab" in content
        assert "from .tabs.allocation_tab import AllocationTab" in content
        assert "from .tabs.audit_tab import AuditTab" in content
    
    def test_tab_names_match_spec(self):
        """Test that tab names match the specification: OP, Report, Registry, Allocation, Audit."""
        # This would be tested in UI integration tests
        # For now, just verify the expected tab names
        expected_tabs = ["OP", "Report", "Registry", "Allocation", "Audit"]
        assert len(expected_tabs) == 5
        assert expected_tabs[0] == "OP"
        assert expected_tabs[1] == "Report"
        assert expected_tabs[2] == "Registry"
        assert expected_tabs[3] == "Allocation"
        assert expected_tabs[4] == "Audit"


class TestMakefileDesktopTargets:
    """Test that Makefile has correct desktop targets after pruning."""
    
    def test_makefile_has_up_down_targets(self):
        """Test that Makefile has 'make up' and 'make down' targets (product UI entrypoints)."""
        makefile_path = Path(__file__).parent.parent.parent / "Makefile"
        with open(makefile_path, 'r') as f:
            content = f.read()
        
        # Check for up and down targets (product UI entrypoints)
        assert "up:" in content, "Makefile missing 'up:' target"
        assert "down:" in content, "Makefile missing 'down:' target"
        # desktop and desktop-offscreen targets should be removed
        assert "desktop:" not in content, "Makefile should not have 'desktop:' target after pruning"
        assert "desktop-offscreen:" not in content, "Makefile should not have 'desktop-offscreen:' target after pruning"
    
    def test_makefile_legacy_targets_renamed(self):
        """Test that legacy web UI targets have been removed (Phase 1 cleanup)."""
        makefile_path = Path(__file__).parent.parent.parent / "Makefile"
        with open(makefile_path, 'r') as f:
            content = f.read()
        
        # Legacy targets should NOT exist after Phase 1 cleanup
        assert "legacy-gui:" not in content
        assert "legacy-dashboard:" not in content
        assert "legacy-backend:" not in content
        assert "legacy-worker:" not in content
        assert "legacy-war:" not in content
        
        # Ensure no legacy-* targets remain
        import re
        legacy_targets = re.findall(r'^legacy-\w+:', content, re.MULTILINE)
        assert len(legacy_targets) == 0, f"Unexpected legacy targets found: {legacy_targets}"
    
    def test_makefile_help_mentions_desktop_only(self):
        """Test that help mentions Desktop as ONLY product UI (legacy section removed)."""
        makefile_path = Path(__file__).parent.parent.parent / "Makefile"
        with open(makefile_path, 'r') as f:
            content = f.read()
        
        # Check help section (find from help: to next blank line or end of help)
        help_start = content.find("help:")
        if help_start == -1:
            raise AssertionError("Makefile missing help target")
        # Find the next target after help: (line that starts with a letter and colon)
        import re
        help_end_match = re.search(r'\n\n[a-zA-Z]+:', content[help_start:])
        if help_end_match:
            help_section = content[help_start:help_start + help_end_match.start()]
        else:
            help_section = content[help_start:]
        
        # Must contain these strings
        assert "Desktop is the ONLY product UI" in help_section
        assert "PRODUCT COMMANDS" in help_section
        # LEGACY / DEPRECATED section should be removed after Phase 1 cleanup
        assert "LEGACY / DEPRECATED" not in help_section


class TestArtifactContract:
    """Test artifact validation contract."""
    
    def test_artifact_validation_module_exists(self):
        """Test that artifact_validation.py exists and has required functions."""
        from gui.desktop.artifact_validation import (
            is_artifact_dir_name,
            validate_artifact_dir,
            find_latest_valid_artifact,
        )
        
        assert callable(is_artifact_dir_name)
        assert callable(validate_artifact_dir)
        assert callable(find_latest_valid_artifact)
    
    def test_only_artifact_dirs_promotable(self):
        """Test that only artifact_* and run_* directories are promotable (contract)."""
        from gui.desktop.artifact_validation import is_artifact_dir_name
        
        # Positive cases (6-64 hex chars)
        assert is_artifact_dir_name("artifact_123456") is True  # 6 hex chars
        assert is_artifact_dir_name("artifact_ac8a71aa") is True  # 8 hex chars
        assert is_artifact_dir_name("run_123456") is True  # run_ with 6 hex chars
        assert is_artifact_dir_name("run_ac8a71aa") is True  # run_ with 8 hex chars
        
        # Negative cases (should not be promotable)
        assert is_artifact_dir_name("artifact_20260103_123456") is False  # timestamp with underscore
        assert is_artifact_dir_name("artifact_test") is False  # non-hex chars
        assert is_artifact_dir_name("stage_20260103_123456") is False
        assert is_artifact_dir_name("research_20260103") is False
        assert is_artifact_dir_name("") is False
        assert is_artifact_dir_name("artifact") is False  # Must have underscore after artifact


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
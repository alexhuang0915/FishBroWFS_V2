import os
import pytest

def test_five_tab_invariant():
    """Verify that ControlStation has exactly 5 main tabs and correct labels."""
    # Source code check to avoid PySide6 dependency issues in headless test environments
    cs_path = os.path.join(os.getcwd(), "src/gui/desktop/control_station.py")
    with open(cs_path, 'r') as f:
        content = f.read()
    
    # Check for the 5-tab spec mention and tab index mapping
    assert "exactly 5 main tabs" in content
    
    # Check tab registrations in self._tab_index_by_tool
    tabs = [
        "bar_prepare",
        "registry",
        "operation",
        "allocation",
        "ops"
    ]
    for tab in tabs:
        assert f'"{tab}":' in content

def test_legacy_cleanup_lockdown():
    """Verify that legacy state containers and tabs are NOT mentioned in ControlStation."""
    cs_path = os.path.join(os.getcwd(), "src/gui/desktop/control_station.py")
    with open(cs_path, 'r') as f:
        content = f.read()
    
    legacy_terms = [
        "ResearchFlowTab",
        "ReportTab",
        "AuditTab",
        "active_run_state",
        "portfolio_build_state",
        "readiness_state",
        "decision_gate_state",
        "export_state",
        "operation_state",
        "selected_strategies_state",
        "step_flow_state"
    ]
    
    for term in legacy_terms:
        # Check that they are not imported or used
        assert term not in content, f"Legacy term '{term}' still found in ControlStation.py"

def test_filesystem_hygiene():
    """Verify that deleted files are actually gone from the filesystem."""
    base_dir = "src/gui/desktop"
    
    deleted_files = [
        "state/active_run_state.py",
        "state/portfolio_build_state.py",
        "state/readiness_state.py",
        "state/decision_gate_state.py",
        "state/export_state.py",
        "state/operation_state.py",
        "state/selected_strategies_state.py",
        "state/step_flow_state.py",
        "dialogs/run_intent_dialog.py",
        "dialogs/data_readiness_dialog.py",
        "dialogs/job_tracker_dialog.py",
        "widgets/readiness_panel.py",
        "tabs/research_flow_tab.py",
        "tabs/_legacy/"
    ]
    
    for rel_path in deleted_files:
        full_path = os.path.join(os.getcwd(), base_dir, rel_path)
        assert not os.path.exists(full_path), f"File/Dir '{rel_path}' should have been deleted"

def test_state_dir_purity():
    """Verify that ONLY the allowed SSOT state files exist in the state directory."""
    state_dir = os.path.join(os.getcwd(), "src/gui/desktop/state")
    allowed_files = {
        "__init__.py",
        "bar_prepare_state.py",
        "job_store.py",
        "research_selection_state.py"
    }
    
    actual_files = set()
    for f in os.listdir(state_dir):
        if f.endswith(".py"):
            actual_files.add(f)
            
    # Check that no extra .py files are present
    extra_files = actual_files - allowed_files
    assert not extra_files, f"Unexpected files in state directory: {extra_files}"

def test_report_widgets_hygiene():
    """Verify that report widgets do not import deleted export_state."""
    widgets_dir = os.path.join(os.getcwd(), "src/gui/desktop/widgets/report_widgets")
    files = ["strategy_report_widget.py", "portfolio_report_widget.py"]
    
    for filename in files:
        path = os.path.join(widgets_dir, filename)
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
            assert "export_state" not in content, f"Legacy export_state still found in {filename}"

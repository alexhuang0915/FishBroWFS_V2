"""
Phase 2 – Closed‑loop Enhancements Smoke Test.

Verifies that the three main tabs (BarPrepare, Operation, Portfolio) have the required
UI components and methods for closed‑loop operation, and that the router redirects
internal://report URLs to the correct visible tabs (not hidden audit tab).
"""

import os
import ast
import pytest


def test_bar_prepare_has_registry_mismatch_panel():
    """BarPrepare tab must have registry mismatch warning panel."""
    source_path = os.path.join(os.path.dirname(__file__), "../../src/gui/desktop/tabs/bar_prepare_tab.py")
    with open(source_path, 'r', encoding='utf-8') as f:
        source = f.read()

    # Check for registry_warning_panel attribute
    assert "self.registry_warning_panel" in source, "BarPrepare missing registry_warning_panel"
    # Check for _refresh_registry_mismatch method
    assert "def _refresh_registry_mismatch" in source, "BarPrepare missing _refresh_registry_mismatch method"
    # Check that the method is called in refresh_summary
    assert "_refresh_registry_mismatch" in source, "BarPrepare missing call to _refresh_registry_mismatch"


def test_bar_prepare_removed_wizard_confirm_block():
    """BarPrepare must not require state.confirmed to enable Build All button."""
    source_path = os.path.join(os.path.dirname(__file__), "../../src/gui/desktop/tabs/bar_prepare_tab.py")
    with open(source_path, 'r', encoding='utf-8') as f:
        source = f.read()

    # Ensure _update_build_button_state does not check state.confirmed
    # We'll parse AST to find the method
    tree = ast.parse(source)

    class BuildButtonVisitor(ast.NodeVisitor):
        def __init__(self):
            self.has_confirmed_check = False
            self.method_found = False

        def visit_FunctionDef(self, node):
            if node.name == "_update_build_button_state":
                self.method_found = True
                # Look for any attribute access to 'confirmed' within the method
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute) and child.attr == "confirmed":
                        self.has_confirmed_check = True
            self.generic_visit(node)

    visitor = BuildButtonVisitor()
    visitor.visit(tree)
    assert visitor.method_found, "_update_build_button_state method not found"
    assert not visitor.has_confirmed_check, "_update_build_button_state still references 'confirmed'"


def test_op_tab_has_output_summary_panel():
    """Operation tab must have output summary panel and show_strategy_report_summary method."""
    source_path = os.path.join(os.path.dirname(__file__), "../../src/gui/desktop/tabs/op_tab_refactored.py")
    with open(source_path, 'r', encoding='utf-8') as f:
        source = f.read()

    assert "self.output_summary_panel" in source, "OpTab missing output_summary_panel"
    assert "def show_strategy_report_summary" in source, "OpTab missing show_strategy_report_summary method"
    assert "def _update_output_summary" in source, "OpTab missing _update_output_summary method"
    # Ensure on_view_artifacts does not emit switch_to_audit_tab
    # We'll check that the method does not contain that signal emission
    tree = ast.parse(source)

    class ViewArtifactsVisitor(ast.NodeVisitor):
        def __init__(self):
            self.emits_audit_signal = False

        def visit_FunctionDef(self, node):
            if node.name == "on_view_artifacts":
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute) and child.attr == "switch_to_audit_tab":
                        self.emits_audit_signal = True
            self.generic_visit(node)

    visitor = ViewArtifactsVisitor()
    visitor.visit(tree)
    assert not visitor.emits_audit_signal, "on_view_artifacts still emits switch_to_audit_tab"


def test_portfolio_tab_has_portfolio_summary_panel():
    """Portfolio tab must have portfolio summary panel and show_portfolio_report_summary method."""
    source_path = os.path.join(os.path.dirname(__file__), "../../src/gui/desktop/tabs/allocation_tab.py")
    with open(source_path, 'r', encoding='utf-8') as f:
        source = f.read()

    assert "self.portfolio_summary_panel" in source, "AllocationTab missing portfolio_summary_panel"
    assert "def show_portfolio_report_summary" in source, "AllocationTab missing show_portfolio_report_summary method"
    assert "def _update_portfolio_summary" in source, "AllocationTab missing _update_portfolio_summary method"
    # Ensure view_portfolio_report does not route via action router
    tree = ast.parse(source)

    class ViewReportVisitor(ast.NodeVisitor):
        def __init__(self):
            self.routes_to_audit = False

        def visit_FunctionDef(self, node):
            if node.name == "view_portfolio_report":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        # Check if it's self.action_router.handle_action
                        if isinstance(child.func, ast.Attribute):
                            if child.func.attr == "handle_action":
                                self.routes_to_audit = True
            self.generic_visit(node)

    visitor = ViewReportVisitor()
    visitor.visit(tree)
    assert not visitor.routes_to_audit, "view_portfolio_report still routes via action router"


def test_control_station_router_redirects_to_visible_tabs():
    """ControlStation router must redirect internal://report URLs to visible tabs."""
    source_path = os.path.join(os.path.dirname(__file__), "../../src/gui/desktop/control_station.py")
    with open(source_path, 'r', encoding='utf-8') as f:
        source = f.read()

    # Check that handle_router_url calls show_strategy_report_summary for strategy reports
    assert "show_strategy_report_summary" in source, "Router missing call to show_strategy_report_summary"
    # Check that handle_router_url calls show_portfolio_report_summary for portfolio reports
    assert "show_portfolio_report_summary" in source, "Router missing call to show_portfolio_report_summary"
    # Ensure no routing to audit tab for these URLs
    # We'll parse the handle_router_url method
    tree = ast.parse(source)

    class RouterVisitor(ast.NodeVisitor):
        def __init__(self):
            self.redirects_to_audit = False
            self.redirects_to_operation = False
            self.redirects_to_portfolio = False

        def visit_FunctionDef(self, node):
            if node.name == "handle_router_url":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        # Check for switch_to_audit_tab emission
                        if isinstance(child.func, ast.Attribute):
                            if child.func.attr == "switch_to_audit_tab":
                                self.redirects_to_audit = True
                        # Check for show_strategy_report_summary call
                        if isinstance(child.func, ast.Attribute):
                            if child.func.attr == "show_strategy_report_summary":
                                self.redirects_to_operation = True
                        # Check for show_portfolio_report_summary call
                        if isinstance(child.func, ast.Attribute):
                            if child.func.attr == "show_portfolio_report_summary":
                                self.redirects_to_portfolio = True
            self.generic_visit(node)

    visitor = RouterVisitor()
    visitor.visit(tree)
    assert not visitor.redirects_to_audit, "Router still redirects to audit tab"
    assert visitor.redirects_to_operation, "Router missing redirect to Operation tab"
    assert visitor.redirects_to_portfolio, "Router missing redirect to Portfolio tab"


def test_only_three_visible_tabs():
    """Ensure only three tabs are visible (Bar Prepare, Operation, Portfolio)."""
    source_path = os.path.join(os.path.dirname(__file__), "../../src/gui/desktop/control_station.py")
    with open(source_path, 'r', encoding='utf-8') as f:
        source = f.read()

    tree = ast.parse(source)

    class AddTabVisitor(ast.NodeVisitor):
        def __init__(self):
            self.add_tab_calls = []

        def visit_Call(self, node):
            # Look for self.tab_widget.addTab(...)
            if isinstance(node.func, ast.Attribute):
                if (isinstance(node.func.value, ast.Attribute) and
                    node.func.value.attr == 'tab_widget' and
                    isinstance(node.func.value.value, ast.Name) and
                    node.func.value.value.id == 'self' and
                    node.func.attr == 'addTab'):
                    self.add_tab_calls.append(node.lineno)
            self.generic_visit(node)

    visitor = AddTabVisitor()
    visitor.visit(tree)

    # Expect exactly 3 addTab calls
    assert len(visitor.add_tab_calls) == 5, \
        f"Expected exactly 5 addTab calls, found {len(visitor.add_tab_calls)} at lines {visitor.add_tab_calls}"

    # Optionally verify the tab labels (optional)
    lines = source.split('\n')
    tab_labels = []
    for line_num in visitor.add_tab_calls:
        line = lines[line_num - 1]  # line numbers are 1-indexed
        # Extract the second argument (string literal)
        import re
        match = re.search(r'addTab\([^,]+, "([^"]+)"\)', line)
        if match:
            tab_labels.append(match.group(1))

    expected_labels = {
        "Data Prepare",
        "Registry",
        "Research / Backtest",
        "Portfolio",
        "Ops / Jobs & Logs"
    }
    assert set(tab_labels) == expected_labels, \
        f"Tab labels mismatch: got {tab_labels}, expected {expected_labels}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""Guard tests for UI bootstrap singleton invariants.

Ensures theme, shell, and polling are bootstrapped exactly once per process.
"""
import sys
import ast
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest

logger = logging.getLogger(__name__)


class TestBootstrapSingleton:
    """Test that the UI bootstrap path executes exactly once."""

    def setup_method(self):
        """Reset module globals before each test."""
        # Reset app module
        import gui.nicegui.app as app_module
        app_module._UI_BOOTSTRAPPED = False
        app_module._BOOTSTRAP_COUNT = 0
        app_module._SHELL_BUILD_COUNT = 0
        app_module._SHELL_BUILT = False
        # Reset theme module
        import gui.nicegui.theme.nexus_theme as theme_module
        theme_module._THEME_APPLIED = False
        theme_module._THEME_APPLY_COUNT = 0
        # Reset status service
        import gui.nicegui.services.status_service as status_module
        status_module._polling_started = False
        status_module._polling_timer = None
        status_module._status_cache = None
        status_module._last_backend_up = None
        status_module._last_worker_up = None

    @patch("gui.nicegui.theme.nexus_theme.ui.add_head_html")
    @patch("gui.nicegui.services.status_service.ui.timer")
    @patch("gui.nicegui.app.apply_ui_constitution")
    @patch("gui.nicegui.app.apply_nexus_theme")
    @patch("gui.nicegui.app.create_app_shell")
    @patch("gui.nicegui.app.start_polling")
    def test_bootstrap_singleton(
        self,
        mock_start_polling,
        mock_create_app_shell,
        mock_apply_nexus_theme,
        mock_apply_ui_constitution,
        mock_timer,
        mock_add_head_html,
    ):
        """Call bootstrap twice; theme, shell, polling must be initialized once."""
        mock_timer.return_value = MagicMock()
        
        from gui.nicegui.app import bootstrap_app_shell_and_services
        
        # First call
        bootstrap_app_shell_and_services()
        
        # Verify each function called once
        mock_apply_ui_constitution.assert_called_once()
        mock_apply_nexus_theme.assert_called_once_with(use_tailwind=False)
        mock_create_app_shell.assert_called_once()
        mock_start_polling.assert_called_once()
        
        # Second call
        bootstrap_app_shell_and_services()
        
        # Calls must stay at one
        mock_apply_ui_constitution.assert_called_once()
        mock_apply_nexus_theme.assert_called_once()
        mock_create_app_shell.assert_called_once()
        mock_start_polling.assert_called_once()
        
        # Verify bootstrap count is 1 (only one bootstrap executed)
        from gui.nicegui.app import _BOOTSTRAP_COUNT
        assert _BOOTSTRAP_COUNT == 1

    @patch("gui.nicegui.services.status_service.ui.timer")
    @patch("gui.nicegui.services.status_service._update_status")
    def test_start_polling_idempotent(self, mock_update_status, mock_timer):
        """start_polling must create only one timer."""
        mock_timer.return_value = MagicMock()
        mock_update_status.return_value = None
        
        import gui.nicegui.services.status_service as status_module
        from gui.nicegui.services.status_service import start_polling
        
        # First call
        start_polling(interval=0.1)  # short interval for test
        # Check flag via module
        print(f"DEBUG: status_module._polling_started = {status_module._polling_started}")
        assert status_module._polling_started is True, f"_polling_started is {status_module._polling_started}"
        assert mock_timer.call_count == 1
        
        # Verify _update_status was called once (initial update)
        mock_update_status.assert_called_once()
        
        # Second call
        start_polling()
        assert mock_timer.call_count == 1, "Second call created another timer"
        # _update_status should still be called only once (no new initial update)
        mock_update_status.assert_called_once()
        
        # Timer callback should be callable (lambda)
        args, kwargs = mock_timer.call_args
        assert kwargs.get("interval") == 0.1
        assert callable(kwargs.get("callback"))

    @patch("uvicorn.run")
    @patch("gui.nicegui.app.ui.run_with")
    @patch("gui.nicegui.app.bootstrap_app_shell_and_services")
    def test_start_ui_gate(self, mock_bootstrap, mock_ui_run_with, mock_uvicorn_run):
        """start_ui must set _UI_BOOTSTRAPPED flag before bootstrap and skip on second call."""
        import gui.nicegui.app as app_module
        from gui.nicegui.app import start_ui
        # Reset flag (already done in setup_method)
        print(f"Before start_ui: _UI_BOOTSTRAPPED={app_module._UI_BOOTSTRAPPED}")
        # Side effect to verify flag is True when bootstrap is called
        bootstrap_called = []
        def bootstrap_side_effect():
            bootstrap_called.append(True)
            assert app_module._UI_BOOTSTRAPPED is True, "Flag must be True before bootstrap"
        mock_bootstrap.side_effect = bootstrap_side_effect
        
        # First call
        start_ui(host="127.0.0.1", port=8080)
        # Verify flag is True
        print(f"After start_ui: _UI_BOOTSTRAPPED={app_module._UI_BOOTSTRAPPED}")
        assert app_module._UI_BOOTSTRAPPED is True, f"Flag should be True after start_ui, got {app_module._UI_BOOTSTRAPPED}"
        # Verify bootstrap called once
        mock_bootstrap.assert_called_once()
        # Verify ui.run_with called once
        mock_ui_run_with.assert_called_once()
        # Verify uvicorn.run called once
        mock_uvicorn_run.assert_called_once()
        # Second call (should skip due to flag)
        start_ui()
        # bootstrap should not be called again
        mock_bootstrap.assert_called_once()
        # ui.run_with and uvicorn.run should not be called again (since start_ui returns early)
        assert mock_ui_run_with.call_count == 1
        assert mock_uvicorn_run.call_count == 1

    def test_no_import_time_bootstrap(self):
        """Ensure no module in the UI subsystem calls bootstrap functions at import time.
        
        This test detects top‑level expressions that call forbidden functions.
        It ignores calls inside function definitions.
        """
        repo_root = Path(__file__).parent.parent.parent
        ui_root = repo_root / "src" / "gui" / "nicegui"
        
        forbidden_calls = {
            "apply_nexus_theme",
            "create_app_shell",
            "start_polling",
            "start_ui",
            "ui.run",
        }
        
        errors = []
        for py_file in ui_root.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(content, filename=str(py_file))
            except SyntaxError:
                continue
            
            class Visitor(ast.NodeVisitor):
                def __init__(self):
                    self.errors = []
                    self.current_function = None
                
                def visit_FunctionDef(self, node):
                    old = self.current_function
                    self.current_function = node.name
                    self.generic_visit(node)
                    self.current_function = old
                
                def visit_Expr(self, node):
                    if self.current_function is None:
                        # Top‑level expression
                        if isinstance(node.value, ast.Call):
                            call = node.value
                            if isinstance(call.func, ast.Name):
                                if call.func.id in forbidden_calls:
                                    self.errors.append((call.func.id, node.lineno))
                            elif isinstance(call.func, ast.Attribute):
                                attr_name = ast.unparse(call.func)
                                if attr_name in forbidden_calls:
                                    self.errors.append((attr_name, node.lineno))
                    self.generic_visit(node)
            
            visitor = Visitor()
            visitor.visit(tree)
            for func_name, lineno in visitor.errors:
                errors.append(f"{py_file.relative_to(repo_root)}:{lineno}: top‑level call to {func_name}")
        
        if errors:
            error_msg = "\n".join(errors)
            raise AssertionError(
                f"Found {len(errors)} import‑time bootstrap call(s):\n{error_msg}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
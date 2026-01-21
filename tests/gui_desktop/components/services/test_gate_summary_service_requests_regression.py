"""
Regression test for gate summary service to ensure 'requests' never triggers UnboundLocalError.

This test verifies that the service can handle missing or broken requests module
without raising UnboundLocalError, and that it returns a safe fallback summary.
"""

import pytest
from unittest.mock import Mock, patch
import sys

# Import the real module (not patched) to test the actual import behavior
import gui.services.gate_summary_service as module


class TestGateSummaryServiceRequestsRegression:
    """Regression tests for requests UnboundLocalError."""

    def test_fetch_never_unboundlocal(self, monkeypatch):
        """
        Ensure fetch() does not raise UnboundLocalError when requests is missing.

        This test patches the module-level 'requests' to simulate a missing module
        (by raising ImportError) and verifies that fetch() still returns a
        consumable GateSummary (fallback) rather than crashing.
        """
        # Create a mock client to avoid real network calls
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = []
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        # Instantiate service with mocked client
        service = module.GateSummaryService(client=mock_client)

        # Patch the module-level 'requests' to raise ImportError when accessed
        # This simulates the scenario where import requests fails at runtime
        original_requests = module.requests
        try:
            # Temporarily delete the module attribute to cause AttributeError
            # but we'll patch the import side effect.
            # Instead, we'll patch the requests.get used inside the functions.
            # Since we already have a mocked session, the requests module is not used.
            # However we need to ensure that if requests is missing, the exception
            # handling does not cause UnboundLocalError.
            # Let's simulate a missing attribute by monkeypatching requests to None.
            monkeypatch.setattr(module, 'requests', None)
        except AttributeError:
            pass

        # The fetch should still work because the internal functions use self.client.session
        # which we have mocked. However the exception handling in _fetch_api_readiness
        # and _fetch_registry_surface references requests.exceptions.
        # If requests is None, accessing requests.exceptions will raise AttributeError.
        # That's okay; the except block will catch Exception and return a FAIL gate.
        # So fetch should still return a summary.
        summary = service.fetch()
        assert summary is not None
        assert isinstance(summary, module.GateSummary)
        # At least one gate should be present
        assert len(summary.gates) > 0
        # Ensure no UnboundLocalError was raised (implicitly by the test not crashing)

    def test_fetch_with_mocked_requests_get(self):
        """
        Ensure fetch works when requests.get is patched with a fake response.

        This test patches the lowest IO primitive (requests.get) to verify that
        the service does not rely on any uninitialized local variable.
        """
        # Create a fake response that mimics a successful readiness/registry call
        fake_response = Mock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"status": "ok"}
        fake_response.raise_for_status.return_value = None

        with patch.object(module.requests, 'get', return_value=fake_response):
            # We also need to mock the client's session.get because the service uses
            # self.client.session.get, not requests.get directly.
            # Actually the service uses self.client.session.get, not requests.get.
            # So patching requests.get may not be needed. However we still patch
            # to ensure no UnboundLocalError.
            mock_client = Mock()
            mock_client.health.return_value = {"status": "ok"}
            mock_client.get_jobs.return_value = []
            mock_session = Mock()
            mock_session.get.return_value = fake_response
            mock_client.session = mock_session
            mock_client.base_url = "http://testserver"

            service = module.GateSummaryService(client=mock_client)
            summary = service.fetch()
            assert summary is not None
            assert summary.overall_status in (module.GateStatus.PASS,
                                              module.GateStatus.WARN,
                                              module.GateStatus.FAIL)

    def test_fallback_on_catastrophic_exception(self):
        """
        Ensure fetch returns a safe fallback summary when an unexpected exception occurs.

        This test simulates a catastrophic failure (e.g., AttributeError) inside
        the fetch method and verifies that the outer try‑except catches it and
        returns a fallback GateSummary.
        """
        mock_client = Mock()
        # Make health raise an unexpected exception (not SupervisorClientError)
        mock_client.health.side_effect = AttributeError("Something went wrong")
        mock_client.get_jobs.return_value = []
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = module.GateSummaryService(client=mock_client)
        summary = service.fetch()
        # Should still return a GateSummary (fallback)
        assert summary is not None
        assert isinstance(summary, module.GateSummary)
        # The fallback summary should have overall_status FAIL
        assert summary.overall_status == module.GateStatus.FAIL
        # There should be at least one gate
        assert len(summary.gates) >= 1
        # The gate should be the catastrophic_failure gate
        catastrophic_gates = [g for g in summary.gates if g.gate_id == "catastrophic_failure"]
        assert len(catastrophic_gates) == 1
        assert catastrophic_gates[0].status == module.GateStatus.FAIL

    def test_requests_module_level_import(self):
        """
        Verify that requests is imported at module level (not inside functions).

        This is a static check: ensure there is no 'import requests' inside
        any function in the module.
        """
        import ast
        import os

        # Use the module's own file path
        file_path = module.__file__
        if file_path.endswith('.pyc'):
            file_path = file_path[:-1]
        with open(file_path, 'r') as f:
            source = f.read()
        tree = ast.parse(source)

        # Collect all import statements inside function definitions
        function_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Import):
                        for alias in subnode.names:
                            if alias.name == 'requests':
                                function_imports.append(node.name)
                    elif isinstance(subnode, ast.ImportFrom):
                        if subnode.module == 'requests':
                            function_imports.append(node.name)

        # Assert no function contains import requests
        assert not function_imports, (
            f"Found 'import requests' inside functions: {function_imports}. "
            "Requests must be imported at module level to avoid UnboundLocalError."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
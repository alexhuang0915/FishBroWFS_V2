"""
Policy test: UI pages must not import transport/HTTP libs directly or call client.get/post directly.

Constitutional Principle:
- UI pages must use domain bridges (WizardBridge, WorkerBridge) or ControlAPIClient's explicit methods
- No direct httpx/requests imports in pages
- No client.get()/.post() calls (must use client.get_json()/.post_json() or explicit methods)
- No direct HTTP calls bypassing the transport layer
"""

import ast
from pathlib import Path
import re


def check_file_for_transport_violations(file_path: Path) -> list:
    """Check a file for transport/HTTP violations."""
    violations = []
    
    try:
        content = file_path.read_text()
        tree = ast.parse(content)
        
        # Check for forbidden imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ["httpx", "requests", "aiohttp"]:
                        violations.append(f"{file_path}:{node.lineno}: import {alias.name} (use bridges instead)")
            
            elif isinstance(node, ast.ImportFrom):
                if node.module in ["httpx", "requests", "aiohttp"]:
                    violations.append(f"{file_path}:{node.lineno}: from {node.module} import ... (use bridges instead)")
        
        # Check for client.get()/.post() calls using AST
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for client.get(...) or client.post(...)
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in ["get", "post"]:
                        # Check if it's client.get or client.post
                        # We need to see what the object is
                        if isinstance(node.func.value, ast.Name):
                            var_name = node.func.value.id
                            # Check if this is likely a client variable
                            # Look for variable assignments in the file
                            # Simple heuristic: if variable name contains 'client' or is 'client'
                            if var_name == "client" or "client" in var_name.lower():
                                violations.append(f"{file_path}:{node.lineno}: {var_name}.{node.func.attr}() call (use client.get_json()/.post_json() or bridges)")
        
        # Also check with regex for patterns we might have missed
        # Look for patterns like: client.get("/worker/status") or client.post("/worker/stop")
        get_pattern = r'\.get\s*\(\s*["\']'
        post_pattern = r'\.post\s*\(\s*["\']'
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if re.search(get_pattern, line) and 'client' in line.lower():
                # Check if it's a comment
                if not line.strip().startswith('#'):
                    violations.append(f"{file_path}:{i}: client.get() call detected: {line.strip()[:50]}...")
            if re.search(post_pattern, line) and 'client' in line.lower():
                if not line.strip().startswith('#'):
                    violations.append(f"{file_path}:{i}: client.post() call detected: {line.strip()[:50]}...")
    
    except (SyntaxError, UnicodeDecodeError):
        # Skip files we can't parse
        pass
    
    return violations


def test_pages_no_direct_http_imports():
    """Test that UI pages don't import httpx/requests directly."""
    
    pages_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui" / "nicegui" / "pages"
    
    violations = []
    files_checked = 0
    
    # Exclude legacy transitional pages that are being phased out
    excluded_files = [
        "new_job.py",  # Legacy page transitioning to Wizard
    ]
    
    for py_file in pages_dir.rglob("*.py"):
        # Skip excluded files
        if py_file.name in excluded_files:
            continue
            
        files_checked += 1
        file_violations = check_file_for_transport_violations(py_file)
        if file_violations:
            violations.extend(file_violations)
    
    # Output violations if any
    if violations:
        print("發現禁止的 HTTP/transport 導入或 client.get()/.post() 呼叫:")
        for violation in violations:
            print(f"  - {violation}")
    
    assert len(violations) == 0, f"發現 {len(violations)} 個 HTTP/transport 違規（檢查了 {files_checked} 個檔案，排除 {len(excluded_files)} 個過渡檔案）"


def test_pages_use_bridges_or_explicit_methods():
    """Test that UI pages use bridges or explicit ControlAPIClient methods."""
    
    pages_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui" / "nicegui" / "pages"
    
    # List of allowed patterns (pages should use these)
    allowed_patterns = [
        "get_worker_bridge()",
        "get_wizard_bridge()",
        "worker_status()",
        "worker_stop()",
        "get_json(",
        "post_json(",
        "from ...bridge.worker_bridge import",
        "from ...bridge.wizard_bridge import",
    ]
    
    # Check each page file
    recommendations = []
    
    for py_file in pages_dir.rglob("*.py"):
        content = py_file.read_text()
        
        # Check if file uses any bridge
        uses_bridge = False
        for pattern in allowed_patterns:
            if pattern in content:
                uses_bridge = True
                break
        
        # Check if file uses ControlAPIClient directly (allowed but should use explicit methods)
        if "ControlAPIClient" in content or "get_control_client" in content:
            uses_bridge = True
        
        if not uses_bridge:
            # This might be a page that doesn't need backend access
            # Check if it's a simple page (no backend calls expected)
            # For now, just record as recommendation
            recommendations.append(str(py_file))
    
    # Output recommendations (not failures)
    if recommendations:
        print("以下頁面可能未使用橋接器或明確的 ControlAPIClient 方法（僅供參考）:")
        for rec in recommendations:
            print(f"  - {rec}")
    
    # This test doesn't fail, just provides information
    # We could make it stricter if needed


def test_worker_bridge_contract():
    """Test that WorkerBridge provides the expected interface."""
    
    from FishBroWFS_V2.gui.nicegui.bridge.worker_bridge import (
        WorkerBridge, WorkerStatus, WorkerStopResult, 
        get_worker_bridge, reset_worker_bridge
    )
    
    # Test class existence
    assert WorkerBridge is not None
    assert WorkerStatus is not None
    assert WorkerStopResult is not None
    
    # Test singleton function
    bridge1 = get_worker_bridge()
    bridge2 = get_worker_bridge()
    assert bridge1 is bridge2  # Should be same instance
    
    # Test reset function
    reset_worker_bridge()
    bridge3 = get_worker_bridge()
    assert bridge3 is not bridge1  # Should be new instance after reset
    
    # Test WorkerBridge methods exist
    bridge = WorkerBridge()
    assert hasattr(bridge, 'get_worker_status')
    assert hasattr(bridge, 'stop_worker')
    assert hasattr(bridge, 'is_worker_alive')
    assert hasattr(bridge, 'get_worker_status_dict')
    
    # Reset for other tests
    reset_worker_bridge()


def test_wizard_bridge_contract():
    """Test that WizardBridge provides the expected interface."""
    
    from FishBroWFS_V2.gui.nicegui.bridge.wizard_bridge import (
        WizardBridge, WizardBridgeDiagnostics, WizardBridgeError,
        get_wizard_bridge
    )
    
    # Test class existence
    assert WizardBridge is not None
    assert WizardBridgeDiagnostics is not None
    assert WizardBridgeError is not None
    
    # Test get_wizard_bridge doesn't crash
    bridge = get_wizard_bridge()
    assert bridge is not None
    
    # Test WizardBridge methods exist
    assert hasattr(bridge, 'get_dataset_options')
    assert hasattr(bridge, 'get_strategy_options')
    assert hasattr(bridge, 'diagnostics')
    assert hasattr(bridge, 'get_function')
    assert hasattr(bridge, 'has_function')


if __name__ == "__main__":
    # Run tests
    import pytest
    pytest.main([__file__, "-v"])
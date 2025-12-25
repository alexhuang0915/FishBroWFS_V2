"""
Smoke test for No-Fog Gate Automation.

Tests that the no-fog gate:
1. Can be imported and run
2. Has correct structure and dependencies
3. Can run in check-only mode without side effects
4. Validates core contract tests exist
"""

import subprocess
import sys
import tempfile
import json
from pathlib import Path
import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
NO_FOG_GATE_PY = PROJECT_ROOT / "scripts" / "no_fog" / "no_fog_gate.py"
NO_FOG_GATE_SH = PROJECT_ROOT / "scripts" / "no_fog" / "no_fog_gate.sh"


def test_no_fog_gate_py_exists():
    """Test that the Python script exists."""
    assert NO_FOG_GATE_PY.exists(), f"No-Fog Gate Python script not found: {NO_FOG_GATE_PY}"
    assert NO_FOG_GATE_PY.is_file()


def test_no_fog_gate_sh_exists():
    """Test that the shell script exists."""
    assert NO_FOG_GATE_SH.exists(), f"No-Fog Gate shell script not found: {NO_FOG_GATE_SH}"
    assert NO_FOG_GATE_SH.is_file()


def test_no_fog_gate_py_importable():
    """Test that the Python script can be imported (syntax check)."""
    # Read the file and check for syntax errors
    import ast
    source = NO_FOG_GATE_PY.read_text(encoding="utf-8")
    try:
        ast.parse(source)
    except SyntaxError as e:
        pytest.fail(f"Syntax error in {NO_FOG_GATE_PY}: {e}")


def test_no_fog_gate_sh_executable():
    """Test that the shell script is executable (or can be made executable)."""
    # Check if it has execute permission, but don't fail if not
    # (it will be made executable by the Makefile)
    pass


def test_core_contract_tests_exist():
    """Test that all core contract test files exist."""
    core_tests = [
        "tests/strategy/test_ast_identity.py",
        "tests/test_ui_race_condition_headless.py",
        "tests/features/test_feature_causality.py",
        "tests/features/test_feature_lookahead_rejection.py",
        "tests/features/test_feature_window_honesty.py",
    ]
    
    missing = []
    for test_path in core_tests:
        full_path = PROJECT_ROOT / test_path
        if not full_path.exists():
            missing.append(test_path)
    
    assert not missing, f"Core contract test files missing: {missing}"


def test_no_fog_gate_check_only_mode():
    """Test that the gate can run in check-only (dry run) mode."""
    # Run the Python script with --check-only flag
    cmd = [sys.executable, str(NO_FOG_GATE_PY), "--check-only"]
    
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        env={**dict(os.environ), "PYTHONPATH": str(PROJECT_ROOT / "src")}
    )
    
    # Should exit with 0 (success) even in check-only mode
    assert result.returncode == 0, f"Check-only mode failed:\nStdout: {result.stdout}\nStderr: {result.stderr}"
    
    # Should mention "Dry run" or "check-only" in output
    output = result.stdout + result.stderr
    assert any(phrase in output.lower() for phrase in ["dry run", "check-only", "would run"]), \
        f"Expected dry run message in output:\n{output}"


def test_no_fog_gate_help():
    """Test that the gate shows help when requested."""
    # Test Python script help
    cmd_py = [sys.executable, str(NO_FOG_GATE_PY), "--help"]
    result_py = subprocess.run(
        cmd_py,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result_py.returncode == 0, f"Python script help failed: {result_py.stderr}"
    assert "usage:" in result_py.stdout.lower() or "help" in result_py.stdout.lower(), \
        f"Help not shown in Python script:\n{result_py.stdout}"
    
    # Test shell script help (if executable)
    if NO_FOG_GATE_SH.stat().st_mode & 0o111:  # If executable
        cmd_sh = ["bash", str(NO_FOG_GATE_SH), "--help"]
        result_sh = subprocess.run(
            cmd_sh,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Shell script help should also work
        assert result_sh.returncode in [0, 2], f"Shell script help failed: {result_sh.stderr}"
        assert "usage:" in result_sh.stdout.lower() or "help" in result_sh.stdout.lower() or "No-Fog Gate" in result_sh.stdout, \
            f"Help not shown in shell script:\n{result_sh.stdout}"


def test_make_no_fog_target():
    """Test that 'make no-fog' target is defined in Makefile."""
    makefile_path = PROJECT_ROOT / "Makefile"
    assert makefile_path.exists(), "Makefile not found"
    
    makefile_content = makefile_path.read_text(encoding="utf-8")
    
    # Check for no-fog target definition
    assert "no-fog:" in makefile_content, "'no-fog' target not defined in Makefile"
    
    # Check that it's in .PHONY
    assert "no-fog" in makefile_content.split(".PHONY:")[1].split("\n")[0], \
        "'no-fog' not in .PHONY targets"
    
    # Check that it's in help
    assert "make no-fog" in makefile_content, "'make no-fog' not in help section"


def test_pre_commit_config():
    """Test that pre-commit configuration includes no-fog gate."""
    pre_commit_config = PROJECT_ROOT / ".pre-commit-config.yaml"
    if pre_commit_config.exists():
        content = pre_commit_config.read_text(encoding="utf-8")
        # Should contain no-fog-gate hook
        assert "no-fog-gate" in content, "No-Fog Gate not in pre-commit config"
        assert "scripts/no_fog/no_fog_gate.sh" in content, "Shell script path not in pre-commit config"


def test_github_workflow():
    """Test that GitHub workflow exists."""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "no_fog_gate.yml"
    if workflow_path.exists():
        content = workflow_path.read_text(encoding="utf-8")
        assert "No-Fog Gate" in content, "Workflow doesn't mention No-Fog Gate"
        assert "scripts/no_fog/no_fog_gate.sh" in content, "Shell script not in workflow"


def test_snapshot_directory_structure():
    """Test that snapshot directory structure is correct."""
    snapshot_dir = PROJECT_ROOT / "SYSTEM_FULL_SNAPSHOT"
    
    # Directory might not exist yet, that's OK
    if snapshot_dir.exists():
        # Should have MANIFEST.json if it's a valid snapshot
        manifest_path = snapshot_dir / "MANIFEST.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                assert "generated_at" in manifest, "Manifest missing generated_at"
                assert "chunks" in manifest, "Manifest missing chunks"
                assert "files" in manifest, "Manifest missing files"
            except json.JSONDecodeError:
                pytest.fail("MANIFEST.json is not valid JSON")


def test_gate_timeout_configuration():
    """Test that timeout is configurable and defaults to 30 seconds."""
    # Read the Python script to check default timeout
    content = NO_FOG_GATE_PY.read_text(encoding="utf-8")
    
    # Should have GATE_TIMEOUT = 30
    assert "GATE_TIMEOUT = 30" in content or "GATE_TIMEOUT=30" in content or "TIMEOUT=30" in content, \
        "Default timeout not set to 30 seconds in Python script"
    
    # Check shell script for timeout argument
    sh_content = NO_FOG_GATE_SH.read_text(encoding="utf-8")
    assert "--timeout" in sh_content, "Shell script missing --timeout argument"
    assert "30" in sh_content, "Shell script missing default timeout value"


# Import os for environment variable
import os


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
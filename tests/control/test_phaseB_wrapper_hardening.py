"""
Phase B Hardening Tests - Verify wrapper scripts are disabled by default.

These tests verify that legacy wrapper scripts exit with code 2 and print
appropriate guidance when FISHBRO_ALLOW_LEGACY_WRAPPERS is not set to "1".
"""

import os
import subprocess
import sys
from pathlib import Path
import tempfile


def run_wrapper_script(script_path: Path, args: list = None, env: dict = None) -> tuple[int, str, str]:
    """Run a wrapper script and return (exit_code, stdout, stderr)."""
    if args is None:
        args = []
    
    # Build environment
    script_env = os.environ.copy()
    if env:
        script_env.update(env)
    
    # Ensure PYTHONPATH includes src
    script_env["PYTHONPATH"] = "src"
    
    cmd = [sys.executable, str(script_path)] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=script_env,
            timeout=10,
            cwd=Path(__file__).parent.parent.parent  # Project root
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout expired"


def test_wrapper_disabled_by_default():
    """Test that wrapper scripts exit with code 2 when env var is not set."""
    scripts_dir = Path("scripts")
    
    # List of wrapper scripts to test
    wrapper_scripts = [
        "run_research_v3.py",
        "run_phase3a_plateau.py",
        "run_phase3b_freeze.py",
        "run_phase3c_compile.py",
        "build_portfolio_from_research.py",
    ]
    
    for script_name in wrapper_scripts:
        script_path = scripts_dir / script_name
        assert script_path.exists(), f"Wrapper script not found: {script_path}"
        
        # Run without env var (should be disabled)
        exit_code, stdout, stderr = run_wrapper_script(
            script_path,
            env={"FISHBRO_ALLOW_LEGACY_WRAPPERS": ""}  # Explicitly empty
        )
        
        # Should exit with code 2 (wrapper disabled)
        assert exit_code == 2, (
            f"{script_name}: Expected exit code 2 (wrapper disabled), got {exit_code}\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )
        
        # Should contain error message about being disabled
        combined_output = stdout + stderr
        assert "Legacy wrapper execution is DISABLED" in combined_output, (
            f"{script_name}: Missing 'DISABLED' message in output"
        )
        assert "FISHBRO_ALLOW_LEGACY_WRAPPERS=1" in combined_output, (
            f"{script_name}: Missing env var guidance in output"
        )
        assert "Qt Desktop UI" in combined_output or "Supervisor API" in combined_output, (
            f"{script_name}: Missing alternative guidance in output"
        )


def test_wrapper_enabled_with_env_var():
    """Test that wrapper scripts run (or at least don't exit with code 2) when env var is set."""
    scripts_dir = Path("scripts")
    
    # We'll test with a simple script that should at least start
    script_path = scripts_dir / "run_research_v3.py"
    assert script_path.exists()
    
    # Run with env var set to "1" (enabled)
    exit_code, stdout, stderr = run_wrapper_script(
        script_path,
        env={"FISHBRO_ALLOW_LEGACY_WRAPPERS": "1"}
    )
    
    # Should NOT exit with code 2 (wrapper enabled)
    # It might exit with other codes (e.g., 1 for missing Supervisor), but not 2
    assert exit_code != 2, (
        f"run_research_v3.py: Should not exit with code 2 when env var is set\n"
        f"stdout: {stdout}\nstderr: {stderr}"
    )
    
    # Should show deprecation warning but not disabled error
    combined_output = stdout + stderr
    assert "DEPRECATED" in combined_output, (
        f"run_research_v3.py: Should show deprecation warning when enabled"
    )
    assert "Legacy wrapper execution is DISABLED" not in combined_output, (
        f"run_research_v3.py: Should not show disabled error when env var is set"
    )


def test_makefile_targets_respect_env_var():
    """Test that Makefile targets check FISHBRO_ALLOW_LEGACY_WRAPPERS."""
    makefile_path = Path("Makefile")
    assert makefile_path.exists()
    
    content = makefile_path.read_text()
    
    # Check that each run-* target contains the env var check
    targets = ["run-research", "run-plateau", "run-freeze", "run-compile", "run-portfolio"]
    
    for target in targets:
        # Find the target definition and a reasonable amount of following lines
        # Look for the target line and capture enough context
        lines = content.split('\n')
        target_line_idx = None
        for i, line in enumerate(lines):
            if line.startswith(f"{target}:"):
                target_line_idx = i
                break
        
        assert target_line_idx is not None, f"Makefile target {target} not found"
        
        # Capture the target and next 15 lines
        target_section = '\n'.join(lines[target_line_idx:target_line_idx + 20])
        
        # Should contain FISHBRO_ALLOW_LEGACY_WRAPPERS check
        assert "FISHBRO_ALLOW_LEGACY_WRAPPERS" in target_section, (
            f"Makefile target {target} should check FISHBRO_ALLOW_LEGACY_WRAPPERS"
        )
        
        # Should contain exit 2 (might be on a different line)
        assert "exit 2" in target_section, (
            f"Makefile target {target} should exit with code 2 when env var not set"
        )
        
        # Should mention Phase B hardening or similar warning
        assert "PHASE B HARDENING" in target_section or "Phase B" in target_section or "root-cut" in target_section, (
            f"Makefile target {target} should mention Phase B hardening"
        )


def test_wrapper_scripts_have_phase_b_header():
    """Test that wrapper scripts have Phase B hardening documentation."""
    scripts_dir = Path("scripts")
    
    wrapper_scripts = [
        "run_research_v3.py",
        "run_phase3a_plateau.py",
        "run_phase3b_freeze.py",
        "run_phase3c_compile.py",
        "build_portfolio_from_research.py",
    ]
    
    for script_name in wrapper_scripts:
        script_path = scripts_dir / script_name
        content = script_path.read_text()
        
        # Should mention Phase B hardening
        assert "PHASE B HARDENING" in content or "Phase B" in content, (
            f"{script_name}: Missing Phase B hardening documentation"
        )
        
        # Should mention FISHBRO_ALLOW_LEGACY_WRAPPERS
        assert "FISHBRO_ALLOW_LEGACY_WRAPPERS" in content, (
            f"{script_name}: Missing FISHBRO_ALLOW_LEGACY_WRAPPERS documentation"
        )
        
        # Should have the env check at the top (check first 40 lines)
        lines = content.split('\n')
        early_content = '\n'.join(lines[:40])
        # Check for the environment variable check pattern
        env_check_patterns = [
            'os.environ.get("FISHBRO_ALLOW_LEGACY_WRAPPERS") != "1"',
            "os.environ.get('FISHBRO_ALLOW_LEGACY_WRAPPERS') != '1'",
            'environ.get("FISHBRO_ALLOW_LEGACY_WRAPPERS")',
        ]
        
        has_env_check = any(pattern in early_content for pattern in env_check_patterns)
        assert has_env_check, (
            f"{script_name}: Env check should be near the top of the file\n"
            f"First 40 lines:\n{early_content}"
        )


# Import regex module for Makefile parsing
import re

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
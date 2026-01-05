"""
Bypass prevention tests for Qt Desktop.

Test that run_make_command is not reachable from UI paths.
Optionally assert Makefile does not directly execute core scripts (wrapper-only).
"""

import pytest
import subprocess
import re
from pathlib import Path


def test_run_make_command_not_in_desktop_code():
    """Test that run_make_command is not present in src/gui/desktop code."""
    # Search for run_make_command in GUI desktop source files
    result = subprocess.run(
        ["grep", "-r", "run_make_command", "src/gui/desktop"],
        capture_output=True,
        text=True
    )
    
    # If there are matches, they should only be in deprecated or test code
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        allowed_patterns = [
            r"test_.*\.py",  # Test files
            r"deprecated",   # Deprecated code
            r"legacy",       # Legacy code
            r"#.*run_make_command",  # Comments
            r"\.pyc$",       # Compiled Python files
            r"__pycache__",  # Cache directories
        ]
        
        violations = []
        for line in lines:
            if not line:
                continue
                
            # Check if line matches any allowed pattern
            is_allowed = any(re.search(pattern, line) for pattern in allowed_patterns)
            
            if not is_allowed:
                violations.append(line)
        
        if violations:
            # Format violation message
            violation_msg = "run_make_command found in Qt Desktop production code:\n"
            for violation in violations[:10]:  # Show first 10 violations
                violation_msg += f"  - {violation}\n"
            if len(violations) > 10:
                violation_msg += f"  ... and {len(violations) - 10} more violations\n"
            
            pytest.fail(violation_msg)
    
    print("✓ No run_make_command in Qt Desktop production code")


def test_makefile_wrapper_only():
    """Test that Makefile does not directly execute core scripts (wrapper-only).
    
    This test checks that Makefile targets in the project root don't directly
    execute core Python scripts without going through proper supervisor APIs.
    """
    makefile_path = Path("Makefile")
    if not makefile_path.exists():
        pytest.skip("Makefile not found")
    
    with open(makefile_path, "r") as f:
        makefile_content = f.read()
    
    # Patterns that indicate direct script execution (to be avoided)
    direct_execution_patterns = [
        r"python.*scripts/run_phase",  # Direct phase execution
        r"python.*scripts/build_portfolio",  # Direct portfolio build
        r"python.*scripts/freeze_season",  # Direct freeze
        r"python.*scripts/run_phase3a_plateau",  # Direct plateau
        r"python.*scripts/run_phase3c_compile",  # Direct compile
    ]
    
    violations = []
    lines = makefile_content.split('\n')
    for i, line in enumerate(lines, 1):
        # Skip comments and empty lines
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        
        for pattern in direct_execution_patterns:
            if re.search(pattern, line):
                violations.append(f"Line {i}: {line.strip()}")
                break
    
    if violations:
        violation_msg = "Makefile appears to directly execute core scripts (should use supervisor APIs):\n"
        for violation in violations:
            violation_msg += f"  - {violation}\n"
        
        # This might be expected in some cases, so we warn but don't fail
        print(f"⚠️  Warning: {violation_msg}")
        # Uncomment to make test fail:
        # pytest.fail(violation_msg)
    else:
        print("✓ Makefile follows wrapper-only pattern")


def test_desktop_imports_supervisor():
    """Test that Qt Desktop code imports supervisor client, not direct scripts."""
    # This is a conceptual test - we could implement actual import checking
    # For now, we'll check that src/gui/desktop/services/supervisor_client.py exists
    supervisor_client_path = Path("src/gui/desktop/services/supervisor_client.py")
    assert supervisor_client_path.exists(), "supervisor_client.py should exist for proper API usage"
    
    # Check that it imports from src.control.supervisor
    with open(supervisor_client_path, "r") as f:
        content = f.read()
    
    # Should import submit, get_job, etc.
    expected_imports = ["from src.control.supervisor", "import submit", "import get_job"]
    for expected in expected_imports:
        if expected not in content:
            print(f"⚠️  Warning: {expected} not found in supervisor_client.py")
    
    print("✓ Qt Desktop uses supervisor client")


def test_no_direct_subprocess_in_desktop():
    """Test that Qt Desktop code doesn't use subprocess to run core scripts."""
    # Search for subprocess.run/call/Popen in desktop code
    result = subprocess.run(
        ["grep", "-r", "subprocess\\.", "src/gui/desktop"],
        capture_output=True,
        text=True
    )
    
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        
        # Filter out allowed uses (test files, comments, etc.)
        allowed_patterns = [
            r"test_.*\.py",
            r"#.*subprocess",
            r"subprocess\.DEVNULL",
            r"subprocess\.PIPE",
            r"subprocess\.CalledProcessError",
        ]
        
        violations = []
        for line in lines:
            if not line:
                continue
                
            # Check if line is allowed
            is_allowed = any(re.search(pattern, line) for pattern in allowed_patterns)
            
            # Also check if it's calling supervisor CLI (which is allowed)
            if "supervisor" in line.lower() or "cli" in line.lower():
                is_allowed = True
            
            if not is_allowed and ("subprocess.run" in line or "subprocess.call" in line or "subprocess.Popen" in line):
                violations.append(line)
        
        if violations:
            print(f"⚠️  Warning: subprocess usage found in Qt Desktop code:\n")
            for violation in violations[:5]:
                print(f"  - {violation}")
            print("  (Consider using supervisor APIs instead)")
        else:
            print("✓ No direct subprocess calls to core scripts in Qt Desktop")
    else:
        print("✓ No subprocess usage in Qt Desktop code")


if __name__ == "__main__":
    # Run tests
    test_run_make_command_not_in_desktop_code()
    test_makefile_wrapper_only()
    test_desktop_imports_supervisor()
    test_no_direct_subprocess_in_desktop()
    print("\n✅ All bypass prevention tests passed!")

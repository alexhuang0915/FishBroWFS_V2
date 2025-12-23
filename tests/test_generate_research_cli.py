"""Test generate_research.py CLI behavior.

Ensure that:
1. -h / --help does not execute generate logic
2. --dry-run works without writing files
3. Script does not crash on import errors
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import pytest


def test_generate_research_help_does_not_execute():
    """Test that -h/--help does not execute generate logic."""
    # Test -h
    result = subprocess.run(
        [sys.executable, "scripts/generate_research.py", "-h"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, f"Help should exit with 0, got {result.returncode}"
    assert "usage:" in result.stdout.lower() or "help" in result.stdout.lower()
    assert "error" not in result.stdout.lower()
    assert "error" not in result.stderr.lower()
    
    # Test --help
    result = subprocess.run(
        [sys.executable, "scripts/generate_research.py", "--help"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, f"Help should exit with 0, got {result.returncode}"
    assert "usage:" in result.stdout.lower() or "help" in result.stdout.lower()
    assert "error" not in result.stdout.lower()
    assert "error" not in result.stderr.lower()


def test_generate_research_dry_run():
    """Test that --dry-run works without writing files."""
    # Create a temporary outputs directory to test
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()
        
        result = subprocess.run(
            [
                sys.executable,
                "scripts/generate_research.py",
                "--outputs-root", str(outputs_root),
                "--dry-run",
                "--verbose",
            ],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, f"Dry run should exit with 0, got {result.returncode}"
        assert "dry run" in result.stdout.lower() or "would generate" in result.stdout.lower()
        
        # Ensure no files were actually created
        research_dir = outputs_root / "research"
        assert not research_dir.exists() or not list(research_dir.glob("*.json"))


def test_generate_research_without_outputs_dir():
    """Test that script handles missing outputs directory gracefully."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        outputs_root = tmp_path / "nonexistent"
        
        result = subprocess.run(
            [
                sys.executable,
                "scripts/generate_research.py",
                "--outputs-root", str(outputs_root),
            ],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
        )
        
        # Should either succeed (creating empty results) or fail gracefully
        # but not crash with import errors
        assert result.returncode in (0, 1), f"Unexpected exit code: {result.returncode}"
        assert "import error" not in result.stderr.lower(), f"Import error occurred: {result.stderr}"


def test_generate_research_import_fixed():
    """Test that import errors are fixed (no NameError for extract_canonical_metrics)."""
    # This test imports the module directly to check for import errors
    import sys
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root / "src"))
    
    try:
        from FishBroWFS_V2.research.__main__ import generate_canonical_results
        from FishBroWFS_V2.research.registry import build_research_index
        
        # If we get here, imports succeeded
        assert True
    except ImportError as e:
        pytest.fail(f"Import error: {e}")
    except NameError as e:
        pytest.fail(f"NameError (missing import): {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
import os
import sys
from pathlib import Path

def test_rooignore_presence_and_guard():
    """Guard that ensures .rooignore exists and contains mandatory rules for AI context control."""
    
    # A) Locate repo root robustly
    test_file_path = Path(__file__).resolve()
    repo_root = None
    for parent in test_file_path.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists() or (parent / "Makefile").exists():
            repo_root = parent
            break
    
    if repo_root is None:
        raise AssertionError("Could not locate repository root. Must contain pyproject.toml, .git, or Makefile")
    
    # B) Verify .rooignore exists at root
    rooignore_path = repo_root / ".rooignore"
    if not rooignore_path.exists() or not rooignore_path.is_file():
        raise AssertionError(".rooignore file missing at repo root. This guard is mandatory for API cost control.")
    
    # C) Read contents and check for mandatory patterns
    with open(rooignore_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Required patterns (must appear exactly as shown, though whitespace/newlines may vary)
    required_patterns = [
        ".env",
        ".venv/",
        "__pycache__/",
        "FishBroData/",
        "*.csv",
        "outputs/seasons/",
        "outputs/runs/"
    ]
    
    missing_patterns = []
    for pattern in required_patterns:
        # Check if pattern appears in content (allowing for surrounding whitespace)
        # Simple substring search is sufficient for this guard
        if pattern not in content:
            missing_patterns.append(pattern)
    
    if missing_patterns:
        missing_str = ", ".join(missing_patterns)
        raise AssertionError(
            f"Missing required .rooignore rule(s): {missing_str}. "
            "This guard is mandatory for API cost control."
        )
    
    # If we reach here, all is good
    assert True
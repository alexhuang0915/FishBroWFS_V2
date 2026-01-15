"""Root hygiene guard test - ensures repo root contains only allowed project files."""

import os
import re
import json
import datetime
import pytest
from pathlib import Path


def test_root_hygiene_no_forbidden_files():
    """Ensure repo root contains only allowed project files."""
    # Get project root (two levels up from this test file)
    test_dir = Path(__file__).parent
    root = test_dir.parent.parent
    
    # Standard allowed files and directories
    allowed_files = {
        'README.md',
        'main.py',
        'Makefile',
        'pyproject.toml',
        'pytest.ini',
        'requirements.txt',
        'SNAPSHOT_CLEAN.jsonl',
        '.gitattributes',
        '.gitignore',
        '.cursorignore',  # Cursor IDE developer tooling ignore file (non-runtime)
        '.pre-commit-config.yaml',
        'FishBroWFS_UI.bat',  # Sole human entrypoint. Approved by constitution.
        '.rooignore',  # AI context guard for API cost control
        'pyrightconfig.json',  # Pyright configuration for type checking
    }
    
    allowed_dirs = {
        'src',
        'tests',
        'docs',
        'plans',
        'scripts',
        'outputs',
        'configs',
        '.continue',
        '.github',
        '.vscode',
        'FishBroData',  # Data directory for the project
    }
    
    # Patterns that are forbidden in root
    forbidden_patterns = [
        r'^tmp_.*\.py$',
        r'.*_verification.*\.py$',
        r'.*_report.*\.md$',
        r'^AS_IS_.*\.md$',
        r'^GAP_LIST\.md$',
        r'^S2S3_CONTRACT\.md$',
        r'.*\.zip$',
        r'.*\.tar\.gz$',
        r'.*\.save$',  # Backup files like .gitattributes.save
    ]
    
    # Items to ignore completely (development artifacts)
    ignore_items = {
        '.git',
        '.venv',
        '__pycache__',
        '.pytest_cache',
        '.mypy_cache',
        '.pytest_cache',
        'examples',
    }
    
    violations = []
    actual_items = []
    
    for item in os.listdir(root):
        if item in ignore_items:
            continue
            
        item_path = root / item
        actual_items.append(item)
        
        if os.path.isdir(item_path):
            if item not in allowed_dirs:
                violations.append(f"Unexpected directory: {item}")
        else:
            if item not in allowed_files:
                # Check forbidden patterns
                matched_pattern = None
                for pattern in forbidden_patterns:
                    if re.match(pattern, item):
                        matched_pattern = pattern
                        break
                
                if matched_pattern:
                    violations.append(f"Forbidden pattern match: {item} (matches {matched_pattern})")
                else:
                    # Not in allowed_files and doesn't match forbidden patterns
                    violations.append(f"Unexpected file: {item}")
    
    # Save evidence for debugging
    evidence_dir = root / "outputs" / "_dp_evidence" / "root_hygiene"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    evidence = {
        "root_path": str(root),
        "allowed_files": sorted(list(allowed_files)),
        "allowed_dirs": sorted(list(allowed_dirs)),
        "forbidden_patterns": forbidden_patterns,
        "ignore_items": sorted(list(ignore_items)),
        "actual_items": sorted(actual_items),
        "violations": violations,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    
    evidence_file = evidence_dir / "root_hygiene_evidence.json"
    with open(evidence_file, 'w') as f:
        json.dump(evidence, f, indent=2)
    
    if violations:
        pytest.fail(f"Root hygiene violations ({len(violations)}):\n" + "\n".join(violations))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
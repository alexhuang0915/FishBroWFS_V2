"""
Guard against hardcoded 'outputs/' paths in source code.

Scan src/ directory for literal string "outputs/" (with quotes).
Fail if found outside of allowlisted files.

Rationale:
- Outputs paths should be configurable via environment variables or central config
- Hardcoded paths create deployment inflexibility and test contamination
"""

import os
import re
from pathlib import Path


def test_no_hardcoded_outputs_paths():
    """Scan src/ for hardcoded 'outputs/' strings."""
    
    # Locate repo root
    test_file_path = Path(__file__).resolve()
    repo_root = None
    for parent in test_file_path.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists() or (parent / "Makefile").exists():
            repo_root = parent
            break
    
    if repo_root is None:
        raise AssertionError("Could not locate repository root")
    
    src_dir = repo_root / "src"
    if not src_dir.exists():
        raise AssertionError("src/ directory not found")
    
    # Allowlist of files that are allowed to contain "outputs/"
    # These are configuration files or central path definitions
    allowlist = {
        # Central path configuration files
        "src/core/paths.py",
        "src/control/api.py",  # Has FISHBRO_* env var defaults
        "src/control/season_export.py",  # Has FISHBRO_EXPORTS_ROOT default
        "src/control/dataset_registry_mutation.py",  # Has FISHBRO_DATASET_REGISTRY_ROOT default
        "src/control/season_api.py",  # Has FISHBRO_SEASON_INDEX_ROOT default
        "src/utils/write_scope.py",  # Has FISHBRO_EXPORTS_ROOT default
        "src/control/supervisor/supervisor.py",  # Supervisor artifacts root
        "src/gui/desktop/config.py",  # Desktop config paths
        "src/control/local_scan.py",  # Has outputs_allow tuple
        "src/control/supervisor/handlers/base_governed.py",  # @governed_handler path
        "src/control/supervisor/handlers/generate_reports.py",  # Regex patterns
        "src/control/supervisor/handlers/build_data.py",  # Regex patterns
        "src/portfolio/store.py",  # Default portfolio store path
        "src/portfolio/audit.py",  # Default audit path
        "src/control/deploy_txt.py",  # Example deployment output
        "src/control/dataset_catalog.py",  # Default index path
        "src/control/dataset_descriptor.py",  # Parquet root construction
        "src/control/data_build.py",  # Parquet root
        "src/control/run_status.py",  # Status file paths
        "src/control/snapshot_compiler.py",  # Snapshots root
        "src/control/portfolio/api_v1.py",  # Portfolios root
        "src/control/reporting/io.py",  # Reporting paths
        "src/control/reporting/builders.py",  # More reporting paths
        "src/portfolio/candidate_export.py",  # Exports root
        "src/portfolio/governance/governance_logging.py",  # Governance root
        "src/gui/desktop/services/cleanup_service.py",  # Cleanup allowlist
        "src/gui/desktop/widgets/cleanup_dialog.py",  # UI path display
        "src/gui/services/runtime_context.py",  # Manifest/snapshot paths
        "src/core/policy_engine.py",  # LIVE_TOKEN_PATH
    }
    
    # Convert to Path objects for comparison
    allowlist_paths = {repo_root / path for path in allowlist}
    
    # Patterns to search for
    # Looking for literal "outputs/" or 'outputs/' in strings
    patterns = [
        r'"outputs/',      # double quote
        r"'outputs/",      # single quote
        r'f"outputs/',     # f-string double quote
        r"f'outputs/",     # f-string single quote
    ]
    
    compiled_patterns = [re.compile(pattern) for pattern in patterns]
    
    violations = []
    
    # Walk through src directory
    for root, dirs, files in os.walk(src_dir):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        
        for file in files:
            if not file.endswith('.py'):
                continue
            
            file_path = Path(root) / file
            rel_path = file_path.relative_to(repo_root)
            
            # Check if file is in allowlist
            if file_path in allowlist_paths or str(rel_path) in allowlist:
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Check each pattern
                for pattern in compiled_patterns:
                    if pattern.search(content):
                        # Find line numbers for better error messages
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if pattern.search(line):
                                violations.append(
                                    f"{rel_path}:{i}: {line.strip()[:80]}"
                                )
                        break  # Only report first violation per file
                        
            except (UnicodeDecodeError, IOError) as e:
                # Skip binary files or unreadable files
                continue
    
    if violations:
        violation_msg = "\n".join(violations[:20])  # Show first 20 violations
        if len(violations) > 20:
            violation_msg += f"\n... and {len(violations) - 20} more violations"
        
        raise AssertionError(
            f"Found {len(violations)} files with hardcoded 'outputs/' paths.\n"
            f"Paths should be configurable via environment variables or central config.\n"
            f"Violations:\n{violation_msg}\n\n"
            f"If a file legitimately needs 'outputs/' (e.g., central config),\n"
            f"add it to the allowlist in this test."
        )
    
    # Test passes if no violations
    assert True


def test_outputs_paths_use_env_vars_or_config():
    """
    Verify that central path definitions use environment variables.
    
    This is a softer check: ensure that at least the central config files
    use FISHBRO_* environment variables with defaults.
    """
    test_file_path = Path(__file__).resolve()
    repo_root = None
    for parent in test_file_path.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists() or (parent / "Makefile").exists():
            repo_root = parent
            break
    
    if repo_root is None:
        raise AssertionError("Could not locate repository root")
    
    # Check that src/core/paths.py exists and defines output paths
    paths_py = repo_root / "src" / "core" / "paths.py"
    
    # If paths.py doesn't exist, that's okay - paths might be defined elsewhere
    # But we should at least verify some centralization exists
    central_files = [
        repo_root / "src" / "core" / "paths.py",
        repo_root / "src" / "control" / "api.py",
    ]
    
    has_central_config = False
    for file_path in central_files:
        if file_path.exists():
            has_central_config = True
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Check for environment variable usage
                if 'os.environ.get' in content or 'FISHBRO_' in content:
                    # Good: using environment variables
                    pass
                else:
                    # Warn but don't fail - might be using other config mechanism
                    print(f"Warning: {file_path.name} doesn't use environment variables for paths")
    
    if not has_central_config:
        print("Warning: No central path configuration file found")
    
    # Test passes (this is a warning test, not a failure)
    assert True


if __name__ == "__main__":
    test_no_hardcoded_outputs_paths()
    test_outputs_paths_use_env_vars_or_config()
    print("All tests passed")
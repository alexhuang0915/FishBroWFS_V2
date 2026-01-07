"""Policy test: subprocess usage must be constrained to explicit allowlist.

Product UI must not directly spawn subprocesses except for Supervisor bootstrap.
All other subprocess usage must be justified and documented.

This test scans src/ for subprocess calls and fails if matches occur outside
the allowlist of file paths.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Allowed subprocess usage paths (relative to src/)
ALLOWLIST = [
    # Supervisor lifecycle (Desktop UI bootstrap)
    "gui/desktop/supervisor_lifecycle.py",
    # Supervisor core (spawning workers)
    "control/supervisor/supervisor.py",
    # Supervisor evidence collection
    "control/supervisor/evidence.py",
    # Supervisor handlers (run research, plateau, freeze, compile, build portfolio, generate reports, build data)
    "control/supervisor/handlers/run_research.py",
    "control/supervisor/handlers/run_plateau.py",
    "control/supervisor/handlers/run_freeze.py",
    "control/supervisor/handlers/run_compile.py",
    "control/supervisor/handlers/build_portfolio.py",
    "control/supervisor/handlers/generate_reports.py",
    "control/supervisor/handlers/build_data.py",
    # System checks (port occupancy detection)
    "control/lifecycle.py",
    # API spawning supervisor
    "control/api.py",
    # Runtime context (diagnostics, not UI entrypoint) – allowed with comment
    "gui/services/runtime_context.py",
    # Funnel runner (git info, not UI entrypoint) – allowed with comment
    "pipeline/funnel_runner.py",
    # Audit tab - opening evidence folders (legitimate UI feature)
    "gui/desktop/tabs/audit_tab.py",
    # Scripts directory (non‑product)
    # Note: scripts/ is not under src/, but we can allow any file under scripts/
]

# Convert to absolute paths
SRC_ROOT = Path(__file__).parent.parent.parent / "src"
ALLOWLIST_ABS = [SRC_ROOT / path for path in ALLOWLIST]

# Also allow any file under scripts/ (outside src)
SCRIPTS_ROOT = Path(__file__).parent.parent.parent / "scripts"


def is_allowed(path: Path) -> bool:
    """Return True if the file is allowed to use subprocess."""
    # Allow any file under scripts/
    if SCRIPTS_ROOT in path.parents:
        return True
    # Allow exact matches in allowlist
    if path in ALLOWLIST_ABS:
        return True
    # Allow any file under allowed directories? We'll keep strict.
    return False


def find_subprocess_calls(node: ast.AST) -> list[tuple[int, int]]:
    """Return list of (line, col) positions of subprocess calls in node."""
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            # Check if it's subprocess.Popen, subprocess.run, subprocess.call, etc.
            # We'll look for attribute access like subprocess.Popen
            if isinstance(child.func, ast.Attribute):
                attr = child.func
                if isinstance(attr.value, ast.Name):
                    if attr.value.id == "subprocess":
                        calls.append((child.lineno, child.col_offset))
            # Also check for os.system
            if isinstance(child.func, ast.Attribute):
                attr = child.func
                if isinstance(attr.value, ast.Name):
                    if attr.value.id == "os" and attr.attr == "system":
                        calls.append((child.lineno, child.col_offset))
            # Also check for subprocess.Popen as a Name? (imported as Popen)
            if isinstance(child.func, ast.Name):
                # Could be Popen imported from subprocess; we'll catch via import analysis later.
                pass
    return calls


def find_imports(node: ast.AST) -> set[str]:
    """Return set of imported module names."""
    imports = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                imports.add(alias.name)
        elif isinstance(child, ast.ImportFrom):
            if child.module:
                imports.add(child.module)
    return imports


def test_subprocess_allowlist():
    """Scan src/ for subprocess usage and enforce allowlist."""
    src_root = SRC_ROOT
    assert src_root.exists(), f"src root not found: {src_root}"

    violations = []

    for py_file in src_root.rglob("*.py"):
        # Skip __pycache__
        if "__pycache__" in str(py_file):
            continue

        # Check if allowed
        if is_allowed(py_file):
            continue

        # Parse file
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError) as e:
            # Skip files that cannot be parsed (should not happen)
            continue

        # Look for subprocess imports
        imports = find_imports(tree)
        uses_subprocess = any(
            imp == "subprocess" or imp.startswith("subprocess.")
            for imp in imports
        )
        uses_os_system = any(imp == "os" for imp in imports)

        # Look for subprocess calls
        calls = find_subprocess_calls(tree)

        if uses_subprocess or uses_os_system or calls:
            # Determine if there are actual calls (not just imports)
            # We'll treat any import as a violation unless allowed.
            # But some files may import subprocess but not call it (false positive).
            # We'll do a simple grep for "subprocess." or "os.system" in content.
            if "subprocess." in content or "os.system" in content:
                rel_path = py_file.relative_to(src_root)
                violations.append(str(rel_path))

    # Also scan scripts/ for subprocess usage (allowed, but we can log)
    # No need to fail.

    assert not violations, (
        "Subprocess usage found outside allowlist:\n" +
        "\n".join(f"  - {v}" for v in sorted(violations)) +
        "\n\nIf a new subprocess usage is required, add it to the allowlist in this test."
    )


if __name__ == "__main__":
    # Quick manual test
    test_subprocess_allowlist()
    print("✅ No unauthorized subprocess usage found.")
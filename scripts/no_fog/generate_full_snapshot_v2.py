#!/usr/bin/env python3
"""
Generate a FULL high-resolution repository snapshot using Local-Strict filesystem scanner.

Mission: Scan ALL files (tracked + untracked) within allowed roots, produce artifacts,
prove architectural compliance.

Output: SYSTEM_FULL_SNAPSHOT.md (flattened snapshot)
Intermediate artifacts are written to a temporary directory and embedded into the final
SYSTEM_FULL_SNAPSHOT.md, then cleaned up.

Hard Constraints:
- Use Local-Strict scanner as canonical source (filesystem truth)
- Skip large (>2MB) and binary files (NUL in first 8KB)
- Output must be deterministic and reproducible
- Total size < 5MB (target)
- Exit non-zero if any required artifact missing
- Handle encoding errors gracefully (replace)
- NO intermediate artifacts remain on disk after compilation
"""

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any, BinaryIO, NamedTuple

# Ensure we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Import our new Local-Strict scanner
try:
    from FishBroWFS_V2.control.local_scan import (
        default_local_strict_policy,
        iter_repo_files_local_strict,
        write_local_scan_rules,
        should_include_file,
    )
    LOCAL_SCAN_AVAILABLE = True
except ImportError:
    LOCAL_SCAN_AVAILABLE = False
    print("WARNING: Local-Strict scanner not available", file=sys.stderr)

# Optional import for YAML parsing
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None
    YAML_AVAILABLE = False

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# Output directory for final compiled snapshot
FINAL_SNAPSHOT_DIR = Path("outputs/snapshots")
FINAL_SNAPSHOT_FILE = FINAL_SNAPSHOT_DIR / "SYSTEM_FULL_SNAPSHOT.md"

# Temporary directory for intermediate artifacts (will be cleaned up)
TEMP_DIR_PREFIX = "fishbro_snapshot_"

# Skip policies (aligned with Local-Strict policy)
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
BINARY_CHECK_SIZE = 8192  # 8KB

# Excluded directory patterns (for reporting only, not scanning)
EXCLUDED_DIR_PATTERNS = [
    "outputs/",
    "artifacts/",
    "tmp_data/",
    ".venv/",
    "__pycache__/",
    ".git/",
    ".pytest_cache/",
    ".vscode/",
    ".idea/",
    "node_modules/",
    "dist/",
    "build/",
    "htmlcov/",
    "logs/",
    "temp/",
    "site-packages/",
    "venv/",
    "env/",
    "FishBroData/",
    "legacy/",
]

# Grep patterns for AUDIT_GREP.txt
GREP_PATTERNS = [
    "FishBroWFS_V2.control",
    "src/FishBroWFS_V2/data/profiles",
    "configs/profiles",
    "scripts/dev_dashboard.py",
    "app_nicegui.py",
    "Path(__file__).parent.parent",
    "importlib.import_module",
]

MAX_MATCHES_PER_PATTERN = 50  # As per spec: Max 50 hits per pattern (truncate)

# Patterns for AUDIT_CALL_GRAPH.txt
CALL_GRAPH_PATTERNS = [
    "dev_dashboard",
    "viewer.app",
    "nicegui.app",
]

# Patterns for AUDIT_RUNTIME_MUTATIONS.txt
MUTATION_PATTERNS = [
    r"open\([^)]*['\"]w['\"]",
    r"Path\([^)]*\)\.write_",
    r"os\.remove",
    r"shutil\.rmtree",
    r"json\.dump",
    r"yaml\.dump",
    r"pickle\.dump",
    r"to_parquet",
    r"to_csv",
    r"outputs/",
    r"artifacts/",
]

# Config key patterns for AUDIT_CONFIG_REFERENCES.txt
CONFIG_KEY_PATTERNS = [
    "path",
    "profile",
    "session_profile",
    "spec",
    "instrument",
    "policy",
]

# ------------------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------------------

def run_git(args: List[str]) -> str:
    """Run git command and return stdout as string."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {' '.join(args)}", file=sys.stderr)
        print(f"Error: {e.stderr}", file=sys.stderr)
        sys.exit(1)

def git_head() -> str:
    """Get current HEAD commit hash."""
    return run_git(["rev-parse", "HEAD"])

def is_binary_file(file_path: Path) -> bool:
    """
    Detect if file is binary by checking for null bytes in first BINARY_CHECK_SIZE bytes.
    Returns True if binary, False if text.
    """
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(BINARY_CHECK_SIZE)
            return b"\x00" in chunk
    except Exception:
        # If we can't read, treat as binary to skip
        return True

def sha256_file(file_path: Path) -> str:
    """Compute SHA256 hash of file bytes."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        return f"ERROR:{e.__class__.__name__}"

def file_size(file_path: Path) -> int:
    """Get file size in bytes."""
    try:
        return file_path.stat().st_size
    except Exception:
        return 0

def should_skip_file(file_path: Path, size: int) -> Tuple[bool, Optional[str]]:
    """
    Determine if a file should be skipped for content scanning.
    Returns (skip, reason) where reason is None if not skipped.
    """
    if size > MAX_FILE_SIZE:
        return True, "TOO_LARGE"
    if is_binary_file(file_path):
        return True, "SKIP_BINARY"
    return False, None

def decode_with_replace(content_bytes: bytes) -> str:
    """Decode bytes to UTF-8 with replacement for errors."""
    return content_bytes.decode("utf-8", errors="replace")

# ------------------------------------------------------------------------------
# Artifact generators
# ------------------------------------------------------------------------------

def generate_local_scan_rules(output_path: Path, repo_root: Path):
    """Generate LOCAL_SCAN_RULES.json with policy and metadata."""
    if not LOCAL_SCAN_AVAILABLE:
        print("ERROR: Local-Strict scanner not available", file=sys.stderr)
        sys.exit(1)
    
    policy = default_local_strict_policy()
    write_local_scan_rules(policy, output_path, repo_root)

def generate_repo_tree_local_strict(files: List[Path], output_path: Path):
    """Generate REPO_TREE.txt based on Local-Strict file list."""
    lines = []
    
    # Section A: Local-Strict list
    lines.append("== LOCAL_STRICT_FILES ==")
    for path in sorted(files, key=lambda p: str(p)):
        lines.append(str(path))
    
    # Section B: Human tree view (simplified)
    lines.append("\n== TREE_VIEW (approx) ==")
    try:
        # Try to use tree command if available
        result = subprocess.run(
            ["tree", "-a", "-I", ".git|__pycache__|.venv|outputs|artifacts|tmp_data|node_modules"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            lines.append(result.stdout)
        else:
            lines.append("(tree command not available or failed)")
    except Exception:
        # Fallback: simple Python tree printer
        lines.append("(tree command not installed)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def generate_manifest(
    files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    output_path: Path,
    git_head_hash: str,
):
    """Generate MANIFEST.json with SHA256 for all files."""
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head_hash,
        "scan_mode": "local-strict",
        "file_count": len(files),
        "files": [],
    }
    
    for path in sorted(files, key=lambda p: str(p)):
        size = file_size(path)
        sha256 = sha256_file(path) if path.exists() else "ERROR:MISSING"
        manifest["files"].append({
            "path": str(path),
            "sha256": sha256,
            "bytes": size,
        })
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

def generate_skipped_files(
    files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    output_path: Path,
    policy,
):
    """Generate SKIPPED_FILES.txt with skip policies and skipped files."""
    lines = []
    
    # Section: Local-Strict policy
    lines.append("== LOCAL_STRICT_POLICY ==")
    lines.append(f"Allowed roots: {list(policy.allowed_roots)}")
    lines.append(f"Allowed root files glob: {list(policy.allowed_root_files_glob)}")
    lines.append(f"Deny segments: {list(policy.deny_segments)}")
    lines.append(f"Outputs allow: {list(policy.outputs_allow)}")
    lines.append(f"Max files: {policy.max_files}")
    lines.append(f"Max bytes: {policy.max_bytes}")
    lines.append(f"Gitignore respected: {policy.gitignore_respected}")
    
    # Section: Skip policies
    lines.append("\n== CONTENT_SKIP_POLICIES ==")
    for pattern in EXCLUDED_DIR_PATTERNS:
        lines.append(f"DIRECTORY: {pattern}")
    lines.append(f"SIZE_LIMIT: >{MAX_FILE_SIZE} bytes")
    lines.append("BINARY_DETECT: NUL in first 8KB")
    
    # Section: Skipped files (content scanning)
    lines.append("\n== SKIPPED_FILES_CONTENT_SCAN ==")
    if skipped_map:
        for path, (reason, size) in sorted(skipped_map.items(), key=lambda x: str(x[0])):
            lines.append(f"{reason}\t{size}\t{path}")
    else:
        lines.append("(none)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def scan_grep(
    files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    patterns: List[str],
) -> Dict[str, List[Tuple[Path, int, str]]]:
    """
    Scan files for grep patterns.
    Returns dict: pattern -> list of (path, lineno, line_text)
    """
    results = {pattern: [] for pattern in patterns}
    
    for path in files:
        if path in skipped_map:
            continue  # Skip large/binary files
        
        try:
            content_bytes = path.read_bytes()
            content = decode_with_replace(content_bytes)
            lines = content.splitlines()
        except Exception:
            continue
        
        for pattern in patterns:
            if len(results[pattern]) >= MAX_MATCHES_PER_PATTERN:
                continue
            
            for i, line in enumerate(lines, 1):
                if pattern in line:
                    results[pattern].append((path, i, line.strip()))
                    if len(results[pattern]) >= MAX_MATCHES_PER_PATTERN:
                        break
    
    return results

def generate_audit_grep(
    grep_results: Dict[str, List[Tuple[Path, int, str]]],
    output_path: Path,
):
    """Generate AUDIT_GREP.txt with pattern matches."""
    lines = []
    
    for pattern, matches in grep_results.items():
        lines.append(f"== PATTERN: {pattern} ==")
        if not matches:
            lines.append("0 matches")
        else:
            total_matches = len(matches)
            displayed = matches[:MAX_MATCHES_PER_PATTERN]
            for path, lineno, line_text in displayed:
                lines.append(f"{path}:{lineno}: {line_text}")
            
            if total_matches > MAX_MATCHES_PER_PATTERN:
                lines.append(f"TRUNCATED: total_matches={total_matches} kept={MAX_MATCHES_PER_PATTERN}")
        
        lines.append("")  # blank line between patterns
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

class ImportRow(NamedTuple):
    file: Path
    lineno: int
    kind: str  # "import" or "from"
    module: str
    name: str

def scan_imports_py(
    files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
) -> List[ImportRow]:
    """
    Parse Python files for imports using AST.
    Returns list of ImportRow.
    """
    rows = []
    
    for path in files:
        if path in skipped_map:
            continue
        if path.suffix != ".py":
            continue
        
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(path))
        except Exception as e:
            # Record error row
            rows.append(ImportRow(
                file=path,
                lineno=1,
                kind="ERROR",
                module="AST_PARSE_FAILED",
                name=e.__class__.__name__,
            ))
            continue
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    rows.append(ImportRow(
                        file=path,
                        lineno=node.lineno,
                        kind="import",
                        module=alias.name,
                        name=alias.asname if alias.asname else alias.name,
                    ))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    rows.append(ImportRow(
                        file=path,
                        lineno=node.lineno,
                        kind="from",
                        module=module,
                        name=alias.asname if alias.asname else alias.name,
                    ))
    
    # Sort: file asc, lineno asc, kind asc, module asc
    rows.sort(key=lambda r: (str(r.file).lower(), r.lineno, r.kind, r.module.lower()))
    return rows

def generate_audit_imports(
    import_rows: List[ImportRow],
    output_path: Path,
):
    """Generate AUDIT_IMPORTS.csv."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "lineno", "kind", "module", "name"])
        for row in import_rows:
            writer.writerow([str(row.file), row.lineno, row.kind, row.module, row.name])

def generate_audit_entrypoints(
    files: List[Path],
    git_head_hash: str,
    output_path: Path,
):
    """Generate AUDIT_ENTRYPOINTS.md."""
    lines = []
    
    # Section A: Git HEAD
    lines.append("## Git HEAD")
    lines.append(f"`{git_head_hash}`")
    lines.append("")
    
    # Section B: Makefile Targets Extract
    lines.append("## Makefile Targets Extract")
    makefile_path = Path("Makefile")
    if makefile_path.exists():
        content = makefile_path.read_text(encoding="utf-8", errors="replace")
        targets_to_find = ["dashboard", "check", "test", "snapshot", "full-snapshot"]
        for target in targets_to_find:
            pattern = rf"^{target}:"
            found = False
            for line in content.splitlines():
                if re.match(pattern, line.strip()):
                    lines.append(f"### {target}")
                    lines.append(f"```makefile")
                    # Include the target and its recipe (next lines with tabs)
                    lines.append(line.rstrip())
                    # Could extract more, but keep simple
                    lines.append(f"```")
                    found = True
                    break
            if not found:
                lines.append(f"### {target}")
                lines.append("NOT FOUND")
            lines.append("")
    else:
        lines.append("Makefile not found")
        lines.append("")
    
    # Section C: Detected Python Entrypoints
    lines.append("## Detected Python Entrypoints")
    entrypoints = []
    for path in files:
        if path.suffix != ".py":
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if '__name__ == "__main__"' in content:
                # Find line number
                for i, line in enumerate(content.splitlines(), 1):
                    if '__name__ == "__main__"' in line:
                        entrypoints.append((path, i))
                        break
        except Exception:
            pass
    
    if entrypoints:
        for path, lineno in sorted(entrypoints, key=lambda x: str(x[0])):
            lines.append(f"- `{path}:{lineno}`")
    else:
        lines.append("(none)")
    lines.append("")
    
    # Section D: Notes / Risk Flags
    lines.append("## Notes / Risk Flags")
    lines.append("- **Local-Strict scanner**: uses filesystem truth (includes untracked)")
    lines.append("- **Max file size**: 2MB limit for content scanning")
    lines.append("- **Binary detection**: NUL in first 8KB")
    lines.append("- **Deterministic ordering**: sorted by path")
    lines.append("- **Gitignore ignored**: gitignore_respected=false")
    lines.append("- **Outputs exception**: only outputs/snapshots/** allowed")
    lines.append("")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def generate_audit_call_graph(
    files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    patterns: List[str],
    output_path: Path,
):
    """Generate AUDIT_CALL_GRAPH.txt."""
    lines = []
    lines.append("== CALL GRAPH PATTERNS ==")
    
    grep_results = scan_grep(files, skipped_map, patterns)
    for pattern, matches in grep_results.items():
        lines.append(f"=== {pattern} ===")
        if not matches:
            lines.append("0 matches")
        else:
            for path, lineno, line_text in matches[:MAX_MATCHES_PER_PATTERN]:
                lines.append(f"{path}:{lineno}: {line_text}")
            if len(matches) > MAX_MATCHES_PER_PATTERN:
                lines.append(f"TRUNCATED: total_matches={len(matches)} kept={MAX_MATCHES_PER_PATTERN}")
        lines.append("")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def generate_audit_runtime_mutations(
    files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    patterns: List[str],
    output_path: Path,
):
    """Generate AUDIT_RUNTIME_MUTATIONS.txt."""
    lines = []
    lines.append("== RUNTIME MUTATION PATTERNS ==")
    
    for pattern in patterns:
        lines.append(f"=== {pattern} ===")
        # We'll reuse scan_grep but with regex patterns
        # For simplicity, we'll just note the pattern
        lines.append(f"Pattern: {pattern}")
        lines.append("")
    
    # Actually scan
    grep_results = scan_grep(files, skipped_map, patterns)
    for pattern, matches in grep_results.items():
        lines.append(f"=== {pattern} ===")
        if not matches:
            lines.append("0 matches")
        else:
            for path, lineno, line_text in matches[:MAX_MATCHES_PER_PATTERN]:
                lines.append(f"{path}:{lineno}: {line_text}")
            if len(matches) > MAX_MATCHES_PER_PATTERN:
                lines.append(f"TRUNCATED: total_matches={len(matches)} kept={MAX_MATCHES_PER_PATTERN}")
        lines.append("")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def generate_audit_config_references(
    files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    patterns: List[str],
    output_path: Path,
):
    """Generate AUDIT_CONFIG_REFERENCES.txt."""
    lines = []
    lines.append("== CONFIG KEY REFERENCES ==")
    
    grep_results = scan_grep(files, skipped_map, patterns)
    for pattern, matches in grep_results.items():
        lines.append(f"=== {pattern} ===")
        if not matches:
            lines.append("0 matches")
        else:
            for path, lineno, line_text in matches[:MAX_MATCHES_PER_PATTERN]:
                lines.append(f"{path}:{lineno}: {line_text}")
            if len(matches) > MAX_MATCHES_PER_PATTERN:
                lines.append(f"TRUNCATED: total_matches={len(matches)} kept={MAX_MATCHES_PER_PATTERN}")
        lines.append("")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def generate_audit_test_surface(
    files: List[Path],
    output_path: Path,
):
    """Generate AUDIT_TEST_SURFACE.txt."""
    lines = []
    lines.append("== TEST SURFACE ==")
    
    test_files = [p for p in files if "test" in str(p).lower() and p.suffix == ".py"]
    lines.append(f"Total test files: {len(test_files)}")
    lines.append("")
    
    for path in sorted(test_files, key=lambda p: str(p)):
        lines.append(str(path))
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def generate_audit_state_flow(
    files: List[Path],
    output_path: Path,
):
    """Generate AUDIT_STATE_FLOW.md."""
    lines = []
    lines.append("# State Flow Audit")
    lines.append("")
    lines.append("## Overview")
    lines.append("This document tracks architectural layer flow based on file locations.")
    lines.append("")
    
    # Categorize files
    categories = {
        "src/": [],
        "tests/": [],
        "scripts/": [],
        "configs/": [],
        "docs/": [],
        "other": [],
    }
    
    for path in files:
        path_str = str(path)
        categorized = False
        for prefix in categories:
            if prefix != "other" and path_str.startswith(prefix):
                categories[prefix].append(path_str)
                categorized = True
                break
        if not categorized:
            categories["other"].append(path_str)
    
    for cat, paths in categories.items():
        lines.append(f"## {cat}")
        lines.append(f"Count: {len(paths)}")
        if paths:
            lines.append("```")
            for p in sorted(paths)[:20]:  # Limit to 20 per category
                lines.append(p)
            if len(paths) > 20:
                lines.append(f"... and {len(paths) - 20} more")
            lines.append("```")
        lines.append("")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Generate full repository snapshot (Local-Strict)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing artifacts")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (deprecated, kept for compatibility)")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Keep temporary directory for debugging (default: False)")
    args = parser.parse_args()
    
    repo_root = Path.cwd()
    
    # Override output directory via environment variable
    final_snapshot_dir = Path(os.environ.get("FISHBRO_SNAPSHOT_OUTPUT_DIR", "outputs/snapshots"))
    final_snapshot_file = final_snapshot_dir / "SYSTEM_FULL_SNAPSHOT.md"
    
    # Create final snapshot directory
    final_snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean up old subdirectories (full/, runtime/) to enforce flattened structure
    old_dirs = ["full", "runtime"]
    for dir_name in old_dirs:
        old_dir = final_snapshot_dir / dir_name
        if old_dir.exists():
            print(f"Removing old subdirectory: {old_dir}")
            shutil.rmtree(old_dir, ignore_errors=True)
    
    print(f"Generating Local-Strict snapshot (flattened)")
    print(f"Repo root: {repo_root}")
    print(f"Final output: {final_snapshot_file}")
    
    if not LOCAL_SCAN_AVAILABLE:
        print("ERROR: Local-Strict scanner module not found", file=sys.stderr)
        sys.exit(1)
    
    # Create temporary directory for intermediate artifacts
    temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    print(f"Temporary directory: {temp_dir}")
    
    try:
        # Get policy and file list
        policy = default_local_strict_policy()
        print(f"Policy: allowed_roots={policy.allowed_roots}")
        
        files = iter_repo_files_local_strict(repo_root, policy)
        print(f"Local-Strict files found: {len(files)}")
        
        # Build skipped map for content scanning
        skipped_map = {}
        for path in files:
            size = file_size(path)
            skip, reason = should_skip_file(path, size)
            if skip:
                skipped_map[path] = (reason, size)
        
        print(f"Files skipped for content scanning: {len(skipped_map)}")
        
        git_head_hash = git_head()
        print(f"Git HEAD: {git_head_hash}")
        
        # Generate artifacts in temp directory
        print("\nGenerating artifacts...")
        
        # 1. LOCAL_SCAN_RULES.json
        local_scan_rules_path = temp_dir / "LOCAL_SCAN_RULES.json"
        print(f"  • {local_scan_rules_path.name}")
        generate_local_scan_rules(local_scan_rules_path, repo_root)
        
        # 2. REPO_TREE.txt
        repo_tree_path = temp_dir / "REPO_TREE.txt"
        print(f"  • {repo_tree_path.name}")
        generate_repo_tree_local_strict(files, repo_tree_path)
        
        # 3. MANIFEST.json
        manifest_path = temp_dir / "MANIFEST.json"
        print(f"  • {manifest_path.name}")
        generate_manifest(files, skipped_map, manifest_path, git_head_hash)
        
        # 4. SKIPPED_FILES.txt
        skipped_path = temp_dir / "SKIPPED_FILES.txt"
        print(f"  • {skipped_path.name}")
        generate_skipped_files(files, skipped_map, skipped_path, policy)
        
        # 5. AUDIT_GREP.txt
        grep_path = temp_dir / "AUDIT_GREP.txt"
        print(f"  • {grep_path.name}")
        grep_results = scan_grep(files, skipped_map, GREP_PATTERNS)
        generate_audit_grep(grep_results, grep_path)
        
        # 6. AUDIT_IMPORTS.csv
        imports_path = temp_dir / "AUDIT_IMPORTS.csv"
        print(f"  • {imports_path.name}")
        import_rows = scan_imports_py(files, skipped_map)
        generate_audit_imports(import_rows, imports_path)
        
        # 7. AUDIT_ENTRYPOINTS.md
        entrypoints_path = temp_dir / "AUDIT_ENTRYPOINTS.md"
        print(f"  • {entrypoints_path.name}")
        generate_audit_entrypoints(files, git_head_hash, entrypoints_path)
        
        # 8. AUDIT_CALL_GRAPH.txt
        call_graph_path = temp_dir / "AUDIT_CALL_GRAPH.txt"
        print(f"  • {call_graph_path.name}")
        generate_audit_call_graph(files, skipped_map, CALL_GRAPH_PATTERNS, call_graph_path)
        
        # 9. AUDIT_RUNTIME_MUTATIONS.txt
        mutations_path = temp_dir / "AUDIT_RUNTIME_MUTATIONS.txt"
        print(f"  • {mutations_path.name}")
        generate_audit_runtime_mutations(files, skipped_map, MUTATION_PATTERNS, mutations_path)
        
        # 10. AUDIT_CONFIG_REFERENCES.txt
        config_ref_path = temp_dir / "AUDIT_CONFIG_REFERENCES.txt"
        print(f"  • {config_ref_path.name}")
        generate_audit_config_references(files, skipped_map, CONFIG_KEY_PATTERNS, config_ref_path)
        
        # 11. AUDIT_TEST_SURFACE.txt
        test_surface_path = temp_dir / "AUDIT_TEST_SURFACE.txt"
        print(f"  • {test_surface_path.name}")
        generate_audit_test_surface(files, test_surface_path)
        
        # 12. AUDIT_STATE_FLOW.md
        state_flow_path = temp_dir / "AUDIT_STATE_FLOW.md"
        print(f"  • {state_flow_path.name}")
        generate_audit_state_flow(files, state_flow_path)
        
        # Verify required artifacts exist
        required = [
            local_scan_rules_path,
            repo_tree_path,
            manifest_path,
            skipped_path,
            grep_path,
            imports_path,
            entrypoints_path,
            call_graph_path,
            mutations_path,
            config_ref_path,
            test_surface_path,
            state_flow_path,
        ]
        
        missing = [p for p in required if not p.exists()]
        if missing:
            print(f"ERROR: Missing required artifacts: {[p.name for p in missing]}", file=sys.stderr)
            sys.exit(1)
        
        # Print summary
        total_size = sum(p.stat().st_size for p in required if p.exists())
        print(f"Total artifact size: {total_size / 1024:.1f} KB")
        
        # Compile snapshot using the compiler module
        print("\nCompiling snapshot into SYSTEM_FULL_SNAPSHOT.md...")
        try:
            from FishBroWFS_V2.control.snapshot_compiler import compile_full_snapshot
            out_path = compile_full_snapshot(
                snapshots_root=str(temp_dir),  # Use temp dir as root
                full_dir_name=".",  # Artifacts are directly in temp_dir
                out_name="SYSTEM_FULL_SNAPSHOT.md"
            )
            # Move the compiled snapshot to final location
            shutil.move(str(out_path), str(final_snapshot_file))
            print(f"✓ Compiled snapshot written to: {final_snapshot_file}")
            print(f"Size: {final_snapshot_file.stat().st_size:,} bytes")
        except ImportError:
            print("ERROR: Snapshot compiler module not found", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to compile snapshot: {e}", file=sys.stderr)
            sys.exit(1)
        
        print("\n✅ Snapshot generation complete")
        
    finally:
        # Clean up temporary directory unless --keep-temp flag is set
        if not args.keep_temp:
            print(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            print(f"Temporary directory kept (--keep-temp): {temp_dir}")

if __name__ == "__main__":
    main()

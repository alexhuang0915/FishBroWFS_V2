#!/usr/bin/env python3
"""
Generate a FULL high-resolution repository snapshot (Carpet Audit / Forensic Kit).

Mission: Scan ALL git-tracked code files, produce SMALL artifacts, prove architectural compliance.

Output directory: outputs/snapshots/full/
  - REPO_TREE.txt
  - MANIFEST.json
  - SKIPPED_FILES.txt
  - AUDIT_GREP.txt
  - AUDIT_IMPORTS.csv
  - AUDIT_ENTRYPOINTS.md

Hard Constraints:
- Use git ls-files as canonical source (100% coverage of tracked files)
- Skip large (>2MB) and binary files (NUL in first 8KB)
- Output must be deterministic and reproducible
- Total size < 5MB (target)
- Exit non-zero if any required artifact missing
- Handle encoding errors gracefully (replace)
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any, BinaryIO, NamedTuple

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

# Output directory (SSOT) - can be overridden by environment variable
OUTPUT_DIR = Path(
    os.environ.get("FISHBRO_SNAPSHOT_OUTPUT_DIR", "outputs/snapshots/full")
)

# Skip policies
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

def tracked_files() -> List[Path]:
    """Get list of all git-tracked files (NUL-separated)."""
    output = run_git(["ls-files", "-z"])
    if not output:
        return []
    # Split on NUL character
    files = output.split("\x00")
    # Remove empty strings
    files = [f for f in files if f]
    return [Path(f) for f in files]

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
    Determine if a tracked file should be skipped for content scanning.
    Returns (skip, reason) where reason is None if not skipped.
    """
    if size > MAX_FILE_SIZE:
        return True, "SKIP_LARGE"
    if is_binary_file(file_path):
        return True, "SKIP_BINARY"
    return False, None

def decode_with_replace(content_bytes: bytes) -> str:
    """Decode bytes to UTF-8 with replacement for errors."""
    return content_bytes.decode("utf-8", errors="replace")

# ------------------------------------------------------------------------------
# Artifact generators
# ------------------------------------------------------------------------------

def generate_repo_tree(tracked_files: List[Path], output_path: Path):
    """Generate REPO_TREE.txt with two sections."""
    lines = []
    
    # Section A: Git tracked list
    lines.append("== GIT_TRACKED_FILES ==")
    for path in sorted(tracked_files, key=lambda p: str(p)):
        lines.append(str(path))
    
    # Section B: Human tree view
    lines.append("\n== TREE_VIEW (approx) ==")
    try:
        # Try to use tree command if available
        result = subprocess.run(
            ["tree", "-a", "-I", ".git|__pycache__|.venv|outputs|artifacts|tmp_data"],
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
        # Could implement a simple tree printer here, but not required
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def generate_manifest(
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    output_path: Path,
    git_head_hash: str,
):
    """Generate MANIFEST.json with SHA256 for all tracked files."""
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head_hash,
        "file_count": len(tracked_files),
        "files": [],
    }
    
    for path in sorted(tracked_files, key=lambda p: str(p)):
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
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    output_path: Path,
):
    """Generate SKIPPED_FILES.txt with skip policies and skipped tracked files."""
    lines = []
    
    # Section: Skip policies
    lines.append("== SKIP_POLICIES ==")
    for pattern in EXCLUDED_DIR_PATTERNS:
        lines.append(f"DIRECTORY: {pattern}")
    lines.append(f"SIZE_LIMIT: >{MAX_FILE_SIZE} bytes")
    lines.append("BINARY_DETECT: NUL in first 8KB")
    
    # Section: Skipped tracked files
    lines.append("\n== SKIPPED_TRACKED_FILES ==")
    if skipped_map:
        for path, (reason, size) in sorted(skipped_map.items(), key=lambda x: str(x[0])):
            lines.append(f"{reason}\t{size}\t{path}")
    else:
        lines.append("(none)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")

def scan_grep(
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    patterns: List[str],
) -> Dict[str, List[Tuple[Path, int, str]]]:
    """
    Scan files for grep patterns.
    Returns dict: pattern -> list of (path, lineno, line_text)
    """
    results = {pattern: [] for pattern in patterns}
    
    for path in tracked_files:
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
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
) -> List[ImportRow]:
    """
    Parse Python files for imports using AST.
    Returns list of ImportRow.
    """
    rows = []
    
    for path in tracked_files:
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
    tracked_files: List[Path],
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
        targets_to_find = ["dashboard", "check", "test", "full-snapshot"]
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
    for path in tracked_files:
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
    
    # Check for legacy entrypoint risks
    risk_flags = []
    
    # Check if Makefile dashboard points to scripts/dev_dashboard.py
    if makefile_path.exists():
        content = makefile_path.read_text(encoding="utf-8", errors="replace")
        if "scripts/dev_dashboard.py" in content:
            risk_flags.append("LEGACY_ENTRYPOINT_RISK: Makefile references scripts/dev_dashboard.py")
    
    # Check if scripts/dev_dashboard.py exists
    if Path("scripts/dev_dashboard.py").exists():
        risk_flags.append("LEGACY_ENTRYPOINT_PRESENCE: scripts/dev_dashboard.py exists in repo")
    
    # Check if FishBroWFS_V2.control.app_nicegui.py exists
    if Path("src/FishBroWFS_V2/control/app_nicegui.py").exists():
        risk_flags.append("LEGACY_ENTRYPOINT_PRESENCE: src/FishBroWFS_V2/control/app_nicegui.py exists")
    
    if risk_flags:
        for flag in risk_flags:
            lines.append(f"- ⚠️ {flag}")
    else:
        lines.append("(no risk flags detected)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")


def generate_audit_config_references(
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    output_path: Path,
):
    """
    Generate AUDIT_CONFIG_REFERENCES.txt.
    Scan configs/**/*.yaml, configs/**/*.yml, configs/**/*.json.
    Extract any value under keys matching CONFIG_KEY_PATTERNS.
    """
    lines = []
    
    config_exts = {".yaml", ".yml", ".json"}
    config_files = [
        p for p in tracked_files
        if p.suffix in config_exts and str(p).startswith("configs/")
        and p not in skipped_map
    ]
    
    for config_file in sorted(config_files, key=lambda p: str(p)):
        try:
            content = config_file.read_text(encoding="utf-8", errors="replace")
            if config_file.suffix == ".json":
                data = json.loads(content)
            else:
                if not YAML_AVAILABLE:
                    lines.append(f"{config_file} → YAML_NOT_AVAILABLE (install pyyaml)")
                    continue
                data = yaml.safe_load(content)
        except Exception as e:
            lines.append(f"{config_file} → PARSE_ERROR → {e.__class__.__name__}")
            continue
        
        if not isinstance(data, dict):
            continue
        
        # Recursively find keys matching patterns
        def extract_matches(obj, prefix=""):
            matches = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    full_key = f"{prefix}.{key}" if prefix else key
                    # Check if key matches any pattern
                    if any(pattern in key for pattern in CONFIG_KEY_PATTERNS):
                        matches.append((full_key, value))
                    # Recurse
                    matches.extend(extract_matches(value, full_key))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    matches.extend(extract_matches(item, f"{prefix}[{i}]"))
            return matches
        
        matches = extract_matches(data)
        if matches:
            for key, value in matches:
                # Convert value to string, truncate if too long
                val_str = str(value)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                lines.append(f"{config_file} → {key} → {val_str}")
        else:
            lines.append(f"{config_file} → (no matching keys)")
    
    if not lines:
        lines.append("(no config files found)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")


def generate_audit_call_graph(
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    output_path: Path,
):
    """
    Generate AUDIT_CALL_GRAPH.txt.
    Grep for references to CALL_GRAPH_PATTERNS.
    Output: caller_file → referenced_target
    """
    lines = []
    
    for path in tracked_files:
        if path in skipped_map:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        
        for pattern in CALL_GRAPH_PATTERNS:
            if pattern in content:
                lines.append(f"{path} → {pattern}")
    
    if not lines:
        lines.append("(no references found)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")


def generate_audit_test_surface(
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    import_rows: List[ImportRow],
    output_path: Path,
):
    """
    Generate AUDIT_TEST_SURFACE.txt.
    List every test file, classified with imports_control, imports_gui,
    touches_outputs, touches_artifacts.
    """
    lines = []
    
    test_files = [p for p in tracked_files if "test" in str(p).lower() and p.suffix == ".py"]
    
    for test_file in sorted(test_files, key=lambda p: str(p)):
        if test_file in skipped_map:
            continue
        
        # Determine imports
        imports_control = False
        imports_gui = False
        for row in import_rows:
            if row.file == test_file:
                if "control" in row.module.lower():
                    imports_control = True
                if "gui" in row.module.lower() or "nicegui" in row.module.lower():
                    imports_gui = True
        
        # Determine touches outputs/artifacts via grep
        touches_outputs = False
        touches_artifacts = False
        try:
            content = test_file.read_text(encoding="utf-8", errors="replace")
            if "outputs/" in content:
                touches_outputs = True
            if "artifacts/" in content:
                touches_artifacts = True
        except Exception:
            pass
        
        lines.append(f"TEST_FILE {test_file}")
        lines.append(f"  imports_control: {'yes' if imports_control else 'no'}")
        lines.append(f"  imports_gui: {'yes' if imports_gui else 'no'}")
        lines.append(f"  touches_outputs: {'yes' if touches_outputs else 'no'}")
        lines.append(f"  touches_artifacts: {'yes' if touches_artifacts else 'no'}")
        lines.append("")
    
    if not lines:
        lines.append("(no test files found)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")


def generate_audit_runtime_mutations(
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    output_path: Path,
):
    """
    Generate AUDIT_RUNTIME_MUTATIONS.txt.
    Scan for runtime mutation ops defined in MUTATION_PATTERNS.
    Output: file:line → operation
    """
    lines = []
    
    for path in tracked_files:
        if path in skipped_map:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            lines_content = content.splitlines()
        except Exception:
            continue
        
        for i, line in enumerate(lines_content, 1):
            for pattern in MUTATION_PATTERNS:
                if re.search(pattern, line):
                    # Clean operation name
                    op_name = pattern.replace(r"\.", ".").replace(r"\(", "(").replace(r"\)", ")")
                    lines.append(f"{path}:{i} → {op_name}")
                    break  # only record first match per line
    
    if not lines:
        lines.append("(no mutation operations found)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")


def generate_audit_state_flow(
    tracked_files: List[Path],
    skipped_map: Dict[Path, Tuple[str, int]],
    import_rows: List[ImportRow],
    output_path: Path,
):
    """
    Generate AUDIT_STATE_FLOW.md.
    Auto-generate state flow declaration and list modules per layer.
    """
    lines = []
    
    lines.append("# Architectural State Flow")
    lines.append("")
    lines.append("## Declared Flow")
    lines.append("")
    lines.append("```")
    lines.append("UI → IntentBridge → ActionQueue → Worker → Artifacts")
    lines.append("CLI → Control API → ActionQueue")
    lines.append("Tests → Direct Function Calls (NO IO)")
    lines.append("Viewer → Read-only Artifacts")
    lines.append("```")
    lines.append("")
    
    # Collect modules per layer based on import patterns
    ui_modules = set()
    control_modules = set()
    worker_modules = set()
    test_modules = set()
    viewer_modules = set()
    
    for row in import_rows:
        module = row.module
        if "gui" in module or "nicegui" in module or "ui" in module:
            ui_modules.add(module)
        elif "control" in module:
            control_modules.add(module)
        elif "worker" in module or "runner" in module:
            worker_modules.add(module)
        elif "test" in module:
            test_modules.add(module)
        elif "viewer" in module:
            viewer_modules.add(module)
    
    lines.append("## Observed Modules per Layer")
    lines.append("")
    lines.append("### UI Layer")
    lines.append(", ".join(sorted(ui_modules)) if ui_modules else "(none)")
    lines.append("")
    lines.append("### Control Layer")
    lines.append(", ".join(sorted(control_modules)) if control_modules else "(none)")
    lines.append("")
    lines.append("### Worker Layer")
    lines.append(", ".join(sorted(worker_modules)) if worker_modules else "(none)")
    lines.append("")
    lines.append("### Test Layer")
    lines.append(", ".join(sorted(test_modules)) if test_modules else "(none)")
    lines.append("")
    lines.append("### Viewer Layer")
    lines.append(", ".join(sorted(viewer_modules)) if viewer_modules else "(none)")
    lines.append("")
    
    # Detect forbidden cross-layer imports
    lines.append("## Forbidden Cross‑Layer Imports Detected")
    lines.append("")
    forbidden = []
    for row in import_rows:
        src_layer = None
        dst_layer = None
        # Determine source file layer
        src_file = str(row.file)
        if "test" in src_file:
            src_layer = "test"
        elif "gui" in src_file or "ui" in src_file:
            src_layer = "ui"
        elif "control" in src_file:
            src_layer = "control"
        elif "worker" in src_file or "runner" in src_file:
            src_layer = "worker"
        elif "viewer" in src_file:
            src_layer = "viewer"
        
        # Determine destination module layer
        dst_module = row.module
        if "gui" in dst_module or "nicegui" in dst_module or "ui" in dst_module:
            dst_layer = "ui"
        elif "control" in dst_module:
            dst_layer = "control"
        elif "worker" in dst_module or "runner" in dst_module:
            dst_layer = "worker"
        elif "test" in dst_module:
            dst_layer = "test"
        elif "viewer" in dst_module:
            dst_layer = "viewer"
        
        if src_layer and dst_layer and src_layer != dst_layer:
            # Check if this is allowed (some cross-layer imports are okay)
            # For simplicity, we flag all cross-layer imports
            forbidden.append(f"{src_file}:{row.lineno} {src_layer} → {dst_layer} ({row.module})")
    
    if forbidden:
        for item in forbidden[:20]:  # limit output
            lines.append(f"- {item}")
        if len(forbidden) > 20:
            lines.append(f"- ... and {len(forbidden) - 20} more")
    else:
        lines.append("(none)")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------------------------
# Main execution
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate full repository forensic snapshot (Carpet Audit Kit)."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output directory if it exists",
    )
    args = parser.parse_args()
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Clean output directory if --force
    if args.force:
        for file in OUTPUT_DIR.glob("*"):
            file.unlink()
    
    print("Generating forensic snapshot...")
    print(f"Output directory: {OUTPUT_DIR}")
    
    # Get git information
    git_head_hash = git_head()
    print(f"Git HEAD: {git_head_hash[:8]}")
    
    # Get tracked files
    tracked = tracked_files()
    print(f"Tracked files: {len(tracked)}")
    
    # Determine which tracked files to skip for content scanning
    skipped_map = {}  # path -> (reason, size)
    for path in tracked:
        if not path.exists():
            continue
        size = file_size(path)
        skip, reason = should_skip_file(path, size)
        if skip:
            skipped_map[path] = (reason, size)
    
    print(f"Skipped for content scanning: {len(skipped_map)} files")
    
    # Generate artifacts
    print("Generating REPO_TREE.txt...")
    generate_repo_tree(tracked, OUTPUT_DIR / "REPO_TREE.txt")
    
    print("Generating MANIFEST.json...")
    generate_manifest(tracked, skipped_map, OUTPUT_DIR / "MANIFEST.json", git_head_hash)
    
    print("Generating SKIPPED_FILES.txt...")
    generate_skipped_files(tracked, skipped_map, OUTPUT_DIR / "SKIPPED_FILES.txt")
    
    print("Scanning for grep patterns...")
    grep_results = scan_grep(tracked, skipped_map, GREP_PATTERNS)
    print("Generating AUDIT_GREP.txt...")
    generate_audit_grep(grep_results, OUTPUT_DIR / "AUDIT_GREP.txt")
    
    print("Scanning Python imports...")
    import_rows = scan_imports_py(tracked, skipped_map)
    print("Generating AUDIT_IMPORTS.csv...")
    generate_audit_imports(import_rows, OUTPUT_DIR / "AUDIT_IMPORTS.csv")
    
    print("Generating AUDIT_ENTRYPOINTS.md...")
    generate_audit_entrypoints(tracked, git_head_hash, OUTPUT_DIR / "AUDIT_ENTRYPOINTS.md")
    
    # New artifact generators
    print("Generating AUDIT_CONFIG_REFERENCES.txt...")
    generate_audit_config_references(tracked, skipped_map, OUTPUT_DIR / "AUDIT_CONFIG_REFERENCES.txt")
    
    print("Generating AUDIT_CALL_GRAPH.txt...")
    generate_audit_call_graph(tracked, skipped_map, OUTPUT_DIR / "AUDIT_CALL_GRAPH.txt")
    
    print("Generating AUDIT_TEST_SURFACE.txt...")
    generate_audit_test_surface(tracked, skipped_map, import_rows, OUTPUT_DIR / "AUDIT_TEST_SURFACE.txt")
    
    print("Generating AUDIT_RUNTIME_MUTATIONS.txt...")
    generate_audit_runtime_mutations(tracked, skipped_map, OUTPUT_DIR / "AUDIT_RUNTIME_MUTATIONS.txt")
    
    print("Generating AUDIT_STATE_FLOW.md...")
    generate_audit_state_flow(tracked, skipped_map, import_rows, OUTPUT_DIR / "AUDIT_STATE_FLOW.md")
    
    # Verify all required artifacts exist
    required_files = [
        "REPO_TREE.txt",
        "MANIFEST.json",
        "SKIPPED_FILES.txt",
        "AUDIT_GREP.txt",
        "AUDIT_IMPORTS.csv",
        "AUDIT_ENTRYPOINTS.md",
        "AUDIT_CONFIG_REFERENCES.txt",
        "AUDIT_CALL_GRAPH.txt",
        "AUDIT_TEST_SURFACE.txt",
        "AUDIT_RUNTIME_MUTATIONS.txt",
        "AUDIT_STATE_FLOW.md",
    ]
    
    missing = []
    for filename in required_files:
        path = OUTPUT_DIR / filename
        if not path.exists():
            missing.append(filename)
        elif path.stat().st_size == 0:
            print(f"Warning: {filename} is empty")
    
    if missing:
        print(f"ERROR: Missing required artifacts: {missing}", file=sys.stderr)
        sys.exit(2)
    
    # Print summary
    print("\n" + "=" * 60)
    print("FORENSIC SNAPSHOT GENERATION COMPLETE")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Tracked files scanned: {len(tracked)}")
    print(f"Skipped for content (binary/large): {len(skipped_map)}")
    
    # Grep match counts
    print("\nGrep pattern matches:")
    for pattern in GREP_PATTERNS:
        matches = grep_results[pattern]
        total = len(matches)
        truncated = total > MAX_MATCHES_PER_PATTERN
        display = f"{total}" + (" (truncated)" if truncated else "")
        print(f"  {pattern[:40]:40} : {display}")
    
    # Python files parsed
    py_files = [p for p in tracked if p.suffix == ".py" and p not in skipped_map]
    print(f"Python files parsed by AST: {len(py_files)}")
    
    # Total size
    total_size = sum(f.stat().st_size for f in OUTPUT_DIR.glob("*") if f.is_file())
    print(f"Total artifact size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
    if total_size > 5 * 1024 * 1024:
        print(f"WARNING: Total size exceeds 5MB target")
    
    print("\nArtifacts generated:")
    for filename in required_files:
        path = OUTPUT_DIR / filename
        size = path.stat().st_size
        print(f"  {filename:25} : {size:,} bytes")
    
    print("\nTo view artifacts:")
    print(f"  cat {OUTPUT_DIR}/REPO_TREE.txt | head -20")
    print(f"  head -20 {OUTPUT_DIR}/AUDIT_GREP.txt")


if __name__ == "__main__":
    main()

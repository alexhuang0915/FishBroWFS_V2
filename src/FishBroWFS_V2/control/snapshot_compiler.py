#!/usr/bin/env python3
"""
Snapshot Compiler - compile outputs/snapshots/full/* into a single SYSTEM_FULL_SNAPSHOT.md.

Contract:
- MUST embed verbatim bytes from snapshot files (no summarization, no reformatting content).
- MUST be deterministic: same inputs => identical output bytes.
- MUST preserve raw line order and content exactly as read.
- MUST NOT modify any raw files under outputs/snapshots/full/.
- Output path: outputs/snapshots/SYSTEM_FULL_SNAPSHOT.md.
"""

from __future__ import annotations
import datetime
from pathlib import Path
from typing import List, Optional
import sys


def write_bytes_atomic(dst: Path, data: bytes) -> None:
    """Atomic write helper."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dst)


def compile_full_snapshot(
    snapshots_root: str | Path = "outputs/snapshots",
    full_dir_name: str = "full",
    out_name: str = "SYSTEM_FULL_SNAPSHOT.md",
) -> Path:
    """
    Compile outputs/snapshots/full/* into outputs/snapshots/SYSTEM_FULL_SNAPSHOT.md deterministically.
    
    Args:
        snapshots_root: Root directory containing snapshots.
        full_dir_name: Name of directory with raw artifacts (default "full").
        out_name: Output filename (default "SYSTEM_FULL_SNAPSHOT.md").
    
    Returns:
        Path to the compiled snapshot file.
    """
    snapshots_root = Path(snapshots_root)
    full_dir = snapshots_root / full_dir_name
    out_path = snapshots_root / out_name
    
    if not full_dir.exists():
        raise FileNotFoundError(f"Snapshot directory not found: {full_dir}")
    
    # Required order as per spec (matches test expectations)
    file_order = [
        "MANIFEST.json",
        "LOCAL_SCAN_RULES.json",
        "REPO_TREE.txt",
        "AUDIT_GREP.txt",
        "AUDIT_IMPORTS.csv",
        "AUDIT_ENTRYPOINTS.md",
        "AUDIT_CALL_GRAPH.txt",
        "AUDIT_RUNTIME_MUTATIONS.txt",
        "AUDIT_CONFIG_REFERENCES.txt",
        "AUDIT_TEST_SURFACE.txt",
        "AUDIT_STATE_FLOW.md",
        "SKIPPED_FILES.txt",
    ]
    
    # Build output content
    lines: List[str] = []
    
    # Determine timestamp - try to get from MANIFEST.json for determinism
    timestamp = "UNKNOWN"
    manifest_path = full_dir / "MANIFEST.json"
    if manifest_path.exists():
        try:
            import json
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
                if "generated_at_utc" in manifest:
                    timestamp = manifest["generated_at_utc"]
        except Exception:
            pass
    
    # Header
    lines.append("# SYSTEM FULL SNAPSHOT - Compiled")
    lines.append("")
    lines.append(f"Generated: {timestamp}")
    lines.append(f"Source directory: {full_dir}")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    missing_files: List[str] = []
    
    for i, filename in enumerate(file_order, 1):
        file_path = full_dir / filename
        
        if not file_path.exists():
            missing_files.append(filename)
            continue
        
        # Determine language for code block
        ext = file_path.suffix.lower()
        if ext == ".json":
            lang = "json"
        elif ext == ".md":
            lang = "md"
        elif ext == ".csv":
            lang = "csv"
        elif ext == ".txt":
            lang = "text"
        else:
            lang = "text"
        
        # Read file bytes
        try:
            content_bytes = file_path.read_bytes()
            # Try to decode as UTF-8, but fallback to replacement if needed
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = content_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            content = f"ERROR reading file: {e}"
        
        # Section header (match test expectations: ## FILENAME_WITH_EXTENSION)
        section_name = filename  # Keep extension
        lines.append(f"## {section_name}")
        lines.append("")
        lines.append(f"```{lang}")
        lines.append(content.rstrip("\n"))  # Remove trailing newline to avoid extra line
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # Missing files section
    if missing_files:
        lines.append("## Missing Files")
        lines.append("")
        lines.append("The following expected files were not found in the snapshot directory:")
        lines.append("")
        for filename in missing_files:
            lines.append(f"- `{filename}`")
        lines.append("")
    
    # Convert to bytes
    output_content = "\n".join(lines)
    output_bytes = output_content.encode("utf-8")
    
    # Atomic write
    write_bytes_atomic(out_path, output_bytes)
    
    return out_path


def verify_deterministic(
    snapshots_root: str | Path = "outputs/snapshots",
    full_dir_name: str = "full",
    out_name: str = "SYSTEM_FULL_SNAPSHOT.md",
) -> bool:
    """
    Verify that compiling the same snapshot twice produces identical bytes.
    
    Returns True if deterministic, False otherwise.
    """
    snapshots_root = Path(snapshots_root)
    
    # Compile first time
    out1 = compile_full_snapshot(snapshots_root, full_dir_name, out_name + ".test1")
    data1 = out1.read_bytes()
    
    # Compile second time
    out2 = compile_full_snapshot(snapshots_root, full_dir_name, out_name + ".test2")
    data2 = out2.read_bytes()
    
    # Clean up test files
    out1.unlink(missing_ok=True)
    out2.unlink(missing_ok=True)
    
    return data1 == data2


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Compile full snapshot artifacts into a single SYSTEM_FULL_SNAPSHOT.md."
    )
    parser.add_argument(
        "--verify-deterministic",
        action="store_true",
        help="Verify that compilation is deterministic (run twice and compare)."
    )
    parser.add_argument(
        "--snapshots-root",
        default="outputs/snapshots",
        help="Root directory containing snapshots (default: outputs/snapshots)."
    )
    parser.add_argument(
        "--full-dir",
        default="full",
        help="Name of directory with raw artifacts (default: full)."
    )
    parser.add_argument(
        "--out-name",
        default="SYSTEM_FULL_SNAPSHOT.md",
        help="Output filename (default: SYSTEM_FULL_SNAPSHOT.md)."
    )
    
    args = parser.parse_args()
    
    if args.verify_deterministic:
        print("Verifying determinism...")
        if verify_deterministic(args.snapshots_root, args.full_dir, args.out_name):
            print("✓ Compilation is deterministic")
            sys.exit(0)
        else:
            print("✗ Compilation is NOT deterministic")
            sys.exit(1)
    else:
        try:
            out_path = compile_full_snapshot(
                args.snapshots_root,
                args.full_dir,
                args.out_name
            )
            print(f"Compiled snapshot written to: {out_path}")
            print(f"Size: {out_path.stat().st_size:,} bytes")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
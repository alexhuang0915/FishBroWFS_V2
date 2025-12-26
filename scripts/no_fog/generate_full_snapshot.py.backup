#!/usr/bin/env python3
"""
Generate a FULL high-resolution repository snapshot.

Mission: Eliminate "fog" by generating a FULL high-resolution repository snapshot that is:
- complete for whitelisted text/code/config files
- deterministic (stable ordering)
- chunked (upload-friendly)
- auditable (sha256 per file + per chunk)
- safe (hard excludes + best-effort secret redaction)

Output directory: SYSTEM_FULL_SNAPSHOT/
  - REPO_TREE.txt
  - MANIFEST.json
  - SKIPPED_FILES.txt
  - SNAPSHOT_0001.md, SNAPSHOT_0002.md, ...
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any, BinaryIO

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# Hard excludes: directories
EXCLUDE_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".vscode",
    ".idea",
    "node_modules",
    "dist",
    "build",
    "htmlcov",
    "logs",
    "temp",
    "site-packages",
    "venv",
    "env",
    ".venv",
    "outputs",
    "FishBroData",
    "legacy",
}

# Hard excludes: exact filenames
EXCLUDE_FILES_EXACT: Set[str] = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
}

# Hard excludes: glob patterns (extensions)
EXCLUDE_GLOBS: List[str] = [
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.pkl",
    "*.db",
    "*.sqlite*",
    "*.parquet",
    "*.feather",
    "*.csv",
    "*.tsv",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.svg",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.tar.gz",
    "*.7z",
    "*.gz",
    "*.dll",
    "*.exe",
    "*.bin",
    "package-lock.json",
    "yarn.lock",
]

# Include full content ONLY for:
INCLUDE_EXTENSIONS: Set[str] = {
    ".py",
    ".js",
    ".ts",
    ".vue",
    ".css",
    ".html",
    ".sql",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".md",
    ".txt",
}

# Include exact filenames (regardless of extension)
INCLUDE_FILENAMES: Set[str] = {
    "Makefile",
    "Dockerfile",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
}

# Safety valve: max file size for content inclusion (bytes)
MAX_CONTENT_SIZE = 300 * 1024  # 300 KB

# Chunk size limit (characters)
CHUNK_SIZE_LIMIT = 700_000

# Secret patterns for redaction
SECRET_PATTERNS = [
    r"OPENAI_API_KEY",
    r"API_KEY",
    r"SECRET",
    r"TOKEN",
    r"PASSWORD",
]

# ------------------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------------------

def compute_sha256(data: bytes) -> str:
    """Compute SHA256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()

def is_binary_file(file_path: Path) -> bool:
    """
    Detect if file is binary by checking for null bytes in first 4KB.
    Returns True if binary, False if text.
    """
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(4096)
            return b"\x00" in chunk
    except Exception:
        # If we can't read, treat as binary to skip
        return True

def should_include_file(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Determine if a file should be included (content or metadata only).
    Returns (include_content, reason_if_skipped)
    """
    # Check exact filename exclusion
    if file_path.name in EXCLUDE_FILES_EXACT:
        return False, "exact filename excluded"

    # Check glob patterns
    for pattern in EXCLUDE_GLOBS:
        if file_path.match(pattern):
            return False, f"glob pattern {pattern}"

    # Check if in whitelist
    if file_path.suffix in INCLUDE_EXTENSIONS:
        pass  # OK
    elif file_path.name in INCLUDE_FILENAMES:
        pass  # OK
    else:
        return False, "extension/filename not in whitelist"

    # Safety valve: file size
    try:
        size = file_path.stat().st_size
        if size > MAX_CONTENT_SIZE:
            return False, f"size {size} > {MAX_CONTENT_SIZE}"
    except OSError:
        return False, "cannot stat"

    # Safety valve: binary detection
    if is_binary_file(file_path):
        return False, "binary detected"

    return True, None

def redact_line(line: str) -> Tuple[str, bool]:
    """
    Redact secrets in a line.
    Returns (redacted_line, was_redacted).
    """
    original = line
    redacted = False

    # Only redact lines containing '=' or ':' (likely assignments)
    if "=" in line or ":" in line:
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                # Simple redaction: mask everything after '=' or ':' on that line
                # This is best-effort, not perfect
                if "=" in line:
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        line = parts[0] + "=[REDACTED]"
                        redacted = True
                        break
                elif ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        line = parts[0] + ":[REDACTED]"
                        redacted = True
                        break

    return line, redacted

def redact_content(content: str) -> Tuple[str, bool]:
    """
    Redact secrets in file content.
    Returns (redacted_content, any_redacted).
    """
    lines = content.splitlines(keepends=True)
    any_redacted = False
    redacted_lines = []
    for line in lines:
        redacted_line, redacted = redact_line(line)
        redacted_lines.append(redacted_line)
        if redacted:
            any_redacted = True
    return "".join(redacted_lines), any_redacted

# ------------------------------------------------------------------------------
# Main snapshot generator
# ------------------------------------------------------------------------------

class SnapshotGenerator:
    def __init__(self, repo_root: Path, output_dir: Path):
        self.repo_root = repo_root.resolve()
        self.output_dir = output_dir.resolve()
        self.manifest: Dict[str, Any] = {
            "generated_at": None,
            "repo_root": str(self.repo_root),
            "chunks": [],
            "files": [],
            "skipped": [],
        }
        self.skipped_files: List[Dict[str, Any]] = []
        self.included_files: List[Dict[str, Any]] = []
        self.chunks: List[Dict[str, Any]] = []
        self.current_chunk: List[str] = []
        self.current_chunk_size = 0
        self.chunk_index = 1

    def ensure_output_dir(self):
        """Create output directory if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def walk_repo(self) -> List[Path]:
        """
        Walk repository deterministically (sorted order).
        Returns list of all file paths relative to repo_root.
        """
        all_files = []
        for root, dirs, files in os.walk(self.repo_root, topdown=True):
            # Sort directories and files for deterministic order
            dirs[:] = sorted(dirs)
            files = sorted(files)

            # Exclude directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            root_path = Path(root)
            for file in files:
                file_path = root_path / file
                rel_path = file_path.relative_to(self.repo_root)
                all_files.append(rel_path)
        return all_files

    def process_file(self, rel_path: Path) -> Optional[Dict[str, Any]]:
        """
        Process a single file.
        Returns file metadata dict if included, None if skipped.
        """
        abs_path = self.repo_root / rel_path

        # Check if should include content
        include_content, skip_reason = should_include_file(abs_path)

        # Read original bytes for hash
        try:
            original_bytes = abs_path.read_bytes()
        except Exception as e:
            # If we can't read, skip
            self.skipped_files.append({
                "path": str(rel_path),
                "reason": f"read error: {e}",
            })
            return None

        # Compute SHA256 of original source bytes (pre-redaction)
        sha256 = compute_sha256(original_bytes)
        size = len(original_bytes)

        file_meta = {
            "path": str(rel_path),
            "sha256": sha256,
            "size": size,
            "include_content": include_content,
            "redacted": False,
        }

        if not include_content:
            # Record as skipped
            self.skipped_files.append({
                "path": str(rel_path),
                "reason": skip_reason,
                "sha256": sha256,
                "size": size,
            })
            return None

        # Decode as text (best-effort)
        try:
            content = original_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # If not UTF-8, treat as binary and skip content
            self.skipped_files.append({
                "path": str(rel_path),
                "reason": "not UTF-8 text",
                "sha256": sha256,
                "size": size,
            })
            return None

        # Apply redaction
        redacted_content, was_redacted = redact_content(content)
        file_meta["redacted"] = was_redacted

        # Add to chunk
        self.add_to_chunk(rel_path, sha256, size, was_redacted, redacted_content)

        # Record file metadata
        self.included_files.append(file_meta)
        return file_meta

    def add_to_chunk(self, rel_path: Path, sha256: str, size: int,
                     redacted: bool, content: str):
        """
        Add file content to current chunk. Start new chunk if needed.
        """
        # Format file block
        block = f"""FILE {rel_path}
sha256(source_bytes) = {sha256}
bytes = {size}
redacted = {redacted}
{'-' * 80}
{content}
{'-' * 80}

"""
        block_size = len(block)

        # If adding this block would exceed chunk limit, flush current chunk
        if self.current_chunk_size + block_size > CHUNK_SIZE_LIMIT and self.current_chunk:
            self.flush_chunk()

        # Add block to current chunk
        self.current_chunk.append(block)
        self.current_chunk_size += block_size

    def flush_chunk(self):
        """Write current chunk to file and reset."""
        if not self.current_chunk:
            return

        # Create chunk filename
        chunk_filename = f"SNAPSHOT_{self.chunk_index:04d}.md"
        chunk_path = self.output_dir / chunk_filename

        # Build chunk content
        chunk_content = []
        if self.chunk_index == 1:
            # First chunk includes REPO_TREE section
            chunk_content.append("# REPOSITORY SNAPSHOT\n\n")
            chunk_content.append("## Repository Tree\n")
            chunk_content.append("```\n")
            # We'll add tree later after we have all files
            chunk_content.append("(Repository tree will be generated separately)\n")
            chunk_content.append("```\n\n")
            chunk_content.append("## File Contents\n\n")

        chunk_content.extend(self.current_chunk)

        # Write chunk
        chunk_content_str = "".join(chunk_content)
        chunk_path.write_text(chunk_content_str, encoding="utf-8")

        # Compute chunk hash
        chunk_bytes = chunk_content_str.encode("utf-8")
        chunk_sha256 = compute_sha256(chunk_bytes)

        # Record chunk metadata
        chunk_meta = {
            "index": self.chunk_index,
            "filename": chunk_filename,
            "sha256": chunk_sha256,
            "size": len(chunk_bytes),
            "file_count": len(self.current_chunk),
        }
        self.chunks.append(chunk_meta)

        # Reset for next chunk
        self.current_chunk = []
        self.current_chunk_size = 0
        self.chunk_index += 1

    def generate_repo_tree(self) -> str:
        """Generate REPO_TREE.txt content."""
        lines = []
        for file_meta in self.included_files:
            path = file_meta["path"]
            size = file_meta["size"]
            sha256_short = file_meta["sha256"][:8]
            lines.append(f"{path} ({size} bytes, sha256:{sha256_short})")

        for skipped in self.skipped_files:
            path = skipped["path"]
            reason = skipped["reason"]
            lines.append(f"{path} [SKIPPED: {reason}]")

        lines.sort()  # Deterministic order
        return "\n".join(lines)

    def generate_manifest(self):
        """Generate MANIFEST.json."""
        self.manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
        self.manifest["chunks"] = self.chunks
        self.manifest["files"] = self.included_files
        self.manifest["skipped"] = self.skipped_files

        manifest_path = self.output_dir / "MANIFEST.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2, sort_keys=True)

    def generate_skipped_list(self):
        """Generate SKIPPED_FILES.txt."""
        skipped_path = self.output_dir / "SKIPPED_FILES.txt"
        lines = []
        for skipped in self.skipped_files:
            lines.append(f"{skipped['path']}: {skipped['reason']}")
        skipped_path.write_text("\n".join(sorted(lines)), encoding="utf-8")

    def run(self):
        """Main execution."""
        print(f"Generating snapshot of {self.repo_root}")
        print(f"Output directory: {self.output_dir}")
        self.ensure_output_dir()

        # Walk repository
        print("Walking repository...")
        all_files = self.walk_repo()
        print(f"Found {len(all_files)} total files")

        # Process each file
        for i, rel_path in enumerate(all_files):
            if i % 100 == 0:
                print(f"Processed {i}/{len(all_files)} files...")
            self.process_file(rel_path)

        # Flush any remaining chunk
        self.flush_chunk()

        # Generate REPO_TREE.txt
        print("Generating REPO_TREE.txt...")
        repo_tree = self.generate_repo_tree()
        (self.output_dir / "REPO_TREE.txt").write_text(repo_tree, encoding="utf-8")

        # Update first chunk with actual tree
        if self.chunks:
            first_chunk_path = self.output_dir / "SNAPSHOT_0001.md"
            if first_chunk_path.exists():
                content = first_chunk_path.read_text(encoding="utf-8")
                # Replace placeholder with actual tree
                tree_section = f"# REPOSITORY SNAPSHOT\n\n## Repository Tree\n```\n{repo_tree}\n```\n\n## File Contents\n\n"
                # Find where the placeholder ends
                if "(Repository tree will be generated separately)" in content:
                    content = content.replace(
                        "# REPOSITORY SNAPSHOT\n\n## Repository Tree\n```\n(Repository tree will be generated separately)\n```\n\n## File Contents\n\n",
                        tree_section
                    )
                    first_chunk_path.write_text(content, encoding="utf-8")
                    # Recompute hash
                    chunk_bytes = content.encode("utf-8")
                    chunk_sha256 = compute_sha256(chunk_bytes)
                    self.chunks[0]["sha256"] = chunk_sha256
                    self.chunks[0]["size"] = len(chunk_bytes)

        # Generate manifest and skipped list
        print("Generating MANIFEST.json and SKIPPED_FILES.txt...")
        self.generate_manifest()
        self.generate_skipped_list()

        # Print summary
        print("\n" + "=" * 60)
        print("SNAPSHOT GENERATION COMPLETE")
        print("=" * 60)
        print(f"Output directory: {self.output_dir}")
        print(f"Chunks generated: {len(self.chunks)}")
        print(f"Files included: {len(self.included_files)}")
        print(f"Files skipped: {len(self.skipped_files)}")
        print(f"Manifest: {self.output_dir / 'MANIFEST.json'}")
        print(f"Repository tree: {self.output_dir / 'REPO_TREE.txt'}")
        print(f"Skipped files list: {self.output_dir / 'SKIPPED_FILES.txt'}")

# ------------------------------------------------------------------------------
# Command-line interface
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a full repository snapshot for audit/backup."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: current directory)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("SYSTEM_FULL_SNAPSHOT"),
        help="Output directory (default: SYSTEM_FULL_SNAPSHOT)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output directory if it exists",
    )
    args = parser.parse_args()

    # Validate repo root
    if not args.repo_root.exists():
        print(f"Error: Repository root does not exist: {args.repo_root}")
        sys.exit(1)

    # Check output directory
    if args.output_dir.exists():
        if args.force:
            print(f"Warning: Overwriting existing output directory: {args.output_dir}")
            import shutil
            shutil.rmtree(args.output_dir)
        else:
            print(f"Error: Output directory already exists: {args.output_dir}")
            print("Use --force to overwrite.")
            sys.exit(1)

    # Create generator and run
    generator = SnapshotGenerator(args.repo_root, args.output_dir)
    generator.run()


if __name__ == "__main__":
    main()
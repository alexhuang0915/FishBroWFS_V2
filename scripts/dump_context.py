#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FishBro Snapshot Generator vNext (JSONL schema v2) - Balanced Parts Edition
File: scripts/dump_context.py

Goals:
- Outputs exactly 10 parts: part_00.jsonl .. part_09.jsonl
- Balances content across parts automatically (no "all in part_00")
- Never emits "file_truncated"
- Fully emits included text files via chunking (chunks may span parts)
- outputs/* big/binary -> metadata-only (file_skipped)
- Writes a single manifest at the end (part_09)

Usage (WSL zsh):
  cd /home/fishbro/FishBroWFS_V2
  make snapshot

Or direct:
  PYTHONPATH=src .venv/bin/python scripts/dump_context.py --repo-root .

Notes:
- Text files are read as UTF-8 with errors='replace' to avoid crashes.
- Newlines in emitted "content" lines are without trailing newline.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


# -----------------------------
# Policy / Filtering
# -----------------------------

DEFAULT_ALWAYS_INCLUDE = [
    "src",
    "tests",
    "scripts",
    "Makefile",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "README.md",
    "README.txt",
    "docs",
]

DEFAULT_ALWAYS_SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".idea",
    ".vscode",
    "dist",
    "build",
}

# Do not snapshot SNAPSHOT itself (avoid recursion).
# outputs are handled separately (metadata-only for big/binary).
OUTPUTS_ROOTS = {"outputs", "SNAPSHOT"}

BINARY_EXTS = {
    ".db", ".sqlite", ".sqlite3",
    ".parquet", ".feather",
    ".zip", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".pdf",
    ".mp4", ".mov", ".avi",
    ".bin", ".so", ".dll", ".exe",
    ".pkl", ".pickle",
}

DEFAULT_OUTPUTS_MAX_BYTES_FOR_CONTENT = 2_000_000  # 2MB

# Balanced strategy knobs
DEFAULT_BALANCE_BUFFER_RATIO = 1.08   # 8% buffer to account for estimation error
MIN_TARGET_BYTES_PER_PART = 500_000   # never set target too tiny (avoid too many part rotations)


# -----------------------------
# JSONL Writers
# -----------------------------

@dataclass
class PartWriter:
    path: Path
    fp: any
    bytes_written: int = 0
    lines_written: int = 0

    def write_obj(self, obj: dict) -> None:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
        b = s.encode("utf-8")
        self.fp.write(b)
        self.bytes_written += len(b)
        self.lines_written += 1


@dataclass
class FileRecord:
    path: str
    kind: str  # "text" or "binary"
    encoding: str
    newline: str
    bytes: int
    sha256: str
    total_lines: Optional[int]
    chunk_count: Optional[int]
    complete: bool
    skipped: bool
    skip_reason: Optional[str] = None


@dataclass
class RunStats:
    total_text_bytes: int = 0
    total_chunks: int = 0
    files_total: int = 0
    files_complete: int = 0
    files_skipped: int = 0
    skipped_by_reason: Dict[str, int] = dataclasses.field(default_factory=dict)
    violations: List[str] = dataclasses.field(default_factory=list)


# -----------------------------
# Utilities
# -----------------------------

def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_run_id() -> str:
    return time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_probably_binary(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in BINARY_EXTS:
        return True
    try:
        with path.open("rb") as f:
            sample = f.read(8192)
        if b"\x00" in sample:
            return True
    except Exception:
        return True
    return False


def normalize_relpath(repo_root: Path, p: Path) -> str:
    return str(p.relative_to(repo_root)).replace("\\", "/")


def should_skip_path(relpath: str) -> Tuple[bool, Optional[str]]:
    """
    Returns (skip, reason).
    Reasons:
      - "cache": cache/venv/git/node_modules/__pycache__/etc.
      - "snapshot_output": avoid snapshotting SNAPSHOT/ itself
    """
    parts = relpath.split("/")
    for seg in parts:
        if seg in DEFAULT_ALWAYS_SKIP_DIRS:
            return True, "cache"
    if parts and parts[0] == "SNAPSHOT":
        return True, "snapshot_output"
    return False, None


def iter_repo_files(repo_root: Path, include_roots: List[str]) -> Iterator[Path]:
    for root in include_roots:
        rp = (repo_root / root)
        if not rp.exists():
            continue
        if rp.is_file():
            yield rp
            continue
        for p in rp.rglob("*"):
            if p.is_file():
                yield p


def stable_sort_paths(paths: Iterable[Path]) -> List[Path]:
    return sorted(paths, key=lambda p: str(p).lower())


def read_text_lines(path: Path) -> Tuple[List[str], str, str, bytes]:
    raw = path.read_bytes()
    newline = "lf"
    if b"\r\n" in raw:
        newline = "crlf"
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines, "utf-8", newline, raw


def jsonl_len(obj: dict) -> int:
    """Exact bytes length of one JSONL line."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    return len(s.encode("utf-8"))


# -----------------------------
# Chunk planning (deterministic)
# -----------------------------

@dataclass
class PlannedTextFile:
    relpath: str
    bytes_size: int
    sha256: str
    encoding: str
    newline: str
    total_lines: int
    chunks: List[Tuple[int, int, List[str]]]  # (line_start, line_end, content)
    estimated_emit_bytes: int  # header+chunks+footer jsonl bytes


@dataclass
class PlannedSkipFile:
    relpath: str
    reason: str
    bytes_size: int
    sha256: str
    note: str
    estimated_emit_bytes: int  # file_skipped jsonl bytes


def plan_text_file(
    repo_root: Path,
    abs_path: Path,
    relpath: str,
    chunk_max_lines: int,
    chunk_max_bytes: int,
) -> PlannedTextFile:
    lines, encoding, newline, raw = read_text_lines(abs_path)
    sha = sha256_bytes(raw)
    total_lines = len(lines)
    bytes_size = len(raw)

    chunks: List[Tuple[int, int, List[str]]] = []
    idx = 0
    start = 1
    while idx < total_lines:
        take_lines = min(chunk_max_lines, total_lines - idx)
        candidate = lines[idx: idx + take_lines]

        # Enforce chunk_max_bytes (ensure at least 1 line)
        while True:
            payload = json.dumps(candidate, ensure_ascii=False).encode("utf-8")
            if len(payload) <= chunk_max_bytes or len(candidate) == 1:
                break
            candidate = candidate[:-1]

        end = start + len(candidate) - 1
        chunks.append((start, end, candidate))
        idx += len(candidate)
        start = end + 1

    chunk_count = len(chunks)

    header_obj = {
        "type": "file_header",
        "path": relpath,
        "kind": "text",
        "encoding": encoding,
        "newline": newline,
        "bytes": bytes_size,
        "sha256": sha,
        "total_lines": total_lines,
        "chunk_count": chunk_count,
    }
    footer_obj = {
        "type": "file_footer",
        "path": relpath,
        "complete": True,
        "emitted_chunks": chunk_count,
    }

    est = jsonl_len(header_obj)
    for i, (ls, le, content) in enumerate(chunks):
        est += jsonl_len({
            "type": "file_chunk",
            "path": relpath,
            "chunk_index": i,
            "line_start": ls,
            "line_end": le,
            "content": content,
        })
    est += jsonl_len(footer_obj)

    return PlannedTextFile(
        relpath=relpath,
        bytes_size=bytes_size,
        sha256=sha,
        encoding=encoding,
        newline=newline,
        total_lines=total_lines,
        chunks=chunks,
        estimated_emit_bytes=est,
    )


def plan_skip_file(relpath: str, reason: str, bytes_size: int, sha256: str, note: str) -> PlannedSkipFile:
    obj = {
        "type": "file_skipped",
        "path": relpath,
        "reason": reason,
        "bytes": bytes_size,
        "sha256": sha256,
        "note": note,
    }
    return PlannedSkipFile(
        relpath=relpath,
        reason=reason,
        bytes_size=bytes_size,
        sha256=sha256,
        note=note,
        estimated_emit_bytes=jsonl_len(obj),
    )


# -----------------------------
# Core Generator
# -----------------------------

class SnapshotGenerator:
    def __init__(
        self,
        repo_root: Path,
        snapshot_root: Path,
        parts: int,
        # If balance_parts=True, this value is ignored and replaced by estimated_total/parts
        target_bytes_per_part: int,
        chunk_max_lines: int,
        chunk_max_bytes: int,
        outputs_max_bytes_for_content: int,
        balance_parts: bool,
        balance_buffer_ratio: float,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.snapshot_root = snapshot_root
        self.parts = parts
        self.target_bytes_per_part = target_bytes_per_part
        self.chunk_max_lines = chunk_max_lines
        self.chunk_max_bytes = chunk_max_bytes
        self.outputs_max_bytes_for_content = outputs_max_bytes_for_content
        self.balance_parts = balance_parts
        self.balance_buffer_ratio = balance_buffer_ratio

        self.run_id = make_run_id()
        self.out_dir = (self.repo_root / self.snapshot_root / self.run_id)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.writers: List[PartWriter] = []
        self.current_part = 0

        self.stats = RunStats()
        self.file_records: Dict[str, FileRecord] = {}

        # Planned emit queue
        self.plan_text: List[PlannedTextFile] = []
        self.plan_skip: List[PlannedSkipFile] = []
        self.estimated_total_bytes: int = 0

    def _open_parts(self) -> None:
        self.writers = []
        for i in range(self.parts):
            p = self.out_dir / f"part_{i:02d}.jsonl"
            fp = p.open("wb")
            w = PartWriter(path=p, fp=fp)
            self.writers.append(w)

        # Write meta lazily per part when first used OR always at start?
        # To satisfy "exactly 10 parts exist", we write meta immediately (small overhead).
        for i, w in enumerate(self.writers):
            meta = {
                "type": "meta",
                "schema_version": 2,
                "run_id": self.run_id,
                "repo_root": str(self.repo_root),
                "snapshot_root": str(self.snapshot_root),
                "part": i,
                "parts": self.parts,
                "created_at": iso_now(),
                "generator": {"name": "dump_context", "version": "vNext-balanced"},
                "policies": {
                    "max_parts": self.parts,
                    "target_bytes_per_part": self.target_bytes_per_part,
                    "chunk_max_lines": self.chunk_max_lines,
                    "chunk_max_bytes": self.chunk_max_bytes,
                    "outputs_max_bytes_for_content": self.outputs_max_bytes_for_content,
                    "outputs_policy": "manifest_only_for_big_files",
                    "forbid_file_truncated": True,
                    "balance_parts": self.balance_parts,
                    "estimated_total_bytes": self.estimated_total_bytes,
                    "balance_buffer_ratio": self.balance_buffer_ratio,
                },
            }
            w.write_obj(meta)

    def _close_parts(self) -> None:
        for w in self.writers:
            try:
                w.fp.flush()
                w.fp.close()
            except Exception:
                pass

    def _writer(self) -> PartWriter:
        return self.writers[self.current_part]

    def _rotate_part_if_needed(self, upcoming_bytes: int) -> None:
        w = self._writer()
        if self.current_part < (self.parts - 1):
            if w.bytes_written + upcoming_bytes > self.target_bytes_per_part:
                self.current_part += 1

    def _write(self, obj: dict) -> None:
        b_len = jsonl_len(obj)
        self._rotate_part_if_needed(b_len)
        self._writer().write_obj(obj)

    def _plan_files(self, include_roots: List[str]) -> None:
        # Collect candidate files, stable sorted
        files = list(iter_repo_files(self.repo_root, include_roots))
        files = [p for p in files if p.is_file()]
        files = stable_sort_paths(files)

        planned_total = 0

        for p in files:
            rel = normalize_relpath(self.repo_root, p)
            # Avoid recursion
            if rel.startswith("SNAPSHOT/"):
                continue

            skip, reason = should_skip_path(rel)
            if skip:
                # cache/snapshot_output: metadata record (we keep metadata, still counts)
                try:
                    sz = p.stat().st_size
                    sha = sha256_file(p)
                except Exception:
                    sz, sha = 0, ""
                rr = reason or "cache"
                ps = plan_skip_file(
                    relpath=rel,
                    reason=rr,
                    bytes_size=sz,
                    sha256=sha,
                    note="skipped by policy",
                )
                self.plan_skip.append(ps)
                planned_total += ps.estimated_emit_bytes
                continue

            # Compute stats for classification
            try:
                sz = p.stat().st_size
            except Exception:
                sz = 0
            sha = sha256_file(p) if p.exists() else ""

            parts = rel.split("/")
            is_outputs = bool(parts and parts[0] == "outputs")

            if is_outputs:
                if is_probably_binary(p) or sz > self.outputs_max_bytes_for_content:
                    ps = plan_skip_file(
                        relpath=rel,
                        reason="outputs_big_binary",
                        bytes_size=sz,
                        sha256=sha,
                        note="outputs file too large or binary; metadata only",
                    )
                    self.plan_skip.append(ps)
                    planned_total += ps.estimated_emit_bytes
                else:
                    pt = plan_text_file(
                        repo_root=self.repo_root,
                        abs_path=p,
                        relpath=rel,
                        chunk_max_lines=self.chunk_max_lines,
                        chunk_max_bytes=self.chunk_max_bytes,
                    )
                    self.plan_text.append(pt)
                    planned_total += pt.estimated_emit_bytes
                continue

            # Non-outputs
            if is_probably_binary(p):
                ps = plan_skip_file(
                    relpath=rel,
                    reason="binary",
                    bytes_size=sz,
                    sha256=sha,
                    note="binary file skipped; metadata only",
                )
                self.plan_skip.append(ps)
                planned_total += ps.estimated_emit_bytes
            else:
                pt = plan_text_file(
                    repo_root=self.repo_root,
                    abs_path=p,
                    relpath=rel,
                    chunk_max_lines=self.chunk_max_lines,
                    chunk_max_bytes=self.chunk_max_bytes,
                )
                self.plan_text.append(pt)
                planned_total += pt.estimated_emit_bytes

        self.estimated_total_bytes = planned_total

    def _apply_balanced_target(self) -> None:
        if not self.balance_parts:
            return
        # Avoid overly small target
        raw_target = math.ceil((self.estimated_total_bytes * self.balance_buffer_ratio) / self.parts)
        self.target_bytes_per_part = max(int(raw_target), MIN_TARGET_BYTES_PER_PART)

    def _emit_skip(self, ps: PlannedSkipFile) -> None:
        self.stats.files_total += 1
        self.stats.files_skipped += 1
        self.stats.skipped_by_reason[ps.reason] = self.stats.skipped_by_reason.get(ps.reason, 0) + 1
        self.file_records[ps.relpath] = FileRecord(
            path=ps.relpath,
            kind="binary",
            encoding="",
            newline="",
            bytes=ps.bytes_size,
            sha256=ps.sha256,
            total_lines=None,
            chunk_count=None,
            complete=False,
            skipped=True,
            skip_reason=ps.reason,
        )
        self._write({
            "type": "file_skipped",
            "path": ps.relpath,
            "reason": ps.reason,
            "bytes": ps.bytes_size,
            "sha256": ps.sha256,
            "note": ps.note,
        })

    def _emit_text(self, pt: PlannedTextFile) -> None:
        self.stats.files_total += 1
        self.stats.files_complete += 1
        self.stats.total_text_bytes += pt.bytes_size
        self.stats.total_chunks += len(pt.chunks)

        self.file_records[pt.relpath] = FileRecord(
            path=pt.relpath,
            kind="text",
            encoding=pt.encoding,
            newline=pt.newline,
            bytes=pt.bytes_size,
            sha256=pt.sha256,
            total_lines=pt.total_lines,
            chunk_count=len(pt.chunks),
            complete=False,
            skipped=False,
        )

        self._write({
            "type": "file_header",
            "path": pt.relpath,
            "kind": "text",
            "encoding": pt.encoding,
            "newline": pt.newline,
            "bytes": pt.bytes_size,
            "sha256": pt.sha256,
            "total_lines": pt.total_lines,
            "chunk_count": len(pt.chunks),
        })

        for i, (ls, le, content) in enumerate(pt.chunks):
            self._write({
                "type": "file_chunk",
                "path": pt.relpath,
                "chunk_index": i,
                "line_start": ls,
                "line_end": le,
                "content": content,
            })

        self._write({
            "type": "file_footer",
            "path": pt.relpath,
            "complete": True,
            "emitted_chunks": len(pt.chunks),
        })

        rec = self.file_records[pt.relpath]
        rec.complete = True
        self.file_records[pt.relpath] = rec

    def generate(self, include_roots: List[str]) -> None:
        # Phase A: plan
        self._plan_files(include_roots)

        # Balanced target
        self._apply_balanced_target()

        # Now open parts (meta includes estimated_total + target)
        self._open_parts()

        try:
            # Emit in stable order: file_skipped and file_text should interleave by path for readability.
            # We merge them by relpath.
            all_items: List[Tuple[str, str, object]] = []
            for ps in self.plan_skip:
                all_items.append((ps.relpath, "skip", ps))
            for pt in self.plan_text:
                all_items.append((pt.relpath, "text", pt))
            all_items.sort(key=lambda t: t[0].lower())

            for _, kind, item in all_items:
                if kind == "skip":
                    self._emit_skip(item)  # type: ignore[arg-type]
                else:
                    self._emit_text(item)  # type: ignore[arg-type]

            # Manifest in last part
            self.current_part = self.parts - 1
            manifest = {
                "type": "manifest",
                "run_id": self.run_id,
                "schema_version": 2,
                "files_total": self.stats.files_total,
                "files_complete": self.stats.files_complete,
                "files_skipped": self.stats.files_skipped,
                "skipped_by_reason": self.stats.skipped_by_reason,
                "violations": self.stats.violations,
                "stats": {
                    "total_text_bytes": self.stats.total_text_bytes,
                    "total_chunks": self.stats.total_chunks,
                    "estimated_total_emit_bytes": self.estimated_total_bytes,
                    "target_bytes_per_part": self.target_bytes_per_part,
                    "balance_buffer_ratio": self.balance_buffer_ratio,
                },
            }
            self._write(manifest)
            # Write separate manifest file for compatibility with no-fog gate
            manifest_path = self.repo_root / self.snapshot_root / "MANIFEST.json"
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
        finally:
            self._close_parts()


# -----------------------------
# CLI
# -----------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".", help="Repo root path (default: .)")
    ap.add_argument("--snapshot-root", default="SNAPSHOT", help="Snapshot output root folder under repo root")
    ap.add_argument("--parts", type=int, default=10, help="Number of parts (hard rule: 10)")
    ap.add_argument("--target-bytes-per-part", type=int, default=20_000_000,
                    help="Soft target size per part in bytes (ignored if --balance-parts)")
    ap.add_argument("--chunk-max-lines", type=int, default=200, help="Max lines per chunk")
    ap.add_argument("--chunk-max-bytes", type=int, default=120_000, help="Max bytes per chunk content payload")
    ap.add_argument("--outputs-max-bytes-for-content", type=int, default=DEFAULT_OUTPUTS_MAX_BYTES_FOR_CONTENT,
                    help="For outputs/* only: if larger than this, metadata-only")
    ap.add_argument("--include", nargs="*", default=DEFAULT_ALWAYS_INCLUDE,
                    help="Include roots/files (default includes src/tests/scripts/Makefile/pyproject/docs/requirements/README)")
    ap.add_argument("--balance-parts", action="store_true", default=True,
                    help="Balance content across parts by estimating total emit bytes (default: true)")
    ap.add_argument("--balance-buffer-ratio", type=float, default=DEFAULT_BALANCE_BUFFER_RATIO,
                    help="Buffer ratio applied to estimated total bytes (default: 1.08)")
    return ap.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    repo_root = Path(args.repo_root)
    if not repo_root.exists():
        print(f"ERROR: repo-root not found: {repo_root}", file=sys.stderr)
        return 2

    parts = int(args.parts)
    if parts != 10:
        print("ERROR: --parts must be exactly 10 (hard rule).", file=sys.stderr)
        return 2

    gen = SnapshotGenerator(
        repo_root=repo_root,
        snapshot_root=Path(args.snapshot_root),
        parts=parts,
        target_bytes_per_part=int(args.target_bytes_per_part),
        chunk_max_lines=int(args.chunk_max_lines),
        chunk_max_bytes=int(args.chunk_max_bytes),
        outputs_max_bytes_for_content=int(args.outputs_max_bytes_for_content),
        balance_parts=bool(args.balance_parts),
        balance_buffer_ratio=float(args.balance_buffer_ratio),
    )

    gen.generate(include_roots=list(args.include))

    out_dir = (repo_root.resolve() / args.snapshot_root / gen.run_id)
    print(f"OK: snapshot written to: {out_dir}")
    for i in range(parts):
        p = out_dir / f"part_{i:02d}.jsonl"
        sz = p.stat().st_size if p.exists() else 0
        print(f" - {p.name}: {sz} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

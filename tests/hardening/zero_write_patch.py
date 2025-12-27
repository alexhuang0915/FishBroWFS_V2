
"""Unified zero‑write patch for hardening tests.

Patches all filesystem write operations that could affect mtime or create files:
- Path.mkdir
- os.rename / os.replace
- tempfile.NamedTemporaryFile
- open(..., 'w/a/x/+')
- Path.write_text / Path.write_bytes
- Path.touch (optional)
- shutil.copy / shutil.move (optional)
"""

import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
from typing import List, Callable, Any


class ZeroWritePatch:
    """Context manager that patches all filesystem write operations."""
    
    def __init__(self, raise_on_write: bool = True, collect_calls: bool = True):
        """
        Args:
            raise_on_write: If True, raise AssertionError on any write attempt.
                If False, only collect calls (for debugging).
            collect_calls: If True, collect write attempts in self.write_calls.
        """
        self.raise_on_write = raise_on_write
        self.collect_calls = collect_calls
        self.write_calls: List[str] = []
        
        # Original functions
        self.original_open = open
        self.original_write_text = Path.write_text
        self.original_write_bytes = Path.write_bytes
        self.original_mkdir = Path.mkdir
        self.original_rename = os.rename
        self.original_replace = os.replace
        self.original_namedtemporaryfile = tempfile.NamedTemporaryFile
        self.original_touch = Path.touch
        self.original_shutil_copy = shutil.copy
        self.original_shutil_move = shutil.move
        
    def _record_call(self, msg: str) -> None:
        """Record a write attempt."""
        if self.collect_calls:
            self.write_calls.append(msg)
        if self.raise_on_write:
            raise AssertionError(f"Zero‑write violation: {msg}")
    
    def guarded_open(self, file, mode='r', *args, **kwargs):
        """Patch for builtins.open."""
        if any(c in mode for c in ['w', 'a', '+', 'x']):
            self._record_call(f"open({file!r}, mode={mode!r})")
        return self.original_open(file, mode, *args, **kwargs)
    
    def guarded_write_text(self, self_path, text, *args, **kwargs):
        """Patch for Path.write_text."""
        self._record_call(f"write_text({self_path!r})")
        return self.original_write_text(self_path, text, *args, **kwargs)
    
    def guarded_write_bytes(self, self_path, data, *args, **kwargs):
        """Patch for Path.write_bytes."""
        self._record_call(f"write_bytes({self_path!r})")
        return self.original_write_bytes(self_path, data, *args, **kwargs)
    
    def guarded_mkdir(self, self_path, mode=0o777, parents=False, exist_ok=False):
        """Patch for Path.mkdir."""
        self._record_call(f"mkdir({self_path!r}, parents={parents}, exist_ok={exist_ok})")
        return self.original_mkdir(self_path, mode=mode, parents=parents, exist_ok=exist_ok)
    
    def guarded_rename(self, src, dst, *args, **kwargs):
        """Patch for os.rename."""
        self._record_call(f"rename({src!r} → {dst!r})")
        return self.original_rename(src, dst, *args, **kwargs)
    
    def guarded_replace(self, src, dst, *args, **kwargs):
        """Patch for os.replace."""
        self._record_call(f"replace({src!r} → {dst!r})")
        return self.original_replace(src, dst, *args, **kwargs)
    
    def guarded_namedtemporaryfile(self, mode='w+b', *args, **kwargs):
        """Patch for tempfile.NamedTemporaryFile."""
        if any(c in mode for c in ['w', 'a', '+', 'x']):
            self._record_call(f"NamedTemporaryFile(mode={mode!r})")
        return self.original_namedtemporaryfile(mode=mode, *args, **kwargs)
    
    def guarded_touch(self, self_path, mode=0o666, exist_ok=True):
        """Patch for Path.touch (changes mtime)."""
        self._record_call(f"touch({self_path!r})")
        return self.original_touch(self_path, mode=mode, exist_ok=exist_ok)
    
    def guarded_shutil_copy(self, src, dst, *args, **kwargs):
        """Patch for shutil.copy."""
        self._record_call(f"shutil.copy({src!r} → {dst!r})")
        return self.original_shutil_copy(src, dst, *args, **kwargs)
    
    def guarded_shutil_move(self, src, dst, *args, **kwargs):
        """Patch for shutil.move."""
        self._record_call(f"shutil.move({src!r} → {dst!r})")
        return self.original_shutil_move(src, dst, *args, **kwargs)
    
    def __enter__(self):
        """Enter context and apply patches."""
        self.patches = [
            patch('builtins.open', self.guarded_open),
            patch.object(Path, 'write_text', self.guarded_write_text),
            patch.object(Path, 'write_bytes', self.guarded_write_bytes),
            patch.object(Path, 'mkdir', self.guarded_mkdir),
            patch('os.rename', self.guarded_rename),
            patch('os.replace', self.guarded_replace),
            patch('tempfile.NamedTemporaryFile', self.guarded_namedtemporaryfile),
            patch.object(Path, 'touch', self.guarded_touch),
            patch('shutil.copy', self.guarded_shutil_copy),
            patch('shutil.move', self.guarded_shutil_move),
        ]
        for p in self.patches:
            p.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and stop patches."""
        for p in self.patches:
            p.stop()
        return False  # propagate exceptions


def with_zero_write_patch(func: Callable) -> Callable:
    """Decorator that applies zero‑write patch to a test function."""
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with ZeroWritePatch():
            return func(*args, **kwargs)
    
    return wrapper


# Convenience context manager for snapshot equality checking
import contextlib
from utils.fs_snapshot import snapshot_tree, diff_snap


@contextlib.contextmanager
def snapshot_equality_check(root: Path):
    """
    Context manager that takes snapshot before and after, asserts no changes.
    
    Usage:
        with snapshot_equality_check(plan_dir):
            call_read_only_function()
    """
    snap_before = snapshot_tree(root, include_sha256=True)
    yield
    snap_after = snapshot_tree(root, include_sha256=True)
    diff = diff_snap(snap_before, snap_after)
    assert diff["added"] == [], f"Files added: {diff['added']}"
    assert diff["removed"] == [], f"Files removed: {diff['removed']}"
    assert diff["changed"] == [], f"Files changed: {diff['changed']}"
    
    # Also verify mtimes unchanged
    for rel_path, snap in snap_before.items():
        if rel_path in snap_after:
            assert snap.mtime_ns == snap_after[rel_path].mtime_ns, \
                f"mtime changed for {rel_path}"



"""
Governance Guard: Anti-Shadowing & Runtime Integrity.

Contracts:
- No dangerous stdlib-shadowing filenames under src/
- Importing stdlib `types` must not resolve into this repo
"""
from __future__ import annotations
from pathlib import Path
import pytest

BLACKLIST_FILENAMES = {
    "types.py","enum.py","json.py","time.py",
    "asyncio.py","pathlib.py","copy.py","weakref.py",
    "re.py","socket.py","logging.py","dataclasses.py",
    "typing.py","collections.py","math.py","random.py",
}

def _root() -> Path:
    return Path(__file__).resolve().parents[2]

def test_no_stdlib_shadowing_files():
    root = _root()
    src = root / "src"
    assert src.exists()
    violations = [str(p.relative_to(root)) for p in src.rglob("*.py") if p.name in BLACKLIST_FILENAMES]
    assert not violations, f"Found stdlib-shadowing filenames under src/: {violations}"

def test_runtime_types_integrity():
    root = _root()
    import types
    origin = getattr(types, "__file__", "")
    if origin and str(root) in str(origin):
        pytest.fail(f"CRITICAL: stdlib 'types' resolved inside repo: {origin}")
    assert hasattr(types, "SimpleNamespace")
    assert hasattr(types, "ModuleType")
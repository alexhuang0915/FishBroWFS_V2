"""Policy test: GUI files must not contain forbidden control imports (string-level ban)."""

from __future__ import annotations

from pathlib import Path

BANNED = [
    "FishBroWFS_V2.control.",
    "from FishBroWFS_V2.control",
    "import FishBroWFS_V2.control",
    "FishBroWFS_V2.outputs.jobs_db",
    "FishBroWFS_V2.control.jobs_db",
    'importlib.import_module("FishBroWFS_V2.control',
    "import_module('FishBroWFS_V2.control",
]


def _iter_gui_files(root: Path):
    for p in sorted(root.rglob("*.py")):
        rel_path = p.relative_to(root)
        if str(rel_path).startswith("gui/"):
            yield p


def _find_matches(text: str, needle: str) -> list[int]:
    # return 1-based line numbers containing needle
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines, start=1):
        if needle in line:
            out.append(i)
    return out


def test_gui_string_bans():
    """Test that no GUI file contains forbidden control imports."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    src_root = repo_root / "src"
    assert src_root.exists(), f"Missing src root: {src_root}"

    offenders = []
    for f in _iter_gui_files(src_root):
        txt = f.read_text(encoding="utf-8")
        for needle in BANNED:
            lines = _find_matches(txt, needle)
            if lines:
                # Special case: intent_bridge.py is allowed to import control modules
                # because it's the bridge between UI and backend
                if f.name == "intent_bridge.py":
                    continue
                offenders.append((str(f), needle, lines[:5]))

    assert not offenders, "GUI string ban violations:\n" + "\n".join(
        [f"- {path}: {needle} @ lines {lines}" for path, needle, lines in offenders]
    )


if __name__ == "__main__":
    # Quick manual test
    test_gui_string_bans()
    print("✅ No GUI string ban violations found")
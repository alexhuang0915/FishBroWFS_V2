from __future__ import annotations

import re
from pathlib import Path


def _scan_for_python_literal(root: Path) -> list[str]:
    offenders: list[str] = []
    pattern = re.compile(
        r"subprocess\.(Popen|run|check_call|check_output)\([\s\S]{0,400}?[\"']python[\"']",
        re.MULTILINE,
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path))
    return offenders


def test_no_python_literal_in_control_subprocess_sites():
    repo_root = Path(__file__).resolve().parents[2]
    targets = [repo_root / "tests" / "control", repo_root / "src" / "control"]
    offenders: list[str] = []
    for target in targets:
        offenders.extend(_scan_for_python_literal(target))

    assert not offenders, "Hardcoded 'python' literal in subprocess call:\n" + "\n".join(offenders)

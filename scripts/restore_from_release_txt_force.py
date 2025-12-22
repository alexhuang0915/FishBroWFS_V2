#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

FILE_LINE = re.compile(r"^FILE:\s+(?P<path>.+?)\s*$", re.MULTILINE)

def strip_separators(text: str) -> str:
    text = text.lstrip("\ufeff")
    lines = text.splitlines(True)
    i = 0
    while i < len(lines):
        t = lines[i].strip()
        if not t:
            i += 1
            continue
        if len(t) >= 10 and set(t) <= {"="}:
            i += 1
            continue
        if len(t) >= 10 and set(t) <= {"-"}:
            i += 1
            continue
        break
    return "".join(lines[i:])

def main() -> None:
    repo = Path.cwd()
    txt = repo / "FishBroWFS_V2_release_20251223_005323-b55a84d.txt"
    if not txt.exists():
        raise SystemExit(f"TXT not found: {txt}")

    text = txt.read_text(encoding="utf-8", errors="replace")
    blocks = list(FILE_LINE.finditer(text))
    if not blocks:
        raise SystemExit("No FILE: blocks found")

    restored = 0
    for i, m in enumerate(blocks):
        rel = m.group("path").strip()
        start = m.end()
        end = blocks[i+1].start() if i+1 < len(blocks) else len(text)
        content = strip_separators(text[start:end])

        out = repo / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        restored += 1

    print(f"[OK] Restored {restored} files from TXT")

if __name__ == "__main__":
    main()

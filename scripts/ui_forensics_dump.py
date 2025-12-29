#!/usr/bin/env python3
"""
CLI script to generate a UI forensic dump without launching the UI.

Usage:
    python -m scripts.ui_forensics_dump

This script calls the forensics service, writes JSON and text reports,
and prints the absolute paths of the generated files.
"""
import json
import sys
from pathlib import Path

# Ensure src/ is in sys.path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gui.nicegui.services.forensics_service import (
    generate_ui_forensics,
    write_forensics_files,
)


def main() -> None:
    """Generate UI forensic dump and write files."""
    out_dir = Path("outputs/forensics")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Generating UI forensic dump in {out_dir.resolve()}")

    # 1. Generate snapshot
    snapshot = generate_ui_forensics(outputs_dir=str(out_dir))

    # 2. Write JSON and text files (service writes them)
    result = write_forensics_files(snapshot, outputs_dir=str(out_dir))
    json_path = Path(result["json_path"])
    txt_path = Path(result["txt_path"])

    # 3. Verify files exist
    if not json_path.is_file():
        raise RuntimeError(f"JSON file not created: {json_path}")
    if not txt_path.is_file():
        raise RuntimeError(f"Text file not created: {txt_path}")

    # 4. Print success messages
    print(f"[OK] {json_path.resolve()}")
    print(f"[OK] {txt_path.resolve()}")

    # Optional: print a short summary
    status = snapshot.get("status", {})
    print(
        f"[SUMMARY] System state: {status.get('state', 'UNKNOWN')} "
        f"({status.get('summary', 'No summary')})"
    )


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
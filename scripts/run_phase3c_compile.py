#!/usr/bin/env python3
"""
Phase 3C Portfolio Compilation – Execution Script.

Compile a frozen Season Manifest into deployment TXT files for MultiCharts.

Usage:
    python scripts/run_phase3c_compile.py path/to/season_manifest.json

This script must NOT read the current "live" config. All info must come from the frozen manifest.
"""

import sys
from pathlib import Path

# Ensure the package root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from deployment.compiler import compile_season


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_phase3c_compile.py <path/to/season_manifest.json>")
        sys.exit(1)

    manifest_path = Path(sys.argv[1])
    if not manifest_path.exists():
        print(f"ERROR: Manifest file not found: {manifest_path}")
        sys.exit(1)

    # Determine output directory
    from governance.models import SeasonManifest
    manifest = SeasonManifest.load(manifest_path)
    output_dir = Path("outputs") / "deployment" / manifest.season_id

    print(f"Compiling season {manifest.season_id}...")
    print(f"  manifest: {manifest_path}")
    print(f"  output: {output_dir}")

    try:
        compile_season(manifest_path, output_dir)
    except Exception as e:
        print(f"Compilation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"Deployment Pack ready at: {output_dir}")


if __name__ == "__main__":
    main()
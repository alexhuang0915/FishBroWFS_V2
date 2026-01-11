#!/usr/bin/env python3
"""
Dump OpenAPI contract snapshot.

This tool is used to manually update the OpenAPI snapshot stored in
tests/policy/api_contract/openapi.json.

Usage:
    python -m src.control.tools.dump_openapi --out tests/policy/api_contract/openapi.json

The snapshot is used by the policy test to detect API drift.
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from control.api import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump OpenAPI contract snapshot")
    parser.add_argument(
        "--out",
        required=True,
        help="Output JSON file path (e.g., tests/policy/api_contract/openapi.json)",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate OpenAPI spec
    spec = app.openapi()

    # Write with indentation
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"OpenAPI snapshot written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
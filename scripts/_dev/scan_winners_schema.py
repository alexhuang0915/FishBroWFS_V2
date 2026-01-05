#!/usr/bin/env python3
"""Scan winners.json files for legacy schema markers."""

import json
import sys
from pathlib import Path

def detect_schema_version(data: dict) -> str:
    """Return 'v2', 'legacy', or 'unknown'."""
    # V2 winners have a "version" field (maybe "v2") and "winners" list of objects
    if "version" in data:
        return "v2"
    # Legacy winners may have a flat list of dicts with keys like "param_id", "score"
    if isinstance(data, list):
        return "legacy"
    # If data has "winners" key that's a list, likely v2
    if "winners" in data and isinstance(data["winners"], list):
        return "v2"
    return "unknown"

def main():
    # Read list from stdin or from file
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            files = [line.strip() for line in f if line.strip()]
    else:
        # Read from find output
        find_output = Path(__file__).parent.parent.parent / "outputs" / "_dp_evidence" / "phase1_cleanup" / "80_find_winners_files.txt"
        if not find_output.exists():
            print("No find output file.")
            return
        with open(find_output, 'r') as f:
            files = [line.strip() for line in f if line.strip()]
    
    results = []
    for fpath in files:
        path = Path(fpath)
        if not path.exists():
            results.append((fpath, "missing"))
            continue
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            results.append((fpath, f"invalid JSON: {e}"))
            continue
        schema = detect_schema_version(data)
        results.append((fpath, schema))
    
    # Output
    out_lines = []
    for fpath, schema in results:
        out_lines.append(f"{fpath}: {schema}")
    out_text = "\n".join(out_lines)
    print(out_text)
    
    # Write to evidence file
    evidence_path = Path(__file__).parent.parent.parent / "outputs" / "_dp_evidence" / "phase1_cleanup" / "81_winners_schema_scan.txt"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(out_text)
    
    # Determine if any legacy winners exist
    legacy_files = [f for f, s in results if s == "legacy"]
    if legacy_files:
        print(f"\nWARNING: Found {len(legacy_files)} legacy winners files:")
        for f in legacy_files:
            print(f"  {f}")
        sys.exit(1)
    else:
        print("\nNo legacy winners found. Safe to remove conversion logic.")

if __name__ == "__main__":
    main()
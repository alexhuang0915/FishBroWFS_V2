from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.paths import get_artifacts_root

def get_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def extract_grade_val(grade: str) -> int:
    order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
    return order.get(grade, 99)

def find_latest_auto_run() -> Optional[str]:
    auto_runs_dir = get_artifacts_root() / "auto_runs"
    if not auto_runs_dir.exists():
        return None
    dirs = sorted([d.name for d in auto_runs_dir.iterdir() if d.is_dir() and d.name.startswith("auto_")])
    return dirs[-1] if dirs else None

def main() -> int:
    ap = argparse.ArgumentParser(description="Matrix WFS Selection CLI")
    ap.add_argument("--auto-run", type=str, help="Auto run ID")
    ap.add_argument("--latest-auto-run", action="store_true", help="Use latest auto-run")
    ap.add_argument("--filter-grade", type=str, help="Comma-separated allowed grades (e.g. S,A,B)")
    ap.add_argument("--min-trades", type=int, default=0, help="Minimum trades")
    ap.add_argument("--max-missing-ratio", type=float, default=100.0, help="Maximum data2 missing ratio pct")
    ap.add_argument("--top-k-per-data1", type=int, default=None, help="Top K results per Data1 instrument")
    ap.add_argument("--sort-by", type=str, default="score_total_weighted", help="Sorting metric")
    args = ap.parse_args()

    auto_run_id = args.auto_run
    if args.latest_auto_run:
        auto_run_id = find_latest_auto_run()
        if not auto_run_id:
            print("Error: No auto-runs found.")
            return 1
        print(f"Using latest auto-run: {auto_run_id}")

    if not auto_run_id:
        print("Error: --auto-run or --latest-auto-run is required.")
        return 1

    auto_run_dir = get_artifacts_root() / "auto_runs" / auto_run_id
    summary_path = auto_run_dir / "matrix_summary.json"
    
    if not summary_path.exists():
        print(f"Error: matrix_summary.json not found in {auto_run_dir}. Please run matrix_summary_cli first.")
        return 1

    summary = load_json(summary_path)
    rows: List[Dict[str, Any]] = summary.get("rows", [])

    # 1. Filtering
    allowed_grades = set()
    if args.filter_grade:
        allowed_grades = {g.strip().upper() for g in args.filter_grade.split(",") if g.strip()}

    filtered_rows = []
    for r in rows:
        # Grade filter
        if allowed_grades and (r.get("grade") or "N/A") not in allowed_grades:
            continue
        # Min trades
        if int(r.get("trades") or 0) < args.min_trades:
            continue
        # Max missing ratio
        if float(r.get("data2_missing_ratio_pct") or 0.0) > args.max_missing_ratio:
            continue
        filtered_rows.append(r)

    # 2. Sorting
    # Default: score_total_weighted DESC, then Grade ASC, then Trades DESC, then JobID ASC
    def sort_key(r):
        val = r.get(args.sort_by)
        if val is None:
            val = float("-inf")
        # Higher score better, Lower grade order better, Higher trades better
        return (-val, extract_grade_val(r.get("grade", "D")), -(r.get("trades") or 0), r.get("job_id", ""))

    filtered_rows.sort(key=sort_key)

    # 3. Top-K per data1
    final_rows = []
    if args.top_k_per_data1 is not None:
        counts: Dict[str, int] = {}
        for r in filtered_rows:
            d1 = r.get("data1", "unknown")
            counts[d1] = counts.get(d1, 0) + 1
            if counts[d1] <= args.top_k_per_data1:
                final_rows.append(r)
    else:
        final_rows = filtered_rows

    # 4. Results
    selection_job_ids = [r["job_id"] for r in final_rows]
    grouped: Dict[str, List[str]] = {}
    for r in final_rows:
        d1 = r["data1"]
        if d1 not in grouped:
            grouped[d1] = []
        grouped[d1].append(r["job_id"])

    selection_data = {
        "version": "1.0",
        "generated_at": get_iso_now(),
        "auto_run_id": auto_run_id,
        "rules_used": vars(args),
        "selected_job_ids": selection_job_ids,
        "grouped": grouped,
        "selection_details": final_rows
    }

    # Write JSON
    json_path = auto_run_dir / "selection.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(selection_data, f, indent=2)
    print(f"Generated {json_path}")

    # Write CSV
    csv_path = auto_run_dir / "selection.csv"
    if final_rows:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=final_rows[0].keys())
            writer.writeheader()
            writer.writerows(final_rows)
        print(f"Generated {csv_path}")

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())

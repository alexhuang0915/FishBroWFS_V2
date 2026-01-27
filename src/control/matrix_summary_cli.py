from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from control.job_artifacts import get_job_evidence_dir
from core.paths import get_artifacts_root

def get_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def extract_grade_val(grade: str) -> int:
    # A < B < C < D
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    return order.get(grade, 99)

def _read_wfs_result_path(job_id: str, season: Optional[str]) -> Optional[Path]:
    """
    Resolve the canonical domain WFS result.json for a job.

    Contract (preferred): job evidence contains `wfs_result_path.txt` pointing to domain `.../seasons/<season>/wfs/<job_id>/result.json`.
    Fallbacks exist for legacy/partial artifacts.
    """
    evidence_dir = get_job_evidence_dir(job_id)
    path_txt = evidence_dir / "wfs_result_path.txt"
    if path_txt.exists():
        p = path_txt.read_text(encoding="utf-8").strip()
        if p:
            return Path(p)

    # Backward-compat: some tools may have written a JSON evidence file with a key.
    legacy_json = load_json(evidence_dir / "result.json") or {}
    legacy_path = legacy_json.get("wfs_result_path")
    if isinstance(legacy_path, str) and legacy_path.strip():
        return Path(legacy_path.strip())

    # Last-resort fallback if caller provided season.
    if season:
        p = get_artifacts_root() / "seasons" / season / "wfs" / job_id / "result.json"
        if p.exists():
            return p
    return None


def process_job(job_id: str, season: Optional[str]) -> Optional[Dict[str, Any]]:
    wfs_result_path = _read_wfs_result_path(job_id, season)
    if not wfs_result_path:
        return None

    wfs_result = load_json(wfs_result_path)
    if not wfs_result:
        return None

    meta = wfs_result.get("meta", {})
    config = wfs_result.get("config", {})
    metrics = wfs_result.get("metrics", {})
    verdict = wfs_result.get("verdict", {})
    windows = wfs_result.get("windows", [])

    # Extract ratios and aggregate (simple mean)
    missing_ratios = []
    update_ratios = []
    hold_ratios = []
    for w in windows:
        oos = w.get("oos_metrics", {})
        if "data2_missing_ratio_pct" in oos:
            missing_ratios.append(oos["data2_missing_ratio_pct"])
        if "data2_update_ratio_pct" in oos:
            update_ratios.append(oos["data2_update_ratio_pct"])
        if "data2_hold_ratio_pct" in oos:
            hold_ratios.append(oos["data2_hold_ratio_pct"])

    def mean(vals: List[float]) -> Optional[float]:
        return sum(vals) / len(vals) if vals else None

    # strategy_id: try meta["strategy_id"] then meta["strategy_family"], or from bridge payload
    strategy_id = meta.get("strategy_id") or meta.get("strategy_family")

    return {
        "job_id": job_id,
        "data1": meta.get("instrument") or config.get("data", {}).get("data1"),
        "data2": config.get("data", {}).get("data2"),
        "timeframe": meta.get("timeframe") or config.get("data", {}).get("timeframe"),
        "strategy_id": strategy_id,
        "grade": verdict.get("grade"),
        "is_tradable": verdict.get("is_tradable"),
        "score_total_weighted": metrics.get("scores", {}).get("total_weighted"),
        "pass_rate": metrics.get("raw", {}).get("pass_rate"),
        "trades": metrics.get("raw", {}).get("trades"),
        "wfe": metrics.get("raw", {}).get("wfe"),
        "ulcer_index": metrics.get("raw", {}).get("ulcer_index"),
        "max_underwater_days": metrics.get("raw", {}).get("max_underwater_days"),
        "data2_missing_ratio_pct": mean(missing_ratios),
        "data2_update_ratio_pct": mean(update_ratios),
        "data2_hold_ratio_pct": mean(hold_ratios),
    }

def main() -> int:
    ap = argparse.ArgumentParser(description="Matrix WFS Summary CLI")
    ap.add_argument("--auto-run", type=str, help="Auto run ID to read manifest from")
    ap.add_argument("--latest-auto-run", action="store_true", help="Automatically find the latest auto-run")
    ap.add_argument("--season", type=str, help="Season (required if not using --auto-run)")
    ap.add_argument("--job-ids", type=str, help="Comma-separated job IDs (required if not using --auto-run)")
    ap.add_argument("--out", type=Path, help="Explicit output directory")
    args = ap.parse_args()

    auto_run_id = args.auto_run
    if args.latest_auto_run:
        auto_runs_dir = get_artifacts_root() / "auto_runs"
        if not auto_runs_dir.exists():
            print(f"Error: auto_runs directory not found: {auto_runs_dir}")
            return 1
        
        # Directories are named auto_YYYYQ#_YYYYMMDD_HHMMSS, so alphabetical sort works
        dirs = sorted([d.name for d in auto_runs_dir.iterdir() if d.is_dir() and d.name.startswith("auto_")])
        if not dirs:
            print(f"No auto-runs found in {auto_runs_dir}")
            return 1
        auto_run_id = dirs[-1]
        print(f"Using latest auto-run: {auto_run_id}")

    season = args.season
    job_ids: List[str] = []

    output_dir: Path = Path.cwd()

    if auto_run_id:
        auto_run_dir = get_artifacts_root() / "auto_runs" / auto_run_id
        manifest = load_json(auto_run_dir / "manifest.json")
        if not manifest:
            print(f"Error: manifest.json not found in {auto_run_dir}")
            return 1
        
        season = manifest.get("plan", {}).get("season")
        steps = manifest.get("steps", [])
        for step in steps:
            if step.get("name") == "RUN_RESEARCH_WFS":
                states = step.get("states", {})
                job_ids = [jid for jid, state in states.items() if state == "SUCCEEDED"]
                break
        output_dir = auto_run_dir
    else:
        if not season or not args.job_ids:
            print("Error: --season and --job-ids are required when not using --auto-run")
            return 1
        job_ids = [jid.strip() for jid in args.job_ids.split(",") if jid.strip()]
        # Default output dir for manual run: outputs/artifacts/seasons/<season>
        output_dir = get_artifacts_root() / "seasons" / season
        output_dir.mkdir(parents=True, exist_ok=True)

    if args.out:
        output_dir = args.out
        output_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for jid in job_ids:
        row = process_job(jid, season)
        if row:
            rows.append(row)

    # Sorting
    # 1. data1 ASC
    # 2. grade A<B<C<D
    # 3. score_total_weighted DESC (null = -inf)
    # 4. job_id ASC
    rows.sort(key=lambda r: (
        r["data1"] or "",
        extract_grade_val(r["grade"]),
        -(r["score_total_weighted"] if r["score_total_weighted"] is not None else float("-inf")),
        r["job_id"]
    ))

    # Grouping
    grouped: Dict[str, Dict[str, List[str]]] = {}
    for row in rows:
        d1 = row["data1"]
        if d1 not in grouped:
            grouped[d1] = {"ranked_job_ids": []}
        grouped[d1]["ranked_job_ids"].append(row["job_id"])

    summary = {
        "version": "1.0",
        "generated_at": get_iso_now(),
        "auto_run_id": auto_run_id,
        "season": season,
        "rows": rows,
        "grouped": grouped
    }

    json_path = output_dir / "matrix_summary.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Generated {json_path}")

    csv_path = output_dir / "matrix_summary.csv"
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"Generated {csv_path}")

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())

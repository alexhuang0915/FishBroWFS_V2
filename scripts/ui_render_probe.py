#!/usr/bin/env python3
"""
CLI script to run UI render probe and generate diff report.

Usage:
    python -m scripts.ui_render_probe

This script calls render_probe_service, writes JSON and text reports,
and prints a human-readable summary.
"""
import json
import sys
from pathlib import Path

# Ensure src/ is in sys.path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gui.nicegui.services.render_probe_service import (
    probe_all_pages,
    build_render_diff_report,
)


def main() -> None:
    """Run render probe and write outputs."""
    out_dir = Path("outputs/forensics")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Running UI render probe, output directory: {out_dir.resolve()}")

    # 1. Probe all pages
    results = probe_all_pages(mode="probe")

    # 2. Build diff report
    report = build_render_diff_report(results)

    # 3. Write JSON report
    json_path = out_dir / "ui_render_probe.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "results": results,
                "report": report,
                "meta": {
                    "script": "ui_render_probe.py",
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
                },
            },
            f,
            indent=2,
            sort_keys=True,
            default=str,
        )
    print(f"[OK] {json_path.resolve()}")

    # 4. Write human-readable text report
    txt_path = out_dir / "ui_render_probe.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(render_text_report(results, report))

    print(f"[OK] {txt_path.resolve()}")

    # 5. Print summary to console
    summary = report.get("summary", {})
    anomalies = report.get("anomalies", [])
    print(f"\n[SUMMARY] Pages passed: {summary.get('passed', 0)}/{summary.get('total', 0)}")
    if anomalies:
        print(f"[ANOMALIES] {len(anomalies)} anomalies detected:")
        for a in anomalies[:5]:  # limit output
            print(f"  • {a['page_id']}: {a['reason']}")
        if len(anomalies) > 5:
            print(f"  ... and {len(anomalies) - 5} more.")
    else:
        print("[ANOMALIES] No anomalies detected.")


def render_text_report(results: dict, report: dict) -> str:
    """Generate a human-readable text report."""
    lines = []
    lines.append("UI RENDER PROBE REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Per-page status
    lines.append("Page status:")
    lines.append("")
    for page_id, result in results.items():
        render_ok = result.get("render_ok", False)
        errors = result.get("errors", [])
        counts = result.get("counts", {})
        total = sum(counts.values())
        status = "PASS" if render_ok and total > 0 else "FAIL"
        lines.append(f"  {page_id:12} {status:4}  elements={total:3d}  " +
                     " ".join(f"{k}:{v}" for k, v in counts.items() if v > 0))
        if errors:
            lines.append(f"      errors: {errors}")
    lines.append("")

    # Diff per page
    per_page = report.get("per_page", {})
    if per_page:
        lines.append("Expectation diff:")
        for page_id, diff_info in per_page.items():
            diff = diff_info.get("diff", {})
            if diff:
                lines.append(f"  {page_id}:")
                for elem, info in diff.items():
                    lines.append(f"    {elem}: expected >= {info['expected']}, got {info['actual']}")
        lines.append("")

    # Anomalies
    anomalies = report.get("anomalies", [])
    if anomalies:
        lines.append("Anomalies (by severity):")
        for a in anomalies:
            lines.append(f"  [{a.get('severity', '??')}] {a['page_id']}: {a['reason']}")
        lines.append("")

    # Summary
    summary = report.get("summary", {})
    lines.append(f"Summary: {summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed, {summary.get('total', 0)} total")
    lines.append("")
    lines.append("End of report.")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
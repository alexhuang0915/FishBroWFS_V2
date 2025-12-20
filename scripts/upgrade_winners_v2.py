#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

# --- Ensure src/ is on sys.path so `import FishBroWFS_V2` works even when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from FishBroWFS_V2.core.winners_builder import build_winners_v2  # noqa: E402
from FishBroWFS_V2.core.winners_schema import is_winners_v2      # noqa: E402


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True, separators=(",", ":"), indent=2)
        f.write("\n")


def _read_required_artifacts(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    manifest = _read_json(run_dir / "manifest.json")
    config_snapshot = _read_json(run_dir / "config_snapshot.json")
    metrics = _read_json(run_dir / "metrics.json")
    winners = _read_json(run_dir / "winners.json")
    return {
        "manifest": manifest,
        "config_snapshot": config_snapshot,
        "metrics": metrics,
        "winners": winners,
    }


def upgrade_one_run_dir(run_dir: Path, *, dry_run: bool) -> bool:
    winners_path = run_dir / "winners.json"
    if not winners_path.exists():
        return False

    data = _read_required_artifacts(run_dir)
    winners_data = data["winners"]

    if is_winners_v2(winners_data):
        return False

    manifest = data["manifest"]
    config_snapshot = data["config_snapshot"]
    metrics = data["metrics"]

    stage_name = metrics.get("stage_name") or config_snapshot.get("stage_name") or "unknown_stage"
    run_id = manifest.get("run_id", run_dir.name)

    legacy_topk = winners_data.get("topk", [])
    winners_v2 = build_winners_v2(
        stage_name=stage_name,
        run_id=run_id,
        manifest=manifest,
        config_snapshot=config_snapshot,
        legacy_topk=legacy_topk,
    )

    if dry_run:
        print(f"[DRY] would upgrade: {run_dir}")
        return True

    backup_path = run_dir / "winners_legacy.json"
    if not backup_path.exists():
        _write_json(backup_path, winners_data)

    _write_json(winners_path, winners_v2)
    print(f"[OK] upgraded: {run_dir}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", required=True)
    ap.add_argument("--outputs-root", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    outputs_root = Path(args.outputs_root)
    runs_dir = outputs_root / "seasons" / args.season / "runs"
    if not runs_dir.exists():
        raise SystemExit(f"runs dir not found: {runs_dir}")

    scanned = 0
    changed = 0

    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        scanned += 1
        try:
            if upgrade_one_run_dir(run_dir, dry_run=args.dry_run):
                changed += 1
        except FileNotFoundError as e:
            print(f"[SKIP] missing file in {run_dir}: {e}")
        except json.JSONDecodeError as e:
            print(f"[SKIP] bad json in {run_dir}: {e}")

    print(f"[DONE] scanned={scanned} changed={changed} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

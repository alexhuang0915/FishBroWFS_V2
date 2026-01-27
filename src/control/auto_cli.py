from __future__ import annotations

import argparse
from pathlib import Path

from control.auto.orchestrator import run_auto_wfs
from control.auto.portfolio_spec import load_portfolio_spec_v1
from control.auto.run_plan import plan_from_portfolio_spec, default_portfolio_spec_path


def _parse_tfs(raw: str) -> list[int]:
    out: list[int] = []
    for part in (raw or "").split(","):
        p = part.strip()
        if not p:
            continue
        out.append(int(p))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="FishBro Auto WFS Orchestrator (deterministic + optional LLM mode)")
    ap.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic")
    ap.add_argument("--spec", type=Path, default=default_portfolio_spec_path(), help="Portfolio spec V1 path")
    ap.add_argument("--season", type=str, default=None, help="Season override (default: last season in spec)")
    ap.add_argument("--tfs", type=str, default="60", help="Timeframes in minutes, comma-separated")
    ap.add_argument("--data2", type=str, default=None, help="Override: use this single data2_dataset_id for all data1 instruments")
    ap.add_argument(
        "--data2-mode",
        choices=["single", "matrix"],
        default="matrix",
        help="SSOT-driven data2 pairing mode (ignored when --data2 override is provided)",
    )
    ap.add_argument("--max-workers", type=int, default=1)
    ap.add_argument("--no-finalize", action="store_true", default=False, help="Do not auto-finalize portfolio")
    ap.add_argument("--select-policy", choices=["recommended", "all"], default="recommended")
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--timeout-sec", type=float, default=None, help="Global timeout for waiting job completion (seconds)")
    args = ap.parse_args()

    spec = load_portfolio_spec_v1(args.spec)
    plan = plan_from_portfolio_spec(
        spec,
        mode=args.mode,
        season=args.season,
        timeframes_min=_parse_tfs(args.tfs),
        data2_dataset_id=args.data2,
        data2_mode=args.data2_mode,
        max_workers=args.max_workers,
        auto_finalize=not args.no_finalize,
        select_policy=args.select_policy,
    )
    run_auto_wfs(plan=plan, dry_run=bool(args.dry_run), timeout_sec=args.timeout_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

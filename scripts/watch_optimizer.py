from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def newest_dir(parent: Path) -> Path | None:
    if not parent.exists():
        return None
    dirs = [p for p in parent.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Monitor FishBro optimizer run_state + pid until closure.")
    ap.add_argument("--pid-file", type=Path, required=True)
    ap.add_argument("--run-state", type=Path, default=None, help="Explicit run_state.json path (optional)")
    ap.add_argument("--poll-sec", type=float, default=60.0)
    ap.add_argument("--touch-on-close", type=Path, default=Path("outputs/optimizer/CLOSED.txt"))
    args = ap.parse_args()

    pid_file: Path = args.pid_file
    if not pid_file.exists():
        print(f"[{iso_now()}] missing pid-file: {pid_file}")
        return 2

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        print(f"[{iso_now()}] invalid pid-file: {pid_file}")
        return 2

    run_state_path: Path | None = args.run_state
    if run_state_path is None:
        latest = newest_dir(Path("outputs/optimizer"))
        if latest is not None:
            cand = latest / "run_state.json"
            if cand.exists():
                run_state_path = cand

    last_iters: int | None = None
    while True:
        running = True
        try:
            os.kill(pid, 0)
        except Exception:
            running = False

        if run_state_path is None or not run_state_path.exists():
            print(f"[{iso_now()}] pid={pid} running={running} run_state=missing")
        else:
            try:
                state = read_json(run_state_path)
                history = state.get("history") or []
                best = state.get("best") or {}
                iters = len(history) if isinstance(history, list) else 0
                if last_iters != iters:
                    last_iters = iters
                    last = history[-1] if history else {}
                    print(
                        f"[{iso_now()}] pid={pid} running={running} "
                        f"iters={iters} best_ok={bool(best.get('closure_ok'))} "
                        f"last_ok={bool(last.get('closure_ok'))} last_run={last.get('auto_run_id')}"
                    )
                    if last.get("closure_ok") is True or best.get("closure_ok") is True:
                        args.touch_on_close.parent.mkdir(parents=True, exist_ok=True)
                        args.touch_on_close.write_text(
                            json.dumps(
                                {
                                    "generated_at": iso_now(),
                                    "run_state": str(run_state_path),
                                    "best": best,
                                },
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                        print(f"[{iso_now()}] CLOSED -> {args.touch_on_close}")
                        return 0
            except Exception as e:
                print(f"[{iso_now()}] pid={pid} running={running} run_state=error {e!r}")

        if not running:
            print(f"[{iso_now()}] pid={pid} not running; exiting monitor")
            return 0

        time.sleep(float(args.poll_sec))


if __name__ == "__main__":
    raise SystemExit(main())


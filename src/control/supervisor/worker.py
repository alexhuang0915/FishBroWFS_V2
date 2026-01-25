"""Local Job Orchestrator (Worker Loop).

This is the only supported runtime form of the Supervisor Core in Local mode:
- No HTTP
- No ports
- No external API

It does exactly:
1) poll jobs_v2.db for QUEUED jobs
2) execute handlers via bootstrap workers
3) write back state/progress/artifacts
"""

from __future__ import annotations

import time
import os
from pathlib import Path

from .supervisor import Supervisor
from .db import get_default_db_path
from core.paths import get_numba_cache_root


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="FishBro Supervisor Worker (local, no HTTP)")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to jobs_v2.db (default: outputs/runtime/jobs_v2.db)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Maximum concurrent workers",
    )
    parser.add_argument(
        "--tick-interval",
        type=float,
        default=0.2,
        help="Tick interval in seconds",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Run a single tick and exit (for diagnostics).",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Run until this many jobs are spawned and completed, then exit.",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=None,
        help="Artifacts root directory (default from core.paths)",
    )

    args = parser.parse_args()
    db_path = args.db or get_default_db_path()

    # Ensure numba JIT cache is centralized and writable (disk cache enabled via @njit(cache=True)).
    try:
        numba_dir = get_numba_cache_root()
        numba_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("NUMBA_CACHE_DIR", str(numba_dir))
    except Exception:
        pass

    print("=" * 60)
    print("FISHBRO WORKER INITIALIZING...")
    print(f"DATABASE: {db_path}")
    print(f"MAX WORKERS: {args.max_workers}")
    print(f"TICK INTERVAL: {args.tick_interval}s")
    print("=" * 60)

    sup = Supervisor(
        db_path=db_path,
        max_workers=args.max_workers,
        tick_interval=args.tick_interval,
        artifacts_root=args.artifacts_root,
    )

    def _count_queued() -> int:
        with sup.db._connect() as conn:
            cur = conn.execute("SELECT COUNT(1) AS n FROM jobs WHERE state = 'QUEUED'")
            row = cur.fetchone()
            return int(row["n"]) if row else 0

    def _count_running() -> int:
        with sup.db._connect() as conn:
            cur = conn.execute("SELECT COUNT(1) AS n FROM jobs WHERE state = 'RUNNING'")
            row = cur.fetchone()
            return int(row["n"]) if row else 0

    if args.once:
        sup.tick()
        sup.shutdown()
        return

    max_jobs = int(args.max_jobs) if args.max_jobs is not None else None
    spawned_total = 0
    try:
        while True:
            spawned = sup.tick()
            spawned_total += len(spawned)

            if max_jobs is None:
                time.sleep(sup.tick_interval)
                continue

            # Exit condition for test/CI: we spawned enough jobs and the system drained.
            if spawned_total >= max_jobs and not sup.children and _count_queued() == 0 and _count_running() == 0:
                break

            time.sleep(sup.tick_interval)
    finally:
        sup.shutdown()


if __name__ == "__main__":
    main()

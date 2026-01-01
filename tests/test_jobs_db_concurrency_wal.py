
"""Tests for jobs_db concurrency with WAL mode.

Tests concurrent writes from multiple processes to ensure no database locked errors.
"""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

import os

from control.jobs_db import append_log, create_job, init_db, mark_done, update_running
from control.control_types import DBJobSpec


def _worker(db_path: str, n: int) -> None:
    """Worker function: create job, append log, mark done."""
    p = Path(db_path)
    pid = os.getpid()
    for i in range(n):
        spec = DBJobSpec(
            season="2026Q1",
            dataset_id="test_dataset",
            outputs_root="/tmp/outputs",
            config_snapshot={"test": f"config_{i}"},
            config_hash=f"hash_{i}",
        )
        job_id = create_job(p, spec, tags=["test", f"worker_{i}"])
        append_log(p, job_id, f"hello {i}")
        update_running(p, job_id, pid=pid)  # ✅ 對齊狀態機：QUEUED → RUNNING
        mark_done(p, job_id, run_id=f"R_{i}", report_link=f"/b5?x=y&i={i}")


@pytest.mark.parametrize("n", [50])
def test_jobs_db_concurrent_writes(tmp_path: Path, n: int) -> None:
    """
    Test concurrent writes from multiple processes.
    
    Two processes each create n jobs, append logs, and mark done.
    Should not raise database locked errors.
    """
    db = tmp_path / "jobs.db"
    init_db(db)

    procs = [mp.Process(target=_worker, args=(str(db), n)) for _ in range(2)]
    for pr in procs:
        pr.start()
    for pr in procs:
        pr.join()

    for pr in procs:
        assert pr.exitcode == 0, f"Process {pr.pid} exited with code {pr.exitcode}"



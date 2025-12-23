
"""Smoke test for jobs_db concurrency (WAL + retry + state machine)."""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

from FishBroWFS_V2.control.jobs_db import (
    append_log,
    create_job,
    init_db,
    list_jobs,
    mark_done,
    mark_running,
)
from FishBroWFS_V2.control.types import DBJobSpec


def _proc(db_path: str, n: int) -> None:
    """Worker process: create n jobs and complete them."""
    p = Path(db_path)
    for i in range(n):
        spec = DBJobSpec(
            season="test",
            dataset_id="test",
            outputs_root="outputs",
            config_snapshot={"test": i},
            config_hash=f"hash{i}",
        )
        job_id = create_job(p, spec)
        mark_running(p, job_id, pid=1000 + i)
        append_log(p, job_id, f"hi {i}")
        mark_done(p, job_id, run_id=f"R{i}", report_link=f"/b5?i={i}")


@pytest.mark.parametrize("n", [50])
def test_jobs_db_concurrency_smoke(tmp_path: Path, n: int) -> None:
    """
    Test concurrent job creation and completion across multiple processes.
    
    This test ensures WAL mode, retry logic, and state machine work correctly
    under concurrent access.
    """
    db = tmp_path / "jobs.db"
    init_db(db)

    ps = [mp.Process(target=_proc, args=(str(db), n)) for _ in range(2)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()

    for p in ps:
        assert p.exitcode == 0, f"Process {p.pid} exited with code {p.exitcode}"

    # Verify job count
    jobs = list_jobs(db, limit=1000)
    assert len(jobs) == 2 * n, f"Expected {2 * n} jobs, got {len(jobs)}"

    # Verify all jobs are DONE
    for job in jobs:
        assert job.status.value == "DONE", f"Job {job.job_id} status is {job.status}, expected DONE"



## Discovery for DP4.4 deflake

### Target
- `tests/control/test_build_portfolio_job_lifecycle.py::test_submit_build_portfolio_v2_job`

### Reproduction command
```
FISHBRO_DEFLAKE_REPRO=1 ./.venv/bin/python3 -m pytest -q tests/control/test_build_portfolio_job_lifecycle.py::test_submit_build_portfolio_v2_job
```

### Failure trace
```
tests/control/test_build_portfolio_job_lifecycle.py F                    [100%]

=================================== FAILURES ===================================
______________________ test_submit_build_portfolio_v2_job ______________________
tests/control/test_build_portfolio_job_lifecycle.py:81: in test_submit_build_portfolio_v2_job
    assert job.state == "QUEUED"
E   AssertionError: assert 'RUNNING' == 'QUEUED'
    - QUEUED
    + RUNNING
=========================== short test summary info ============================
FAILED tests/control/test_build_portfolio_job_lifecycle.py::test_submit_build_portfolio_v2_job - AssertionError: assert 'RUNNING' == 'QUEUED'
```

### Nondeterministic point
- `submit()` returns quickly and the test immediately calls `get_job(job_id)` expecting to see the freshly queued record.
- When the supervisor loop (or any concurrent worker) samples the jobs table shortly afterward, it jumps the state from `QUEUED` to `RUNNING`, so `job.state == "QUEUED"` sometimes fails depending on timing.

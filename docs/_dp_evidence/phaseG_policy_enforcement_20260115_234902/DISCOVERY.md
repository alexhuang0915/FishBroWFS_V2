# Discovery

## 3.1 Job submission entrypoints
- `rg -n "submit_job|submit_job_endpoint|POST.*\/api\/v1\/jobs|api\/v1\/jobs" src` (see `rg_submit_job.txt`) resolves to `src/control/api.py` `@api_v1.post("/jobs")`, and the underlying worker submission helper `control.supervisor.submit`. `_create` paths and the DB layer were tracked via `rg_create_job.txt` which includes `control.supervisor.submit`, `SupervisorDB.submit_job`, and `spawn_worker` candidates inside `src/control/supervisor`.

## 3.2 Policy engine & related tests
- `rg -n "\bpolicy\b|gates?|selector|enforce|invariant" src tests` (see `rg_policy.txt`) highlighted existing WFS policy engine (`src/wfs/policy_engine.py`, `run_research_wfs` handler) and the new control enforcement helper at `src/control/policy_enforcement.py`.
- `ls -la tests/policy` (see `ls_tests_policy.txt`) confirmed policy-focused tests reside under `tests/policy/`.
- Additional references from `rg_policy_terms.txt` surfaced `PolicyGateModel`, `policy_check.json`, and policy artifacts under `src/control/reporting`.

## 3.3 Supervisor execution lifecycle states
- `rg -n "RUNNING|SUCCEEDED|FAILED|ABORTED|status.*=" src/control` (see `rg_states.txt`) shows the `jobs` state machine in `control/supervisor/db.py` plus transitions in `control/supervisor/supervisor.py` and handlers. This anchored where postflight verification needed to run.


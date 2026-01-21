Bar Build Guard: Evidence Report
==============================

1. Summary
----------
Successfully implemented a fail-closed guard for Bar Data builds.
- Refactored `shared_cli.py` to use a safe `main()` entry point.
- Updated `BuildDataHandler` to Verify artifact presence after CLI success.
- Fixed a BUG in handler where `season` and correct params were not passed to CLI.

2. Changes
----------
- Modified: src/control/shared_cli.py
- Modified: src/control/supervisor/handlers/build_data.py
- Added: tests/product/control/test_build_data_fail_closed_missing_bars.py

3. Verification
---------------
- Regression Test: tests/product/control/test_build_data_fail_closed_missing_bars.py (PASSED)
- Smoke Test: SMOKE_BARS.txt (PASSED)
- Full Suite: make check-fast (PASSED)

4. Bug Fix Details
------------------
During implementation, discovered that `BuildDataHandler._execute_via_cli` was:
- Not extracting `season`.
- Using incorrect CLI flags (e.g. `--dataset` vs `--dataset-id`).
- Fixed logic to correctly construct CLI command:
  `python -m src.control.shared_cli build --season ... --dataset-id ... --tfs ...`

5. Failure Mode
---------------
Now, if the CLI returns 0 but artifacts are missing (e.g. logic error, wrong path), the job FAILS with:
`ERR_BUILD_ARTIFACTS_MISSING: Subprocess success but artifacts missing`

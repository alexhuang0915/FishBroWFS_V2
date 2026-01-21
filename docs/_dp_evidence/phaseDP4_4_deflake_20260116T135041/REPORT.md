# DP4.4 deflake report

- Root cause: After submitting BUILD_PORTFOLIO_V2 the supervisor can race in, fetch the queued job, and flip its state to RUNNING before the test sees the creation.
- Fix pattern: Pattern A – poll the supervisor DB (max 1s total) until the job record becomes visible so the QUEUED assertion can run against a stable write.
- Determinism rationale: The bounded poll eliminates timing dependence by waiting for the eventual database write and failing with a descriptive message if the job never appears.
- Final commit hash: 11dbc3a5b11548cf430e64eec3b15ca94bdf8b38
- Tests: `python3 -m pytest -q -k test_submit_build_portfolio_v2_job`, `python3 -m pytest -q tests/control`, `make check`

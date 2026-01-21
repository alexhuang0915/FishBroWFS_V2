# REPORT: PING Supervisor Test Deflake

## Root Cause

The `test_ping_integration_smoke` test could hang or "feel stuck" due to two blocking operations:

1. **`supervisor.tick()` blocking in `handle_abort_requests()`** – When aborting a running job, the supervisor waits up to 5 seconds for the worker process to terminate (SIGTERM grace period + SIGKILL).
2. **`supervisor.shutdown()` blocking in `kill_worker()`** – Each worker is given up to 1 second to terminate after SIGTERM, plus a 0.5‑second sleep between SIGTERM and SIGKILL phases.

While these timeouts are intentional for production robustness, they cause the test to appear slow or unresponsive if a worker fails to exit promptly. The test's `wait_until` loop calls `tick()` directly; if `tick()` blocks longer than the loop's interval (0.1 s), the test still waits for the full interval before checking again, extending the total runtime.

## Chosen Test‑Side Fix

We hardened the test **without modifying production code**, preserving the supervisor's existing behavior.

### 1. Bounded Tick Wrapper (`_safe_tick`)
- Runs `supervisor.tick()` in a daemon thread with a hard timeout (default 0.5 s).
- If the thread is still alive after the timeout, raises `AssertionError` with a message that includes the current job state.
- Re‑raises any exception thrown inside `tick()`.

### 2. Bounded Shutdown Wrapper (`_safe_shutdown`)
- Wraps `supervisor.shutdown()` in a daemon thread with a 1.0 s timeout.
- Raises `AssertionError` if shutdown blocks longer.

### 3. Updated Wait Loop
- The predicate `_tick_until_done` now calls `_safe_tick()` instead of raw `supervisor.tick()`.
- The existing `wait_until` timeout (6 s) and interval (0.1 s) remain unchanged.

### 4. Monotonic Timing (Optional Improvement)
- Changed `time.time()` to `time.monotonic()` in `test_ping_execute_quick` to avoid clock‑skew issues.

## Why Deterministic

- The test now has **hard upper bounds** on how long `tick()` and `shutdown()` may block.
- If either operation exceeds its bound, the test fails **fast** (within the timeout) with an explicit error message, rather than hanging until the outer `wait_until` timeout.
- The total test runtime is capped by:
  - `wait_until` timeout (6 s)
  - plus at most one `_safe_tick` timeout (0.5 s)
  - plus `_safe_shutdown` timeout (1.0 s)
  → **worst‑case ~7.5 s**, but typically completes in ~1 s.

## Verification

- All existing PING tests pass (`python3 -m pytest tests/control/test_supervisor_ping_contract_v1.py`).
- All supervisor‑related tests pass (`python3 -m pytest tests/control -k "ping or supervisor"`).
- `make check` passes (see attached `rg_make_check.txt`).

## Files Modified

- `tests/control/test_supervisor_ping_contract_v1.py`
  - Added `_safe_tick` and `_safe_shutdown` helpers inside `test_ping_integration_smoke`.
  - Updated `_tick_until_done` to use `_safe_tick`.
  - Changed `time.time()` → `time.monotonic()` in `test_ping_execute_quick`.

## No Production Changes

The supervisor's `tick()` and `shutdown()` methods remain unchanged; the fix is entirely test‑side, satisfying the requirement "Do NOT change production code behavior unless discovery proves the bug is in production shutdown/tick and the fix is minimal + safe."

## Commit & Push

Single commit: "Test: harden PING supervisor smoke test (bounded tick/shutdown)"

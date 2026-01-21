# DISCOVERY: PING Supervisor Test Deflake

## 1. Files Located

### 1.1 Test File
- **Path**: `tests/control/test_supervisor_ping_contract_v1.py`
- **Relevant test**: `test_ping_integration_smoke` (lines 104-146)
- **Key code**: Creates Supervisor instance, calls `supervisor.tick()` in loop, uses `wait_until` helper

### 1.2 Supervisor Class
- **Path**: `src/control/supervisor/supervisor.py`
- **Class**: `Supervisor`
- **Key methods**:
  - `__init__`: Initializes with db_path, max_workers, tick_interval, artifacts_root
  - `tick()`: Performs one supervisor tick (reap children, handle stale jobs, handle abort requests, spawn workers)
  - `run_forever()`: Starts infinite loop with `self.running = True`, calls tick() in loop
  - `shutdown()`: Stops supervisor, kills workers with SIGTERM then SIGKILL
- **No explicit start/startup method**: Supervisor does not require explicit start; `tick()` works immediately after instantiation. However, `run_forever()` sets `self.running = True` and starts the loop.

### 1.3 Wait Helper
- **Path**: `tests/control/_helpers/job_wait.py`
- **Function**: `wait_until(predicate, timeout_s=5.0, interval_s=0.05, on_timeout_dump=None)`
- **Behavior**: Uses `time.monotonic()` for deadline, sleeps in intervals, calls predicate each iteration. On timeout, raises `AssertionError` with optional dump.

## 2. Supervisor API Analysis

### 2.1 Start Semantics
- **Observation**: Supervisor can be used in two ways:
  1. **Manual ticking**: Call `supervisor.tick()` directly (as in tests)
  2. **Background loop**: Call `supervisor.run_forever()` which starts a background thread/loop
- **Current test usage**: Uses manual ticking (`supervisor.tick()` inside `_tick_until_done`)
- **No context manager**: Supervisor does not implement `__enter__`/`__exit__`
- **No start() method**: No explicit start required for manual ticking

### 2.2 Potential Blocking Points
1. **`supervisor.tick()`**:
   - Calls `self.reap_children()` (non-blocking, uses `poll()`)
   - Calls `self.handle_stale_jobs()` (non-blocking, DB queries)
   - Calls `self.handle_abort_requests()` (may call `os.killpg` with timeout up to 5 seconds)
   - Calls `self.spawn_worker()` (subprocess.Popen, could block if system resource constrained)
   - **Risk**: `handle_abort_requests` may sleep up to 5 seconds waiting for process termination.

2. **`supervisor.shutdown()`**:
   - Sends SIGTERM to all children, waits 0.5 seconds, then SIGKILL
   - Uses `self.kill_worker()` which may block up to 1 second per worker
   - **Risk**: Could block indefinitely if child process ignores signals.

### 2.3 Test-Side Issues
- **Current test**: Calls `supervisor.tick()` directly in predicate; if tick blocks > interval_s (0.1s), wait_until will still sleep interval_s but predicate evaluation will be delayed.
- **No timeout on tick**: If tick blocks indefinitely, test will hang until wait_until timeout (6 seconds) then raise AssertionError with dump.
- **Shutdown after test**: `supervisor.shutdown()` called without timeout; could block indefinitely.

## 3. Canonical Patterns Found

### 3.1 Other Test Usage
Examined other test files (`test_supervisor_handler_clean_cache_v1.py`, `test_supervisor_handler_build_data_v1.py`):
- All use same pattern: instantiate Supervisor, call tick() in loop, wait_until, then shutdown.
- No explicit start/startup calls.
- No context manager usage.

### 3.2 Supervisor Lifecycle in Production
- `run_forever()` used by CLI entry point (`main()`).
- Supervisor runs as daemon with infinite loop.
- Shutdown via KeyboardInterrupt or SIGTERM.

## 4. Recommendations for Test Hardening

### 4.1 Supervisor Start
- **No change needed**: Manual ticking works without explicit start.
- **Consider**: Ensure supervisor is "ready" (no internal state requiring initialization beyond __init__).

### 4.2 Bounded Tick Wrapper
- Implement `_safe_tick(supervisor, timeout_s=0.5)` using daemon thread.
- Raise `AssertionError` with job state dump if tick blocks > timeout.

### 4.3 Bounded Shutdown
- Wrap `supervisor.shutdown()` in thread with timeout (1.0s).
- Fail fast with explicit message.

### 4.4 Wait Loop Improvements
- Keep existing `wait_until` with timeout 6s, interval 0.1s.
- Replace direct `supervisor.tick()` with `_safe_tick()`.

### 4.5 Monotonic Timing
- `wait_until` already uses `time.monotonic()`.
- Test uses `time.time()` for elapsed measurement; consider switching to `time.monotonic()`.

## 5. Evidence of Blocking Risks

From supervisor.py:
- `handle_abort_requests()` lines 214-236: while loop with sleep up to 5 seconds waiting for process death.
- `kill_worker()` lines 129-133: `proc.wait(timeout=1.0)` could block up to 1 second.
- `shutdown()` lines 302-303: `time.sleep(0.5)` between SIGTERM and SIGKILL.

These are intentional delays but could cause test to "feel stuck" if multiple workers exist.

## 6. Conclusion

The test can hang if:
1. `supervisor.tick()` blocks in `handle_abort_requests` (up to 5s)
2. `supervisor.shutdown()` blocks in `kill_worker` (up to 1s per worker)

Test-side hardening with bounded timeouts will ensure test fails fast with explicit message rather than hanging.

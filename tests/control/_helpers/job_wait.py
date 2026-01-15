from __future__ import annotations

import time
from typing import Callable, Optional


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_s: float = 5.0,
    interval_s: float = 0.05,
    on_timeout_dump: Optional[Callable[[], str]] = None,
) -> None:
    """
    Wait until predicate returns True or raise AssertionError on timeout.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval_s)

    dump = ""
    if on_timeout_dump:
        try:
            dump = on_timeout_dump()
        except Exception as exc:  # pragma: no cover - best-effort debug output
            dump = f"dump_error={exc}"

    message = "wait_until timeout"
    if dump:
        message = f"{message}: {dump}"
    raise AssertionError(message)

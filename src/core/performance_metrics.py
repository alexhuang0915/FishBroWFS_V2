from __future__ import annotations

from typing import Iterable


def max_underwater_days(equity: Iterable[float]) -> int:
    """
    Return the maximum drawdown duration in *bars* of the provided equity series.

    Caller is responsible for ensuring the equity series is sampled at "1 point per trading day"
    if they want the result to represent trading days.
    """
    peak = None
    current = 0
    best = 0

    for x in equity:
        try:
            v = float(x)
        except Exception:
            continue

        if peak is None:
            peak = v
            current = 0
            continue

        if v >= peak:
            peak = v
            current = 0
            continue

        current += 1
        if current > best:
            best = current

    return int(best)


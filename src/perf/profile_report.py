
from __future__ import annotations

import cProfile
import io
import os
import pstats


def _format_profile_report(
    lane_id: str,
    n_bars: int,
    n_params: int,
    jit_enabled: bool,
    sort_params: bool,
    topn: int,
    mode: str,
    pr: cProfile.Profile,
) -> str:
    """
    Format a deterministic profile report string for perf harness.

    Contract:
    - Always includes __PROFILE_START__/__PROFILE_END__ markers.
    - Always includes the 'pstats sort: cumtime' header even if no stats exist.
    - Must not throw when the profile has no collected stats (empty Profile).
    """
    s = io.StringIO()
    s.write("__PROFILE_START__\n")
    s.write(f"lane_id={lane_id}\n")
    s.write(f"bars={n_bars} params={n_params}\n")
    s.write(f"jit_enabled={jit_enabled} sort_params={sort_params}\n")
    s.write(f"pid={os.getpid()}\n")
    if mode is not None:
        s.write(f"mode={mode}\n")
    s.write("\n")

    # Always emit the headers so tests can rely on markers/labels.
    s.write(f"== pstats sort: cumtime (top {topn}) ==\n")
    try:
        ps = pstats.Stats(pr, stream=s).strip_dirs()
        ps.sort_stats("cumtime")
        ps.print_stats(topn)
    except TypeError:
        s.write("(no profile stats collected)\n")

    s.write("\n\n")
    s.write(f"== pstats sort: tottime (top {topn}) ==\n")
    try:
        ps = pstats.Stats(pr, stream=s).strip_dirs()
        ps.sort_stats("tottime")
        ps.print_stats(topn)
    except TypeError:
        s.write("(no profile stats collected)\n")

    s.write("\n\n__PROFILE_END__\n")
    return s.getvalue()



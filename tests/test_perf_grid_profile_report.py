from __future__ import annotations

import cProfile

from FishBroWFS_V2.perf.profile_report import _format_profile_report


def test_profile_report_markers_present() -> None:
    pr = cProfile.Profile()
    pr.enable()
    _ = sum(range(10_000))  # tiny workload, deterministic
    pr.disable()
    report = _format_profile_report(
        lane_id="3",
        n_bars=2000,
        n_params=100,
        jit_enabled=True,
        sort_params=False,
        topn=10,
        mode="",
        pr=pr,
    )
    assert "__PROFILE_START__" in report
    assert "pstats sort: cumtime" in report
    assert "__PROFILE_END__" in report



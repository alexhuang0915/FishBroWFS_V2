"""
Freeze test for JobType enum.

Ensures the canonical job type list is stable and matches the frozen set.
"""

from control.supervisor.models import JobType


def test_job_type_enum_frozen():
    """Assert that JobType enum contains exactly the canonical set."""
    expected = {
        "BUILD_DATA",
        "BUILD_PORTFOLIO_V2",
        "CLEAN_CACHE",
        "GENERATE_REPORTS",
        "PING",
        "RUN_COMPILE_V2",
        "RUN_FREEZE_V2",
        "RUN_PLATEAU_V2",
        "RUN_RESEARCH_V2",
        "RUN_RESEARCH_WFS",  # Phase4-A: Walk-Forward Simulation research
        "RUN_PORTFOLIO_ADMISSION",  # Phase4-B: Portfolio Admission analysis
    }
    actual = {t.value for t in JobType}
    assert actual == expected, f"JobType mismatch: expected {expected}, got {actual}"
    # Ensure no extra values
    assert len(JobType) == len(expected), f"JobType length mismatch"


def test_job_type_normalization():
    """Test that normalize_job_type maps legacy aliases to canonical values."""
    from control.supervisor.models import normalize_job_type
    
    # Direct enum values
    assert normalize_job_type("BUILD_DATA") == JobType.BUILD_DATA
    assert normalize_job_type("PING") == JobType.PING
    
    # Legacy aliases
    assert normalize_job_type("RUN_RESEARCH") == JobType.RUN_RESEARCH_V2
    assert normalize_job_type("RUN_PLATEAU") == JobType.RUN_PLATEAU_V2
    assert normalize_job_type("RUN_FREEZE") == JobType.RUN_FREEZE_V2
    assert normalize_job_type("RUN_COMPILE") == JobType.RUN_COMPILE_V2
    assert normalize_job_type("BUILD_PORTFOLIO") == JobType.BUILD_PORTFOLIO_V2
    
    # Case-insensitive
    assert normalize_job_type("run_research") == JobType.RUN_RESEARCH_V2
    assert normalize_job_type("Run_Research") == JobType.RUN_RESEARCH_V2
    
    # Invalid job type raises ValueError
    import pytest
    with pytest.raises(ValueError, match="Invalid job type"):
        normalize_job_type("UNKNOWN_JOB_TYPE")
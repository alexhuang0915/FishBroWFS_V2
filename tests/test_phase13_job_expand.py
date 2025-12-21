"""Unit tests for job_expand module (Phase 13)."""

import pytest
from FishBroWFS_V2.control.param_grid import GridMode, ParamGridSpec
from FishBroWFS_V2.control.job_expand import JobTemplate, expand_job_template, estimate_total_jobs, validate_template
from FishBroWFS_V2.control.job_spec import WFSSpec


def test_job_template_creation():
    """JobTemplate creation and serialization."""
    param_grid = {
        "param1": ParamGridSpec(mode=GridMode.SINGLE, single_value=10),
        "param2": ParamGridSpec(mode=GridMode.RANGE, range_start=0, range_end=2, range_step=1),
    }
    wfs = WFSSpec(stage0_subsample=0.5, top_k=100, mem_limit_mb=2048, allow_auto_downsample=True)
    template = JobTemplate(
        season="2024Q1",
        dataset_id="CME_MNQ_v2",
        strategy_id="my_strategy",
        param_grid=param_grid,
        wfs=wfs
    )
    assert template.season == "2024Q1"
    assert template.dataset_id == "CME_MNQ_v2"
    assert template.strategy_id == "my_strategy"
    assert len(template.param_grid) == 2
    assert template.wfs == wfs


def test_expand_job_template_single():
    """Expand single parameter."""
    param_grid = {
        "p": ParamGridSpec(mode=GridMode.SINGLE, single_value=42),
    }
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    jobs = list(expand_job_template(template))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.season == "2024Q1"
    assert job.dataset_id == "test"
    assert job.strategy_id == "s"
    assert job.params == {"p": 42}


def test_expand_job_template_range():
    """Expand range parameter."""
    param_grid = {
        "p": ParamGridSpec(mode=GridMode.RANGE, range_start=1, range_end=3, range_step=1),
    }
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    jobs = list(expand_job_template(template))
    assert len(jobs) == 3
    values = [job.params["p"] for job in jobs]
    assert values == [1, 2, 3]
    # Order should be deterministic (sorted by param name, then values)
    assert jobs[0].params["p"] == 1
    assert jobs[1].params["p"] == 2
    assert jobs[2].params["p"] == 3


def test_expand_job_template_multi():
    """Expand multi values parameter."""
    param_grid = {
        "p": ParamGridSpec(mode=GridMode.MULTI, multi_values=["a", "b", "c"]),
    }
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    jobs = list(expand_job_template(template))
    assert len(jobs) == 3
    values = [job.params["p"] for job in jobs]
    assert values == ["a", "b", "c"]


def test_expand_job_template_two_params():
    """Expand two parameters (cartesian product)."""
    param_grid = {
        "p1": ParamGridSpec(mode=GridMode.RANGE, range_start=1, range_end=2, range_step=1),
        "p2": ParamGridSpec(mode=GridMode.MULTI, multi_values=["x", "y"]),
    }
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    jobs = list(expand_job_template(template))
    assert len(jobs) == 4  # 2 * 2
    # Order: param names sorted alphabetically, then values
    # p1 values: 1,2 ; p2 values: x,y
    # Expected order: (p1=1, p2=x), (p1=1, p2=y), (p1=2, p2=x), (p1=2, p2=y)
    expected = [
        {"p1": 1, "p2": "x"},
        {"p1": 1, "p2": "y"},
        {"p1": 2, "p2": "x"},
        {"p1": 2, "p2": "y"},
    ]
    for i, job in enumerate(jobs):
        assert job.params == expected[i]


def test_estimate_total_jobs():
    """Estimate total jobs count."""
    param_grid = {
        "p1": ParamGridSpec(mode=GridMode.RANGE, range_start=1, range_end=10, range_step=1),  # 10 values
        "p2": ParamGridSpec(mode=GridMode.MULTI, multi_values=["a", "b", "c"]),  # 3 values
        "p3": ParamGridSpec(mode=GridMode.SINGLE, single_value=99),  # 1 value
    }
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    total = estimate_total_jobs(template)
    assert total == 10 * 3 * 1  # 30


def test_validate_template_ok():
    """Valid template passes."""
    param_grid = {
        "p": ParamGridSpec(mode=GridMode.SINGLE, single_value=5),
    }
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    validate_template(template)  # no exception


def test_validate_template_empty_param_grid():
    """Empty param grid raises."""
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="s",
        param_grid={},
        wfs=WFSSpec()
    )
    with pytest.raises(ValueError, match="param_grid cannot be empty"):
        validate_template(template)


def test_validate_template_missing_season():
    """Missing season raises."""
    param_grid = {"p": ParamGridSpec(mode=GridMode.SINGLE, single_value=1)}
    template = JobTemplate(
        season="",
        dataset_id="test",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    with pytest.raises(ValueError, match="season must be non-empty"):
        validate_template(template)


def test_validate_template_missing_dataset_id():
    """Missing dataset_id raises."""
    param_grid = {"p": ParamGridSpec(mode=GridMode.SINGLE, single_value=1)}
    template = JobTemplate(
        season="2024Q1",
        dataset_id="",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    with pytest.raises(ValueError, match="dataset_id must be non-empty"):
        validate_template(template)


def test_validate_template_missing_strategy_id():
    """Missing strategy_id raises."""
    param_grid = {"p": ParamGridSpec(mode=GridMode.SINGLE, single_value=1)}
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    with pytest.raises(ValueError, match="strategy_id must be non-empty"):
        validate_template(template)


def test_validate_template_param_grid_invalid():
    """ParamGrid validation errors propagate."""
    param_grid = {
        "p": ParamGridSpec(mode=GridMode.RANGE, range_start=10, range_end=0, range_step=1),  # invalid
    }
    template = JobTemplate(
        season="2024Q1",
        dataset_id="test",
        strategy_id="s",
        param_grid=param_grid,
        wfs=WFSSpec()
    )
    with pytest.raises(ValueError, match="start <= end"):
        validate_template(template)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
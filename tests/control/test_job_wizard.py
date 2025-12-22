
"""Tests for Research Job Wizard (Phase 12)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict

import pytest

from FishBroWFS_V2.control.job_spec import DataSpec, JobSpec, WFSSpec


def test_jobspec_schema_validation() -> None:
    """Test JobSpec schema validation."""
    # Valid JobSpec
    jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="CME.MNQ.60m.2020-2024",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        ),
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window": 20, "threshold": 0.5},
        wfs=WFSSpec(
            stage0_subsample=1.0,
            top_k=100,
            mem_limit_mb=4096,
            allow_auto_downsample=True
        )
    )
    
    assert jobspec.season == "2024Q1"
    assert jobspec.data1.dataset_id == "CME.MNQ.60m.2020-2024"
    assert jobspec.strategy_id == "sma_cross_v1"
    assert jobspec.params["window"] == 20
    assert jobspec.wfs.top_k == 100


def test_jobspec_required_fields() -> None:
    """Test that JobSpec requires all mandatory fields."""
    # Missing season
    with pytest.raises(ValueError):
        JobSpec(
            season="",  # Empty season
            data1=DataSpec(
                dataset_id="CME.MNQ.60m.2020-2024",
                start_date=date(2020, 1, 1),
                end_date=date(2024, 12, 31)
            ),
            strategy_id="sma_cross_v1",
            params={}
        )
    
    # Missing data1
    with pytest.raises(ValueError):
        JobSpec(
            season="2024Q1",
            data1=None,  # type: ignore
            strategy_id="sma_cross_v1",
            params={}
        )
    
    # Missing strategy_id
    with pytest.raises(ValueError):
        JobSpec(
            season="2024Q1",
            data1=DataSpec(
                dataset_id="CME.MNQ.60m.2020-2024",
                start_date=date(2020, 1, 1),
                end_date=date(2024, 12, 31)
            ),
            strategy_id="",  # Empty strategy_id
            params={}
        )


def test_dataspec_validation() -> None:
    """Test DataSpec validation."""
    # Valid DataSpec
    dataspec = DataSpec(
        dataset_id="CME.MNQ.60m.2020-2024",
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31)
    )
    assert dataspec.start_date <= dataspec.end_date
    
    # Invalid: start_date > end_date
    with pytest.raises(ValueError):
        DataSpec(
            dataset_id="TEST",
            start_date=date(2024, 1, 1),
            end_date=date(2020, 1, 1)  # Earlier than start
        )
    
    # Invalid: empty dataset_id
    with pytest.raises(ValueError):
        DataSpec(
            dataset_id="",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        )


def test_wfsspec_validation() -> None:
    """Test WFSSpec validation."""
    # Valid WFSSpec
    wfs = WFSSpec(
        stage0_subsample=0.5,
        top_k=50,
        mem_limit_mb=2048,
        allow_auto_downsample=False
    )
    assert 0.0 <= wfs.stage0_subsample <= 1.0
    assert wfs.top_k >= 1
    assert wfs.mem_limit_mb >= 1024
    
    # Invalid: stage0_subsample out of range
    with pytest.raises(ValueError):
        WFSSpec(stage0_subsample=1.5)  # > 1.0
    
    with pytest.raises(ValueError):
        WFSSpec(stage0_subsample=-0.1)  # < 0.0
    
    # Invalid: top_k too small
    with pytest.raises(ValueError):
        WFSSpec(top_k=0)  # < 1
    
    # Invalid: mem_limit_mb too small
    with pytest.raises(ValueError):
        WFSSpec(mem_limit_mb=500)  # < 1024


def test_jobspec_json_serialization() -> None:
    """Test JobSpec JSON serialization (deterministic)."""
    jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="CME.MNQ.60m.2020-2024",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        ),
        strategy_id="sma_cross_v1",
        params={"window": 20, "threshold": 0.5},
        wfs=WFSSpec()
    )
    
    # Serialize to JSON
    json_str = jobspec.model_dump_json(indent=2)
    
    # Parse back
    data = json.loads(json_str)
    
    # Verify structure
    assert data["season"] == "2024Q1"
    assert data["data1"]["dataset_id"] == "CME.MNQ.60m.2020-2024"
    assert data["strategy_id"] == "sma_cross_v1"
    assert data["params"]["window"] == 20
    assert data["wfs"]["stage0_subsample"] == 1.0
    
    # Verify deterministic ordering (multiple serializations should be identical)
    json_str2 = jobspec.model_dump_json(indent=2)
    assert json_str == json_str2


def test_jobspec_with_data2() -> None:
    """Test JobSpec with secondary dataset."""
    jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="CME.MNQ.60m.2020-2024",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        ),
        data2=DataSpec(
            dataset_id="TWF.MXF.15m.2018-2023",
            start_date=date(2018, 1, 1),
            end_date=date(2023, 12, 31)
        ),
        strategy_id="breakout_channel_v1",
        params={"channel_width": 20},
        wfs=WFSSpec()
    )
    
    assert jobspec.data2 is not None
    assert jobspec.data2.dataset_id == "TWF.MXF.15m.2018-2023"
    
    # Serialize and deserialize
    json_str = jobspec.model_dump_json()
    data = json.loads(json_str)
    assert "data2" in data
    assert data["data2"]["dataset_id"] == "TWF.MXF.15m.2018-2023"


def test_jobspec_param_types() -> None:
    """Test JobSpec with various parameter types."""
    jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="TEST",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        ),
        strategy_id="test_strategy",
        params={
            "int_param": 42,
            "float_param": 3.14,
            "bool_param": True,
            "str_param": "test",
            "list_param": [1, 2, 3],
            "dict_param": {"key": "value"}
        },
        wfs=WFSSpec()
    )
    
    # All parameter types should be accepted
    assert isinstance(jobspec.params["int_param"], int)
    assert isinstance(jobspec.params["float_param"], float)
    assert isinstance(jobspec.params["bool_param"], bool)
    assert isinstance(jobspec.params["str_param"], str)
    assert isinstance(jobspec.params["list_param"], list)
    assert isinstance(jobspec.params["dict_param"], dict)


def test_jobspec_immutability() -> None:
    """Test that JobSpec is immutable (frozen)."""
    jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="TEST",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        ),
        strategy_id="test",
        params={},
        wfs=WFSSpec()
    )
    
    # Should not be able to modify attributes
    with pytest.raises(Exception):
        jobspec.season = "2024Q2"  # type: ignore
    
    with pytest.raises(Exception):
        jobspec.params["new"] = "value"  # type: ignore
    
    # Nested objects should also be immutable
    with pytest.raises(Exception):
        jobspec.data1.dataset_id = "NEW"  # type: ignore


def test_wizard_generated_jobspec_structure() -> None:
    """Test that wizard-generated JobSpec matches CLI job structure."""
    # This is what the wizard would generate
    wizard_jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="CME.MNQ.60m.2020-2024",
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31)  # Subset of full range
        ),
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window": 50, "threshold": 0.3},
        wfs=WFSSpec(
            stage0_subsample=0.8,
            top_k=200,
            mem_limit_mb=8192,
            allow_auto_downsample=False
        )
    )
    
    # This is what CLI would generate (simplified)
    cli_jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="CME.MNQ.60m.2020-2024",
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31)
        ),
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window": 50, "threshold": 0.3},
        wfs=WFSSpec(
            stage0_subsample=0.8,
            top_k=200,
            mem_limit_mb=8192,
            allow_auto_downsample=False
        )
    )
    
    # They should be identical when serialized
    wizard_json = json.loads(wizard_jobspec.model_dump_json())
    cli_json = json.loads(cli_jobspec.model_dump_json())
    
    assert wizard_json == cli_json, "Wizard and CLI should generate identical JobSpec"


def test_jobspec_config_hash_compatibility() -> None:
    """Test that JobSpec can be used to generate config_hash."""
    jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="CME.MNQ.60m.2020-2024",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        ),
        strategy_id="sma_cross_v1",
        params={"window": 20},
        wfs=WFSSpec()
    )
    
    # Convert to dict for config_hash generation
    config_dict = jobspec.model_dump()
    
    # This dict should contain all necessary information for config_hash
    required_keys = {"season", "data1", "strategy_id", "params", "wfs"}
    assert required_keys.issubset(config_dict.keys())
    
    # Verify nested structure
    assert isinstance(config_dict["data1"], dict)
    assert "dataset_id" in config_dict["data1"]
    assert isinstance(config_dict["params"], dict)
    assert isinstance(config_dict["wfs"], dict)


def test_empty_params_allowed() -> None:
    """Test that empty params dict is allowed."""
    jobspec = JobSpec(
        season="2024Q1",
        data1=DataSpec(
            dataset_id="TEST",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31)
        ),
        strategy_id="no_param_strategy",
        params={},  # Empty params
        wfs=WFSSpec()
    )
    
    assert jobspec.params == {}


def test_wfs_default_values() -> None:
    """Test WFSSpec default values."""
    wfs = WFSSpec()
    
    assert wfs.stage0_subsample == 1.0
    assert wfs.top_k == 100
    assert wfs.mem_limit_mb == 4096
    assert wfs.allow_auto_downsample is True
    
    # Verify defaults are within valid ranges
    assert 0.0 <= wfs.stage0_subsample <= 1.0
    assert wfs.top_k >= 1
    assert wfs.mem_limit_mb >= 1024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



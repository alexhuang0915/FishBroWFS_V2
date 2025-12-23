"""
Test that the control module does not export ambiguous JobSpec.

P0-1: Ensure WizardJobSpec and DBJobSpec are properly separated,
and the ambiguous 'JobSpec' name is not exported.
"""

import FishBroWFS_V2.control as control_module


def test_control_no_ambiguous_jobspec() -> None:
    """Verify that control module exports only WizardJobSpec and DBJobSpec, not JobSpec."""
    # Must NOT have JobSpec
    assert not hasattr(control_module, "JobSpec"), (
        "control module must not export 'JobSpec' (ambiguous name)"
    )
    
    # Must have WizardJobSpec
    assert hasattr(control_module, "WizardJobSpec"), (
        "control module must export 'WizardJobSpec'"
    )
    
    # Must have DBJobSpec
    assert hasattr(control_module, "DBJobSpec"), (
        "control module must export 'DBJobSpec'"
    )
    
    # Verify they are different classes
    from FishBroWFS_V2.control.job_spec import WizardJobSpec
    from FishBroWFS_V2.control.types import DBJobSpec
    
    assert control_module.WizardJobSpec is WizardJobSpec
    assert control_module.DBJobSpec is DBJobSpec
    assert WizardJobSpec is not DBJobSpec


def test_jobspec_import_paths() -> None:
    """Verify that import statements work correctly after the rename."""
    # These imports should succeed
    from FishBroWFS_V2.control.job_spec import WizardJobSpec
    from FishBroWFS_V2.control.types import DBJobSpec
    
    # Verify class attributes
    assert WizardJobSpec.__name__ == "WizardJobSpec"
    assert DBJobSpec.__name__ == "DBJobSpec"
    
    # Verify that JobSpec cannot be imported from control module
    import pytest
    with pytest.raises(ImportError):
        # Attempt to import JobSpec from control (should fail)
        from FishBroWFS_V2.control import JobSpec  # type: ignore


def test_jobspec_usage_scenarios() -> None:
    """Quick sanity check that the two specs are used as intended."""
    from datetime import date
    from FishBroWFS_V2.control.job_spec import WizardJobSpec, DataSpec, WFSSpec
    from FishBroWFS_V2.control.types import DBJobSpec
    
    # WizardJobSpec is Pydantic-based, should have model_config
    wizard = WizardJobSpec(
        season="2026Q1",
        data1=DataSpec(
            dataset_id="test_dataset",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
        ),
        data2=None,
        strategy_id="test_strategy",
        params={"window": 20},
        wfs=WFSSpec(),
    )
    assert wizard.season == "2026Q1"
    assert wizard.dataset_id == "test_dataset"  # alias property
    # params may be a mappingproxy due to frozen model, but should behave like dict
    assert hasattr(wizard.params, "get")
    assert wizard.params.get("window") == 20
    
    # DBJobSpec is a dataclass
    db_spec = DBJobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root="/tmp/outputs",
        config_snapshot={"window": 20},
        config_hash="abc123",
        data_fingerprint_sha256_40="fingerprint1234567890123456789012345678901234567890",
    )
    assert db_spec.season == "2026Q1"
    assert db_spec.data_fingerprint_sha256_40.startswith("fingerprint")
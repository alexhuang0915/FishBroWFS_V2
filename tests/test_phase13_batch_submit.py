
"""Unit tests for batch_submit module (Phase 13)."""

import pytest
from FishBroWFS_V2.control.batch_submit import (
    BatchSubmitRequest,
    BatchSubmitResponse,
    compute_batch_id,
    wizard_to_db_jobspec,
    submit_batch,
)
from FishBroWFS_V2.control.job_spec import WizardJobSpec, DataSpec, WFSSpec
from FishBroWFS_V2.control.types import DBJobSpec
from datetime import date


def test_batch_submit_request():
    """BatchSubmitRequest creation."""
    jobs = [
        WizardJobSpec(
            season="2024Q1",
            data1=DataSpec(dataset_id="test", start_date=date(2020,1,1), end_date=date(2020,12,31)),
            strategy_id="s1",
            params={"p": 1},
            wfs=WFSSpec()
        ),
        WizardJobSpec(
            season="2024Q1",
            data1=DataSpec(dataset_id="test", start_date=date(2020,1,1), end_date=date(2020,12,31)),
            strategy_id="s1",
            params={"p": 2},
            wfs=WFSSpec()
        ),
    ]
    req = BatchSubmitRequest(jobs=jobs)
    assert len(req.jobs) == 2
    assert req.jobs[0].params["p"] == 1
    assert req.jobs[1].params["p"] == 2


def test_batch_submit_response():
    """BatchSubmitResponse creation."""
    resp = BatchSubmitResponse(
        batch_id="batch-123",
        total_jobs=5,
        job_ids=["job1", "job2", "job3", "job4", "job5"]
    )
    assert resp.batch_id == "batch-123"
    assert resp.total_jobs == 5
    assert len(resp.job_ids) == 5


def test_compute_batch_id_deterministic():
    """Batch ID is deterministic based on sorted JobSpec JSON."""
    jobs = [
        WizardJobSpec(
            season="2024Q1",
            data1=DataSpec(dataset_id="test", start_date=date(2020,1,1), end_date=date(2020,12,31)),
            strategy_id="s1",
            params={"a": 1, "b": 2},
            wfs=WFSSpec()
        ),
        WizardJobSpec(
            season="2024Q1",
            data1=DataSpec(dataset_id="test", start_date=date(2020,1,1), end_date=date(2020,12,31)),
            strategy_id="s1",
            params={"a": 3, "b": 4},
            wfs=WFSSpec()
        ),
    ]
    batch_id1 = compute_batch_id(jobs)
    # Same jobs, different order should produce same batch ID
    jobs_reversed = list(reversed(jobs))
    batch_id2 = compute_batch_id(jobs_reversed)
    assert batch_id1 == batch_id2
    # Different jobs produce different ID
    jobs2 = [jobs[0]]
    batch_id3 = compute_batch_id(jobs2)
    assert batch_id1 != batch_id3


def test_wizard_to_db_jobspec():
    """Convert Wizard JobSpec to DB JobSpec."""
    wizard_spec = WizardJobSpec(
        season="2024Q1",
        data1=DataSpec(dataset_id="CME_MNQ_v2", start_date=date(2020,1,1), end_date=date(2020,12,31)),
        strategy_id="my_strategy",
        params={"param1": 42},
        wfs=WFSSpec(stage0_subsample=0.5, top_k=100, mem_limit_mb=2048, allow_auto_downsample=True)
    )
    # Mock dataset record with fingerprint
    dataset_record = {
        "fingerprint_sha256_40": "abc123def456ghi789jkl012mno345pqr678stu901",
        "normalized_sha256_40": "abc123def456ghi789jkl012mno345pqr678stu901"
    }
    db_spec = wizard_to_db_jobspec(wizard_spec, dataset_record)
    assert isinstance(db_spec, DBJobSpec)
    assert db_spec.season == "2024Q1"
    assert db_spec.dataset_id == "CME_MNQ_v2"
    assert db_spec.outputs_root == "outputs/seasons/2024Q1/runs"
    # config_snapshot should contain params and wfs
    config = db_spec.config_snapshot
    assert config["params"]["param1"] == 42
    assert config["wfs"]["stage0_subsample"] == 0.5
    assert config["wfs"]["top_k"] == 100
    # config_hash should be non-empty
    assert db_spec.config_hash
    assert db_spec.created_by == "wizard_batch"
    # fingerprint should be set
    assert db_spec.data_fingerprint_sha256_40 == "abc123def456ghi789jkl012mno345pqr678stu901"


def test_submit_batch_mocked(monkeypatch):
    """Test submit_batch with mocked DB calls."""
    # Mock create_job to return predictable job IDs
    job_ids = ["job-a", "job-b", "job-c"]
    call_count = 0
    def mock_create_job(db_path, spec):
        nonlocal call_count
        # Ensure spec is DBJobSpec
        assert isinstance(spec, DBJobSpec)
        # Return sequential ID
        result = job_ids[call_count]
        call_count += 1
        return result
    
    import FishBroWFS_V2.control.batch_submit as batch_module
    monkeypatch.setattr(batch_module, "create_job", mock_create_job)
    
    # Prepare request
    jobs = [
        WizardJobSpec(
            season="2024Q1",
            data1=DataSpec(dataset_id="test", start_date=date(2020,1,1), end_date=date(2020,12,31)),
            strategy_id="s1",
            params={"p": i},
            wfs=WFSSpec()
        ) for i in range(3)
    ]
    req = BatchSubmitRequest(jobs=jobs)
    
    # Mock dataset index
    dataset_index = {
        "test": {
            "fingerprint_sha256_40": "abc123def456ghi789jkl012mno345pqr678stu901",
            "normalized_sha256_40": "abc123def456ghi789jkl012mno345pqr678stu901"
        }
    }
    
    # Call submit_batch with dummy db_path
    from pathlib import Path
    db_path = Path("/tmp/test.db")
    resp = submit_batch(db_path, req, dataset_index)
    
    assert resp.batch_id.startswith("batch-")
    assert resp.total_jobs == 3
    assert resp.job_ids == job_ids
    assert call_count == 3


def test_submit_batch_empty_jobs():
    """Empty jobs list raises."""
    req = BatchSubmitRequest(jobs=[])
    from pathlib import Path
    db_path = Path("/tmp/test.db")
    dataset_index = {"test": {"fingerprint_sha256_40": "abc123"}}
    with pytest.raises(ValueError, match="jobs list cannot be empty"):
        submit_batch(db_path, req, dataset_index)


def test_submit_batch_too_many_jobs():
    """Jobs exceed cap raises."""
    jobs = [
        WizardJobSpec(
            season="2024Q1",
            data1=DataSpec(dataset_id="test", start_date=date(2020,1,1), end_date=date(2020,12,31)),
            strategy_id="s1",
            params={"p": i},
            wfs=WFSSpec()
        ) for i in range(1001)  # exceed default cap of 1000
    ]
    req = BatchSubmitRequest(jobs=jobs)
    from pathlib import Path
    db_path = Path("/tmp/test.db")
    dataset_index = {"test": {"fingerprint_sha256_40": "abc123"}}
    with pytest.raises(ValueError, match="exceeds maximum"):
        submit_batch(db_path, req, dataset_index)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



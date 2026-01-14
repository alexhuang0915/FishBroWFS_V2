"""
Tests for Data Prepare Service (Route 4).

Tests the explicit data preparation workflow with progress reporting,
artifact persistence, and integration with DatasetResolver.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from gui.services.data_prepare_service import (
    DataPrepareService,
    PrepareStatus,
    PrepareResult,
    get_data_prepare_service,
)
from gui.services.dataset_resolver import DerivedDatasets, DatasetStatus


class TestDataPrepareService:
    """Test DataPrepareService functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary directory for outputs
        self.temp_dir = tempfile.mkdtemp()
        self.outputs_root = Path(self.temp_dir) / "outputs"
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        
        # Create service with test outputs root
        self.service = DataPrepareService(outputs_root=self.outputs_root)
        
        # Mock DerivedDatasets for testing
        self.derived_datasets = DerivedDatasets(
            data1_id="CME.MNQ.60m",
            data2_id="CME.ES.60m",
            mapping_reason="Test mapping",
            data1_status=DatasetStatus.MISSING,
            data2_status=DatasetStatus.STALE,
            data1_min_date="2020-01-01",
            data1_max_date="2024-12-31",
            data2_min_date="2020-01-01",
            data2_max_date="2024-12-31",
        )
    
    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init(self):
        """Test service initialization."""
        assert self.service.outputs_root == self.outputs_root
        assert self.service.prepare_artifacts_dir.exists()
        assert self.service.prepare_artifacts_dir.name == "data_prepare"
        assert isinstance(self.service._active_preparations, dict)
        assert isinstance(self.service._prepare_results, dict)
    
    def test_get_prepare_status_no_result(self):
        """Test get_prepare_status when no result exists."""
        status = self.service.get_prepare_status("DATA1")
        assert status is None
        
        status = self.service.get_prepare_status("DATA2")
        assert status is None
    
    def test_get_prepare_result_no_result(self):
        """Test get_prepare_result when no result exists."""
        result = self.service.get_prepare_result("DATA1")
        assert result is None
        
        result = self.service.get_prepare_result("DATA2")
        assert result is None
    
    @patch('gui.services.data_prepare_service.submit_job')
    def test_prepare_data1_missing(self, mock_submit_job):
        """Test prepare for DATA1 with MISSING status."""
        # Mock submit_job response
        mock_response = {"job_id": "test-job-123"}
        mock_submit_job.return_value = mock_response
        
        # Prepare DATA1
        self.service.prepare("DATA1", self.derived_datasets)
        
        # Verify job was submitted
        mock_submit_job.assert_called_once()
        call_args = mock_submit_job.call_args[0][0]
        assert call_args["job_type"] == "BUILD_DATA"
        assert call_args["dataset_id"] == "CME.MNQ.60m"
        assert call_args["force_rebuild"] is False  # MISSING -> Build Cache
        
        # Verify active preparation tracking
        assert "DATA1" in self.service._active_preparations
        assert self.service._active_preparations["DATA1"] == "test-job-123"
        
        # Verify result stored
        assert "DATA1" in self.service._prepare_results
        result = self.service._prepare_results["DATA1"]
        assert result.dataset_key == "DATA1"
        assert result.dataset_id == "CME.MNQ.60m"
        assert result.status == PrepareStatus.PREPARING
    
    @patch('gui.services.data_prepare_service.submit_job')
    def test_prepare_data2_stale(self, mock_submit_job):
        """Test prepare for DATA2 with STALE status."""
        # Mock submit_job response
        mock_response = {"job_id": "test-job-456"}
        mock_submit_job.return_value = mock_response
        
        # Prepare DATA2
        self.service.prepare("DATA2", self.derived_datasets)
        
        # Verify job was submitted with force_rebuild=True for STALE
        mock_submit_job.assert_called_once()
        call_args = mock_submit_job.call_args[0][0]
        assert call_args["force_rebuild"] is True  # STALE -> Rebuild Cache
    
    @patch('gui.services.data_prepare_service.submit_job')
    def test_prepare_already_preparing(self, mock_submit_job):
        """Test prepare when dataset is already being prepared."""
        # Mock submit_job response
        mock_response = {"job_id": "test-job-123"}
        mock_submit_job.return_value = mock_response
        
        # First prepare
        self.service.prepare("DATA1", self.derived_datasets)
        
        # Reset mock to track second call
        mock_submit_job.reset_mock()
        
        # Second prepare (should not submit another job)
        self.service.prepare("DATA1", self.derived_datasets)
        
        # Verify submit_job was NOT called again
        mock_submit_job.assert_not_called()
    
    @patch('gui.services.data_prepare_service.submit_job')
    def test_prepare_already_ready(self, mock_submit_job):
        """Test prepare when dataset is already READY."""
        # Create datasets with READY status
        ready_datasets = DerivedDatasets(
            data1_id="CME.MNQ.60m",
            data2_id=None,
            mapping_reason="Test",
            data1_status=DatasetStatus.READY,
            data2_status=DatasetStatus.UNKNOWN,
        )
        
        # Prepare DATA1 (should not submit job)
        self.service.prepare("DATA1", ready_datasets)
        
        # Verify submit_job was NOT called
        mock_submit_job.assert_not_called()
    
    def test_cancel_preparation(self):
        """Test cancel_preparation method."""
        # Set up active preparation
        self.service._active_preparations["DATA1"] = "test-job-123"
        self.service._prepare_results["DATA1"] = PrepareResult(
            dataset_key="DATA1",
            dataset_id="CME.MNQ.60m",
            success=False,
            status=PrepareStatus.PREPARING,
            message="Preparation started",
            job_id="test-job-123",
        )
        
        # Cancel preparation
        result = self.service.cancel_preparation("DATA1")
        
        # Verify cancellation
        assert result is True
        assert "DATA1" not in self.service._active_preparations
        assert self.service._prepare_results["DATA1"].status == PrepareStatus.FAILED
        assert "cancelled" in self.service._prepare_results["DATA1"].message.lower()
    
    def test_cancel_preparation_not_active(self):
        """Test cancel_preparation when no active preparation exists."""
        result = self.service.cancel_preparation("DATA1")
        assert result is False
    
    def test_clear_result(self):
        """Test clear_result method."""
        # Set up a result
        self.service._prepare_results["DATA1"] = PrepareResult(
            dataset_key="DATA1",
            dataset_id="CME.MNQ.60m",
            success=True,
            status=PrepareStatus.READY,
            message="Test",
        )
        
        # Write artifact
        self.service._write_prepare_artifact("DATA1")
        artifact_path = self.service._get_artifact_path("DATA1")
        assert artifact_path.exists()
        
        # Clear result
        result = self.service.clear_result("DATA1")
        
        # Verify clearing
        assert result is True
        assert "DATA1" not in self.service._prepare_results
        assert not artifact_path.exists()
    
    def test_write_and_read_artifact(self):
        """Test artifact persistence."""
        # Create a result
        test_result = PrepareResult(
            dataset_key="DATA1",
            dataset_id="CME.MNQ.60m",
            success=True,
            status=PrepareStatus.READY,
            message="Test preparation completed",
            job_id="test-job-123",
            artifact_path="/some/path",
            timestamp="2026-01-14T00:00:00",
        )
        
        # Store result
        self.service._prepare_results["DATA1"] = test_result
        
        # Write artifact
        self.service._write_prepare_artifact("DATA1")
        
        # Verify artifact exists
        artifact_path = self.service._get_artifact_path("DATA1")
        assert artifact_path.exists()
        
        # Read artifact back
        with open(artifact_path, "r") as f:
            artifact_data = json.load(f)
        
        # Verify artifact content
        assert artifact_data["dataset_key"] == "DATA1"
        assert artifact_data["dataset_id"] == "CME.MNQ.60m"
        assert artifact_data["success"] is True
        assert artifact_data["status"] == "READY"
        assert artifact_data["message"] == "Test preparation completed"
        
        # Test get_prepare_status reads from artifact
        status = self.service.get_prepare_status("DATA1")
        assert status == PrepareStatus.READY
        
        # Test get_prepare_result reads from artifact
        result = self.service.get_prepare_result("DATA1")
        assert result is not None
        assert result.dataset_key == "DATA1"
        assert result.status == PrepareStatus.READY
    
    @patch('gui.services.data_prepare_service.get_job')
    def test_poll_active_preparations_completed(self, mock_get_job):
        """Test polling when job completes successfully."""
        # Set up active preparation
        self.service._active_preparations["DATA1"] = "test-job-123"
        self.service._prepare_results["DATA1"] = PrepareResult(
            dataset_key="DATA1",
            dataset_id="CME.MNQ.60m",
            success=False,
            status=PrepareStatus.PREPARING,
            message="Preparation started",
            job_id="test-job-123",
        )
        
        # Mock job details as COMPLETED
        mock_get_job.return_value = {
            "state": "COMPLETED",
            "progress": 100,
        }
        
        # Poll active preparations
        self.service._poll_active_preparations()
        
        # Verify job removed from active preparations
        assert "DATA1" not in self.service._active_preparations
        
        # Verify result updated
        result = self.service._prepare_results["DATA1"]
        assert result.status == PrepareStatus.READY
        assert result.success is True
    
    @patch('gui.services.data_prepare_service.get_job')
    def test_poll_active_preparations_failed(self, mock_get_job):
        """Test polling when job fails."""
        # Set up active preparation
        self.service._active_preparations["DATA1"] = "test-job-123"
        
        # Mock job details as FAILED
        mock_get_job.return_value = {
            "state": "FAILED",
            "progress": 0,
        }
        
        # Poll active preparations
        self.service._poll_active_preparations()
        
        # Verify job removed from active preparations
        assert "DATA1" not in self.service._active_preparations
        
        # Verify result updated
        result = self.service._prepare_results["DATA1"]
        assert result.status == PrepareStatus.FAILED
        assert result.success is False
    
    def test_singleton_pattern(self):
        """Test get_data_prepare_service returns singleton."""
        service1 = get_data_prepare_service()
        service2 = get_data_prepare_service()
        
        assert service1 is service2
        assert isinstance(service1, DataPrepareService)


class TestPrepareStatusEnum:
    """Test PrepareStatus enum values."""
    
    def test_enum_values(self):
        """Verify all expected enum values exist."""
        assert PrepareStatus.READY == "READY"
        assert PrepareStatus.MISSING == "MISSING"
        assert PrepareStatus.STALE == "STALE"
        assert PrepareStatus.UNKNOWN == "UNKNOWN"
        assert PrepareStatus.PREPARING == "PREPARING"
        assert PrepareStatus.FAILED == "FAILED"
        
        # Verify all values can be instantiated
        for status in ["READY", "MISSING", "STALE", "UNKNOWN", "PREPARING", "FAILED"]:
            assert PrepareStatus(status) == status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
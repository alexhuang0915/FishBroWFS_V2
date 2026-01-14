"""
Tests for Dataset Resolver (Route 1 Governance Core).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from gui.services.dataset_resolver import (
    DatasetResolver,
    DerivedDatasets,
    DatasetStatus,
    GateStatus,
    resolve_datasets,
    evaluate_data2_gate,
    evaluate_run_readiness,
    evaluate_run_readiness_with_prepare_status,
)


class TestDatasetResolver:
    """Test DatasetResolver functionality."""
    
    def test_init(self):
        """Test resolver initialization."""
        resolver = DatasetResolver()
        assert resolver.strategy_catalog is not None
        assert resolver.dataset_registry is not None
        assert resolver.timeframe_registry is not None
    
    @patch('gui.services.dataset_resolver.load_strategy_catalog')
    @patch('gui.services.dataset_resolver.load_datasets')
    @patch('gui.services.dataset_resolver.load_timeframes')
    def test_resolve_datasets_basic(self, mock_timeframes, mock_datasets, mock_strategy_catalog):
        """Test basic dataset resolution."""
        # Mock strategy catalog
        mock_strategy = Mock()
        mock_strategy.requires_secondary_data = False
        mock_catalog = Mock()
        mock_catalog.get_strategy_by_id.return_value = mock_strategy
        mock_strategy_catalog.return_value = mock_catalog
        
        # Mock dataset registry
        mock_dataset = Mock()
        mock_dataset.id = "CME.MNQ.60m"
        mock_dataset.instrument_id = "CME.MNQ"
        mock_dataset.timeframe = 60
        mock_dataset.date_range = "2020-2024"
        mock_registry = Mock()
        mock_registry.datasets = [mock_dataset]
        mock_datasets.return_value = mock_registry
        
        # Mock timeframe registry
        mock_timeframes.return_value = Mock()
        
        resolver = DatasetResolver()
        result = resolver.resolve(
            strategy_id="s1_v1",
            instrument_id="CME.MNQ",
            timeframe_id="60",
            mode="research",
            season="2026Q1"
        )
        
        assert isinstance(result, DerivedDatasets)
        assert result.data1_id == "CME.MNQ.60m"
        assert result.data2_id is None  # Strategy doesn't require DATA2
        assert "Mapped by instrument" in result.mapping_reason
        assert result.data1_status == DatasetStatus.READY
        assert result.data2_status == DatasetStatus.UNKNOWN
    
    @patch('gui.services.dataset_resolver.load_strategy_catalog')
    @patch('gui.services.dataset_resolver.load_datasets')
    @patch('gui.services.dataset_resolver.load_timeframes')
    def test_resolve_datasets_requires_data2(self, mock_timeframes, mock_datasets, mock_strategy_catalog):
        """Test dataset resolution when strategy requires DATA2."""
        # Mock strategy catalog
        mock_strategy = Mock()
        mock_strategy.requires_secondary_data = True
        mock_catalog = Mock()
        mock_catalog.get_strategy_by_id.return_value = mock_strategy
        mock_strategy_catalog.return_value = mock_catalog
        
        # Mock dataset registry with primary dataset
        mock_dataset1 = Mock()
        mock_dataset1.id = "CME.MNQ.60m"
        mock_dataset1.instrument_id = "CME.MNQ"
        mock_dataset1.timeframe = 60
        mock_dataset1.date_range = "2020-2024"
        
        # Mock secondary dataset
        mock_dataset2 = Mock()
        mock_dataset2.id = "CME.ES.60m"
        mock_dataset2.instrument_id = "CME.ES"
        mock_dataset2.timeframe = 60
        mock_dataset2.date_range = "2020-2024"
        
        mock_registry = Mock()
        mock_registry.datasets = [mock_dataset1, mock_dataset2]
        mock_datasets.return_value = mock_registry
        
        # Mock timeframe registry
        mock_timeframes.return_value = Mock()
        
        resolver = DatasetResolver()
        result = resolver.resolve(
            strategy_id="s1_v1",
            instrument_id="CME.MNQ",
            timeframe_id="60",
            mode="research"
        )
        
        assert result.data1_id == "CME.MNQ.60m"
        # Should find secondary dataset via mapping
        assert result.data2_id == "CME.ES.60m"
        assert result.data1_status == DatasetStatus.READY
        assert result.data2_status == DatasetStatus.READY
    
    @patch('gui.services.dataset_resolver.load_strategy_catalog')
    @patch('gui.services.dataset_resolver.load_datasets')
    @patch('gui.services.dataset_resolver.load_timeframes')
    def test_evaluate_data2_gate_pass_no_requirement(self, mock_timeframes, mock_datasets, mock_strategy_catalog):
        """Test DATA2 gate PASS when strategy doesn't require DATA2."""
        # Mock strategy catalog
        mock_strategy = Mock()
        mock_strategy.requires_secondary_data = False
        mock_catalog = Mock()
        mock_catalog.get_strategy_by_id.return_value = mock_strategy
        mock_strategy_catalog.return_value = mock_catalog
        
        # Mock dataset registry
        mock_registry = Mock()
        mock_registry.datasets = []
        mock_datasets.return_value = mock_registry
        
        # Mock timeframe registry
        mock_timeframes.return_value = Mock()
        
        resolver = DatasetResolver()
        gate_result = resolver.evaluate_data2_gate(
            strategy_id="s1_v1",
            instrument_id="CME.MNQ",
            timeframe_id="60",
            mode="research"
        )
        
        assert isinstance(gate_result, GateStatus)
        assert gate_result.level == "PASS"
        assert "does not require DATA2" in gate_result.detail
    
    @patch('gui.services.dataset_resolver.load_strategy_catalog')
    @patch('gui.services.dataset_resolver.load_datasets')
    @patch('gui.services.dataset_resolver.load_timeframes')
    def test_evaluate_data2_gate_fail_missing_required(self, mock_timeframes, mock_datasets, mock_strategy_catalog):
        """Test DATA2 gate FAIL when strategy requires DATA2 but it's missing."""
        # Mock strategy catalog
        mock_strategy = Mock()
        mock_strategy.requires_secondary_data = True
        mock_catalog = Mock()
        mock_catalog.get_strategy_by_id.return_value = mock_strategy
        mock_strategy_catalog.return_value = mock_catalog
        
        # Mock dataset registry (empty - no datasets)
        mock_registry = Mock()
        mock_registry.datasets = []
        mock_datasets.return_value = mock_registry
        
        # Mock timeframe registry
        mock_timeframes.return_value = Mock()
        
        resolver = DatasetResolver()
        gate_result = resolver.evaluate_data2_gate(
            strategy_id="s1_v1",
            instrument_id="CME.MNQ",
            timeframe_id="60",
            mode="research"
        )
        
        assert gate_result.level == "FAIL"
        assert "DATA2 required but missing" in gate_result.detail
    
    @patch('gui.services.dataset_resolver.load_strategy_catalog')
    @patch('gui.services.dataset_resolver.load_datasets')
    @patch('gui.services.dataset_resolver.load_timeframes')
    def test_evaluate_data2_gate_safe_default(self, mock_timeframes, mock_datasets, mock_strategy_catalog):
        """Test DATA2 gate safe default (missing strategy entry -> requires=True)."""
        # Mock strategy catalog (strategy not found)
        mock_catalog = Mock()
        mock_catalog.get_strategy_by_id.return_value = None
        mock_strategy_catalog.return_value = mock_catalog
        
        # Mock dataset registry (empty)
        mock_registry = Mock()
        mock_registry.datasets = []
        mock_datasets.return_value = mock_registry
        
        # Mock timeframe registry
        mock_timeframes.return_value = Mock()
        
        resolver = DatasetResolver()
        gate_result = resolver.evaluate_data2_gate(
            strategy_id="unknown_strategy",
            instrument_id="CME.MNQ",
            timeframe_id="60",
            mode="research"
        )
        
        # Safe default: treat as requires=True
        assert gate_result.level == "FAIL"
        assert "DATA2 required" in gate_result.detail
    
    @patch('gui.services.dataset_resolver.load_strategy_catalog')
    @patch('gui.services.dataset_resolver.load_datasets')
    @patch('gui.services.dataset_resolver.load_timeframes')
    def test_evaluate_run_readiness_data1_fail(self, mock_timeframes, mock_datasets, mock_strategy_catalog):
        """Test run readiness when DATA1 is missing (should FAIL)."""
        # Mock strategy catalog
        mock_strategy = Mock()
        mock_strategy.requires_secondary_data = False
        mock_catalog = Mock()
        mock_catalog.get_strategy_by_id.return_value = mock_strategy
        mock_strategy_catalog.return_value = mock_catalog
        
        # Mock dataset registry (empty - no DATA1)
        mock_registry = Mock()
        mock_registry.datasets = []
        mock_datasets.return_value = mock_registry
        
        # Mock timeframe registry
        mock_timeframes.return_value = Mock()
        
        resolver = DatasetResolver()
        gate_result = resolver.evaluate_run_readiness(
            strategy_id="s1_v1",
            instrument_id="CME.MNQ",
            timeframe_id="60",
            mode="research"
        )
        
        # DATA1 missing should cause FAIL
        assert gate_result.level == "FAIL"
        assert "DATA1" in gate_result.detail
    
    @patch('gui.services.dataset_resolver.load_strategy_catalog')
    @patch('gui.services.dataset_resolver.load_datasets')
    @patch('gui.services.dataset_resolver.load_timeframes')
    def test_evaluate_run_readiness_both_ready(self, mock_timeframes, mock_datasets, mock_strategy_catalog):
        """Test run readiness when both DATA1 and DATA2 are READY."""
        # Mock strategy catalog
        mock_strategy = Mock()
        mock_strategy.requires_secondary_data = True
        mock_catalog = Mock()
        mock_catalog.get_strategy_by_id.return_value = mock_strategy
        mock_strategy_catalog.return_value = mock_catalog
        
        # Mock dataset registry with both datasets
        mock_dataset1 = Mock()
        mock_dataset1.id = "CME.MNQ.60m"
        mock_dataset1.instrument_id = "CME.MNQ"
        mock_dataset1.timeframe = 60
        mock_dataset1.date_range = "2020-2024"
        
        mock_dataset2 = Mock()
        mock_dataset2.id = "CME.ES.60m"
        mock_dataset2.instrument_id = "CME.ES"
        mock_dataset2.timeframe = 60
        mock_dataset2.date_range = "2020-2024"
        
        mock_registry = Mock()
        mock_registry.datasets = [mock_dataset1, mock_dataset2]
        mock_datasets.return_value = mock_registry
        
        # Mock timeframe registry
        mock_timeframes.return_value = Mock()
        
        resolver = DatasetResolver()
        gate_result = resolver.evaluate_run_readiness(
            strategy_id="s1_v1",
            instrument_id="CME.MNQ",
            timeframe_id="60",
            mode="research"
        )
        
        # Both ready should PASS
        assert gate_result.level == "PASS"
        assert "DATA1" in gate_result.detail
        assert "DATA2" in gate_result.detail
    
    @patch('gui.services.dataset_resolver.load_strategy_catalog')
    @patch('gui.services.dataset_resolver.load_datasets')
    @patch('gui.services.dataset_resolver.load_timeframes')
    @patch('gui.services.data_prepare_service.get_data_prepare_service')
    def test_evaluate_run_readiness_with_prepare_status_preparing(
        self, mock_get_service, mock_timeframes, mock_datasets, mock_strategy_catalog
    ):
        """Test run readiness when DATA1 is PREPARING (should FAIL)."""
        # Import PrepareStatus enum
        from gui.services.data_prepare_service import PrepareStatus
        
        # Mock strategy catalog
        mock_strategy = Mock()
        mock_strategy.requires_secondary_data = False
        mock_catalog = Mock()
        mock_catalog.get_strategy_by_id.return_value = mock_strategy
        mock_strategy_catalog.return_value = mock_catalog
        
        # Mock dataset registry with DATA1
        mock_dataset = Mock()
        mock_dataset.id = "CME.MNQ.60m"
        mock_dataset.instrument_id = "CME.MNQ"
        mock_dataset.timeframe = 60
        mock_dataset.date_range = "2020-2024"
        
        mock_registry = Mock()
        mock_registry.datasets = [mock_dataset]
        mock_datasets.return_value = mock_registry
        
        # Mock timeframe registry
        mock_timeframes.return_value = Mock()
        
        # Mock data prepare service returning PREPARING status
        mock_service = Mock()
        mock_service.get_prepare_status.return_value = PrepareStatus.PREPARING
        mock_get_service.return_value = mock_service
        
        resolver = DatasetResolver()
        gate_result = resolver.evaluate_run_readiness_with_prepare_status(
            strategy_id="s1_v1",
            instrument_id="CME.MNQ",
            timeframe_id="60",
            mode="research"
        )
        
        # PREPARING should cause FAIL
        assert gate_result.level == "FAIL"
        assert "currently being prepared" in gate_result.detail
        # Check that get_prepare_status was called with DATA1
        # Note: It might be called with both DATA1 and DATA2, so we check any call
        mock_service.get_prepare_status.assert_any_call("DATA1")
    
    @patch('gui.services.dataset_resolver._dataset_resolver')
    def test_convenience_functions(self, mock_resolver):
        """Test convenience functions."""
        # Test resolve_datasets
        mock_resolver.resolve.return_value = DerivedDatasets(
            data1_id="test1",
            data2_id=None,
            mapping_reason="test",
            data1_status=DatasetStatus.READY,
            data2_status=DatasetStatus.UNKNOWN
        )
        
        result = resolve_datasets("s1_v1", "CME.MNQ", "60", "research")
        assert result.data1_id == "test1"
        mock_resolver.resolve.assert_called_once_with("s1_v1", "CME.MNQ", "60", "research", None)
        
        # Test evaluate_data2_gate
        mock_gate_result = GateStatus(level="PASS", title="Test", detail="Test")
        mock_resolver.evaluate_data2_gate.return_value = mock_gate_result
        
        gate_result = evaluate_data2_gate("s1_v1", "CME.MNQ", "60", "research")
        assert gate_result.level == "PASS"
        mock_resolver.evaluate_data2_gate.assert_called_once_with("s1_v1", "CME.MNQ", "60", "research", None)
        
        # Test evaluate_run_readiness
        mock_resolver.evaluate_run_readiness.return_value = mock_gate_result
        
        run_readiness_result = evaluate_run_readiness("s1_v1", "CME.MNQ", "60", "research")
        assert run_readiness_result.level == "PASS"
        mock_resolver.evaluate_run_readiness.assert_called_once_with("s1_v1", "CME.MNQ", "60", "research", None)
        
        # Test evaluate_run_readiness_with_prepare_status
        mock_resolver.evaluate_run_readiness_with_prepare_status.return_value = mock_gate_result
        
        run_readiness_with_prepare_result = evaluate_run_readiness_with_prepare_status("s1_v1", "CME.MNQ", "60", "research")
        assert run_readiness_with_prepare_result.level == "PASS"
        mock_resolver.evaluate_run_readiness_with_prepare_status.assert_called_once_with("s1_v1", "CME.MNQ", "60", "research", None)


class TestStrategyCatalogDefaultSafety:
    """Test strategy catalog default safety (missing requires_secondary_data field)."""
    
    def test_strategy_catalog_entry_default(self):
        """Test that StrategyCatalogEntry has requires_secondary_data with default True."""
        from config.registry.strategy_catalog import StrategyCatalogEntry
        
        # Test that field exists with default
        field_info = StrategyCatalogEntry.model_fields.get('requires_secondary_data')
        assert field_info is not None
        assert field_info.default is True
        
        # Test that model can be instantiated without the field
        entry = StrategyCatalogEntry(
            id="test",
            display_name="Test",
            family="trend_following",
            status="active",
            config_file="test.yaml"
        )
        assert entry.requires_secondary_data is True  # Default applied


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
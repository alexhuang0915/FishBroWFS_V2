"""
Test data readiness service for checking bars and features.
"""

from pathlib import Path
import pytest

from src.gui.desktop.services.data_readiness_service import (
    check_bars,
    check_features,
    check_all,
    Readiness,
)


def test_check_bars_exists(tmp_path):
    """Test check_bars when bars file exists."""
    # Mock the bars_store module to return a path we control
    import sys
    import types
    
    # Create a mock bars_store module
    mock_bars_store = types.ModuleType("control.bars_store")
    
    def mock_bars_dir(root, season, market, timeframe):
        return root / "seasons" / season / "bars" / market / f"{timeframe}m"
    
    def mock_resampled_bars_path(root, season, market, timeframe):
        return root / "seasons" / season / "bars" / market / f"{timeframe}m" / "bars.parquet"
    
    mock_bars_store.bars_dir = mock_bars_dir
    mock_bars_store.resampled_bars_path = mock_resampled_bars_path
    
    # Temporarily replace the module
    sys.modules["control.bars_store"] = mock_bars_store
    
    try:
        # Create the bars file
        bars_path = tmp_path / "seasons" / "2026Q1" / "bars" / "MNQ" / "5m"
        bars_path.mkdir(parents=True)
        (bars_path / "bars.parquet").write_text("mock bars data")
        
        ready, reason = check_bars("MNQ", 5, "2026Q1", tmp_path)
        assert ready is True
        assert "exists" in reason.lower()
    finally:
        # Restore original module if it exists
        if "control.bars_store" in sys.modules:
            del sys.modules["control.bars_store"]


def test_check_bars_missing(tmp_path):
    """Test check_bars when bars file doesn't exist."""
    import sys
    import types
    
    mock_bars_store = types.ModuleType("control.bars_store")
    
    def mock_resampled_bars_path(root, season, market, timeframe):
        return root / "seasons" / season / "bars" / market / f"{timeframe}m" / "bars.parquet"
    
    mock_bars_store.resampled_bars_path = mock_resampled_bars_path
    
    sys.modules["control.bars_store"] = mock_bars_store
    
    try:
        # Don't create the file
        ready, reason = check_bars("MNQ", 5, "2026Q1", tmp_path)
        assert ready is False
        assert "no bars data" in reason.lower() or "not found" in reason.lower()
    finally:
        if "control.bars_store" in sys.modules:
            del sys.modules["control.bars_store"]


def test_check_features_exists(tmp_path):
    """Test check_features when features file exists."""
    import sys
    import types
    
    mock_features_store = types.ModuleType("control.features_store")
    
    def mock_features_dir(root, season, market, timeframe):
        return root / "seasons" / season / "features" / market / f"{timeframe}m"
    
    def mock_features_path(root, season, market, timeframe):
        return root / "seasons" / season / "features" / market / f"{timeframe}m" / "features.npz"
    
    mock_features_store.features_dir = mock_features_dir
    mock_features_store.features_path = mock_features_path
    
    sys.modules["control.features_store"] = mock_features_store
    
    try:
        # Create the features file
        features_path = tmp_path / "seasons" / "2026Q1" / "features" / "MNQ" / "5m"
        features_path.mkdir(parents=True)
        (features_path / "features.npz").write_text("mock features data")
        
        ready, reason = check_features("MNQ", 5, "2026Q1", tmp_path)
        assert ready is True
        assert "exists" in reason.lower()
    finally:
        if "control.features_store" in sys.modules:
            del sys.modules["control.features_store"]


def test_check_features_missing(tmp_path):
    """Test check_features when features file doesn't exist."""
    import sys
    import types
    
    mock_features_store = types.ModuleType("control.features_store")
    
    def mock_features_path(root, season, market, timeframe):
        return root / "seasons" / season / "features" / market / f"{timeframe}m" / "features.npz"
    
    mock_features_store.features_path = mock_features_path
    
    sys.modules["control.features_store"] = mock_features_store
    
    try:
        ready, reason = check_features("MNQ", 5, "2026Q1", tmp_path)
        assert ready is False
        assert "no features data" in reason.lower() or "not found" in reason.lower()
    finally:
        if "control.features_store" in sys.modules:
            del sys.modules["control.features_store"]


def test_check_all_both_ready(tmp_path):
    """Test check_all when both bars and features are ready (using fallback paths)."""
    # Create bars file in fallback location
    bars_dir = tmp_path / "shared" / "2026Q1" / "MNQ" / "bars"
    bars_dir.mkdir(parents=True)
    bars_file = bars_dir / "resampled_5m.npz"
    bars_file.write_text("mock bars")
    
    # Create features file in fallback location
    features_dir = tmp_path / "shared" / "2026Q1" / "MNQ" / "features"
    features_dir.mkdir(parents=True)
    features_file = features_dir / "features_5m.npz"
    features_file.write_text("mock features")
    
    readiness = check_all("MNQ", 5, "2026Q1", tmp_path)
    assert isinstance(readiness, Readiness)
    assert readiness.bars_ready is True
    assert readiness.features_ready is True
    assert "exists" in readiness.bars_reason.lower()
    assert "exists" in readiness.features_reason.lower()


def test_check_all_none_ready(tmp_path):
    """Test check_all when neither bars nor features are ready."""
    import sys
    import types
    
    mock_bars_store = types.ModuleType("control.bars_store")
    mock_features_store = types.ModuleType("control.features_store")
    
    def mock_resampled_bars_path(root, season, market, timeframe):
        return root / "seasons" / season / "bars" / market / f"{timeframe}m" / "bars.parquet"
    
    def mock_features_path(root, season, market, timeframe):
        return root / "seasons" / season / "features" / market / f"{timeframe}m" / "features.npz"
    
    mock_bars_store.resampled_bars_path = mock_resampled_bars_path
    mock_features_store.features_path = mock_features_path
    
    sys.modules["control.bars_store"] = mock_bars_store
    sys.modules["control.features_store"] = mock_features_store
    
    try:
        readiness = check_all("MNQ", 5, "2026Q1", tmp_path)
        assert readiness.bars_ready is False
        assert readiness.features_ready is False
        assert "no bars data" in readiness.bars_reason.lower() or "not found" in readiness.bars_reason.lower()
        assert "no features data" in readiness.features_reason.lower() or "not found" in readiness.features_reason.lower()
    finally:
        if "control.bars_store" in sys.modules:
            del sys.modules["control.bars_store"]
        if "control.features_store" in sys.modules:
            del sys.modules["control.features_store"]


def test_check_all_mixed(tmp_path):
    """Test check_all when only bars are ready."""
    # Create bars file in fallback location
    bars_dir = tmp_path / "shared" / "2026Q1" / "MNQ" / "bars"
    bars_dir.mkdir(parents=True)
    bars_file = bars_dir / "resampled_5m.npz"
    bars_file.write_text("mock bars")
    
    # Don't create features file
    
    readiness = check_all("MNQ", 5, "2026Q1", tmp_path)
    assert readiness.bars_ready is True
    assert readiness.features_ready is False
    assert "exists" in readiness.bars_reason.lower()
    assert "no features data" in readiness.features_reason.lower() or "not found" in readiness.features_reason.lower()


def test_readiness_dataclass():
    """Test the Readiness dataclass."""
    readiness = Readiness(
        bars_ready=True,
        features_ready=False,
        bars_reason="Bars exist",
        features_reason="No features"
    )
    
    assert readiness.bars_ready is True
    assert readiness.features_ready is False
    assert readiness.bars_reason == "Bars exist"
    assert readiness.features_reason == "No features"
    
    # Test repr
    repr_str = repr(readiness)
    assert "Readiness" in repr_str
    assert "bars_ready=True" in repr_str
    assert "features_ready=False" in repr_str


def test_module_import_fallback(tmp_path):
    """Test that functions handle missing imports gracefully (use fallback paths)."""
    import sys
    
    # Temporarily remove the modules if they exist
    bars_store_original = sys.modules.pop("control.bars_store", None)
    features_store_original = sys.modules.pop("control.features_store", None)
    
    try:
        # Create test data in fallback location
        bars_dir = tmp_path / "shared" / "2026Q1" / "MNQ" / "bars"
        bars_dir.mkdir(parents=True)
        bars_file = bars_dir / "resampled_5m.npz"
        bars_file.write_text("mock bars")
        
        # Test with existing file (should return True)
        ready, reason = check_bars("MNQ", 5, "2026Q1", tmp_path)
        assert ready is True
        assert "exists" in reason.lower()
        
        # Test without file (should return False)
        ready, reason = check_features("MNQ", 5, "2026Q1", tmp_path)
        assert ready is False
        assert "no features data" in reason.lower() or "not found" in reason.lower()
        
        readiness = check_all("MNQ", 5, "2026Q1", tmp_path)
        assert readiness.bars_ready is True
        assert readiness.features_ready is False
        assert "exists" in readiness.bars_reason.lower()
        assert "no features data" in readiness.features_reason.lower() or "not found" in readiness.features_reason.lower()
    finally:
        # Restore original modules
        if bars_store_original:
            sys.modules["control.bars_store"] = bars_store_original
        if features_store_original:
            sys.modules["control.features_store"] = features_store_original


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
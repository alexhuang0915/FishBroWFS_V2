"""
Test partial run behavior for OPEN LAST RUN functionality.

Ensures that runs with only metrics.json (partial runs) are properly
handled and displayed in the UI without clearing analytics.
"""

import pytest
import json
import tempfile
from pathlib import Path
import sys

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))


class TestPartialRunBehavior:
    """Test that partial runs (metrics.json only) are handled correctly."""
    
    def test_active_run_state_classification(self):
        """Test that RunStatus classification works correctly for partial runs."""
        # Import directly from src to avoid gui.desktop.__init__ issues
        from src.gui.desktop.state.active_run_state import ActiveRunState, RunStatus
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Test 1: NONE - no run directory
            status, diagnostics = ActiveRunState.classify_run_dir(tmp_path / "nonexistent")
            assert status == RunStatus.NONE
            assert "reason" in diagnostics
            
            # Test 2: NONE - directory exists but no metrics.json
            run_dir = tmp_path / "run_123456"
            run_dir.mkdir()
            status, diagnostics = ActiveRunState.classify_run_dir(run_dir)
            assert status == RunStatus.NONE
            assert diagnostics.get("reason") == "metrics_json_missing"
            
            # Test 3: PARTIAL - metrics.json exists, no other files
            metrics_path = run_dir / "metrics.json"
            metrics_data = {
                "net_profit": 1000.0,
                "max_dd": -500.0,
                "trades": 42,
                "sharpe": 1.5
            }
            with open(metrics_path, "w") as f:
                json.dump(metrics_data, f)
            
            status, diagnostics = ActiveRunState.classify_run_dir(run_dir)
            assert status == RunStatus.PARTIAL
            assert diagnostics["metrics_json"] == "READY"
            assert diagnostics["equity_parquet"] == "MISSING"
            assert diagnostics["trades_parquet"] == "MISSING"
            assert diagnostics["report_json"] == "MISSING"
            
            # Test 4: READY - metrics.json + at least one other artifact
            # Create an empty equity.parquet file (size > 0)
            equity_path = run_dir / "equity.parquet"
            equity_path.write_text("dummy parquet data")  # Not real parquet, but size > 0
            
            status, diagnostics = ActiveRunState.classify_run_dir(run_dir)
            assert status == RunStatus.READY
            assert diagnostics["equity_parquet"] == "READY"
    
    @pytest.mark.skip(reason="Requires PySide6 for GUI widgets")
    def test_analysis_widget_tolerant_loading(self):
        """Test that AnalysisWidget.load_artifact is tolerant of partial runs."""
        pass
    
    @pytest.mark.skip(reason="Requires PySide6 for GUI widgets")
    def test_op_tab_open_run_partial(self, monkeypatch):
        """Test that OpTab.open_run handles partial runs correctly."""
        pass
    
    @pytest.mark.skip(reason="Requires PySide6 for GUI widgets")
    def test_report_tab_updates_from_state(self):
        """Test that ReportTab updates correctly from active run state."""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import numpy as np

from contracts.ranking_explain import RankingExplainReasonCode, RankingExplainReasonCard
from gui.services.ranking_explain_builder import _build_warning_reasons

def test_build_warning_reasons_numba():
    """Verify WARN_NUMBA_MISSING is converted to ReasonCard."""
    warnings = [RankingExplainReasonCode.WARN_NUMBA_MISSING.value]
    # Mock context
    context = RankingExplainReasonCode.CANDIDATE if hasattr(RankingExplainReasonCode, "CANDIDATE") else "CANDIDATE"
    # Actually need RankingExplainContext
    from contracts.ranking_explain import RankingExplainContext
    context = RankingExplainContext.CANDIDATE
    
    cards = _build_warning_reasons(context, warnings)
    assert len(cards) == 1
    assert cards[0].code == RankingExplainReasonCode.WARN_NUMBA_MISSING
    assert "pure Python mode" in cards[0].summary

def test_build_warning_reasons_plateau_fallback():
    """Verify WARN_PLATEAU_FALLBACK is converted to ReasonCard."""
    warnings = [RankingExplainReasonCode.WARN_PLATEAU_FALLBACK.value]
    from contracts.ranking_explain import RankingExplainContext
    context = RankingExplainContext.FINAL_SELECTION
    
    cards = _build_warning_reasons(context, warnings)
    assert len(cards) == 1
    assert cards[0].code == RankingExplainReasonCode.WARN_PLATEAU_FALLBACK
    assert "Plateau generation skipped or failed" in cards[0].summary

def test_runner_adapter_populates_warnings():
    """Verify runner_adapter adds warning if Numba is missing."""
    # We need to simulate runner_adapter logic. 
    # Since we can't easily uninstall Numba, we patch engine_jit.nb
    
    from pipeline.runner_adapter import run_stage_job
    
    # Mock cfg
    cfg = {
        "stage_name": "stage1_topk",
        "strategy_id": "strategy_A",
        "open_": np.array([1.0]), "high": np.array([2.0]), "low": np.array([0.5]), "close": np.array([1.5]),
        "params_matrix": np.array([[1.0, 2.0, 3.0]]),
        "commission": 0.0, "slip": 0.0,
        "param_subsample_rate": 1.0,
    }
    
    with patch("pipeline.runner_adapter.engine_jit") as mock_jit:
        mock_jit.nb = None # Simulate Numba missing
        
        # We also need to mock registry because we don't want real strategy lookup failure
        with patch("pipeline.runner_adapter.registry") as mock_registry, \
             patch("pipeline.runner_adapter.run_grid") as mock_grid:
             
            # Mock registry
            mock_spec = MagicMock()
            mock_spec.param_schema = {"a": {"type": "int"}, "b": {"type": "int"}, "c": {"type": "float"}}
            mock_registry.get.return_value = mock_spec
            mock_registry.convert_to_gui_spec.return_value.params = [
                MagicMock(name="a", type="int"), MagicMock(name="b", type="int"), MagicMock(name="c", type="float")
            ]
            
            # Mock grid result
            mock_grid.return_value = {"metrics": np.array([[100.0, 10, 0.1]])} # 1 row
            
            # Run
            result = run_stage_job(cfg)
            
            # Assert warnings
            assert "warnings" in result
            assert RankingExplainReasonCode.WARN_NUMBA_MISSING.value in result["warnings"]

def test_ranking_explain_report_contains_warning(tmp_path):
    """Verify end-to-end like flow: warnings -> artifact."""
    from core.artifacts import write_run_artifacts
    from contracts.ranking_explain import RankingExplainContext
    
    run_dir = tmp_path / "run_X"
    warnings = [RankingExplainReasonCode.WARN_NUMBA_MISSING.value]
    manifest = {"run_id": "run_X"}
    config = {}
    metrics = {"stage_name": "stage1_topk"}
    winners = {"topk": [], "notes": {"schema": "v2"}}
    
    write_run_artifacts(
        run_dir=run_dir,
        manifest=manifest,
        config_snapshot=config,
        metrics=metrics,
        winners=winners,
        warnings=warnings
    )
    
    # Check ranking_explain_report.json
    report_path = run_dir / "ranking_explain_report.json"
    
    if not report_path.exists():
        error_path = run_dir / "ranking_explain_error.txt"
        warning_path = run_dir / "ranking_explain_warning.txt"
        
        msg = "Report missing."
        if error_path.exists():
            msg += f" Error: {error_path.read_text()}"
        if warning_path.exists():
            msg += f" Warning: {warning_path.read_text()}"
            
        params_path = run_dir / "winners.json"
        if params_path.exists():
             msg += f" Winners: {params_path.read_text()}"
        else:
             msg += " Winners.json missing."
             
        pytest.fail(msg)
        
    assert report_path.exists()
    
    report_data = json.loads(report_path.read_text())
    reasons = report_data["reasons"]
    
    # Find warning card
    warning_card = next((r for r in reasons if r["code"] == RankingExplainReasonCode.WARN_NUMBA_MISSING.value), None)
    assert warning_card is not None
    assert warning_card["severity"] == "WARN"



def test_runner_adapter_detects_malformed_env():
    """Test that runner adapter detects missing environment variables."""
    import os
    from pipeline.runner_adapter import _run_stage1_job
    
    cfg = {
        "season": "test_season",
        "dataset_id": "test_dataset",
        "bars": 100,
        "params_total": 10,
        "param_subsample_rate": 1.0,
        "open_": np.random.randn(100),
        "high": np.random.randn(100),
        "low": np.random.randn(100),
        "close": np.random.randn(100),
        "params_matrix": np.random.randn(10, 3),
        "commission": 0.0,
        "slip": 0.0,
        "strategy_id": "test_strat",
    }
    
    # Mock os.environ to look like it's missing critical vars
    with patch.dict(os.environ, {}, clear=True):
        # We also need to mock engine_jit.nb and registry
        with patch("pipeline.runner_adapter.engine_jit") as mock_jit, \
             patch("pipeline.runner_adapter.registry") as mock_registry:
            
            mock_jit.nb = MagicMock() 
            
            # Mock registry.get
            mock_spec = MagicMock()
            mock_spec.param_schema = {}
            mock_registry.get.return_value = mock_spec
            
            # Run stage1 job
            result = _run_stage1_job(cfg)
            
            # Verify WARN_ENV_MALFORMED is in warnings
            warnings = result.get("warnings", [])
            assert RankingExplainReasonCode.WARN_ENV_MALFORMED.value in warnings


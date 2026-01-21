import pytest
import os
import shutil
from pathlib import Path
import pandas as pd
import numpy as np
from portfolio.runner_v1 import load_signal_series

def test_load_signal_series_determinism(tmp_path):
    """Verify that load_signal_series picks the same file deterministically."""
    
    # Setup mock structure
    # outputs/jobs/{job_id}/artifacts/{strategy_id}/{instrument_id}/signal_series.parquet
    strategy_id = "S1"
    instrument_id = "CME.MNQ"
    season = "2026Q1"
    
    # Create two "job" directories with the same strategy artifact
    job_a = tmp_path / "jobs" / "aaaa-1111" / "artifacts" / strategy_id / instrument_id
    job_b = tmp_path / "jobs" / "bbbb-2222" / "artifacts" / strategy_id / instrument_id
    
    job_a.mkdir(parents=True)
    job_b.mkdir(parents=True)
    
    # Create dummy parquet files
    df_a = pd.DataFrame({"val": [1]}, index=[pd.Timestamp("2025-01-01")])
    df_b = pd.DataFrame({"val": [2]}, index=[pd.Timestamp("2025-01-01")])
    
    path_a = job_a / "signal_series.parquet"
    path_b = job_b / "signal_series.parquet"
    
    df_a.to_parquet(path_a)
    df_b.to_parquet(path_b)
    
    # We want to ensure that regardless of underlying filesystem order,
    # the runner always picks the same one (alphabetically first: aaaa-1111)
    
    # Run multiple times to observe stability
    for _ in range(5):
        df = load_signal_series(tmp_path, season, strategy_id, instrument_id)
        assert df is not None
        # Should always pick the one from 'aaaa-1111' which has val=1
        assert df["val"].iloc[0] == 1
        assert df["val"].iloc[0] != 2

if __name__ == "__main__":
    pytest.main([__file__])

"""
Pytest configuration and fixtures for control tests.
"""

from __future__ import annotations

import numpy as np
from pathlib import Path
import pytest


@pytest.fixture(scope="session", autouse=True)
def ensure_minimal_shared_feature_cache():
    """
    Ensure minimal shared feature cache exists for baseline tests.
    
    This fixture creates a dummy features_60m.npz file at:
        outputs/shared/2026Q1/CME.MNQ/features/features_60m.npz
    
    The file contains minimal valid data that allows baseline tests to pass
    without requiring actual feature computation or pre-existing outputs.
    
    This is safe after outputs prune because:
    1. It only creates the file if missing
    2. The file is minimal (tiny arrays)
    3. It's created in the project's outputs directory (not committed)
    4. Tests that need real feature data should use their own temp directories
    """
    # Determine project root
    repo_root = Path(__file__).resolve().parent.parent.parent
    target_path = repo_root / "outputs" / "shared" / "2026Q1" / "CME.MNQ" / "features" / "features_60m.npz"
    
    # If file already exists, do nothing
    if target_path.exists():
        return
    
    # Create directory structure
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create minimal valid NPZ data
    # Baseline tests expect at least these S1 features:
    s1_features = [
        "sma_5", "sma_10", "sma_20", "sma_40",
        "hh_5", "hh_10", "hh_20", "hh_40",
        "ll_5", "ll_10", "ll_20", "ll_40",
        "atr_10", "atr_14",
        "percentile_126", "percentile_252",
        "ret_z_200",
        "session_vwap",
    ]
    # S2/S3 features
    s2_s3_features = ["ema_40", "bb_pb_20"]
    
    # Create tiny arrays (size 2) to keep file small
    n = 2
    ts = np.arange(n) * 3600
    ts = ts.astype("datetime64[s]")
    
    features_data = {"ts": ts}
    for feat in s1_features + s2_s3_features:
        features_data[feat] = np.array([0.0, 1.0], dtype=np.float64)
    
    # Save NPZ
    np.savez(str(target_path), **features_data)
    
    # Verify file was created
    assert target_path.exists(), f"Failed to create dummy feature cache at {target_path}"
"""Tests for signal series exporter V1."""

import pandas as pd
import numpy as np
import pytest
from pathlib import Path

from FishBroWFS_V2.engine.signal_exporter import build_signal_series_v1, REQUIRED_COLUMNS
from FishBroWFS_V2.portfolio.instruments import load_instruments_config


def test_mnq_usd_fx_to_base_32():
    """MNQ (USD): fx_to_base=32 時 margin_base 正確"""
    # Create test data
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=5, freq="5min"),
        "close": [15000.0, 15010.0, 15020.0, 15030.0, 15040.0],
    })
    
    fills_df = pd.DataFrame({
        "ts": [bars_df["ts"][0], bars_df["ts"][2]],
        "qty": [1.0, -1.0],
    })
    
    # MNQ parameters (USD) - updated values from instruments.yaml (exchange_maintenance)
    df = build_signal_series_v1(
        instrument="CME.MNQ",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=32.0,
        multiplier=2.0,
        initial_margin_per_contract=4000.0,
        maintenance_margin_per_contract=3500.0,
    )
    
    # Check columns
    assert list(df.columns) == REQUIRED_COLUMNS
    
    # Check fx_to_base is 32.0 for all rows
    assert (df["fx_to_base"] == 32.0).all()
    
    # Check close_base = close * 32.0
    assert np.allclose(df["close_base"].values, df["close"].values * 32.0)
    
    # Check margin calculations
    # Row 0: position=1, margin_initial_base = 1 * 4000.0 * 32 = 128000.0
    assert np.isclose(df.loc[0, "margin_initial_base"], 1 * 4000.0 * 32.0)
    assert np.isclose(df.loc[0, "margin_maintenance_base"], 1 * 3500.0 * 32.0)
    
    # Row 2: position=0 (after exit), margin should be 0
    assert np.isclose(df.loc[2, "margin_initial_base"], 0.0)
    assert np.isclose(df.loc[2, "margin_maintenance_base"], 0.0)
    
    # Check notional_base = position * close_base * multiplier
    # Row 0: position=1, close_base=15000*32=480000, multiplier=2, notional=960000
    expected_notional = 1 * 15000.0 * 32.0 * 2.0
    assert np.isclose(df.loc[0, "notional_base"], expected_notional)


def test_mxf_twd_fx_to_base_1():
    """MXF (TWD): fx_to_base=1 時 margin_base 正確"""
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=3, freq="5min"),
        "close": [18000.0, 18050.0, 18100.0],
    })
    
    fills_df = pd.DataFrame({
        "ts": [bars_df["ts"][0]],
        "qty": [2.0],
    })
    
    # MXF parameters (TWD) - updated values from instruments.yaml (conservative_over_exchange)
    df = build_signal_series_v1(
        instrument="TWF.MXF",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="TWD",
        fx_to_base=1.0,
        multiplier=50.0,
        initial_margin_per_contract=88000.0,
        maintenance_margin_per_contract=80000.0,
    )
    
    # Check fx_to_base is 1.0 for all rows
    assert (df["fx_to_base"] == 1.0).all()
    
    # Check close_base = close * 1.0 (same)
    assert np.allclose(df["close_base"].values, df["close"].values)
    
    # Check margin calculations (no FX conversion)
    # Row 0: position=2, margin_initial_base = 2 * 88000 * 1 = 176000
    assert np.isclose(df.loc[0, "margin_initial_base"], 2 * 88000.0)
    assert np.isclose(df.loc[0, "margin_maintenance_base"], 2 * 80000.0)
    
    # Check notional_base
    expected_notional = 2 * 18000.0 * 1.0 * 50.0
    assert np.isclose(df.loc[0, "notional_base"], expected_notional)


def test_multiple_fills_same_bar():
    """同一 bar 多 fills（+1, +2, -1）→ position 正確"""
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=3, freq="5min"),
        "close": [100.0, 101.0, 102.0],
    })
    
    # Three fills at same timestamp (first bar)
    fill_ts = bars_df["ts"][0]
    fills_df = pd.DataFrame({
        "ts": [fill_ts, fill_ts, fill_ts],
        "qty": [1.0, 2.0, -1.0],  # Net +2
    })
    
    df = build_signal_series_v1(
        instrument="TEST",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=1.0,
        multiplier=1.0,
        initial_margin_per_contract=1000.0,
        maintenance_margin_per_contract=800.0,
    )
    
    # Check position_contracts
    # Bar 0: position = 1 + 2 - 1 = 2
    assert np.isclose(df.loc[0, "position_contracts"], 2.0)
    # Bar 1 and 2: position stays 2 (no more fills)
    assert np.isclose(df.loc[1, "position_contracts"], 2.0)
    assert np.isclose(df.loc[2, "position_contracts"], 2.0)


def test_fills_between_bars_merge_asof():
    """fills 落在兩根 bar 中間 → merge_asof 對齊規則正確"""
    # Create bars at 00:00, 00:05, 00:10
    bars_df = pd.DataFrame({
        "ts": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 00:05", "2025-01-01 00:10"]),
        "close": [100.0, 101.0, 102.0],
    })
    
    # Fill at 00:02 (between bar 0 and bar 1)
    # Should be assigned to bar 0 (backward fill, <= fill_ts 的最近 bar ts)
    fills_df = pd.DataFrame({
        "ts": pd.to_datetime(["2025-01-01 00:02"]),
        "qty": [1.0],
    })
    
    df = build_signal_series_v1(
        instrument="TEST",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=1.0,
        multiplier=1.0,
        initial_margin_per_contract=1000.0,
        maintenance_margin_per_contract=800.0,
    )
    
    # Check position_contracts
    # Bar 0: position = 1 (fill assigned to bar 0)
    assert np.isclose(df.loc[0, "position_contracts"], 1.0)
    # Bar 1 and 2: position stays 1
    assert np.isclose(df.loc[1, "position_contracts"], 1.0)
    assert np.isclose(df.loc[2, "position_contracts"], 1.0)
    
    # Test fill at 00:07 (between bar 1 and bar 2)
    fills_df2 = pd.DataFrame({
        "ts": pd.to_datetime(["2025-01-01 00:07"]),
        "qty": [2.0],
    })
    
    df2 = build_signal_series_v1(
        instrument="TEST",
        bars_df=bars_df,
        fills_df=fills_df2,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=1.0,
        multiplier=1.0,
        initial_margin_per_contract=1000.0,
        maintenance_margin_per_contract=800.0,
    )
    
    # Bar 0: position = 0
    assert np.isclose(df2.loc[0, "position_contracts"], 0.0)
    # Bar 1: position = 2 (fill at 00:07 assigned to bar 1 at 00:05)
    assert np.isclose(df2.loc[1, "position_contracts"], 2.0)
    # Bar 2: position stays 2
    assert np.isclose(df2.loc[2, "position_contracts"], 2.0)


def test_deterministic_same_input():
    """deterministic：同 input 連跑兩次 df.equals(True)"""
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=10, freq="5min"),
        "close": np.random.randn(10) * 100 + 15000.0,
    })
    
    fills_df = pd.DataFrame({
        "ts": bars_df["ts"].sample(5, random_state=42).sort_values(),
        "qty": np.random.choice([-1.0, 1.0], 5),
    })
    
    # First run
    df1 = build_signal_series_v1(
        instrument="CME.MNQ",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=32.0,
        multiplier=2.0,
        initial_margin_per_contract=4000.0,
        maintenance_margin_per_contract=3500.0,
    )
    
    # Second run with same input
    df2 = build_signal_series_v1(
        instrument="CME.MNQ",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=32.0,
        multiplier=2.0,
        initial_margin_per_contract=4000.0,
        maintenance_margin_per_contract=3500.0,
    )
    
    # DataFrames should be equal
    pd.testing.assert_frame_equal(df1, df2)


def test_columns_complete_no_nan():
    """欄位完整且無 NaN（close_base/notional/margins）"""
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=3, freq="5min"),
        "close": [100.0, 101.0, 102.0],
    })
    
    fills_df = pd.DataFrame({
        "ts": [bars_df["ts"][0], bars_df["ts"][2]],
        "qty": [1.0, -1.0],
    })
    
    df = build_signal_series_v1(
        instrument="TEST",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=1.0,
        multiplier=1.0,
        initial_margin_per_contract=1000.0,
        maintenance_margin_per_contract=800.0,
    )
    
    # Check all required columns present
    assert set(df.columns) == set(REQUIRED_COLUMNS)
    
    # Check no NaN values in numeric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    assert not df[numeric_cols].isna().any().any()
    
    # Specifically check calculated columns
    assert not df["close_base"].isna().any()
    assert not df["notional_base"].isna().any()
    assert not df["margin_initial_base"].isna().any()
    assert not df["margin_maintenance_base"].isna().any()


def test_instruments_config_loader():
    """Test instruments config loader with SHA256."""
    config_path = Path("configs/portfolio/instruments.yaml")
    
    # Load config
    cfg = load_instruments_config(config_path)
    
    # Check basic structure
    assert cfg.version == 1
    assert cfg.base_currency == "TWD"
    assert "USD" in cfg.fx_rates
    assert "TWD" in cfg.fx_rates
    assert cfg.fx_rates["TWD"] == 1.0
    
    # Check instruments
    assert "CME.MNQ" in cfg.instruments
    assert "TWF.MXF" in cfg.instruments
    
    mnq = cfg.instruments["CME.MNQ"]
    assert mnq.currency == "USD"
    assert mnq.multiplier == 2.0
    assert mnq.initial_margin_per_contract == 4000.0
    assert mnq.maintenance_margin_per_contract == 3500.0
    assert mnq.margin_basis == "exchange_maintenance"
    
    mxf = cfg.instruments["TWF.MXF"]
    assert mxf.currency == "TWD"
    assert mxf.multiplier == 50.0
    assert mxf.initial_margin_per_contract == 88000.0
    assert mxf.maintenance_margin_per_contract == 80000.0
    assert mxf.margin_basis == "conservative_over_exchange"
    
    # Check SHA256 is present and non-empty
    assert cfg.sha256
    assert len(cfg.sha256) == 64  # SHA256 hex length
    
    # Test that modifying config changes SHA256
    import tempfile
    import yaml
    
    # Create a modified config
    with open(config_path, "r") as f:
        original_data = yaml.safe_load(f)
    
    modified_data = original_data.copy()
    modified_data["fx_rates"]["USD"] = 33.0  # Change FX rate
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        yaml.dump(modified_data, tmp)
        tmp_path = Path(tmp.name)
    
    try:
        cfg2 = load_instruments_config(tmp_path)
        # SHA256 should be different
        assert cfg2.sha256 != cfg.sha256
    finally:
        tmp_path.unlink()


def test_anti_regression_margin_minimums():
    """防回歸測試：確保保證金不低於交易所 maintenance 等級"""
    config_path = Path("configs/portfolio/instruments.yaml")
    cfg = load_instruments_config(config_path)
    
    # MNQ: 必須大於 3000 USD (避免被改回 day margin)
    mnq = cfg.instruments["CME.MNQ"]
    assert mnq.maintenance_margin_per_contract > 3000.0, \
        f"MNQ maintenance margin ({mnq.maintenance_margin_per_contract}) must be > 3000 USD to avoid day margin"
    assert mnq.initial_margin_per_contract > mnq.maintenance_margin_per_contract, \
        f"MNQ initial margin ({mnq.initial_margin_per_contract}) must be > maintenance margin"
    
    # MXF: 必須 ≥ TAIFEX 官方 maintenance (64,750 TWD)
    mxf = cfg.instruments["TWF.MXF"]
    taifex_official_maintenance = 64750.0
    assert mxf.maintenance_margin_per_contract >= taifex_official_maintenance, \
        f"MXF maintenance margin ({mxf.maintenance_margin_per_contract}) must be >= TAIFEX official ({taifex_official_maintenance})"
    
    # MXF: 必須 ≥ TAIFEX 官方 initial (84,500 TWD)
    taifex_official_initial = 84500.0
    assert mxf.initial_margin_per_contract >= taifex_official_initial, \
        f"MXF initial margin ({mxf.initial_margin_per_contract}) must be >= TAIFEX official ({taifex_official_initial})"
    
    # 檢查 margin_basis 符合預期
    assert mnq.margin_basis in ["exchange_maintenance", "conservative_over_exchange"], \
        f"MNQ margin_basis must be exchange_maintenance or conservative_over_exchange, got {mnq.margin_basis}"
    assert mxf.margin_basis in ["exchange_maintenance", "conservative_over_exchange"], \
        f"MXF margin_basis must be exchange_maintenance or conservative_over_exchange, got {mxf.margin_basis}"
    
    # 禁止使用 broker_day
    assert mnq.margin_basis != "broker_day", "MNQ must not use broker_day margin basis"
    assert mxf.margin_basis != "broker_day", "MXF must not use broker_day margin basis"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
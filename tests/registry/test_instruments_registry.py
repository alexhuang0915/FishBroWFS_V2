import pytest
from pathlib import Path

from config.registry.instruments import load_instruments
from config import ConfigError


def _write_registry(path: Path, content: str) -> None:
    path.write_text(content)


def test_instrument_missing_trade_date_roll_time_local(tmp_path: Path):
    path = tmp_path / "missing_roll.yaml"
    _write_registry(
        path,
        """version: "1.0"
instruments:
  - id: "XYZ.FUT"
    display_name: "Example Future"
    type: "future"
    default_profile: "XYZ_PROFILE"
    currency: "USD"
    default_timeframe: 60
    timezone: "America/New_York"
default: "XYZ.FUT"
""",
    )

    with pytest.raises(ConfigError):
        load_instruments(path=path)


def test_instrument_missing_timezone(tmp_path: Path):
    path = tmp_path / "missing_timezone.yaml"
    _write_registry(
        path,
        """version: "1.0"
instruments:
  - id: "XYZ.FUT"
    display_name: "Example Future"
    type: "future"
    default_profile: "XYZ_PROFILE"
    currency: "USD"
    default_timeframe: 60
    trade_date_roll_time_local: "17:00"
default: "XYZ.FUT"
""",
    )

    with pytest.raises(ConfigError):
        load_instruments(path=path)


def test_valid_instrument_registry(tmp_path: Path):
    path = tmp_path / "valid.yaml"
    _write_registry(
        path,
        """version: "1.0"
instruments:
  - id: "XYZ.FUT"
    display_name: "Example Future"
    type: "future"
    default_profile: "XYZ_PROFILE"
    currency: "USD"
    default_timeframe: 60
    timezone: "America/New_York"
    trade_date_roll_time_local: "17:00"
default: "XYZ.FUT"
""",
    )

    registry = load_instruments(path=path)
    assert registry.default == "XYZ.FUT"
    assert registry.get_instrument_by_id("XYZ.FUT") is not None

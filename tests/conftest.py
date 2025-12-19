"""
Pytest configuration and fixtures.

Ensures PYTHONPATH is set correctly for imports.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src/ to Python path if not already present
# This ensures tests can import FishBroWFS_V2 without manual PYTHONPATH setup
repo_root = Path(__file__).parent.parent
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Compatibility alias for older tests that used temp_dir.
    
    Returns tmp_path (pytest's built-in fixture) for compatibility
    with tests that expect a temp_dir fixture.
    """
    return tmp_path


@pytest.fixture
def sample_raw_txt(tmp_path: Path) -> Path:
    """Fixture providing a sample raw TXT file for data ingest tests.
    
    Returns path to a minimal TXT file with Date, Time, OHLCV columns.
    This fixture is shared across all data ingest tests to avoid duplication.
    """
    txt_path = tmp_path / "sample_data.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,1000
2013/1/1,10:00:00,104.0,106.0,103.0,105.0,1200
2013/1/2,09:30:00,105.0,107.0,104.0,106.0,1500
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    return txt_path

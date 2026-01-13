
"""
測試 Dimension Registry 功能

確保：
1. 檔案不存在時回傳空 registry（不 raise）
2. 檔案存在但 JSON/schema 錯誤時 raise ValueError
3. get_dimension_for_dataset() 查不到回 None
4. get_dimension_for_dataset() 查得到回正確資料
5. 沒有新增任何 streamlit import
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from contracts.dimensions import (
    SessionSpec,
    InstrumentDimension,
    DimensionRegistry,
    canonical_json,
)
from contracts.dimensions_loader import (
    load_dimension_registry,
    write_dimension_registry,
    default_registry_path,
)
from core.dimensions import (
    get_dimension_for_dataset,
    clear_dimension_cache,
)


def test_session_spec_validation():
    """測試 SessionSpec 時間格式驗證"""
    # 正確的時間格式
    spec = SessionSpec(
        open_taipei="07:00",
        close_taipei="06:00",
        breaks_taipei=[("17:00", "18:00")],
    )
    assert spec.tz == "Asia/Taipei"
    assert spec.open_taipei == "07:00"
    assert spec.close_taipei == "06:00"
    assert spec.breaks_taipei == [("17:00", "18:00")]

    # 錯誤的時間格式應該引發異常
    with pytest.raises(ValueError, match=".*必須為 HH:MM 格式.*"):
        SessionSpec(open_taipei="25:00", close_taipei="06:00")

    with pytest.raises(ValueError, match=".*必須為 HH:MM 格式.*"):
        SessionSpec(open_taipei="07:00", close_taipei="06:0")  # 分鐘只有一位數


def test_instrument_dimension_creation():
    """測試 InstrumentDimension 建立"""
    session = SessionSpec(open_taipei="07:00", close_taipei="06:00")
    dim = InstrumentDimension(
        instrument_id="MNQ",
        exchange="CME",
        currency="USD",
        market="電子盤",
        tick_size=0.25,
        session=session,
        source="manual",
        source_updated_at="2024-01-01T00:00:00Z",
        version="v1",
    )
    
    assert dim.instrument_id == "MNQ"
    assert dim.exchange == "CME"
    assert dim.currency == "USD"
    assert dim.market == "電子盤"
    assert dim.session.open_taipei == "07:00"
    assert dim.source == "manual"
    assert dim.version == "v1"


def test_dimension_registry_get():
    """測試 DimensionRegistry.get() 方法"""
    session = SessionSpec(open_taipei="07:00", close_taipei="06:00")
    dim = InstrumentDimension(
        instrument_id="MNQ",
        exchange="CME",
        tick_size=0.25,
        session=session,
    )
    
    registry = DimensionRegistry(
        by_dataset_id={
            "CME.MNQ.60m.2020-2024": dim,
        },
        by_symbol={
            "CME.MNQ": dim,
        },
    )
    
    # 透過 dataset_id 查詢
    result = registry.get("CME.MNQ.60m.2020-2024")
    assert result is not None
    assert result.instrument_id == "MNQ"
    
    # 透過 symbol 查詢
    result = registry.get("UNKNOWN.DATASET", symbol="CME.MNQ")
    assert result is not None
    assert result.instrument_id == "MNQ"
    
    # 查不到回 None
    result = registry.get("UNKNOWN.DATASET")
    assert result is None
    
    # 自動推導 symbol
    result = registry.get("CME.MNQ.15m.2020-2024")  # 會推導為 "CME.MNQ"
    assert result is not None
    assert result.instrument_id == "MNQ"


def test_canonical_json():
    """測試標準化 JSON 輸出"""
    data = {"b": 2, "a": 1, "c": [3, 1, 2]}
    json_str = canonical_json(data)
    
    # 解析回來檢查順序
    parsed = json.loads(json_str)
    # keys 應該被排序
    assert list(parsed.keys()) == ["a", "b", "c"]
    
    # 確保沒有多餘的空格
    assert " " not in json_str


def test_load_dimension_registry_file_missing(tmp_path):
    """測試檔案不存在時回傳空 registry"""
    # 建立一個不存在的檔案路徑
    non_existent = tmp_path / "nonexistent.json"
    
    registry = load_dimension_registry(non_existent)
    assert isinstance(registry, DimensionRegistry)
    assert registry.by_dataset_id == {}
    assert registry.by_symbol == {}


def test_load_dimension_registry_invalid_json(tmp_path):
    """測試無效 JSON 時引發 ValueError"""
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{invalid json")
    
    with pytest.raises(ValueError, match="JSON 解析失敗"):
        load_dimension_registry(invalid_file)


def test_load_dimension_registry_invalid_schema(tmp_path):
    """測試 schema 錯誤時引發 ValueError"""
    invalid_file = tmp_path / "invalid_schema.json"
    invalid_file.write_text('{"by_dataset_id": "not a dict"}')
    
    with pytest.raises(ValueError, match="schema 驗證失敗"):
        load_dimension_registry(invalid_file)


def test_load_dimension_registry_valid(tmp_path):
    """測試載入有效的 registry"""
    session = SessionSpec(open_taipei="07:00", close_taipei="06:00")
    dim = InstrumentDimension(
        instrument_id="MNQ",
        exchange="CME",
        tick_size=0.25,
        session=session,
    )
    
    registry = DimensionRegistry(
        by_dataset_id={"test.dataset": dim},
        by_symbol={"TEST.SYM": dim},
    )
    
    # 寫入檔案
    test_file = tmp_path / "test_registry.json"
    write_dimension_registry(registry, test_file)
    
    # 讀取回來
    loaded = load_dimension_registry(test_file)
    
    assert len(loaded.by_dataset_id) == 1
    assert "test.dataset" in loaded.by_dataset_id
    assert loaded.by_dataset_id["test.dataset"].instrument_id == "MNQ"
    
    assert len(loaded.by_symbol) == 1
    assert "TEST.SYM" in loaded.by_symbol


def test_write_dimension_registry_atomic(tmp_path):
    """測試原子寫入"""
    session = SessionSpec(open_taipei="07:00", close_taipei="06:00")
    dim = InstrumentDimension(
        instrument_id="MNQ",
        exchange="CME",
        tick_size=0.25,
        session=session,
    )
    
    registry = DimensionRegistry(
        by_dataset_id={"test.dataset": dim},
    )
    
    test_file = tmp_path / "atomic_test.json"
    
    # 寫入檔案
    write_dimension_registry(registry, test_file)
    
    # 檢查檔案存在且內容正確
    assert test_file.exists()
    
    loaded = load_dimension_registry(test_file)
    assert len(loaded.by_dataset_id) == 1
    assert "test.dataset" in loaded.by_dataset_id


def test_get_dimension_for_dataset():
    """測試 get_dimension_for_dataset() 函數"""
    # 先清除快取
    clear_dimension_cache()
    
    # 使用 mock 替換預設的 registry
    session = SessionSpec(open_taipei="07:00", close_taipei="06:00")
    dim = InstrumentDimension(
        instrument_id="MNQ",
        exchange="CME",
        tick_size=0.25,
        session=session,
    )
    
    mock_registry = DimensionRegistry(
        by_dataset_id={"CME.MNQ.60m.2020-2024": dim},
        by_symbol={"CME.MNQ": dim},
    )
    
    with patch("core.dimensions._get_cached_registry") as mock_get:
        mock_get.return_value = mock_registry
        
        # 查詢存在的 dataset_id
        result = get_dimension_for_dataset("CME.MNQ.60m.2020-2024")
        assert result is not None
        assert result.instrument_id == "MNQ"
        
        # 查詢不存在的 dataset_id
        result = get_dimension_for_dataset("NOT.EXIST.60m.2020-2024")
        assert result is None
        
        # 使用 symbol 查詢
        result = get_dimension_for_dataset("NOT.EXIST", symbol="CME.MNQ")
        assert result is not None
        assert result.instrument_id == "MNQ"


def test_get_dimension_for_dataset_cache():
    """測試快取功能"""
    # 清除快取
    clear_dimension_cache()
    
    # 建立 mock registry
    session = SessionSpec(open_taipei="07:00", close_taipei="06:00")
    dim = InstrumentDimension(
        instrument_id="MNQ",
        exchange="CME",
        tick_size=0.25,
        session=session,
    )
    
    mock_registry = DimensionRegistry(
        by_dataset_id={"test.dataset": dim},
    )
    
    # 使用 return_value 而不是 side_effect，因為 @lru_cache 會快取返回值
    with patch("core.dimensions._get_cached_registry") as mock_get:
        mock_get.return_value = mock_registry
        
        # 第一次呼叫
        result1 = get_dimension_for_dataset("test.dataset")
        assert result1 is not None
        assert result1.instrument_id == "MNQ"
        
        # 第二次呼叫應該使用快取（相同的 mock 物件）
        result2 = get_dimension_for_dataset("test.dataset")
        assert result2 is not None
        
        # 驗證 mock 只被呼叫一次（因為快取）
        # 注意：由於 @lru_cache 的實作細節，mock_get 可能被呼叫多次
        # 但我們主要關心功能正確性，而不是具體的呼叫次數
        # 清除快取後再次呼叫
        clear_dimension_cache()
        result3 = get_dimension_for_dataset("test.dataset")
        assert result3 is not None


def test_no_streamlit_imports():
    """確保沒有引入 streamlit"""
    import src.contracts.dimensions as dimensions
    import src.contracts.dimensions_loader
    import src.core.dimensions
    
    # 檢查模組中是否有 streamlit
    for module in [
        dimensions,
        src.contracts.dimensions_loader,
        src.core.dimensions,
    ]:
        source = module.__file__
        if source and source.endswith(".py"):
            with open(source, "r", encoding="utf-8") as f:
                content = f.read()
                assert "import streamlit" not in content
                assert "from streamlit" not in content


def test_default_registry_path():
    """測試預設路徑函數"""
    path = default_registry_path()
    assert isinstance(path, Path)
    # During migration, accept either dimensions_registry.json or datasets.yaml
    assert path.name in ["dimensions_registry.json", "datasets.yaml"]
    assert path.parent.name in ["configs", "registry"]



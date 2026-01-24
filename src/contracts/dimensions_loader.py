
from __future__ import annotations

import json
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dimensions import DimensionRegistry, InstrumentDimension, SessionSpec, canonical_json
# from config.profiles import ProfileConfig, load_profile # REMOVED


def default_registry_path() -> Path:
    """
    取得預設維度註冊表檔案路徑
    
    Returns:
        Path 物件指向 configs/dimensions_registry.json (legacy)
        or configs/registry/datasets.yaml (new)
    """
    # 從專案根目錄開始
    project_root = Path(__file__).parent.parent.parent
    
    # First try YAML registry (new)
    yaml_path = project_root / "configs" / "registry" / "datasets.yaml"
    if yaml_path.exists():
        return yaml_path
    
    # Fall back to legacy JSON
    return project_root / "configs" / "dimensions_registry.json"


def load_dimension_registry(path: Path | None = None) -> DimensionRegistry:
    """
    載入維度註冊表
    
    Args:
        path: 註冊表檔案路徑，若為 None 則使用預設路徑
    
    Returns:
        DimensionRegistry 物件
    
    Raises:
        ValueError: 檔案存在但 JSON 解析失敗或 schema 驗證失敗
        FileNotFoundError: 不會引發，檔案不存在時回傳空註冊表
    """
    if path is None:
        path = default_registry_path()
    
    # 檔案不存在 -> 回傳空註冊表
    if not path.exists():
        return DimensionRegistry()
    
    # Determine file type and load accordingly
    if path.suffix.lower() in ['.yaml', '.yml']:
        return _load_dimension_registry_from_yaml(path)
    else:
        # Assume JSON (legacy format)
        return _load_dimension_registry_from_json(path)


def _load_dimension_registry_from_json(path: Path) -> DimensionRegistry:
    """
    從 JSON 檔案載入維度註冊表 (legacy format)
    """
    # 讀取檔案內容
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取維度註冊表檔案 {path}: {e}")
    
    # 解析 JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"維度註冊表 JSON 解析失敗 {path}: {e}")
    
    # 驗證並建立 DimensionRegistry
    try:
        # 確保有必要的鍵
        if not isinstance(data, dict):
            raise ValueError("根節點必須是字典")
        
        # 建立 registry，pydantic 會驗證 schema
        registry = DimensionRegistry(**data)
        return registry
    except Exception as e:
        raise ValueError(f"維度註冊表 schema 驗證失敗 {path}: {e}")


def _load_dimension_registry_from_yaml(path: Path) -> DimensionRegistry:
    """
    從 YAML 檔案載入維度註冊表 (new format)
    
    Note: This now builds DimensionRegistry from profiles + instruments registry
    instead of reading from datasets.yaml directly.
    """
    try:
        # Build DimensionRegistry from profiles and instruments registry
        return _build_dimension_registry_from_profiles()
    except Exception as e:
        raise ValueError(f"無法從 profiles 建立維度註冊表: {e}")


def _build_dimension_registry_from_profiles() -> DimensionRegistry:
    """
    Stubbed for Mainline: Returns hardcoded InstrumentDimension for MNQ/VX.
    """
    from .dimensions import SessionSpec # Ensure imported
    
    # Stub MNQ session
    mnq_session = SessionSpec(
        tz="Asia/Taipei",
        open_taipei = "06:00",
        close_taipei = "05:00",
        breaks_taipei=[]
    )
    
    # Stub VX session
    vx_session = SessionSpec(
        tz="Asia/Taipei",
        open_taipei="06:00",
        close_taipei="05:00",
        breaks_taipei=[]
    )

    mnq = InstrumentDimension(
        instrument_id="MNQ",
        exchange="CME",
        market="FUTURE",
        currency="USD",
        tick_size=0.25,
        session=mnq_session,
        source="stub",
        source_updated_at="2026-01-22T00:00:00Z",
        version="v2"
    )
    
    vx = InstrumentDimension(
        instrument_id="VX",
        exchange="CFE",
        market="FUTURE",
        currency="USD",
        tick_size=0.05,
        session=vx_session,
        source="stub",
        source_updated_at="2026-01-22T00:00:00Z",
        version="v2"
    )

    by_symbol = {
        "CME.MNQ": mnq,
        "CFE.VX": vx
    }
    
    by_dataset_id = {
        # Catch-all or specific? The build command passes "CME.MNQ.60m.2020-2024"
        "CME.MNQ.60m.2020-2024": mnq,
        "CFE.VX.60m.2020-2024": vx
    }

    return DimensionRegistry(by_dataset_id=by_dataset_id, by_symbol=by_symbol)

# Helper function _build_instrument_dimension Removed (unused)


def write_dimension_registry(registry: DimensionRegistry, path: Path | None = None) -> None:
    """
    寫入維度註冊表（原子寫入）
    
    Args:
        registry: 要寫入的 DimensionRegistry
        path: 目標檔案路徑，若為 None 則使用預設路徑
    
    Note:
        使用原子寫入（tmp + replace）避免寫入過程中斷
    """
    if path is None:
        path = default_registry_path()
    
    # 確保目錄存在
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 轉換為字典並標準化 JSON
    data = registry.model_dump()
    json_str = canonical_json(data)
    
    # 原子寫入：先寫到暫存檔案，再移動
    temp_path = path.with_suffix(".json.tmp")
    try:
        temp_path.write_text(json_str, encoding="utf-8")
        temp_path.replace(path)
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        raise IOError(f"寫入維度註冊表失敗 {path}: {e}")




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
        Mainline: use any stable YAML path under configs/registry/ so we can
        deterministically build DimensionRegistry without relying on a datasets registry.
    """
    # 從專案根目錄開始
    project_root = Path(__file__).parent.parent.parent

    # Mainline: datasets registry is removed; DimensionRegistry is derived (stubbed)
    # from profiles/instruments. Keep a YAML suffix to route to YAML loader.
    return project_root / "configs" / "registry" / "instruments.yaml"


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
    
    Note: Mainline builds DimensionRegistry from profiles/instruments and does not
    parse the YAML content for registry rows.
    """
    try:
        # Build DimensionRegistry from profiles and instruments registry
        return _build_dimension_registry_from_profiles()
    except Exception as e:
        raise ValueError(f"無法從 profiles 建立維度註冊表: {e}")


def _build_dimension_registry_from_profiles() -> DimensionRegistry:
    """
    Build DimensionRegistry from configs/registry/instruments.yaml and each instrument's default_profile.

    Note:
      - This registry is used mainly as a stable lookup for session tz and tick_size.
      - Detailed session boundaries are enforced via `core.trade_dates.is_trading_time_for_instrument`
        (DST-aware and profile-window-aware), so we keep SessionSpec minimal and deterministic here.
    """
    project_root = Path(__file__).parent.parent.parent
    instruments_path = project_root / "configs" / "registry" / "instruments.yaml"
    profiles_dir = project_root / "configs" / "profiles"

    if not instruments_path.exists():
        return DimensionRegistry()

    doc = yaml.safe_load(instruments_path.read_text(encoding="utf-8")) or {}
    instruments = doc.get("instruments") or []
    if not isinstance(instruments, list):
        return DimensionRegistry()

    by_symbol: Dict[str, InstrumentDimension] = {}
    by_dataset_id: Dict[str, InstrumentDimension] = {}

    for item in instruments:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("id") or "").strip()
        if not symbol:
            continue

        exchange = str(item.get("exchange") or "").strip()
        currency = str(item.get("currency") or "").strip()
        market = str(item.get("type") or "").strip().upper()

        try:
            tick_size = float(item.get("tick_size"))
        except Exception:
            continue

        # Determine data tz from profile if available; default to Taipei.
        data_tz = "Asia/Taipei"
        default_profile = str(item.get("default_profile") or "").strip()
        if default_profile:
            prof_path = profiles_dir / f"{default_profile}.yaml"
            if prof_path.exists():
                try:
                    prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
                    data_tz = str(prof.get("data_tz") or data_tz)
                except Exception:
                    pass

        # InstrumentDimension expects instrument_id like "MNQ" (not "CME.MNQ").
        parts = symbol.split(".", 1)
        instrument_id = parts[1] if len(parts) == 2 else symbol

        session = SessionSpec(
            tz=data_tz,
            open_taipei="00:00",
            close_taipei="23:59",
            breaks_taipei=[],
            notes="derived_from_configs",
        )

        dim = InstrumentDimension(
            instrument_id=instrument_id,
            exchange=exchange,
            market=market,
            currency=currency,
            tick_size=tick_size,
            session=session,
            source="derived_from_configs",
            source_updated_at="",
            version="v2",
        )

        by_symbol[symbol] = dim
        # Mainline: dataset_id == instrument symbol (DimensionRegistry.get also derives symbol from legacy ids).
        by_dataset_id[symbol] = dim

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

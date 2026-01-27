
"""
Strategy Feature Declaration 合約

定義策略特徵需求的統一格式，讓 resolver 能夠解析與驗證。
"""

from __future__ import annotations

import json
from typing import List, Optional, Any
from pydantic import BaseModel, Field


class FeatureRef(BaseModel):
    """
    單一特徵引用
    
    Attributes:
        name: 特徵名稱，例如 "atr_14", "ret_z_200", "session_vwap"
        timeframe_min: timeframe 分鐘數，例如 15, 30, 60, 120, 240
    """
    name: str = Field(..., description="特徵名稱")
    timeframe_min: int = Field(..., description="timeframe 分鐘數 (15, 30, 60, 120, 240)")


class StrategyFeatureRequirements(BaseModel):
    """
    策略特徵需求
    
    Attributes:
        strategy_id: 策略 ID
        required: 必需的特徵列表
        optional: 可選的特徵列表（預設為空）
        min_schema_version: 最小 schema 版本（預設 "v1"）
        notes: 備註（預設為空字串）
    """
    strategy_id: str = Field(..., description="策略 ID")
    required: List[FeatureRef] = Field(..., description="必需的特徵列表")
    optional: List[FeatureRef] = Field(default_factory=list, description="可選的特徵列表")
    min_schema_version: str = Field(default="v1", description="最小 schema 版本")
    notes: str = Field(default="", description="備註")


def canonical_json_requirements(req: StrategyFeatureRequirements) -> str:
    """
    產生 deterministic JSON 字串
    
    使用 sort_keys=True 確保字典順序穩定，separators 移除多餘空白。
    
    Args:
        req: StrategyFeatureRequirements 實例
    
    Returns:
        deterministic JSON 字串
    """
    # 轉換為字典（使用 pydantic 的 dict 方法）
    data = req.model_dump()
    
    # 使用與其他 contracts 一致的 canonical_json 格式
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def load_requirements_from_json(json_path: str) -> StrategyFeatureRequirements:
    """
    從 JSON 檔案載入策略特徵需求
    
    Args:
        json_path: JSON 檔案路徑
    
    Returns:
        StrategyFeatureRequirements 實例
    
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: JSON 解析失敗或驗證失敗
    """
    import json
    from pathlib import Path
    
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"需求檔案不存在: {json_path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取需求檔案 {json_path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"需求 JSON 解析失敗 {json_path}: {e}")
    
    try:
        return StrategyFeatureRequirements(**data)
    except Exception as e:
        raise ValueError(f"需求資料驗證失敗 {json_path}: {e}")


def load_requirements_from_yaml(
    yaml_path: str,
    *,
    default_timeframe_min: int = 60,
) -> StrategyFeatureRequirements:
    """
    從 YAML 策略配置檔案載入策略特徵需求

    Args:
        yaml_path: YAML 策略配置檔案路徑

    Returns:
        StrategyFeatureRequirements 實例

    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: YAML 解析失敗或驗證失敗
    """
    import yaml
    from pathlib import Path
    
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"策略配置檔案不存在: {yaml_path}")
    
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"策略配置 YAML 解析失敗 {yaml_path}: {e}") from e
    
    # 提取 strategy_id
    strategy_id = data.get("strategy_id")
    if not strategy_id:
        raise ValueError(f"策略配置缺少 strategy_id: {yaml_path}")
    
    # 提取 features
    features = data.get("features", [])
    
    # 轉換為 StrategyFeatureRequirements 格式
    required = []
    optional = []
    
    def _parse_timeframe(raw: Any) -> int:
        if raw is None or raw == "":
            return int(default_timeframe_min)
        if isinstance(raw, str):
            token = raw.strip().upper()
            if token in {"RUN", "@RUN", "@TF", "@TIMEFRAME"}:
                return int(default_timeframe_min)
            return int(token)
        return int(raw)

    def _consume(items):
        for feature in items or []:
            if not isinstance(feature, dict):
                continue
            name = feature.get("name")
            timeframe = feature.get("timeframe")
            required_flag = feature.get("required", True)
            if not name:
                raise ValueError(f"特徵缺少 name: {feature}")
            try:
                tf_min = _parse_timeframe(timeframe)
            except Exception as e:
                raise ValueError(f"無法解析 timeframe: {feature}") from e
            feature_ref = FeatureRef(name=str(name), timeframe_min=tf_min)
            if required_flag:
                required.append(feature_ref)
            else:
                optional.append(feature_ref)

    def _expand_decl(decl):
        if isinstance(decl, list):
            return decl
        if isinstance(decl, dict):
            from control.feature_packs_yaml import expand_pack_with_overrides

            pack_id = decl.get("pack")
            add = decl.get("add")
            remove = decl.get("remove")
            return expand_pack_with_overrides(
                pack_id=str(pack_id).strip() if pack_id else None,
                add=add if isinstance(add, list) else None,
                remove=remove if isinstance(remove, list) else None,
            )
        return []

    # legacy: list
    if isinstance(features, list):
        _consume(features)
    # v2: dict partitions
    elif isinstance(features, dict):
        _consume(_expand_decl(features.get("data1")))
        _consume(_expand_decl(features.get("data2")))
        _consume(_expand_decl(features.get("cross")))
    else:
        raise ValueError(f"不支援的 features 格式: {type(features)}")
    
    return StrategyFeatureRequirements(
        strategy_id=strategy_id,
        required=required,
        optional=optional,
        min_schema_version="v1",
        notes=f"Loaded from YAML: {yaml_path}"
    )


def save_requirements_to_json(
    req: StrategyFeatureRequirements,
    json_path: str,
) -> None:
    """
    將策略特徵需求儲存為 JSON 檔案

    Args:
        req: StrategyFeatureRequirements 實例
        json_path: JSON 檔案路徑

    Raises:
        ValueError: 寫入失敗
    """
    import json
    from pathlib import Path

    path = Path(json_path)

    # 建立目錄（如果不存在）
    path.parent.mkdir(parents=True, exist_ok=True)

    # 使用 canonical JSON 格式
    json_str = canonical_json_requirements(req)

    try:
        path.write_text(json_str, encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法寫入需求檔案 {json_path}: {e}")

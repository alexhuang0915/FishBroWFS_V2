
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SessionSpec(BaseModel):
    """交易時段規格，所有時間皆為台北時間 (Asia/Taipei)"""
    tz: str = "Asia/Taipei"
    open_taipei: str  # HH:MM 格式，例如 "07:00"
    close_taipei: str  # HH:MM 格式，例如 "06:00"（次日）
    breaks_taipei: List[Tuple[str, str]] = []  # 休市時段列表，每個時段為 (start, end)
    notes: str = ""  # 備註，例如 "CME MNQ 電子盤"

    @model_validator(mode="after")
    def _validate_time_format(self) -> "SessionSpec":
        """驗證時間格式為 HH:MM"""
        import re
        time_pattern = re.compile(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$")
        
        if not time_pattern.match(self.open_taipei):
            raise ValueError(f"open_taipei 必須為 HH:MM 格式，收到: {self.open_taipei}")
        if not time_pattern.match(self.close_taipei):
            raise ValueError(f"close_taipei 必須為 HH:MM 格式，收到: {self.close_taipei}")
        
        for start, end in self.breaks_taipei:
            if not time_pattern.match(start):
                raise ValueError(f"break start 必須為 HH:MM 格式，收到: {start}")
            if not time_pattern.match(end):
                raise ValueError(f"break end 必須為 HH:MM 格式，收到: {end}")
        
        return self


class InstrumentDimension(BaseModel):
    """商品維度定義，包含交易所、時區、交易時段等資訊"""
    instrument_id: str  # 例如 "MNQ", "MES", "NK", "TXF"
    exchange: str  # 例如 "CME", "TAIFEX"
    market: str = ""  # 可選，例如 "電子盤", "日盤"
    currency: str = ""  # 可選，例如 "USD", "TWD"
    tick_size: float  # tick 大小，必須 > 0，例如 MNQ=0.25, MES=0.25, MXF=1.0
    session: SessionSpec
    source: str = "manual"  # 來源標記，未來可為 "official_site"
    source_updated_at: str = ""  # 來源更新時間，ISO 格式
    version: str = "v1"  # 版本標記，未來升級用

    @model_validator(mode="after")
    def _validate_tick_size(self) -> "InstrumentDimension":
        """驗證 tick_size 為正數"""
        if self.tick_size <= 0:
            raise ValueError(f"tick_size 必須 > 0，收到: {self.tick_size}")
        return self


class DimensionRegistry(BaseModel):
    """維度註冊表，支援透過 dataset_id 或 symbol 查詢"""
    model_config = ConfigDict(extra="forbid")  # 嚴格禁止未定義欄位
    
    by_dataset_id: Dict[str, InstrumentDimension] = Field(default_factory=dict)
    by_symbol: Dict[str, InstrumentDimension] = Field(default_factory=dict)

    def get(self, dataset_id: str, symbol: str | None = None) -> InstrumentDimension | None:
        """
        查詢維度定義，優先使用 dataset_id，其次 symbol
        
        Args:
            dataset_id: 資料集 ID，例如 "CME.MNQ.60m.2020-2024"
            symbol: 商品符號，例如 "CME.MNQ"
        
        Returns:
            InstrumentDimension 或 None（如果找不到）
        """
        # 優先使用 dataset_id
        if dataset_id in self.by_dataset_id:
            return self.by_dataset_id[dataset_id]
        
        # 其次使用 symbol
        if symbol and symbol in self.by_symbol:
            return self.by_symbol[symbol]
        
        # 如果沒有提供 symbol，嘗試從 dataset_id 推導 symbol
        if not symbol:
            # 簡單推導：取前兩個部分（例如 "CME.MNQ.60m.2020-2024" -> "CME.MNQ"）
            parts = dataset_id.split(".")
            if len(parts) >= 2:
                derived_symbol = f"{parts[0]}.{parts[1]}"
                if derived_symbol in self.by_symbol:
                    return self.by_symbol[derived_symbol]
        
        return None


def canonical_json(obj: dict) -> str:
    """
    產生標準化 JSON 字串，確保序列化一致性
    
    Args:
        obj: 要序列化的字典
    
    Returns:
        標準化 JSON 字串
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))



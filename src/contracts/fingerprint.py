
"""
Fingerprint Index 資料模型

用於記錄資料集每日的 hash 指紋，支援增量重算的證據系統。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Dict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.dimensions import canonical_json


class FingerprintIndex(BaseModel):
    """
    資料集指紋索引
    
    記錄資料集每日的 hash 指紋，用於檢測資料變更與增量重算。
    """
    model_config = ConfigDict(frozen=True)  # 不可變，確保 deterministic
    
    dataset_id: str = Field(
        ...,
        description="資料集 ID，例如 'CME.MNQ.60m.2020-2024'",
        examples=["CME.MNQ.60m.2020-2024", "TWF.MXF.15m.2018-2023"]
    )
    
    dataset_timezone: str = Field(
        default="Asia/Taipei",
        description="資料集時區，預設為台北時間",
        examples=["Asia/Taipei", "UTC"]
    )
    
    range_start: str = Field(
        ...,
        description="資料範圍起始日 (YYYY-MM-DD)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        examples=["2020-01-01", "2018-01-01"]
    )
    
    range_end: str = Field(
        ...,
        description="資料範圍結束日 (YYYY-MM-DD)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        examples=["2024-12-31", "2023-12-31"]
    )
    
    day_hashes: Dict[str, str] = Field(
        default_factory=dict,
        description="每日 hash 映射，key 為日期 (YYYY-MM-DD)，value 為 sha256 hex",
        examples=[{"2020-01-01": "abc123...", "2020-01-02": "def456..."}]
    )
    
    index_sha256: str = Field(
        ...,
        description="索引本身的 SHA256 hash，計算方式為 canonical_json(index_without_index_sha256)",
        examples=["a1b2c3d4e5f6..."]
    )
    
    build_notes: str = Field(
        default="",
        description="建置備註，例如建置工具版本或特殊處理說明",
        examples=["built with fingerprint v1.0", "normalized 24:00:00 times"]
    )
    
    @model_validator(mode="after")
    def _validate_date_range(self) -> "FingerprintIndex":
        """驗證日期範圍與 day_hashes 的一致性"""
        try:
            start_date = date.fromisoformat(self.range_start)
            end_date = date.fromisoformat(self.range_end)
            
            if start_date > end_date:
                raise ValueError(f"range_start ({self.range_start}) 不能晚於 range_end ({self.range_end})")
            
            # 驗證 day_hashes 中的日期都在範圍內
            for day_str in self.day_hashes.keys():
                try:
                    day_date = date.fromisoformat(day_str)
                    if not (start_date <= day_date <= end_date):
                        raise ValueError(
                            f"day_hashes 中的日期 {day_str} 不在範圍 [{self.range_start}, {self.range_end}] 內"
                        )
                except ValueError as e:
                    raise ValueError(f"無效的日期格式: {day_str}") from e
            
            # 驗證 hash 格式
            for day_str, hash_val in self.day_hashes.items():
                if not isinstance(hash_val, str):
                    raise ValueError(f"day_hashes[{day_str}] 必須是字串")
                if len(hash_val) != 64:  # SHA256 hex 長度
                    raise ValueError(f"day_hashes[{day_str}] 長度必須為 64 (SHA256 hex)，實際長度: {len(hash_val)}")
                # 簡單驗證是否為 hex
                try:
                    int(hash_val, 16)
                except ValueError:
                    raise ValueError(f"day_hashes[{day_str}] 不是有效的 hex 字串")
            
            return self
        except ValueError as e:
            raise ValueError(f"日期驗證失敗: {e}")
    
    @model_validator(mode="after")
    def _validate_index_sha256(self) -> "FingerprintIndex":
        """驗證 index_sha256 是否正確計算"""
        # 計算預期的 hash
        expected_hash = self._compute_index_sha256()
        
        if self.index_sha256 != expected_hash:
            raise ValueError(
                f"index_sha256 驗證失敗: 預期 {expected_hash}，實際 {self.index_sha256}"
            )
        
        return self
    
    def _compute_index_sha256(self) -> str:
        """
        計算索引的 SHA256 hash
        
        排除 index_sha256 欄位本身，使用 canonical_json 確保 deterministic
        """
        # 建立不包含 index_sha256 的字典
        data = self.model_dump(exclude={"index_sha256"})
        
        # 使用 canonical_json 確保排序一致
        json_str = canonical_json(data)
        
        # 計算 SHA256
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    
    @classmethod
    def create(
        cls,
        dataset_id: str,
        range_start: str,
        range_end: str,
        day_hashes: Dict[str, str],
        dataset_timezone: str = "Asia/Taipei",
        build_notes: str = ""
    ) -> "FingerprintIndex":
        """
        建立新的 FingerprintIndex，自動計算 index_sha256
        
        Args:
            dataset_id: 資料集 ID
            range_start: 起始日期 (YYYY-MM-DD)
            range_end: 結束日期 (YYYY-MM-DD)
            day_hashes: 每日 hash 映射
            dataset_timezone: 時區
            build_notes: 建置備註
        
        Returns:
            FingerprintIndex 實例
        """
        # 建立字典（不含 index_sha256）
        data = {
            "dataset_id": dataset_id,
            "dataset_timezone": dataset_timezone,
            "range_start": range_start,
            "range_end": range_end,
            "day_hashes": day_hashes,
            "build_notes": build_notes,
        }
        
        # 直接計算 hash，避免建立暫存實例觸發驗證
        import hashlib
        from contracts.dimensions import canonical_json
        
        json_str = canonical_json(data)
        index_sha256 = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        
        # 建立最終實例
        return cls(**data, index_sha256=index_sha256)
    
    def get_day_hash(self, day_str: str) -> str | None:
        """
        取得指定日期的 hash
        
        Args:
            day_str: 日期字串 (YYYY-MM-DD)
        
        Returns:
            hash 字串或 None（如果不存在）
        """
        return self.day_hashes.get(day_str)
    
    def get_earliest_changed_day(
        self,
        other: "FingerprintIndex"
    ) -> str | None:
        """
        比較兩個索引，找出最早變更的日期
        
        只考慮兩個索引中都存在的日期，且 hash 不同。
        如果一個日期只在一個索引中存在（新增或刪除），不視為「變更」。
        
        Args:
            other: 另一個 FingerprintIndex
        
        Returns:
            最早變更的日期字串，如果完全相同則回傳 None
        """
        if self.dataset_id != other.dataset_id:
            raise ValueError("無法比較不同 dataset_id 的索引")
        
        earliest_changed = None
        
        # 只檢查兩個索引中都存在的日期
        common_days = set(self.day_hashes.keys()) & set(other.day_hashes.keys())
        
        for day_str in sorted(common_days):
            hash1 = self.get_day_hash(day_str)
            hash2 = other.get_day_hash(day_str)
            
            if hash1 != hash2:
                if earliest_changed is None or day_str < earliest_changed:
                    earliest_changed = day_str
        
        return earliest_changed
    
    def is_append_only(self, other: "FingerprintIndex") -> bool:
        """
        檢查是否僅為尾部新增（append-only）
        
        條件：
        1. 所有舊的日期 hash 都相同
        2. 新的索引只新增日期，沒有刪除日期
        
        Args:
            other: 新的 FingerprintIndex
        
        Returns:
            是否為 append-only
        """
        if self.dataset_id != other.dataset_id:
            return False
        
        # 檢查是否有日期被刪除
        for day_str in self.day_hashes:
            if day_str not in other.day_hashes:
                return False
        
        # 檢查舊日期的 hash 是否相同
        for day_str, hash_val in self.day_hashes.items():
            if other.get_day_hash(day_str) != hash_val:
                return False
        
        return True
    
    def get_append_range(self, other: "FingerprintIndex") -> tuple[str, str] | None:
        """
        取得新增的日期範圍（如果為 append-only）
        
        Args:
            other: 新的 FingerprintIndex
        
        Returns:
            (start_date, end_date) 或 None（如果不是 append-only）
        """
        if not self.is_append_only(other):
            return None
        
        # 找出新增的日期
        new_days = set(other.day_hashes.keys()) - set(self.day_hashes.keys())
        
        if not new_days:
            return None
        
        sorted_days = sorted(new_days)
        return sorted_days[0], sorted_days[-1]



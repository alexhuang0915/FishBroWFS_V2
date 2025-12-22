
# src/FishBroWFS_V2/core/feature_bundle.py
"""
FeatureBundle：engine/wfs 的統一輸入

提供 frozen dataclass 結構，確保特徵資料的不可變性與型別安全。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Any
import numpy as np


@dataclass(frozen=True)
class FeatureSeries:
    """
    單一特徵時間序列
    
    Attributes:
        ts: 時間戳記陣列，dtype 必須是 datetime64[s]
        values: 特徵值陣列，dtype 必須是 float64
        name: 特徵名稱
        timeframe_min: timeframe 分鐘數
    """
    ts: np.ndarray  # datetime64[s]
    values: np.ndarray  # float64
    name: str
    timeframe_min: int
    
    def __post_init__(self):
        """驗證資料型別與一致性"""
        # 驗證 ts dtype
        if not np.issubdtype(self.ts.dtype, np.datetime64):
            raise TypeError(f"ts 必須是 datetime64，實際為 {self.ts.dtype}")
        
        # 驗證 values dtype
        if not np.issubdtype(self.values.dtype, np.floating):
            raise TypeError(f"values 必須是浮點數，實際為 {self.values.dtype}")
        
        # 驗證長度一致
        if len(self.ts) != len(self.values):
            raise ValueError(
                f"ts 與 values 長度不一致: ts={len(self.ts)}, values={len(self.values)}"
            )
        
        # 驗證 timeframe 為正整數
        if not isinstance(self.timeframe_min, int) or self.timeframe_min <= 0:
            raise ValueError(f"timeframe_min 必須為正整數: {self.timeframe_min}")
        
        # 驗證名稱非空
        if not self.name:
            raise ValueError("name 不能為空")


@dataclass(frozen=True)
class FeatureBundle:
    """
    特徵資料包
    
    包含一個資料集的所有特徵時間序列，以及相關 metadata。
    
    Attributes:
        dataset_id: 資料集 ID
        season: 季節標記
        series: 特徵序列字典，key 為 (name, timeframe_min)
        meta: metadata 字典，包含 manifest hashes, breaks_policy, ts_dtype 等
    """
    dataset_id: str
    season: str
    series: Dict[Tuple[str, int], FeatureSeries]
    meta: Dict[str, Any]
    
    def __post_init__(self):
        """驗證 bundle 一致性"""
        # 驗證 dataset_id 與 season 非空
        if not self.dataset_id:
            raise ValueError("dataset_id 不能為空")
        if not self.season:
            raise ValueError("season 不能為空")
        
        # 驗證 meta 包含必要欄位
        required_meta_keys = {"ts_dtype", "breaks_policy"}
        missing_keys = required_meta_keys - set(self.meta.keys())
        if missing_keys:
            raise ValueError(f"meta 缺少必要欄位: {missing_keys}")
        
        # 驗證 ts_dtype
        if self.meta["ts_dtype"] != "datetime64[s]":
            raise ValueError(f"ts_dtype 必須為 'datetime64[s]'，實際為 {self.meta['ts_dtype']}")
        
        # 驗證 breaks_policy
        if self.meta["breaks_policy"] != "drop":
            raise ValueError(f"breaks_policy 必須為 'drop'，實際為 {self.meta['breaks_policy']}")
        
        # 驗證所有 series 的 ts dtype 一致
        for (name, tf), series in self.series.items():
            if not np.issubdtype(series.ts.dtype, np.datetime64):
                raise TypeError(
                    f"series ({name}, {tf}) 的 ts dtype 必須為 datetime64，實際為 {series.ts.dtype}"
                )
    
    def get_series(self, name: str, timeframe_min: int) -> FeatureSeries:
        """
        取得特定特徵序列
        
        Args:
            name: 特徵名稱
            timeframe_min: timeframe 分鐘數
        
        Returns:
            FeatureSeries 實例
        
        Raises:
            KeyError: 特徵不存在
        """
        key = (name, timeframe_min)
        if key not in self.series:
            raise KeyError(f"特徵不存在: {name}@{timeframe_min}m")
        return self.series[key]
    
    def has_series(self, name: str, timeframe_min: int) -> bool:
        """
        檢查是否包含特定特徵序列
        
        Args:
            name: 特徵名稱
            timeframe_min: timeframe 分鐘數
        
        Returns:
            bool
        """
        return (name, timeframe_min) in self.series
    
    def list_series(self) -> list[Tuple[str, int]]:
        """
        列出所有特徵序列的 (name, timeframe) 對
        
        Returns:
            排序後的 (name, timeframe) 列表
        """
        return sorted(self.series.keys())
    
    def validate_against_requirements(
        self,
        required: list[Tuple[str, int]],
        optional: list[Tuple[str, int]] = None,
    ) -> bool:
        """
        驗證 bundle 是否滿足需求
        
        Args:
            required: 必需的特徵列表，每個元素為 (name, timeframe)
            optional: 可選的特徵列表（預設為空）
        
        Returns:
            bool: 是否滿足所有必需特徵
        
        Raises:
            ValueError: 參數無效
        """
        if optional is None:
            optional = []
        
        # 檢查必需特徵
        for name, tf in required:
            if not self.has_series(name, tf):
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """
        轉換為字典表示（僅 metadata，不包含大型陣列）
        
        Returns:
            字典包含 bundle 的基本資訊
        """
        return {
            "dataset_id": self.dataset_id,
            "season": self.season,
            "series_count": len(self.series),
            "series_keys": self.list_series(),
            "meta": self.meta,
        }



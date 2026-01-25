from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict

from core.feature_bundle import FeatureBundle


@dataclass(frozen=True)
class FeatureContext:
    """
    B1 FeatureContext (V1: data1 + optional data2 + optional cross).
    """
    timeframe_min: int
    data1: FeatureBundle
    data2: Optional[FeatureBundle] = None
    cross: Optional[FeatureBundle] = None
    data2_id: Optional[str] = None

    def d1(self) -> FeatureBundle:
        return self.data1

    def d2(self) -> Optional[FeatureBundle]:
        return self.data2

    def x(self) -> Optional[FeatureBundle]:
        return self.cross

    def list_d2(self) -> list[str]:
        return [self.data2_id] if self.data2_id else []

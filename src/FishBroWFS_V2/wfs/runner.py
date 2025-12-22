
# src/FishBroWFS_V2/wfs/runner.py
"""
WFS Runner - 接受 FeatureBundle 並執行策略的入口點

Phase 4.1: 新增 run_wfs_with_features API，讓 Research Runner 可以注入特徵。
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from FishBroWFS_V2.core.feature_bundle import FeatureBundle
from FishBroWFS_V2.strategy.runner import run_strategy
from FishBroWFS_V2.strategy.registry import get as get_strategy_spec

logger = logging.getLogger(__name__)


def run_wfs_with_features(
    *,
    strategy_id: str,
    feature_bundle: FeatureBundle,
    config: Optional[dict] = None,
) -> dict:
    """
    WFS entrypoint that consumes FeatureBundle only.

    行為規格：
    1. 不得自行計算特徵（全部來自 feature_bundle）
    2. 不得讀取 TXT / bars / features 檔案
    3. 使用策略的預設參數（或 config 中提供的參數）
    4. 執行策略並產生 intents
    5. 執行引擎模擬（如果需要的話）
    6. 回傳摘要字典（不含大量數據）

    Args:
        strategy_id: 策略 ID
        feature_bundle: 特徵資料包
        config: 配置字典，可包含 params, context 等（可選）

    Returns:
        摘要字典，至少包含：
            - strategy_id
            - dataset_id
            - season
            - intents_count
            - fills_count
            - net_profit (如果可計算)
            - trades
            - max_dd
    """
    if config is None:
        config = {}

    # 1. 從 feature_bundle 建立 features dict
    features = _extract_features_dict(feature_bundle)

    # 2. 取得策略參數（優先使用 config 中的 params，否則使用預設值）
    params = config.get("params", {})
    if not params:
        # 使用策略的預設參數
        spec = get_strategy_spec(strategy_id)
        params = spec.defaults

    # 3. 建立 context（預設值）
    context = config.get("context", {})
    if "bar_index" not in context:
        # 假設從第一個 bar 開始
        context["bar_index"] = 0
    if "order_qty" not in context:
        context["order_qty"] = 1

    # 4. 執行策略，產生 intents
    try:
        intents = run_strategy(
            strategy_id=strategy_id,
            features=features,
            params=params,
            context=context,
        )
    except Exception as e:
        logger.error(f"策略執行失敗: {e}")
        raise RuntimeError(f"策略 {strategy_id} 執行失敗: {e}") from e

    # 5. 執行引擎模擬（簡化版本，僅回傳基本摘要）
    # 注意：這裡我們不實際模擬，因為 Phase 4.1 只要求介面。
    # 我們回傳一個模擬的摘要，後續階段再實作完整的模擬。
    summary = _simulate_intents(intents, feature_bundle, config)

    # 6. 加入 metadata
    summary.update({
        "strategy_id": strategy_id,
        "dataset_id": feature_bundle.dataset_id,
        "season": feature_bundle.season,
        "intents_count": len(intents),
        "features_used": list(features.keys()),
    })

    return summary


def _extract_features_dict(feature_bundle: FeatureBundle) -> Dict[str, Any]:
    """
    從 FeatureBundle 提取特徵字典，格式為 {name: values_array}
    """
    features = {}
    for series in feature_bundle.series.values():
        features[series.name] = series.values
    return features


def _simulate_intents(intents, feature_bundle: FeatureBundle, config: dict) -> dict:
    """
    模擬 intents 並計算基本 metrics（簡化版本）

    目前回傳固定值，後續階段應整合真正的引擎模擬。
    """
    # 如果沒有 intents，回傳零值
    if not intents:
        return {
            "fills_count": 0,
            "net_profit": 0.0,
            "trades": 0,
            "max_dd": 0.0,
            "simulation": "stub",
        }

    # 簡化：假設每個 intent 產生一個 fill，且每個 fill 的 profit 為 0
    # 實際應呼叫 engine.simulate
    fills_count = len(intents) // 2  # 假設每個 entry 對應一個 exit
    net_profit = 0.0
    trades = fills_count
    max_dd = 0.0

    return {
        "fills_count": fills_count,
        "net_profit": net_profit,
        "trades": trades,
        "max_dd": max_dd,
        "simulation": "stub",
    }



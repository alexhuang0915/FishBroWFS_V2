
# src/FishBroWFS_V2/control/research_runner.py
"""
Research Runner - 研究執行的唯一入口

負責載入策略、解析特徵需求、呼叫 Feature Resolver、注入 FeatureBundle 到 WFS、執行研究。
嚴格區分 Research vs Run/Viewer 路徑。

Phase 4.1: 新增 Research Runner + WFS Integration
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from FishBroWFS_V2.contracts.strategy_features import (
    StrategyFeatureRequirements,
    load_requirements_from_json,
)
from FishBroWFS_V2.control.build_context import BuildContext
from FishBroWFS_V2.control.feature_resolver import (
    resolve_features,
    MissingFeaturesError,
    ManifestMismatchError,
    BuildNotAllowedError,
    FeatureResolutionError,
)
from FishBroWFS_V2.core.feature_bundle import FeatureBundle
from FishBroWFS_V2.wfs.runner import run_wfs_with_features
from FishBroWFS_V2.core.slippage_policy import SlippagePolicy
from FishBroWFS_V2.control.research_slippage_stress import (
    compute_stress_matrix,
    survive_s2,
    compute_stress_test_passed,
    generate_stress_report,
    CommissionConfig,
)

logger = logging.getLogger(__name__)


class ResearchRunError(RuntimeError):
    """Research Runner 專用錯誤類別"""
    pass


def _load_strategy_feature_requirements(
    strategy_id: str,
    outputs_root: Path,
) -> StrategyFeatureRequirements:
    """
    載入策略特徵需求

    順序：
    1. 先嘗試 strategy.feature_requirements()（Python）
    2. 再 fallback strategies/{strategy_id}/features.json

    若都沒有 → raise ResearchRunError
    """
    # 1. 嘗試 Python 方法（如果策略有實作）
    try:
        from FishBroWFS_V2.strategy.registry import get
        spec = get(strategy_id)
        if hasattr(spec, "feature_requirements") and callable(spec.feature_requirements):
            req = spec.feature_requirements()
            if isinstance(req, StrategyFeatureRequirements):
                logger.debug(f"策略 {strategy_id} 透過 Python 方法提供特徵需求")
                return req
    except Exception as e:
        logger.debug(f"策略 {strategy_id} 無 Python 特徵需求方法: {e}")

    # 2. 嘗試 JSON 檔案
    json_path = outputs_root / "strategies" / strategy_id / "features.json"
    if not json_path.exists():
        # 也嘗試在 configs/strategies 資料夾
        json_path = Path("configs/strategies") / strategy_id / "features.json"
        if not json_path.exists():
            raise ResearchRunError(
                f"策略 {strategy_id} 無特徵需求定義："
                f"既無 Python 方法，也找不到 JSON 檔案 ({json_path})"
            )

    try:
        req = load_requirements_from_json(str(json_path))
        logger.debug(f"從 {json_path} 載入策略 {strategy_id} 特徵需求")
        return req
    except Exception as e:
        raise ResearchRunError(f"載入策略 {strategy_id} 特徵需求失敗: {e}")


def run_research(
    *,
    season: str,
    dataset_id: str,
    strategy_id: str,
    outputs_root: Path = Path("outputs"),
    allow_build: bool = False,
    build_ctx: Optional[BuildContext] = None,
    wfs_config: Optional[Dict[str, Any]] = None,
    enable_slippage_stress: bool = False,
    slippage_policy: Optional[SlippagePolicy] = None,
    commission_config: Optional[CommissionConfig] = None,
    tick_size_map: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Execute a research run for a single strategy.
    Returns a run report (no raw arrays).

    Args:
        season: 季節標識，例如 "2026Q1"
        dataset_id: 資料集 ID，例如 "CME.MNQ"
        strategy_id: 策略 ID，例如 "S1"
        outputs_root: 輸出根目錄（預設 "outputs"）
        allow_build: 是否允許自動建置缺失的特徵
        build_ctx: BuildContext 實例（若 allow_build=True 則必須提供）
        wfs_config: WFS 配置字典（可選）
        enable_slippage_stress: 是否啟用滑價壓力測試（預設 False）
        slippage_policy: 滑價政策（若 enable_slippage_stress=True 則必須提供）
        commission_config: 手續費配置（若 enable_slippage_stress=True 則必須提供）
        tick_size_map: tick_size 對應表（若 enable_slippage_stress=True 則必須提供）

    Returns:
        run report 字典，包含：
            strategy_id
            dataset_id
            season
            used_features (list)
            features_manifest_sha256
            build_performed (bool)
            wfs_summary（摘要，不含大量數據）
            slippage_stress（若啟用）

    Raises:
        ResearchRunError: 研究執行失敗
    """
    # 1. 載入策略特徵需求
    logger.info(f"開始研究執行: {strategy_id} on {dataset_id} ({season})")
    try:
        req = _load_strategy_feature_requirements(strategy_id, outputs_root)
    except Exception as e:
        raise ResearchRunError(f"載入策略特徵需求失敗: {e}")

    # 2. Resolve Features
    try:
        feature_bundle, build_performed = resolve_features(
            dataset_id=dataset_id,
            season=season,
            requirements=req,
            outputs_root=outputs_root,
            allow_build=allow_build,
            build_ctx=build_ctx,
        )
    except MissingFeaturesError as e:
        if not allow_build:
            # 缺失特徵且不允許建置 → 轉為 exit code 20（在 CLI 層處理）
            raise ResearchRunError(
                f"缺失特徵且不允許建置: {e}"
            ) from e
        # 若 allow_build=True 但 build_ctx=None，則 BuildNotAllowedError 會被拋出
        raise
    except BuildNotAllowedError as e:
        raise ResearchRunError(
            f"允許建置但缺少 BuildContext: {e}"
        ) from e
    except (ManifestMismatchError, FeatureResolutionError) as e:
        raise ResearchRunError(f"特徵解析失敗: {e}") from e

    # 3. 注入 FeatureBundle 到 WFS
    try:
        wfs_result = run_wfs_with_features(
            strategy_id=strategy_id,
            feature_bundle=feature_bundle,
            config=wfs_config,
        )
    except Exception as e:
        raise ResearchRunError(f"WFS 執行失敗: {e}") from e

    # 4. 滑價壓力測試（若啟用）
    slippage_stress_report = None
    if enable_slippage_stress:
        if slippage_policy is None:
            slippage_policy = SlippagePolicy()  # 預設政策
        if commission_config is None:
            # 預設手續費配置（僅示例，實際應從配置檔讀取）
            commission_config = CommissionConfig(
                per_side_usd={"MNQ": 2.8, "MES": 2.8, "MXF": 20.0},
                default_per_side_usd=0.0,
            )
        if tick_size_map is None:
            # 預設 tick_size（僅示例，實際應從 dimension contract 讀取）
            tick_size_map = {"MNQ": 0.25, "MES": 0.25, "MXF": 1.0}
        
        # 從 dataset_id 推導商品符號（簡化：取最後一部分）
        symbol = dataset_id.split(".")[1] if "." in dataset_id else dataset_id
        
        # 檢查 tick_size 是否存在
        if symbol not in tick_size_map:
            raise ResearchRunError(
                f"商品 {symbol} 的 tick_size 未定義於 tick_size_map 中"
            )
        
        # 假設 wfs_result 包含 fills/intents 資料
        # 目前我們沒有實際的 fills 資料，因此跳過計算
        # 這裡僅建立一個框架，實際計算需根據 fills/intents 實作
        logger.warning(
            "滑價壓力測試已啟用，但 fills/intents 資料不可用，跳過計算。"
            "請確保 WFS 結果包含 fills 欄位。"
        )
        # 建立一個空的 stress matrix 報告
        slippage_stress_report = {
            "enabled": True,
            "policy": {
                "definition": slippage_policy.definition,
                "levels": slippage_policy.levels,
                "selection_level": slippage_policy.selection_level,
                "stress_level": slippage_policy.stress_level,
                "mc_execution_level": slippage_policy.mc_execution_level,
            },
            "stress_matrix": {},
            "survive_s2": False,
            "stress_test_passed": False,
            "note": "fills/intents 資料不可用，計算被跳過",
        }

    # 5. 組裝 run report
    used_features = [
        {"name": fs.name, "timeframe_min": fs.timeframe_min}
        for fs in feature_bundle.series.values()
    ]
    report = {
        "strategy_id": strategy_id,
        "dataset_id": dataset_id,
        "season": season,
        "used_features": used_features,
        "features_manifest_sha256": feature_bundle.meta.get("manifest_sha256", ""),
        "build_performed": build_performed,
        "wfs_summary": {
            "status": "completed",
            "metrics_keys": list(wfs_result.keys()) if isinstance(wfs_result, dict) else [],
        },
    }
    # 如果 wfs_result 包含摘要，合併進去
    if isinstance(wfs_result, dict) and "summary" in wfs_result:
        report["wfs_summary"].update(wfs_result["summary"])
    
    # 加入滑價壓力測試報告（若啟用）
    if enable_slippage_stress and slippage_stress_report is not None:
        report["slippage_stress"] = slippage_stress_report

    logger.info(f"研究執行完成: {strategy_id}")
    return report



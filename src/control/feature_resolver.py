
"""
Feature Dependency Resolver（特徵依賴解析器）

讓任何 strategy/wfs 在執行前可以：
1. 讀取 strategy 的 feature 需求（declaration）
2. 檢查 shared features cache 是否存在且合約一致
3. 缺少就觸發 BUILD_SHARED features-only（需遵守治理規則）
4. 返回統一的 FeatureBundle（可直接餵給 engine）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import numpy as np

from contracts.strategy_features import (
    StrategyFeatureRequirements,
    FeatureRef,
)
from core.feature_bundle import FeatureBundle, FeatureSeries
from control.build_context import BuildContext
from control.features_manifest import (
    features_manifest_path,
    load_features_manifest,
)
from control.features_store import (
    features_path,
    load_features_npz,
)
from control.shared_build import build_shared


class FeatureResolutionError(RuntimeError):
    """特徵解析錯誤的基底類別"""
    pass


class MissingFeaturesError(FeatureResolutionError):
    """缺少特徵錯誤"""
    def __init__(self, missing: List[Tuple[str, int]]):
        self.missing = missing
        missing_str = ", ".join(f"{name}@{tf}m" for name, tf in missing)
        super().__init__(f"缺少特徵: {missing_str}")


class ManifestMismatchError(FeatureResolutionError):
    """Manifest 合約不符錯誤"""
    pass


class BuildNotAllowedError(FeatureResolutionError):
    """不允許 build 錯誤"""
    pass


def resolve_features(
    *,
    season: str,
    dataset_id: str,
    requirements: StrategyFeatureRequirements,
    outputs_root: Path = Path("outputs"),
    allow_build: bool = False,
    build_ctx: Optional[BuildContext] = None,
) -> Tuple[FeatureBundle, bool]:
    """
    Ensure required features exist in shared cache and load them.
    
    行為規格（必須精準）：
    1. 找到 features 目錄：outputs/shared/{season}/{dataset_id}/features/
    2. 檢查 features_manifest.json 是否存在
        - 不存在 → missing
    3. 載入 manifest，驗證硬合約：
        - ts_dtype == "datetime64[s]"
        - breaks_policy == "drop"
    4. 檢查 manifest 是否包含所需 features_{tf}m.npz 檔
    5. 打開 npz，檢查 keys：
        - ts, 以及需求的 feature key
        - ts 對齊檢查（同 tf 同檔）：ts 必須與檔內所有 feature array 同長
    6. 組裝 FeatureBundle 回傳
    
    若任何缺失：
        - allow_build=False → raise MissingFeaturesError
        - allow_build=True → 需要 build_ctx 存在，否則 raise BuildNotAllowedError
        - 呼叫 build_shared() 進行 build
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        requirements: 策略特徵需求
        outputs_root: 輸出根目錄（預設為專案根目錄下的 outputs/）
        allow_build: 是否允許自動 build
        build_ctx: Build 上下文（僅在 allow_build=True 且需要 build 時使用）
    
    Returns:
        Tuple[FeatureBundle, bool]：特徵資料包與是否執行了 build 的標記
    
    Raises:
        MissingFeaturesError: 缺少特徵且不允許 build
        ManifestMismatchError: manifest 合約不符
        BuildNotAllowedError: 允許 build 但缺少 build_ctx
        ValueError: 參數無效
        FileNotFoundError: 檔案不存在且不允許 build
    """
    # 參數驗證
    if not season:
        raise ValueError("season 不能為空")
    if not dataset_id:
        raise ValueError("dataset_id 不能為空")
    
    if not isinstance(outputs_root, Path):
        outputs_root = Path(outputs_root)
    
    # 1. 檢查 features manifest 是否存在
    manifest_path = features_manifest_path(outputs_root, season, dataset_id)
    
    if not manifest_path.exists():
        # features cache 完全不存在
        missing_all = [(ref.name, ref.timeframe_min) for ref in requirements.required]
        return _handle_missing_features(
            season=season,
            dataset_id=dataset_id,
            missing=missing_all,
            allow_build=allow_build,
            build_ctx=build_ctx,
            outputs_root=outputs_root,
            requirements=requirements,
        )
    
    # 2. 載入並驗證 manifest
    try:
        manifest = load_features_manifest(manifest_path)
    except Exception as e:
        raise ManifestMismatchError(f"無法載入 features manifest: {e}")
    
    # 3. 驗證硬合約
    _validate_manifest_contracts(manifest)
    
    # 4. 檢查所需特徵是否存在
    missing = _check_missing_features(manifest, requirements)
    
    if missing:
        # 有特徵缺失
        return _handle_missing_features(
            season=season,
            dataset_id=dataset_id,
            missing=missing,
            allow_build=allow_build,
            build_ctx=build_ctx,
            outputs_root=outputs_root,
            requirements=requirements,
        )
    
    # 5. 載入所有特徵並建立 FeatureBundle
    return _load_feature_bundle(
        season=season,
        dataset_id=dataset_id,
        requirements=requirements,
        manifest=manifest,
        outputs_root=outputs_root,
    )


def _validate_manifest_contracts(manifest: Dict[str, Any]) -> None:
    """
    驗證 manifest 硬合約
    
    Raises:
        ManifestMismatchError: 合約不符
    """
    # 檢查 ts_dtype
    ts_dtype = manifest.get("ts_dtype")
    if ts_dtype != "datetime64[s]":
        raise ManifestMismatchError(
            f"ts_dtype 必須為 'datetime64[s]'，實際為 {ts_dtype}"
        )
    
    # 檢查 breaks_policy
    breaks_policy = manifest.get("breaks_policy")
    if breaks_policy != "drop":
        raise ManifestMismatchError(
            f"breaks_policy 必須為 'drop'，實際為 {breaks_policy}"
        )
    
    # 檢查 files 欄位存在
    if "files" not in manifest:
        raise ManifestMismatchError("manifest 缺少 'files' 欄位")
    
    # 檢查 features_specs 欄位存在
    if "features_specs" not in manifest:
        raise ManifestMismatchError("manifest 缺少 'features_specs' 欄位")


def _check_missing_features(
    manifest: Dict[str, Any],
    requirements: StrategyFeatureRequirements,
) -> List[Tuple[str, int]]:
    """
    檢查 manifest 中缺少哪些特徵
    
    Args:
        manifest: features manifest 字典
        requirements: 策略特徵需求
    
    Returns:
        缺少的特徵列表，每個元素為 (name, timeframe)
    """
    missing = []
    
    # 從 manifest 取得可用的特徵規格
    available_specs = manifest.get("features_specs", [])
    available_keys = set()
    
    for spec in available_specs:
        name = spec.get("name")
        timeframe_min = spec.get("timeframe_min")
        if name and timeframe_min:
            available_keys.add((name, timeframe_min))
    
    # 檢查必需特徵
    for ref in requirements.required:
        key = (ref.name, ref.timeframe_min)
        if key not in available_keys:
            missing.append(key)
    
    return missing


def _handle_missing_features(
    *,
    season: str,
    dataset_id: str,
    missing: List[Tuple[str, int]],
    allow_build: bool,
    build_ctx: Optional[BuildContext],
    outputs_root: Path,
    requirements: StrategyFeatureRequirements,
) -> Tuple[FeatureBundle, bool]:
    """
    處理缺失特徵
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        missing: 缺失的特徵列表
        allow_build: 是否允許自動 build
        build_ctx: Build 上下文
        outputs_root: 輸出根目錄
        requirements: 策略特徵需求
    
    Returns:
        Tuple[FeatureBundle, bool]：特徵資料包與是否執行了 build 的標記
    
    Raises:
        MissingFeaturesError: 不允許 build
        BuildNotAllowedError: 允許 build 但缺少 build_ctx
    """
    if not allow_build:
        raise MissingFeaturesError(missing)
    
    if build_ctx is None:
        raise BuildNotAllowedError(
            "允許 build 但缺少 build_ctx（需要 txt_path 等參數）"
        )
    
    # 執行 build
    try:
        # 使用 build_shared 進行 build
        # 注意：這裡我們使用 build_ctx 中的參數，但覆蓋 season 和 dataset_id
        build_kwargs = build_ctx.to_build_shared_kwargs()
        build_kwargs.update({
            "season": season,
            "dataset_id": dataset_id,
            "build_bars": build_ctx.build_bars_if_missing,
            "build_features": True,
        })
        
        report = build_shared(**build_kwargs)
        
        if not report.get("success"):
            raise FeatureResolutionError(f"build 失敗: {report}")
        
        # build 成功後，重新嘗試解析
        # 遞迴呼叫 resolve_features（但這次不允許 build，避免無限遞迴）
        bundle, _ = resolve_features(
            season=season,
            dataset_id=dataset_id,
            requirements=requirements,
            outputs_root=outputs_root,
            allow_build=False,  # 不允許再次 build
            build_ctx=None,  # 不需要 build_ctx
        )
        # 因為我們執行了 build，所以標記為 True
        return bundle, True
        
    except Exception as e:
        # 將其他錯誤包裝為 FeatureResolutionError
        raise FeatureResolutionError(f"build 失敗: {e}")


def _load_feature_bundle(
    *,
    season: str,
    dataset_id: str,
    requirements: StrategyFeatureRequirements,
    manifest: Dict[str, Any],
    outputs_root: Path,
) -> Tuple[FeatureBundle, bool]:
    """
    載入特徵並建立 FeatureBundle
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        requirements: 策略特徵需求
        manifest: features manifest 字典
        outputs_root: 輸出根目錄
    
    Returns:
        Tuple[FeatureBundle, bool]：特徵資料包與是否執行了 build 的標記（此處永遠為 False）
    
    Raises:
        FeatureResolutionError: 載入失敗
    """
    series_dict = {}
    
    # 載入必需特徵
    for ref in requirements.required:
        key = (ref.name, ref.timeframe_min)
        
        try:
            series = _load_single_feature_series(
                season=season,
                dataset_id=dataset_id,
                feature_name=ref.name,
                timeframe_min=ref.timeframe_min,
                outputs_root=outputs_root,
                manifest=manifest,
            )
            series_dict[key] = series
        except Exception as e:
            raise FeatureResolutionError(
                f"無法載入特徵 {ref.name}@{ref.timeframe_min}m: {e}"
            )
    
    # 載入可選特徵（如果存在）
    for ref in requirements.optional:
        key = (ref.name, ref.timeframe_min)
        
        # 檢查特徵是否存在於 manifest
        if _feature_exists_in_manifest(ref.name, ref.timeframe_min, manifest):
            try:
                series = _load_single_feature_series(
                    season=season,
                    dataset_id=dataset_id,
                    feature_name=ref.name,
                    timeframe_min=ref.timeframe_min,
                    outputs_root=outputs_root,
                    manifest=manifest,
                )
                series_dict[key] = series
            except Exception:
                # 可選特徵載入失敗，忽略（不加入 bundle）
                pass
    
    # 建立 metadata
    meta = {
        "ts_dtype": manifest.get("ts_dtype", "datetime64[s]"),
        "breaks_policy": manifest.get("breaks_policy", "drop"),
        "manifest_sha256": manifest.get("manifest_sha256"),
        "mode": manifest.get("mode"),
        "season": season,
        "dataset_id": dataset_id,
        "files_sha256": manifest.get("files", {}),
    }
    
    # 建立 FeatureBundle
    try:
        bundle = FeatureBundle(
            dataset_id=dataset_id,
            season=season,
            series=series_dict,
            meta=meta,
        )
        return bundle, False
    except Exception as e:
        raise FeatureResolutionError(f"無法建立 FeatureBundle: {e}")


def _feature_exists_in_manifest(
    feature_name: str,
    timeframe_min: int,
    manifest: Dict[str, Any],
) -> bool:
    """
    檢查特徵是否存在於 manifest 中
    
    Args:
        feature_name: 特徵名稱
        timeframe_min: timeframe 分鐘數
        manifest: features manifest 字典
    
    Returns:
        bool
    """
    specs = manifest.get("features_specs", [])
    for spec in specs:
        if (spec.get("name") == feature_name and 
            spec.get("timeframe_min") == timeframe_min):
            return True
    return False


def _load_single_feature_series(
    *,
    season: str,
    dataset_id: str,
    feature_name: str,
    timeframe_min: int,
    outputs_root: Path,
    manifest: Dict[str, Any],
) -> FeatureSeries:
    """
    載入單一特徵序列
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        feature_name: 特徵名稱
        timeframe_min: timeframe 分鐘數
        outputs_root: 輸出根目錄
        manifest: features manifest 字典（用於驗證）
    
    Returns:
        FeatureSeries 實例
    
    Raises:
        FeatureResolutionError: 載入失敗
    """
    # 1. 載入 features NPZ 檔案
    feat_path = features_path(outputs_root, season, dataset_id, timeframe_min)
    
    if not feat_path.exists():
        raise FeatureResolutionError(
            f"features 檔案不存在: {feat_path}"
        )
    
    try:
        data = load_features_npz(feat_path)
    except Exception as e:
        raise FeatureResolutionError(f"無法載入 features NPZ: {e}")
    
    # 2. 檢查必要 keys
    required_keys = {"ts", feature_name}
    missing_keys = required_keys - set(data.keys())
    if missing_keys:
        raise FeatureResolutionError(
            f"features NPZ 缺少必要 keys: {missing_keys}，現有 keys: {list(data.keys())}"
        )
    
    # 3. 驗證 ts dtype
    ts = data["ts"]
    if not np.issubdtype(ts.dtype, np.datetime64):
        raise FeatureResolutionError(
            f"ts dtype 必須為 datetime64，實際為 {ts.dtype}"
        )
    
    # 4. 驗證特徵值 dtype
    values = data[feature_name]
    if not np.issubdtype(values.dtype, np.floating):
        # 嘗試轉換為 float64
        try:
            values = values.astype(np.float64)
        except Exception as e:
            raise FeatureResolutionError(
                f"特徵值無法轉換為浮點數: {e}，dtype: {values.dtype}"
            )
    
    # 5. 驗證長度一致
    if len(ts) != len(values):
        raise FeatureResolutionError(
            f"ts 與特徵值長度不一致: ts={len(ts)}, {feature_name}={len(values)}"
        )
    
    # 6. 建立 FeatureSeries
    try:
        return FeatureSeries(
            ts=ts,
            values=values,
            name=feature_name,
            timeframe_min=timeframe_min,
        )
    except Exception as e:
        raise FeatureResolutionError(f"無法建立 FeatureSeries: {e}")


# Cache invalidation functions for reload service
def invalidate_feature_cache() -> bool:
    """Invalidate feature resolver cache.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Currently there's no persistent cache in this module
        # This function exists for API compatibility
        return True
    except Exception:
        return False


def reload_feature_registry() -> bool:
    """Reload feature registry.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Currently there's no registry to reload
        # This function exists for API compatibility
        return True
    except Exception:
        return False



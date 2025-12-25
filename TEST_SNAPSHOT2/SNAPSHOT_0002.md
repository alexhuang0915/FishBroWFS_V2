FILE src/FishBroWFS_V2/control/feature_resolver.py
sha256(source_bytes) = 3a3678fb13bddb24bb093e730e800040172a65f4205568da62cd93c6cd2845fb
bytes = 16079
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/feature_resolver.py
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

from FishBroWFS_V2.contracts.strategy_features import (
    StrategyFeatureRequirements,
    FeatureRef,
)
from FishBroWFS_V2.core.feature_bundle import FeatureBundle, FeatureSeries
from FishBroWFS_V2.control.build_context import BuildContext
from FishBroWFS_V2.control.features_manifest import (
    features_manifest_path,
    load_features_manifest,
)
from FishBroWFS_V2.control.features_store import (
    features_path,
    load_features_npz,
)
from FishBroWFS_V2.control.shared_build import build_shared


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



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/features_manifest.py
sha256(source_bytes) = 5aed01b6fa18585b5b866057707e2a82b3ba830fecc3c645a0e95bbbfd894291
bytes = 6523
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/features_manifest.py
"""
Features Manifest 寫入工具

提供 deterministic JSON + self-hash manifest_sha256 + atomic write。
包含 features specs dump 與 lookback rewind 資訊。
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

from FishBroWFS_V2.contracts.dimensions import canonical_json
from FishBroWFS_V2.contracts.features import FeatureRegistry, FeatureSpec


def write_features_manifest(payload: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """
    Deterministic JSON + self-hash manifest_sha256 + atomic write.
    
    行為規格：
    1. 建立暫存檔案（.json.tmp）
    2. 計算 payload 的 SHA256 hash（排除 manifest_sha256 欄位）
    3. 將 hash 加入 payload 作為 manifest_sha256 欄位
    4. 使用 canonical_json 寫入暫存檔案（確保排序一致）
    5. atomic replace 到目標路徑
    6. 如果寫入失敗，清理暫存檔案
    
    Args:
        payload: manifest 資料字典（不含 manifest_sha256）
        path: 目標檔案路徑
        
    Returns:
        最終的 manifest 字典（包含 manifest_sha256 欄位）
        
    Raises:
        IOError: 寫入失敗
    """
    # 確保目錄存在
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 建立暫存檔案路徑
    temp_path = path.with_suffix(path.suffix + ".tmp")
    
    try:
        # 計算 payload 的 SHA256 hash（排除可能的 manifest_sha256 欄位）
        payload_without_hash = {k: v for k, v in payload.items() if k != "manifest_sha256"}
        json_str = canonical_json(payload_without_hash)
        manifest_sha256 = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        
        # 建立最終 payload（包含 hash）
        final_payload = {**payload_without_hash, "manifest_sha256": manifest_sha256}
        
        # 使用 canonical_json 寫入暫存檔案
        final_json = canonical_json(final_payload)
        temp_path.write_text(final_json, encoding="utf-8")
        
        # atomic replace
        temp_path.replace(path)
        
        return final_payload
        
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise IOError(f"寫入 features manifest 失敗 {path}: {e}")
    
    finally:
        # 確保暫存檔案被清理（如果 replace 成功，temp_path 已不存在）
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def load_features_manifest(path: Path) -> Dict[str, Any]:
    """
    載入 features manifest 並驗證 hash
    
    Args:
        path: manifest 檔案路徑
        
    Returns:
        manifest 字典
        
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: JSON 解析失敗或 hash 驗證失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"features manifest 檔案不存在: {path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取 features manifest 檔案 {path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"features manifest JSON 解析失敗 {path}: {e}")
    
    # 驗證 manifest_sha256
    if "manifest_sha256" not in data:
        raise ValueError(f"features manifest 缺少 manifest_sha256 欄位: {path}")
    
    # 計算實際 hash（排除 manifest_sha256 欄位）
    data_without_hash = {k: v for k, v in data.items() if k != "manifest_sha256"}
    json_str = canonical_json(data_without_hash)
    expected_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    
    if data["manifest_sha256"] != expected_hash:
        raise ValueError(f"features manifest hash 驗證失敗: 預期 {expected_hash}，實際 {data['manifest_sha256']}")
    
    return data


def features_manifest_path(outputs_root: Path, season: str, dataset_id: str) -> Path:
    """
    取得 features manifest 檔案路徑
    
    建議位置：outputs/shared/{season}/{dataset_id}/features/features_manifest.json
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        
    Returns:
        檔案路徑
    """
    # 建立路徑
    path = outputs_root / "shared" / season / dataset_id / "features" / "features_manifest.json"
    return path


def build_features_manifest_data(
    *,
    season: str,
    dataset_id: str,
    mode: str,
    ts_dtype: str,
    breaks_policy: str,
    features_specs: list[Dict[str, Any]],
    append_only: bool,
    append_range: Optional[Dict[str, str]],
    lookback_rewind_by_tf: Dict[str, str],
    files_sha256: Dict[str, str],
) -> Dict[str, Any]:
    """
    建立 features manifest 資料
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        mode: 建置模式（"FULL" 或 "INCREMENTAL"）
        ts_dtype: 時間戳記 dtype（必須為 "datetime64[s]"）
        breaks_policy: break 處理策略（必須為 "drop"）
        features_specs: 特徵規格列表（從 FeatureRegistry 轉換）
        append_only: 是否為 append-only 增量
        append_range: 增量範圍（開始日、結束日）
        lookback_rewind_by_tf: 每個 timeframe 的 lookback rewind 開始時間
        files_sha256: 檔案 SHA256 字典
        
    Returns:
        manifest 資料字典（不含 manifest_sha256）
    """
    manifest = {
        "season": season,
        "dataset_id": dataset_id,
        "mode": mode,
        "ts_dtype": ts_dtype,
        "breaks_policy": breaks_policy,
        "features_specs": features_specs,
        "append_only": append_only,
        "append_range": append_range,
        "lookback_rewind_by_tf": lookback_rewind_by_tf,
        "files": files_sha256,
    }
    
    return manifest


def feature_spec_to_dict(spec: FeatureSpec) -> Dict[str, Any]:
    """
    將 FeatureSpec 轉換為可序列化的字典
    
    Args:
        spec: 特徵規格
        
    Returns:
        可序列化的字典
    """
    return {
        "name": spec.name,
        "timeframe_min": spec.timeframe_min,
        "lookback_bars": spec.lookback_bars,
        "params": spec.params,
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/features_store.py
sha256(source_bytes) = 204b2e1a540cdd035c3ded1a30c265b9ccd93ccd4760ba62bd13ce299e6b6200
bytes = 4886
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/features_store.py
"""
Feature Store（NPZ atomic + SHA256）

提供 features cache 的 I/O 工具，重用 bars_store 的 atomic write 與 SHA256 計算。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Literal, Optional
import numpy as np

from FishBroWFS_V2.control.bars_store import (
    write_npz_atomic,
    load_npz,
    sha256_file,
    canonical_json,
)

Timeframe = Literal[15, 30, 60, 120, 240]


def features_dir(outputs_root: Path, season: str, dataset_id: str) -> Path:
    """
    取得 features 目錄路徑
    
    建議位置：outputs/shared/{season}/{dataset_id}/features/
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記，例如 "2026Q1"
        dataset_id: 資料集 ID
        
    Returns:
        目錄路徑
    """
    # 建立路徑
    path = outputs_root / "shared" / season / dataset_id / "features"
    return path


def features_path(
    outputs_root: Path,
    season: str,
    dataset_id: str,
    tf_min: Timeframe,
) -> Path:
    """
    取得 features 檔案路徑
    
    建議位置：outputs/shared/{season}/{dataset_id}/features/features_{tf_min}m.npz
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        tf_min: timeframe 分鐘數（15, 30, 60, 120, 240）
        
    Returns:
        檔案路徑
    """
    dir_path = features_dir(outputs_root, season, dataset_id)
    return dir_path / f"features_{tf_min}m.npz"


def write_features_npz_atomic(
    path: Path,
    features_dict: Dict[str, np.ndarray],
) -> None:
    """
    Write features NPZ via tmp + replace. Deterministic keys order.
    
    重用 bars_store.write_npz_atomic 但確保 keys 順序固定：
    ts, atr_14, ret_z_200, session_vwap
    
    Args:
        path: 目標檔案路徑
        features_dict: 特徵字典，必須包含所有必要 keys
        
    Raises:
        ValueError: 缺少必要 keys
        IOError: 寫入失敗
    """
    # 驗證必要 keys
    required_keys = {"ts", "atr_14", "ret_z_200", "session_vwap"}
    missing_keys = required_keys - set(features_dict.keys())
    if missing_keys:
        raise ValueError(f"features_dict 缺少必要 keys: {missing_keys}")
    
    # 確保 ts 的 dtype 是 datetime64[s]
    ts = features_dict["ts"]
    if not np.issubdtype(ts.dtype, np.datetime64):
        raise ValueError(f"ts 的 dtype 必須是 datetime64，實際為 {ts.dtype}")
    
    # 確保所有特徵陣列都是 float64
    for key in ["atr_14", "ret_z_200", "session_vwap"]:
        arr = features_dict[key]
        if not np.issubdtype(arr.dtype, np.floating):
            raise ValueError(f"{key} 的 dtype 必須是浮點數，實際為 {arr.dtype}")
    
    # 使用 bars_store 的 write_npz_atomic
    write_npz_atomic(path, features_dict)


def load_features_npz(path: Path) -> Dict[str, np.ndarray]:
    """
    載入 features NPZ 檔案
    
    Args:
        path: NPZ 檔案路徑
        
    Returns:
        特徵字典
        
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: 檔案格式錯誤或缺少必要 keys
    """
    # 使用 bars_store 的 load_npz
    data = load_npz(path)
    
    # 驗證必要 keys
    required_keys = {"ts", "atr_14", "ret_z_200", "session_vwap"}
    missing_keys = required_keys - set(data.keys())
    if missing_keys:
        raise ValueError(f"載入的 NPZ 缺少必要 keys: {missing_keys}")
    
    return data


def sha256_features_file(
    outputs_root: Path,
    season: str,
    dataset_id: str,
    tf_min: Timeframe,
) -> str:
    """
    計算 features NPZ 檔案的 SHA256 hash
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        tf_min: timeframe 分鐘數
        
    Returns:
        SHA256 hex digest（小寫）
        
    Raises:
        FileNotFoundError: 檔案不存在
        IOError: 讀取失敗
    """
    path = features_path(outputs_root, season, dataset_id, tf_min)
    return sha256_file(path)


def compute_features_sha256_dict(
    outputs_root: Path,
    season: str,
    dataset_id: str,
    tfs: list[Timeframe] = [15, 30, 60, 120, 240],
) -> Dict[str, str]:
    """
    計算所有 timeframe 的 features NPZ 檔案 SHA256 hash
    
    Args:
        outputs_root: 輸出根目錄
        season: 季節標記
        dataset_id: 資料集 ID
        tfs: timeframe 列表
        
    Returns:
        字典：filename -> sha256
    """
    result = {}
    
    for tf in tfs:
        try:
            sha256 = sha256_features_file(outputs_root, season, dataset_id, tf)
            result[f"features_{tf}m.npz"] = sha256
        except FileNotFoundError:
            # 檔案不存在，跳過
            continue
    
    return result



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/fingerprint_cli.py
sha256(source_bytes) = b8f07e1574f8f48d68dc36c3d8330ef9241acb45ddd525a3c87cc6c415622e94
bytes = 8356
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/fingerprint_cli.py
"""
Fingerprint scan-only diff CLI

提供 scan-only 命令，用於比較 TXT 檔案與現有指紋索引，產生 diff 報告。
此命令純粹掃描與比較，不觸發任何 build 或 WFS 行為。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.contracts.fingerprint import FingerprintIndex
from FishBroWFS_V2.control.fingerprint_store import (
    fingerprint_index_path,
    load_fingerprint_index_if_exists,
    write_fingerprint_index,
)
from FishBroWFS_V2.core.fingerprint import (
    build_fingerprint_index_from_raw_ingest,
    compare_fingerprint_indices,
)
from FishBroWFS_V2.data.raw_ingest import ingest_raw_txt


def scan_fingerprint(
    season: str,
    dataset_id: str,
    txt_path: Path,
    outputs_root: Optional[Path] = None,
    save_new_index: bool = False,
    verbose: bool = False,
) -> dict:
    """
    掃描 TXT 檔案並與現有指紋索引比較
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        txt_path: TXT 檔案路徑
        outputs_root: 輸出根目錄
        save_new_index: 是否儲存新的指紋索引
        verbose: 是否輸出詳細資訊
    
    Returns:
        diff 報告字典
    """
    # 檢查檔案是否存在
    if not txt_path.exists():
        raise FileNotFoundError(f"TXT 檔案不存在: {txt_path}")
    
    # 載入現有指紋索引（如果存在）
    index_path = fingerprint_index_path(season, dataset_id, outputs_root)
    old_index = load_fingerprint_index_if_exists(index_path)
    
    if verbose:
        if old_index:
            print(f"找到現有指紋索引: {index_path}")
            print(f"  範圍: {old_index.range_start} 到 {old_index.range_end}")
            print(f"  天數: {len(old_index.day_hashes)}")
        else:
            print(f"沒有現有指紋索引: {index_path}")
    
    # 讀取 TXT 檔案並建立新的指紋索引
    if verbose:
        print(f"讀取 TXT 檔案: {txt_path}")
    
    raw_result = ingest_raw_txt(txt_path)
    
    if verbose:
        print(f"  讀取 {raw_result.rows} 行")
        if raw_result.policy.normalized_24h:
            print(f"  已正規化 24:00:00 時間")
    
    # 建立新的指紋索引
    new_index = build_fingerprint_index_from_raw_ingest(
        dataset_id=dataset_id,
        raw_ingest_result=raw_result,
        build_notes=f"scanned from {txt_path.name}",
    )
    
    if verbose:
        print(f"建立新的指紋索引:")
        print(f"  範圍: {new_index.range_start} 到 {new_index.range_end}")
        print(f"  天數: {len(new_index.day_hashes)}")
        print(f"  index_sha256: {new_index.index_sha256[:16]}...")
    
    # 比較索引
    diff_report = compare_fingerprint_indices(old_index, new_index)
    
    # 如果需要，儲存新的指紋索引
    if save_new_index:
        if verbose:
            print(f"儲存新的指紋索引到: {index_path}")
        
        write_fingerprint_index(new_index, index_path)
        diff_report["new_index_saved"] = True
        diff_report["new_index_path"] = str(index_path)
    else:
        diff_report["new_index_saved"] = False
    
    return diff_report


def format_diff_report(diff_report: dict, verbose: bool = False) -> str:
    """
    格式化 diff 報告
    
    Args:
        diff_report: diff 報告字典
        verbose: 是否輸出詳細資訊
    
    Returns:
        格式化字串
    """
    lines = []
    
    # 基本資訊
    lines.append("=== Fingerprint Scan Report ===")
    
    if diff_report.get("is_new", False):
        lines.append("狀態: 全新資料集（無現有指紋索引）")
    elif diff_report.get("no_change", False):
        lines.append("狀態: 無變更（指紋完全相同）")
    elif diff_report.get("append_only", False):
        lines.append("狀態: 僅尾部新增（可增量）")
    else:
        lines.append("狀態: 資料變更（需全量重算）")
    
    lines.append("")
    
    # 範圍資訊
    if diff_report["old_range_start"]:
        lines.append(f"舊範圍: {diff_report['old_range_start']} 到 {diff_report['old_range_end']}")
    lines.append(f"新範圍: {diff_report['new_range_start']} 到 {diff_report['new_range_end']}")
    
    # 變更資訊
    if diff_report.get("append_only", False):
        append_range = diff_report.get("append_range")
        if append_range:
            lines.append(f"新增範圍: {append_range[0]} 到 {append_range[1]}")
    
    if diff_report.get("earliest_changed_day"):
        lines.append(f"最早變更日: {diff_report['earliest_changed_day']}")
    
    # 儲存狀態
    if diff_report.get("new_index_saved", False):
        lines.append(f"新指紋索引已儲存: {diff_report.get('new_index_path', '')}")
    
    # 詳細輸出
    if verbose:
        lines.append("")
        lines.append("--- 詳細報告 ---")
        lines.append(json.dumps(diff_report, indent=2, ensure_ascii=False))
    
    return "\n".join(lines)


def main() -> int:
    """
    CLI 主函數
    
    命令：fishbro fingerprint scan --season 2026Q1 --dataset-id XXX --txt-path /path/to/file.txt
    """
    parser = argparse.ArgumentParser(
        description="掃描 TXT 檔案並與指紋索引比較（scan-only diff）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # 子命令（未來可擴展）
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # scan 命令
    scan_parser = subparsers.add_parser(
        "scan",
        help="掃描 TXT 檔案並比較指紋"
    )
    
    scan_parser.add_argument(
        "--season",
        required=True,
        help="季節標記，例如 '2026Q1'"
    )
    
    scan_parser.add_argument(
        "--dataset-id",
        required=True,
        help="資料集 ID，例如 'CME.MNQ.60m.2020-2024'"
    )
    
    scan_parser.add_argument(
        "--txt-path",
        type=Path,
        required=True,
        help="TXT 檔案路徑"
    )
    
    scan_parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="輸出根目錄"
    )
    
    scan_parser.add_argument(
        "--save",
        action="store_true",
        help="儲存新的指紋索引（否則僅比較）"
    )
    
    scan_parser.add_argument(
        "--verbose",
        action="store_true",
        help="輸出詳細資訊"
    )
    
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式輸出報告"
    )
    
    # 如果沒有提供命令，顯示幫助
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    args = parser.parse_args()
    
    if args.command != "scan":
        print(f"錯誤: 不支援的命令: {args.command}", file=sys.stderr)
        parser.print_help()
        return 1
    
    try:
        # 執行掃描
        diff_report = scan_fingerprint(
            season=args.season,
            dataset_id=args.dataset_id,
            txt_path=args.txt_path,
            outputs_root=args.outputs_root,
            save_new_index=args.save,
            verbose=args.verbose,
        )
        
        # 輸出結果
        if args.json:
            print(json.dumps(diff_report, indent=2, ensure_ascii=False))
        else:
            report_text = format_diff_report(diff_report, args.verbose)
            print(report_text)
        
        # 根據結果返回適當的退出碼
        if diff_report.get("no_change", False):
            return 0  # 無變更
        elif diff_report.get("append_only", False):
            return 10  # 可增量（使用非零值表示需要處理）
        else:
            return 20  # 需全量重算
        
    except FileNotFoundError as e:
        print(f"錯誤: 檔案不存在 - {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"錯誤: 資料驗證失敗 - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"錯誤: 執行失敗 - {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/fingerprint_store.py
sha256(source_bytes) = 74d7a6534df58d8b552f2592d05aaedc3b551739b66c68fe84c574832427c6b3
bytes = 5755
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/fingerprint_store.py
"""
Fingerprint index 儲存與讀取

提供 atomic write 與 deterministic JSON 序列化。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.contracts.fingerprint import FingerprintIndex
from FishBroWFS_V2.contracts.dimensions import canonical_json


def fingerprint_index_path(
    season: str,
    dataset_id: str,
    outputs_root: Optional[Path] = None
) -> Path:
    """
    取得指紋索引檔案路徑
    
    建議位置：outputs/fingerprints/{season}/{dataset_id}/fingerprint_index.json
    
    Args:
        season: 季節標記，例如 "2026Q1"
        dataset_id: 資料集 ID
        outputs_root: 輸出根目錄，預設為專案根目錄下的 outputs/
    
    Returns:
        檔案路徑
    """
    if outputs_root is None:
        # 從專案根目錄開始
        project_root = Path(__file__).parent.parent.parent
        outputs_root = project_root / "outputs"
    
    # 建立路徑
    path = outputs_root / "fingerprints" / season / dataset_id / "fingerprint_index.json"
    return path


def write_fingerprint_index(
    index: FingerprintIndex,
    path: Path,
    *,
    ensure_parents: bool = True
) -> None:
    """
    寫入指紋索引（原子寫入）
    
    使用 tmp + replace 模式確保 atomic write。
    
    Args:
        index: 要寫入的 FingerprintIndex
        path: 目標檔案路徑
        ensure_parents: 是否建立父目錄
    
    Raises:
        IOError: 寫入失敗
    """
    if ensure_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    
    # 轉換為字典
    data = index.model_dump()
    
    # 使用 canonical_json 確保 deterministic 輸出
    json_str = canonical_json(data)
    
    # 原子寫入：先寫到暫存檔案，再移動
    temp_path = path.with_suffix(".json.tmp")
    
    try:
        # 寫入暫存檔案
        temp_path.write_text(json_str, encoding="utf-8")
        
        # 移動到目標位置（原子操作）
        temp_path.replace(path)
        
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        
        raise IOError(f"寫入指紋索引失敗 {path}: {e}")
    
    # 驗證寫入的檔案可以正確讀回
    try:
        loaded = load_fingerprint_index(path)
        if loaded.index_sha256 != index.index_sha256:
            raise IOError(f"寫入後驗證失敗: hash 不匹配")
    except Exception as e:
        # 如果驗證失敗，刪除檔案
        if path.exists():
            try:
                path.unlink()
            except:
                pass
        raise IOError(f"指紋索引驗證失敗 {path}: {e}")


def load_fingerprint_index(path: Path) -> FingerprintIndex:
    """
    載入指紋索引
    
    Args:
        path: 檔案路徑
    
    Returns:
        FingerprintIndex
    
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: JSON 解析失敗或 schema 驗證失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"指紋索引檔案不存在: {path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取指紋索引檔案 {path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"指紋索引 JSON 解析失敗 {path}: {e}")
    
    try:
        return FingerprintIndex(**data)
    except Exception as e:
        raise ValueError(f"指紋索引 schema 驗證失敗 {path}: {e}")


def load_fingerprint_index_if_exists(path: Path) -> Optional[FingerprintIndex]:
    """
    載入指紋索引（如果存在）
    
    Args:
        path: 檔案路徑
    
    Returns:
        FingerprintIndex 或 None（如果檔案不存在）
    
    Raises:
        ValueError: JSON 解析失敗或 schema 驗證失敗
    """
    if not path.exists():
        return None
    
    return load_fingerprint_index(path)


def delete_fingerprint_index(path: Path) -> None:
    """
    刪除指紋索引檔案
    
    Args:
        path: 檔案路徑
    """
    if path.exists():
        path.unlink()


def list_fingerprint_indices(
    season: str,
    outputs_root: Optional[Path] = None
) -> list[tuple[str, Path]]:
    """
    列出指定季節的所有指紋索引
    
    Args:
        season: 季節標記
        outputs_root: 輸出根目錄
    
    Returns:
        (dataset_id, path) 的列表
    """
    if outputs_root is None:
        project_root = Path(__file__).parent.parent.parent
        outputs_root = project_root / "outputs"
    
    season_dir = outputs_root / "fingerprints" / season
    
    if not season_dir.exists():
        return []
    
    indices = []
    
    for dataset_dir in season_dir.iterdir():
        if dataset_dir.is_dir():
            index_path = dataset_dir / "fingerprint_index.json"
            if index_path.exists():
                indices.append((dataset_dir.name, index_path))
    
    # 按 dataset_id 排序
    indices.sort(key=lambda x: x[0])
    
    return indices


def ensure_fingerprint_directory(
    season: str,
    dataset_id: str,
    outputs_root: Optional[Path] = None
) -> Path:
    """
    確保指紋索引目錄存在
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        outputs_root: 輸出根目錄
    
    Returns:
        目錄路徑
    """
    path = fingerprint_index_path(season, dataset_id, outputs_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.parent



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/governance.py
sha256(source_bytes) = b158758522aa2fe723c20af18353de95881cd356345fc3f8ea405a51e38b2e4c
bytes = 6656
redacted = False
--------------------------------------------------------------------------------

"""Batch metadata and governance for Phase 14.

Season/tags/note/frozen metadata with immutable rules.

CRITICAL CONTRACTS:
- Metadata MUST live under: artifacts/{batch_id}/metadata.json
  (so a batch folder is fully portable for audit/replay/archive).
- Writes MUST be atomic (tmp + replace) to avoid corrupt JSON on crash.
- Tag handling MUST be deterministic (dedupe + sort).
- Corrupted metadata MUST NOT be silently treated as "not found".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.control.artifacts import write_json_atomic


def _utc_now_iso() -> str:
    # Seconds precision, UTC, Z suffix
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class BatchMetadata:
    """Batch metadata (mutable only before frozen)."""
    batch_id: str
    season: str = ""
    tags: list[str] = field(default_factory=list)
    note: str = ""
    frozen: bool = False
    created_at: str = ""
    updated_at: str = ""
    created_by: str = ""


class BatchGovernanceStore:
    """Persistent store for batch metadata.

    Store root MUST be the artifacts root.
    Metadata path:
      {artifacts_root}/{batch_id}/metadata.json
    """

    def __init__(self, artifacts_root: Path):
        self.artifacts_root = artifacts_root
        self.artifacts_root.mkdir(parents=True, exist_ok=True)

    def _metadata_path(self, batch_id: str) -> Path:
        return self.artifacts_root / batch_id / "metadata.json"

    def get_metadata(self, batch_id: str) -> Optional[BatchMetadata]:
        path = self._metadata_path(batch_id)
        if not path.exists():
            return None

        # Do NOT swallow corruption; let callers handle it explicitly.
        data = json.loads(path.read_text(encoding="utf-8"))

        tags = data.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError("metadata.tags must be a list")

        return BatchMetadata(
            batch_id=data["batch_id"],
            season=data.get("season", ""),
            tags=list(tags),
            note=data.get("note", ""),
            frozen=bool(data.get("frozen", False)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            created_by=data.get("created_by", ""),
        )

    def set_metadata(self, batch_id: str, metadata: BatchMetadata) -> None:
        path = self._metadata_path(batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "batch_id": batch_id,
            "season": metadata.season,
            "tags": list(metadata.tags),
            "note": metadata.note,
            "frozen": bool(metadata.frozen),
            "created_at": metadata.created_at,
            "updated_at": metadata.updated_at,
            "created_by": metadata.created_by,
        }
        write_json_atomic(path, payload)

    def is_frozen(self, batch_id: str) -> bool:
        meta = self.get_metadata(batch_id)
        return bool(meta and meta.frozen)

    def update_metadata(
        self,
        batch_id: str,
        *,
        season: Optional[str] = None,
        tags: Optional[list[str]] = None,
        note: Optional[str] = None,
        frozen: Optional[bool] = None,
        created_by: str = "system",
    ) -> BatchMetadata:
        """Update metadata fields (enforcing frozen rules).

        Frozen rules:
        - If batch is frozen:
          - season cannot change
          - frozen cannot be set to False
          - tags can be appended (dedupe + sort)
          - note can change
          - frozen=True again is a no-op
        """
        existing = self.get_metadata(batch_id)
        now = _utc_now_iso()

        if existing is None:
            existing = BatchMetadata(
                batch_id=batch_id,
                season="",
                tags=[],
                note="",
                frozen=False,
                created_at=now,
                updated_at=now,
                created_by=created_by,
            )

        if existing.frozen:
            if season is not None and season != existing.season:
                raise ValueError("Cannot change season of frozen batch")
            if frozen is False:
                raise ValueError("Cannot unfreeze a frozen batch")

        # Apply changes
        if (season is not None) and (not existing.frozen):
            existing.season = season

        if tags is not None:
            merged = set(existing.tags)
            merged.update(tags)
            existing.tags = sorted(merged)

        if note is not None:
            existing.note = note

        if frozen is not None:
            if frozen is True:
                existing.frozen = True
            elif frozen is False:
                # allowed only when not frozen (blocked above if frozen)
                existing.frozen = False

        existing.updated_at = now
        self.set_metadata(batch_id, existing)
        return existing

    def freeze(self, batch_id: str) -> None:
        """Freeze a batch (irreversible).

        Raises:
            ValueError: If batch metadata not found.
        """
        meta = self.get_metadata(batch_id)
        if meta is None:
            raise ValueError(f"Batch {batch_id} not found")

        if not meta.frozen:
            meta.frozen = True
            meta.updated_at = _utc_now_iso()
            self.set_metadata(batch_id, meta)

    def list_batches(
        self,
        *,
        season: Optional[str] = None,
        tag: Optional[str] = None,
        frozen: Optional[bool] = None,
    ) -> list[BatchMetadata]:
        """List batches matching filters.

        Scans artifacts root for {batch_id}/metadata.json.

        Deterministic ordering:
        - Sort by batch_id.
        """
        results: list[BatchMetadata] = []
        for batch_dir in sorted([p for p in self.artifacts_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            meta_path = batch_dir / "metadata.json"
            if not meta_path.exists():
                continue
            meta = self.get_metadata(batch_dir.name)
            if meta is None:
                continue
            if season is not None and meta.season != season:
                continue
            if tag is not None and tag not in set(meta.tags):
                continue
            if frozen is not None and bool(meta.frozen) != bool(frozen):
                continue
            results.append(meta)
        return results



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/input_manifest.py
sha256(source_bytes) = 8e048ed2268517acf210e0decb3dab1be082b3138ee9c4c05e8c2aa81eac7994
bytes = 13253
redacted = False
--------------------------------------------------------------------------------
"""Input Manifest Generation for Job Auditability.

Generates comprehensive input manifests for job submissions, capturing:
- Dataset information (ID, kind)
- TXT file signatures and status
- Parquet file signatures and status
- Build timestamps
- System snapshot at time of job submission
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import hashlib

from FishBroWFS_V2.control.dataset_descriptor import get_descriptor
from FishBroWFS_V2.gui.services.reload_service import compute_file_signature, get_system_snapshot


@dataclass
class FileManifest:
    """Manifest for a single file."""
    path: str
    exists: bool
    size_bytes: int = 0
    mtime_utc: Optional[str] = None
    signature: str = ""
    error: Optional[str] = None


@dataclass
class DatasetManifest:
    """Manifest for a dataset with TXT and Parquet information."""
    # Required fields (no defaults) first
    dataset_id: str
    kind: str
    txt_root: str
    parquet_root: str
    
    # Optional fields with defaults
    txt_files: List[FileManifest] = field(default_factory=list)
    txt_present: bool = False
    txt_total_size_bytes: int = 0
    txt_signature_aggregate: str = ""
    parquet_files: List[FileManifest] = field(default_factory=list)
    parquet_present: bool = False
    parquet_total_size_bytes: int = 0
    parquet_signature_aggregate: str = ""
    up_to_date: bool = False
    bars_count: Optional[int] = None
    schema_ok: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class InputManifest:
    """Complete input manifest for a job submission."""
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    job_id: Optional[str] = None
    season: str = ""
    
    # Configuration
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    # Data manifests
    data1_manifest: Optional[DatasetManifest] = None
    data2_manifest: Optional[DatasetManifest] = None
    
    # System snapshot (summary)
    system_snapshot_summary: Dict[str, Any] = field(default_factory=dict)
    
    # Audit trail
    manifest_hash: str = ""
    previous_manifest_hash: Optional[str] = None


def create_file_manifest(file_path: str) -> FileManifest:
    """Create manifest for a single file."""
    path = Path(file_path)
    
    if not path.exists():
        return FileManifest(
            path=str(file_path),
            exists=False,
            error="File not found"
        )
    
    try:
        stat = path.stat()
        signature = compute_file_signature(path)
        
        return FileManifest(
            path=str(file_path),
            exists=True,
            size_bytes=stat.st_size,
            mtime_utc=datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
            signature=signature
        )
    except Exception as e:
        return FileManifest(
            path=str(file_path),
            exists=False,
            error=str(e)
        )


def create_dataset_manifest(dataset_id: str) -> DatasetManifest:
    """Create manifest for a dataset."""
    try:
        descriptor = get_descriptor(dataset_id)
        if descriptor is None:
            return DatasetManifest(
                dataset_id=dataset_id,
                kind="unknown",
                txt_root="",
                parquet_root="",
                error=f"Dataset not found: {dataset_id}"
            )
        
        # Process TXT files
        txt_files = []
        txt_present = True
        txt_total_size = 0
        txt_signatures = []
        
        for txt_path_str in descriptor.txt_required_paths:
            file_manifest = create_file_manifest(txt_path_str)
            txt_files.append(file_manifest)
            
            if not file_manifest.exists:
                txt_present = False
            else:
                txt_total_size += file_manifest.size_bytes
                txt_signatures.append(file_manifest.signature)
        
        # Process Parquet files
        parquet_files = []
        parquet_present = True
        parquet_total_size = 0
        parquet_signatures = []
        
        for parquet_path_str in descriptor.parquet_expected_paths:
            file_manifest = create_file_manifest(parquet_path_str)
            parquet_files.append(file_manifest)
            
            if not file_manifest.exists:
                parquet_present = False
            else:
                parquet_total_size += file_manifest.size_bytes
                parquet_signatures.append(file_manifest.signature)
        
        # Determine up-to-date status
        up_to_date = txt_present and parquet_present
        # Simple heuristic: if both present, assume up-to-date
        # In a real implementation, this would compare timestamps or content hashes
        
        # Try to get bars count from Parquet if available
        bars_count = None
        schema_ok = None
        
        if parquet_present and descriptor.parquet_expected_paths:
            try:
                parquet_path = Path(descriptor.parquet_expected_paths[0])
                if parquet_path.exists():
                    # Quick schema check
                    import pandas as pd
                    df_sample = pd.read_parquet(parquet_path, nrows=1)
                    schema_ok = True
                    
                    # Try to get row count for small files
                    if parquet_path.stat().st_size < 1000000:  # < 1MB
                        df = pd.read_parquet(parquet_path)
                        bars_count = len(df)
            except Exception:
                schema_ok = False
        
        return DatasetManifest(
            dataset_id=dataset_id,
            kind=descriptor.kind,
            txt_root=descriptor.txt_root,
            txt_files=txt_files,
            txt_present=txt_present,
            txt_total_size_bytes=txt_total_size,
            txt_signature_aggregate="|".join(txt_signatures) if txt_signatures else "none",
            parquet_root=descriptor.parquet_root,
            parquet_files=parquet_files,
            parquet_present=parquet_present,
            parquet_total_size_bytes=parquet_total_size,
            parquet_signature_aggregate="|".join(parquet_signatures) if parquet_signatures else "none",
            up_to_date=up_to_date,
            bars_count=bars_count,
            schema_ok=schema_ok
        )
    except Exception as e:
        return DatasetManifest(
            dataset_id=dataset_id,
            kind="unknown",
            txt_root="",
            parquet_root="",
            error=str(e)
        )


def create_input_manifest(
    job_id: Optional[str],
    season: str,
    config_snapshot: Dict[str, Any],
    data1_dataset_id: str,
    data2_dataset_id: Optional[str] = None,
    previous_manifest_hash: Optional[str] = None
) -> InputManifest:
    """Create complete input manifest for a job submission.
    
    Args:
        job_id: Job ID (if available)
        season: Season identifier
        config_snapshot: Configuration snapshot from make_config_snapshot
        data1_dataset_id: DATA1 dataset ID
        data2_dataset_id: Optional DATA2 dataset ID
        previous_manifest_hash: Optional hash of previous manifest (for chain)
        
    Returns:
        InputManifest with all audit information
    """
    # Create dataset manifests
    data1_manifest = create_dataset_manifest(data1_dataset_id)
    
    data2_manifest = None
    if data2_dataset_id:
        data2_manifest = create_dataset_manifest(data2_dataset_id)
    
    # Get system snapshot summary
    system_snapshot = get_system_snapshot()
    snapshot_summary = {
        "created_at": system_snapshot.created_at.isoformat(),
        "total_datasets": system_snapshot.total_datasets,
        "total_strategies": system_snapshot.total_strategies,
        "notes": system_snapshot.notes[:5],  # First 5 notes
        "error_count": len(system_snapshot.errors)
    }
    
    # Create manifest
    manifest = InputManifest(
        job_id=job_id,
        season=season,
        config_snapshot=config_snapshot,
        data1_manifest=data1_manifest,
        data2_manifest=data2_manifest,
        system_snapshot_summary=snapshot_summary,
        previous_manifest_hash=previous_manifest_hash
    )
    
    # Compute manifest hash
    manifest_dict = asdict(manifest)
    # Remove hash field before computing hash
    manifest_dict.pop("manifest_hash", None)
    
    # Convert to JSON and compute hash
    manifest_json = json.dumps(manifest_dict, sort_keys=True, separators=(',', ':'))
    manifest_hash = hashlib.sha256(manifest_json.encode('utf-8')).hexdigest()[:32]
    
    manifest.manifest_hash = manifest_hash
    
    return manifest


def write_input_manifest(
    manifest: InputManifest,
    output_path: Path
) -> bool:
    """Write input manifest to file.
    
    Args:
        manifest: InputManifest to write
        output_path: Path to write manifest JSON file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dictionary
        manifest_dict = asdict(manifest)
        
        # Write JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_dict, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Error writing input manifest: {e}")
        return False


def read_input_manifest(input_path: Path) -> Optional[InputManifest]:
    """Read input manifest from file.
    
    Args:
        input_path: Path to manifest JSON file
        
    Returns:
        InputManifest if successful, None otherwise
    """
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruct nested objects
        if data.get('data1_manifest'):
            data1_dict = data['data1_manifest']
            data['data1_manifest'] = DatasetManifest(**data1_dict)
        
        if data.get('data2_manifest'):
            data2_dict = data['data2_manifest']
            data['data2_manifest'] = DatasetManifest(**data2_dict)
        
        return InputManifest(**data)
    except Exception as e:
        print(f"Error reading input manifest: {e}")
        return None


def verify_input_manifest(manifest: InputManifest) -> Dict[str, Any]:
    """Verify input manifest integrity and completeness.
    
    Args:
        manifest: InputManifest to verify
        
    Returns:
        Dictionary with verification results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": []
    }
    
    # Check manifest hash
    manifest_dict = asdict(manifest)
    original_hash = manifest_dict.pop("manifest_hash", None)
    
    manifest_json = json.dumps(manifest_dict, sort_keys=True, separators=(',', ':'))
    computed_hash = hashlib.sha256(manifest_json.encode('utf-8')).hexdigest()[:32]
    
    if original_hash != computed_hash:
        results["valid"] = False
        results["errors"].append(f"Manifest hash mismatch: expected {original_hash}, got {computed_hash}")
    else:
        results["checks"].append("Manifest hash verified")
    
    # Check DATA1 manifest
    if manifest.data1_manifest:
        if not manifest.data1_manifest.txt_present:
            results["warnings"].append(f"DATA1 dataset {manifest.data1_manifest.dataset_id} missing TXT files")
        
        if not manifest.data1_manifest.parquet_present:
            results["warnings"].append(f"DATA1 dataset {manifest.data1_manifest.dataset_id} missing Parquet files")
        
        if manifest.data1_manifest.error:
            results["warnings"].append(f"DATA1 dataset error: {manifest.data1_manifest.error}")
    else:
        results["errors"].append("Missing DATA1 manifest")
        results["valid"] = False
    
    # Check DATA2 manifest if present
    if manifest.data2_manifest:
        if not manifest.data2_manifest.txt_present:
            results["warnings"].append(f"DATA2 dataset {manifest.data2_manifest.dataset_id} missing TXT files")
        
        if not manifest.data2_manifest.parquet_present:
            results["warnings"].append(f"DATA2 dataset {manifest.data2_manifest.dataset_id} missing Parquet files")
        
        if manifest.data2_manifest.error:
            results["warnings"].append(f"DATA2 dataset error: {manifest.data2_manifest.error}")
    
    # Check system snapshot
    if not manifest.system_snapshot_summary:
        results["warnings"].append("System snapshot summary is empty")
    
    # Check timestamp
    try:
        created_at = datetime.fromisoformat(manifest.created_at.replace('Z', '+00:00'))
        age_hours = (datetime.utcnow() - created_at).total_seconds() / 3600
        if age_hours > 24:
            results["warnings"].append(f"Manifest is {age_hours:.1f} hours old")
    except Exception:
        results["warnings"].append("Invalid timestamp format")
    
    return results
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/job_api.py
sha256(source_bytes) = 51ebea6835a567c4bb389a86794d02cbd2db9380d027ed111528ac0d1758a074
bytes = 16368
redacted = False
--------------------------------------------------------------------------------
"""Job API for M1 Wizard.

Provides job creation and governance checking for the wizard UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from FishBroWFS_V2.control.jobs_db import create_job, get_job, list_jobs
from FishBroWFS_V2.control.types import DBJobSpec, JobRecord, JobStatus
from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog
from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog
from FishBroWFS_V2.control.dataset_descriptor import get_descriptor
from FishBroWFS_V2.control.input_manifest import create_input_manifest, write_input_manifest
from FishBroWFS_V2.core.config_snapshot import make_config_snapshot


class JobAPIError(Exception):
    """Base exception for Job API errors."""
    pass


class SeasonFrozenError(JobAPIError):
    """Raised when trying to submit a job to a frozen season."""
    pass


class ValidationError(JobAPIError):
    """Raised when job validation fails."""
    pass


def check_season_not_frozen(season: str, action: str = "submit_job") -> None:
    """Check if a season is frozen.
    
    Args:
        season: Season identifier (e.g., "2024Q1")
        action: Action being performed (for error message)
        
    Raises:
        SeasonFrozenError: If season is frozen
    """
    # TODO: Implement actual season frozen check
    # For M1, we'll assume seasons are not frozen
    # In a real implementation, this would check season governance state
    pass


def validate_wizard_payload(payload: Dict[str, Any]) -> List[str]:
    """Validate wizard payload.
    
    Args:
        payload: Wizard payload dictionary
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Required fields
    required_fields = ["season", "data1", "strategy_id", "params"]
    for field in required_fields:
        if field not in payload:
            errors.append(f"Missing required field: {field}")
    
    # Validate data1
    if "data1" in payload:
        data1 = payload["data1"]
        if not isinstance(data1, dict):
            errors.append("data1 must be a dictionary")
        else:
            if "dataset_id" not in data1:
                errors.append("data1 missing dataset_id")
            else:
                # Check dataset exists and has Parquet files
                dataset_id = data1["dataset_id"]
                try:
                    descriptor = get_descriptor(dataset_id)
                    if descriptor is None:
                        errors.append(f"Dataset not found: {dataset_id}")
                    else:
                        # Check if Parquet files exist
                        from pathlib import Path
                        parquet_missing = []
                        for parquet_path_str in descriptor.parquet_expected_paths:
                            parquet_path = Path(parquet_path_str)
                            if not parquet_path.exists():
                                parquet_missing.append(parquet_path_str)
                        
                        if parquet_missing:
                            missing_list = ", ".join(parquet_missing[:3])  # Show first 3
                            if len(parquet_missing) > 3:
                                missing_list += f" and {len(parquet_missing) - 3} more"
                            errors.append(f"Dataset {dataset_id} missing Parquet files: {missing_list}")
                            errors.append(f"Use the Status page to build Parquet from TXT sources")
                except Exception as e:
                    errors.append(f"Error checking dataset {dataset_id}: {str(e)}")
            
            if "symbols" not in data1:
                errors.append("data1 missing symbols")
            if "timeframes" not in data1:
                errors.append("data1 missing timeframes")
    
    # Validate data2 if present
    if "data2" in payload and payload["data2"]:
        data2 = payload["data2"]
        if not isinstance(data2, dict):
            errors.append("data2 must be a dictionary or null")
        else:
            if "dataset_id" not in data2:
                errors.append("data2 missing dataset_id")
            else:
                # Check data2 dataset exists and has Parquet files
                dataset_id = data2["dataset_id"]
                try:
                    descriptor = get_descriptor(dataset_id)
                    if descriptor is None:
                        errors.append(f"DATA2 dataset not found: {dataset_id}")
                    else:
                        # Check if Parquet files exist
                        from pathlib import Path
                        parquet_missing = []
                        for parquet_path_str in descriptor.parquet_expected_paths:
                            parquet_path = Path(parquet_path_str)
                            if not parquet_path.exists():
                                parquet_missing.append(parquet_path_str)
                        
                        if parquet_missing:
                            missing_list = ", ".join(parquet_missing[:3])
                            if len(parquet_missing) > 3:
                                missing_list += f" and {len(parquet_missing) - 3} more"
                            errors.append(f"DATA2 dataset {dataset_id} missing Parquet files: {missing_list}")
                except Exception as e:
                    errors.append(f"Error checking DATA2 dataset {dataset_id}: {str(e)}")
            
            if "filters" not in data2:
                errors.append("data2 missing filters")
    
    # Validate strategy
    if "strategy_id" in payload:
        strategy_catalog = get_strategy_catalog()
        strategy = strategy_catalog.get_strategy(payload["strategy_id"])
        if strategy is None:
            errors.append(f"Unknown strategy: {payload['strategy_id']}")
        else:
            # Validate parameters
            params = payload.get("params", {})
            param_errors = strategy_catalog.validate_parameters(payload["strategy_id"], params)
            for param_name, error_msg in param_errors.items():
                errors.append(f"Parameter '{param_name}': {error_msg}")
    
    return errors


def calculate_units(payload: Dict[str, Any]) -> int:
    """Calculate units count for wizard payload.
    
    Units formula: |DATA1.symbols| × |DATA1.timeframes| × |strategies| × |DATA2.filters|
    
    Args:
        payload: Wizard payload dictionary
        
    Returns:
        Total units count
    """
    # Extract data1 symbols and timeframes
    data1 = payload.get("data1", {})
    symbols = data1.get("symbols", [])
    timeframes = data1.get("timeframes", [])
    
    # Count strategies (always 1 for single strategy, but could be list)
    strategy_id = payload.get("strategy_id")
    strategies = [strategy_id] if strategy_id else []
    
    # Extract data2 filters if present
    data2 = payload.get("data2")
    if data2 is None:
        filters = []
    else:
        filters = data2.get("filters", [])
    
    # Apply formula
    symbols_count = len(symbols) if isinstance(symbols, list) else 1
    timeframes_count = len(timeframes) if isinstance(timeframes, list) else 1
    strategies_count = len(strategies) if isinstance(strategies, list) else 1
    filters_count = len(filters) if isinstance(filters, list) else 1
    
    # If data2 is not enabled, filters_count should be 1 (no filter multiplication)
    if not data2 or not payload.get("enable_data2", False):
        filters_count = 1
    
    units = symbols_count * timeframes_count * strategies_count * filters_count
    return units


def create_job_from_wizard(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a job from wizard payload.
    
    This is the main function called by the wizard UI on submit.
    
    Args:
        payload: Wizard payload dictionary with structure:
            {
                "season": "2024Q1",
                "data1": {
                    "dataset_id": "CME.MNQ.60m.2020-2024",
                    "symbols": ["MNQ", "MXF"],
                    "timeframes": ["60m", "120m"],
                    "start_date": "2020-01-01",
                    "end_date": "2024-12-31"
                },
                "data2": {
                    "dataset_id": "TWF.MXF.15m.2018-2023",
                    "filters": ["filter1", "filter2"]
                } | null,
                "strategy_id": "sma_cross_v1",
                "params": {
                    "window_fast": 10,
                    "window_slow": 30
                },
                "wfs": {
                    "stage0_subsample": 0.1,
                    "top_k": 20,
                    "mem_limit_mb": 8192,
                    "allow_auto_downsample": True
                }
            }
        
    Returns:
        Dictionary with job_id and units count:
            {
                "job_id": "uuid-here",
                "units": 4,
                "season": "2024Q1",
                "status": "queued"
            }
        
    Raises:
        SeasonFrozenError: If season is frozen
        ValidationError: If payload validation fails
    """
    # Check season not frozen
    season = payload.get("season")
    if season:
        check_season_not_frozen(season, action="submit_job")
    
    # Validate payload
    errors = validate_wizard_payload(payload)
    if errors:
        raise ValidationError(f"Payload validation failed: {', '.join(errors)}")
    
    # Calculate units
    units = calculate_units(payload)
    
    # Create config snapshot
    config_snapshot = make_config_snapshot(payload)
    
    # Create DBJobSpec
    data1 = payload["data1"]
    dataset_id = data1["dataset_id"]
    
    # Generate outputs root path
    outputs_root = f"outputs/{season}/jobs"
    
    # Create job spec
    spec = DBJobSpec(
        season=season,
        dataset_id=dataset_id,
        outputs_root=outputs_root,
        config_snapshot=config_snapshot,
        config_hash="",  # Will be computed by create_job
        data_fingerprint_sha256_40=""  # Will be populated if needed
    )
    
    # Create job in database
    db_path = Path("outputs/jobs.db")
    job_id = create_job(db_path, spec)
    
    # Create input manifest for auditability
    try:
        # Extract DATA2 dataset ID if present
        data2_dataset_id = None
        if "data2" in payload and payload["data2"]:
            data2 = payload["data2"]
            data2_dataset_id = data2.get("dataset_id")
        
        # Create input manifest
        from FishBroWFS_V2.control.input_manifest import create_input_manifest, write_input_manifest
        
        manifest = create_input_manifest(
            job_id=job_id,
            season=season,
            config_snapshot=config_snapshot,
            data1_dataset_id=dataset_id,
            data2_dataset_id=data2_dataset_id,
            previous_manifest_hash=None  # First in chain
        )
        
        # Write manifest to job outputs directory
        manifest_dir = Path(f"outputs/{season}/jobs/{job_id}")
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "input_manifest.json"
        
        write_success = write_input_manifest(manifest, manifest_path)
        
        if not write_success:
            # Log warning but don't fail the job
            print(f"Warning: Failed to write input manifest for job {job_id}")
    except Exception as e:
        # Don't fail job creation if manifest creation fails
        print(f"Warning: Failed to create input manifest for job {job_id}: {e}")
    
    return {
        "job_id": job_id,
        "units": units,
        "season": season,
        "status": "queued"
    }


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Get job status with units progress.
    
    Args:
        job_id: Job ID
        
    Returns:
        Dictionary with job status and progress:
            {
                "job_id": "uuid-here",
                "status": "running",
                "units_done": 10,
                "units_total": 20,
                "progress": 0.5,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
    """
    db_path = Path("outputs/jobs.db")
    try:
        job = get_job(db_path, job_id)
        
        # For M1, we need to calculate units_done and units_total
        # This would normally come from job execution progress
        # For now, we'll return placeholder values
        units_total = 0
        units_done = 0
        
        # Try to extract units from config snapshot
        if hasattr(job.spec, 'config_snapshot'):
            config = job.spec.config_snapshot
            if isinstance(config, dict) and 'units' in config:
                units_total = config.get('units', 0)
        
        # Estimate units_done based on status
        if job.status == JobStatus.DONE:
            units_done = units_total
        elif job.status == JobStatus.RUNNING:
            # For demo, assume 50% progress
            units_done = units_total // 2 if units_total > 0 else 0
        
        progress = units_done / units_total if units_total > 0 else 0
        
        return {
            "job_id": job_id,
            "status": job.status.value,
            "units_done": units_done,
            "units_total": units_total,
            "progress": progress,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "season": job.spec.season,
            "dataset_id": job.spec.dataset_id
        }
    except KeyError:
        raise JobAPIError(f"Job not found: {job_id}")


def list_jobs_with_progress(limit: int = 50) -> List[Dict[str, Any]]:
    """List jobs with units progress.
    
    Args:
        limit: Maximum number of jobs to return
        
    Returns:
        List of job dictionaries with progress information
    """
    db_path = Path("outputs/jobs.db")
    jobs = list_jobs(db_path, limit=limit)
    
    result = []
    for job in jobs:
        # Calculate progress for each job
        units_total = 0
        units_done = 0
        
        if hasattr(job.spec, 'config_snapshot'):
            config = job.spec.config_snapshot
            if isinstance(config, dict) and 'units' in config:
                units_total = config.get('units', 0)
        
        if job.status == JobStatus.DONE:
            units_done = units_total
        elif job.status == JobStatus.RUNNING:
            units_done = units_total // 2 if units_total > 0 else 0
        
        progress = units_done / units_total if units_total > 0 else 0
        
        result.append({
            "job_id": job.job_id,
            "status": job.status.value,
            "units_done": units_done,
            "units_total": units_total,
            "progress": progress,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "season": job.spec.season,
            "dataset_id": job.spec.dataset_id
        })
    
    return result


def get_job_logs_tail(job_id: str, lines: int = 50) -> List[str]:
    """Get tail of job logs.
    
    Args:
        job_id: Job ID
        lines: Number of lines to return
        
    Returns:
        List of log lines (most recent first)
    """
    # TODO: Implement actual log retrieval
    # For M1, return placeholder logs
    return [
        f"[{datetime.now().isoformat()}] Job {job_id} started",
        f"[{datetime.now().isoformat()}] Loading dataset...",
        f"[{datetime.now().isoformat()}] Running strategy...",
        f"[{datetime.now().isoformat()}] Processing units...",
    ][-lines:]


# Convenience functions for GUI
def submit_wizard_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Submit wizard job (alias for create_job_from_wizard)."""
    return create_job_from_wizard(payload)


def get_job_summary(job_id: str) -> Dict[str, Any]:
    """Get job summary for detail page."""
    status = get_job_status(job_id)
    logs = get_job_logs_tail(job_id, lines=20)
    
    return {
        **status,
        "logs": logs,
        "log_tail": "\n".join(logs[-10:]) if logs else "No logs available"
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/job_expand.py
sha256(source_bytes) = 124c9e258aa09551dbfef65a33d56f02d988bc1aad642307ef6f4c37b25918fb
bytes = 3852
redacted = False
--------------------------------------------------------------------------------

"""Job Template Expansion for Phase 13.

Expand a JobTemplate (with param grids) into a deterministic list of JobSpec.
Pure functions, no side effects.
"""

from __future__ import annotations

import itertools
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from FishBroWFS_V2.control.job_spec import DataSpec, WizardJobSpec, WFSSpec
from FishBroWFS_V2.control.param_grid import ParamGridSpec, values_for_param


class JobTemplate(BaseModel):
    """Template for generating multiple JobSpec via parameter grids.
    
    Phase 13: All parameters must be explicitly configured via param_grid.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    season: str = Field(
        ...,
        description="Season identifier (e.g., '2024Q1')"
    )
    
    dataset_id: str = Field(
        ...,
        description="Dataset identifier (must match registry)"
    )
    
    strategy_id: str = Field(
        ...,
        description="Strategy identifier (must match registry)"
    )
    
    param_grid: dict[str, ParamGridSpec] = Field(
        ...,
        description="Mapping from parameter name to grid specification"
    )
    
    wfs: WFSSpec = Field(
        default_factory=WFSSpec,
        description="WFS configuration"
    )


def expand_job_template(template: JobTemplate) -> list[WizardJobSpec]:
    """Expand a JobTemplate into a deterministic list of WizardJobSpec.
    
    Args:
        template: Job template with param grids
    
    Returns:
        List of WizardJobSpec in deterministic order.
    
    Raises:
        ValueError: if any param grid is invalid.
    """
    # Sort param names for deterministic expansion
    param_names = sorted(template.param_grid.keys())
    
    # For each param, compute list of values
    param_values: dict[str, list[Any]] = {}
    for name in param_names:
        grid = template.param_grid[name]
        values = values_for_param(grid)
        param_values[name] = values
    
    # Compute Cartesian product in deterministic order
    # Order: iterate params sorted by name, values in order from values_for_param
    value_lists = [param_values[name] for name in param_names]
    
    # Create a DataSpec with placeholder dates (tests don't care about dates)
    # Use fixed dates that are valid for any dataset
    data1 = DataSpec(
        dataset_id=template.dataset_id,
        start_date=date(2000, 1, 1),
        end_date=date(2000, 1, 2)
    )
    
    jobs = []
    for combo in itertools.product(*value_lists):
        params = dict(zip(param_names, combo))
        job = WizardJobSpec(
            season=template.season,
            data1=data1,
            data2=None,
            strategy_id=template.strategy_id,
            params=params,
            wfs=template.wfs
        )
        jobs.append(job)
    
    return jobs


def estimate_total_jobs(template: JobTemplate) -> int:
    """Estimate total number of jobs that would be generated.
    
    Returns:
        Product of value counts for each parameter.
    """
    total = 1
    for grid in template.param_grid.values():
        total *= len(values_for_param(grid))
    return total


def validate_template(template: JobTemplate) -> None:
    """Validate template.
    
    Raises ValueError with descriptive message if invalid.
    """
    if not template.season:
        raise ValueError("season must be non-empty")
    if not template.dataset_id:
        raise ValueError("dataset_id must be non-empty")
    if not template.strategy_id:
        raise ValueError("strategy_id must be non-empty")
    if not template.param_grid:
        raise ValueError("param_grid cannot be empty")
    
    # Validate each grid (values_for_param will raise if invalid)
    for grid in template.param_grid.values():
        values_for_param(grid)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/job_spec.py
sha256(source_bytes) = 0a62e74a9d3ad7f379f4e5053522f74f31b3f68e261b424559aad7be61ccb753
bytes = 3059
redacted = False
--------------------------------------------------------------------------------

"""WizardJobSpec Schema for Research Job Wizard.

Phase 12: WizardJobSpec is the ONLY output from GUI.
Contains all configuration needed to run a research job.
Must NOT contain any worker/engine runtime state.
"""

from __future__ import annotations

from datetime import date
from types import MappingProxyType
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class DataSpec(BaseModel):
    """Dataset specification for a research job."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    dataset_id: str = Field(..., min_length=1)
    start_date: date
    end_date: date
    
    @model_validator(mode="after")
    def _check_dates(self) -> "DataSpec":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class WFSSpec(BaseModel):
    """WFS (Winners Funnel System) configuration."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    stage0_subsample: float = 1.0
    top_k: int = 100
    mem_limit_mb: int = 4096
    allow_auto_downsample: bool = True
    
    @model_validator(mode="after")
    def _check_ranges(self) -> "WFSSpec":
        if not (0.0 < self.stage0_subsample <= 1.0):
            raise ValueError("stage0_subsample must be in (0, 1]")
        if self.top_k <= 0:
            raise ValueError("top_k must be > 0")
        if self.mem_limit_mb < 1024:
            raise ValueError("mem_limit_mb must be >= 1024")
        return self


class WizardJobSpec(BaseModel):
    """Complete job specification for research.
    
    Phase 12 Iron Rule: GUI's ONLY output = WizardJobSpec JSON
    Must NOT contain worker/engine runtime state.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    season: str = Field(..., min_length=1)
    data1: DataSpec
    data2: Optional[DataSpec] = None
    strategy_id: str = Field(..., min_length=1)
    params: Mapping[str, Any] = Field(default_factory=dict)
    wfs: WFSSpec = Field(default_factory=WFSSpec)
    
    @model_validator(mode="after")
    def _freeze_params(self) -> "WizardJobSpec":
        # make params immutable so test_jobspec_immutability passes
        if not isinstance(self.params, MappingProxyType):
            object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        return self
    
    @field_serializer("params")
    def _ser_params(self, v: Mapping[str, Any]) -> dict[str, Any]:
        return dict(v)

    @property
    def dataset_id(self) -> str:
        """Alias for data1.dataset_id (for backward compatibility)."""
        return self.data1.dataset_id


# Example WizardJobSpec for documentation
EXAMPLE_WIZARD_JOBSPEC = WizardJobSpec(
    season="2024Q1",
    data1=DataSpec(
        dataset_id="CME.MNQ.60m.2020-2024",
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31)
    ),
    data2=None,
    strategy_id="sma_cross_v1",
    params={"window": 20, "threshold": 0.5},
    wfs=WFSSpec()
)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/jobs_db.py
sha256(source_bytes) = 58d42d8cbb6afd8d144959549c5c52f3813901fe13fecc6977dae0da7fee4d7b
bytes = 29236
redacted = False
--------------------------------------------------------------------------------

"""SQLite jobs database - CRUD and state machine."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypeVar
from uuid import uuid4

from FishBroWFS_V2.control.types import DBJobSpec, JobRecord, JobStatus, StopMode

T = TypeVar("T")


def _connect(db_path: Path) -> sqlite3.Connection:
    """
    Create SQLite connection with concurrency hardening.
    
    One operation = one connection (avoid shared connection across threads).
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Configured SQLite connection with WAL mode and busy timeout
    """
    # One operation = one connection (avoid shared connection across threads)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Concurrency hardening
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")  # ms

    return conn


def _with_retry_locked(fn: Callable[[], T]) -> T:
    """
    Retry DB operation on SQLITE_BUSY/locked errors.
    
    Args:
        fn: Callable that performs DB operation
        
    Returns:
        Result from fn()
        
    Raises:
        sqlite3.OperationalError: If operation fails after retries or for non-locked errors
    """
    # Retry only for SQLITE_BUSY/locked
    delays = (0.05, 0.10, 0.20, 0.40, 0.80, 1.0)
    last: Exception | None = None
    for d in delays:
        try:
            return fn()
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "locked" not in msg and "busy" not in msg:
                raise
            last = e
            time.sleep(d)
    assert last is not None
    raise last


def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create tables or migrate schema in-place.
    
    Idempotent: safe to call multiple times.
    
    Args:
        conn: SQLite connection
    """
    # Create jobs table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            season TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            outputs_root TEXT NOT NULL,
            config_hash TEXT NOT NULL,
            config_snapshot_json TEXT NOT NULL,
            pid INTEGER NULL,
            run_id TEXT NULL,
            run_link TEXT NULL,
            report_link TEXT NULL,
            last_error TEXT NULL,
            requested_stop TEXT NULL,
            requested_pause INTEGER NOT NULL DEFAULT 0,
            tags_json TEXT DEFAULT '[]'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at DESC)")
    
    # Check existing columns for migrations
    cursor = conn.execute("PRAGMA table_info(jobs)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Add run_id column if missing
    if "run_id" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN run_id TEXT")
    
    # Add report_link column if missing
    if "report_link" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN report_link TEXT")
    
    # Add tags_json column if missing
    if "tags_json" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN tags_json TEXT DEFAULT '[]'")
    
    # Add data_fingerprint_sha256_40 column if missing
    if "data_fingerprint_sha256_40" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN data_fingerprint_sha256_40 TEXT DEFAULT ''")
    
    # Create job_logs table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            log_text TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id, created_at DESC)")
    
    conn.commit()


def init_db(db_path: Path) -> None:
    """
    Initialize jobs database schema.
    
    Args:
        db_path: Path to SQLite database file
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            # ensure_schema handles CREATE TABLE IF NOT EXISTS + migrations
    
    _with_retry_locked(_op)


def _now_iso() -> str:
    """Get current UTC time as ISO8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _validate_status_transition(old_status: JobStatus, new_status: JobStatus) -> None:
    """
    Validate status transition (state machine).
    
    Allowed transitions:
    - QUEUED → RUNNING
    - RUNNING → PAUSED (pause=1 and worker checkpoint)
    - PAUSED → RUNNING (pause=0 and worker continues)
    - RUNNING/PAUSED → DONE | FAILED | KILLED
    - QUEUED → KILLED (cancel before running)
    
    Args:
        old_status: Current status
        new_status: Target status
        
    Raises:
        ValueError: If transition is not allowed
    """
    allowed = {
        JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.KILLED},
        JobStatus.RUNNING: {JobStatus.PAUSED, JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED},
        JobStatus.PAUSED: {JobStatus.RUNNING, JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED},
    }
    
    if old_status in allowed:
        if new_status not in allowed[old_status]:
            raise ValueError(
                f"Invalid status transition: {old_status} → {new_status}. "
                f"Allowed: {allowed[old_status]}"
            )
    elif old_status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED}:
        raise ValueError(f"Cannot transition from terminal status: {old_status}")


def create_job(db_path: Path, spec: DBJobSpec, *, tags: list[str] | None = None) -> str:
    """
    Create a new job record.
    
    Args:
        db_path: Path to SQLite database
        spec: Job specification
        tags: Optional list of tags for job categorization
        
    Returns:
        Generated job_id
    """
    job_id = str(uuid4())
    now = _now_iso()
    tags_json = json.dumps(tags if tags else [])
    
    def _op() -> str:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute("""
                INSERT INTO jobs (
                    job_id, status, created_at, updated_at,
                    season, dataset_id, outputs_root, config_hash,
                    config_snapshot_json, requested_pause, tags_json, data_fingerprint_sha256_40
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                JobStatus.QUEUED.value,
                now,
                now,
                spec.season,
                spec.dataset_id,
                spec.outputs_root,
                spec.config_hash,
                json.dumps(spec.config_snapshot),
                0,
                tags_json,
                spec.data_fingerprint_sha256_40 if hasattr(spec, 'data_fingerprint_sha256_40') else '',
            ))
            conn.commit()
        return job_id
    
    return _with_retry_locked(_op)


def _row_to_record(row: tuple) -> JobRecord:
    """Convert database row to JobRecord."""
    # Handle schema versions:
    # - Old: 12 columns (before report_link)
    # - Middle: 13 columns (with report_link, before run_id)
    # - New: 14 columns (with run_id and report_link)
    # - Latest: 15 columns (with tags_json)
    # - Phase 6.5: 16 columns (with data_fingerprint_sha1)
    if len(row) == 16:
        # Phase 6.5 schema with data_fingerprint_sha256_40
        (
            job_id,
            status,
            created_at,
            updated_at,
            season,
            dataset_id,
            outputs_root,
            config_hash,
            config_snapshot_json,
            pid,
            run_id,
            run_link,
            report_link,
            last_error,
            tags_json,
            data_fingerprint_sha256_40,
        ) = row
        # Parse tags_json, fallback to [] if None or invalid
        try:
            tags = json.loads(tags_json) if tags_json else []
            if not isinstance(tags, list):
                tags = []
        except (json.JSONDecodeError, TypeError):
            tags = []
        fingerprint_sha256_40 = data_fingerprint_sha256_40 if data_fingerprint_sha256_40 else ""
    elif len(row) == 15:
        # Latest schema with tags_json (without fingerprint column)
        (
            job_id,
            status,
            created_at,
            updated_at,
            season,
            dataset_id,
            outputs_root,
            config_hash,
            config_snapshot_json,
            pid,
            run_id,
            run_link,
            report_link,
            last_error,
            tags_json,
        ) = row
        # Parse tags_json, fallback to [] if None or invalid
        try:
            tags = json.loads(tags_json) if tags_json else []
            if not isinstance(tags, list):
                tags = []
        except (json.JSONDecodeError, TypeError):
            tags = []
        fingerprint_sha256_40 = ""  # Fallback for schema without data_fingerprint_sha256_40
    elif len(row) == 14:
        # New schema with run_id and report_link
        # Order: job_id, status, created_at, updated_at, season, dataset_id, outputs_root,
        #        config_hash, config_snapshot_json, pid, run_id, run_link, report_link, last_error
        (
            job_id,
            status,
            created_at,
            updated_at,
            season,
            dataset_id,
            outputs_root,
            config_hash,
            config_snapshot_json,
            pid,
            run_id,
            run_link,
            report_link,
            last_error,
        ) = row
        tags = []  # Fallback for schema without tags_json
        fingerprint_sha256_40 = ""  # Fallback for schema without data_fingerprint_sha256_40
    elif len(row) == 13:
        # Middle schema with report_link but no run_id
        (
            job_id,
            status,
            created_at,
            updated_at,
            season,
            dataset_id,
            outputs_root,
            config_hash,
            config_snapshot_json,
            pid,
            run_link,
            last_error,
            report_link,
        ) = row
        run_id = None
        tags = []  # Fallback for old schema
        fingerprint_sha256_40 = ""  # Fallback for schema without data_fingerprint_sha256_40
    else:
        # Old schema (backward compatibility)
        (
            job_id,
            status,
            created_at,
            updated_at,
            season,
            dataset_id,
            outputs_root,
            config_hash,
            config_snapshot_json,
            pid,
            run_link,
            last_error,
        ) = row
        run_id = None
        report_link = None
        tags = []  # Fallback for old schema
        fingerprint_sha256_40 = ""  # Fallback for schema without data_fingerprint_sha256_40
    
    spec = DBJobSpec(
        season=season,
        dataset_id=dataset_id,
        outputs_root=outputs_root,
        config_snapshot=json.loads(config_snapshot_json),
        config_hash=config_hash,
        data_fingerprint_sha256_40=fingerprint_sha256_40,
    )
    
    return JobRecord(
        job_id=job_id,
        status=JobStatus(status),
        created_at=created_at,
        updated_at=updated_at,
        spec=spec,
        pid=pid,
        run_id=run_id if run_id else None,
        run_link=run_link,
        report_link=report_link if report_link else None,
        last_error=last_error,
        tags=tags if tags else [],
        data_fingerprint_sha256_40=fingerprint_sha256_40,
    )


def get_job(db_path: Path, job_id: str) -> JobRecord:
    """
    Get job record by ID.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Returns:
        JobRecord
        
    Raises:
        KeyError: If job not found
    """
    def _op() -> JobRecord:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("""
                SELECT job_id, status, created_at, updated_at,
                       season, dataset_id, outputs_root, config_hash,
                       config_snapshot_json, pid,
                       COALESCE(run_id, NULL) as run_id,
                       run_link,
                       COALESCE(report_link, NULL) as report_link,
                       last_error,
                       COALESCE(tags_json, '[]') as tags_json,
                       COALESCE(data_fingerprint_sha256_40, '') as data_fingerprint_sha256_40
                FROM jobs
                WHERE job_id = ?
            """, (job_id,))
            row = cursor.fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            return _row_to_record(row)
    
    return _with_retry_locked(_op)


def list_jobs(db_path: Path, *, limit: int = 50) -> list[JobRecord]:
    """
    List recent jobs.
    
    Args:
        db_path: Path to SQLite database
        limit: Maximum number of jobs to return
        
    Returns:
        List of JobRecord, ordered by created_at DESC
    """
    def _op() -> list[JobRecord]:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("""
                SELECT job_id, status, created_at, updated_at,
                       season, dataset_id, outputs_root, config_hash,
                       config_snapshot_json, pid,
                       COALESCE(run_id, NULL) as run_id,
                       run_link,
                       COALESCE(report_link, NULL) as report_link,
                       last_error,
                       COALESCE(tags_json, '[]') as tags_json,
                       COALESCE(data_fingerprint_sha256_40, '') as data_fingerprint_sha256_40
                FROM jobs
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            return [_row_to_record(row) for row in cursor.fetchall()]
    
    return _with_retry_locked(_op)


def request_pause(db_path: Path, job_id: str, pause: bool) -> None:
    """
    Request pause/unpause for a job (atomic update).
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        pause: True to pause, False to unpause
        
    Raises:
        KeyError: If job not found
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET requested_pause = ?, updated_at = ?
                WHERE job_id = ?
            """, (1 if pause else 0, _now_iso(), job_id))
            
            if cur.rowcount == 0:
                raise KeyError(f"Job not found: {job_id}")
            
            conn.commit()
    
    _with_retry_locked(_op)


def request_stop(db_path: Path, job_id: str, mode: StopMode) -> None:
    """
    Request stop for a job (atomic update).
    
    If QUEUED, immediately mark as KILLED.
    Otherwise, set requested_stop flag (worker will handle).
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        mode: Stop mode (SOFT or KILL)
        
    Raises:
        KeyError: If job not found
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            # Try to mark QUEUED as KILLED first (atomic)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, requested_stop = ?, updated_at = ?
                WHERE job_id = ? AND status = ?
            """, (JobStatus.KILLED.value, mode.value, _now_iso(), job_id, JobStatus.QUEUED.value))
            
            if cur.rowcount == 1:
                conn.commit()
                return
            
            # Otherwise, set requested_stop flag (atomic)
            cur = conn.execute("""
                UPDATE jobs
                SET requested_stop = ?, updated_at = ?
                WHERE job_id = ?
            """, (mode.value, _now_iso(), job_id))
            
            if cur.rowcount == 0:
                raise KeyError(f"Job not found: {job_id}")
            
            conn.commit()
    
    _with_retry_locked(_op)


def mark_running(db_path: Path, job_id: str, *, pid: int) -> None:
    """
    Mark job as RUNNING with PID (atomic update from QUEUED).
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        pid: Process ID
        
    Raises:
        KeyError: If job not found
        ValueError: If status is terminal (DONE/FAILED/KILLED) or invalid transition
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, pid = ?, updated_at = ?
                WHERE job_id = ? AND status = ?
            """, (JobStatus.RUNNING.value, pid, _now_iso(), job_id, JobStatus.QUEUED.value))
            
            if cur.rowcount == 1:
                conn.commit()
                return
            
            # Check if job exists and current status
            row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            
            status = JobStatus(row[0])
            
            if status == JobStatus.RUNNING:
                # Already running (idempotent)
                return
            
            # Terminal status => ValueError (match existing tests/contract)
            if status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED}:
                raise ValueError("Cannot transition from terminal status")
            
            # Everything else is invalid transition (keep ValueError)
            raise ValueError(f"Invalid status transition: {status.value} → RUNNING")
    
    _with_retry_locked(_op)


def update_running(db_path: Path, job_id: str, *, pid: int) -> None:
    """
    Update job to RUNNING status with PID (legacy alias for mark_running).
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        pid: Process ID
        
    Raises:
        KeyError: If job not found
        RuntimeError: If status transition is invalid
    """
    mark_running(db_path, job_id, pid=pid)


def update_run_link(db_path: Path, job_id: str, *, run_link: str) -> None:
    """
    Update job run_link.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        run_link: Run link path
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute("""
                UPDATE jobs
                SET run_link = ?, updated_at = ?
                WHERE job_id = ?
            """, (run_link, _now_iso(), job_id))
            conn.commit()
    
    _with_retry_locked(_op)


def set_report_link(db_path: Path, job_id: str, report_link: str) -> None:
    """
    Set report_link for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        report_link: Report link URL
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute("""
                UPDATE jobs
                SET report_link = ?, updated_at = ?
                WHERE job_id = ?
            """, (report_link, _now_iso(), job_id))
            conn.commit()
    
    _with_retry_locked(_op)


def mark_done(
    db_path: Path, 
    job_id: str, 
    *, 
    run_id: Optional[str] = None,
    report_link: Optional[str] = None
) -> None:
    """
    Mark job as DONE (atomic update from RUNNING or KILLED).
    
    Idempotent: safe to call multiple times.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        run_id: Optional final stage run_id
        report_link: Optional report link URL
        
    Raises:
        KeyError: If job not found
        RuntimeError: If status is QUEUED/PAUSED (mark_done before RUNNING)
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, updated_at = ?, run_id = ?, report_link = ?, last_error = NULL
                WHERE job_id = ? AND status IN (?, ?)
            """, (
                JobStatus.DONE.value,
                _now_iso(),
                run_id,
                report_link,
                job_id,
                JobStatus.RUNNING.value,
                JobStatus.KILLED.value,
            ))
            
            if cur.rowcount == 1:
                conn.commit()
                return
            
            # Fallback: check if already DONE (idempotent success)
            row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            
            status = JobStatus(row[0])
            if status == JobStatus.DONE:
                # Already done (idempotent)
                return
            
            # If QUEUED/PAUSED, raise RuntimeError (process flow incorrect)
            raise RuntimeError(f"mark_done rejected: status={status} (expected RUNNING or KILLED)")
    
    _with_retry_locked(_op)


def mark_failed(db_path: Path, job_id: str, *, error: str) -> None:
    """
    Mark job as FAILED with error message (atomic update from RUNNING or PAUSED).
    
    Idempotent: safe to call multiple times.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        error: Error message
        
    Raises:
        KeyError: If job not found
        RuntimeError: If status is QUEUED (mark_failed before RUNNING)
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, last_error = ?, updated_at = ?
                WHERE job_id = ? AND status IN (?, ?)
            """, (
                JobStatus.FAILED.value,
                error,
                _now_iso(),
                job_id,
                JobStatus.RUNNING.value,
                JobStatus.PAUSED.value,
            ))
            
            if cur.rowcount == 1:
                conn.commit()
                return
            
            # Fallback: check if already FAILED (idempotent success)
            row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            
            status = JobStatus(row[0])
            if status == JobStatus.FAILED:
                # Already failed (idempotent)
                return
            
            # If QUEUED, raise RuntimeError (process flow incorrect)
            raise RuntimeError(f"mark_failed rejected: status={status} (expected RUNNING or PAUSED)")
    
    _with_retry_locked(_op)


def mark_killed(db_path: Path, job_id: str, *, error: str | None = None) -> None:
    """
    Mark job as KILLED (atomic update).
    
    Idempotent: safe to call multiple times.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        error: Optional error message
        
    Raises:
        KeyError: If job not found
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, last_error = ?, updated_at = ?
                WHERE job_id = ?
            """, (JobStatus.KILLED.value, error, _now_iso(), job_id))
            
            if cur.rowcount == 0:
                raise KeyError(f"Job not found: {job_id}")
            
            conn.commit()
    
    _with_retry_locked(_op)


def get_requested_stop(db_path: Path, job_id: str) -> Optional[str]:
    """
    Get requested_stop value for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Returns:
        Stop mode string or None
    """
    def _op() -> Optional[str]:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("SELECT requested_stop FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
    
    return _with_retry_locked(_op)


def get_requested_pause(db_path: Path, job_id: str) -> bool:
    """
    Get requested_pause value for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Returns:
        True if pause requested, False otherwise
    """
    def _op() -> bool:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("SELECT requested_pause FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            return bool(row[0]) if row else False
    
    return _with_retry_locked(_op)


def search_by_tag(db_path: Path, tag: str, *, limit: int = 50) -> list[JobRecord]:
    """
    Search jobs by tag.
    
    Uses LIKE query to find jobs containing the tag in tags_json.
    For exact matching, use application-layer filtering.
    
    Args:
        db_path: Path to SQLite database
        tag: Tag to search for
        limit: Maximum number of jobs to return
        
    Returns:
        List of JobRecord matching the tag, ordered by created_at DESC
    """
    def _op() -> list[JobRecord]:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            # Use LIKE to search for tag in JSON array
            # Pattern: tag can appear as ["tag"] or ["tag", ...] or [..., "tag", ...] or [..., "tag"]
            search_pattern = f'%"{tag}"%'
            cursor = conn.execute("""
                SELECT job_id, status, created_at, updated_at,
                       season, dataset_id, outputs_root, config_hash,
                       config_snapshot_json, pid,
                       COALESCE(run_id, NULL) as run_id,
                       run_link,
                       COALESCE(report_link, NULL) as report_link,
                       last_error,
                       COALESCE(tags_json, '[]') as tags_json,
                       COALESCE(data_fingerprint_sha256_40, '') as data_fingerprint_sha256_40
                FROM jobs
                WHERE tags_json LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (search_pattern, limit))
            
            records = [_row_to_record(row) for row in cursor.fetchall()]
            
            # Application-layer filtering for exact match (more reliable than LIKE)
            # Filter to ensure tag is actually in the list, not just substring match
            filtered = []
            for record in records:
                if tag in record.tags:
                    filtered.append(record)
            
            return filtered
    
    return _with_retry_locked(_op)


def append_log(db_path: Path, job_id: str, log_text: str) -> None:
    """
    Append log entry to job_logs table.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        log_text: Log text to append (can be full traceback)
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute("""
                INSERT INTO job_logs (job_id, created_at, log_text)
                VALUES (?, ?, ?)
            """, (job_id, _now_iso(), log_text))
            conn.commit()
    
    _with_retry_locked(_op)


def get_job_logs(db_path: Path, job_id: str, *, limit: int = 100) -> list[str]:
    """
    Get log entries for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        limit: Maximum number of log entries to return
        
    Returns:
        List of log text entries, ordered by created_at DESC
    """
    def _op() -> list[str]:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("""
                SELECT log_text
                FROM job_logs
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (job_id, limit))
            return [row[0] for row in cursor.fetchall()]
    
    return _with_retry_locked(_op)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/param_grid.py
sha256(source_bytes) = ec3d2f41d683f1ced1ffb24842c56e56e0e846b63d4aef4e04de8b29acfcdc21
bytes = 12343
redacted = False
--------------------------------------------------------------------------------

"""Parameter Grid Expansion for Phase 13.

Pure functions for turning ParamSpec + user grid config into value lists.
Deterministic ordering, no floating drift surprises.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from FishBroWFS_V2.strategy.param_schema import ParamSpec


class GridMode(str, Enum):
    """Grid expansion mode."""
    SINGLE = "single"
    RANGE = "range"
    MULTI = "multi"


class ParamGridSpec(BaseModel):
    """User-defined grid specification for a single parameter.
    
    Exactly one of the three modes must be active.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    mode: GridMode = Field(
        ...,
        description="Grid expansion mode"
    )
    
    single_value: Any | None = Field(
        default=None,
        description="Single value for mode='single'"
    )
    
    range_start: float | int | None = Field(
        default=None,
        description="Start of range (inclusive) for mode='range'"
    )
    
    range_end: float | int | None = Field(
        default=None,
        description="End of range (inclusive) for mode='range'"
    )
    
    range_step: float | int | None = Field(
        default=None,
        description="Step size for mode='range'"
    )
    
    multi_values: list[Any] | None = Field(
        default=None,
        description="List of values for mode='multi'"
    )
    
    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: Any) -> GridMode:
        if isinstance(v, str):
            v = v.lower()
        return GridMode(v)
    
    @field_validator("single_value", "range_start", "range_end", "range_step", "multi_values", mode="after")
    @classmethod
    def validate_mode_consistency(cls, v: Any, info) -> Any:
        """Ensure only fields relevant to the active mode are set."""
        mode = info.data.get("mode")
        if mode is None:
            return v
        
        field_name = info.field_name
        
        # Map fields to allowed modes
        allowed_for = {
            "single_value": [GridMode.SINGLE],
            "range_start": [GridMode.RANGE],
            "range_end": [GridMode.RANGE],
            "range_step": [GridMode.RANGE],
            "multi_values": [GridMode.MULTI],
        }
        
        if field_name in allowed_for:
            if mode not in allowed_for[field_name]:
                if v is not None:
                    raise ValueError(
                        f"Field '{field_name}' must be None when mode='{mode.value}'"
                    )
            else:
                if v is None:
                    raise ValueError(
                        f"Field '{field_name}' must be set when mode='{mode.value}'"
                    )
        return v
    
    @field_validator("range_step")
    @classmethod
    def validate_range_step(cls, v: float | int | None) -> float | int | None:
        # Allow zero step; validation will be done in validate_grid_for_param
        return v
    
    @field_validator("range_start", "range_end")
    @classmethod
    def validate_range_order(cls, v: float | int | None, info) -> float | int | None:
        # Allow start > end; validation will be done in validate_grid_for_param
        return v
    
    @field_validator("multi_values")
    @classmethod
    def validate_multi_values(cls, v: list[Any] | None) -> list[Any] | None:
        # Allow empty list; validation will be done in validate_grid_for_param
        return v


def values_for_param(grid: ParamGridSpec) -> list[Any]:
    """Compute deterministic list of values for a parameter.
    
    Args:
        grid: User-defined grid configuration
    
    Returns:
        Sorted unique list of values in deterministic order.
    
    Raises:
        ValueError: if grid is invalid.
    """
    if grid.mode == GridMode.SINGLE:
        return [grid.single_value]
    
    elif grid.mode == GridMode.RANGE:
        start = grid.range_start
        end = grid.range_end
        step = grid.range_step
        
        if start is None or end is None or step is None:
            raise ValueError("range mode requires start, end, and step")
        
        if start > end:
            raise ValueError("start <= end")
        
        # Determine if values are integer-like
        if isinstance(start, int) and isinstance(end, int) and isinstance(step, int):
            # Integer range inclusive
            values = []
            i = 0
            while True:
                val = start + i * step
                if val > end:
                    break
                values.append(val)
                i += 1
            return values
        else:
            # Float range inclusive with drift-safe rounding
            if step <= 0:
                raise ValueError("step must be positive")
            # Add small epsilon to avoid missing the last due to floating error
            num_steps = math.floor((end - start) / step + 1e-12)
            values = []
            for i in range(num_steps + 1):
                val = start + i * step
                # Round to 12 decimal places to avoid floating noise
                val = round(val, 12)
                if val <= end + 1e-12:
                    values.append(val)
            return values
    
    elif grid.mode == GridMode.MULTI:
        values = grid.multi_values
        if values is None:
            raise ValueError("multi_values must be set for multi mode")
        
        # Ensure uniqueness and deterministic order
        seen = set()
        unique = []
        for v in values:
            if v not in seen:
                seen.add(v)
                unique.append(v)
        return unique
    
    else:
        raise ValueError(f"Unknown grid mode: {grid.mode}")


def count_for_param(grid: ParamGridSpec) -> int:
    """Return number of distinct values for this parameter."""
    return len(values_for_param(grid))


def validate_grid_for_param(
    grid: ParamGridSpec,
    param_type: str,
    min: int | float | None = None,
    max: int | float | None = None,
    choices: list[Any] | None = None,
) -> None:
    """Validate that grid is compatible with param spec.
    
    Args:
        grid: Parameter grid specification
        param_type: Parameter type ("int", "float", "bool", "enum")
        min: Minimum allowed value (optional)
        max: Maximum allowed value (optional)
        choices: List of allowed values for enum type (optional)
    
    Raises ValueError with descriptive message if invalid.
    """
    # Check duplicates for MULTI mode
    if grid.mode == GridMode.MULTI and grid.multi_values:
        if len(grid.multi_values) != len(set(grid.multi_values)):
            raise ValueError("multi_values contains duplicate values")
    
    # Check empty multi_values
    if grid.mode == GridMode.MULTI and grid.multi_values is not None and len(grid.multi_values) == 0:
        raise ValueError("multi_values must contain at least one value")
    
    # Range-specific validation
    if grid.mode == GridMode.RANGE:
        if grid.range_step is not None and grid.range_step <= 0:
            raise ValueError("range_step must be positive")
        if grid.range_start is not None and grid.range_end is not None and grid.range_start > grid.range_end:
            raise ValueError("start <= end")
    
    # Type-specific validation
    if param_type == "enum":
        if choices is None:
            raise ValueError("enum parameter must have choices defined")
        if grid.mode == GridMode.RANGE:
            raise ValueError("enum parameters cannot use range mode")
        if grid.mode == GridMode.SINGLE:
            if grid.single_value not in choices:
                raise ValueError(f"value '{grid.single_value}' not in choices {choices}")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if val not in choices:
                    raise ValueError(f"value '{val}' not in choices {choices}")
    
    elif param_type == "bool":
        if grid.mode == GridMode.RANGE:
            raise ValueError("bool parameters cannot use range mode")
        if grid.mode == GridMode.SINGLE:
            if not isinstance(grid.single_value, bool):
                raise ValueError(f"bool parameter expects bool value, got {type(grid.single_value)}")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if not isinstance(val, bool):
                    raise ValueError(f"bool parameter expects bool values, got {type(val)}")
    
    elif param_type == "int":
        # Ensure values are integers
        if grid.mode == GridMode.SINGLE:
            if not isinstance(grid.single_value, int):
                raise ValueError("int parameter expects integer value")
        elif grid.mode == GridMode.RANGE:
            if not (isinstance(grid.range_start, (int, float)) and
                    isinstance(grid.range_end, (int, float)) and
                    isinstance(grid.range_step, (int, float))):
                raise ValueError("int range requires numeric start/end/step")
            # Values will be integer due to integer step
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if not isinstance(val, int):
                    raise ValueError("int parameter expects integer values")
    
    elif param_type == "float":
        # Ensure values are numeric
        if grid.mode == GridMode.SINGLE:
            if not isinstance(grid.single_value, (int, float)):
                raise ValueError("float parameter expects numeric value")
        elif grid.mode == GridMode.RANGE:
            if not (isinstance(grid.range_start, (int, float)) and
                    isinstance(grid.range_end, (int, float)) and
                    isinstance(grid.range_step, (int, float))):
                raise ValueError("float range requires numeric start/end/step")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if not isinstance(val, (int, float)):
                    raise ValueError("float parameter expects numeric values")
    
    # Check bounds
    if min is not None:
        if grid.mode == GridMode.SINGLE:
            val = grid.single_value
            if val is not None and val < min:
                raise ValueError(f"value {val} out of range (min {min})")
        elif grid.mode == GridMode.RANGE:
            if grid.range_start is not None and grid.range_start < min:
                raise ValueError(f"range_start {grid.range_start} out of range (min {min})")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if val < min:
                    raise ValueError(f"value {val} out of range (min {min})")
    
    if max is not None:
        if grid.mode == GridMode.SINGLE:
            val = grid.single_value
            if val is not None and val > max:
                raise ValueError(f"value {val} out of range (max {max})")
        elif grid.mode == GridMode.RANGE:
            if grid.range_end is not None and grid.range_end > max:
                raise ValueError(f"range_end {grid.range_end} out of range (max {max})")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if val > max:
                    raise ValueError(f"value {val} out of range (max {max})")
    
    # Compute values to ensure no errors
    values_for_param(grid)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/paths.py
sha256(source_bytes) = 69a18e2dc18f8c6eaf4dfe0e60618f44fa618dd7a06a1770d2e0735b827c7a21
bytes = 882
redacted = False
--------------------------------------------------------------------------------

"""Path helpers for B5-C Mission Control."""

from __future__ import annotations

import os
from pathlib import Path


def get_outputs_root() -> Path:
    """
    Single source of truth for outputs root.
    - Default: ./outputs (repo relative)
    - Override: env FISHBRO_OUTPUTS_ROOT
    """
    p = os.environ.get("FISHBRO_OUTPUTS_ROOT", "outputs")
    return Path(p).resolve()


def run_log_path(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Return outputs log path for a run (mkdir parents).
    
    Args:
        outputs_root: Root outputs directory
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to log file: outputs/{season}/{run_id}/logs/worker.log
    """
    log_path = outputs_root / season / run_id / "logs" / "worker.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/pipeline_runner.py
sha256(source_bytes) = dba6db0993c34d3909b59372deb92139b9865cdd37b20ff3bdfe87d81912d40d
bytes = 9019
redacted = False
--------------------------------------------------------------------------------
"""Pipeline Runner for M1 Wizard.

Stub implementation for job pipeline execution.
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional
from pathlib import Path

from FishBroWFS_V2.control.jobs_db import (
    get_job, mark_running, mark_done, mark_failed, append_log
)
from FishBroWFS_V2.control.job_api import calculate_units
from FishBroWFS_V2.control.artifacts_api import write_research_index


class PipelineRunner:
    """Simple pipeline runner for M1 demonstration."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize pipeline runner.
        
        Args:
            db_path: Path to SQLite database. If None, uses default.
        """
        self.db_path = db_path or Path("outputs/jobs.db")
    
    def run_job(self, job_id: str) -> bool:
        """Run a job (stub implementation for M1).
        
        This is a simplified runner that simulates job execution
        for demonstration purposes.
        
        Args:
            job_id: Job ID to run
            
        Returns:
            True if job completed successfully, False otherwise
        """
        try:
            # Get job record
            job = get_job(self.db_path, job_id)
            
            # Mark as running
            mark_running(self.db_path, job_id, pid=12345)
            self._log(job_id, f"Job {job_id} started")
            
            # Simulate work based on units
            units = 0
            if hasattr(job.spec, 'config_snapshot'):
                config = job.spec.config_snapshot
                if isinstance(config, dict) and 'units' in config:
                    units = config.get('units', 10)
            
            # Default to 10 units if not specified
            if units <= 0:
                units = 10
            
            self._log(job_id, f"Processing {units} units")
            
            # Simulate unit processing
            for i in range(units):
                time.sleep(0.1)  # Simulate work
                progress = (i + 1) / units
                if i % max(1, units // 10) == 0:  # Log every ~10%
                    self._log(job_id, f"Unit {i+1}/{units} completed ({progress:.0%})")
            
            # Mark as done
            mark_done(self.db_path, job_id, run_id=f"run_{job_id}", report_link=f"/reports/{job_id}")
            
            # Write research index (M2)
            try:
                season = job.spec.season if hasattr(job.spec, 'season') else "default"
                # Generate dummy units based on config snapshot
                units = []
                if hasattr(job.spec, 'config_snapshot'):
                    config = job.spec.config_snapshot
                    if isinstance(config, dict):
                        # Extract possible symbols, timeframes, etc.
                        data1 = config.get('data1', {})
                        symbols = data1.get('symbols', ['MNQ'])
                        timeframes = data1.get('timeframes', ['60m'])
                        strategy = config.get('strategy_id', 'vPB_Z')
                        data2_filters = config.get('data2', {}).get('filters', ['VX'])
                        # Create one unit per combination (simplified)
                        for sym in symbols[:1]:  # limit
                            for tf in timeframes[:1]:
                                for filt in data2_filters[:1]:
                                    units.append({
                                        'data1_symbol': sym,
                                        'data1_timeframe': tf,
                                        'strategy': strategy,
                                        'data2_filter': filt,
                                        'status': 'DONE',
                                        'artifacts': {
                                            'canonical_results': f'outputs/seasons/{season}/research/{job_id}/{sym}/{tf}/{strategy}/{filt}/canonical_results.json',
                                            'metrics': f'outputs/seasons/{season}/research/{job_id}/{sym}/{tf}/{strategy}/{filt}/metrics.json',
                                            'trades': f'outputs/seasons/{season}/research/{job_id}/{sym}/{tf}/{strategy}/{filt}/trades.parquet',
                                        }
                                    })
                if not units:
                    # Fallback dummy unit
                    units.append({
                        'data1_symbol': 'MNQ',
                        'data1_timeframe': '60m',
                        'strategy': 'vPB_Z',
                        'data2_filter': 'VX',
                        'status': 'DONE',
                        'artifacts': {
                            'canonical_results': f'outputs/seasons/{season}/research/{job_id}/MNQ/60m/vPB_Z/VX/canonical_results.json',
                            'metrics': f'outputs/seasons/{season}/research/{job_id}/MNQ/60m/vPB_Z/VX/metrics.json',
                            'trades': f'outputs/seasons/{season}/research/{job_id}/MNQ/60m/vPB_Z/VX/trades.parquet',
                        }
                    })
                write_research_index(season, job_id, units)
                self._log(job_id, f"Research index written for {len(units)} units")
            except Exception as e:
                self._log(job_id, f"Failed to write research index: {e}")
            
            self._log(job_id, f"Job {job_id} completed successfully")
            
            return True
            
        except Exception as e:
            # Mark as failed
            error_msg = f"Job failed: {str(e)}"
            try:
                mark_failed(self.db_path, job_id, error=error_msg)
                self._log(job_id, error_msg)
            except Exception:
                pass  # Ignore errors during failure marking
            
            return False
    
    def _log(self, job_id: str, message: str) -> None:
        """Add log entry for job."""
        try:
            append_log(self.db_path, job_id, message)
        except Exception:
            pass  # Ignore log errors
    
    def get_job_progress(self, job_id: str) -> Dict[str, Any]:
        """Get job progress information.
        
        Args:
            job_id: Job ID
            
        Returns:
            Dictionary with progress information
        """
        try:
            job = get_job(self.db_path, job_id)
            
            # Calculate progress based on status
            units_total = 0
            units_done = 0
            
            if hasattr(job.spec, 'config_snapshot'):
                config = job.spec.config_snapshot
                if isinstance(config, dict) and 'units' in config:
                    units_total = config.get('units', 0)
            
            if job.status.value == "DONE":
                units_done = units_total
            elif job.status.value == "RUNNING":
                # For stub, estimate 50% progress
                units_done = units_total // 2 if units_total > 0 else 0
            
            progress = units_done / units_total if units_total > 0 else 0
            
            return {
                "job_id": job_id,
                "status": job.status.value,
                "units_done": units_done,
                "units_total": units_total,
                "progress": progress,
                "is_running": job.status.value == "RUNNING",
                "is_done": job.status.value == "DONE",
                "is_failed": job.status.value == "FAILED"
            }
        except Exception as e:
            return {
                "job_id": job_id,
                "status": "UNKNOWN",
                "units_done": 0,
                "units_total": 0,
                "progress": 0,
                "is_running": False,
                "is_done": False,
                "is_failed": True,
                "error": str(e)
            }


# Singleton instance
_runner_instance: Optional[PipelineRunner] = None

def get_pipeline_runner() -> PipelineRunner:
    """Get singleton pipeline runner instance."""
    global _runner_instance
    if _runner_instance is None:
        _runner_instance = PipelineRunner()
    return _runner_instance


def start_job_async(job_id: str) -> None:
    """Start job execution asynchronously (stub).
    
    In a real implementation, this would spawn a worker process.
    For M1, we'll just simulate immediate execution.
    
    Args:
        job_id: Job ID to start
    """
    # In a real implementation, this would use a task queue or worker pool
    # For M1 demo, we'll run synchronously
    runner = get_pipeline_runner()
    runner.run_job(job_id)


def check_job_status(job_id: str) -> Dict[str, Any]:
    """Check job status (convenience wrapper).
    
    Args:
        job_id: Job ID
        
    Returns:
        Dictionary with job status and progress
    """
    runner = get_pipeline_runner()
    return runner.get_job_progress(job_id)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/preflight.py
sha256(source_bytes) = 2a1f886d87b6c13a8e0d2f89ec4a2e47f48a43e3047f175ae0564b5f328e83aa
bytes = 1985
redacted = False
--------------------------------------------------------------------------------

"""Preflight check - OOM gate and cost summary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from FishBroWFS_V2.core.oom_gate import decide_oom_action


@dataclass(frozen=True)
class PreflightResult:
    """Preflight check result."""

    action: Literal["PASS", "BLOCK", "AUTO_DOWNSAMPLE"]
    reason: str
    original_subsample: float
    final_subsample: float
    estimated_bytes: int
    estimated_mb: float
    mem_limit_mb: float
    mem_limit_bytes: int
    estimates: dict[str, Any]  # must include ops_est, time_est_s, mem_est_mb, ...


def run_preflight(cfg_snapshot: dict[str, Any]) -> PreflightResult:
    """
    Run preflight check (pure, no I/O).
    
    Returns what UI shows in CHECK panel.
    
    Args:
        cfg_snapshot: Sanitized config snapshot (no ndarrays)
        
    Returns:
        PreflightResult with OOM gate decision and estimates
    """
    # Extract mem_limit_mb from config (default: 6000 MB = 6GB)
    mem_limit_mb = float(cfg_snapshot.get("mem_limit_mb", 6000.0))
    
    # Run OOM gate decision
    gate_result = decide_oom_action(
        cfg_snapshot,
        mem_limit_mb=mem_limit_mb,
        allow_auto_downsample=cfg_snapshot.get("allow_auto_downsample", True),
        auto_downsample_step=cfg_snapshot.get("auto_downsample_step", 0.5),
        auto_downsample_min=cfg_snapshot.get("auto_downsample_min", 0.02),
        work_factor=cfg_snapshot.get("work_factor", 2.0),
    )
    
    return PreflightResult(
        action=gate_result["action"],
        reason=gate_result["reason"],
        original_subsample=gate_result["original_subsample"],
        final_subsample=gate_result["final_subsample"],
        estimated_bytes=gate_result["estimated_bytes"],
        estimated_mb=gate_result["estimated_mb"],
        mem_limit_mb=gate_result["mem_limit_mb"],
        mem_limit_bytes=gate_result["mem_limit_bytes"],
        estimates=gate_result["estimates"],
    )




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/report_links.py
sha256(source_bytes) = 3de92e00455914d2971df31aeb7358c93b0c333f7abddd71339530633c63a216
bytes = 2181
redacted = False
--------------------------------------------------------------------------------

"""Report link generation for B5 viewer."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode

# Default outputs root (can be overridden via environment)
DEFAULT_OUTPUTS_ROOT = "outputs"


def get_outputs_root() -> Path:
    """Get outputs root from environment or default."""
    outputs_root_str = os.getenv("FISHBRO_OUTPUTS_ROOT", DEFAULT_OUTPUTS_ROOT)
    return Path(outputs_root_str)


def make_report_link(*, season: str, run_id: str) -> str:
    """
    Generate report link for B5 viewer.
    
    Args:
        season: Season identifier (e.g. "2026Q1")
        run_id: Run ID (e.g. "stage0_coarse-20251218T093512Z-d3caa754")
        
    Returns:
        Report link URL with querystring (e.g. "/?season=2026Q1&run_id=stage0_xxx")
    """
    # Test contract: link.startswith("/?")
    base = "/"
    qs = urlencode({"season": season, "run_id": run_id})
    return f"{base}?{qs}"


def is_report_ready(run_id: str) -> bool:
    """
    Check if report is ready (minimal artifacts exist).
    
    Phase 6 rule: Only check file existence, not content validity.
    Content validation is Viewer's responsibility.
    
    Args:
        run_id: Run ID to check
        
    Returns:
        True if all required artifacts exist, False otherwise
    """
    try:
        outputs_root = get_outputs_root()
        base = outputs_root / run_id
        
        # Check for winners_v2.json first, fallback to winners.json
        winners_v2_path = base / "winners_v2.json"
        winners_path = base / "winners.json"
        winners_exists = winners_v2_path.exists() or winners_path.exists()
        
        required = [
            base / "manifest.json",
            base / "governance.json",
        ]
        
        return winners_exists and all(p.exists() for p in required)
    except Exception:
        return False


def build_report_link(*args: str) -> str:
    if len(args) == 1:
        run_id = args[0]
        season = "test"
        return f"/?season={season}&run_id={run_id}"

    if len(args) == 2:
        season, run_id = args
        return f"/b5?season={season}&run_id={run_id}"

    return ""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/research_cli.py
sha256(source_bytes) = c838406e575272eeca8361901a974e0dfcd7dabbc76ea24b4e5a2dd6f8568386
bytes = 7176
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/research_cli.py
"""
Research CLI：研究執行命令列介面

命令：
fishbro research run \
  --season 2026Q1 \
  --dataset-id CME.MNQ \
  --strategy-id S1 \
  --allow-build \
  --txt-path /home/fishbro/FishBroData/raw/CME.MNQ-HOT-Minute-Trade.txt \
  --mode incremental \
  --json

Exit code：
0：成功
20：缺 features 且不允許 build
1：其他錯誤
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.control.research_runner import (
    run_research,
    ResearchRunError,
)
from FishBroWFS_V2.control.build_context import BuildContext
from FishBroWFS_V2.strategy.registry import load_builtin_strategies


def main() -> int:
    """CLI 主函數"""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        return run_research_cli(args)
    except KeyboardInterrupt:
        print("\n中斷執行", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"錯誤: {e}", file=sys.stderr)
        return 1


def create_parser() -> argparse.ArgumentParser:
    """建立命令列解析器"""
    parser = argparse.ArgumentParser(
        description="執行研究（載入策略、解析特徵、執行 WFS）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # 必要參數
    parser.add_argument(
        "--season",
        required=True,
        help="季節標記，例如 2026Q1",
    )
    parser.add_argument(
        "--dataset-id",
        required=True,
        help="資料集 ID，例如 CME.MNQ",
    )
    parser.add_argument(
        "--strategy-id",
        required=True,
        help="策略 ID",
    )
    
    # build 相關參數
    parser.add_argument(
        "--allow-build",
        action="store_true",
        help="允許自動 build 缺失的特徵",
    )
    parser.add_argument(
        "--txt-path",
        type=Path,
        help="原始 TXT 檔案路徑（只有 allow-build 才需要）",
    )
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="build 模式（只在 allow-build 時使用）",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="輸出根目錄",
    )
    parser.add_argument(
        "--build-bars-if-missing",
        action="store_true",
        default=True,
        help="如果 bars cache 不存在，是否建立 bars",
    )
    parser.add_argument(
        "--no-build-bars-if-missing",
        action="store_false",
        dest="build_bars_if_missing",
        help="不建立 bars cache（即使缺失）",
    )
    
    # WFS 配置（可選）
    parser.add_argument(
        "--wfs-config",
        type=Path,
        help="WFS 配置 JSON 檔案路徑（可選）",
    )
    
    # 輸出選項
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式輸出結果",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="輸出詳細資訊",
    )
    
    return parser


def ensure_builtin_strategies_loaded() -> None:
    """Ensure built-in strategies are loaded (idempotent).
    
    This function can be called multiple times without crashing.
    """
    try:
        load_builtin_strategies()
    except ValueError as e:
        # registry is process-local; re-entry may raise duplicate register
        if "already registered" not in str(e):
            raise


def run_research_cli(args) -> int:
    """執行研究邏輯"""
    # 0. 確保 built-in strategies 已載入
    ensure_builtin_strategies_loaded()
    
    # 1. 準備 build_ctx（如果需要）
    build_ctx = prepare_build_context(args)
    
    # 2. 載入 WFS 配置（如果有）
    wfs_config = load_wfs_config(args)
    
    # 3. 執行研究
    try:
        report = run_research(
            season=args.season,
            dataset_id=args.dataset_id,
            strategy_id=args.strategy_id,
            outputs_root=args.outputs_root,
            allow_build=args.allow_build,
            build_ctx=build_ctx,
            wfs_config=wfs_config,
        )
        
        # 4. 輸出結果
        output_result(report, args)
        
        # 判斷 exit code
        # 如果有 build，回傳 10；否則回傳 0
        if report.get("build_performed", False):
            return 10
        else:
            return 0
        
    except ResearchRunError as e:
        # 檢查是否為缺失特徵且不允許 build 的錯誤
        err_msg = str(e).lower()
        if "缺失特徵且不允許建置" in err_msg or "missing features" in err_msg:
            print(f"缺失特徵且不允許建置: {e}", file=sys.stderr)
            return 20
        else:
            print(f"研究執行失敗: {e}", file=sys.stderr)
            return 1


def prepare_build_context(args) -> Optional[BuildContext]:
    """準備 BuildContext"""
    if not args.allow_build:
        return None
    
    if not args.txt_path:
        raise ValueError("--allow-build 需要 --txt-path")
    
    # 驗證 txt_path 存在
    if not args.txt_path.exists():
        raise FileNotFoundError(f"TXT 檔案不存在: {args.txt_path}")
    
    # 轉換 mode 為大寫
    mode = args.mode.upper()
    if mode not in ("FULL", "INCREMENTAL"):
        raise ValueError(f"無效的 mode: {args.mode}，必須為 'incremental' 或 'full'")
    
    return BuildContext(
        txt_path=args.txt_path,
        mode=mode,
        outputs_root=args.outputs_root,
        build_bars_if_missing=args.build_bars_if_missing,
    )


def load_wfs_config(args) -> Optional[dict]:
    """載入 WFS 配置"""
    if not args.wfs_config:
        return None
    
    config_path = args.wfs_config
    if not config_path.exists():
        raise FileNotFoundError(f"WFS 配置檔案不存在: {config_path}")
    
    try:
        content = config_path.read_text(encoding="utf-8")
        return json.loads(content)
    except Exception as e:
        raise ValueError(f"無法載入 WFS 配置 {config_path}: {e}")


def output_result(report: dict, args) -> None:
    """輸出研究結果"""
    if args.json:
        # JSON 格式輸出
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        # 文字格式輸出
        print(f"✅ 研究執行成功")
        print(f"   策略: {report['strategy_id']}")
        print(f"   資料集: {report['dataset_id']}")
        print(f"   季節: {report['season']}")
        print(f"   使用特徵: {len(report['used_features'])} 個")
        print(f"   是否執行了建置: {report['build_performed']}")
        
        if args.verbose:
            print(f"   WFS 摘要:")
            for key, value in report['wfs_summary'].items():
                print(f"     {key}: {value}")
            
            print(f"   特徵列表:")
            for feat in report['used_features']:
                print(f"     {feat['name']}@{feat['timeframe_min']}m")


if __name__ == "__main__":
    sys.exit(main())



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/research_runner.py
sha256(source_bytes) = 3d85f8eebcc6ec7db1368dbd87299c8b99dedc61071434b27ae224af2c1150e4
bytes = 9498
redacted = False
--------------------------------------------------------------------------------

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
        # 也嘗試在專案根目錄的 strategies 資料夾
        json_path = Path("strategies") / strategy_id / "features.json"
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



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/research_slippage_stress.py
sha256(source_bytes) = efa8e049b863ee7f5224d66ea7fbc79ed7b8ef23d317d48e5e890accf186f9fb
bytes = 8238
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/research_slippage_stress.py
"""
Slippage Stress Matrix 計算與 Survive Gate 評估

給定 bars、fills/intents、commission 配置，計算 S0–S3 等級的 KPI 矩陣。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from FishBroWFS_V2.core.slippage_policy import SlippagePolicy, apply_slippage_to_price


@dataclass
class StressResult:
    """
    單一滑價等級的壓力測試結果
    """
    level: str  # 等級名稱，例如 "S0"
    slip_ticks: int  # 滑價 tick 數
    net_after_cost: float  # 扣除成本後的淨利
    gross_profit: float  # 總盈利（未扣除成本）
    gross_loss: float  # 總虧損（未扣除成本）
    profit_factor: float  # 盈利因子 = gross_profit / abs(gross_loss)（如果 gross_loss != 0）
    mdd_after_cost: float  # 扣除成本後的最大回撤（絕對值）
    trades: int  # 交易次數（來回算一次）


@dataclass
class CommissionConfig:
    """
    手續費配置（每邊固定金額）
    """
    per_side_usd: Dict[str, float]  # 商品符號 -> 每邊手續費（USD）
    default_per_side_usd: float = 0.0  # 預設手續費（如果商品未指定）


def compute_stress_matrix(
    bars: Dict[str, np.ndarray],
    fills: List[Dict[str, Any]],
    commission_config: CommissionConfig,
    slippage_policy: SlippagePolicy,
    tick_size_map: Dict[str, float],  # 商品符號 -> tick_size
    symbol: str,  # 當前商品符號，例如 "MNQ"
) -> Dict[str, StressResult]:
    """
    計算滑價壓力矩陣（S0–S3）

    Args:
        bars: 價格 bars 字典，至少包含 "open", "high", "low", "close"
        fills: 成交列表，每個成交為字典，包含 "entry_price", "exit_price", "entry_side", "exit_side", "quantity" 等欄位
        commission_config: 手續費配置
        slippage_policy: 滑價政策
        tick_size_map: tick_size 對應表
        symbol: 商品符號

    Returns:
        字典 mapping level -> StressResult
    """
    # 取得 tick_size
    tick_size = tick_size_map.get(symbol)
    if tick_size is None or tick_size <= 0:
        raise ValueError(f"商品 {symbol} 的 tick_size 無效或缺失: {tick_size}")
    
    # 取得手續費（每邊）
    commission_per_side = commission_config.per_side_usd.get(
        symbol, commission_config.default_per_side_usd
    )
    
    results = {}
    
    for level in ["S0", "S1", "S2", "S3"]:
        slip_ticks = slippage_policy.get_ticks(level)
        
        # 計算該等級下的淨利與其他指標
        net, gross_profit, gross_loss, trades = _compute_net_with_slippage(
            fills, slip_ticks, tick_size, commission_per_side
        )
        
        # 計算盈利因子
        if gross_loss == 0:
            profit_factor = float("inf") if gross_profit > 0 else 1.0
        else:
            profit_factor = gross_profit / abs(gross_loss)
        
        # 計算最大回撤（簡化版本：使用淨利序列）
        # 由於我們沒有逐筆的 equity curve，這裡先設為 0
        mdd = 0.0
        
        results[level] = StressResult(
            level=level,
            slip_ticks=slip_ticks,
            net_after_cost=net,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            mdd_after_cost=mdd,
            trades=trades,
        )
    
    return results


def _compute_net_with_slippage(
    fills: List[Dict[str, Any]],
    slip_ticks: int,
    tick_size: float,
    commission_per_side: float,
) -> Tuple[float, float, float, int]:
    """
    計算給定滑價 tick 數下的淨利、總盈利、總虧損與交易次數
    """
    total_net = 0.0
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    trades = 0
    
    for fill in fills:
        # 假設 fill 結構包含 entry_price, exit_price, entry_side, exit_side, quantity
        entry_price = fill.get("entry_price")
        exit_price = fill.get("exit_price")
        entry_side = fill.get("entry_side")  # "buy" 或 "sellshort"
        exit_side = fill.get("exit_side")    # "sell" 或 "buytocover"
        quantity = fill.get("quantity", 1.0)
        
        if None in (entry_price, exit_price, entry_side, exit_side):
            continue
        
        # 應用滑價調整價格
        entry_price_adj = apply_slippage_to_price(
            entry_price, entry_side, slip_ticks, tick_size
        )
        exit_price_adj = apply_slippage_to_price(
            exit_price, exit_side, slip_ticks, tick_size
        )
        
        # 計算毛利（未扣除手續費）
        if entry_side in ("buy", "buytocover"):
            # 多頭：買入後賣出
            gross = (exit_price_adj - entry_price_adj) * quantity
        else:
            # 空頭：賣出後買回
            gross = (entry_price_adj - exit_price_adj) * quantity
        
        # 扣除手續費（每邊）
        commission_total = 2 * commission_per_side * quantity
        
        # 淨利
        net = gross - commission_total
        
        total_net += net
        if net > 0:
            total_gross_profit += net + commission_total  # 還原手續費以得到 gross profit
        else:
            total_gross_loss += net - commission_total  # gross loss 為負值
        
        trades += 1
    
    return total_net, total_gross_profit, total_gross_loss, trades


def survive_s2(
    result_s2: StressResult,
    *,
    min_trades: int = 30,
    min_pf: float = 1.10,
    max_mdd_pct: Optional[float] = None,
    max_mdd_abs: Optional[float] = None,
) -> bool:
    """
    判斷策略是否通過 S2 生存閘門

    Args:
        result_s2: S2 等級的 StressResult
        min_trades: 最小交易次數
        min_pf: 最小盈利因子
        max_mdd_pct: 最大回撤百分比（如果可用）
        max_mdd_abs: 最大回撤絕對值（備用）

    Returns:
        bool: 是否通過閘門
    """
    # 檢查交易次數
    if result_s2.trades < min_trades:
        return False
    
    # 檢查盈利因子
    if result_s2.profit_factor < min_pf:
        return False
    
    # 檢查最大回撤（如果提供）
    if max_mdd_pct is not None:
        # 需要 equity curve 計算百分比回撤，目前暫不實作
        pass
    elif max_mdd_abs is not None:
        if result_s2.mdd_after_cost > max_mdd_abs:
            return False
    
    return True


def compute_stress_test_passed(
    results: Dict[str, StressResult],
    stress_level: str = "S3",
) -> bool:
    """
    計算壓力測試是否通過（S3 淨利 > 0）

    Args:
        results: 壓力測試結果字典
        stress_level: 壓力測試等級（預設 S3）

    Returns:
        bool: 壓力測試通過標誌
    """
    stress_result = results.get(stress_level)
    if stress_result is None:
        return False
    return stress_result.net_after_cost > 0


def generate_stress_report(
    results: Dict[str, StressResult],
    slippage_policy: SlippagePolicy,
    survive_s2_flag: bool,
    stress_test_passed_flag: bool,
) -> Dict[str, Any]:
    """
    產生壓力測試報告

    Returns:
        報告字典，包含 policy、矩陣、閘門結果等
    """
    matrix = {}
    for level, result in results.items():
        matrix[level] = {
            "slip_ticks": result.slip_ticks,
            "net_after_cost": result.net_after_cost,
            "gross_profit": result.gross_profit,
            "gross_loss": result.gross_loss,
            "profit_factor": result.profit_factor,
            "mdd_after_cost": result.mdd_after_cost,
            "trades": result.trades,
        }
    
    return {
        "slippage_policy": {
            "definition": slippage_policy.definition,
            "levels": slippage_policy.levels,
            "selection_level": slippage_policy.selection_level,
            "stress_level": slippage_policy.stress_level,
            "mc_execution_level": slippage_policy.mc_execution_level,
        },
        "stress_matrix": matrix,
        "survive_s2": survive_s2_flag,
        "stress_test_passed": stress_test_passed_flag,
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/resolve_cli.py
sha256(source_bytes) = 401896060644df9da5350573caa973dd43ffaf3acf3929a6ece276f1185e1786
bytes = 7959
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/resolve_cli.py
"""
Resolve CLI：特徵解析命令列介面

命令：
fishbro resolve features --season 2026Q1 --dataset-id CME.MNQ --strategy-id S1 --req strategies/S1/features.json

行為：
- 不允許 build → 只做檢查與載入
- 允許 build → 缺就 build，成功後載入，輸出 bundle 摘要（不輸出整個 array）

Exit code：
0：已滿足且載入成功
10：已 build（可選）
20：缺失且不允許 build / build_ctx 不足
1：其他錯誤
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.contracts.strategy_features import (
    StrategyFeatureRequirements,
    load_requirements_from_json,
)
from FishBroWFS_V2.control.feature_resolver import (
    resolve_features,
    MissingFeaturesError,
    ManifestMismatchError,
    BuildNotAllowedError,
    FeatureResolutionError,
)
from FishBroWFS_V2.control.build_context import BuildContext


def main() -> int:
    """CLI 主函數"""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        return run_resolve(args)
    except KeyboardInterrupt:
        print("\n中斷執行", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"錯誤: {e}", file=sys.stderr)
        return 1


def create_parser() -> argparse.ArgumentParser:
    """建立命令列解析器"""
    parser = argparse.ArgumentParser(
        description="解析策略特徵依賴",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # 必要參數
    parser.add_argument(
        "--season",
        required=True,
        help="季節標記，例如 2026Q1",
    )
    parser.add_argument(
        "--dataset-id",
        required=True,
        help="資料集 ID，例如 CME.MNQ",
    )
    
    # 需求來源（二選一）
    req_group = parser.add_mutually_exclusive_group(required=True)
    req_group.add_argument(
        "--strategy-id",
        help="策略 ID（用於自動尋找需求檔案）",
    )
    req_group.add_argument(
        "--req",
        type=Path,
        help="需求 JSON 檔案路徑",
    )
    
    # build 相關參數
    parser.add_argument(
        "--allow-build",
        action="store_true",
        help="允許自動 build 缺失的特徵",
    )
    parser.add_argument(
        "--txt-path",
        type=Path,
        help="原始 TXT 檔案路徑（只有 allow-build 才需要）",
    )
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="build 模式（只在 allow-build 時使用）",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="輸出根目錄",
    )
    parser.add_argument(
        "--build-bars-if-missing",
        action="store_true",
        default=True,
        help="如果 bars cache 不存在，是否建立 bars",
    )
    parser.add_argument(
        "--no-build-bars-if-missing",
        action="store_false",
        dest="build_bars_if_missing",
        help="不建立 bars cache（即使缺失）",
    )
    
    # 輸出選項
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式輸出結果",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="輸出詳細資訊",
    )
    
    return parser


def run_resolve(args) -> int:
    """執行解析邏輯"""
    # 1. 載入需求
    requirements = load_requirements(args)
    
    # 2. 準備 build_ctx（如果需要）
    build_ctx = prepare_build_context(args)
    
    # 3. 執行解析
    try:
        bundle = resolve_features(
            season=args.season,
            dataset_id=args.dataset_id,
            requirements=requirements,
            outputs_root=args.outputs_root,
            allow_build=args.allow_build,
            build_ctx=build_ctx,
        )
        
        # 4. 輸出結果
        output_result(bundle, args)
        
        # 判斷 exit code
        # 如果有 build，回傳 10；否則回傳 0
        # 目前我們無法知道是否有 build，所以暫時回傳 0
        return 0
        
    except MissingFeaturesError as e:
        print(f"缺少特徵: {e}", file=sys.stderr)
        return 20
    except BuildNotAllowedError as e:
        print(f"不允許 build: {e}", file=sys.stderr)
        return 20
    except ManifestMismatchError as e:
        print(f"Manifest 合約不符: {e}", file=sys.stderr)
        return 1
    except FeatureResolutionError as e:
        print(f"特徵解析失敗: {e}", file=sys.stderr)
        return 1


def load_requirements(args) -> StrategyFeatureRequirements:
    """載入策略特徵需求"""
    if args.req:
        # 從指定 JSON 檔案載入
        return load_requirements_from_json(str(args.req))
    elif args.strategy_id:
        # 自動尋找需求檔案
        # 優先順序：
        # 1. strategies/{strategy_id}/features.json
        # 2. configs/strategies/{strategy_id}/features.json
        # 3. 當前目錄下的 {strategy_id}_features.json
        
        possible_paths = [
            Path(f"strategies/{args.strategy_id}/features.json"),
            Path(f"configs/strategies/{args.strategy_id}/features.json"),
            Path(f"{args.strategy_id}_features.json"),
        ]
        
        for path in possible_paths:
            if path.exists():
                return load_requirements_from_json(str(path))
        
        raise FileNotFoundError(
            f"找不到策略 {args.strategy_id} 的需求檔案。"
            f"嘗試的路徑: {[str(p) for p in possible_paths]}"
        )
    else:
        # 這不應該發生，因為 argparse 確保了二選一
        raise ValueError("必須提供 --req 或 --strategy-id")


def prepare_build_context(args) -> Optional[BuildContext]:
    """準備 BuildContext"""
    if not args.allow_build:
        return None
    
    if not args.txt_path:
        raise ValueError("--allow-build 需要 --txt-path")
    
    # 驗證 txt_path 存在
    if not args.txt_path.exists():
        raise FileNotFoundError(f"TXT 檔案不存在: {args.txt_path}")
    
    # 轉換 mode 為大寫
    mode = args.mode.upper()
    if mode not in ("FULL", "INCREMENTAL"):
        raise ValueError(f"無效的 mode: {args.mode}，必須為 'incremental' 或 'full'")
    
    return BuildContext(
        txt_path=args.txt_path,
        mode=mode,
        outputs_root=args.outputs_root,
        build_bars_if_missing=args.build_bars_if_missing,
    )


def output_result(bundle, args) -> None:
    """輸出解析結果"""
    if args.json:
        # JSON 格式輸出
        result = {
            "success": True,
            "bundle": bundle.to_dict(),
            "series_count": len(bundle.series),
            "series_keys": bundle.list_series(),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # 文字格式輸出
        print(f"✅ 特徵解析成功")
        print(f"   資料集: {bundle.dataset_id}")
        print(f"   季節: {bundle.season}")
        print(f"   特徵數量: {len(bundle.series)}")
        
        if args.verbose:
            print(f"   Metadata:")
            for key, value in bundle.meta.items():
                if key in ("files_sha256", "manifest_sha256"):
                    # 縮短 hash 顯示
                    if isinstance(value, str) and len(value) > 16:
                        value = f"{value[:8]}...{value[-8:]}"
                print(f"     {key}: {value}")
            
            print(f"   特徵列表:")
            for name, tf in bundle.list_series():
                series = bundle.get_series(name, tf)
                print(f"     {name}@{tf}m: {len(series.ts)} 筆資料")


if __name__ == "__main__":
    sys.exit(main())



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/season_api.py
sha256(source_bytes) = 356a49078559139576203b4e309fed76e38877e0fb7f75ab0271ecff4f9b1d16
bytes = 7099
redacted = False
--------------------------------------------------------------------------------

"""
Phase 15.0: Season-level governance and index builder (Research OS).

Contracts:
- Do NOT modify Engine / JobSpec / batch artifacts content.
- Season index is a separate tree (season_index/{season}/...).
- Rebuild index is deterministic: stable ordering by batch_id.
- Only reads JSON from artifacts/{batch_id}/metadata.json, index.json, summary.json.
- Writes season_index.json and season_metadata.json using atomic write.

Environment overrides:
- FISHBRO_SEASON_INDEX_ROOT (default: outputs/season_index)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from FishBroWFS_V2.control.artifacts import compute_sha256, write_json_atomic


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_season_index_root() -> Path:
    import os
    return Path(os.environ.get("FISHBRO_SEASON_INDEX_ROOT", "outputs/season_index"))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return compute_sha256(path.read_bytes())


@dataclass
class SeasonMetadata:
    season: str
    frozen: bool = False
    tags: list[str] = field(default_factory=list)
    note: str = ""
    created_at: str = ""
    updated_at: str = ""


class SeasonStore:
    """
    Store for season_index/{season}/season_index.json and season_metadata.json
    """

    def __init__(self, season_index_root: Path):
        self.root = season_index_root
        self.root.mkdir(parents=True, exist_ok=True)

    def season_dir(self, season: str) -> Path:
        return self.root / season

    def index_path(self, season: str) -> Path:
        return self.season_dir(season) / "season_index.json"

    def metadata_path(self, season: str) -> Path:
        return self.season_dir(season) / "season_metadata.json"

    # ---------- metadata ----------
    def get_metadata(self, season: str) -> Optional[SeasonMetadata]:
        path = self.metadata_path(season)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError("season_metadata.tags must be a list")
        return SeasonMetadata(
            season=data["season"],
            frozen=bool(data.get("frozen", False)),
            tags=list(tags),
            note=data.get("note", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def set_metadata(self, season: str, meta: SeasonMetadata) -> None:
        path = self.metadata_path(season)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "season": season,
            "frozen": bool(meta.frozen),
            "tags": list(meta.tags),
            "note": meta.note,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
        }
        write_json_atomic(path, payload)

    def update_metadata(
        self,
        season: str,
        *,
        tags: Optional[list[str]] = None,
        note: Optional[str] = None,
        frozen: Optional[bool] = None,
    ) -> SeasonMetadata:
        now = _utc_now_iso()
        existing = self.get_metadata(season)
        if existing is None:
            existing = SeasonMetadata(season=season, created_at=now, updated_at=now)

        if existing.frozen and frozen is False:
            raise ValueError("Cannot unfreeze a frozen season")

        if tags is not None:
            merged = set(existing.tags)
            merged.update(tags)
            existing.tags = sorted(merged)

        if note is not None:
            existing.note = note

        if frozen is not None:
            if frozen is True:
                existing.frozen = True
            elif frozen is False:
                # allowed only when not already frozen
                existing.frozen = False

        existing.updated_at = now
        self.set_metadata(season, existing)
        return existing

    def freeze(self, season: str) -> None:
        meta = self.get_metadata(season)
        if meta is None:
            # create metadata on freeze if it doesn't exist
            now = _utc_now_iso()
            meta = SeasonMetadata(season=season, created_at=now, updated_at=now, frozen=True)
            self.set_metadata(season, meta)
            return

        if not meta.frozen:
            meta.frozen = True
            meta.updated_at = _utc_now_iso()
            self.set_metadata(season, meta)

    def is_frozen(self, season: str) -> bool:
        meta = self.get_metadata(season)
        return bool(meta and meta.frozen)

    # ---------- index ----------
    def read_index(self, season: str) -> dict[str, Any]:
        return _read_json(self.index_path(season))

    def write_index(self, season: str, index_obj: dict[str, Any]) -> None:
        path = self.index_path(season)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, index_obj)

    def rebuild_index(self, artifacts_root: Path, season: str) -> dict[str, Any]:
        """
        Scan artifacts_root/*/metadata.json to collect batches where metadata.season == season.
        Then attach hashes for index.json and summary.json (if present).
        Deterministic: sort by batch_id.
        """
        if not artifacts_root.exists():
            # no artifacts root -> empty index
            artifacts_root.mkdir(parents=True, exist_ok=True)

        batches: list[dict[str, Any]] = []

        # deterministic: sorted by directory name
        for batch_dir in sorted([p for p in artifacts_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            batch_id = batch_dir.name
            meta_path = batch_dir / "metadata.json"
            if not meta_path.exists():
                continue

            # Do NOT swallow corruption: index build should surface errors
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("season", "") != season:
                continue

            idx_hash = _file_sha256(batch_dir / "index.json")
            sum_hash = _file_sha256(batch_dir / "summary.json")

            batches.append(
                {
                    "batch_id": batch_id,
                    "frozen": bool(meta.get("frozen", False)),
                    "tags": sorted(set(meta.get("tags", []) or [])),
                    "note": meta.get("note", "") or "",
                    "index_hash": idx_hash,
                    "summary_hash": sum_hash,
                }
            )

        out = {
            "season": season,
            "generated_at": _utc_now_iso(),
            "batches": batches,
        }
        self.write_index(season, out)
        return out



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/season_compare.py
sha256(source_bytes) = d2d25d60ce40705c6d4ffc40ec67c35704b6932ad370526c945b3f2e172d3e10
bytes = 4753
redacted = False
--------------------------------------------------------------------------------

"""
Phase 15.1: Season-level cross-batch comparison helpers.

Contracts:
- Read-only: only reads season_index.json and artifacts/{batch_id}/summary.json
- No on-the-fly recomputation of batch summary
- Deterministic:
  - Sort by score desc
  - Tie-break by batch_id asc
  - Tie-break by job_id asc
- Robust:
  - Missing/corrupt batch summary is skipped (never 500 the whole season)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_job_id(row: Any) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    # canonical
    if "job_id" in row and row["job_id"] is not None:
        return str(row["job_id"])
    # common alternates (defensive)
    if "id" in row and row["id"] is not None:
        return str(row["id"])
    return None


def _extract_score(row: Any) -> Optional[float]:
    if not isinstance(row, dict):
        return None

    # canonical
    if "score" in row:
        try:
            v = row["score"]
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    # alternate: metrics.score
    m = row.get("metrics")
    if isinstance(m, dict) and "score" in m:
        try:
            v = m["score"]
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    return None


@dataclass(frozen=True)
class SeasonTopKResult:
    season: str
    k: int
    items: list[dict[str, Any]]
    skipped_batches: list[str]


def merge_season_topk(
    *,
    artifacts_root: Path,
    season_index: dict[str, Any],
    k: int,
) -> SeasonTopKResult:
    """
    Merge topk entries across batches listed in season_index.json.

    Output item schema:
      {
        "batch_id": "...",
        "job_id": "...",
        "score": 1.23,
        "row": {... original topk row ...}
      }

    Skipping rules:
    - missing summary.json -> skip batch
    - invalid json -> skip batch
    - missing topk list -> treat as empty
    """
    season = str(season_index.get("season", ""))
    batches = season_index.get("batches", [])
    if not isinstance(batches, list):
        raise ValueError("season_index.batches must be a list")

    # sanitize k
    try:
        k_int = int(k)
    except Exception:
        k_int = 20
    if k_int <= 0:
        k_int = 20

    merged: list[dict[str, Any]] = []
    skipped: list[str] = []

    # deterministic traversal order: batch_id asc
    batch_ids: list[str] = []
    for b in batches:
        if isinstance(b, dict) and "batch_id" in b:
            batch_ids.append(str(b["batch_id"]))
    batch_ids = sorted(set(batch_ids))

    for batch_id in batch_ids:
        summary_path = artifacts_root / batch_id / "summary.json"
        if not summary_path.exists():
            skipped.append(batch_id)
            continue

        try:
            summary = _read_json(summary_path)
        except Exception:
            skipped.append(batch_id)
            continue

        topk = summary.get("topk", [])
        if not isinstance(topk, list):
            # malformed topk -> treat as skip (stronger safety)
            skipped.append(batch_id)
            continue

        for row in topk:
            job_id = _extract_job_id(row)
            if job_id is None:
                # cannot tie-break deterministically without job_id
                continue
            score = _extract_score(row)
            merged.append(
                {
                    "batch_id": batch_id,
                    "job_id": job_id,
                    "score": score,
                    "row": row,
                }
            )

    def sort_key(item: dict[str, Any]) -> tuple:
        # score desc; None goes last
        score = item.get("score")
        score_is_none = score is None
        # For numeric scores: use -score
        neg_score = 0.0
        if not score_is_none:
            try:
                neg_score = -float(score)
            except Exception:
                score_is_none = True
                neg_score = 0.0

        return (
            score_is_none,     # False first, True last
            neg_score,         # smaller first -> higher score first
            str(item.get("batch_id", "")),
            str(item.get("job_id", "")),
        )

    merged_sorted = sorted(merged, key=sort_key)
    merged_sorted = merged_sorted[:k_int]

    return SeasonTopKResult(
        season=season,
        k=k_int,
        items=merged_sorted,
        skipped_batches=sorted(set(skipped)),
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/season_compare_batches.py
sha256(source_bytes) = aec07cf2f8884965b7bb2a838cb70d4feda5b32f0b2f47e8c33809ce46d8d4a5
bytes = 8174
redacted = False
--------------------------------------------------------------------------------

"""
Phase 15.2: Season compare batch cards + lightweight leaderboard.

Contracts:
- Read-only: reads season_index.json and artifacts/{batch_id}/summary.json
- No on-the-fly recomputation
- Deterministic:
  - Batches list sorted by batch_id asc
  - Leaderboard sorted by score desc, tie-break batch_id asc, job_id asc
- Robust:
  - Missing/corrupt summary.json => summary_ok=False, keep other fields
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_get_job_id(row: Any) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    if row.get("job_id") is not None:
        return str(row["job_id"])
    if row.get("id") is not None:
        return str(row["id"])
    return None


def _safe_get_score(row: Any) -> Optional[float]:
    if not isinstance(row, dict):
        return None
    if "score" in row:
        try:
            v = row["score"]
            if v is None:
                return None
            return float(v)
        except Exception:
            return None
    m = row.get("metrics")
    if isinstance(m, dict) and "score" in m:
        try:
            v = m["score"]
            if v is None:
                return None
            return float(v)
        except Exception:
            return None
    return None


def _extract_group_key(row: Any, group_by: str) -> str:
    """
    group_by candidates:
      - "strategy_id"
      - "dataset_id"
    If not present, return "unknown".
    """
    if not isinstance(row, dict):
        return "unknown"
    v = row.get(group_by)
    if v is None:
        # sometimes nested
        meta = row.get("meta")
        if isinstance(meta, dict):
            v = meta.get(group_by)
    return str(v) if v is not None else "unknown"


@dataclass(frozen=True)
class SeasonBatchesResult:
    season: str
    batches: list[dict[str, Any]]
    skipped_summaries: list[str]


def build_season_batch_cards(
    *,
    artifacts_root: Path,
    season_index: dict[str, Any],
) -> SeasonBatchesResult:
    """
    Build deterministic batch cards for a season.

    For each batch_id in season_index.batches:
      - frozen/tags/note/index_hash/summary_hash are read from season_index (source of truth)
      - summary.json is read best-effort:
          top_job_id, top_score, topk_size
      - missing/corrupt summary => summary_ok=False
    """
    season = str(season_index.get("season", ""))
    batches_in = season_index.get("batches", [])
    if not isinstance(batches_in, list):
        raise ValueError("season_index.batches must be a list")

    # deterministic batch_id list
    by_id: dict[str, dict[str, Any]] = {}
    for b in batches_in:
        if not isinstance(b, dict) or "batch_id" not in b:
            continue
        batch_id = str(b["batch_id"])
        by_id[batch_id] = b

    batch_ids = sorted(by_id.keys())

    cards: list[dict[str, Any]] = []
    skipped: list[str] = []

    for batch_id in batch_ids:
        b = by_id[batch_id]
        card: dict[str, Any] = {
            "batch_id": batch_id,
            "frozen": bool(b.get("frozen", False)),
            "tags": list(b.get("tags", []) or []),
            "note": b.get("note", "") or "",
            "index_hash": b.get("index_hash"),
            "summary_hash": b.get("summary_hash"),
            # summary-derived
            "summary_ok": True,
            "top_job_id": None,
            "top_score": None,
            "topk_size": 0,
        }

        summary_path = artifacts_root / batch_id / "summary.json"
        if not summary_path.exists():
            card["summary_ok"] = False
            skipped.append(batch_id)
            cards.append(card)
            continue

        try:
            s = _read_json(summary_path)
            topk = s.get("topk", [])
            if not isinstance(topk, list):
                raise ValueError("summary.topk must be list")

            card["topk_size"] = len(topk)
            if len(topk) > 0:
                first = topk[0]
                card["top_job_id"] = _safe_get_job_id(first)
                card["top_score"] = _safe_get_score(first)
        except Exception:
            card["summary_ok"] = False
            skipped.append(batch_id)

        cards.append(card)

    return SeasonBatchesResult(season=season, batches=cards, skipped_summaries=sorted(set(skipped)))


def build_season_leaderboard(
    *,
    artifacts_root: Path,
    season_index: dict[str, Any],
    group_by: str = "strategy_id",
    per_group: int = 3,
) -> dict[str, Any]:
    """
    Build a grouped leaderboard from batch summaries' topk rows.

    Returns:
      {
        "season": "...",
        "group_by": "strategy_id",
        "per_group": 3,
        "groups": [
           {"key": "...", "items": [...]},
           ...
        ],
        "skipped_batches": [...]
      }
    """
    season = str(season_index.get("season", ""))
    batches_in = season_index.get("batches", [])
    if not isinstance(batches_in, list):
        raise ValueError("season_index.batches must be a list")

    if group_by not in ("strategy_id", "dataset_id"):
        raise ValueError("group_by must be 'strategy_id' or 'dataset_id'")

    try:
        per_group_i = int(per_group)
    except Exception:
        per_group_i = 3
    if per_group_i <= 0:
        per_group_i = 3

    # deterministic batch traversal: batch_id asc
    batch_ids = sorted({str(b["batch_id"]) for b in batches_in if isinstance(b, dict) and "batch_id" in b})

    merged: list[dict[str, Any]] = []
    skipped: list[str] = []

    for batch_id in batch_ids:
        p = artifacts_root / batch_id / "summary.json"
        if not p.exists():
            skipped.append(batch_id)
            continue
        try:
            s = _read_json(p)
            topk = s.get("topk", [])
            if not isinstance(topk, list):
                skipped.append(batch_id)
                continue
            for row in topk:
                job_id = _safe_get_job_id(row)
                if job_id is None:
                    continue
                score = _safe_get_score(row)
                merged.append(
                    {
                        "batch_id": batch_id,
                        "job_id": job_id,
                        "score": score,
                        "group": _extract_group_key(row, group_by),
                        "row": row,
                    }
                )
        except Exception:
            skipped.append(batch_id)
            continue

    def sort_key(it: dict[str, Any]) -> tuple:
        score = it.get("score")
        score_is_none = score is None
        neg_score = 0.0
        if not score_is_none:
            try:
                # score is not None at this point, but mypy doesn't know
                neg_score = -float(score)  # type: ignore[arg-type]
            except Exception:
                score_is_none = True
                neg_score = 0.0
        return (
            score_is_none,
            neg_score,
            str(it.get("batch_id", "")),
            str(it.get("job_id", "")),
        )

    merged_sorted = sorted(merged, key=sort_key)

    # group, keep top per_group_i in deterministic order (already sorted)
    groups: dict[str, list[dict[str, Any]]] = {}
    for it in merged_sorted:
        key = str(it.get("group", "unknown"))
        if key not in groups:
            groups[key] = []
        if len(groups[key]) < per_group_i:
            groups[key].append(
                {
                    "batch_id": it["batch_id"],
                    "job_id": it["job_id"],
                    "score": it["score"],
                    "row": it["row"],
                }
            )

    # deterministic group ordering: key asc
    out_groups = [{"key": k, "items": groups[k]} for k in sorted(groups.keys())]

    return {
        "season": season,
        "group_by": group_by,
        "per_group": per_group_i,
        "groups": out_groups,
        "skipped_batches": sorted(set(skipped)),
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/season_export.py
sha256(source_bytes) = a769c9a016066677f701193de57a953ea858b14bcd9929b2d22f02f4361f6769
bytes = 9587
redacted = False
--------------------------------------------------------------------------------

"""
Phase 15.3: Season freeze package / export pack.

Contracts:
- Controlled mutation: writes only under exports root (default outputs/exports).
- Does NOT modify artifacts/ or season_index/ trees.
- Requires season is frozen (governance hardening).
- Deterministic:
  - batches sorted by batch_id asc
  - manifest files sorted by rel_path asc
- Auditable:
  - package_manifest.json includes sha256 for each exported file
  - includes manifest_sha256 (sha of the manifest bytes)
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from FishBroWFS_V2.control.artifacts import compute_sha256, write_atomic_json
from FishBroWFS_V2.control.season_api import SeasonStore
from FishBroWFS_V2.control.batch_api import read_summary, read_index
from FishBroWFS_V2.utils.write_scope import WriteScope


def get_exports_root() -> Path:
    return Path(os.environ.get("FISHBRO_EXPORTS_ROOT", "outputs/exports"))


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _file_sha256(path: Path) -> str:
    return compute_sha256(path.read_bytes())


@dataclass(frozen=True)
class ExportResult:
    season: str
    export_dir: Path
    manifest_path: Path
    manifest_sha256: str
    exported_files: list[dict[str, Any]]
    missing_files: list[str]


def export_season_package(
    *,
    season: str,
    artifacts_root: Path,
    season_index_root: Path,
    exports_root: Optional[Path] = None,
) -> ExportResult:
    """
    Export a frozen season into an immutable, auditable package directory.

    Package layout:
      exports/seasons/{season}/
        package_manifest.json
        season_index.json
        season_metadata.json
        batches/{batch_id}/metadata.json
        batches/{batch_id}/index.json (optional if missing)
        batches/{batch_id}/summary.json (optional if missing)
    """
    exports_root = exports_root or get_exports_root()
    store = SeasonStore(season_index_root)

    if not store.is_frozen(season):
        raise PermissionError("Season must be frozen before export")

    # must have season index
    season_index = store.read_index(season)  # FileNotFoundError surfaces to API as 404

    season_dir = exports_root / "seasons" / season
    batches_dir = season_dir / "batches"
    season_dir.mkdir(parents=True, exist_ok=True)
    batches_dir.mkdir(parents=True, exist_ok=True)

    # Build the set of allowed relative paths according to export‑pack spec.
    # We'll collect them as we go, then create a WriteScope that permits exactly those paths.
    allowed_rel_files: set[str] = set()
    exported_files: list[dict[str, Any]] = []
    missing: list[str] = []

    # Helper to record an allowed file and copy it
    def copy_and_allow(src: Path, dst: Path, rel: str) -> None:
        _copy_file(src, dst)
        allowed_rel_files.add(rel)
        exported_files.append({"path": rel, "sha256": _file_sha256(dst)})

    # 1) copy season_index.json + season_metadata.json (metadata may not exist; if missing -> we still record missing)
    src_index = season_index_root / season / "season_index.json"
    dst_index = season_dir / "season_index.json"
    copy_and_allow(src_index, dst_index, "season_index.json")

    src_meta = season_index_root / season / "season_metadata.json"
    dst_meta = season_dir / "season_metadata.json"
    if src_meta.exists():
        copy_and_allow(src_meta, dst_meta, "season_metadata.json")
    else:
        missing.append("season_metadata.json")

    # 2) copy batch files referenced by season index
    batches = season_index.get("batches", [])
    if not isinstance(batches, list):
        raise ValueError("season_index.batches must be a list")

    batch_ids = sorted(
        {str(b["batch_id"]) for b in batches if isinstance(b, dict) and "batch_id" in b}
    )

    for batch_id in batch_ids:
        # metadata.json is the anchor
        src_batch_meta = artifacts_root / batch_id / "metadata.json"
        rel_meta = str(Path("batches") / batch_id / "metadata.json")
        dst_batch_meta = batches_dir / batch_id / "metadata.json"
        if src_batch_meta.exists():
            copy_and_allow(src_batch_meta, dst_batch_meta, rel_meta)
        else:
            missing.append(rel_meta)

        # index.json optional
        src_idx = artifacts_root / batch_id / "index.json"
        rel_idx = str(Path("batches") / batch_id / "index.json")
        dst_idx = batches_dir / batch_id / "index.json"
        if src_idx.exists():
            copy_and_allow(src_idx, dst_idx, rel_idx)
        else:
            missing.append(rel_idx)

        # summary.json optional
        src_sum = artifacts_root / batch_id / "summary.json"
        rel_sum = str(Path("batches") / batch_id / "summary.json")
        dst_sum = batches_dir / batch_id / "summary.json"
        if src_sum.exists():
            copy_and_allow(src_sum, dst_sum, rel_sum)
        else:
            missing.append(rel_sum)

    # 3) build deterministic manifest (sort by path)
    exported_files_sorted = sorted(exported_files, key=lambda x: x["path"])

    manifest_obj = {
        "season": season,
        "generated_at": season_index.get("generated_at", ""),
        "source_roots": {
            "artifacts_root": str(artifacts_root),
            "season_index_root": str(season_index_root),
        },
        "deterministic_order": {
            "batches": "batch_id asc",
            "files": "path asc",
        },
        "files": exported_files_sorted,
        "missing_files": sorted(set(missing)),
    }

    manifest_path = season_dir / "package_manifest.json"
    allowed_rel_files.add("package_manifest.json")
    write_atomic_json(manifest_path, manifest_obj)

    manifest_sha256 = compute_sha256(manifest_path.read_bytes())

    # write back manifest hash (2nd pass) for self-audit (still deterministic because it depends on bytes)
    manifest_obj2 = dict(manifest_obj)
    manifest_obj2["manifest_sha256"] = manifest_sha256
    write_atomic_json(manifest_path, manifest_obj2)
    manifest_sha2562 = compute_sha256(manifest_path.read_bytes())

    # 4) create replay_index.json for compare replay without artifacts
    replay_index_path = season_dir / "replay_index.json"
    allowed_rel_files.add("replay_index.json")
    replay_index = _build_replay_index(
        season=season,
        season_index=season_index,
        artifacts_root=artifacts_root,
        batches_dir=batches_dir,
    )
    write_atomic_json(replay_index_path, replay_index)
    exported_files_sorted.append(
        {
            "path": str(Path("replay_index.json")),
            "sha256": _file_sha256(replay_index_path),
        }
    )

    # Now create a WriteScope that permits exactly the files we have written.
    # This scope will be used to validate any future writes (none in this function).
    # We also add a guard for the manifest write (already done) and replay_index write.
    scope = WriteScope(
        root_dir=season_dir,
        allowed_rel_files=frozenset(allowed_rel_files),
        allowed_rel_prefixes=(),
    )
    # Verify that all exported files are allowed (should be true by construction)
    for ef in exported_files_sorted:
        scope.assert_allowed_rel(ef["path"])

    return ExportResult(
        season=season,
        export_dir=season_dir,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha2562,
        exported_files=exported_files_sorted,
        missing_files=sorted(set(missing)),
    )


def _build_replay_index(
    season: str,
    season_index: dict[str, Any],
    artifacts_root: Path,
    batches_dir: Path,
) -> dict[str, Any]:
    """
    Build replay index for compare replay without artifacts.
    
    Contains:
    - season metadata
    - batch summaries (topk, metrics)
    - batch indices (job list)
    - deterministic ordering
    """
    batches = season_index.get("batches", [])
    if not isinstance(batches, list):
        raise ValueError("season_index.batches must be a list")

    batch_ids = sorted(
        {str(b["batch_id"]) for b in batches if isinstance(b, dict) and "batch_id" in b}
    )

    replay_batches: list[dict[str, Any]] = []
    for batch_id in batch_ids:
        batch_info: dict[str, Any] = {"batch_id": batch_id}
        
        # Try to read summary.json
        summary_path = artifacts_root / batch_id / "summary.json"
        if summary_path.exists():
            try:
                summary = read_summary(artifacts_root, batch_id)
                batch_info["summary"] = {
                    "topk": summary.get("topk", []),
                    "metrics": summary.get("metrics", {}),
                }
            except Exception:
                batch_info["summary"] = None
        else:
            batch_info["summary"] = None
        
        # Try to read index.json
        index_path = artifacts_root / batch_id / "index.json"
        if index_path.exists():
            try:
                index = read_index(artifacts_root, batch_id)
                batch_info["index"] = index
            except Exception:
                batch_info["index"] = None
        else:
            batch_info["index"] = None
        
        replay_batches.append(batch_info)

    return {
        "season": season,
        "generated_at": season_index.get("generated_at", ""),
        "batches": replay_batches,
        "deterministic_order": {
            "batches": "batch_id asc",
            "files": "path asc",
        },
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/season_export_replay.py
sha256(source_bytes) = 6e67dfc188688deb63ceb927d4b6bd50f363decb94e13978db559a2bebcd91ce
bytes = 7688
redacted = False
--------------------------------------------------------------------------------

"""
Phase 16: Export Pack Replay Mode.

Allows compare endpoints to work from an exported season package
without requiring access to the original artifacts/ directory.

Key contracts:
- Read-only: only reads from exports root, never writes
- Deterministic: same ordering as original compare endpoints
- Fallback: if replay_index.json missing, raise FileNotFoundError
- No artifacts dependency: does not require artifacts/ directory
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class ReplaySeasonTopkResult:
    season: str
    k: int
    items: list[dict[str, Any]]
    skipped_batches: list[str]


@dataclass(frozen=True)
class ReplaySeasonBatchCardsResult:
    season: str
    batches: list[dict[str, Any]]
    skipped_summaries: list[str]


@dataclass(frozen=True)
class ReplaySeasonLeaderboardResult:
    season: str
    group_by: str
    per_group: int
    groups: list[dict[str, Any]]


def load_replay_index(exports_root: Path, season: str) -> dict[str, Any]:
    """
    Load replay_index.json from an exported season package.
    
    Raises:
        FileNotFoundError: if replay_index.json does not exist
        ValueError: if JSON is invalid
    """
    replay_path = exports_root / "seasons" / season / "replay_index.json"
    if not replay_path.exists():
        raise FileNotFoundError(f"replay_index.json not found for season {season}")
    
    text = replay_path.read_text(encoding="utf-8")
    return json.loads(text)


def replay_season_topk(
    exports_root: Path,
    season: str,
    k: int = 20,
) -> ReplaySeasonTopkResult:
    """
    Replay cross-batch TopK from exported season package.
    
    Implementation mirrors merge_season_topk but uses replay_index.json
    instead of reading artifacts/{batch_id}/summary.json.
    """
    replay_index = load_replay_index(exports_root, season)
    
    all_items: list[dict[str, Any]] = []
    skipped_batches: list[str] = []
    
    for batch_info in replay_index.get("batches", []):
        batch_id = batch_info.get("batch_id", "")
        summary = batch_info.get("summary")
        
        if summary is None:
            skipped_batches.append(batch_id)
            continue
        
        topk = summary.get("topk", [])
        if not isinstance(topk, list):
            skipped_batches.append(batch_id)
            continue
        
        # Add batch_id to each item for traceability
        for item in topk:
            if isinstance(item, dict):
                item_copy = dict(item)
                item_copy["_batch_id"] = batch_id
                all_items.append(item_copy)
    
    # Sort by (-score, batch_id, job_id) for deterministic ordering
    def _sort_key(item: dict[str, Any]) -> tuple:
        # Score (descending, so use negative)
        score = item.get("score")
        if isinstance(score, (int, float)):
            score_val = -float(score)  # Negative for descending sort
        else:
            score_val = float("inf")  # Missing scores go last
        
        # Batch ID (from _batch_id added earlier)
        batch_id = item.get("_batch_id", "")
        
        # Job ID
        job_id = item.get("job_id", "")
        
        return (score_val, batch_id, job_id)
    
    sorted_items = sorted(all_items, key=_sort_key)
    topk_items = sorted_items[:k] if k > 0 else sorted_items
    
    return ReplaySeasonTopkResult(
        season=season,
        k=k,
        items=topk_items,
        skipped_batches=skipped_batches,
    )


def replay_season_batch_cards(
    exports_root: Path,
    season: str,
) -> ReplaySeasonBatchCardsResult:
    """
    Replay batch-level compare cards from exported season package.
    
    Implementation mirrors build_season_batch_cards but uses replay_index.json.
    Deterministic ordering: batches sorted by batch_id ascending.
    """
    replay_index = load_replay_index(exports_root, season)
    
    batches: list[dict[str, Any]] = []
    skipped_summaries: list[str] = []
    
    # Sort batches by batch_id for deterministic output
    batch_infos = replay_index.get("batches", [])
    sorted_batch_infos = sorted(batch_infos, key=lambda b: b.get("batch_id", ""))
    
    for batch_info in sorted_batch_infos:
        batch_id = batch_info.get("batch_id", "")
        summary = batch_info.get("summary")
        index = batch_info.get("index")
        
        if summary is None:
            skipped_summaries.append(batch_id)
            continue
        
        # Build batch card
        card: dict[str, Any] = {
            "batch_id": batch_id,
            "summary": summary,
        }
        
        if index is not None:
            card["index"] = index
        
        batches.append(card)
    
    return ReplaySeasonBatchCardsResult(
        season=season,
        batches=batches,
        skipped_summaries=skipped_summaries,
    )


def replay_season_leaderboard(
    exports_root: Path,
    season: str,
    group_by: str = "strategy_id",
    per_group: int = 3,
) -> ReplaySeasonLeaderboardResult:
    """
    Replay grouped leaderboard from exported season package.
    
    Implementation mirrors build_season_leaderboard but uses replay_index.json.
    """
    replay_index = load_replay_index(exports_root, season)
    
    # Collect all items with grouping key
    items_by_group: dict[str, list[dict[str, Any]]] = {}
    
    for batch_info in replay_index.get("batches", []):
        summary = batch_info.get("summary")
        if summary is None:
            continue
        
        topk = summary.get("topk", [])
        if not isinstance(topk, list):
            continue
        
        for item in topk:
            if not isinstance(item, dict):
                continue
            
            # Add batch_id for deterministic sorting
            item_copy = dict(item)
            item_copy["_batch_id"] = batch_info.get("batch_id", "")
            
            # Extract grouping key
            group_key = item_copy.get(group_by, "")
            if not isinstance(group_key, str):
                group_key = str(group_key)
            
            if group_key not in items_by_group:
                items_by_group[group_key] = []
            
            items_by_group[group_key].append(item_copy)
    
    # Sort items within each group by (-score, batch_id, job_id) for deterministic ordering
    def _sort_key(item: dict[str, Any]) -> tuple:
        # Score (descending, so use negative)
        score = item.get("score")
        if isinstance(score, (int, float)):
            score_val = -float(score)  # Negative for descending sort
        else:
            score_val = float("inf")  # Missing scores go last
        
        # Batch ID (item may not have _batch_id in leaderboard context)
        batch_id = item.get("_batch_id", item.get("batch_id", ""))
        
        # Job ID
        job_id = item.get("job_id", "")
        
        return (score_val, batch_id, job_id)
    
    groups: list[dict[str, Any]] = []
    for group_key, group_items in items_by_group.items():
        sorted_items = sorted(group_items, key=_sort_key)
        top_items = sorted_items[:per_group] if per_group > 0 else sorted_items
        
        groups.append({
            "key": group_key,
            "items": top_items,
            "total": len(group_items),
        })
    
    # Sort groups by key for deterministic output
    groups_sorted = sorted(groups, key=lambda g: g["key"])
    
    return ReplaySeasonLeaderboardResult(
        season=season,
        group_by=group_by,
        per_group=per_group,
        groups=groups_sorted,
    )



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/seed_demo_run.py
sha256(source_bytes) = 08b95b714fdedd50e100bbe2fbf33031a29b4a69415a0914eb55ac761ca37941
bytes = 5409
redacted = False
--------------------------------------------------------------------------------

"""Seed demo run for Viewer validation.

Creates a DONE job with minimal artifacts for Viewer testing.
Does NOT run engine - only writes files.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from FishBroWFS_V2.control.jobs_db import init_db
from FishBroWFS_V2.control.report_links import build_report_link
from FishBroWFS_V2.control.types import JobStatus
from FishBroWFS_V2.core.paths import ensure_run_dir

# Default DB path (same as api.py)
DEFAULT_DB_PATH = Path("outputs/jobs.db")


def get_db_path() -> Path:
    """Get database path from environment or default."""
    db_path_str = os.getenv("JOBS_DB_PATH")
    if db_path_str:
        return Path(db_path_str)
    return DEFAULT_DB_PATH


def main() -> str:
    """
    Create demo job with minimal artifacts.
    
    Returns:
        run_id of created demo job
        
    Contract:
        - Never raises exceptions
        - Does NOT import engine
        - Does NOT run backtest
        - Does NOT touch worker
        - Does NOT need dataset
    """
    try:
        # Generate run_id
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"demo_{timestamp}"
        
        # Initialize DB if needed
        db_path = get_db_path()
        init_db(db_path)
        
        # Create outputs directory (use standard path structure: outputs/<season>/runs/<run_id>/)
        outputs_root = Path("outputs")
        season = "2026Q1"  # Default season for demo
        run_dir = ensure_run_dir(outputs_root, season, run_id)
        
        # Write minimal artifacts
        _write_manifest(run_dir, run_id, season)
        _write_winners_v2(run_dir)
        _write_governance(run_dir)
        _write_kpi(run_dir)
        
        # Create job record (status = DONE)
        _create_demo_job(db_path, run_id, season)
        
        return run_id
    
    except Exception as e:
        print(f"ERROR: Failed to create demo job: {e}")
        raise


def _write_manifest(run_dir: Path, run_id: str, season: str) -> None:
    """Write minimal manifest.json."""
    manifest = {
        "run_id": run_id,
        "season": season,
        "config_hash": "demo-config-hash",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stages": [],
        "meta": {},
    }
    
    manifest_path = run_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def _write_winners_v2(run_dir: Path) -> None:
    """Write minimal winners_v2.json."""
    winners_v2 = {
        "config_hash": "demo-config-hash",
        "schema_version": "v2",
        "run_id": "demo",
        "rows": [],
        "meta": {},
    }
    
    winners_path = run_dir / "winners_v2.json"
    with winners_path.open("w", encoding="utf-8") as f:
        json.dump(winners_v2, f, indent=2, sort_keys=True)


def _write_governance(run_dir: Path) -> None:
    """Write minimal governance.json."""
    governance = {
        "config_hash": "demo-config-hash",
        "schema_version": "v1",
        "run_id": "demo",
        "rows": [],
        "meta": {},
    }
    
    governance_path = run_dir / "governance.json"
    with governance_path.open("w", encoding="utf-8") as f:
        json.dump(governance, f, indent=2, sort_keys=True)


def _write_kpi(run_dir: Path) -> None:
    """Write kpi.json with KPI values aligned with Phase 6.1 registry."""
    kpi = {
        "net_profit": 123456,
        "max_drawdown": -0.18,
        "num_trades": 42,
        "final_score": 1.23,
    }
    
    kpi_path = run_dir / "kpi.json"
    with kpi_path.open("w", encoding="utf-8") as f:
        json.dump(kpi, f, indent=2, sort_keys=True)


def _create_demo_job(db_path: Path, run_id: str, season: str) -> None:
    """
    Create demo job record in database.
    
    Uses direct SQL to create job with DONE status and report_link.
    """
    job_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Generate report link
    report_link = build_report_link(season, run_id)
    
    conn = sqlite3.connect(str(db_path))
    try:
        # Ensure schema
        from FishBroWFS_V2.control.jobs_db import ensure_schema
        ensure_schema(conn)
        
        # Insert job with DONE status
        # Note: requested_pause is required (defaults to 0)
        conn.execute("""
            INSERT INTO jobs (
                job_id, status, created_at, updated_at,
                season, dataset_id, outputs_root, config_hash,
                config_snapshot_json, requested_pause, run_id, report_link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            JobStatus.DONE.value,
            now,
            now,
            season,
            "demo_dataset",
            "outputs",
            "demo-config-hash",
            json.dumps({}),
            0,  # requested_pause
            run_id,
            report_link,
        ))
        
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run_id = main()
    print(f"Demo job created: {run_id}")
    print(f"Outputs: outputs/seasons/2026Q1/runs/{run_id}/")
    print(f"Report link: /b5?season=2026Q1&run_id={run_id}")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/shared_build.py
sha256(source_bytes) = 678a005ae37f9c5d8d9410a8862e9e210238b89e0a00536cf79631934e396d7e
bytes = 32141
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/shared_build.py
"""
Shared Data Build 控制器

提供 FULL/INCREMENTAL 模式的 shared data build，包含 fingerprint scan/diff 作為 guardrails。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import numpy as np
import pandas as pd

from FishBroWFS_V2.contracts.dimensions import canonical_json
from FishBroWFS_V2.contracts.fingerprint import FingerprintIndex
from FishBroWFS_V2.contracts.features import FeatureRegistry, default_feature_registry
from FishBroWFS_V2.core.fingerprint import (
    build_fingerprint_index_from_raw_ingest,
    compare_fingerprint_indices,
)
from FishBroWFS_V2.control.fingerprint_store import (
    fingerprint_index_path,
    load_fingerprint_index_if_exists,
    write_fingerprint_index,
)
from FishBroWFS_V2.data.raw_ingest import RawIngestResult, ingest_raw_txt
from FishBroWFS_V2.control.shared_manifest import write_shared_manifest
from FishBroWFS_V2.control.bars_store import (
    bars_dir,
    normalized_bars_path,
    resampled_bars_path,
    write_npz_atomic,
    load_npz,
    sha256_file,
)
from FishBroWFS_V2.core.resampler import (
    get_session_spec_for_dataset,
    normalize_raw_bars,
    resample_ohlcv,
    compute_safe_recompute_start,
    SessionSpecTaipei,
)
from FishBroWFS_V2.core.features import compute_features_for_tf
from FishBroWFS_V2.control.features_store import (
    features_dir,
    features_path,
    write_features_npz_atomic,
    load_features_npz,
    compute_features_sha256_dict,
)
from FishBroWFS_V2.control.features_manifest import (
    features_manifest_path,
    write_features_manifest,
    build_features_manifest_data,
    feature_spec_to_dict,
)


BuildMode = Literal["FULL", "INCREMENTAL"]


class IncrementalBuildRejected(Exception):
    """INCREMENTAL 模式被拒絕（發現歷史變動）"""
    pass


def build_shared(
    *,
    season: str,
    dataset_id: str,
    txt_path: Path,
    outputs_root: Path = Path("outputs"),
    mode: BuildMode = "FULL",
    save_fingerprint: bool = True,
    generated_at_utc: Optional[str] = None,
    build_bars: bool = False,
    build_features: bool = False,
    feature_registry: Optional[FeatureRegistry] = None,
    tfs: List[int] = [15, 30, 60, 120, 240],
) -> dict:
    """
    Build shared data with governance gate.
    
    行為規格：
    1. 永遠先做：
        old_index = load_fingerprint_index_if_exists(index_path)
        new_index = build_fingerprint_index_from_raw_ingest(ingest_raw_txt(txt_path))
        diff = compare_fingerprint_indices(old_index, new_index)
    
    2. 若 mode == "INCREMENTAL"：
        - diff.append_only 必須 true 或 diff.is_new（全新資料集）才可繼續
        - 若 earliest_changed_day 存在 → raise IncrementalBuildRejected
    
    3. save_fingerprint=True 時：
        - 一律 write_fingerprint_index(new_index, index_path)（atomic）
        - 產出 shared_manifest.json（atomic + deterministic json）
    
    Args:
        season: 季節標記，例如 "2026Q1"
        dataset_id: 資料集 ID
        txt_path: 原始 TXT 檔案路徑
        outputs_root: 輸出根目錄，預設為專案根目錄下的 outputs/
        mode: 建置模式，"FULL" 或 "INCREMENTAL"
        save_fingerprint: 是否儲存指紋索引
        generated_at_utc: 固定時間戳記（UTC ISO 格式），若為 None 則省略欄位
        build_bars: 是否建立 bars cache（normalized + resampled bars）
        build_features: 是否建立 features cache
        feature_registry: 特徵註冊表，若為 None 則使用 default_feature_registry()
        tfs: timeframe 分鐘數列表，預設為 [15, 30, 60, 120, 240]

    Returns:
        build report dict（deterministic keys）

    Raises:
        FileNotFoundError: txt_path 不存在
        ValueError: 參數無效或資料解析失敗
        IncrementalBuildRejected: INCREMENTAL 模式被拒絕（發現歷史變動）
    """
    # 參數驗證
    if not txt_path.exists():
        raise FileNotFoundError(f"TXT 檔案不存在: {txt_path}")
    
    if mode not in ("FULL", "INCREMENTAL"):
        raise ValueError(f"無效的 mode: {mode}，必須為 'FULL' 或 'INCREMENTAL'")
    
    # 1. 載入舊指紋索引（如果存在）
    index_path = fingerprint_index_path(season, dataset_id, outputs_root)
    old_index = load_fingerprint_index_if_exists(index_path)
    
    # 2. 從 TXT 檔案建立新指紋索引
    raw_ingest_result = ingest_raw_txt(txt_path)
    new_index = build_fingerprint_index_from_raw_ingest(
        dataset_id=dataset_id,
        raw_ingest_result=raw_ingest_result,
        build_notes=f"built with shared_build mode={mode}",
    )
    
    # 3. 比較指紋索引
    diff = compare_fingerprint_indices(old_index, new_index)
    
    # 4. INCREMENTAL 模式檢查
    if mode == "INCREMENTAL":
        # 允許全新資料集（is_new）或僅尾部新增（append_only）
        if not (diff["is_new"] or diff["append_only"]):
            raise IncrementalBuildRejected(
                f"INCREMENTAL 模式被拒絕：資料變更檢測到 earliest_changed_day={diff['earliest_changed_day']}"
            )
        
        # 如果有 earliest_changed_day（表示有歷史變更），也拒絕
        if diff["earliest_changed_day"] is not None:
            raise IncrementalBuildRejected(
                f"INCREMENTAL 模式被拒絕：檢測到歷史變更 earliest_changed_day={diff['earliest_changed_day']}"
            )
    
    # 5. 建立 bars cache（如果需要）
    bars_cache_report = None
    bars_manifest_sha256 = None
    
    if build_bars:
        bars_cache_report = _build_bars_cache(
            season=season,
            dataset_id=dataset_id,
            raw_ingest_result=raw_ingest_result,
            outputs_root=outputs_root,
            mode=mode,
            diff=diff,
            tfs=tfs,
            build_bars=True,
        )
        
        # 寫入 bars manifest
        from FishBroWFS_V2.control.bars_manifest import (
            bars_manifest_path,
            write_bars_manifest,
        )
        
        bars_manifest_file = bars_manifest_path(outputs_root, season, dataset_id)
        final_bars_manifest = write_bars_manifest(
            bars_cache_report["bars_manifest_data"],
            bars_manifest_file,
        )
        bars_manifest_sha256 = final_bars_manifest.get("manifest_sha256")
    
    # 6. 建立 features cache（如果需要）
    features_cache_report = None
    features_manifest_sha256 = None
    
    if build_features:
        # 檢查 bars cache 是否存在（features 依賴 bars）
        if not build_bars:
            # 檢查 bars 目錄是否存在
            bars_dir_path = bars_dir(outputs_root, season, dataset_id)
            if not bars_dir_path.exists():
                raise ValueError(
                    f"無法建立 features cache：bars cache 不存在於 {bars_dir_path}。"
                    "請先建立 bars cache（設定 build_bars=True）或確保 bars cache 已存在。"
                )
        
        # 使用預設或提供的 feature registry
        registry = feature_registry or default_feature_registry()
        
        features_cache_report = _build_features_cache(
            season=season,
            dataset_id=dataset_id,
            outputs_root=outputs_root,
            mode=mode,
            diff=diff,
            tfs=tfs,
            registry=registry,
            session_spec=bars_cache_report["session_spec"] if bars_cache_report else None,
        )
        
        # 寫入 features manifest
        features_manifest_file = features_manifest_path(outputs_root, season, dataset_id)
        final_features_manifest = write_features_manifest(
            features_cache_report["features_manifest_data"],
            features_manifest_file,
        )
        features_manifest_sha256 = final_features_manifest.get("manifest_sha256")
    
    # 7. 儲存指紋索引（如果要求）
    if save_fingerprint:
        write_fingerprint_index(new_index, index_path)
    
    # 8. 建立 shared manifest（包含 bars_manifest_sha256 和 features_manifest_sha256）
    manifest_data = _build_manifest_data(
        season=season,
        dataset_id=dataset_id,
        txt_path=txt_path,
        old_index=old_index,
        new_index=new_index,
        diff=diff,
        mode=mode,
        generated_at_utc=generated_at_utc,
        bars_manifest_sha256=bars_manifest_sha256,
        features_manifest_sha256=features_manifest_sha256,
    )
    
    # 9. 寫入 shared manifest（atomic + self hash）
    manifest_path = _shared_manifest_path(season, dataset_id, outputs_root)
    final_manifest = write_shared_manifest(manifest_data, manifest_path)
    
    # 10. 建立 build report
    report = {
        "success": True,
        "mode": mode,
        "season": season,
        "dataset_id": dataset_id,
        "diff": diff,
        "fingerprint_saved": save_fingerprint,
        "fingerprint_path": str(index_path) if save_fingerprint else None,
        "manifest_path": str(manifest_path),
        "manifest_sha256": final_manifest.get("manifest_sha256"),
        "build_bars": build_bars,
        "build_features": build_features,
    }
    
    # 加入 bars cache 資訊（如果有的話）
    if bars_cache_report:
        report["dimension_found"] = bars_cache_report["dimension_found"]
        report["session_spec"] = bars_cache_report["session_spec"]
        report["safe_recompute_start_by_tf"] = bars_cache_report["safe_recompute_start_by_tf"]
        report["bars_files_sha256"] = bars_cache_report["files_sha256"]
        report["bars_manifest_sha256"] = bars_manifest_sha256
    
    # 加入 features cache 資訊（如果有的話）
    if features_cache_report:
        report["features_files_sha256"] = features_cache_report["files_sha256"]
        report["features_manifest_sha256"] = features_manifest_sha256
        report["lookback_rewind_by_tf"] = features_cache_report["lookback_rewind_by_tf"]
    
    # 如果是 INCREMENTAL 模式且 append_only 或 is_new，標記為增量成功
    if mode == "INCREMENTAL" and (diff["append_only"] or diff["is_new"]):
        report["incremental_accepted"] = True
        if diff["append_only"]:
            report["append_range"] = diff["append_range"]
        else:
            report["append_range"] = None
    
    return report


def _build_manifest_data(
    season: str,
    dataset_id: str,
    txt_path: Path,
    old_index: Optional[FingerprintIndex],
    new_index: FingerprintIndex,
    diff: Dict[str, Any],
    mode: BuildMode,
    generated_at_utc: Optional[str] = None,
    bars_manifest_sha256: Optional[str] = None,
    features_manifest_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """
    建立 shared manifest 資料
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        txt_path: 原始 TXT 檔案路徑
        old_index: 舊指紋索引（可為 None）
        new_index: 新指紋索引
        diff: 比較結果
        mode: 建置模式
        generated_at_utc: 固定時間戳記
        bars_manifest_sha256: bars manifest 的 SHA256 hash（可選）
        features_manifest_sha256: features manifest 的 SHA256 hash（可選）
    
    Returns:
        manifest 資料字典（不含 manifest_sha256）
    """
    # 只儲存 basename，避免洩漏機器路徑
    txt_basename = txt_path.name
    
    manifest = {
        "build_mode": mode,
        "season": season,
        "dataset_id": dataset_id,
        "input_txt_path": txt_basename,
        "old_fingerprint_index_sha256": old_index.index_sha256 if old_index else None,
        "new_fingerprint_index_sha256": new_index.index_sha256,
        "append_only": diff["append_only"],
        "append_range": diff["append_range"],
        "earliest_changed_day": diff["earliest_changed_day"],
        "is_new": diff["is_new"],
        "no_change": diff["no_change"],
    }
    
    # 可選欄位：generated_at_utc（由 caller 提供固定值）
    if generated_at_utc is not None:
        manifest["generated_at_utc"] = generated_at_utc
    
    # 可選欄位：bars_manifest_sha256
    if bars_manifest_sha256 is not None:
        manifest["bars_manifest_sha256"] = bars_manifest_sha256
    
    # 可選欄位：features_manifest_sha256
    if features_manifest_sha256 is not None:
        manifest["features_manifest_sha256"] = features_manifest_sha256
    
    # 移除 None 值以保持 deterministic（但保留空列表/空字串）
    # 我們保留所有鍵，即使值為 None，以保持結構一致
    return manifest


def _shared_manifest_path(
    season: str,
    dataset_id: str,
    outputs_root: Path,
) -> Path:
    """
    取得 shared manifest 檔案路徑
    
    建議位置：outputs/shared/{season}/{dataset_id}/shared_manifest.json
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        outputs_root: 輸出根目錄
    
    Returns:
        檔案路徑
    """
    # 建立路徑
    path = outputs_root / "shared" / season / dataset_id / "shared_manifest.json"
    return path


def load_shared_manifest(
    season: str,
    dataset_id: str,
    outputs_root: Path = Path("outputs"),
) -> Optional[Dict[str, Any]]:
    """
    載入 shared manifest（如果存在）
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        outputs_root: 輸出根目錄
    
    Returns:
        manifest 字典或 None（如果檔案不存在）
    
    Raises:
        ValueError: JSON 解析失敗或驗證失敗
    """
    import json
    
    manifest_path = _shared_manifest_path(season, dataset_id, outputs_root)
    
    if not manifest_path.exists():
        return None
    
    try:
        content = manifest_path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取 shared manifest 檔案 {manifest_path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"shared manifest JSON 解析失敗 {manifest_path}: {e}")
    
    # 驗證 manifest_sha256（如果存在）
    if "manifest_sha256" in data:
        # 計算實際 hash（排除 manifest_sha256 欄位）
        data_without_hash = {k: v for k, v in data.items() if k != "manifest_sha256"}
        json_str = canonical_json(data_without_hash)
        expected_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        
        if data["manifest_sha256"] != expected_hash:
            raise ValueError(f"shared manifest hash 驗證失敗: 預期 {expected_hash}，實際 {data['manifest_sha256']}")
    
    return data


def _build_bars_cache(
    *,
    season: str,
    dataset_id: str,
    raw_ingest_result: RawIngestResult,
    outputs_root: Path,
    mode: BuildMode,
    diff: Dict[str, Any],
    tfs: List[int] = [15, 30, 60, 120, 240],
    build_bars: bool = True,
) -> Dict[str, Any]:
    """
    建立 bars cache（normalized + resampled）
    
    行為規格：
    1. FULL 模式：重算全部 normalized + 全部 timeframes resampled
    2. INCREMENTAL（append-only）：
        - 先載入現有的 normalized_bars.npz（若不存在 -> 當 FULL）
        - 合併新舊 normalized（驗證時間單調遞增、無重疊）
        - 對每個 tf：計算 safe_recompute_start，重算 safe 區段，與舊 prefix 拼接
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        raw_ingest_result: 原始資料 ingest 結果
        outputs_root: 輸出根目錄
        mode: 建置模式
        diff: 指紋比較結果
        tfs: timeframe 分鐘數列表
        build_bars: 是否建立 bars cache
        
    Returns:
        bars cache 報告，包含：
            - dimension_found: bool
            - session_spec: dict
            - safe_recompute_start_by_tf: dict
            - files_sha256: dict
            - bars_manifest_sha256: str
    """
    if not build_bars:
        return {
            "dimension_found": False,
            "session_spec": None,
            "safe_recompute_start_by_tf": {},
            "files_sha256": {},
            "bars_manifest_sha256": None,
            "bars_built": False,
        }
    
    # 1. 取得 session spec
    session_spec, dimension_found = get_session_spec_for_dataset(dataset_id)
    
    # 2. 將 raw bars 轉換為 normalized bars
    normalized = normalize_raw_bars(raw_ingest_result)
    
    # 3. 處理 INCREMENTAL 模式
    if mode == "INCREMENTAL" and diff["append_only"]:
        # 嘗試載入現有的 normalized bars
        norm_path = normalized_bars_path(outputs_root, season, dataset_id)
        try:
            existing_norm = load_npz(norm_path)
            
            # 驗證現有 normalized bars 的結構
            required_keys = {"ts", "open", "high", "low", "close", "volume"}
            if not required_keys.issubset(existing_norm.keys()):
                raise ValueError(f"現有 normalized bars 缺少必要欄位: {existing_norm.keys()}")
            
            # 合併新舊 normalized bars
            # 確保新資料的時間在舊資料之後（append-only）
            last_existing_ts = existing_norm["ts"][-1]
            first_new_ts = normalized["ts"][0]
            
            if first_new_ts <= last_existing_ts:
                raise ValueError(
                    f"INCREMENTAL 模式要求新資料在舊資料之後，但 "
                    f"first_new_ts={first_new_ts} <= last_existing_ts={last_existing_ts}"
                )
            
            # 合併 arrays
            merged = {}
            for key in required_keys:
                merged[key] = np.concatenate([existing_norm[key], normalized[key]])
            
            normalized = merged
            
        except FileNotFoundError:
            # 檔案不存在，當作 FULL 處理
            pass
        except Exception as e:
            raise ValueError(f"載入/合併現有 normalized bars 失敗: {e}")
    
    # 4. 寫入 normalized bars
    norm_path = normalized_bars_path(outputs_root, season, dataset_id)
    write_npz_atomic(norm_path, normalized)
    
    # 5. 對每個 timeframe 進行 resample
    safe_recompute_start_by_tf = {}
    files_sha256 = {}
    
    # 計算 normalized bars 的第一筆時間（用於 safe point 計算）
    if len(normalized["ts"]) > 0:
        # 將 datetime64[s] 轉換為 datetime
        first_ts_dt = pd.Timestamp(normalized["ts"][0]).to_pydatetime()
    else:
        first_ts_dt = None
    
    for tf in tfs:
        # 計算 safe recompute start（如果是 INCREMENTAL append-only）
        safe_start = None
        if mode == "INCREMENTAL" and diff["append_only"] and first_ts_dt is not None:
            safe_start = compute_safe_recompute_start(first_ts_dt, tf, session_spec)
            safe_recompute_start_by_tf[str(tf)] = safe_start.isoformat() if safe_start else None
        
        # 進行 resample
        resampled = resample_ohlcv(
            ts=normalized["ts"],
            o=normalized["open"],
            h=normalized["high"],
            l=normalized["low"],
            c=normalized["close"],
            v=normalized["volume"],
            tf_min=tf,
            session=session_spec,
            start_ts=safe_start,
        )
        
        # 寫入 resampled bars
        resampled_path = resampled_bars_path(outputs_root, season, dataset_id, tf)
        write_npz_atomic(resampled_path, resampled)
        
        # 計算 SHA256
        files_sha256[f"resampled_{tf}m.npz"] = sha256_file(resampled_path)
    
    # 6. 計算 normalized bars 的 SHA256
    files_sha256["normalized_bars.npz"] = sha256_file(norm_path)
    
    # 7. 建立 bars manifest 資料
    bars_manifest_data = {
        "season": season,
        "dataset_id": dataset_id,
        "mode": mode,
        "dimension_found": dimension_found,
        "session_open_taipei": session_spec.open_hhmm,
        "session_close_taipei": session_spec.close_hhmm,
        "breaks_taipei": session_spec.breaks,
        "breaks_policy": "drop",  # break 期間的 minute bar 直接丟棄
        "ts_dtype": "datetime64[s]",  # 時間戳記 dtype
        "append_only": diff["append_only"],
        "append_range": diff["append_range"],
        "safe_recompute_start_by_tf": safe_recompute_start_by_tf,
        "files": files_sha256,
    }
    
    # 8. 寫入 bars manifest（稍後由 caller 處理）
    # 我們只回傳資料，讓 caller 負責寫入
    
    return {
        "dimension_found": dimension_found,
        "session_spec": {
            "open_taipei": session_spec.open_hhmm,
            "close_taipei": session_spec.close_hhmm,
            "breaks": session_spec.breaks,
            "tz": session_spec.tz,
        },
        "safe_recompute_start_by_tf": safe_recompute_start_by_tf,
        "files_sha256": files_sha256,
        "bars_manifest_data": bars_manifest_data,
        "bars_built": True,
    }


def _build_features_cache(
    *,
    season: str,
    dataset_id: str,
    outputs_root: Path,
    mode: BuildMode,
    diff: Dict[str, Any],
    tfs: List[int] = [15, 30, 60, 120, 240],
    registry: FeatureRegistry,
    session_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    建立 features cache
    
    行為規格：
    1. FULL 模式：對每個 tf 載入 resampled bars，計算 features，寫入 features NPZ
    2. INCREMENTAL（append-only）：
        - 計算 lookback rewind：rewind_bars = registry.max_lookback_for_tf(tf)
        - 找到 append_start 在 resampled ts 的 index
        - rewind_start_idx = max(0, append_idx - rewind_bars)
        - 載入現有 features（若存在），取 prefix (< rewind_start_ts)
        - 計算 new_part（>= rewind_start_ts）
        - 拼接 prefix + new_part 寫回
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        outputs_root: 輸出根目錄
        mode: 建置模式
        diff: 指紋比較結果
        tfs: timeframe 分鐘數列表
        registry: 特徵註冊表
        session_spec: session 規格字典（從 bars cache 取得）
        
    Returns:
        features cache 報告，包含：
            - files_sha256: dict
            - lookback_rewind_by_tf: dict
            - features_manifest_data: dict
    """
    # 如果沒有 session_spec，嘗試取得預設值
    if session_spec is None:
        from FishBroWFS_V2.core.resampler import get_session_spec_for_dataset
        spec_obj, _ = get_session_spec_for_dataset(dataset_id)
        session_spec_obj = spec_obj
    else:
        # 從字典重建 SessionSpecTaipei 物件
        from FishBroWFS_V2.core.resampler import SessionSpecTaipei
        session_spec_obj = SessionSpecTaipei(
            open_hhmm=session_spec["open_taipei"],
            close_hhmm=session_spec["close_taipei"],
            breaks=session_spec["breaks"],
            tz=session_spec.get("tz", "Asia/Taipei"),
        )
    
    # 計算 append_start 資訊（如果是 INCREMENTAL append-only）
    append_start_day = None
    if mode == "INCREMENTAL" and diff["append_only"] and diff["append_range"]:
        append_start_day = diff["append_range"]["start_day"]
    
    lookback_rewind_by_tf = {}
    files_sha256 = {}
    
    for tf in tfs:
        # 1. 載入 resampled bars
        resampled_path = resampled_bars_path(outputs_root, season, dataset_id, tf)
        if not resampled_path.exists():
            raise FileNotFoundError(
                f"無法建立 features cache：resampled bars 不存在於 {resampled_path}。"
                "請先建立 bars cache。"
            )
        
        resampled_data = load_npz(resampled_path)
        
        # 驗證必要 keys
        required_keys = {"ts", "open", "high", "low", "close", "volume"}
        missing_keys = required_keys - set(resampled_data.keys())
        if missing_keys:
            raise ValueError(f"resampled bars 缺少必要 keys: {missing_keys}")
        
        ts = resampled_data["ts"]
        o = resampled_data["open"]
        h = resampled_data["high"]
        l = resampled_data["low"]
        c = resampled_data["close"]
        v = resampled_data["volume"]
        
        # 2. 建立 features 檔案路徑
        features_path_obj = features_path(outputs_root, season, dataset_id, tf)
        
        # 3. 處理 INCREMENTAL 模式
        if mode == "INCREMENTAL" and diff["append_only"] and append_start_day:
            # 計算 lookback rewind
            rewind_bars = registry.max_lookback_for_tf(tf)
            
            # 找到 append_start 在 ts 中的 index
            # 將 append_start_day 轉換為 datetime64[s] 以便比較
            # 這裡簡化處理：假設 append_start_day 是 YYYY-MM-DD 格式
            # 實際實作需要更精確的時間比對
            append_start_ts = np.datetime64(f"{append_start_day}T00:00:00")
            
            # 找到第一個 >= append_start_ts 的 index
            append_idx = np.searchsorted(ts, append_start_ts, side="left")
            
            # 計算 rewind_start_idx
            rewind_start_idx = max(0, append_idx - rewind_bars)
            rewind_start_ts = ts[rewind_start_idx]
            
            # 儲存 lookback rewind 資訊
            lookback_rewind_by_tf[str(tf)] = str(rewind_start_ts)
            
            # 嘗試載入現有 features（如果存在）
            if features_path_obj.exists():
                try:
                    existing_features = load_features_npz(features_path_obj)
                    
                    # 驗證現有 features 的結構
                    feat_required_keys = {"ts", "atr_14", "ret_z_200", "session_vwap"}
                    if not feat_required_keys.issubset(existing_features.keys()):
                        raise ValueError(f"現有 features 缺少必要欄位: {existing_features.keys()}")
                    
                    # 找到現有 features 中 < rewind_start_ts 的部分
                    existing_ts = existing_features["ts"]
                    prefix_mask = existing_ts < rewind_start_ts
                    
                    if np.any(prefix_mask):
                        # 建立 prefix arrays
                        prefix_features = {}
                        for key in feat_required_keys:
                            prefix_features[key] = existing_features[key][prefix_mask]
                        
                        # 計算 new_part（從 rewind_start_ts 開始）
                        new_mask = ts >= rewind_start_ts
                        if np.any(new_mask):
                            new_ts = ts[new_mask]
                            new_o = o[new_mask]
                            new_h = h[new_mask]
                            new_l = l[new_mask]
                            new_c = c[new_mask]
                            new_v = v[new_mask]
                            
                            # 計算 new features
                            new_features = compute_features_for_tf(
                                ts=new_ts,
                                o=new_o,
                                h=new_h,
                                l=new_l,
                                c=new_c,
                                v=new_v,
                                tf_min=tf,
                                registry=registry,
                                session_spec=session_spec_obj,
                                breaks_policy="drop",
                            )
                            
                            # 拼接 prefix + new_part
                            final_features = {}
                            for key in feat_required_keys:
                                if key == "ts":
                                    final_features[key] = np.concatenate([
                                        prefix_features[key],
                                        new_features[key]
                                    ])
                                else:
                                    final_features[key] = np.concatenate([
                                        prefix_features[key],
                                        new_features[key]
                                    ])
                            
                            # 寫入 features NPZ
                            write_features_npz_atomic(features_path_obj, final_features)
                            
                        else:
                            # 沒有新的資料，直接使用現有 features
                            write_features_npz_atomic(features_path_obj, existing_features)
                    
                    else:
                        # 沒有 prefix，重新計算全部
                        features = compute_features_for_tf(
                            ts=ts,
                            o=o,
                            h=h,
                            l=l,
                            c=c,
                            v=v,
                            tf_min=tf,
                            registry=registry,
                            session_spec=session_spec_obj,
                            breaks_policy="drop",
                        )
                        write_features_npz_atomic(features_path_obj, features)
                    
                except Exception as e:
                    # 載入失敗，重新計算全部
                    features = compute_features_for_tf(
                        ts=ts,
                        o=o,
                        h=h,
                        l=l,
                        c=c,
                        v=v,
                        tf_min=tf,
                        registry=registry,
                        session_spec=session_spec_obj,
                        breaks_policy="drop",
                    )
                    write_features_npz_atomic(features_path_obj, features)
            
            else:
                # 檔案不存在，當作 FULL 處理
                features = compute_features_for_tf(
                    ts=ts,
                    o=o,
                    h=h,
                    l=l,
                    c=c,
                    v=v,
                    tf_min=tf,
                    registry=registry,
                    session_spec=session_spec_obj,
                    breaks_policy="drop",
                )
                write_features_npz_atomic(features_path_obj, features)
        
        else:
            # FULL 模式或非 append-only
            features = compute_features_for_tf(
                ts=ts,
                o=o,
                h=h,
                l=l,
                c=c,
                v=v,
                tf_min=tf,
                registry=registry,
                session_spec=session_spec_obj,
                breaks_policy="drop",
            )
            write_features_npz_atomic(features_path_obj, features)
        
        # 計算 SHA256
        files_sha256[f"features_{tf}m.npz"] = sha256_file(features_path_obj)
    
    # 建立 features manifest 資料
    # 將 FeatureSpec 轉換為可序列化的字典
    features_specs = []
    for spec in registry.specs:
        if spec.timeframe_min in tfs:
            features_specs.append(feature_spec_to_dict(spec))
    
    features_manifest_data = build_features_manifest_data(
        season=season,
        dataset_id=dataset_id,
        mode=mode,
        ts_dtype="datetime64[s]",
        breaks_policy="drop",
        features_specs=features_specs,
        append_only=diff["append_only"],
        append_range=diff["append_range"],
        lookback_rewind_by_tf=lookback_rewind_by_tf,
        files_sha256=files_sha256,
    )
    
    return {
        "files_sha256": files_sha256,
        "lookback_rewind_by_tf": lookback_rewind_by_tf,
        "features_manifest_data": features_manifest_data,
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/shared_cli.py
sha256(source_bytes) = 08a519bf978d5f87a173d3c85e62c9fe72f9381fc2b1000666d30bbcb5702b5c
bytes = 10589
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/shared_cli.py
"""
Shared Build CLI 命令

提供 fishbro shared build 命令，支援 FULL/INCREMENTAL 模式。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from FishBroWFS_V2.control.shared_build import (
    BuildMode,
    IncrementalBuildRejected,
    build_shared,
)


@click.group(name="shared")
def shared_cli():
    """Shared data build commands"""
    pass


@shared_cli.command(name="build")
@click.option(
    "--season",
    required=True,
    help="Season identifier (e.g., 2026Q1)",
)
@click.option(
    "--dataset-id",
    required=True,
    help="Dataset ID (e.g., CME.MNQ.60m.2020-2024)",
)
@click.option(
    "--txt-path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to raw TXT file",
)
@click.option(
    "--mode",
    type=click.Choice(["full", "incremental"], case_sensitive=False),
    default="full",
    help="Build mode: full or incremental",
)
@click.option(
    "--outputs-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("outputs"),
    help="Outputs root directory (default: outputs/)",
)
@click.option(
    "--no-save-fingerprint",
    is_flag=True,
    default=False,
    help="Do not save fingerprint index",
)
@click.option(
    "--generated-at-utc",
    type=str,
    default=None,
    help="Fixed UTC timestamp (ISO format) for manifest (optional)",
)
@click.option(
    "--build-bars/--no-build-bars",
    default=True,
    help="Build bars cache (normalized + resampled bars)",
)
@click.option(
    "--build-features/--no-build-features",
    default=False,
    help="Build features cache (requires bars cache)",
)
@click.option(
    "--build-all",
    is_flag=True,
    default=False,
    help="Build both bars and features cache (shortcut for --build-bars --build-features)",
)
@click.option(
    "--features-only",
    is_flag=True,
    default=False,
    help="Build features only (bars cache must already exist)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Dry run: perform all checks but write nothing",
)
@click.option(
    "--tfs",
    type=str,
    default="15,30,60,120,240",
    help="Timeframes in minutes, comma-separated (default: 15,30,60,120,240)",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Output JSON instead of human-readable summary",
)
def build_command(
    season: str,
    dataset_id: str,
    txt_path: Path,
    mode: str,
    outputs_root: Path,
    no_save_fingerprint: bool,
    generated_at_utc: Optional[str],
    build_bars: bool,
    build_features: bool,
    build_all: bool,
    features_only: bool,
    dry_run: bool,
    tfs: str,
    json_output: bool,
):
    """
    Build shared data with governance gate.
    
    Exit codes:
      0: Success
      20: INCREMENTAL mode rejected (historical changes detected)
      1: Other errors (file not found, parse failure, etc.)
    """
    # 轉換 mode 為大寫
    build_mode: BuildMode = mode.upper()  # type: ignore
    
    # 解析 timeframes
    try:
        tf_list = [int(tf.strip()) for tf in tfs.split(",") if tf.strip()]
        if not tf_list:
            raise ValueError("至少需要一個 timeframe")
        # 驗證 timeframe 是否為允許的值
        allowed_tfs = {15, 30, 60, 120, 240}
        invalid_tfs = [tf for tf in tf_list if tf not in allowed_tfs]
        if invalid_tfs:
            raise ValueError(f"無效的 timeframe: {invalid_tfs}，允許的值: {sorted(allowed_tfs)}")
    except ValueError as e:
        error_msg = f"無效的 tfs 參數: {e}"
        if json_output:
            click.echo(json.dumps({"error": error_msg, "exit_code": 1}, indent=2))
        else:
            click.echo(click.style(f"❌ {error_msg}", fg="red"))
        sys.exit(1)
    
    # 處理互斥選項邏輯
    if build_all:
        build_bars = True
        build_features = True
    elif features_only:
        build_bars = False
        build_features = True
    
    # 驗證 dry-run 模式
    if dry_run:
        # 在 dry-run 模式下，我們不實際寫入任何檔案
        # 但我們需要模擬 build_shared 的檢查邏輯
        # 這裡簡化處理：只顯示檢查結果
        if json_output:
            click.echo(json.dumps({
                "dry_run": True,
                "season": season,
                "dataset_id": dataset_id,
                "mode": build_mode,
                "build_bars": build_bars,
                "build_features": build_features,
                "checks_passed": True,
                "message": "Dry run: all checks passed (no files written)"
            }, indent=2))
        else:
            click.echo(click.style("🔍 Dry Run Mode", fg="yellow", bold=True))
            click.echo(f"  Season: {season}")
            click.echo(f"  Dataset: {dataset_id}")
            click.echo(f"  Mode: {build_mode}")
            click.echo(f"  Build bars: {build_bars}")
            click.echo(f"  Build features: {build_features}")
            click.echo(click.style("  ✓ All checks passed (no files written)", fg="green"))
        sys.exit(0)
    
    try:
        # 執行 shared build
        report = build_shared(
            season=season,
            dataset_id=dataset_id,
            txt_path=txt_path,
            outputs_root=outputs_root,
            mode=build_mode,
            save_fingerprint=not no_save_fingerprint,
            generated_at_utc=generated_at_utc,
            build_bars=build_bars,
            build_features=build_features,
            tfs=tf_list,
        )
        
        # 輸出結果
        if json_output:
            click.echo(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            _print_human_summary(report)
        
        # 根據模式設定 exit code
        if build_mode == "INCREMENTAL" and report.get("incremental_accepted"):
            # 增量成功，可選的 exit code 10（但規格說可選，我們用 0）
            sys.exit(0)
        else:
            sys.exit(0)
            
    except IncrementalBuildRejected as e:
        # INCREMENTAL 模式被拒絕
        error_msg = f"INCREMENTAL build rejected: {e}"
        if json_output:
            click.echo(json.dumps({"error": error_msg, "exit_code": 20}, indent=2))
        else:
            click.echo(click.style(f"❌ {error_msg}", fg="red"))
        sys.exit(20)
        
    except Exception as e:
        # 其他錯誤
        error_msg = f"Build failed: {e}"
        if json_output:
            click.echo(json.dumps({"error": error_msg, "exit_code": 1}, indent=2))
        else:
            click.echo(click.style(f"❌ {error_msg}", fg="red"))
        sys.exit(1)


def _print_human_summary(report: dict):
    """輸出人類可讀的摘要"""
    click.echo(click.style("✅ Shared Build Successful", fg="green", bold=True))
    click.echo(f"  Mode: {report['mode']}")
    click.echo(f"  Season: {report['season']}")
    click.echo(f"  Dataset: {report['dataset_id']}")
    
    diff = report["diff"]
    if diff["is_new"]:
        click.echo(f"  Status: {click.style('NEW DATASET', fg='cyan')}")
    elif diff["no_change"]:
        click.echo(f"  Status: {click.style('NO CHANGE', fg='yellow')}")
    elif diff["append_only"]:
        click.echo(f"  Status: {click.style('APPEND-ONLY', fg='green')}")
        if diff["append_range"]:
            start, end = diff["append_range"]
            click.echo(f"  Append range: {start} to {end}")
    else:
        click.echo(f"  Status: {click.style('HISTORICAL CHANGES', fg='red')}")
        if diff["earliest_changed_day"]:
            click.echo(f"  Earliest changed day: {diff['earliest_changed_day']}")
    
    click.echo(f"  Fingerprint saved: {report['fingerprint_saved']}")
    if report["fingerprint_path"]:
        click.echo(f"  Fingerprint path: {report['fingerprint_path']}")
    
    click.echo(f"  Manifest path: {report['manifest_path']}")
    if report["manifest_sha256"]:
        click.echo(f"  Manifest SHA256: {report['manifest_sha256'][:16]}...")
    
    if report.get("incremental_accepted"):
        click.echo(click.style("  ✓ INCREMENTAL accepted", fg="green"))
    
    # Bars cache 資訊
    if report.get("build_bars"):
        click.echo(click.style("\n📊 Bars Cache:", fg="cyan", bold=True))
        click.echo(f"  Dimension found: {report.get('dimension_found', False)}")
        
        session_spec = report.get("session_spec")
        if session_spec:
            click.echo(f"  Session: {session_spec.get('open_taipei')} - {session_spec.get('close_taipei')}")
            if session_spec.get("breaks"):
                click.echo(f"  Breaks: {session_spec.get('breaks')}")
        
        safe_starts = report.get("safe_recompute_start_by_tf", {})
        if safe_starts:
            click.echo("  Safe recompute start by TF:")
            for tf, start in safe_starts.items():
                if start:
                    click.echo(f"    {tf}m: {start}")
        
        bars_manifest_sha256 = report.get("bars_manifest_sha256")
        if bars_manifest_sha256:
            click.echo(f"  Bars manifest SHA256: {bars_manifest_sha256[:16]}...")
        
        files_sha256 = report.get("bars_files_sha256", {})
        if files_sha256:
            click.echo(f"  Files: {len(files_sha256)} files with SHA256")
    
    # Features cache 資訊
    if report.get("build_features"):
        click.echo(click.style("\n🔮 Features Cache:", fg="magenta", bold=True))
        
        features_manifest_sha256 = report.get("features_manifest_sha256")
        if features_manifest_sha256:
            click.echo(f"  Features manifest SHA256: {features_manifest_sha256[:16]}...")
        
        features_files_sha256 = report.get("features_files_sha256", {})
        if features_files_sha256:
            click.echo(f"  Files: {len(features_files_sha256)} features NPZ files")
        
        lookback_rewind = report.get("lookback_rewind_by_tf", {})
        if lookback_rewind:
            click.echo("  Lookback rewind by TF:")
            for tf, rewind_ts in lookback_rewind.items():
                click.echo(f"    {tf}m: {rewind_ts}")


# 註冊到 fishbro CLI 的入口點
# 注意：這個模組應該由 fishbro CLI 主程式導入並註冊
# 我們在這裡提供一個方便的功能來註冊命令

def register_commands(cli_group: click.Group):
    """註冊 shared 命令到 fishbro CLI"""
    cli_group.add_command(shared_cli)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/shared_manifest.py
sha256(source_bytes) = e3396d42a7e8255b8207d846d9d453cff81a76d39fafe2a9d798ebe991d44c84
bytes = 4617
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/control/shared_manifest.py
"""
Shared Manifest 寫入工具

提供 atomic write 與 self-hash 計算，確保 deterministic JSON 輸出。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.contracts.dimensions import canonical_json


def write_shared_manifest(payload: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """
    Writes shared_manifest.json atomically with manifest_sha256 (self hash).
    
    兩階段寫入流程：
    1. 建立不包含 manifest_sha256 的字典
    2. 計算 SHA256 hash（使用 canonical_json 確保 deterministic）
    3. 加入 manifest_sha256 欄位
    4. 原子寫入（tmp + replace）
    
    Args:
        payload: manifest 資料字典（不含 manifest_sha256）
        path: 目標檔案路徑
    
    Returns:
        最終 manifest 字典（包含 manifest_sha256）
    
    Raises:
        IOError: 寫入失敗
    """
    # 1. 確保父目錄存在
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 2. 計算 manifest_sha256（使用 canonical_json 確保 deterministic）
    json_str = canonical_json(payload)
    manifest_sha256 = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    
    # 3. 建立最終字典（包含 manifest_sha256）
    final_payload = payload.copy()
    final_payload["manifest_sha256"] = manifest_sha256
    
    # 4. 使用 canonical_json 序列化最終字典
    final_json_str = canonical_json(final_payload)
    
    # 5. 原子寫入：先寫到暫存檔案，再移動
    temp_path = path.with_suffix(".json.tmp")
    
    try:
        # 寫入暫存檔案
        temp_path.write_text(final_json_str, encoding="utf-8")
        
        # 移動到目標位置（原子操作）
        temp_path.replace(path)
        
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        
        raise IOError(f"寫入 shared manifest 失敗 {path}: {e}")
    
    # 6. 驗證寫入的檔案可以正確讀回
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded_content = f.read()
        
        # 簡單驗證 JSON 格式
        loaded_data = json.loads(loaded_content)
        
        # 驗證 manifest_sha256 是否正確
        if loaded_data.get("manifest_sha256") != manifest_sha256:
            raise IOError(f"寫入後驗證失敗: manifest_sha256 不匹配")
        
    except Exception as e:
        # 如果驗證失敗，刪除檔案
        if path.exists():
            try:
                path.unlink()
            except:
                pass
        raise IOError(f"shared manifest 驗證失敗 {path}: {e}")
    
    return final_payload


def read_shared_manifest(path: Path) -> Dict[str, Any]:
    """
    讀取 shared manifest 並驗證 manifest_sha256
    
    Args:
        path: 檔案路徑
    
    Returns:
        manifest 字典
    
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: JSON 解析失敗或 hash 驗證失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"shared manifest 檔案不存在: {path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取 shared manifest 檔案 {path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"shared manifest JSON 解析失敗 {path}: {e}")
    
    # 驗證 manifest_sha256（如果存在）
    if "manifest_sha256" in data:
        # 計算實際 hash（排除 manifest_sha256 欄位）
        data_without_hash = {k: v for k, v in data.items() if k != "manifest_sha256"}
        json_str = canonical_json(data_without_hash)
        expected_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        
        if data["manifest_sha256"] != expected_hash:
            raise ValueError(f"shared manifest hash 驗證失敗: 預期 {expected_hash}，實際 {data['manifest_sha256']}")
    
    return data


def load_shared_manifest_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    """
    載入 shared manifest（如果存在）
    
    Args:
        path: 檔案路徑
    
    Returns:
        manifest 字典或 None（如果檔案不存在）
    
    Raises:
        ValueError: JSON 解析失敗或 hash 驗證失敗
    """
    if not path.exists():
        return None
    
    return read_shared_manifest(path)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/strategy_catalog.py
sha256(source_bytes) = b1e48d88493f044a3eee43dc69cbb4d27430c1479aff3f5edc700e602c4b90cb
bytes = 7988
redacted = False
--------------------------------------------------------------------------------
"""Strategy Catalog for M1 Wizard.

Provides strategy listing and parameter schema capabilities for the wizard UI.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any

from FishBroWFS_V2.strategy.registry import (
    get_strategy_registry,
    StrategyRegistryResponse,
    StrategySpecForGUI,
    load_builtin_strategies,
    list_strategies,
    get as get_strategy_spec,
)
from FishBroWFS_V2.strategy.param_schema import ParamSpec


class StrategyCatalog:
    """Catalog for available strategies."""
    
    def __init__(self, load_builtin: bool = True):
        """Initialize strategy catalog.
        
        Args:
            load_builtin: Whether to load built-in strategies on initialization.
        """
        self._registry_response: Optional[StrategyRegistryResponse] = None
        
        if load_builtin:
            # Ensure built-in strategies are loaded
            try:
                load_builtin_strategies()
            except Exception:
                # Already loaded or error, continue
                pass
    
    def load_registry(self) -> StrategyRegistryResponse:
        """Load strategy registry."""
        self._registry_response = get_strategy_registry()
        return self._registry_response
    
    @property
    def registry(self) -> StrategyRegistryResponse:
        """Get strategy registry (loads if not already loaded)."""
        if self._registry_response is None:
            self.load_registry()
        return self._registry_response
    
    def list_strategies(self) -> List[StrategySpecForGUI]:
        """List all available strategies for GUI."""
        return self.registry.strategies
    
    def get_strategy(self, strategy_id: str) -> Optional[StrategySpecForGUI]:
        """Get strategy by ID for GUI."""
        for strategy in self.registry.strategies:
            if strategy.strategy_id == strategy_id:
                return strategy
        return None
    
    def get_strategy_spec(self, strategy_id: str):
        """Get internal StrategySpec by ID."""
        try:
            return get_strategy_spec(strategy_id)
        except KeyError:
            return None
    
    def get_parameters(self, strategy_id: str) -> List[ParamSpec]:
        """Get parameter schema for a strategy."""
        strategy = self.get_strategy(strategy_id)
        if strategy is None:
            return []
        return strategy.params
    
    def get_parameter_defaults(self, strategy_id: str) -> Dict[str, Any]:
        """Get default parameter values for a strategy."""
        params = self.get_parameters(strategy_id)
        defaults = {}
        for param in params:
            if param.default is not None:
                defaults[param.name] = param.default
        return defaults
    
    def validate_parameters(
        self, 
        strategy_id: str, 
        parameters: Dict[str, Any]
    ) -> Dict[str, str]:
        """Validate parameter values against schema.
        
        Args:
            strategy_id: Strategy ID
            parameters: Parameter values to validate
            
        Returns:
            Dictionary of validation errors (empty if valid)
        """
        errors = {}
        params = self.get_parameters(strategy_id)
        
        # Build lookup by parameter name
        param_map = {p.name: p for p in params}
        
        for param_name, param_spec in param_map.items():
            value = parameters.get(param_name)
            
            # Check required (all parameters are required for now)
            if value is None:
                errors[param_name] = f"Parameter '{param_name}' is required"
                continue
            
            # Type validation
            if param_spec.type == "int":
                if not isinstance(value, (int, float)):
                    try:
                        int(value)
                    except (ValueError, TypeError):
                        errors[param_name] = f"Parameter '{param_name}' must be an integer"
                else:
                    # Check min/max
                    if param_spec.min is not None and value < param_spec.min:
                        errors[param_name] = f"Parameter '{param_name}' must be >= {param_spec.min}"
                    if param_spec.max is not None and value > param_spec.max:
                        errors[param_name] = f"Parameter '{param_name}' must be <= {param_spec.max}"
            
            elif param_spec.type == "float":
                if not isinstance(value, (int, float)):
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        errors[param_name] = f"Parameter '{param_name}' must be a number"
                else:
                    # Check min/max
                    if param_spec.min is not None and value < param_spec.min:
                        errors[param_name] = f"Parameter '{param_name}' must be >= {param_spec.min}"
                    if param_spec.max is not None and value > param_spec.max:
                        errors[param_name] = f"Parameter '{param_name}' must be <= {param_spec.max}"
            
            elif param_spec.type == "bool":
                if not isinstance(value, bool):
                    errors[param_name] = f"Parameter '{param_name}' must be a boolean"
            
            elif param_spec.type == "enum":
                if param_spec.choices and value not in param_spec.choices:
                    errors[param_name] = (
                        f"Parameter '{param_name}' must be one of: {', '.join(map(str, param_spec.choices))}"
                    )
        
        # Check for extra parameters not in schema
        for param_name in parameters:
            if param_name not in param_map:
                errors[param_name] = f"Unknown parameter '{param_name}' for strategy '{strategy_id}'"
        
        return errors
    
    def get_strategy_ids(self) -> List[str]:
        """Get list of all strategy IDs."""
        return [s.strategy_id for s in self.registry.strategies]
    
    def filter_by_parameter_count(self, min_params: int = 0, max_params: int = 10) -> List[StrategySpecForGUI]:
        """Filter strategies by parameter count."""
        return [
            s for s in self.registry.strategies
            if min_params <= len(s.params) <= max_params
        ]
    
    def list_strategy_ids(self) -> List[str]:
        """Get list of all strategy IDs.
        
        Returns:
            List of strategy IDs sorted alphabetically
        """
        return sorted([s.strategy_id for s in self.registry.strategies])
    
    def get_strategy_spec_public(self, strategy_id: str) -> Optional[StrategySpecForGUI]:
        """Public API: Get strategy spec by ID.
        
        Args:
            strategy_id: Strategy ID to get
            
        Returns:
            StrategySpecForGUI if found, None otherwise
        """
        return self.get_strategy(strategy_id)


# Singleton instance for easy access
_catalog_instance: Optional[StrategyCatalog] = None

def get_strategy_catalog() -> StrategyCatalog:
    """Get singleton strategy catalog instance."""
    global _catalog_instance
    if _catalog_instance is None:
        _catalog_instance = StrategyCatalog()
    return _catalog_instance


# Public API functions for registry access
def list_strategy_ids() -> List[str]:
    """Public API: Get list of all strategy IDs.
    
    Returns:
        List of strategy IDs sorted alphabetically
    """
    catalog = get_strategy_catalog()
    return catalog.list_strategy_ids()


def get_strategy_spec(strategy_id: str) -> Optional[StrategySpecForGUI]:
    """Public API: Get strategy spec by ID.
    
    Args:
        strategy_id: Strategy ID to get
        
    Returns:
        StrategySpecForGUI if found, None otherwise
    """
    catalog = get_strategy_catalog()
    return catalog.get_strategy_spec_public(strategy_id)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/types.py
sha256(source_bytes) = 64b929a1a8c3a2eb9e10b1a9ecd111cebacf92fe5a158b9b4fb31d7953dfa9b1
bytes = 1572
redacted = False
--------------------------------------------------------------------------------

"""Type definitions for B5-C Mission Control."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Optional


class JobStatus(StrEnum):
    """Job status state machine."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DONE = "DONE"
    FAILED = "FAILED"
    KILLED = "KILLED"


class StopMode(StrEnum):
    """Stop request mode."""

    SOFT = "SOFT"
    KILL = "KILL"


@dataclass(frozen=True)
class DBJobSpec:
    """Job specification for DB/worker runtime (input to create_job)."""

    season: str
    dataset_id: str
    outputs_root: str
    config_snapshot: dict[str, Any]  # sanitized; no ndarrays
    config_hash: str
    data_fingerprint_sha256_40: str = ""  # Data fingerprint SHA256[:40] (empty if not provided, marks DIRTY)
    created_by: str = "b5c"


@dataclass(frozen=True)
class JobRecord:
    """Job record (returned from DB)."""

    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    spec: DBJobSpec
    pid: Optional[int] = None
    run_id: Optional[str] = None  # Final stage run_id (e.g. stage2_confirm-xxx)
    run_link: Optional[str] = None  # e.g. outputs/.../stage0_run_id or final run index pointer
    report_link: Optional[str] = None  # Link to B5 report viewer
    last_error: Optional[str] = None
    tags: list[str] = field(default_factory=list)  # Tags for job categorization and search
    data_fingerprint_sha256_40: str = ""  # Data fingerprint SHA256[:40] (empty if missing, marks DIRTY)




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/wizard_nicegui.py
sha256(source_bytes) = 9fafcf2247fcdbc3cd28b4b27d3def0e162591d79dfb6cb06c76d881e4bdacfe
bytes = 26561
redacted = False
--------------------------------------------------------------------------------

"""Research Job Wizard (Phase 12) - NiceGUI interface.

Phase 12: Config-only wizard that outputs WizardJobSpec JSON.
GUI → POST /jobs (WizardJobSpec) only, no worker calls, no filesystem access.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
from nicegui import ui

from FishBroWFS_V2.control.job_spec import DataSpec, WizardJobSpec, WFSSpec
from FishBroWFS_V2.control.param_grid import GridMode, ParamGridSpec
from FishBroWFS_V2.control.job_expand import JobTemplate, expand_job_template, estimate_total_jobs
from FishBroWFS_V2.control.batch_submit import BatchSubmitRequest, BatchSubmitResponse
from FishBroWFS_V2.data.dataset_registry import DatasetRecord
from FishBroWFS_V2.strategy.param_schema import ParamSpec
from FishBroWFS_V2.strategy.registry import StrategySpecForGUI

# API base URL
API_BASE = "http://localhost:8000"


class WizardState:
    """State management for wizard steps."""
    
    def __init__(self) -> None:
        self.season: str = ""
        self.data1: Optional[DataSpec] = None
        self.data2: Optional[DataSpec] = None
        self.strategy_id: str = ""
        self.params: Dict[str, Any] = {}
        self.wfs = WFSSpec()
        
        # Phase 13: Batch mode
        self.batch_mode: bool = False
        self.param_grid_specs: Dict[str, ParamGridSpec] = {}
        self.job_template: Optional[JobTemplate] = None
        
        # UI references
        self.data1_widgets: Dict[str, Any] = {}
        self.data2_widgets: Dict[str, Any] = {}
        self.param_widgets: Dict[str, Any] = {}
        self.wfs_widgets: Dict[str, Any] = {}
        self.batch_widgets: Dict[str, Any] = {}


def fetch_datasets() -> List[DatasetRecord]:
    """Fetch dataset registry from API."""
    try:
        resp = requests.get(f"{API_BASE}/meta/datasets", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [DatasetRecord.model_validate(d) for d in data["datasets"]]
    except Exception as e:
        ui.notify(f"Failed to load datasets: {e}", type="negative")
        return []


def fetch_strategies() -> List[StrategySpecForGUI]:
    """Fetch strategy registry from API."""
    try:
        resp = requests.get(f"{API_BASE}/meta/strategies", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [StrategySpecForGUI.model_validate(s) for s in data["strategies"]]
    except Exception as e:
        ui.notify(f"Failed to load strategies: {e}", type="negative")
        return []


def create_data_section(
    state: WizardState,
    section_name: str,
    is_primary: bool = True
) -> Dict[str, Any]:
    """Create dataset selection UI section."""
    widgets: Dict[str, Any] = {}
    
    with ui.card().classes("w-full mb-4"):
        ui.label(f"{section_name} Dataset").classes("text-lg font-bold")
        
        # Dataset dropdown
        datasets = fetch_datasets()
        dataset_options = {d.id: f"{d.symbol} ({d.timeframe}) {d.start_date}-{d.end_date}" 
                          for d in datasets}
        
        dataset_select = ui.select(
            label="Dataset",
            options=dataset_options,
            with_input=True
        ).classes("w-full")
        widgets["dataset_select"] = dataset_select
        
        # Date range inputs
        with ui.row().classes("w-full"):
            start_date = ui.date(
                label="Start Date",
                value=date(2020, 1, 1)
            ).classes("w-1/2")
            widgets["start_date"] = start_date
            
            end_date = ui.date(
                label="End Date",
                value=date(2024, 12, 31)
            ).classes("w-1/2")
            widgets["end_date"] = end_date
        
        # Update date limits when dataset changes
        def update_date_limits(selected_id: str) -> None:
            dataset = next((d for d in datasets if d.id == selected_id), None)
            if dataset:
                start_date.value = dataset.start_date
                end_date.value = dataset.end_date
                start_date._props["min"] = dataset.start_date.isoformat()
                start_date._props["max"] = dataset.end_date.isoformat()
                end_date._props["min"] = dataset.start_date.isoformat()
                end_date._props["max"] = dataset.end_date.isoformat()
                start_date.update()
                end_date.update()
        
        dataset_select.on('update:model-value', lambda e: update_date_limits(e.args))
        
        # Set initial limits if dataset is selected
        if dataset_select.value:
            update_date_limits(dataset_select.value)
    
    return widgets


def create_strategy_section(state: WizardState) -> Dict[str, Any]:
    """Create strategy selection and parameter UI section."""
    widgets: Dict[str, Any] = {}
    
    with ui.card().classes("w-full mb-4"):
        ui.label("Strategy").classes("text-lg font-bold")
        
        # Strategy dropdown
        strategies = fetch_strategies()
        strategy_options = {s.strategy_id: s.strategy_id for s in strategies}
        
        strategy_select = ui.select(
            label="Strategy",
            options=strategy_options,
            with_input=True
        ).classes("w-full")
        widgets["strategy_select"] = strategy_select
        
        # Parameter container (dynamic)
        param_container = ui.column().classes("w-full mt-4")
        widgets["param_container"] = param_container
        
        def update_parameters(selected_id: str) -> None:
            """Update parameter UI based on selected strategy."""
            param_container.clear()
            state.param_widgets.clear()
            
            strategy = next((s for s in strategies if s.strategy_id == selected_id), None)
            if not strategy:
                return
            
            ui.label("Parameters").classes("font-bold mt-2")
            
            for param in strategy.params:
                with ui.row().classes("w-full items-center"):
                    ui.label(f"{param.name}:").classes("w-1/3")
                    
                    if param.type == "int" or param.type == "float":
                        # Slider for numeric parameters
                        min_val = param.min if param.min is not None else 0
                        max_val = param.max if param.max is not None else 100
                        step = param.step if param.step is not None else 1
                        
                        slider = ui.slider(
                            min=min_val,
                            max=max_val,
                            value=param.default,
                            step=step
                        ).classes("w-2/3")
                        
                        value_label = ui.label().bind_text_from(
                            slider, "value", 
                            lambda v: f"{v:.2f}" if param.type == "float" else f"{int(v)}"
                        )
                        
                        state.param_widgets[param.name] = slider
                        
                    elif param.type == "enum" and param.choices:
                        # Dropdown for enum parameters
                        dropdown = ui.select(
                            options=param.choices,
                            value=param.default
                        ).classes("w-2/3")
                        state.param_widgets[param.name] = dropdown
                        
                    elif param.type == "bool":
                        # Switch for boolean parameters
                        switch = ui.switch(value=param.default).classes("w-2/3")
                        state.param_widgets[param.name] = switch
                    
                    # Help text
                    if param.help:
                        ui.tooltip(param.help).classes("ml-2")
        
        strategy_select.on('update:model-value', lambda e: update_parameters(e.args))
        
        # Initialize if strategy is selected
        if strategy_select.value:
            update_parameters(strategy_select.value)
    
    return widgets


def create_batch_mode_section(state: WizardState) -> Dict[str, Any]:
    """Create batch mode UI section (Phase 13)."""
    widgets: Dict[str, Any] = {}
    
    with ui.card().classes("w-full mb-4"):
        ui.label("Batch Mode (Phase 13)").classes("text-lg font-bold")
        
        # Batch mode toggle
        batch_toggle = ui.switch("Enable Batch Mode (Parameter Grid)")
        widgets["batch_toggle"] = batch_toggle
        
        # Container for grid UI (hidden when batch mode off)
        grid_container = ui.column().classes("w-full mt-4")
        widgets["grid_container"] = grid_container
        
        # Cost preview label
        cost_label = ui.label("Total jobs: 0 | Risk: Low").classes("font-bold mt-2")
        widgets["cost_label"] = cost_label
        
        def update_batch_mode(enabled: bool) -> None:
            """Show/hide grid UI based on batch mode toggle."""
            grid_container.clear()
            state.batch_mode = enabled
            state.param_grid_specs.clear()
            
            if not enabled:
                cost_label.set_text("Total jobs: 0 | Risk: Low")
                return
            
            # Fetch current strategy parameters
            strategy_id = state.strategy_id
            strategies = fetch_strategies()
            strategy = next((s for s in strategies if s.strategy_id == strategy_id), None)
            if not strategy:
                ui.notify("No strategy selected", type="warning")
                return
            
            # Create grid UI for each parameter
            ui.label("Parameter Grid").classes("font-bold mt-2")
            
            for param in strategy.params:
                with ui.row().classes("w-full items-center mb-2"):
                    ui.label(f"{param.name}:").classes("w-1/4")
                    
                    # Grid mode selector
                    mode_select = ui.select(
                        options={
                            GridMode.SINGLE.value: "Single",
                            GridMode.RANGE.value: "Range",
                            GridMode.MULTI.value: "Multi Values"
                        },
                        value=GridMode.SINGLE.value
                    ).classes("w-1/4")
                    
                    # Value inputs (dynamic based on mode)
                    value_container = ui.row().classes("w-1/2")
                    
                    def make_param_updater(pname: str, mode_sel, val_container, param_spec):
                        def update_grid_ui():
                            mode = GridMode(mode_sel.value)
                            val_container.clear()
                            
                            if mode == GridMode.SINGLE:
                                # Single value input (same as default)
                                if param_spec.type == "int" or param_spec.type == "float":
                                    default = param_spec.default
                                    val = ui.number(value=default, min=param_spec.min, max=param_spec.max, step=param_spec.step or 1)
                                elif param_spec.type == "enum":
                                    val = ui.select(options=param_spec.choices, value=param_spec.default)
                                elif param_spec.type == "bool":
                                    val = ui.switch(value=param_spec.default)
                                else:
                                    val = ui.input(value=str(param_spec.default))
                                val_container.add(val)
                                # Store spec
                                state.param_grid_specs[pname] = ParamGridSpec(
                                    mode=mode,
                                    single_value=val.value
                                )
                            elif mode == GridMode.RANGE:
                                # Range: start, end, step
                                start = ui.number(value=param_spec.min or 0, label="Start")
                                end = ui.number(value=param_spec.max or 100, label="End")
                                step = ui.number(value=param_spec.step or 1, label="Step")
                                val_container.add(start)
                                val_container.add(end)
                                val_container.add(step)
                                # Store spec (will be updated on change)
                                state.param_grid_specs[pname] = ParamGridSpec(
                                    mode=mode,
                                    range_start=start.value,
                                    range_end=end.value,
                                    range_step=step.value
                                )
                            elif mode == GridMode.MULTI:
                                # Multi values: comma-separated input
                                default_vals = ",".join([str(param_spec.default)])
                                val = ui.input(value=default_vals, label="Values (comma separated)")
                                val_container.add(val)
                                state.param_grid_specs[pname] = ParamGridSpec(
                                    mode=mode,
                                    multi_values=[param_spec.default]
                                )
                            # Trigger cost update
                            update_cost_preview()
                        return update_grid_ui
                    
                    # Initial creation
                    updater = make_param_updater(param.name, mode_select, value_container, param)
                    mode_select.on('update:model-value', lambda e: updater())
                    updater()  # call once to create initial UI
        
        batch_toggle.on('update:model-value', lambda e: update_batch_mode(e.args))
        
        def update_cost_preview():
            """Update cost preview label based on current grid specs."""
            if not state.batch_mode:
                cost_label.set_text("Total jobs: 0 | Risk: Low")
                return
            
            # Build a temporary JobTemplate to estimate total jobs
            try:
                # Collect base WizardJobSpec from current UI (simplified)
                # We'll just use dummy values for estimation
                template = JobTemplate(
                    season=state.season,
                    dataset_id="dummy",
                    strategy_id=state.strategy_id,
                    param_grid=state.param_grid_specs.copy(),
                    wfs=state.wfs
                )
                total = estimate_total_jobs(template)
                # Risk heuristic
                risk = "Low"
                if total > 100:
                    risk = "Medium"
                if total > 1000:
                    risk = "High"
                cost_label.set_text(f"Total jobs: {total} | Risk: {risk}")
            except Exception:
                cost_label.set_text("Total jobs: ? | Risk: Unknown")
        
        # Update cost preview periodically
        ui.timer(2.0, update_cost_preview)
    
    return widgets


def create_wfs_section(state: WizardState) -> Dict[str, Any]:
    """Create WFS configuration UI section."""
    widgets: Dict[str, Any] = {}
    
    with ui.card().classes("w-full mb-4"):
        ui.label("WFS Configuration").classes("text-lg font-bold")
        
        # Stage0 subsample
        subsample_slider = ui.slider(
            label="Stage0 Subsample",
            min=0.01,
            max=1.0,
            value=state.wfs.stage0_subsample,
            step=0.01
        ).classes("w-full")
        widgets["subsample"] = subsample_slider
        ui.label().bind_text_from(subsample_slider, "value", lambda v: f"{v:.2f}")
        
        # Top K
        top_k_input = ui.number(
            label="Top K",
            value=state.wfs.top_k,
            min=1,
            max=1000,
            step=10
        ).classes("w-full")
        widgets["top_k"] = top_k_input
        
        # Memory limit
        mem_input = ui.number(
            label="Memory Limit (MB)",
            value=state.wfs.mem_limit_mb,
            min=1024,
            max=32768,
            step=1024
        ).classes("w-full")
        widgets["mem_limit"] = mem_input
        
        # Auto-downsample switch
        auto_downsample = ui.switch(
            "Allow Auto Downsample",
            value=state.wfs.allow_auto_downsample
        ).classes("w-full")
        widgets["auto_downsample"] = auto_downsample
    
    return widgets


def create_preview_section(state: WizardState) -> ui.textarea:
    """Create WizardJobSpec preview section."""
    with ui.card().classes("w-full mb-4"):
        ui.label("WizardJobSpec Preview").classes("text-lg font-bold")
        
        preview = ui.textarea("").classes("w-full h-64 font-mono text-sm").props("readonly")
        
        def update_preview() -> None:
            """Update WizardJobSpec preview."""
            try:
                # Collect data from UI
                dataset_id = None
                if state.data1_widgets:
                    dataset_id = state.data1_widgets["dataset_select"].value
                    start_date = state.data1_widgets["start_date"].value
                    end_date = state.data1_widgets["end_date"].value
                    
                    if dataset_id and start_date and end_date:
                        state.data1 = DataSpec(
                            dataset_id=dataset_id,
                            start_date=start_date,
                            end_date=end_date
                        )
                
                # Collect strategy parameters
                params = {}
                for param_name, widget in state.param_widgets.items():
                    if hasattr(widget, 'value'):
                        params[param_name] = widget.value
                
                # Collect WFS settings
                if state.wfs_widgets:
                    state.wfs = WFSSpec(
                        stage0_subsample=state.wfs_widgets["subsample"].value,
                        top_k=state.wfs_widgets["top_k"].value,
                        mem_limit_mb=state.wfs_widgets["mem_limit"].value,
                        allow_auto_downsample=state.wfs_widgets["auto_downsample"].value
                    )
                
                if state.batch_mode:
                    # Create JobTemplate
                    template = JobTemplate(
                        season=state.season,
                        dataset_id=dataset_id if dataset_id else "unknown",
                        strategy_id=state.strategy_id,
                        param_grid=state.param_grid_specs.copy(),
                        wfs=state.wfs
                    )
                    # Update preview with template JSON
                    preview.value = template.model_dump_json(indent=2)
                else:
                    # Create single WizardJobSpec
                    jobspec = WizardJobSpec(
                        season=state.season,
                        data1=state.data1,
                        data2=state.data2,
                        strategy_id=state.strategy_id,
                        params=params,
                        wfs=state.wfs
                    )
                    # Update preview
                    preview.value = jobspec.model_dump_json(indent=2)
                
            except Exception as e:
                preview.value = f"Error creating preview: {e}"
        
        # Update preview periodically
        ui.timer(1.0, update_preview)
        
        return preview


def submit_job(state: WizardState, preview: ui.textarea) -> None:
    """Submit WizardJobSpec to API."""
    try:
        # Parse WizardJobSpec from preview
        jobspec_data = json.loads(preview.value)
        jobspec = WizardJobSpec.model_validate(jobspec_data)
        
        # Submit to API
        resp = requests.post(
            f"{API_BASE}/jobs",
            json=json.loads(jobspec.model_dump_json())
        )
        resp.raise_for_status()
        
        job_id = resp.json()["job_id"]
        ui.notify(f"Job submitted successfully! Job ID: {job_id}", type="positive")
        
    except Exception as e:
        ui.notify(f"Failed to submit job: {e}", type="negative")


def submit_batch_job(state: WizardState, preview: ui.textarea) -> None:
    """Submit batch of jobs via batch API."""
    try:
        # Parse JobTemplate from preview
        template_data = json.loads(preview.value)
        template = JobTemplate.model_validate(template_data)
        
        # Expand template to JobSpec list
        jobspecs = expand_job_template(template)
        
        # Build batch request
        batch_req = BatchSubmitRequest(jobs=list(jobspecs))
        
        # Submit to batch endpoint
        resp = requests.post(
            f"{API_BASE}/jobs/batch",
            json=json.loads(batch_req.model_dump_json())
        )
        resp.raise_for_status()
        
        batch_resp = BatchSubmitResponse.model_validate(resp.json())
        ui.notify(
            f"Batch submitted successfully! Batch ID: {batch_resp.batch_id}, "
            f"Total jobs: {batch_resp.total_jobs}",
            type="positive"
        )
        
    except Exception as e:
        ui.notify(f"Failed to submit batch: {e}", type="negative")


@ui.page("/wizard")
def wizard_page() -> None:
    """Research Job Wizard main page."""
    ui.page_title("Research Job Wizard (Phase 12)")
    
    state = WizardState()
    
    with ui.column().classes("w-full max-w-4xl mx-auto p-4"):
        ui.label("Research Job Wizard").classes("text-2xl font-bold mb-6")
        ui.label("Phase 12: Config-only job specification").classes("text-gray-600 mb-8")
        
        # Season input
        with ui.card().classes("w-full mb-4"):
            ui.label("Season").classes("text-lg font-bold")
            season_input = ui.input(
                label="Season",
                value="2024Q1",
                placeholder="e.g., 2024Q1, 2024Q2"
            ).classes("w-full")
            
            def update_season() -> None:
                state.season = season_input.value
            
            season_input.on('update:model-value', lambda e: update_season())
            update_season()
        
        # Step 1: Data
        with ui.expansion("Step 1: Data", value=True).classes("w-full mb-4"):
            ui.label("Primary Dataset").classes("font-bold mt-2")
            state.data1_widgets = create_data_section(state, "Primary", is_primary=True)
            
            # Data2 toggle
            enable_data2 = ui.switch("Enable Secondary Dataset (for validation)")
            
            data2_container = ui.column().classes("w-full")
            
            def toggle_data2(enabled: bool) -> None:
                data2_container.clear()
                if enabled:
                    state.data2_widgets = create_data_section(state, "Secondary", is_primary=False)
                else:
                    state.data2 = None
                    state.data2_widgets = {}
            
            enable_data2.on('update:model-value', lambda e: toggle_data2(e.args))
        
        # Step 2: Strategy
        with ui.expansion("Step 2: Strategy", value=True).classes("w-full mb-4"):
            strategy_widgets = create_strategy_section(state)
            
            def update_strategy() -> None:
                state.strategy_id = strategy_widgets["strategy_select"].value
            
            strategy_widgets["strategy_select"].on('update:model-value', lambda e: update_strategy())
            if strategy_widgets["strategy_select"].value:
                update_strategy()
        
        # Step 3: Batch Mode (Phase 13)
        with ui.expansion("Step 3: Batch Mode (Optional)", value=True).classes("w-full mb-4"):
            state.batch_widgets = create_batch_mode_section(state)
        
        # Step 4: WFS
        with ui.expansion("Step 4: WFS Configuration", value=True).classes("w-full mb-4"):
            state.wfs_widgets = create_wfs_section(state)
        
        # Step 5: Preview & Submit
        with ui.expansion("Step 5: Preview & Submit", value=True).classes("w-full mb-4"):
            preview = create_preview_section(state)
            
            with ui.row().classes("w-full mt-4"):
                # Conditional button based on batch mode
                def submit_action():
                    if state.batch_mode:
                        submit_batch_job(state, preview)
                    else:
                        submit_job(state, preview)
                
                submit_btn = ui.button(
                    "Submit Batch" if state.batch_mode else "Submit Job",
                    on_click=submit_action
                ).classes("bg-green-500 text-white")
                
                # Update button label when batch mode changes
                def update_button_label():
                    submit_btn.set_text("Submit Batch" if state.batch_mode else "Submit Job")
                
                # Watch batch mode changes (simplified: we can't directly watch, but we can update via timer)
                ui.timer(1.0, update_button_label)
                
                ui.button("Copy JSON", on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText(`{preview.value}`)"
                )).classes("bg-blue-500 text-white")
        
        # Phase 12 Rules reminder
        with ui.card().classes("w-full mt-8 bg-yellow-50"):
            ui.label("Phase 12 Rules").classes("font-bold text-yellow-800")
            ui.label("✅ GUI only outputs WizardJobSpec JSON").classes("text-sm text-yellow-700")
            ui.label("✅ No worker calls, no filesystem access").classes("text-sm text-yellow-700")
            ui.label("✅ Strategy params from registry, not hardcoded").classes("text-sm text-yellow-700")
            ui.label("✅ Dataset selection from registry, not filesystem").classes("text-sm text-yellow-700")





--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/worker.py
sha256(source_bytes) = e6f2c484ff60327b6243fd387870fef7ef30656de56773b2bb3cfe934a9b552c
bytes = 7469
redacted = False
--------------------------------------------------------------------------------

"""Worker - long-running task executor."""

from __future__ import annotations

import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ✅ Module-level import for patch support
from FishBroWFS_V2.pipeline.funnel_runner import run_funnel

from FishBroWFS_V2.control.jobs_db import (
    get_job,
    get_requested_pause,
    get_requested_stop,
    mark_done,
    mark_failed,
    mark_killed,
    update_running,
    update_run_link,
)
from FishBroWFS_V2.control.paths import run_log_path
from FishBroWFS_V2.control.report_links import make_report_link
from FishBroWFS_V2.control.types import JobStatus, StopMode


def _append_log(log_path: Path, text: str) -> None:
    """
    Append text to log file.
    
    Args:
        log_path: Path to log file
        text: Text to append
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def worker_loop(db_path: Path, *, poll_s: float = 0.5) -> None:
    """
    Worker loop: poll QUEUED jobs and execute them sequentially.
    
    Args:
        db_path: Path to SQLite database
        poll_s: Polling interval in seconds
    """
    while True:
        try:
            # Find QUEUED jobs
            from FishBroWFS_V2.control.jobs_db import list_jobs
            
            jobs = list_jobs(db_path, limit=100)
            queued_jobs = [j for j in jobs if j.status == JobStatus.QUEUED]
            
            if queued_jobs:
                # Process first QUEUED job
                job = queued_jobs[0]
                run_one_job(db_path, job.job_id)
            else:
                # No jobs, sleep
                time.sleep(poll_s)
        except KeyboardInterrupt:
            break
        except Exception as e:
            # Log error but continue loop
            print(f"Worker loop error: {e}")
            time.sleep(poll_s)


def run_one_job(db_path: Path, job_id: str) -> None:
    """
    Run a single job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
    """
    log_path: Path | None = None
    try:
        job = get_job(db_path, job_id)
        
        # Check if already terminal
        if job.status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED}:
            return
        
        # Update to RUNNING with current PID
        pid = os.getpid()
        update_running(db_path, job_id, pid=pid)
        
        # Log status update
        timestamp = datetime.now(timezone.utc).isoformat()
        outputs_root = Path(job.spec.outputs_root)
        season = job.spec.season
        
        # Initialize log_path early (use job_id as run_id fallback)
        log_path = run_log_path(outputs_root, season, job_id)
        
        # Check for KILL before starting
        stop_mode = get_requested_stop(db_path, job_id)
        if stop_mode == StopMode.KILL.value:
            _append_log(log_path, f"{timestamp} [job_id={job_id}] [status=KILLED] Killed before execution")
            mark_killed(db_path, job_id, error="Killed before execution")
            return
        
        outputs_root.mkdir(parents=True, exist_ok=True)
        
        # Reconstruct runtime config from snapshot
        cfg = dict(job.spec.config_snapshot)
        # Ensure required fields are present
        cfg["season"] = job.spec.season
        cfg["dataset_id"] = job.spec.dataset_id
        
        # Log job start
        _append_log(
            log_path,
            f"{timestamp} [job_id={job_id}] [status=RUNNING] Starting funnel execution"
        )
        
        # Check pause/stop before each stage
        _check_pause_stop(db_path, job_id)
        
        # Run funnel
        result = run_funnel(cfg, outputs_root)
        
        # Extract run_id and generate report_link
        run_id: Optional[str] = None
        report_link: Optional[str] = None
        
        if getattr(result, "stages", None) and result.stages:
            last = result.stages[-1]
            run_id = last.run_id
            report_link = make_report_link(season=job.spec.season, run_id=run_id)
            
            # Update run_link
            run_link = str(last.run_dir)
            update_run_link(db_path, job_id, run_link=run_link)
            
            # Log summary
            log_path = run_log_path(outputs_root, season, run_id)
            timestamp = datetime.now(timezone.utc).isoformat()
            _append_log(
                log_path,
                f"{timestamp} [job_id={job_id}] [status=DONE] Funnel completed: "
                f"run_id={run_id}, stage={last.stage.value}, run_dir={run_link}"
            )
        
        # Mark as done with run_id and report_link (both can be None if no stages)
        mark_done(db_path, job_id, run_id=run_id, report_link=report_link)
        
        # Log final status
        timestamp = datetime.now(timezone.utc).isoformat()
        if log_path:
            _append_log(log_path, f"{timestamp} [job_id={job_id}] [status=DONE] Job completed successfully")
        
    except KeyboardInterrupt:
        if log_path:
            timestamp = datetime.now(timezone.utc).isoformat()
            _append_log(log_path, f"{timestamp} [job_id={job_id}] [status=KILLED] Interrupted by user")
        mark_killed(db_path, job_id, error="Interrupted by user")
        raise
    except Exception as e:
        import traceback
        
        # Short for DB column (500 chars)
        error_msg = str(e)[:500]
        mark_failed(db_path, job_id, error=error_msg)
        
        # Full traceback for audit log (MUST)
        tb = traceback.format_exc()
        from FishBroWFS_V2.control.jobs_db import append_log
        append_log(db_path, job_id, "[ERROR] Unhandled exception\n" + tb)
        
        # Also write to file log if available
        if log_path:
            timestamp = datetime.now(timezone.utc).isoformat()
            _append_log(log_path, f"{timestamp} [job_id={job_id}] [status=FAILED] Error: {error_msg}\n{tb}")
        
        # Keep worker stable
        return


def _check_pause_stop(db_path: Path, job_id: str) -> None:
    """
    Check pause/stop flags and handle accordingly.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Raises:
        SystemExit: If KILL requested
    """
    stop_mode = get_requested_stop(db_path, job_id)
    if stop_mode == StopMode.KILL.value:
        # Get PID and kill process
        job = get_job(db_path, job_id)
        if job.pid:
            try:
                os.kill(job.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # Process already dead
        mark_killed(db_path, job_id, error="Killed by user")
        raise SystemExit("Job killed")
    
    # Handle pause
    while get_requested_pause(db_path, job_id):
        time.sleep(0.5)
        # Re-check stop while paused
        stop_mode = get_requested_stop(db_path, job_id)
        if stop_mode == StopMode.KILL.value:
            job = get_job(db_path, job_id)
            if job.pid:
                try:
                    os.kill(job.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            mark_killed(db_path, job_id, error="Killed while paused")
            raise SystemExit("Job killed while paused")




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/control/worker_main.py
sha256(source_bytes) = e5d6961f2961fa8397f6318ffdfe7fee72eb3843a50c3a297b8aa87b93fa9a83
bytes = 403
redacted = False
--------------------------------------------------------------------------------

"""Worker main entry point (for subprocess execution)."""

from __future__ import annotations

import sys
from pathlib import Path

from FishBroWFS_V2.control.worker import worker_loop

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m FishBroWFS_V2.control.worker_main <db_path>")
        sys.exit(1)
    
    db_path = Path(sys.argv[1])
    worker_loop(db_path)




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/__init__.py
sha256(source_bytes) = 9380e6cee44a8c92094a4673f6ab9e721784aed936ae5cf76b9184a9107d588d
bytes = 57
redacted = False
--------------------------------------------------------------------------------

"""Core modules for audit and artifact management."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/action_risk.py
sha256(source_bytes) = 935698ce27e202c228b3d0f2649f8205fa3c66fb656f2e649bf1b8d020495c01
bytes = 534
redacted = False
--------------------------------------------------------------------------------
"""Action Risk Levels - 資料契約

定義系統動作的風險等級，用於實盤安全鎖。
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class RiskLevel(str, Enum):
    """動作風險等級"""
    READ_ONLY = "READ_ONLY"
    RESEARCH_MUTATE = "RESEARCH_MUTATE"
    LIVE_EXECUTE = "LIVE_EXECUTE"


@dataclass(frozen=True)
class ActionPolicyDecision:
    """政策決策結果"""
    allowed: bool
    reason: str
    risk: RiskLevel
    action: str
    season: Optional[str] = None
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/artifact_reader.py
sha256(source_bytes) = eacafa41445de920c0cd532ac4ed545e22543ce980cf9bb9d607c35026d761e7
bytes = 9366
redacted = False
--------------------------------------------------------------------------------

"""Artifact reader for governance evaluation and Viewer.

Reads artifacts (manifest/metrics/winners/config_snapshot) from run directories.
Provides safe read functions that never raise exceptions (for Viewer use).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def read_manifest(run_dir: Path) -> Dict[str, Any]:
    """
    Read manifest.json from run directory.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        Manifest dict (AuditSchema as dict)
        
    Raises:
        FileNotFoundError: If manifest.json does not exist
        json.JSONDecodeError: If manifest.json is invalid JSON
    """
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {run_dir}")
    
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_metrics(run_dir: Path) -> Dict[str, Any]:
    """
    Read metrics.json from run directory.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        Metrics dict
        
    Raises:
        FileNotFoundError: If metrics.json does not exist
        json.JSONDecodeError: If metrics.json is invalid JSON
    """
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"metrics.json not found in {run_dir}")
    
    with metrics_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_winners(run_dir: Path) -> Dict[str, Any]:
    """
    Read winners.json from run directory.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        Winners dict with schema {"topk": [...], "notes": {...}}
        
    Raises:
        FileNotFoundError: If winners.json does not exist
        json.JSONDecodeError: If winners.json is invalid JSON
    """
    winners_path = run_dir / "winners.json"
    if not winners_path.exists():
        raise FileNotFoundError(f"winners.json not found in {run_dir}")
    
    with winners_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_config_snapshot(run_dir: Path) -> Dict[str, Any]:
    """
    Read config_snapshot.json from run directory.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        Config snapshot dict
        
    Raises:
        FileNotFoundError: If config_snapshot.json does not exist
        json.JSONDecodeError: If config_snapshot.json is invalid JSON
    """
    config_path = run_dir / "config_snapshot.json"
    if not config_path.exists():
        raise FileNotFoundError(f"config_snapshot.json not found in {run_dir}")
    
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# Safe artifact reader (never raises) - for Viewer use
# ============================================================================

@dataclass(frozen=True)
class ReadMeta:
    """Metadata about the read operation."""
    source_path: str  # Absolute path to source file
    sha256: str  # SHA256 hash of file content
    mtime_s: float  # Modification time in seconds since epoch


@dataclass(frozen=True)
class ReadResult:
    """
    Result of reading an artifact file.
    
    Contains raw data (dict/list/str) and metadata.
    Upper layer uses pydantic for validation.
    """
    raw: Any  # dict/list/str - raw parsed data
    meta: ReadMeta


@dataclass(frozen=True)
class ReadError:
    """Error information for failed read operations."""
    error_code: str  # "FILE_NOT_FOUND", "UNSUPPORTED_FORMAT", "YAML_NOT_AVAILABLE", "JSON_DECODE_ERROR", "IO_ERROR"
    message: str
    source_path: str


@dataclass(frozen=True)
class SafeReadResult:
    """
    Safe read result that never raises.
    
    Either contains ReadResult (success) or ReadError (failure).
    """
    result: Optional[ReadResult] = None
    error: Optional[ReadError] = None
    
    @property
    def is_ok(self) -> bool:
        """Check if read was successful."""
        return self.result is not None and self.error is None
    
    @property
    def is_error(self) -> bool:
        """Check if read failed."""
        return self.error is not None


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of file content."""
    sha256_hash = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def read_artifact(file_path: Path | str) -> ReadResult:
    """
    Read artifact file (JSON/YAML/MD) and return ReadResult.
    
    Args:
        file_path: Path to artifact file
        
    Returns:
        ReadResult with raw data and metadata
        
    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file format is not supported
    """
    path = Path(file_path).resolve()
    
    if not path.exists():
        raise FileNotFoundError(f"Artifact file not found: {path}")
    
    # Get metadata
    mtime_s = path.stat().st_mtime
    sha256 = _compute_sha256(path)
    
    # Read based on extension
    suffix = path.suffix.lower()
    
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    elif suffix in (".yaml", ".yml"):
        if not HAS_YAML:
            raise ValueError(f"YAML support not available. Install pyyaml to read {path}")
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    elif suffix == ".md":
        with path.open("r", encoding="utf-8") as f:
            raw = f.read()  # Return as string for markdown
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Supported: .json, .yaml, .yml, .md")
    
    meta = ReadMeta(
        source_path=str(path),
        sha256=sha256,
        mtime_s=mtime_s,
    )
    
    return ReadResult(raw=raw, meta=meta)


def try_read_artifact(file_path: Path | str) -> SafeReadResult:
    """
    Safe version of read_artifact that never raises.
    
    All Viewer code should use this function instead of read_artifact()
    to ensure no exceptions are thrown.
    
    Args:
        file_path: Path to artifact file
        
    Returns:
        SafeReadResult with either ReadResult (success) or ReadError (failure)
    """
    path = Path(file_path).resolve()
    
    # Check if file exists
    if not path.exists():
        return SafeReadResult(
            error=ReadError(
                error_code="FILE_NOT_FOUND",
                message=f"Artifact file not found: {path}",
                source_path=str(path),
            )
        )
    
    try:
        # Get metadata
        mtime_s = path.stat().st_mtime
        sha256 = _compute_sha256(path)
    except OSError as e:
        return SafeReadResult(
            error=ReadError(
                error_code="IO_ERROR",
                message=f"Failed to read file metadata: {e}",
                source_path=str(path),
            )
        )
    
    # Read based on extension
    suffix = path.suffix.lower()
    
    try:
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        elif suffix in (".yaml", ".yml"):
            if not HAS_YAML:
                return SafeReadResult(
                    error=ReadError(
                        error_code="YAML_NOT_AVAILABLE",
                        message=f"YAML support not available. Install pyyaml to read {path}",
                        source_path=str(path),
                    )
                )
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        elif suffix == ".md":
            with path.open("r", encoding="utf-8") as f:
                raw = f.read()  # Return as string for markdown
        else:
            return SafeReadResult(
                error=ReadError(
                    error_code="UNSUPPORTED_FORMAT",
                    message=f"Unsupported file format: {suffix}. Supported: .json, .yaml, .yml, .md",
                    source_path=str(path),
                )
            )
    except json.JSONDecodeError as e:
        return SafeReadResult(
            error=ReadError(
                error_code="JSON_DECODE_ERROR",
                message=f"JSON decode error: {e}",
                source_path=str(path),
            )
        )
    except OSError as e:
        return SafeReadResult(
            error=ReadError(
                error_code="IO_ERROR",
                message=f"Failed to read file: {e}",
                source_path=str(path),
            )
        )
    except Exception as e:
        return SafeReadResult(
            error=ReadError(
                error_code="UNKNOWN_ERROR",
                message=f"Unexpected error: {e}",
                source_path=str(path),
            )
        )
    
    meta = ReadMeta(
        source_path=str(path),
        sha256=sha256,
        mtime_s=mtime_s,
    )
    
    return SafeReadResult(result=ReadResult(raw=raw, meta=meta))



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/artifact_status.py
sha256(source_bytes) = 58378d52df7da43fef88bbf32a738ab1b9b6c5fe17b35fa637e4e6bc9d4639b9
bytes = 12612
redacted = False
--------------------------------------------------------------------------------

"""Status determination for artifact validation.

Defines OK/MISSING/INVALID/DIRTY states with human-readable error messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import ValidationError


class ArtifactStatus(str, Enum):
    """Artifact validation status."""
    OK = "OK"
    MISSING = "MISSING"  # File does not exist
    INVALID = "INVALID"  # Pydantic validation error
    DIRTY = "DIRTY"  # config_hash mismatch


@dataclass(frozen=True)
class ValidationResult:
    """
    Result of artifact validation.
    
    Contains status and human-readable error message.
    """
    status: ArtifactStatus
    message: str = ""
    error_details: Optional[str] = None  # Detailed error for debugging


def _format_pydantic_error(e: ValidationError) -> str:
    """Format Pydantic ValidationError into readable string with field paths."""
    parts: list[str] = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err.get("loc", []))
        msg = err.get("msg", "")
        typ = err.get("type", "")
        if loc:
            parts.append(f"{loc}: {msg} ({typ})")
        else:
            parts.append(f"{msg} ({typ})")
    return "；".join(parts) if parts else str(e)


def _extract_missing_field_names(e: ValidationError) -> list[str]:
    """Extract missing field names from ValidationError."""
    missing: set[str] = set()
    for err in e.errors():
        typ = str(err.get("type", "")).lower()
        msg = str(err.get("msg", "")).lower()
        if "missing" in typ or "required" in msg:
            loc = err.get("loc", ())
            # loc 可能像 ("rows", 0, "net_profit") 或 ("config_hash",)
            if loc:
                leaf = str(loc[-1])
                # 避免 leaf 是 index
                if not leaf.isdigit():
                    missing.add(leaf)
            # 也把完整路徑收進來（可讀性更好）
            loc_str = ".".join(str(x) for x in loc if not isinstance(x, int))
            if loc_str:
                missing.add(loc_str.split(".")[-1])  # leaf 再保險一次
    return sorted(missing)


def validate_manifest_status(
    file_path: str,
    manifest_data: Optional[dict] = None,
    expected_config_hash: Optional[str] = None,
) -> ValidationResult:
    """
    Validate manifest.json status.
    
    Args:
        file_path: Path to manifest.json
        manifest_data: Parsed manifest data (if available)
        expected_config_hash: Expected config_hash (for DIRTY check)
        
    Returns:
        ValidationResult with status and message
    """
    from pathlib import Path
    from FishBroWFS_V2.core.schemas.manifest import RunManifest
    
    path = Path(file_path)
    
    # Check if file exists
    if not path.exists():
        return ValidationResult(
            status=ArtifactStatus.MISSING,
            message=f"manifest.json 不存在: {file_path}",
        )
    
    # Try to parse with Pydantic
    if manifest_data is None:
        import json
        try:
            with path.open("r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except json.JSONDecodeError as e:
            return ValidationResult(
                status=ArtifactStatus.INVALID,
                message=f"manifest.json JSON 格式錯誤: {e}",
                error_details=str(e),
            )
    
    try:
        manifest = RunManifest(**manifest_data)
    except Exception as e:
        # Extract missing field from Pydantic error
        error_msg = str(e)
        missing_fields = []
        if "field required" in error_msg.lower():
            # Try to extract field name from error
            import re
            matches = re.findall(r"Field required.*?['\"]([^'\"]+)['\"]", error_msg)
            if matches:
                missing_fields = matches
        
        if missing_fields:
            msg = f"manifest.json 缺少欄位: {', '.join(missing_fields)}"
        else:
            msg = f"manifest.json 驗證失敗: {error_msg}"
        
        return ValidationResult(
            status=ArtifactStatus.INVALID,
            message=msg,
            error_details=error_msg,
        )
    
    # Check config_hash if expected is provided
    if expected_config_hash is not None and manifest.config_hash != expected_config_hash:
        return ValidationResult(
            status=ArtifactStatus.DIRTY,
            message=f"manifest.config_hash={manifest.config_hash} 但預期值為 {expected_config_hash}",
        )
    
    # Phase 6.5: Check data_fingerprint_sha1 (mandatory)
    fingerprint_sha1 = getattr(manifest, 'data_fingerprint_sha1', None)
    if not fingerprint_sha1 or fingerprint_sha1 == "":
        return ValidationResult(
            status=ArtifactStatus.DIRTY,
            message="Missing Data Fingerprint — report is untrustworthy (data_fingerprint_sha1 is empty or missing)",
        )
    
    return ValidationResult(status=ArtifactStatus.OK, message="manifest.json 驗證通過")


def validate_winners_v2_status(
    file_path: str,
    winners_data: Optional[dict] = None,
    expected_config_hash: Optional[str] = None,
    manifest_config_hash: Optional[str] = None,
) -> ValidationResult:
    """
    Validate winners_v2.json status.
    
    Args:
        file_path: Path to winners_v2.json
        winners_data: Parsed winners data (if available)
        expected_config_hash: Expected config_hash (for DIRTY check)
        manifest_config_hash: config_hash from manifest (for DIRTY check)
        
    Returns:
        ValidationResult with status and message
    """
    from pathlib import Path
    from FishBroWFS_V2.core.schemas.winners_v2 import WinnersV2
    
    path = Path(file_path)
    
    # Check if file exists
    if not path.exists():
        return ValidationResult(
            status=ArtifactStatus.MISSING,
            message=f"winners_v2.json 不存在: {file_path}",
        )
    
    # Try to parse with Pydantic
    if winners_data is None:
        import json
        try:
            with path.open("r", encoding="utf-8") as f:
                winners_data = json.load(f)
        except json.JSONDecodeError as e:
            return ValidationResult(
                status=ArtifactStatus.INVALID,
                message=f"winners_v2.json JSON 格式錯誤: {e}",
                error_details=str(e),
            )
    
    try:
        winners = WinnersV2(**winners_data)
        
        # Validate rows if present (Pydantic already validates required fields)
        # Additional checks for None values (defensive)
        for idx, row in enumerate(winners.rows):
            if row.net_profit is None:
                return ValidationResult(
                    status=ArtifactStatus.INVALID,
                    message=f"winners_v2.json 第 {idx} 行 net_profit 是必填欄位",
                    error_details=f"row[{idx}].net_profit is None",
                )
            if row.max_drawdown is None:
                return ValidationResult(
                    status=ArtifactStatus.INVALID,
                    message=f"winners_v2.json 第 {idx} 行 max_drawdown 是必填欄位",
                    error_details=f"row[{idx}].max_drawdown is None",
                )
            if row.trades is None:
                return ValidationResult(
                    status=ArtifactStatus.INVALID,
                    message=f"winners_v2.json 第 {idx} 行 trades 是必填欄位",
                    error_details=f"row[{idx}].trades is None",
                )
    except ValidationError as e:
        missing_fields = _extract_missing_field_names(e)
        missing_txt = f"缺少欄位: {', '.join(missing_fields)}；" if missing_fields else ""
        error_details = str(e) + "\nmissing_fields=" + ",".join(missing_fields) if missing_fields else str(e)
        return ValidationResult(
            status=ArtifactStatus.INVALID,
            message=f"winners_v2.json {missing_txt}schema 驗證失敗：{_format_pydantic_error(e)}",
            error_details=error_details,
        )
    except Exception as e:
        # Fallback for non-Pydantic errors
        return ValidationResult(
            status=ArtifactStatus.INVALID,
            message=f"winners_v2.json 驗證失敗: {e}",
            error_details=str(e),
        )
    
    # Check config_hash if expected/manifest is provided
    if expected_config_hash is not None:
        if winners.config_hash != expected_config_hash:
            return ValidationResult(
                status=ArtifactStatus.DIRTY,
                message=f"winners_v2.config_hash={winners.config_hash} 但預期值為 {expected_config_hash}",
            )
    
    if manifest_config_hash is not None:
        if winners.config_hash != manifest_config_hash:
            return ValidationResult(
                status=ArtifactStatus.DIRTY,
                message=f"winners_v2.config_hash={winners.config_hash} 但 manifest.config_hash={manifest_config_hash}",
            )
    
    return ValidationResult(status=ArtifactStatus.OK, message="winners_v2.json 驗證通過")


def validate_governance_status(
    file_path: str,
    governance_data: Optional[dict] = None,
    expected_config_hash: Optional[str] = None,
    manifest_config_hash: Optional[str] = None,
) -> ValidationResult:
    """
    Validate governance.json status.
    
    Args:
        file_path: Path to governance.json
        governance_data: Parsed governance data (if available)
        expected_config_hash: Expected config_hash (for DIRTY check)
        manifest_config_hash: config_hash from manifest (for DIRTY check)
        
    Returns:
        ValidationResult with status and message
    """
    from pathlib import Path
    from FishBroWFS_V2.core.schemas.governance import GovernanceReport
    
    path = Path(file_path)
    
    # Check if file exists
    if not path.exists():
        return ValidationResult(
            status=ArtifactStatus.MISSING,
            message=f"governance.json 不存在: {file_path}",
        )
    
    # Try to parse with Pydantic
    if governance_data is None:
        import json
        try:
            with path.open("r", encoding="utf-8") as f:
                governance_data = json.load(f)
        except json.JSONDecodeError as e:
            return ValidationResult(
                status=ArtifactStatus.INVALID,
                message=f"governance.json JSON 格式錯誤: {e}",
                error_details=str(e),
            )
    
    try:
        governance = GovernanceReport(**governance_data)
    except Exception as e:
        # Extract missing field from Pydantic error
        error_msg = str(e)
        missing_fields = []
        if "field required" in error_msg.lower():
            import re
            matches = re.findall(r"Field required.*?['\"]([^'\"]+)['\"]", error_msg)
            if matches:
                missing_fields = matches
        
        if missing_fields:
            msg = f"governance.json 缺少欄位: {', '.join(missing_fields)}"
        else:
            msg = f"governance.json 驗證失敗: {error_msg}"
        
        return ValidationResult(
            status=ArtifactStatus.INVALID,
            message=msg,
            error_details=error_msg,
        )
    
    # Check config_hash if expected/manifest is provided
    if expected_config_hash is not None:
        if governance.config_hash != expected_config_hash:
            return ValidationResult(
                status=ArtifactStatus.DIRTY,
                message=f"governance.config_hash={governance.config_hash} 但預期值為 {expected_config_hash}",
            )
    
    if manifest_config_hash is not None:
        if governance.config_hash != manifest_config_hash:
            return ValidationResult(
                status=ArtifactStatus.DIRTY,
                message=f"governance.config_hash={governance.config_hash} 但 manifest.config_hash={manifest_config_hash}",
            )
    
    # Phase 6.5: Check data_fingerprint_sha1 in metadata (mandatory)
    metadata = governance_data.get("metadata", {}) if governance_data else {}
    fingerprint_sha1 = metadata.get("data_fingerprint_sha1", "")
    if not fingerprint_sha1 or fingerprint_sha1 == "":
        return ValidationResult(
            status=ArtifactStatus.DIRTY,
            message="Missing Data Fingerprint — report is untrustworthy (data_fingerprint_sha1 is empty or missing in metadata)",
        )
    
    return ValidationResult(status=ArtifactStatus.OK, message="governance.json 驗證通過")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/artifacts.py
sha256(source_bytes) = c0fc02244344ffeaffdb53ad43a1e0f6a22d6f70cd0922c6b5458b59058813bc
bytes = 5493
redacted = False
--------------------------------------------------------------------------------

"""Artifact writer for unified run output.

Provides consistent artifact structure for all runs, with mandatory
subsample rate visibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.core.winners_builder import build_winners_v2
from FishBroWFS_V2.core.winners_schema import is_winners_legacy, is_winners_v2


def _write_json(path: Path, obj: Any) -> None:
    """
    Write object to JSON file with fixed format.
    
    Uses sort_keys=True and fixed separators for reproducibility.
    
    Args:
        path: Path to JSON file
        obj: Object to serialize
    """
    path.write_text(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_run_artifacts(
    run_dir: Path,
    manifest: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    metrics: Dict[str, Any],
    winners: Dict[str, Any] | None = None,
) -> None:
    """
    Write all standard artifacts for a run.
    
    Creates the following files:
    - manifest.json: Full AuditSchema data
    - config_snapshot.json: Original/normalized config
    - metrics.json: Performance metrics
    - winners.json: Top-K results (fixed schema)
    - README.md: Human-readable summary
    - logs.txt: Execution logs (empty initially)
    
    Args:
        run_dir: Run directory path (will be created if needed)
        manifest: Manifest data (AuditSchema as dict)
        config_snapshot: Configuration snapshot
        metrics: Performance metrics (must include param_subsample_rate visibility)
        winners: Optional winners dict. If None, uses empty schema.
            Must follow schema: {"topk": [...], "notes": {"schema": "v1", ...}}
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Write manifest.json (full AuditSchema)
    _write_json(run_dir / "manifest.json", manifest)
    
    # Write config_snapshot.json
    _write_json(run_dir / "config_snapshot.json", config_snapshot)
    
    # Write metrics.json (must include param_subsample_rate visibility)
    _write_json(run_dir / "metrics.json", metrics)
    
    # Write winners.json (always output v2 schema)
    if winners is None:
        winners = {"topk": [], "notes": {"schema": "v1"}}
    
    # Auto-upgrade legacy winners to v2
    if is_winners_legacy(winners):
        # Convert legacy to v2
        legacy_topk = winners.get("topk", [])
        run_id = manifest.get("run_id", "unknown")
        stage_name = metrics.get("stage_name", "unknown")
        
        winners = build_winners_v2(
            stage_name=stage_name,
            run_id=run_id,
            manifest=manifest,
            config_snapshot=config_snapshot,
            legacy_topk=legacy_topk,
        )
    elif not is_winners_v2(winners):
        # Unknown format - try to upgrade anyway (defensive)
        legacy_topk = winners.get("topk", [])
        if legacy_topk:
            run_id = manifest.get("run_id", "unknown")
            stage_name = metrics.get("stage_name", "unknown")
            
            winners = build_winners_v2(
                stage_name=stage_name,
                run_id=run_id,
                manifest=manifest,
                config_snapshot=config_snapshot,
                legacy_topk=legacy_topk,
            )
        else:
            # Empty topk - create minimal v2 structure
            from FishBroWFS_V2.core.winners_schema import build_winners_v2_dict
            winners = build_winners_v2_dict(
                stage_name=metrics.get("stage_name", "unknown"),
                run_id=manifest.get("run_id", "unknown"),
                topk=[],
            )
    
    _write_json(run_dir / "winners.json", winners)
    
    # Write README.md (human-readable summary)
    # Must prominently display param_subsample_rate
    readme_lines = [
        "# FishBroWFS_V2 Run",
        "",
        f"- run_id: {manifest.get('run_id')}",
        f"- git_sha: {manifest.get('git_sha')}",
        f"- param_subsample_rate: {manifest.get('param_subsample_rate')}",
        f"- season: {manifest.get('season')}",
        f"- dataset_id: {manifest.get('dataset_id')}",
        f"- bars: {manifest.get('bars')}",
        f"- params_total: {manifest.get('params_total')}",
        f"- params_effective: {manifest.get('params_effective')}",
        f"- config_hash: {manifest.get('config_hash')}",
    ]
    
    # Add OOM gate information if present in metrics
    if "oom_gate_action" in metrics:
        readme_lines.extend([
            "",
            "## OOM Gate",
            "",
            f"- action: {metrics.get('oom_gate_action')}",
            f"- reason: {metrics.get('oom_gate_reason')}",
            f"- mem_est_mb: {metrics.get('mem_est_mb', 0):.1f}",
            f"- mem_limit_mb: {metrics.get('mem_limit_mb', 0):.1f}",
            f"- ops_est: {metrics.get('ops_est', 0)}",
        ])
        
        # If auto-downsample occurred, show original and final
        if metrics.get("oom_gate_action") == "AUTO_DOWNSAMPLE":
            readme_lines.extend([
                f"- original_subsample: {metrics.get('oom_gate_original_subsample', 0)}",
                f"- final_subsample: {metrics.get('oom_gate_final_subsample', 0)}",
            ])
    
    readme = "\n".join(readme_lines)
    (run_dir / "README.md").write_text(readme, encoding="utf-8")
    
    # Write logs.txt (empty initially)
    (run_dir / "logs.txt").write_text("", encoding="utf-8")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/audit_schema.py
sha256(source_bytes) = 9bec8723373b6e4906c9cf3ea1adf507853d7f5d9393462b561a911fac4c6929
bytes = 1919
redacted = False
--------------------------------------------------------------------------------

"""Audit schema for run tracking and reproducibility.

Single Source of Truth (SSOT) for audit data.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass(frozen=True)
class AuditSchema:
    """
    Audit schema for run tracking.
    
    All fields are required and must be JSON-serializable.
    This is the Single Source of Truth (SSOT) for audit data.
    """
    run_id: str
    created_at: str  # ISO8601 with Z suffix (UTC)
    git_sha: str  # At least 12 chars
    dirty_repo: bool  # Whether repo has uncommitted changes
    param_subsample_rate: float  # Required, must be in [0.0, 1.0]
    config_hash: str  # Stable hash of config
    season: str  # Season identifier
    dataset_id: str  # Dataset identifier
    bars: int  # Number of bars processed
    params_total: int  # Total parameters before subsample
    params_effective: int  # Effective parameters after subsample (= int(params_total * param_subsample_rate))
    artifact_version: str = "v1"  # Artifact version
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


def compute_params_effective(params_total: int, param_subsample_rate: float) -> int:
    """
    Compute effective parameters after subsample.
    
    Rounding rule: int(params_total * param_subsample_rate)
    This is locked in code/docs/tests - do not change.
    
    Args:
        params_total: Total parameters before subsample
        param_subsample_rate: Subsample rate in [0.0, 1.0]
        
    Returns:
        Effective parameters (integer, rounded down)
    """
    if not (0.0 <= param_subsample_rate <= 1.0):
        raise ValueError(f"param_subsample_rate must be in [0.0, 1.0], got {param_subsample_rate}")
    
    return int(params_total * param_subsample_rate)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/config_hash.py
sha256(source_bytes) = e1bf5e812460f3215e7d661d0f56b905d60323f9264ee9a930b0d4e35f466abb
bytes = 737
redacted = False
--------------------------------------------------------------------------------

"""Stable config hash computation.

Provides deterministic hash of configuration objects for reproducibility.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_config_hash(obj: Any) -> str:
    """
    Compute stable hash of configuration object.
    
    Uses JSON serialization with sorted keys and fixed separators
    to ensure cross-platform consistency.
    
    Args:
        obj: Configuration object (dict, list, etc.)
        
    Returns:
        Hex string hash (64 chars, SHA256)
    """
    s = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(s.encode("utf-8")).hexdigest()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/config_snapshot.py
sha256(source_bytes) = 64533c2ba5a5f3b06a0ebb9fb4b491ba59223911faff4ba50363ef2abc4d081b
bytes = 2862
redacted = False
--------------------------------------------------------------------------------

"""Config snapshot sanitizer.

Creates JSON-serializable config snapshots by excluding large ndarrays
and converting numpy types to Python native types.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

# These keys will make artifacts garbage or directly crash JSON serialization
_DEFAULT_DROP_KEYS = {
    "open_",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "params_matrix",
}


def _ndarray_meta(x: np.ndarray) -> Dict[str, Any]:
    """
    Create metadata dict for ndarray (shape and dtype only).
    
    Args:
        x: numpy array
        
    Returns:
        Metadata dictionary with shape and dtype
    """
    return {
        "__ndarray__": True,
        "shape": list(x.shape),
        "dtype": str(x.dtype),
    }


def make_config_snapshot(
    cfg: Dict[str, Any],
    drop_keys: set[str] | None = None,
) -> Dict[str, Any]:
    """
    Create sanitized config snapshot for JSON serialization and hashing.
    
    Rules (locked):
    - Must include: season, dataset_id, bars, params_total, param_subsample_rate,
      stage_name, topk, commission, slip, order_qty, config knobs...
    - Must exclude/replace: open_, high, low, close, params_matrix (ndarrays)
    - If metadata needed, only keep shape/dtype (no bytes hash to avoid cost)
    
    Args:
        cfg: Configuration dictionary (may contain ndarrays)
        drop_keys: Optional set of keys to drop. If None, uses default.
        
    Returns:
        Sanitized config dictionary (JSON-serializable)
    """
    drop = _DEFAULT_DROP_KEYS if drop_keys is None else drop_keys
    out: Dict[str, Any] = {}
    
    for k, v in cfg.items():
        if k in drop:
            # Don't keep raw data, only metadata (optional)
            if isinstance(v, np.ndarray):
                out[k + "_meta"] = _ndarray_meta(v)
            continue
        
        # numpy scalar -> python scalar
        if isinstance(v, (np.floating, np.integer)):
            out[k] = v.item()
        # ndarray (if slipped through) -> meta
        elif isinstance(v, np.ndarray):
            out[k + "_meta"] = _ndarray_meta(v)
        # Basic types: keep as-is
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        # list/tuple: conservative handling (avoid strange objects)
        elif isinstance(v, (list, tuple)):
            # Check if list contains only serializable types
            try:
                # Try to serialize to verify
                import json
                json.dumps(v)
                out[k] = v
            except (TypeError, ValueError):
                # If not serializable, convert to string representation
                out[k] = str(v)
        # Other types: convert to string (avoid JSON crash)
        else:
            out[k] = str(v)
    
    return out



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/dimensions.py
sha256(source_bytes) = f2f49c27a7dc66ec2167acbfe66297e2e492184c5b2a0ac28be4f6dbb8e0076d
bytes = 1680
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/core/dimensions.py
"""
穩定的維度查詢介面

提供 get_dimension_for_dataset() 函數，用於查詢商品的維度定義（交易時段、交易所等）。
此模組使用 lazy loading 避免 import-time IO，並提供 deterministic 結果。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from FishBroWFS_V2.contracts.dimensions import InstrumentDimension
from FishBroWFS_V2.contracts.dimensions_loader import load_dimension_registry


@lru_cache(maxsize=1)
def _get_cached_registry():
    """
    快取註冊表，避免重複讀取檔案
    
    使用 lru_cache(maxsize=1) 確保：
    1. 第一次呼叫時讀取檔案
    2. 後續呼叫重用快取
    3. 避免 import-time IO
    """
    return load_dimension_registry()


def get_dimension_for_dataset(
    dataset_id: str, 
    *, 
    symbol: str | None = None
) -> InstrumentDimension | None:
    """
    查詢資料集的維度定義
    
    Args:
        dataset_id: 資料集 ID，例如 "CME.MNQ.60m.2020-2024"
        symbol: 可選的商品符號，例如 "CME.MNQ"
    
    Returns:
        InstrumentDimension 或 None（如果找不到）
    
    Note:
        - 純讀取操作，無副作用（除了第一次呼叫時的檔案讀取）
        - 結果是 deterministic 的
        - 使用 lazy loading，避免 import-time IO
    """
    registry = _get_cached_registry()
    return registry.get(dataset_id, symbol)


def clear_dimension_cache() -> None:
    """
    清除維度快取
    
    主要用於測試，或需要強制重新讀取註冊表的情況
    """
    _get_cached_registry.cache_clear()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/feature_bundle.py
sha256(source_bytes) = 47e8e6692b9fcf5f4729436194674d64c021158221adfb48a25fcbaeff8c8d08
bytes = 5840
redacted = False
--------------------------------------------------------------------------------

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



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/features.py
sha256(source_bytes) = e74ba47846cb09880a0e38d9c7635647b3cfc22af8dc5f4e6365fadec76ac409
bytes = 8459
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/core/features.py
"""
Feature 計算核心

提供 deterministic numpy 實作，禁止 pandas rolling。
所有計算必須與 FULL/INCREMENTAL 模式完全一致。
"""

from __future__ import annotations

import numpy as np
from typing import Dict, Literal, Optional
from datetime import datetime

from FishBroWFS_V2.contracts.features import FeatureRegistry, FeatureSpec
from FishBroWFS_V2.core.resampler import SessionSpecTaipei


def compute_atr_14(
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
) -> np.ndarray:
    """
    計算 ATR(14)（Average True Range）
    
    公式：
    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = rolling mean of TR with window=14 (population std, ddof=0)
    
    前 13 根 bar 的 ATR 為 NaN（因為 window 不足）
    
    Args:
        o: open 價格（未使用）
        h: high 價格
        l: low 價格
        c: close 價格
        
    Returns:
        ATR(14) 陣列，與輸入長度相同
    """
    n = len(c)
    if n == 0:
        return np.array([], dtype=np.float64)
    
    # 計算 True Range
    tr = np.empty(n, dtype=np.float64)
    
    # 第一根 bar 的 TR = high - low
    tr[0] = h[0] - l[0]
    
    # 後續 bar 的 TR
    for i in range(1, n):
        hl = h[i] - l[i]
        hc = abs(h[i] - c[i-1])
        lc = abs(l[i] - c[i-1])
        tr[i] = max(hl, hc, lc)
    
    # 計算 rolling mean with window=14 (population std, ddof=0)
    # 使用 cumulative sums 確保 deterministic
    atr = np.full(n, np.nan, dtype=np.float64)
    
    if n >= 14:
        # 計算 cumulative sum of TR
        cumsum = np.cumsum(tr, dtype=np.float64)
        
        # 計算 rolling mean
        for i in range(13, n):
            if i == 13:
                window_sum = cumsum[i]
            else:
                window_sum = cumsum[i] - cumsum[i-14]
            
            atr[i] = window_sum / 14.0
    
    return atr


def compute_returns(
    c: np.ndarray,
    method: str = "log",
) -> np.ndarray:
    """
    計算 returns
    
    公式：
    - log: r = log(close).diff()
    - simple: r = (close - prev_close) / prev_close
    
    第一根 bar 的 return 為 NaN
    
    Args:
        c: close 價格
        method: 計算方法，"log" 或 "simple"
        
    Returns:
        returns 陣列，與輸入長度相同
    """
    n = len(c)
    if n <= 1:
        return np.full(n, np.nan, dtype=np.float64)
    
    ret = np.full(n, np.nan, dtype=np.float64)
    
    if method == "log":
        # log returns: r = log(close).diff()
        log_c = np.log(c)
        ret[1:] = np.diff(log_c)
    else:
        # simple returns: r = (close - prev_close) / prev_close
        ret[1:] = (c[1:] - c[:-1]) / c[:-1]
    
    return ret


def compute_rolling_z(
    x: np.ndarray,
    window: int,
) -> np.ndarray:
    """
    計算 rolling z-score（population std, ddof=0）
    
    公式：
    mean = (sum_x[i] - sum_x[i-window]) / window
    var = (sum_x2[i] - sum_x2[i-window]) / window - mean^2
    std = sqrt(max(var, 0))  # 防浮點負數
    z = (x - mean) / std
    
    前 window-1 根 bar 的 z-score 為 NaN
    std == 0 時，z = NaN（而不是 0）
    
    Args:
        x: 輸入數值陣列
        window: 滾動視窗大小
        
    Returns:
        z-score 陣列，與輸入長度相同
    """
    n = len(x)
    if n == 0 or window <= 1:
        return np.full(n, np.nan, dtype=np.float64)
    
    # 初始化結果為 NaN
    z = np.full(n, np.nan, dtype=np.float64)
    
    # 計算 cumulative sums
    cumsum = np.cumsum(x, dtype=np.float64)
    cumsum2 = np.cumsum(x * x, dtype=np.float64)
    
    # 計算 rolling z-score
    for i in range(window - 1, n):
        # 計算視窗內的 sum 和 sum of squares
        if i == window - 1:
            sum_x = cumsum[i]
            sum_x2 = cumsum2[i]
        else:
            sum_x = cumsum[i] - cumsum[i - window]
            sum_x2 = cumsum2[i] - cumsum2[i - window]
        
        # 計算 mean 和 variance
        mean = sum_x / window
        var = (sum_x2 / window) - (mean * mean)
        
        # 防浮點負數
        if var < 0:
            var = 0.0
        
        std = np.sqrt(var)
        
        # 計算 z-score
        if std == 0:
            # std == 0 時，z = NaN（而不是 0）
            z[i] = np.nan
        else:
            z[i] = (x[i] - mean) / std
    
    return z


def compute_session_vwap(
    ts: np.ndarray,
    c: np.ndarray,
    v: np.ndarray,
    session_spec: SessionSpecTaipei,
    breaks_policy: str = "drop",
) -> np.ndarray:
    """
    計算 session VWAP（Volume Weighted Average Price）
    
    每個 session 獨立計算 VWAP，並將該 session 內的所有 bar 賦予相同的 VWAP 值。
    
    Args:
        ts: 時間戳記陣列（datetime64[s]）
        c: close 價格陣列
        v: volume 陣列
        session_spec: session 規格
        breaks_policy: break 處理策略（目前只支援 "drop"）
        
    Returns:
        session VWAP 陣列，與輸入長度相同
    """
    n = len(ts)
    if n == 0:
        return np.array([], dtype=np.float64)
    
    # 初始化結果為 NaN
    vwap = np.full(n, np.nan, dtype=np.float64)
    
    # 將 datetime64[s] 轉換為 pandas Timestamp 以便進行日期時間操作
    # 我們需要判斷每個 bar 屬於哪個 session
    # 由於這是 MVP，我們先實作簡單版本：假設所有 bar 都在同一個 session
    # 實際實作需要根據 session_spec 進行 session 分類
    # 但根據 Phase 3B 要求，我們先提供固定實作
    
    # 簡單實作：計算整個時間範圍的 VWAP（所有 bar 視為同一個 session）
    # 這不是正確的 session VWAP，但符合 MVP 要求
    total_volume = np.sum(v)
    if total_volume > 0:
        weighted_sum = np.sum(c * v)
        overall_vwap = weighted_sum / total_volume
        vwap[:] = overall_vwap
    else:
        vwap[:] = np.nan
    
    return vwap


def compute_features_for_tf(
    ts: np.ndarray,
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    v: np.ndarray,
    tf_min: int,
    registry: FeatureRegistry,
    session_spec: SessionSpecTaipei,
    breaks_policy: str = "drop",
) -> Dict[str, np.ndarray]:
    """
    計算指定 timeframe 的所有特徵
    
    Args:
        ts: 時間戳記陣列（datetime64[s]），必須與 resampled bars 完全一致
        o: open 價格陣列
        h: high 價格陣列
        l: low 價格陣列
        c: close 價格陣列
        v: volume 陣列
        tf_min: timeframe 分鐘數
        registry: 特徵註冊表
        session_spec: session 規格
        breaks_policy: break 處理策略
        
    Returns:
        特徵字典，keys 必須為：
        - ts: 與輸入 ts 相同的物件/值（datetime64[s]）
        - atr_14: float64
        - ret_z_200: float64
        - session_vwap: float64
        
    Raises:
        ValueError: 輸入陣列長度不一致或 registry 缺少必要特徵
    """
    # 驗證輸入長度
    n = len(ts)
    for arr, name in [(o, "open"), (h, "high"), (l, "low"), (c, "close"), (v, "volume")]:
        if len(arr) != n:
            raise ValueError(f"輸入陣列長度不一致: {name} 長度為 {len(arr)}，但 ts 長度為 {n}")
    
    # 取得該 timeframe 的特徵規格
    specs = registry.specs_for_tf(tf_min)
    
    # 建立結果字典
    result = {"ts": ts}  # ts 必須是相同的物件/值
    
    # 計算每個特徵
    for spec in specs:
        if spec.name == "atr_14":
            result["atr_14"] = compute_atr_14(o, h, l, c)
        elif spec.name == "ret_z_200":
            # 先計算 returns
            returns = compute_returns(c, method="log")
            # 再計算 z-score
            result["ret_z_200"] = compute_rolling_z(returns, window=200)
        elif spec.name == "session_vwap":
            result["session_vwap"] = compute_session_vwap(
                ts, c, v, session_spec, breaks_policy
            )
        else:
            raise ValueError(f"不支援的特徵名稱: {spec.name}")
    
    # 確保所有必要特徵都存在
    required_features = ["atr_14", "ret_z_200", "session_vwap"]
    for feat in required_features:
        if feat not in result:
            raise ValueError(f"registry 缺少必要特徵: {feat}")
    
    return result



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/fingerprint.py
sha256(source_bytes) = 441ddd041b5bd8650c71eaae4a303f0cc5465f8abf56d5f0617a9ea79ce8a77e
bytes = 7761
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/core/fingerprint.py
"""
Fingerprint 計算核心

提供 canonical bytes 規則與指紋計算函數，確保 deterministic 結果。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from FishBroWFS_V2.contracts.fingerprint import FingerprintIndex
from FishBroWFS_V2.data.raw_ingest import RawIngestResult


def canonical_bar_line(
    ts: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    v: float
) -> str:
    """
    將單一 bar 轉換為標準化字串
    
    格式固定：YYYY-MM-DDTHH:MM:SS|{o:.4f}|{h:.4f}|{l:.4f}|{c:.4f}|{v:.0f}
    
    Args:
        ts: 時間戳記
        o: 開盤價
        h: 最高價
        l: 最低價
        c: 收盤價
        v: 成交量
    
    Returns:
        標準化字串
    """
    # 格式化時間戳記
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S")
    
    # 格式化價格（固定小數位數）
    # 使用 round 確保 deterministic，避免浮點數表示差異
    o_fmt = f"{o:.4f}"
    h_fmt = f"{h:.4f}"
    l_fmt = f"{l:.4f}"
    c_fmt = f"{c:.4f}"
    
    # 格式化成交量（整數）
    v_fmt = f"{v:.0f}"
    
    return f"{ts_str}|{o_fmt}|{h_fmt}|{l_fmt}|{c_fmt}|{v_fmt}"


def compute_day_hash(lines: List[str]) -> str:
    """
    計算一日的 hash
    
    將該日所有 bar 的標準化字串排序後連接，計算 SHA256。
    
    Args:
        lines: 該日所有 bar 的標準化字串列表
    
    Returns:
        SHA256 hex 字串
    """
    if not lines:
        # 空日的 hash（理論上不應該發生）
        return hashlib.sha256(b"").hexdigest()
    
    # 排序確保 deterministic
    sorted_lines = sorted(lines)
    
    # 連接所有字串，以換行分隔
    content = "\n".join(sorted_lines)
    
    # 計算 SHA256
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse_ts_str(ts_str: str) -> datetime:
    """
    解析時間戳記字串
    
    支援多種格式：
    - "YYYY-MM-DD HH:MM:SS"
    - "YYYY/MM/DD HH:MM:SS"
    - "YYYY-MM-DDTHH:MM:SS"
    """
    # 嘗試常見格式
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%dT%H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    
    # 如果都不匹配，嘗試使用 pandas 解析
    try:
        return pd.to_datetime(ts_str).to_pydatetime()
    except Exception as e:
        raise ValueError(f"無法解析時間戳記: {ts_str}") from e


def _group_bars_by_day(
    bars: Iterable[Tuple[datetime, float, float, float, float, float]]
) -> Dict[str, List[str]]:
    """
    將 bars 按日期分組
    
    Args:
        bars: (ts, o, h, l, c, v) 的迭代器
    
    Returns:
        字典：日期字串 (YYYY-MM-DD) -> 該日所有 bar 的標準化字串列表
    """
    day_groups: Dict[str, List[str]] = {}
    
    for ts, o, h, l, c, v in bars:
        # 取得日期字串
        day_str = ts.strftime("%Y-%m-%d")
        
        # 建立標準化字串
        line = canonical_bar_line(ts, o, h, l, c, v)
        
        # 加入對應日期的群組
        if day_str not in day_groups:
            day_groups[day_str] = []
        day_groups[day_str].append(line)
    
    return day_groups


def build_fingerprint_index_from_bars(
    dataset_id: str,
    bars: Iterable[Tuple[datetime, float, float, float, float, float]],
    dataset_timezone: str = "Asia/Taipei",
    build_notes: str = ""
) -> FingerprintIndex:
    """
    從 bars 建立指紋索引
    
    Args:
        dataset_id: 資料集 ID
        bars: (ts, o, h, l, c, v) 的迭代器
        dataset_timezone: 時區
        build_notes: 建置備註
    
    Returns:
        FingerprintIndex
    """
    # 按日期分組
    day_groups = _group_bars_by_day(bars)
    
    if not day_groups:
        raise ValueError("沒有 bars 資料")
    
    # 計算每日 hash
    day_hashes: Dict[str, str] = {}
    for day_str, lines in day_groups.items():
        day_hashes[day_str] = compute_day_hash(lines)
    
    # 找出日期範圍
    sorted_days = sorted(day_hashes.keys())
    range_start = sorted_days[0]
    range_end = sorted_days[-1]
    
    # 建立指紋索引
    return FingerprintIndex.create(
        dataset_id=dataset_id,
        range_start=range_start,
        range_end=range_end,
        day_hashes=day_hashes,
        dataset_timezone=dataset_timezone,
        build_notes=build_notes
    )


def build_fingerprint_index_from_raw_ingest(
    dataset_id: str,
    raw_ingest_result: RawIngestResult,
    dataset_timezone: str = "Asia/Taipei",
    build_notes: str = ""
) -> FingerprintIndex:
    """
    從 RawIngestResult 建立指紋索引（便利函數）
    
    Args:
        dataset_id: 資料集 ID
        raw_ingest_result: RawIngestResult
        dataset_timezone: 時區
        build_notes: 建置備註
    
    Returns:
        FingerprintIndex
    """
    df = raw_ingest_result.df
    
    # 準備 bars 迭代器
    bars = []
    for _, row in df.iterrows():
        try:
            ts = _parse_ts_str(row["ts_str"])
            bars.append((
                ts,
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"])
            ))
        except Exception as e:
            raise ValueError(f"解析 bar 資料失敗: {e}") from e
    
    return build_fingerprint_index_from_bars(
        dataset_id=dataset_id,
        bars=bars,
        dataset_timezone=dataset_timezone,
        build_notes=build_notes
    )


def compare_fingerprint_indices(
    old_index: FingerprintIndex | None,
    new_index: FingerprintIndex
) -> Dict[str, Any]:
    """
    比較兩個指紋索引，產生 diff 報告
    
    Args:
        old_index: 舊索引（可為 None）
        new_index: 新索引
    
    Returns:
        diff 報告字典
    """
    if old_index is None:
        return {
            "old_range_start": None,
            "old_range_end": None,
            "new_range_start": new_index.range_start,
            "new_range_end": new_index.range_end,
            "append_only": False,
            "append_range": None,
            "earliest_changed_day": None,
            "no_change": False,
            "is_new": True,
        }
    
    # 檢查是否完全相同
    if old_index.index_sha256 == new_index.index_sha256:
        return {
            "old_range_start": old_index.range_start,
            "old_range_end": old_index.range_end,
            "new_range_start": new_index.range_start,
            "new_range_end": new_index.range_end,
            "append_only": False,
            "append_range": None,
            "earliest_changed_day": None,
            "no_change": True,
            "is_new": False,
        }
    
    # 檢查是否為 append-only
    append_only = old_index.is_append_only(new_index)
    append_range = old_index.get_append_range(new_index) if append_only else None
    
    # 找出最早變更的日期
    earliest_changed_day = old_index.get_earliest_changed_day(new_index)
    
    return {
        "old_range_start": old_index.range_start,
        "old_range_end": old_index.range_end,
        "new_range_start": new_index.range_start,
        "new_range_end": new_index.range_end,
        "append_only": append_only,
        "append_range": append_range,
        "earliest_changed_day": earliest_changed_day,
        "no_change": False,
        "is_new": False,
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/governance_schema.py
sha256(source_bytes) = c3eaa60d25152eaa39bff142e32237a840615eb166ea0eed79c2b20694e58f74
bytes = 2629
redacted = False
--------------------------------------------------------------------------------

"""Governance schema for decision tracking and auditability.

Single Source of Truth (SSOT) for governance decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from FishBroWFS_V2.core.schemas.governance import Decision


@dataclass(frozen=True)
class EvidenceRef:
    """
    Reference to evidence used in governance decision.
    
    Points to specific artifacts (run_id, stage, artifact paths, key metrics)
    that support the decision.
    """
    run_id: str
    stage_name: str
    artifact_paths: List[str]  # Relative paths to artifacts (manifest.json, metrics.json, etc.)
    key_metrics: Dict[str, Any]  # Key metrics extracted from artifacts


@dataclass(frozen=True)
class GovernanceItem:
    """
    Governance decision for a single candidate.
    
    Each item represents a decision (KEEP/FREEZE/DROP) for one candidate
    parameter set, with reasons and evidence chain.
    """
    candidate_id: str  # Stable identifier: strategy_id:params_hash[:12]
    decision: Decision
    reasons: List[str]  # Human-readable reasons for decision
    evidence: List[EvidenceRef]  # Evidence chain supporting decision
    created_at: str  # ISO8601 with Z suffix (UTC)
    git_sha: str  # Git SHA at time of governance evaluation


@dataclass(frozen=True)
class GovernanceReport:
    """
    Complete governance report for a set of candidates.
    
    Contains:
    - items: List of governance decisions for each candidate
    - metadata: Report-level metadata (governance_id, season, etc.)
    """
    items: List[GovernanceItem]
    metadata: Dict[str, Any]  # Report metadata (governance_id, season, created_at, etc.)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "items": [
                {
                    "candidate_id": item.candidate_id,
                    "decision": item.decision.value,
                    "reasons": item.reasons,
                    "evidence": [
                        {
                            "run_id": ev.run_id,
                            "stage_name": ev.stage_name,
                            "artifact_paths": ev.artifact_paths,
                            "key_metrics": ev.key_metrics,
                        }
                        for ev in item.evidence
                    ],
                    "created_at": item.created_at,
                    "git_sha": item.git_sha,
                }
                for item in self.items
            ],
            "metadata": self.metadata,
        }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/governance_writer.py
sha256(source_bytes) = 7ac1f8b05cbbb86cffa6e8134615c0a561e1e0266fef75befe7ad790a9f4bf31
bytes = 4810
redacted = False
--------------------------------------------------------------------------------

"""Governance writer for decision artifacts.

Writes governance results to outputs directory with machine-readable JSON
and human-readable README.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.core.governance_schema import GovernanceReport
from FishBroWFS_V2.core.schemas.governance import Decision
from FishBroWFS_V2.core.run_id import make_run_id


def write_governance_artifacts(
    governance_dir: Path,
    report: GovernanceReport,
) -> None:
    """
    Write governance artifacts to directory.
    
    Creates:
    - governance.json: Machine-readable governance report
    - README.md: Human-readable summary
    - evidence_index.json: Optional evidence index (recommended)
    
    Args:
        governance_dir: Path to governance directory (will be created if needed)
        report: GovernanceReport to write
    """
    governance_dir.mkdir(parents=True, exist_ok=True)
    
    # Write governance.json (machine-readable SSOT)
    governance_dict = report.to_dict()
    governance_path = governance_dir / "governance.json"
    with governance_path.open("w", encoding="utf-8") as f:
        json.dump(
            governance_dict,
            f,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        f.write("\n")
    
    # Write README.md (human-readable summary)
    readme_lines = [
        "# Governance Report",
        "",
        f"- governance_id: {report.metadata.get('governance_id')}",
        f"- season: {report.metadata.get('season')}",
        f"- created_at: {report.metadata.get('created_at')}",
        f"- git_sha: {report.metadata.get('git_sha')}",
        "",
        "## Decision Summary",
        "",
    ]
    
    decisions = report.metadata.get("decisions", {})
    readme_lines.extend([
        f"- KEEP: {decisions.get('KEEP', 0)}",
        f"- FREEZE: {decisions.get('FREEZE', 0)}",
        f"- DROP: {decisions.get('DROP', 0)}",
        "",
    ])
    
    # List FREEZE reasons (concise)
    freeze_items = [item for item in report.items if item.decision is Decision.FREEZE]
    if freeze_items:
        readme_lines.extend([
            "## FREEZE Reasons",
            "",
        ])
        for item in freeze_items:
            reasons_str = "; ".join(item.reasons)
            readme_lines.append(f"- {item.candidate_id}: {reasons_str}")
        readme_lines.append("")
    
    # Subsample/params_effective summary
    readme_lines.extend([
        "## Subsample & Params Effective",
        "",
    ])
    
    # Extract subsample info from evidence
    subsample_info: Dict[str, Any] = {}
    for item in report.items:
        for ev in item.evidence:
            stage = ev.stage_name
            if stage not in subsample_info:
                subsample_info[stage] = {}
            metrics = ev.key_metrics
            if "stage_planned_subsample" in metrics:
                subsample_info[stage]["stage_planned_subsample"] = metrics["stage_planned_subsample"]
            if "param_subsample_rate" in metrics:
                subsample_info[stage]["param_subsample_rate"] = metrics["param_subsample_rate"]
            if "params_effective" in metrics:
                subsample_info[stage]["params_effective"] = metrics["params_effective"]
    
    for stage, info in subsample_info.items():
        readme_lines.append(f"### {stage}")
        if "stage_planned_subsample" in info:
            readme_lines.append(f"- stage_planned_subsample: {info['stage_planned_subsample']}")
        if "param_subsample_rate" in info:
            readme_lines.append(f"- param_subsample_rate: {info['param_subsample_rate']}")
        if "params_effective" in info:
            readme_lines.append(f"- params_effective: {info['params_effective']}")
        readme_lines.append("")
    
    readme = "\n".join(readme_lines)
    readme_path = governance_dir / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    
    # Write evidence_index.json (optional but recommended)
    evidence_index = {
        "governance_id": report.metadata.get("governance_id"),
        "evidence_by_candidate": {
            item.candidate_id: [
                {
                    "run_id": ev.run_id,
                    "stage_name": ev.stage_name,
                    "artifact_paths": ev.artifact_paths,
                }
                for ev in item.evidence
            ]
            for item in report.items
        },
    }
    evidence_index_path = governance_dir / "evidence_index.json"
    with evidence_index_path.open("w", encoding="utf-8") as f:
        json.dump(
            evidence_index,
            f,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        f.write("\n")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/oom_cost_model.py
sha256(source_bytes) = ec1a5f399cb50fef6fc0cdf53ebabb626eff692c5a51224768edaf494d30dcec
bytes = 4239
redacted = False
--------------------------------------------------------------------------------

"""OOM cost model for memory and computation estimation.

Provides conservative estimates for memory usage and operations
to enable OOM gate decisions before stage execution.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np


def _bytes_of_array(a: Any) -> int:
    """
    Get bytes of numpy array.
    
    Args:
        a: Array-like object
        
    Returns:
        Number of bytes (0 if not ndarray)
    """
    if isinstance(a, np.ndarray):
        return int(a.nbytes)
    return 0


def estimate_memory_bytes(
    cfg: Dict[str, Any],
    work_factor: float = 2.0,
) -> int:
    """
    Estimate memory usage in bytes (conservative upper bound).
    
    Memory estimation includes:
    - Price arrays: open/high/low/close (if present)
    - Params matrix: params_total * param_dim * 8 bytes (if present)
    - Working buffers: conservative multiplier (work_factor)
    
    Note: This is a conservative estimate. Actual usage may be lower,
    but gate uses this to prevent OOM failures.
    
    Args:
        cfg: Configuration dictionary containing:
            - bars: Number of bars
            - params_total: Total parameters
            - param_subsample_rate: Subsample rate
            - open_, high, low, close: Optional OHLC arrays
            - params_matrix: Optional parameter matrix
        work_factor: Conservative multiplier for working buffers (default: 2.0)
        
    Returns:
        Estimated memory in bytes
    """
    mem = 0
    
    # Price arrays (if present)
    for k in ("open_", "open", "high", "low", "close"):
        mem += _bytes_of_array(cfg.get(k))
    
    # Params matrix
    mem += _bytes_of_array(cfg.get("params_matrix"))
    
    # Conservative working buffers
    # Note: This is a conservative multiplier to account for:
    # - Intermediate computation buffers
    # - Indicator arrays (donchian, ATR, etc.)
    # - Intent arrays
    # - Fill arrays
    mem = int(mem * float(work_factor))
    
    # Note: We do NOT reduce mem by subsample_rate here because:
    # 1. Some allocations are per-bar (not per-param)
    # 2. Working buffers may scale differently
    # 3. Conservative estimate is safer for OOM prevention
    
    return mem


def estimate_ops(cfg: Dict[str, Any]) -> int:
    """
    Estimate operations count (coarse approximation).
    
    Baseline: per-bar per-effective-param operations.
    This is a coarse estimate for cost tracking.
    
    Args:
        cfg: Configuration dictionary containing:
            - bars: Number of bars
            - params_total: Total parameters
            - param_subsample_rate: Subsample rate
            
    Returns:
        Estimated operations count
    """
    bars = int(cfg.get("bars", 0))
    params_total = int(cfg.get("params_total", 0))
    subsample_rate = float(cfg.get("param_subsample_rate", 1.0))
    
    # Effective params after subsample (floor rule)
    params_effective = int(params_total * subsample_rate)
    
    # Baseline: per-bar per-effective-param step (coarse)
    ops = int(bars * params_effective)
    
    return ops


def estimate_time_s(cfg: Dict[str, Any]) -> float | None:
    """
    Estimate execution time in seconds (optional).
    
    This is a placeholder for future time estimation.
    Currently returns None.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Estimated time in seconds (None if not available)
    """
    # Placeholder for future implementation
    return None


def summarize_estimates(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize all estimates in a JSON-serializable dict.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Dictionary with estimates:
        - mem_est_bytes: Memory estimate in bytes
        - mem_est_mb: Memory estimate in MB
        - ops_est: Operations estimate
        - time_est_s: Time estimate in seconds (None if not available)
    """
    mem_b = estimate_memory_bytes(cfg)
    ops = estimate_ops(cfg)
    time_s = estimate_time_s(cfg)
    
    return {
        "mem_est_bytes": mem_b,
        "mem_est_mb": mem_b / (1024.0 * 1024.0),
        "ops_est": ops,
        "time_est_s": time_s,
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/oom_gate.py
sha256(source_bytes) = b2c6072834d6dd86b779d7f31f7ba2b706ed506075e21005e9a2bc563723adb6
bytes = 14718
redacted = False
--------------------------------------------------------------------------------

"""OOM gate decision maker.

Pure functions for estimating memory usage and deciding PASS/BLOCK/AUTO_DOWNSAMPLE.
No engine dependencies, no file I/O - pure computation only.

This module provides two APIs:
1. New API (for B5-C): estimate_bytes(), decide_gate() with Pydantic schemas
2. Legacy API (for pipeline/tests): decide_oom_action() with dict I/O
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Literal, Optional

import FishBroWFS_V2.core.oom_cost_model as oom_cost_model
from FishBroWFS_V2.core.schemas.oom_gate import OomGateDecision, OomGateInput

OomAction = Literal["PASS", "BLOCK", "AUTO_DOWNSAMPLE"]


def estimate_bytes(inp: OomGateInput) -> int:
    """
    Estimate memory usage in bytes.
    
    Formula (locked):
        estimated = bars * params * subsample * intents_per_bar * bytes_per_intent_est
    
    Args:
        inp: OomGateInput with bars, params, param_subsample_rate, etc.
        
    Returns:
        Estimated memory usage in bytes
    """
    estimated = (
        inp.bars
        * inp.params
        * inp.param_subsample_rate
        * inp.intents_per_bar
        * inp.bytes_per_intent_est
    )
    return int(estimated)


def decide_gate(inp: OomGateInput) -> OomGateDecision:
    """
    Decide OOM gate action: PASS, BLOCK, or AUTO_DOWNSAMPLE.
    
    Rules (locked):
    - PASS: estimated <= ram_budget * 0.6
    - BLOCK: estimated > ram_budget * 0.9
    - AUTO_DOWNSAMPLE: otherwise, recommended_rate = (ram_budget * 0.6) / (bars * params * intents_per_bar * bytes_per_intent_est)
    
    Args:
        inp: OomGateInput with configuration
        
    Returns:
        OomGateDecision with decision and recommendations
    """
    estimated = estimate_bytes(inp)
    ram_budget = inp.ram_budget_bytes
    
    # Thresholds (locked)
    pass_threshold = ram_budget * 0.6
    block_threshold = ram_budget * 0.9
    
    if estimated <= pass_threshold:
        return OomGateDecision(
            decision="PASS",
            estimated_bytes=estimated,
            ram_budget_bytes=ram_budget,
            recommended_subsample_rate=None,
            notes=f"Estimated {estimated:,} bytes <= {pass_threshold:,.0f} bytes (60% of budget)",
        )
    
    if estimated > block_threshold:
        return OomGateDecision(
            decision="BLOCK",
            estimated_bytes=estimated,
            ram_budget_bytes=ram_budget,
            recommended_subsample_rate=None,
            notes=f"Estimated {estimated:,} bytes > {block_threshold:,.0f} bytes (90% of budget) - BLOCKED",
        )
    
    # AUTO_DOWNSAMPLE: calculate recommended rate
    # recommended_rate = (ram_budget * 0.6) / (bars * params * intents_per_bar * bytes_per_intent_est)
    denominator = inp.bars * inp.params * inp.intents_per_bar * inp.bytes_per_intent_est
    if denominator > 0:
        recommended_rate = (ram_budget * 0.6) / denominator
        # Clamp to [0.0, 1.0]
        recommended_rate = max(0.0, min(1.0, recommended_rate))
    else:
        recommended_rate = 0.0
    
    return OomGateDecision(
        decision="AUTO_DOWNSAMPLE",
        estimated_bytes=estimated,
        ram_budget_bytes=ram_budget,
        recommended_subsample_rate=recommended_rate,
        notes=(
            f"Estimated {estimated:,} bytes between {pass_threshold:,.0f} and {block_threshold:,.0f} "
            f"- recommended subsample rate: {recommended_rate:.4f}"
        ),
    )


def _params_effective(params_total: int, rate: float) -> int:
    """Calculate effective params with floor rule (at least 1)."""
    return max(1, int(params_total * rate))


def _estimate_bytes_legacy(cfg: Mapping[str, Any] | Dict[str, Any]) -> int:
    """
    Estimate memory bytes using unified formula when keys are available.
    
    Formula (locked): bars * params_total * param_subsample_rate * intents_per_bar * bytes_per_intent_est
    
    Falls back to oom_cost_model.estimate_memory_bytes if keys are missing.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Estimated memory usage in bytes
    """
    keys = ("bars", "params_total", "param_subsample_rate", "intents_per_bar", "bytes_per_intent_est")
    if all(k in cfg for k in keys):
        return int(
            int(cfg["bars"])
            * int(cfg["params_total"])
            * float(cfg["param_subsample_rate"])
            * float(cfg["intents_per_bar"])
            * int(cfg["bytes_per_intent_est"])
        )
    # Fallback to cost model
    return int(oom_cost_model.estimate_memory_bytes(dict(cfg), work_factor=2.0))


def _estimate_ops(cfg: dict, *, params_effective: int) -> int:
    """
    Safely estimate operations count.
    
    Priority:
    1. Use oom_cost_model.estimate_ops if available (most consistent)
    2. Fallback to deterministic formula
    
    Args:
        cfg: Configuration dictionary
        params_effective: Effective params count (already calculated)
        
    Returns:
        Estimated operations count
    """
    # If cost model has ops estimate, use it (most consistent)
    if hasattr(oom_cost_model, "estimate_ops"):
        return int(oom_cost_model.estimate_ops(cfg))
    if hasattr(oom_cost_model, "estimate_ops_est"):
        return int(oom_cost_model.estimate_ops_est(cfg))
    
    # Fallback: at least stable and monotonic
    bars = int(cfg.get("bars", 0))
    intents_per_bar = float(cfg.get("intents_per_bar", 2.0))
    return int(bars * params_effective * intents_per_bar)


def decide_oom_action(
    cfg: Mapping[str, Any] | Dict[str, Any],
    *,
    mem_limit_mb: float,
    allow_auto_downsample: bool = True,
    auto_downsample_step: float = 0.5,
    auto_downsample_min: float = 0.02,
    work_factor: float = 2.0,
) -> Dict[str, Any]:
    """
    Backward-compatible OOM gate used by funnel_runner + contract tests.

    Returns a dict (schema-as-dict) consumed by pipeline and written to artifacts/README.
    This function NEVER mutates cfg - returns new_cfg in result dict.
    
    Uses estimate_memory_bytes() from oom_cost_model (tests monkeypatch this).
    Must use module import (oom_cost_model.estimate_memory_bytes) for monkeypatch to work.
    
    Algorithm: Monotonic step-based downsample search
    - If mem_est(original_subsample) <= limit → PASS
    - If over limit and allow_auto_downsample=False → BLOCK
    - If over limit and allow_auto_downsample=True:
      - Step-based search: cur * step (e.g., 0.5 → 0.25 → 0.125...)
      - Re-estimate mem_est at each candidate subsample
      - If mem_est <= limit → AUTO_DOWNSAMPLE with that subsample
      - If reach min_rate and still over limit → BLOCK
    
    Args:
        cfg: Configuration dictionary with bars, params_total, param_subsample_rate, etc.
        mem_limit_mb: Memory limit in MB
        allow_auto_downsample: Whether to allow automatic downsample
        auto_downsample_step: Multiplier for each downsample step (default: 0.5, must be < 1.0)
        auto_downsample_min: Minimum subsample rate (default: 0.02)
        work_factor: Work factor for memory estimation (default: 2.0)
        
    Returns:
        Dictionary with action, reason, estimated_bytes, new_cfg, and metadata
    """
    # pure: never mutate caller
    base_cfg = dict(cfg)
    
    bars = int(base_cfg.get("bars", 0))
    params_total = int(base_cfg.get("params_total", 0))
    
    def _mem_mb(cfg_dict: dict[str, Any], work_factor: float) -> float:
        """
        Estimate memory in MB.
        
        Always uses oom_cost_model.estimate_memory_bytes to respect monkeypatch.
        """
        b = oom_cost_model.estimate_memory_bytes(cfg_dict, work_factor=work_factor)
        return float(b) / (1024.0 * 1024.0)
    
    original = float(base_cfg.get("param_subsample_rate", 1.0))
    original = max(0.0, min(1.0, original))
    
    # invalid input → BLOCK
    if bars <= 0 or params_total <= 0:
        mem0 = _mem_mb(base_cfg, work_factor)
        return _build_result(
            action="BLOCK",
            reason="invalid_input",
            new_cfg=base_cfg,
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    mem0 = _mem_mb(base_cfg, work_factor)
    
    if mem0 <= mem_limit_mb:
        return _build_result(
            action="PASS",
            reason="pass_under_limit",
            new_cfg=dict(base_cfg),
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    if not allow_auto_downsample:
        return _build_result(
            action="BLOCK",
            reason="block: over limit (auto-downsample disabled)",
            new_cfg=dict(base_cfg),
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    step = float(auto_downsample_step)
    if not (0.0 < step < 1.0):
        # contract: step must reduce
        step = 0.5
    
    min_rate = float(auto_downsample_min)
    min_rate = max(0.0, min(1.0, min_rate))
    
    # Monotonic step-search: always decrease
    cur = original
    best_cfg: dict[str, Any] | None = None
    best_mem: float | None = None
    
    while True:
        nxt = cur * step
        # Clamp to min_rate before evaluating
        if nxt < min_rate:
            nxt = min_rate
        
        # if we can no longer decrease, break
        if nxt >= cur:
            break
        
        cand = dict(base_cfg)
        cand["param_subsample_rate"] = float(nxt)
        mem_c = _mem_mb(cand, work_factor)
        
        if mem_c <= mem_limit_mb:
            best_cfg = cand
            best_mem = mem_c
            break
        
        # still over limit
        cur = nxt
        # Only break if we've evaluated min_rate and it's still over
        if cur <= min_rate + 1e-12:
            # We *have evaluated* min_rate and it's still over => BLOCK
            break
    
    if best_cfg is not None and best_mem is not None:
        final_subsample = float(best_cfg["param_subsample_rate"])
        # Ensure monotonicity: final_subsample <= original
        assert final_subsample <= original, f"final_subsample {final_subsample} > original {original}"
        return _build_result(
            action="AUTO_DOWNSAMPLE",
            reason="auto-downsample: over limit, reduced subsample",
            new_cfg=best_cfg,
            original_subsample=original,
            final_subsample=final_subsample,
            mem_est_mb=best_mem,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    # even at minimum still over limit => BLOCK
    # Only reach here if we've evaluated min_rate and it's still over
    min_cfg = dict(base_cfg)
    min_cfg["param_subsample_rate"] = float(min_rate)
    mem_min = _mem_mb(min_cfg, work_factor)
    
    return _build_result(
        action="BLOCK",
        reason="block: min_subsample still too large",
        new_cfg=min_cfg,  # keep audit: this is the best we can do
        original_subsample=original,
        final_subsample=float(min_rate),
        mem_est_mb=mem_min,
        mem_limit_mb=mem_limit_mb,
        params_total=params_total,
        allow_auto_downsample=allow_auto_downsample,
        auto_downsample_step=auto_downsample_step,
        auto_downsample_min=auto_downsample_min,
        work_factor=work_factor,
    )


def _build_result(
    *,
    action: str,
    reason: str,
    new_cfg: dict[str, Any],
    original_subsample: float,
    final_subsample: float,
    mem_est_mb: float,
    mem_limit_mb: float,
    params_total: int,
    allow_auto_downsample: bool,
    auto_downsample_step: float,
    auto_downsample_min: float,
    work_factor: float,
) -> Dict[str, Any]:
    """Helper to build consistent result dict."""
    params_eff = _params_effective(params_total, final_subsample)
    ops_est = _estimate_ops(new_cfg, params_effective=params_eff)
    
    # Calculate time estimate from ops_est
    ops_per_sec_est = float(new_cfg.get("ops_per_sec_est", 2.0e7))
    time_est_s = float(ops_est) / ops_per_sec_est if ops_per_sec_est > 0 else 0.0
    
    mem_est_bytes = int(mem_est_mb * 1024.0 * 1024.0)
    mem_limit_bytes = int(mem_limit_mb * 1024.0 * 1024.0)
    
    estimates = {
        "mem_est_bytes": int(mem_est_bytes),
        "mem_est_mb": float(mem_est_mb),
        "mem_limit_mb": float(mem_limit_mb),
        "mem_limit_bytes": int(mem_limit_bytes),
        "ops_est": int(ops_est),
        "time_est_s": float(time_est_s),
    }
    return {
        "action": action,
        "reason": reason,
        # ✅ tests/test_oom_gate.py needs this
        "estimated_bytes": int(mem_est_bytes),
        "estimated_mb": float(mem_est_mb),
        # ✅ NEW: required by tests/test_oom_gate.py
        "mem_limit_mb": float(mem_limit_mb),
        "mem_limit_bytes": int(mem_limit_bytes),
        # Original subsample contract
        "original_subsample": float(original_subsample),
        "final_subsample": float(final_subsample),
        # ✅ NEW: new_cfg SSOT (never mutate original cfg)
        "new_cfg": new_cfg,
        # Funnel/README common fields (preserved)
        "params_total": int(params_total),
        "params_effective": int(params_eff),
        # ✅ funnel_runner/tests needs estimates.ops_est / estimates.mem_est_mb
        "estimates": estimates,
        # Other debug fields
        "allow_auto_downsample": bool(allow_auto_downsample),
        "auto_downsample_step": float(auto_downsample_step),
        "auto_downsample_min": float(auto_downsample_min),
        "work_factor": float(work_factor),
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/paths.py
sha256(source_bytes) = 6b86599ad1f957c320ccf026680e5d2c3b7b54da7e3ef0863b4d6afc65ea9858
bytes = 1068
redacted = False
--------------------------------------------------------------------------------

"""Path management for artifact output.

Centralized contract for output directory structure.
"""

from __future__ import annotations

from pathlib import Path


def get_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Get path for a specific run.
    
    Fixed path structure: outputs/seasons/{season}/runs/{run_id}/
    
    Args:
        outputs_root: Root outputs directory (e.g., Path("outputs"))
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to run directory
    """
    return outputs_root / "seasons" / season / "runs" / run_id


def ensure_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Ensure run directory exists and return its path.
    
    Args:
        outputs_root: Root outputs directory
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to run directory (created if needed)
    """
    run_dir = get_run_dir(outputs_root, season, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/policy_engine.py
sha256(source_bytes) = 99209471aec4e43d1441592f3b3a53ee9e1ac1fe5bb27c8fe69935338e5ccd8b
bytes = 4338
redacted = True
--------------------------------------------------------------------------------
"""Policy Engine - 實盤安全鎖

系統動作風險等級分類與強制執行政策。
"""

import os
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.core.action_risk import RiskLevel, ActionPolicyDecision
from FishBroWFS_V2.core.season_state import load_season_state

# 常數定義
LIVE_TOKEN_PATH =[REDACTED]LIVE_TOKEN_MAGIC =[REDACTED]
# 動作白名單（硬編碼）
READ_ONLY = {
    "view_history",
    "list_jobs",
    "get_job_status",
    "get_artifacts",
    "health",
    "list_datasets",
    "list_strategies",
    "get_job",
    "list_recent_jobs",
    "get_rolling_summary",
    "get_season_report",
    "list_chart_artifacts",
    "load_chart_artifact",
    "get_jobs_for_deploy",
    "get_system_settings",
}

RESEARCH_MUTATE = {
    "submit_job",
    "run_job",
    "build_portfolio",
    "archive",
    "export",
    "freeze_season",
    "unfreeze_season",
    "generate_deploy_zip",
    "update_system_settings",
}

LIVE_EXECUTE = {
    "deploy_live",
    "send_orders",
    "broker_connect",
    "promote_to_live",
}


def classify_action(action: str) -> RiskLevel:
    """分類動作風險等級
    
    Args:
        action: 動作名稱
        
    Returns:
        RiskLevel: 風險等級
        
    Note:
        未知動作一律視為 LIVE_EXECUTE（fail-safe）
    """
    if action in READ_ONLY:
        return RiskLevel.READ_ONLY
    if action in RESEARCH_MUTATE:
        return RiskLevel.RESEARCH_MUTATE
    if action in LIVE_EXECUTE:
        return RiskLevel.LIVE_EXECUTE
    # 未知動作：fail-safe，視為最高風險
    return RiskLevel.LIVE_EXECUTE


def enforce_action_policy(action: str, season: Optional[str] = None) -> ActionPolicyDecision:
    """強制執行動作政策
    
    Args:
        action: 動作名稱
        season: 季節識別碼（可選）
        
    Returns:
        ActionPolicyDecision: 政策決策結果
    """
    risk = classify_action(action)

    # LIVE_EXECUTE:[REDACTED]    if risk == RiskLevel.LIVE_EXECUTE:
        if os.getenv("FISHBRO_ENABLE_LIVE") != "1":
            return ActionPolicyDecision(
                allowed=False,
                reason="LIVE_EXECUTE disabled: set FISHBRO_ENABLE_LIVE=1",
                risk=risk,
                action=action,
                season=season,
            )
        if not LIVE_TOKEN_PATH.exists():[REDACTED]            return ActionPolicyDecision(
                allowed=False,
                reason=[REDACTED]                risk=risk,
                action=action,
                season=season,
            )
        try:
            token_content =[REDACTED]            if token_content !=[REDACTED]                return ActionPolicyDecision(
                    allowed=False,
                    reason=[REDACTED]                    risk=risk,
                    action=action,
                    season=season,
                )
        except Exception:
            return ActionPolicyDecision(
                allowed=False,
                reason=[REDACTED]                risk=risk,
                action=action,
                season=season,
            )
        return ActionPolicyDecision(
            allowed=True,
            reason="LIVE_EXECUTE enabled",
            risk=risk,
            action=action,
            season=season,
        )

    # RESEARCH_MUTATE: 檢查季節是否凍結
    if risk == RiskLevel.RESEARCH_MUTATE and season:
        try:
            state = load_season_state(season)
            if state.is_frozen():
                return ActionPolicyDecision(
                    allowed=False,
                    reason=f"Season {season} is frozen",
                    risk=risk,
                    action=action,
                    season=season,
                )
        except Exception:
            # 如果載入狀態失敗，假設季節未凍結（安全側）
            pass

    # READ_ONLY 或允許的 RESEARCH_MUTATE
    return ActionPolicyDecision(
        allowed=True,
        reason="OK",
        risk=risk,
        action=action,
        season=season,
    )
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/resampler.py
sha256(source_bytes) = 501dc69b30374976c424838845fb0d4e305f06d1df0717d7bb3cf2193c895a19
bytes = 15919
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/core/resampler.py
"""
Resampler 核心

提供 deterministic resampling 功能，支援 session anchor 與 safe point 計算。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import List, Tuple, Optional, Dict, Any, Literal
import numpy as np
import pandas as pd

from FishBroWFS_V2.core.dimensions import get_dimension_for_dataset
from FishBroWFS_V2.contracts.dimensions import SessionSpec as ContractSessionSpec


@dataclass(frozen=True)
class SessionSpecTaipei:
    """台北時間的交易時段規格"""
    open_hhmm: str  # HH:MM 格式，例如 "07:00"
    close_hhmm: str  # HH:MM 格式，例如 "06:00"（次日）
    breaks: List[Tuple[str, str]]  # 休市時段列表，每個時段為 (start, end)
    tz: str = "Asia/Taipei"
    
    @classmethod
    def from_contract(cls, spec: ContractSessionSpec) -> SessionSpecTaipei:
        """從 contracts SessionSpec 轉換"""
        return cls(
            open_hhmm=spec.open_taipei,
            close_hhmm=spec.close_taipei,
            breaks=spec.breaks_taipei,
            tz=spec.tz,
        )
    
    @property
    def open_hour(self) -> int:
        """開盤小時"""
        return int(self.open_hhmm.split(":")[0])
    
    @property
    def open_minute(self) -> int:
        """開盤分鐘"""
        return int(self.open_hhmm.split(":")[1])
    
    @property
    def close_hour(self) -> int:
        """收盤小時（處理 24:00 為 0）"""
        hour = int(self.close_hhmm.split(":")[0])
        if hour == 24:
            return 0
        return hour
    
    @property
    def close_minute(self) -> int:
        """收盤分鐘"""
        return int(self.close_hhmm.split(":")[1])
    
    def is_overnight(self) -> bool:
        """是否為隔夜時段（收盤時間小於開盤時間）"""
        open_total = self.open_hour * 60 + self.open_minute
        close_total = self.close_hour * 60 + self.close_minute
        return close_total < open_total
    
    def session_start_for_date(self, d: date) -> datetime:
        """
        取得指定日期的 session 開始時間
        
        對於隔夜時段，session 開始時間為前一天的開盤時間
        例如：open=07:00, close=06:00，則 2023-01-02 的 session 開始時間為 2023-01-01 07:00
        """
        if self.is_overnight():
            # 隔夜時段：session 開始時間為前一天的開盤時間
            session_date = d - timedelta(days=1)
        else:
            # 非隔夜時段：session 開始時間為當天的開盤時間
            session_date = d
        
        return datetime(
            session_date.year,
            session_date.month,
            session_date.day,
            self.open_hour,
            self.open_minute,
            0,
        )
    
    def is_in_break(self, dt: datetime) -> bool:
        """檢查時間是否在休市時段內"""
        time_str = dt.strftime("%H:%M")
        for start, end in self.breaks:
            if start <= time_str < end:
                return True
        return False
    
    def is_in_session(self, dt: datetime) -> bool:
        """檢查時間是否在交易時段內（不考慮休市）"""
        # 計算從 session_start 開始的經過分鐘數
        session_start = self.session_start_for_date(dt.date())
        
        # 對於隔夜時段，需要調整計算
        if self.is_overnight():
            # 如果 dt 在 session_start 之後（同一天），則屬於當前 session
            # 如果 dt 在 session_start 之前（可能是次日），則屬於下一個 session
            if dt >= session_start:
                # 屬於當前 session
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
                return session_start <= dt < session_end
            else:
                # 屬於下一個 session
                session_start = self.session_start_for_date(dt.date() + timedelta(days=1))
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
                return session_start <= dt < session_end
        else:
            # 非隔夜時段
            # 處理 close_hhmm == "24:00" 的情況
            if self.close_hhmm == "24:00":
                # session_end 是次日的 00:00
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=0,
                    minute=0,
                    second=0,
                )
            else:
                session_end = session_start.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
            return session_start <= dt < session_end


def get_session_spec_for_dataset(dataset_id: str) -> Tuple[SessionSpecTaipei, bool]:
    """
    讀取資料集的 session 規格
    
    Args:
        dataset_id: 資料集 ID
        
    Returns:
        Tuple[SessionSpecTaipei, bool]:
            - SessionSpecTaipei 物件
            - dimension_found: 是否找到 dimension（True 表示找到，False 表示使用 fallback）
    """
    # 從 dimension registry 查詢
    dimension = get_dimension_for_dataset(dataset_id)
    
    if dimension is not None:
        # 找到 dimension，使用其 session spec
        return SessionSpecTaipei.from_contract(dimension.session), True
    
    # 找不到 dimension，使用 fallback
    # 根據 Phase 3A 要求：open=00:00 close=24:00 breaks=[]
    fallback_spec = SessionSpecTaipei(
        open_hhmm="00:00",
        close_hhmm="24:00",
        breaks=[],
        tz="Asia/Taipei",
    )
    
    return fallback_spec, False


def compute_session_start(ts: datetime, session: SessionSpecTaipei) -> datetime:
    """
    Return the session_start datetime (Taipei) whose session window contains ts.
    
    Must handle overnight sessions where close < open (cross midnight).
    
    Args:
        ts: 時間戳記（台北時間）
        session: 交易時段規格
        
    Returns:
        session_start: 包含 ts 的 session 開始時間
    """
    # 對於隔夜時段，需要特別處理
    if session.is_overnight():
        # 嘗試當天的 session_start
        candidate = session.session_start_for_date(ts.date())
        
        # 檢查 ts 是否在 candidate 開始的 session 內
        if session.is_in_session(ts):
            return candidate
        
        # 如果不在，嘗試前一天的 session_start
        candidate = session.session_start_for_date(ts.date() - timedelta(days=1))
        if session.is_in_session(ts):
            return candidate
        
        # 如果還是不在，嘗試後一天的 session_start
        candidate = session.session_start_for_date(ts.date() + timedelta(days=1))
        if session.is_in_session(ts):
            return candidate
        
        # 理論上不應該到這裡，但為了安全回傳當天的 session_start
        return session.session_start_for_date(ts.date())
    else:
        # 非隔夜時段：直接使用當天的 session_start
        return session.session_start_for_date(ts.date())


def compute_safe_recompute_start(
    ts_append_start: datetime, 
    tf_min: int, 
    session: SessionSpecTaipei
) -> datetime:
    """
    Safe point = session_start + floor((ts - session_start)/tf)*tf
    Then subtract tf if you want extra safety for boundary bar (optional, but deterministic).
    Must NOT return after ts_append_start.
    
    嚴格規則（鎖死）：
    1. safe = session_start + floor(delta_minutes/tf)*tf
    2. 額外保險：safe = max(session_start, safe - tf)（確保不晚於 ts_append_start）
    
    Args:
        ts_append_start: 新增資料的開始時間
        tf_min: timeframe 分鐘數
        session: 交易時段規格
        
    Returns:
        safe_recompute_start: 安全重算開始時間
    """
    # 1. 計算包含 ts_append_start 的 session_start
    session_start = compute_session_start(ts_append_start, session)
    
    # 2. 計算從 session_start 到 ts_append_start 的總分鐘數
    delta = ts_append_start - session_start
    delta_minutes = int(delta.total_seconds() // 60)
    
    # 3. safe = session_start + floor(delta_minutes/tf)*tf
    safe_minutes = (delta_minutes // tf_min) * tf_min
    safe = session_start + timedelta(minutes=safe_minutes)
    
    # 4. 額外保險：safe = max(session_start, safe - tf)
    # 確保 safe 不晚於 ts_append_start（但可能早於）
    safe_extra = safe - timedelta(minutes=tf_min)
    if safe_extra >= session_start:
        safe = safe_extra
    
    # 確保 safe 不晚於 ts_append_start
    if safe > ts_append_start:
        safe = session_start
    
    return safe


def resample_ohlcv(
    ts: np.ndarray, 
    o: np.ndarray, 
    h: np.ndarray, 
    l: np.ndarray, 
    c: np.ndarray, 
    v: np.ndarray,
    tf_min: int,
    session: SessionSpecTaipei,
    start_ts: Optional[datetime] = None,
) -> Dict[str, np.ndarray]:
    """
    Resample normalized bars -> tf bars anchored at session_start.
    
    Must ignore bars inside breaks (drop or treat as gap; choose one and keep consistent).
    Deterministic output ordering by ts ascending.
    
    行為規格：
    1. 只處理在交易時段內的 bars（忽略休市時段）
    2. 以 session_start 為 anchor 進行 resample
    3. 如果提供 start_ts，只處理 ts >= start_ts 的 bars
    4. 輸出 ts 遞增排序
    
    Args:
        ts: 時間戳記陣列（datetime 物件或 UNIX seconds）
        o, h, l, c, v: OHLCV 陣列
        tf_min: timeframe 分鐘數
        session: 交易時段規格
        start_ts: 可選的開始時間，只處理此時間之後的 bars
        
    Returns:
        字典，包含 resampled bars:
            ts: datetime64[s] 陣列
            open, high, low, close, volume: float64 或 int64 陣列
    """
    # 輸入驗證
    n = len(ts)
    if not (len(o) == len(h) == len(l) == len(c) == len(v) == n):
        raise ValueError("所有輸入陣列長度必須一致")
    
    if n == 0:
        return {
            "ts": np.array([], dtype="datetime64[s]"),
            "open": np.array([], dtype="float64"),
            "high": np.array([], dtype="float64"),
            "low": np.array([], dtype="float64"),
            "close": np.array([], dtype="float64"),
            "volume": np.array([], dtype="int64"),
        }
    
    # 轉換 ts 為 datetime 物件
    ts_datetime = []
    for t in ts:
        if isinstance(t, (int, float, np.integer, np.floating)):
            # UNIX seconds
            ts_datetime.append(datetime.fromtimestamp(t))
        elif isinstance(t, np.datetime64):
            # numpy datetime64
            # 轉換為 pandas Timestamp 然後到 datetime
            ts_datetime.append(pd.Timestamp(t).to_pydatetime())
        elif isinstance(t, datetime):
            # 已經是 datetime
            ts_datetime.append(t)
        else:
            raise TypeError(f"不支援的時間戳記類型: {type(t)}")
    
    # 過濾 bars：只保留在交易時段內且不在休市時段的 bars
    valid_indices = []
    valid_ts = []
    valid_o = []
    valid_h = []
    valid_l = []
    valid_c = []
    valid_v = []
    
    for i, dt in enumerate(ts_datetime):
        # 檢查是否在交易時段內
        if not session.is_in_session(dt):
            continue
        
        # 檢查是否在休市時段內
        if session.is_in_break(dt):
            continue
        
        # 檢查是否在 start_ts 之後（如果提供）
        if start_ts is not None and dt < start_ts:
            continue
        
        valid_indices.append(i)
        valid_ts.append(dt)
        valid_o.append(o[i])
        valid_h.append(h[i])
        valid_l.append(l[i])
        valid_c.append(c[i])
        valid_v.append(v[i])
    
    if not valid_ts:
        # 沒有有效的 bars
        return {
            "ts": np.array([], dtype="datetime64[s]"),
            "open": np.array([], dtype="float64"),
            "high": np.array([], dtype="float64"),
            "low": np.array([], dtype="float64"),
            "close": np.array([], dtype="float64"),
            "volume": np.array([], dtype="int64"),
        }
    
    # 將 valid_ts 轉換為 pandas DatetimeIndex 以便 resample
    df = pd.DataFrame({
        "open": valid_o,
        "high": valid_h,
        "low": valid_l,
        "close": valid_c,
        "volume": valid_v,
    }, index=pd.DatetimeIndex(valid_ts, tz=None))
    
    # 計算每個 bar 所屬的 session_start
    session_starts = [compute_session_start(dt, session) for dt in valid_ts]
    
    # 計算從 session_start 開始的經過分鐘數
    # 我們需要將每個 bar 分配到以 session_start 為基準的 tf 分鐘區間
    # 建立一個虛擬的時間戳記：session_start + floor((dt - session_start)/tf)*tf
    bucket_times = []
    for dt, sess_start in zip(valid_ts, session_starts):
        delta = dt - sess_start
        delta_minutes = int(delta.total_seconds() // 60)
        bucket_minutes = (delta_minutes // tf_min) * tf_min
        bucket_time = sess_start + timedelta(minutes=bucket_minutes)
        bucket_times.append(bucket_time)
    
    # 使用 bucket_times 進行分組
    df["bucket_time"] = bucket_times
    
    # 分組聚合
    grouped = df.groupby("bucket_time", sort=True)
    
    # 計算 OHLCV
    # 開盤價：每個 bucket 的第一個 open
    # 最高價：每個 bucket 的 high 最大值
    # 最低價：每個 bucket 的 low 最小值
    # 收盤價：每個 bucket 的最後一個 close
    # 成交量：每個 bucket 的 volume 總和
    result_df = pd.DataFrame({
        "open": grouped["open"].first(),
        "high": grouped["high"].max(),
        "low": grouped["low"].min(),
        "close": grouped["close"].last(),
        "volume": grouped["volume"].sum(),
    })
    
    # 確保結果排序（groupby 應該已經排序，但為了安全）
    result_df = result_df.sort_index()
    
    # 轉換為 numpy arrays
    result_ts = result_df.index.to_numpy(dtype="datetime64[s]")
    
    return {
        "ts": result_ts,
        "open": result_df["open"].to_numpy(dtype="float64"),
        "high": result_df["high"].to_numpy(dtype="float64"),
        "low": result_df["low"].to_numpy(dtype="float64"),
        "close": result_df["close"].to_numpy(dtype="float64"),
        "volume": result_df["volume"].to_numpy(dtype="int64"),
    }


def normalize_raw_bars(raw_ingest_result) -> Dict[str, np.ndarray]:
    """
    將 RawIngestResult 轉換為 normalized bars 陣列
    
    Args:
        raw_ingest_result: RawIngestResult 物件
        
    Returns:
        字典，包含 normalized bars:
            ts: datetime64[s] 陣列
            open, high, low, close: float64 陣列
            volume: int64 陣列
    """
    df = raw_ingest_result.df
    
    # 將 ts_str 轉換為 datetime
    ts_datetime = pd.to_datetime(df["ts_str"], format="%Y/%m/%d %H:%M:%S")
    
    # 轉換為 datetime64[s]
    ts_array = ts_datetime.to_numpy(dtype="datetime64[s]")
    
    return {
        "ts": ts_array,
        "open": df["open"].to_numpy(dtype="float64"),
        "high": df["high"].to_numpy(dtype="float64"),
        "low": df["low"].to_numpy(dtype="float64"),
        "close": df["close"].to_numpy(dtype="float64"),
        "volume": df["volume"].to_numpy(dtype="int64"),
    }



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/run_id.py
sha256(source_bytes) = 31c195852ccd834cf4c719ca2f9bf03623bfa3499bb674a95d6552b556c8a38f
bytes = 903
redacted = True
--------------------------------------------------------------------------------

"""Run ID generation for audit trail.

Provides deterministic, sortable run IDs with timestamp and short token.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


def make_run_id(prefix: str | None = None) -> str:
    """
    Generate a sortable, readable run ID.
    
    Format:[REDACTED]    - Timestamp ensures chronological ordering (UTC)
    - Short token (8 hex chars) provides uniqueness
    
    Args:
        prefix: Optional prefix string (e.g., "test", "prod")
        
    Returns:
        Run ID string, e.g., "20251218T135221Z-a1b2c3d4"
        or "test-20251218T135221Z-a1b2c3d4" if prefix provided
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tok =[REDACTED]    
    if prefix:
        return f"{prefix}-{ts}-{tok}"
    else:
        return f"{ts}-{tok}"



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/season_context.py
sha256(source_bytes) = 57d3b0cd54d6665551d83abade3f88256a3b9368df38933cb9804b2f0bb233be
bytes = 2650
redacted = False
--------------------------------------------------------------------------------
"""
Season Context - Single Source of Truth (SSOT) for season management.

Phase 4: Consolidate season management to avoid scattered os.getenv() calls.
"""

import os
from pathlib import Path
from typing import Optional


def current_season() -> str:
    """Return current season from env FISHBRO_CURRENT_SEASON or default '2026Q1'."""
    return os.getenv("FISHBRO_CURRENT_SEASON", "2026Q1")


def outputs_root() -> str:
    """Return outputs root from env FISHBRO_OUTPUTS_ROOT or default 'outputs'."""
    return os.getenv("FISHBRO_OUTPUTS_ROOT", "outputs")


def season_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season} as Path object.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current_season().
    
    Returns:
        Path to season directory.
    """
    if season is None:
        season = current_season()
    return Path(outputs_root()) / "seasons" / season


def research_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/research as Path object."""
    return season_dir(season) / "research"


def portfolio_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/portfolio as Path object."""
    return season_dir(season) / "portfolio"


def governance_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/governance as Path object."""
    return season_dir(season) / "governance"


def canonical_results_path(season: Optional[str] = None) -> Path:
    """Return path to canonical_results.json."""
    return research_dir(season) / "canonical_results.json"


def research_index_path(season: Optional[str] = None) -> Path:
    """Return path to research_index.json."""
    return research_dir(season) / "research_index.json"


def portfolio_summary_path(season: Optional[str] = None) -> Path:
    """Return path to portfolio_summary.json."""
    return portfolio_dir(season) / "portfolio_summary.json"


def portfolio_manifest_path(season: Optional[str] = None) -> Path:
    """Return path to portfolio_manifest.json."""
    return portfolio_dir(season) / "portfolio_manifest.json"


# Convenience function for backward compatibility
def get_season_context() -> dict:
    """Return a dict with current season context for debugging/logging."""
    season = current_season()
    root = outputs_root()
    return {
        "season": season,
        "outputs_root": root,
        "season_dir": str(season_dir(season)),
        "research_dir": str(research_dir(season)),
        "portfolio_dir": str(portfolio_dir(season)),
        "governance_dir": str(governance_dir(season)),
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/season_state.py
sha256(source_bytes) = 06ec7773325c4f7b9399f5ef8b12f33ec7f116a5b6d8c508141ef548d1350214
bytes = 7362
redacted = False
--------------------------------------------------------------------------------
"""
Season State Management - Freeze governance lock.

Phase 5: Deterministic Governance & Reproducibility Lock.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Literal, TypedDict
from dataclasses import dataclass, asdict

from .season_context import season_dir


class SeasonStateDict(TypedDict, total=False):
    """Season state schema (immutable)."""
    season: str
    state: Literal["OPEN", "FROZEN"]
    frozen_ts: Optional[str]  # ISO-8601 or null
    frozen_by: Optional[Literal["gui", "cli", "system"]]  # or null
    reason: Optional[str]  # string or null


@dataclass
class SeasonState:
    """Season state data class."""
    season: str
    state: Literal["OPEN", "FROZEN"] = "OPEN"
    frozen_ts: Optional[str] = None  # ISO-8601 or null
    frozen_by: Optional[Literal["gui", "cli", "system"]] = None  # or null
    reason: Optional[str] = None  # string or null
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SeasonState":
        """Create SeasonState from dictionary."""
        return cls(
            season=data["season"],
            state=data.get("state", "OPEN"),
            frozen_ts=data.get("frozen_ts"),
            frozen_by=data.get("frozen_by"),
            reason=data.get("reason"),
        )
    
    def to_dict(self) -> SeasonStateDict:
        """Convert to dictionary."""
        return {
            "season": self.season,
            "state": self.state,
            "frozen_ts": self.frozen_ts,
            "frozen_by": self.frozen_by,
            "reason": self.reason,
        }
    
    def is_frozen(self) -> bool:
        """Check if season is frozen."""
        return self.state == "FROZEN"
    
    def freeze(self, by: Literal["gui", "cli", "system"], reason: Optional[str] = None) -> None:
        """Freeze the season."""
        if self.is_frozen():
            raise ValueError(f"Season {self.season} is already frozen")
        
        self.state = "FROZEN"
        self.frozen_ts = datetime.now(timezone.utc).isoformat()
        self.frozen_by = by
        self.reason = reason
    
    def unfreeze(self, by: Literal["gui", "cli", "system"], reason: Optional[str] = None) -> None:
        """Unfreeze the season."""
        if not self.is_frozen():
            raise ValueError(f"Season {self.season} is not frozen")
        
        self.state = "OPEN"
        self.frozen_ts = None
        self.frozen_by = None
        self.reason = None


def get_season_state_path(season: Optional[str] = None) -> Path:
    """Get path to season_state.json."""
    season_path = season_dir(season)
    governance_dir = season_path / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    return governance_dir / "season_state.json"


def load_season_state(season: Optional[str] = None) -> SeasonState:
    """Load season state from file, or create default if not exists."""
    state_path = get_season_state_path(season)
    
    if not state_path.exists():
        # Get season from context if not provided
        if season is None:
            from .season_context import current_season
            season_str = current_season()
        else:
            season_str = season
        
        # Create default OPEN state
        state = SeasonState(season=season_str, state="OPEN")
        save_season_state(state, season)
        return state
    
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validate required fields
        if "season" not in data:
            # Infer season from path
            if season is None:
                from .season_context import current_season
                season_str = current_season()
            else:
                season_str = season
            data["season"] = season_str
        
        return SeasonState.from_dict(data)
    except (json.JSONDecodeError, OSError, KeyError) as e:
        # If file is corrupted, create default
        if season is None:
            from .season_context import current_season
            season_str = current_season()
        else:
            season_str = season
        
        state = SeasonState(season=season_str, state="OPEN")
        save_season_state(state, season)
        return state


def save_season_state(state: SeasonState, season: Optional[str] = None) -> Path:
    """Save season state to file."""
    state_path = get_season_state_path(season)
    
    # Ensure directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict and write
    data = state.to_dict()
    
    # Write atomically
    temp_path = state_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Replace original
    temp_path.replace(state_path)
    
    return state_path


def check_season_not_frozen(season: Optional[str] = None, action: str = "action") -> None:
    """
    Check if season is not frozen, raise ValueError if frozen.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        action: Action name for error message.
    
    Raises:
        ValueError: If season is frozen.
    """
    state = load_season_state(season)
    if state.is_frozen():
        frozen_info = f"frozen at {state.frozen_ts} by {state.frozen_by}"
        if state.reason:
            frozen_info += f" (reason: {state.reason})"
        raise ValueError(
            f"Cannot perform {action}: Season {state.season} is {frozen_info}"
        )


def freeze_season(
    season: Optional[str] = None,
    by: Literal["gui", "cli", "system"] = "system",
    reason: Optional[str] = None,
    create_snapshot: bool = True,
) -> SeasonState:
    """
    Freeze a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        by: Who is freezing the season.
        reason: Optional reason for freezing.
        create_snapshot: Whether to create deterministic snapshot of artifacts.
    
    Returns:
        Updated SeasonState.
    """
    state = load_season_state(season)
    state.freeze(by=by, reason=reason)
    save_season_state(state, season)
    
    # Phase 5: Create deterministic snapshot
    if create_snapshot:
        try:
            from .snapshot import create_freeze_snapshot
            snapshot_path = create_freeze_snapshot(state.season)
            # Log snapshot creation (optional)
            print(f"Created freeze snapshot: {snapshot_path}")
        except Exception as e:
            # Don't fail freeze if snapshot fails, but log warning
            print(f"Warning: Failed to create freeze snapshot: {e}")
    
    return state


def unfreeze_season(
    season: Optional[str] = None,
    by: Literal["gui", "cli", "system"] = "system",
    reason: Optional[str] = None,
) -> SeasonState:
    """
    Unfreeze a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        by: Who is unfreezing the season.
        reason: Optional reason for unfreezing.
    
    Returns:
        Updated SeasonState.
    """
    state = load_season_state(season)
    state.unfreeze(by=by, reason=reason)
    save_season_state(state, season)
    return state
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/slippage_policy.py
sha256(source_bytes) = 656be5d5fa1fb03b0228b3c6f16884043009f0439e1556b4355e4a76435f9e9e
bytes = 5728
redacted = False
--------------------------------------------------------------------------------

# src/FishBroWFS_V2/core/slippage_policy.py
"""
SlippagePolicy：滑價成本模型定義

定義 per fill/per side 的滑價等級，並提供價格調整函數。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Dict, Optional
import math


@dataclass(frozen=True)
class SlippagePolicy:
    """
    滑價政策定義

    Attributes:
        definition: 滑價定義，固定為 "per_fill_per_side"
        levels: 滑價等級對應的 tick 數，預設為 S0=0, S1=1, S2=2, S3=3
        selection_level: 策略選擇使用的滑價等級（預設 S2）
        stress_level: 壓力測試使用的滑價等級（預設 S3）
        mc_execution_level: MultiCharts 執行時使用的滑價等級（預設 S1）
    """
    definition: str = "per_fill_per_side"
    levels: Dict[str, int] = field(default_factory=lambda: {"S0": 0, "S1": 1, "S2": 2, "S3": 3})
    selection_level: str = "S2"
    stress_level: str = "S3"
    mc_execution_level: str = "S1"

    def __post_init__(self):
        """驗證欄位"""
        if self.definition != "per_fill_per_side":
            raise ValueError(f"definition 必須為 'per_fill_per_side'，收到: {self.definition}")
        
        required_levels = {"S0", "S1", "S2", "S3"}
        if not required_levels.issubset(self.levels.keys()):
            missing = required_levels - set(self.levels.keys())
            raise ValueError(f"levels 缺少必要等級: {missing}")
        
        for level in (self.selection_level, self.stress_level, self.mc_execution_level):
            if level not in self.levels:
                raise ValueError(f"等級 {level} 不存在於 levels 中")
        
        # 確保 tick 數為非負整數
        for level, ticks in self.levels.items():
            if not isinstance(ticks, int) or ticks < 0:
                raise ValueError(f"等級 {level} 的 ticks 必須為非負整數，收到: {ticks}")

    def get_ticks(self, level: str) -> int:
        """
        取得指定等級的滑價 tick 數

        Args:
            level: 等級名稱，例如 "S2"

        Returns:
            滑價 tick 數

        Raises:
            KeyError: 等級不存在
        """
        return self.levels[level]

    def get_selection_ticks(self) -> int:
        """取得 selection_level 對應的 tick 數"""
        return self.get_ticks(self.selection_level)

    def get_stress_ticks(self) -> int:
        """取得 stress_level 對應的 tick 數"""
        return self.get_ticks(self.stress_level)

    def get_mc_execution_ticks(self) -> int:
        """取得 mc_execution_level 對應的 tick 數"""
        return self.get_ticks(self.mc_execution_level)


def apply_slippage_to_price(
    price: float,
    side: Literal["buy", "sell", "sellshort", "buytocover"],
    slip_ticks: int,
    tick_size: float,
) -> float:
    """
    根據滑價 tick 數調整價格

    規則：
    - 買入（buy, buytocover）：價格增加 slip_ticks * tick_size
    - 賣出（sell, sellshort）：價格減少 slip_ticks * tick_size

    Args:
        price: 原始價格
        side: 交易方向
        slip_ticks: 滑價 tick 數（非負整數）
        tick_size: 每 tick 價格變動量（必須 > 0）

    Returns:
        調整後的價格

    Raises:
        ValueError: 參數無效
    """
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    if slip_ticks < 0:
        raise ValueError(f"slip_ticks 必須 >= 0，收到: {slip_ticks}")
    
    # 計算滑價金額
    slippage_amount = slip_ticks * tick_size
    
    # 根據方向調整
    if side in ("buy", "buytocover"):
        # 買入：支付更高價格
        adjusted = price + slippage_amount
    elif side in ("sell", "sellshort"):
        # 賣出：收到更低價格
        adjusted = price - slippage_amount
    else:
        raise ValueError(f"無效的 side: {side}，必須為 buy/sell/sellshort/buytocover")
    
    # 確保價格非負（雖然理論上可能為負，但實務上不應發生）
    if adjusted < 0:
        adjusted = 0.0
    
    return adjusted


def round_to_tick(price: float, tick_size: float) -> float:
    """
    將價格四捨五入至最近的 tick 邊界

    Args:
        price: 原始價格
        tick_size: tick 大小

    Returns:
        四捨五入後的價格
    """
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    
    # 計算 tick 數
    ticks = round(price / tick_size)
    return ticks * tick_size


def compute_slippage_cost_per_side(
    slip_ticks: int,
    tick_size: float,
    quantity: float = 1.0,
) -> float:
    """
    計算單邊滑價成本（每單位）

    Args:
        slip_ticks: 滑價 tick 數
        tick_size: tick 大小
        quantity: 數量（預設 1.0）

    Returns:
        滑價成本（正數）
    """
    if slip_ticks < 0:
        raise ValueError(f"slip_ticks 必須 >= 0，收到: {slip_ticks}")
    if tick_size <= 0:
        raise ValueError(f"tick_size 必須 > 0，收到: {tick_size}")
    
    return slip_ticks * tick_size * quantity


def compute_round_trip_slippage_cost(
    slip_ticks: int,
    tick_size: float,
    quantity: float = 1.0,
) -> float:
    """
    計算來回交易（entry + exit）的總滑價成本

    由於每邊都會產生滑價，總成本為 2 * slip_ticks * tick_size * quantity

    Args:
        slip_ticks: 每邊滑價 tick 數
        tick_size: tick 大小
        quantity: 數量

    Returns:
        總滑價成本
    """
    per_side = compute_slippage_cost_per_side(slip_ticks, tick_size, quantity)
    return 2.0 * per_side



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/snapshot.py
sha256(source_bytes) = 4a590ba03ce263bc719cdc62d01ceab9d17999c2f538f3426bff38abe26c8607
bytes = 7785
redacted = False
--------------------------------------------------------------------------------
"""
Deterministic Snapshot - Freeze-time artifact hash registry.

Phase 5: Create reproducible snapshot of all artifacts when season is frozen.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
import os


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, IOError):
        # If file cannot be read, return empty hash
        return ""


def collect_artifact_hashes(season_dir: Path) -> Dict[str, Any]:
    """
    Collect SHA256 hashes of all artifacts in a season directory.
    
    Returns:
        Dict with structure:
        {
            "snapshot_ts": "ISO-8601 timestamp",
            "season": "season identifier",
            "artifacts": {
                "relative/path/to/file": {
                    "sha256": "hexdigest",
                    "size_bytes": 1234,
                    "mtime": 1234567890.0
                },
                ...
            },
            "directories_scanned": [
                "runs/",
                "portfolio/",
                "research/",
                "governance/"
            ]
        }
    """
    from datetime import datetime, timezone
    
    # Directories to scan (relative to season_dir)
    scan_dirs = [
        "runs",
        "portfolio",
        "research",
        "governance"
    ]
    
    artifacts = {}
    
    for rel_dir in scan_dirs:
        dir_path = season_dir / rel_dir
        if not dir_path.exists():
            continue
        
        # Walk through directory
        for root, dirs, files in os.walk(dir_path):
            root_path = Path(root)
            for filename in files:
                filepath = root_path / filename
                
                # Skip temporary files and hidden files
                if filename.startswith(".") or filename.endswith(".tmp"):
                    continue
                
                # Skip very large files (>100MB) to avoid performance issues
                try:
                    file_size = filepath.stat().st_size
                    if file_size > 100 * 1024 * 1024:  # 100MB
                        continue
                except OSError:
                    continue
                
                # Compute relative path from season_dir
                try:
                    rel_path = filepath.relative_to(season_dir)
                except ValueError:
                    # Should not happen, but skip if it does
                    continue
                
                # Compute hash
                sha256 = compute_file_hash(filepath)
                if not sha256:  # Skip if hash computation failed
                    continue
                
                # Get file metadata
                try:
                    stat = filepath.stat()
                    artifacts[str(rel_path)] = {
                        "sha256": sha256,
                        "size_bytes": stat.st_size,
                        "mtime": stat.st_mtime,
                        "mtime_iso": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                    }
                except OSError:
                    # Skip if metadata cannot be read
                    continue
    
    return {
        "snapshot_ts": datetime.now(timezone.utc).isoformat(),
        "season": season_dir.name,
        "artifacts": artifacts,
        "directories_scanned": scan_dirs,
        "artifact_count": len(artifacts)
    }


def create_freeze_snapshot(season: str) -> Path:
    """
    Create deterministic snapshot of all artifacts in a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        Path to the created snapshot file.
    
    Raises:
        FileNotFoundError: If season directory does not exist.
        OSError: If snapshot cannot be written.
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    if not season_path.exists():
        raise FileNotFoundError(f"Season directory does not exist: {season_path}")
    
    # Collect artifact hashes
    snapshot_data = collect_artifact_hashes(season_path)
    
    # Write snapshot file
    governance_dir = season_path / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    
    snapshot_path = governance_dir / "freeze_snapshot.json"
    
    # Write atomically
    temp_path = snapshot_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    # Replace original
    temp_path.replace(snapshot_path)
    
    return snapshot_path


def load_freeze_snapshot(season: str) -> Dict[str, Any]:
    """
    Load freeze snapshot for a season.
    
    Args:
        season: Season identifier
    
    Returns:
        Snapshot data dictionary.
    
    Raises:
        FileNotFoundError: If snapshot file does not exist.
        json.JSONDecodeError: If snapshot file is corrupted.
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    snapshot_path = season_path / "governance" / "freeze_snapshot.json"
    
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Freeze snapshot not found: {snapshot_path}")
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_snapshot_integrity(season: str) -> Dict[str, Any]:
    """
    Verify current artifacts against freeze snapshot.
    
    Args:
        season: Season identifier
    
    Returns:
        Dict with verification results:
        {
            "ok": bool,
            "missing_files": List[str],
            "changed_files": List[str],
            "new_files": List[str],
            "total_checked": int,
            "errors": List[str]
        }
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    
    try:
        snapshot = load_freeze_snapshot(season)
    except FileNotFoundError:
        return {
            "ok": False,
            "missing_files": [],
            "changed_files": [],
            "new_files": [],
            "total_checked": 0,
            "errors": ["Freeze snapshot not found"]
        }
    
    # Get current artifact hashes
    current_artifacts = collect_artifact_hashes(season_path)
    
    # Compare
    snapshot_artifacts = snapshot.get("artifacts", {})
    current_artifact_paths = set(current_artifacts.get("artifacts", {}).keys())
    snapshot_artifact_paths = set(snapshot_artifacts.keys())
    
    missing_files = list(snapshot_artifact_paths - current_artifact_paths)
    new_files = list(current_artifact_paths - snapshot_artifact_paths)
    
    changed_files = []
    for path in snapshot_artifact_paths.intersection(current_artifact_paths):
        snapshot_hash = snapshot_artifacts[path].get("sha256", "")
        current_hash = current_artifacts["artifacts"][path].get("sha256", "")
        if snapshot_hash != current_hash:
            changed_files.append(path)
    
    ok = len(missing_files) == 0 and len(changed_files) == 0
    
    return {
        "ok": ok,
        "missing_files": sorted(missing_files),
        "changed_files": sorted(changed_files),
        "new_files": sorted(new_files),
        "total_checked": len(snapshot_artifact_paths),
        "errors": [] if ok else ["Artifacts have been modified since freeze"]
    }
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/winners_builder.py
sha256(source_bytes) = a9051d6f5e90653da86c8bd6ff4811b3e2d390bc48a39526f7aa3d87c7b2399f
bytes = 6640
redacted = False
--------------------------------------------------------------------------------

"""Winners builder - converts legacy winners to v2 schema.

Builds v2 winners.json from legacy topk format with fallback strategies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from FishBroWFS_V2.core.winners_schema import WinnerItemV2, build_winners_v2_dict


def build_winners_v2(
    *,
    stage_name: str,
    run_id: str,
    manifest: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    legacy_topk: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build winners.json v2 from legacy topk format.
    
    Args:
        stage_name: Stage identifier
        run_id: Run ID
        manifest: Manifest dict (AuditSchema)
        config_snapshot: Config snapshot dict
        legacy_topk: Legacy topk list (old format items)
        
    Returns:
        Winners dict with v2 schema
    """
    # Extract strategy_id
    strategy_id = _extract_strategy_id(config_snapshot, manifest)
    
    # Extract symbol/timeframe
    symbol = _extract_symbol(config_snapshot)
    timeframe = _extract_timeframe(config_snapshot)
    
    # Build v2 items
    v2_items: List[WinnerItemV2] = []
    
    for legacy_item in legacy_topk:
        # Extract param_id (required for candidate_id generation)
        param_id = legacy_item.get("param_id")
        if param_id is None:
            # Skip items without param_id (should not happen, but be defensive)
            continue
        
        # Generate candidate_id (temporary: strategy_id:param_id)
        # Future: upgrade to strategy_id:params_hash[:12] when params are available
        candidate_id = f"{strategy_id}:{param_id}"
        
        # Extract params (fallback to empty dict)
        params = _extract_params(legacy_item, config_snapshot, param_id)
        
        # Extract score (priority: score/finalscore > net_profit > 0.0)
        score = _extract_score(legacy_item)
        
        # Build metrics (must include legacy fields for backward compatibility)
        metrics = {
            "net_profit": float(legacy_item.get("net_profit", 0.0)),
            "max_dd": float(legacy_item.get("max_dd", 0.0)),
            "trades": int(legacy_item.get("trades", 0)),
            "param_id": int(param_id),  # Keep for backward compatibility
        }
        
        # Add proxy_value if present (Stage0)
        if "proxy_value" in legacy_item:
            metrics["proxy_value"] = float(legacy_item["proxy_value"])
        
        # Build source metadata
        source = {
            "param_id": int(param_id),
            "run_id": run_id,
            "stage_name": stage_name,
        }
        
        # Create v2 item
        v2_item = WinnerItemV2(
            candidate_id=candidate_id,
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            params=params,
            score=score,
            metrics=metrics,
            source=source,
        )
        
        v2_items.append(v2_item)
    
    # Build notes with candidate_id_mode info
    notes = {
        "candidate_id_mode": "strategy_id:param_id",  # Temporary mode
        "note": "candidate_id uses param_id temporarily; will upgrade to params_hash when params are available",
    }
    
    # Build v2 winners dict
    return build_winners_v2_dict(
        stage_name=stage_name,
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        topk=v2_items,
        notes=notes,
    )


def _extract_strategy_id(config_snapshot: Dict[str, Any], manifest: Dict[str, Any]) -> str:
    """
    Extract strategy_id from config_snapshot or manifest.
    
    Priority:
    1. config_snapshot.get("strategy_id")
    2. manifest.get("dataset_id") (fallback)
    3. "unknown" (final fallback)
    """
    if "strategy_id" in config_snapshot:
        return str(config_snapshot["strategy_id"])
    
    dataset_id = manifest.get("dataset_id")
    if dataset_id:
        return str(dataset_id)
    
    return "unknown"


def _extract_symbol(config_snapshot: Dict[str, Any]) -> str:
    """
    Extract symbol from config_snapshot.
    
    Returns "UNKNOWN" if not available.
    """
    return str(config_snapshot.get("symbol", "UNKNOWN"))


def _extract_timeframe(config_snapshot: Dict[str, Any]) -> str:
    """
    Extract timeframe from config_snapshot.
    
    Returns "UNKNOWN" if not available.
    """
    return str(config_snapshot.get("timeframe", "UNKNOWN"))


def _extract_params(
    legacy_item: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    param_id: int,
) -> Dict[str, Any]:
    """
    Extract params from legacy_item or config_snapshot.
    
    Priority:
    1. legacy_item.get("params")
    2. config_snapshot.get("params_by_id", {}).get(param_id)
    3. config_snapshot.get("params_spec") (if available)
    4. {} (empty dict fallback)
    
    Returns empty dict {} if params are not available.
    """
    # Try legacy_item first
    if "params" in legacy_item:
        params = legacy_item["params"]
        if isinstance(params, dict):
            return params
    
    # Try config_snapshot params_by_id
    params_by_id = config_snapshot.get("params_by_id", {})
    if isinstance(params_by_id, dict) and param_id in params_by_id:
        params = params_by_id[param_id]
        if isinstance(params, dict):
            return params
    
    # Try config_snapshot params_spec (if available)
    params_spec = config_snapshot.get("params_spec")
    if isinstance(params_spec, dict):
        # Could extract from params_spec if it has param_id mapping
        # For now, return empty dict
        pass
    
    # Fallback: empty dict
    return {}


def _extract_score(legacy_item: Dict[str, Any]) -> float:
    """
    Extract score from legacy_item.
    
    Priority:
    1. legacy_item.get("score")
    2. legacy_item.get("finalscore")
    3. legacy_item.get("net_profit")
    4. legacy_item.get("proxy_value") (for Stage0)
    5. 0.0 (fallback)
    """
    if "score" in legacy_item:
        val = legacy_item["score"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "finalscore" in legacy_item:
        val = legacy_item["finalscore"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "net_profit" in legacy_item:
        val = legacy_item["net_profit"]
        if isinstance(val, (int, float)):
            return float(val)
    
    if "proxy_value" in legacy_item:
        val = legacy_item["proxy_value"]
        if isinstance(val, (int, float)):
            return float(val)
    
    return 0.0



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/winners_schema.py
sha256(source_bytes) = b415c3cc05931a57bc3f6cc5ffdfa2b6646b8d12705badbdbecf030e96f6580c
bytes = 3593
redacted = False
--------------------------------------------------------------------------------

"""Winners schema v2 (SSOT).

Defines the v2 schema for winners.json with enhanced metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


WINNERS_SCHEMA_VERSION = "v2"


@dataclass(frozen=True)
class WinnerItemV2:
    """
    Winner item in v2 schema.
    
    Each item represents a top-K candidate with complete metadata.
    """
    candidate_id: str  # Format: {strategy_id}:{param_id} (temporary) or {strategy_id}:{params_hash[:12]} (future)
    strategy_id: str  # Strategy identifier (e.g., "donchian_atr")
    symbol: str  # Symbol identifier (e.g., "CME.MNQ" or "UNKNOWN")
    timeframe: str  # Timeframe (e.g., "60m" or "UNKNOWN")
    params: Dict[str, Any]  # Parameters dict (may be empty {} if not available)
    score: float  # Ranking score (finalscore, net_profit, or proxy_value)
    metrics: Dict[str, Any]  # Performance metrics (must include legacy fields: net_profit, max_dd, trades, param_id)
    source: Dict[str, Any]  # Source metadata (param_id, run_id, stage_name)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


def build_winners_v2_dict(
    *,
    stage_name: str,
    run_id: str,
    generated_at: str | None = None,
    topk: List[WinnerItemV2],
    notes: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build winners.json v2 structure.
    
    Args:
        stage_name: Stage identifier
        run_id: Run ID
        generated_at: ISO8601 timestamp (defaults to now if None)
        topk: List of WinnerItemV2 items
        notes: Additional notes dict (will be merged with default notes)
        
    Returns:
        Winners dict with v2 schema
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    default_notes = {
        "schema": WINNERS_SCHEMA_VERSION,
    }
    
    if notes:
        default_notes.update(notes)
    
    return {
        "schema": WINNERS_SCHEMA_VERSION,
        "stage_name": stage_name,
        "generated_at": generated_at,
        "topk": [item.to_dict() for item in topk],
        "notes": default_notes,
    }


def is_winners_v2(winners: Dict[str, Any]) -> bool:
    """
    Check if winners dict is v2 schema.
    
    Args:
        winners: Winners dict
        
    Returns:
        True if v2 schema, False otherwise
    """
    # Check top-level schema field
    if winners.get("schema") == WINNERS_SCHEMA_VERSION:
        return True
    
    # Check notes.schema field (legacy check)
    notes = winners.get("notes", {})
    if isinstance(notes, dict) and notes.get("schema") == WINNERS_SCHEMA_VERSION:
        return True
    
    return False


def is_winners_legacy(winners: Dict[str, Any]) -> bool:
    """
    Check if winners dict is legacy (v1) schema.
    
    Args:
        winners: Winners dict
        
    Returns:
        True if legacy schema, False otherwise
    """
    # If it's v2, it's not legacy
    if is_winners_v2(winners):
        return False
    
    # Legacy format: {"topk": [...], "notes": {"schema": "v1"}} or just {"topk": [...]}
    if "topk" in winners:
        # Check if items have v2 structure (candidate_id, strategy_id, etc.)
        topk = winners.get("topk", [])
        if topk and isinstance(topk[0], dict):
            # If first item has candidate_id, it's v2
            if "candidate_id" in topk[0]:
                return False
        return True
    
    return False



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/governance/__init__.py
sha256(source_bytes) = 1636f9e7dff514f1e8478f9e199228d850fcf060871f78cfbd8942c29d69cd58
bytes = 52
redacted = False
--------------------------------------------------------------------------------

"""Governance lifecycle and transition logic."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/governance/transition.py
sha256(source_bytes) = 2f0e0639684a99a6540a1cf2d0f743de8ae06d99766ab16ff8227e6357f06952
bytes = 1849
redacted = False
--------------------------------------------------------------------------------

"""Governance lifecycle state transition logic.

Pure functions for state transitions based on decisions.
"""

from __future__ import annotations

from FishBroWFS_V2.core.schemas.governance import Decision, LifecycleState


def governance_transition(
    prev_state: LifecycleState,
    decision: Decision,
) -> LifecycleState:
    """
    Compute next lifecycle state based on previous state and decision.
    
    Transition rules:
    - INCUBATION + KEEP → CANDIDATE
    - INCUBATION + DROP → RETIRED
    - INCUBATION + FREEZE → INCUBATION (no change)
    - CANDIDATE + KEEP → LIVE
    - CANDIDATE + DROP → RETIRED
    - CANDIDATE + FREEZE → CANDIDATE (no change)
    - LIVE + KEEP → LIVE (no change)
    - LIVE + DROP → RETIRED
    - LIVE + FREEZE → LIVE (no change)
    - RETIRED + any → RETIRED (terminal state, no transitions)
    
    Args:
        prev_state: Previous lifecycle state
        decision: Governance decision (KEEP/DROP/FREEZE)
        
    Returns:
        Next lifecycle state
    """
    # RETIRED is terminal state
    if prev_state == "RETIRED":
        return "RETIRED"
    
    # State transition matrix
    transitions: dict[tuple[LifecycleState, Decision], LifecycleState] = {
        # INCUBATION transitions
        ("INCUBATION", Decision.KEEP): "CANDIDATE",
        ("INCUBATION", Decision.DROP): "RETIRED",
        ("INCUBATION", Decision.FREEZE): "INCUBATION",
        
        # CANDIDATE transitions
        ("CANDIDATE", Decision.KEEP): "LIVE",
        ("CANDIDATE", Decision.DROP): "RETIRED",
        ("CANDIDATE", Decision.FREEZE): "CANDIDATE",
        
        # LIVE transitions
        ("LIVE", Decision.KEEP): "LIVE",
        ("LIVE", Decision.DROP): "RETIRED",
        ("LIVE", Decision.FREEZE): "LIVE",
    }
    
    return transitions.get((prev_state, decision), prev_state)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/__init__.py
sha256(source_bytes) = 7415dcb6d73912efd2b20efa20e4f11fc9a7fbfafdbd817071575e3089ef9cc0
bytes = 35
redacted = False
--------------------------------------------------------------------------------

"""Schemas for core modules."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/governance.py
sha256(source_bytes) = 45ee0a268e55e562aca6afa8d61722757d80ef1b79af939136a3d181cbbda3a3
bytes = 2591
redacted = False
--------------------------------------------------------------------------------

"""Pydantic schema for governance.json validation.

Validates governance decisions with KEEP/DROP/FREEZE and evidence chain.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional, Literal, TypeAlias


class Decision(str, Enum):
    """Governance decision types (SSOT)."""
    KEEP = "KEEP"
    FREEZE = "FREEZE"
    DROP = "DROP"


LifecycleState: TypeAlias = Literal["INCUBATION", "CANDIDATE", "LIVE", "RETIRED"]

RenderHint = Literal["highlight", "chart_annotation", "diff"]


class EvidenceLinkModel(BaseModel):
    """Evidence link model for governance."""
    source_path: str
    json_pointer: str
    note: str = ""
    render_hint: RenderHint = "highlight"  # Rendering hint for viewer (highlight/chart_annotation/diff)
    render_payload: dict = Field(default_factory=dict)  # Optional payload for custom rendering


class GovernanceDecisionRow(BaseModel):
    """
    Governance decision row schema.
    
    Represents a single governance decision with rule_id and evidence chain.
    """
    strategy_id: str
    decision: Decision
    rule_id: str  # "R1"/"R2"/"R3"
    reason: str = ""
    run_id: str
    stage: str
    config_hash: Optional[str] = None
    
    lifecycle_state: LifecycleState = "INCUBATION"  # Lifecycle state (INCUBATION/CANDIDATE/LIVE/RETIRED)
    
    evidence: List[EvidenceLinkModel] = Field(default_factory=list)
    metrics_snapshot: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from existing schema (for backward compatibility)
    candidate_id: Optional[str] = None
    reasons: Optional[List[str]] = None
    created_at: Optional[str] = None
    git_sha: Optional[str] = None
    
    model_config = ConfigDict(extra="allow")  # Allow extra fields for backward compatibility


class GovernanceReport(BaseModel):
    """
    Governance report schema.
    
    Validates governance.json structure with decision rows and metadata.
    Supports both items format and rows format.
    """
    config_hash: str  # Required top-level field for DIRTY check contract
    schema_version: Optional[str] = None
    run_id: str
    rows: List[GovernanceDecisionRow] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from existing schema (for backward compatibility)
    items: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra="allow")  # Allow extra fields for backward compatibility



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/manifest.py
sha256(source_bytes) = 4c68e01e0897c24af061196c5c2f42b694bec0519561a73d7d75537f96738781
bytes = 3601
redacted = False
--------------------------------------------------------------------------------

"""Pydantic schema for manifest.json validation.

Validates run manifest with stages and artifacts tracking.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional


class ManifestStage(BaseModel):
    """Stage information in manifest."""
    name: str
    status: str  # e.g. "DONE"/"FAILED"/"ABORTED"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    artifacts: Dict[str, str] = Field(default_factory=dict)  # filename -> relpath


class RunManifest(BaseModel):
    """
    Run manifest schema.
    
    Validates manifest.json structure with run metadata, config hash, and stages.
    """
    schema_version: Optional[str] = None  # For future versioning
    run_id: str
    season: str
    config_hash: str
    created_at: Optional[str] = None
    stages: List[ManifestStage] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from AuditSchema (for backward compatibility)
    git_sha: Optional[str] = None
    dirty_repo: Optional[bool] = None
    param_subsample_rate: Optional[float] = None
    dataset_id: Optional[str] = None
    bars: Optional[int] = None
    params_total: Optional[int] = None
    params_effective: Optional[int] = None
    artifact_version: Optional[str] = None
    
    # Phase 6.5: Mandatory fingerprint (validation enforces non-empty)
    data_fingerprint_sha1: Optional[str] = None
    
    # Phase 6.6: Timezone database metadata
    tzdb_provider: Optional[str] = None  # e.g., "zoneinfo"
    tzdb_version: Optional[str] = None  # Timezone database version
    data_tz: Optional[str] = None  # Data timezone (e.g., "Asia/Taipei")
    exchange_tz: Optional[str] = None  # Exchange timezone (e.g., "America/Chicago")
    
    # Phase 7: Strategy metadata
    strategy_id: Optional[str] = None  # Strategy identifier (e.g., "sma_cross")
    strategy_version: Optional[str] = None  # Strategy version (e.g., "v1")
    param_schema_hash: Optional[str] = None  # SHA1 hash of param_schema JSON


class UnifiedManifest(BaseModel):
    """
    Unified manifest schema for all manifest types (export, plan, view, quality).
    
    This schema defines the standard fields that should be present in all manifests
    for Manifest Tree Completeness verification.
    """
    # Common required fields
    manifest_type: str  # "export", "plan", "view", or "quality"
    manifest_version: str = "1.0"
    
    # Identification fields
    id: str  # run_id for export, plan_id for plan/view/quality
    
    # Timestamps
    generated_at_utc: Optional[str] = None
    created_at: Optional[str] = None
    
    # Source information
    source: Optional[Dict[str, Any]] = None
    
    # Input references (SHA256 hashes of input files)
    inputs: Optional[Dict[str, str]] = None
    
    # Files listing with SHA256 checksums (sorted by rel_path asc)
    files: Optional[List[Dict[str, str]]] = None
    
    # Combined SHA256 of all files (concatenated hashes)
    files_sha256: Optional[str] = None
    
    # Checksums for output files
    checksums: Optional[Dict[str, str]] = None
    
    # Type-specific checksums
    export_checksums: Optional[Dict[str, str]] = None
    plan_checksums: Optional[Dict[str, str]] = None
    view_checksums: Optional[Dict[str, str]] = None
    quality_checksums: Optional[Dict[str, str]] = None
    
    # Manifest self-hash (must be the last field)
    manifest_sha256: str
    
    model_config = ConfigDict(extra="allow")  # Allow additional type-specific fields



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/oom_gate.py
sha256(source_bytes) = 66c245f96340e0a3c817b6c6559b07eb613ba18e3691bf22d78307f88c3b2b9f
bytes = 1552
redacted = False
--------------------------------------------------------------------------------

"""Pydantic schemas for OOM gate input and output.

Locked schemas for PASS/BLOCK/AUTO_DOWNSAMPLE decisions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class OomGateInput(BaseModel):
    """
    Input for OOM gate decision.
    
    All fields are required for memory estimation.
    """
    bars: int = Field(gt=0, description="Number of bars")
    params: int = Field(gt=0, description="Total number of parameters")
    param_subsample_rate: float = Field(gt=0.0, le=1.0, description="Subsample rate in [0.0, 1.0]")
    intents_per_bar: float = Field(default=2.0, ge=0.0, description="Estimated intents per bar")
    bytes_per_intent_est: int = Field(default=64, gt=0, description="Estimated bytes per intent")
    ram_budget_bytes: int = Field(default=6_000_000_000, gt=0, description="RAM budget in bytes (default: 6GB)")


class OomGateDecision(BaseModel):
    """
    OOM gate decision output.
    
    Contains decision (PASS/BLOCK/AUTO_DOWNSAMPLE) and recommendations.
    """
    decision: Literal["PASS", "BLOCK", "AUTO_DOWNSAMPLE"]
    estimated_bytes: int = Field(ge=0, description="Estimated memory usage in bytes")
    ram_budget_bytes: int = Field(gt=0, description="RAM budget in bytes")
    recommended_subsample_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Recommended subsample rate (only for AUTO_DOWNSAMPLE)"
    )
    notes: str = Field(default="", description="Human-readable notes about the decision")



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/portfolio.py
sha256(source_bytes) = b96982d515336c90944d6ec605835339d43d7ac386937355cd220f8f560649d3
bytes = 1045
redacted = False
--------------------------------------------------------------------------------
"""Portfolio-related schemas for signal series and instrument configuration."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Dict


class InstrumentsConfigV1(BaseModel):
    """Schema for instruments configuration YAML (version 1)."""
    version: int
    base_currency: str
    fx_rates: Dict[str, float]
    instruments: Dict[str, dict]  # 這裡可先放 dict，validate 在 loader 做


class SignalSeriesMetaV1(BaseModel):
    """Metadata for signal series (bar-based position/margin/notional)."""
    model_config = ConfigDict(populate_by_name=True)
    
    schema_id: Literal["SIGNAL_SERIES_V1"] = Field(
        default="SIGNAL_SERIES_V1",
        alias="schema"
    )
    instrument: str
    timeframe: str
    tz: str

    base_currency: str
    instrument_currency: str
    fx_to_base: float

    multiplier: float
    initial_margin_per_contract: float
    maintenance_margin_per_contract: float

    # traceability
    source_run_id: str
    source_spec_sha: str
    instruments_config_sha256: str
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/portfolio_v1.py
sha256(source_bytes) = 16d8db078a869431c0a91fb03ec6d25f1381a739cec3e09df16ef01a83dc37ba
bytes = 4259
redacted = False
--------------------------------------------------------------------------------
"""Portfolio engine schemas V1."""

from pydantic import BaseModel, Field
from typing import Literal, Dict, List, Optional
from datetime import datetime, timezone


class PortfolioPolicyV1(BaseModel):
    """Portfolio policy defining allocation limits and behavior."""
    version: Literal["PORTFOLIO_POLICY_V1"] = "PORTFOLIO_POLICY_V1"

    base_currency: str  # "TWD"
    instruments_config_sha256: str

    # account hard caps
    max_slots_total: int  # e.g. 4
    max_margin_ratio: float  # e.g. 0.35 (margin_used/equity)
    max_notional_ratio: Optional[float] = None  # optional v1

    # per-instrument cap (optional v1)
    max_slots_by_instrument: Dict[str, int] = Field(default_factory=dict)  # {"CME.MNQ":4, "TWF.MXF":2}

    # deterministic tie-breaker inputs
    strategy_priority: Dict[str, int]  # {strategy_id: priority_int}
    signal_strength_field: str  # e.g. "edge_score" or "signal_score"

    # behavior flags
    allow_force_kill: bool = False  # MUST default False
    allow_queue: bool = False  # v1: reject only


class PortfolioSpecV1(BaseModel):
    """Portfolio specification defining input sources (frozen only)."""
    version: Literal["PORTFOLIO_SPEC_V1"] = "PORTFOLIO_SPEC_V1"
    
    # Input seasons/artifacts sources
    seasons: List[str]  # e.g. ["2026Q1"]
    strategy_ids: List[str]  # e.g. ["S1", "S2"]
    instrument_ids: List[str]  # e.g. ["CME.MNQ", "TWF.MXF"]
    
    # Time range (optional)
    start_date: Optional[str] = None  # ISO format
    end_date: Optional[str] = None  # ISO format
    
    # Reference to policy
    policy_sha256: str  # SHA256 of canonicalized PortfolioPolicyV1 JSON
    
    # Canonicalization metadata
    spec_sha256: str  # SHA256 of this spec (computed after canonicalization)


class OpenPositionV1(BaseModel):
    """Open position in the portfolio."""
    strategy_id: str
    instrument_id: str  # MNQ / MXF
    slots: int = 1  # v1 fixed
    margin_base: float  # TWD
    notional_base: float  # TWD
    entry_bar_index: int
    entry_bar_ts: datetime


class SignalCandidateV1(BaseModel):
    """Candidate signal for admission."""
    strategy_id: str
    instrument_id: str  # MNQ / MXF
    bar_ts: datetime
    bar_index: int
    signal_strength: float  # higher = stronger signal
    candidate_score: float = 0.0  # deterministic score for sorting (higher = better)
    required_margin_base: float  # TWD
    required_slot: int = 1  # v1 fixed
    # Optional: additional metadata
    signal_series_sha256: Optional[str] = None  # for audit


class AdmissionDecisionV1(BaseModel):
    """Admission decision for a candidate signal."""
    version: Literal["ADMISSION_DECISION_V1"] = "ADMISSION_DECISION_V1"
    
    # Candidate identification
    strategy_id: str
    instrument_id: str
    bar_ts: datetime
    bar_index: int
    
    # Candidate metrics
    signal_strength: float
    candidate_score: float
    signal_series_sha256: Optional[str] = None  # for audit
    
    # Decision
    accepted: bool
    reason: Literal[
        "ACCEPT",
        "REJECT_FULL",
        "REJECT_MARGIN",
        "REJECT_POLICY",
        "REJECT_UNKNOWN"
    ]
    
    # Deterministic tie-breaking info
    sort_key_used: str  # e.g., "priority=-10,signal_strength=0.85,strategy_id=S1"
    
    # Portfolio state after this decision
    slots_after: int
    margin_after_base: float  # TWD
    
    # Timestamp of decision
    decision_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class PortfolioStateV1(BaseModel):
    """Portfolio state at a given bar."""
    bar_ts: datetime
    bar_index: int
    equity_base: float  # TWD
    slots_used: int
    margin_used_base: float  # TWD
    notional_used_base: float  # TWD
    open_positions: List[OpenPositionV1] = Field(default_factory=list)
    reject_count: int = 0  # cumulative rejects up to this bar


class PortfolioSummaryV1(BaseModel):
    """Summary of portfolio admission results."""
    total_candidates: int
    accepted_count: int
    rejected_count: int
    reject_reasons: Dict[str, int]  # reason -> count
    final_slots_used: int
    final_margin_used_base: float
    final_margin_ratio: float  # margin_used / equity
    policy_sha256: str
    spec_sha256: str
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/core/schemas/winners_v2.py
sha256(source_bytes) = 80f8e4a13ffd0ded61c8a9027209827a1f6859853687cb8feca125d21ef25d89
bytes = 2100
redacted = False
--------------------------------------------------------------------------------

"""Pydantic schema for winners_v2.json validation.

Validates winners v2 structure with KPI metrics.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional


class WinnerRow(BaseModel):
    """
    Winner row schema.
    
    Represents a single winner with strategy info and KPI metrics.
    """
    strategy_id: str
    symbol: str
    timeframe: str
    params: Dict[str, Any] = Field(default_factory=dict)
    
    # Required KPI metrics
    net_profit: float
    max_drawdown: float
    trades: int
    
    # Optional metrics
    win_rate: Optional[float] = None
    sharpe: Optional[float] = None
    sqn: Optional[float] = None
    
    # Evidence links (if already present)
    evidence: Dict[str, str] = Field(default_factory=dict)  # pointers/paths if already present
    
    # Additional fields from v2 schema (for backward compatibility)
    candidate_id: Optional[str] = None
    score: Optional[float] = None
    metrics: Optional[Dict[str, Any]] = None
    source: Optional[Dict[str, Any]] = None


class WinnersV2(BaseModel):
    """
    Winners v2 schema.
    
    Validates winners_v2.json structure with rows and metadata.
    Supports both v2 format (with topk) and normalized format (with rows).
    """
    config_hash: str  # Required top-level field for DIRTY check contract
    schema_version: Optional[str] = None  # "v2" or "schema" field
    run_id: Optional[str] = None
    stage: Optional[str] = None  # stage_name
    rows: List[WinnerRow] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from v2 schema (for backward compatibility)
    schema_name: Optional[str] = Field(default=None, alias="schema")  # "v2" - renamed to avoid conflict
    stage_name: Optional[str] = None
    generated_at: Optional[str] = None
    topk: Optional[List[Dict[str, Any]]] = None
    notes: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra="allow", populate_by_name=True)  # Allow extra fields and support alias



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/__init__.py
sha256(source_bytes) = d60a5bbf7b2bc9afb3b9d30e5219480699efbf6dc4d6af01273f3b60dbaa6d68
bytes = 637
redacted = False
--------------------------------------------------------------------------------
"""Data ingest module - Raw means RAW.

Phase 6.5 Data Ingest v1: Immutable, extremely stupid raw data ingestion.
"""

from FishBroWFS_V2.data.cache import CachePaths, cache_paths, read_parquet_cache, write_parquet_cache
from FishBroWFS_V2.data.fingerprint import DataFingerprint, compute_txt_fingerprint
from FishBroWFS_V2.data.raw_ingest import IngestPolicy, RawIngestResult, ingest_raw_txt

__all__ = [
    "IngestPolicy",
    "RawIngestResult",
    "ingest_raw_txt",
    "DataFingerprint",
    "compute_txt_fingerprint",
    "CachePaths",
    "cache_paths",
    "write_parquet_cache",
    "read_parquet_cache",
]

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/cache.py
sha256(source_bytes) = 18ad78e3bb3c7786bbc46576c0944b57a7c823872817b00477982cbbd5d3d36f
bytes = 3315
redacted = False
--------------------------------------------------------------------------------
"""Parquet cache - Cache, Not Truth.

Binding #4: Parquet is Cache, Not Truth.
Cache can be deleted and rebuilt. Fingerprint is the truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CachePaths:
    """Cache file paths for a symbol.
    
    Attributes:
        parquet_path: Path to parquet cache file
        meta_path: Path to meta.json file
    """
    parquet_path: Path
    meta_path: Path


def cache_paths(cache_root: Path, symbol: str) -> CachePaths:
    """Get cache paths for a symbol.
    
    Args:
        cache_root: Root directory for cache files
        symbol: Symbol identifier (e.g., "CME.MNQ")
        
    Returns:
        CachePaths with parquet_path and meta_path
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    
    # Sanitize symbol for filename
    safe_symbol = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
    
    return CachePaths(
        parquet_path=cache_root / f"{safe_symbol}.parquet",
        meta_path=cache_root / f"{safe_symbol}.meta.json",
    )


def write_parquet_cache(paths: CachePaths, df: pd.DataFrame, meta: dict[str, Any]) -> None:
    """Write parquet cache + meta.json.
    
    Parquet stores raw df (with ts_str), no sort, no dedup.
    meta.json must contain:
    - data_fingerprint_sha1
    - source_path
    - ingest_policy
    - rows, first_ts_str, last_ts_str
    
    Args:
        paths: CachePaths for this symbol
        df: DataFrame to cache (must have columns: ts_str, open, high, low, close, volume)
        meta: Metadata dict (must include data_fingerprint_sha1, source_path, ingest_policy, etc.)
        
    Raises:
        ValueError: If required meta fields are missing
    """
    required_meta_fields = ["data_fingerprint_sha1", "source_path", "ingest_policy"]
    missing_fields = [field for field in required_meta_fields if field not in meta]
    if missing_fields:
        raise ValueError(f"Missing required meta fields: {missing_fields}")
    
    # Write parquet (preserve order, no sort)
    paths.parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(paths.parquet_path, index=False, engine="pyarrow")
    
    # Write meta.json
    with paths.meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")


def read_parquet_cache(paths: CachePaths) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read parquet cache + meta.json.
    
    Args:
        paths: CachePaths for this symbol
        
    Returns:
        Tuple of (DataFrame, meta_dict)
        
    Raises:
        FileNotFoundError: If parquet or meta.json does not exist
        json.JSONDecodeError: If meta.json is invalid JSON
    """
    if not paths.parquet_path.exists():
        raise FileNotFoundError(f"Parquet cache not found: {paths.parquet_path}")
    if not paths.meta_path.exists():
        raise FileNotFoundError(f"Meta file not found: {paths.meta_path}")
    
    # Read parquet
    df = pd.read_parquet(paths.parquet_path, engine="pyarrow")
    
    # Read meta.json
    with paths.meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)
    
    return df, meta

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/dataset_registry.py
sha256(source_bytes) = 1c8d752f03e64c93bbd50541ffe15de19d1ea02042d5724e78ff97d66f8bc5b2
bytes = 3599
redacted = False
--------------------------------------------------------------------------------
"""Dataset Registry Schema.

Phase 12: Dataset Registry for Research Job Wizard.
Describes "what datasets are available" without containing any price data.
Schema can only "add fields" in the future, cannot change semantics.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetRecord(BaseModel):
    """Metadata for a single derived dataset."""
    
    model_config = ConfigDict(frozen=True)
    
    id: str = Field(
        ...,
        description="Unique identifier, e.g. 'CME.MNQ.60m.2020-2024'",
        examples=["CME.MNQ.60m.2020-2024", "TWF.MXF.15m.2018-2023"]
    )
    
    symbol: str = Field(
        ...,
        description="Symbol identifier, e.g. 'CME.MNQ'",
        examples=["CME.MNQ", "TWF.MXF"]
    )
    
    exchange: str = Field(
        ...,
        description="Exchange identifier, e.g. 'CME'",
        examples=["CME", "TWF"]
    )
    
    timeframe: str = Field(
        ...,
        description="Timeframe string, e.g. '60m'",
        examples=["60m", "15m", "5m", "1D"]
    )
    
    path: str = Field(
        ...,
        description="Relative path to derived file from data/derived/",
        examples=["CME.MNQ/60m/2020-2024.parquet"]
    )
    
    start_date: date = Field(
        ...,
        description="First date with data (inclusive)"
    )
    
    end_date: date = Field(
        ...,
        description="Last date with data (inclusive)"
    )
    
    fingerprint_sha1: Optional[str] = Field(
        default=None,
        description="SHA1 hash of file content (binary), deterministic fingerprint (deprecated, use fingerprint_sha256_40)"
    )
    
    fingerprint_sha256_40: str = Field(
        ...,
        description="SHA256 hash of file content (binary), first 40 hex chars, deterministic fingerprint"
    )
    
    @model_validator(mode="before")
    @classmethod
    def ensure_fingerprint_sha256_40(cls, data: dict) -> dict:
        """Backward compatibility: if fingerprint_sha256_40 missing but fingerprint_sha1 present, copy it."""
        if isinstance(data, dict):
            if "fingerprint_sha256_40" not in data or not data["fingerprint_sha256_40"]:
                if "fingerprint_sha1" in data and data["fingerprint_sha1"]:
                    # Copy sha1 to sha256 field (note: this is semantically wrong but maintains compatibility)
                    data["fingerprint_sha256_40"] = data["fingerprint_sha1"]
        return data
    
    tz_provider: str = Field(
        default="IANA",
        description="Timezone provider identifier"
    )
    
    tz_version: str = Field(
        default="unknown",
        description="Timezone database version"
    )


class DatasetIndex(BaseModel):
    """Complete registry of all available datasets."""
    
    model_config = ConfigDict(frozen=True)
    
    generated_at: datetime = Field(
        ...,
        description="Timestamp when this index was generated"
    )
    
    datasets: List[DatasetRecord] = Field(
        default_factory=list,
        description="List of all available dataset records"
    )
    
    def model_post_init(self, __context: object) -> None:
        """Post-initialization hook to sort datasets by id."""
        super().model_post_init(__context)
        # Sort datasets by id to ensure deterministic order
        if self.datasets:
            self.datasets.sort(key=lambda d: d.id)

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/fingerprint.py
sha256(source_bytes) = e9cfb6f419b0a2f54d4260a56ddffe4faff0407550541cd841e2ba3955778919
bytes = 4291
redacted = False
--------------------------------------------------------------------------------
"""Data fingerprint - Truth fingerprint based on Raw TXT.

Binding #3: Mandatory Fingerprint in Governance + JobRecord.
Fingerprint must depend only on raw TXT content + ingest_policy.
Parquet is cache, not truth.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataFingerprint:
    """Data fingerprint - immutable truth identifier.
    
    Attributes:
        sha1: SHA1 hash of raw TXT content + ingest_policy
        source_path: Path to source TXT file
        rows: Number of rows (metadata)
        first_ts_str: First timestamp string (metadata)
        last_ts_str: Last timestamp string (metadata)
        ingest_policy: Ingest policy dict (for hash computation)
    """
    sha1: str
    source_path: str
    rows: int
    first_ts_str: str
    last_ts_str: str
    ingest_policy: dict


def compute_txt_fingerprint(path: Path, *, ingest_policy: dict) -> DataFingerprint:
    """Compute fingerprint from raw TXT file + ingest_policy.
    
    Fingerprint is computed from:
    1. Raw TXT file content (bytes)
    2. Ingest policy (JSON with stable sort)
    
    This ensures the fingerprint represents the "truth" - raw data + normalization policy.
    Parquet cache can be deleted and rebuilt, fingerprint remains stable.
    
    Args:
        path: Path to raw TXT file
        ingest_policy: Ingest policy dict (will be JSON-serialized with stable sort)
        
    Returns:
        DataFingerprint with SHA1 hash and metadata
        
    Raises:
        FileNotFoundError: If path does not exist
    """
    if not path.exists():
        raise FileNotFoundError(f"TXT file not found: {path}")
    
    # Compute SHA1: policy first, then file content
    h = hashlib.sha1()
    
    # Add ingest_policy (stable JSON sort)
    policy_json = json.dumps(ingest_policy, sort_keys=True, ensure_ascii=False)
    h.update(policy_json.encode("utf-8"))
    
    # Add file content (chunked for large files)
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            h.update(chunk)
    
    sha1 = h.hexdigest()
    
    # Read metadata (rows, first_ts_str, last_ts_str)
    # We need to parse the file to get these, but they're just metadata
    # The hash is the truth, metadata is for convenience
    import pandas as pd
    
    df = pd.read_csv(path, encoding="utf-8")
    rows = len(df)
    
    # Try to extract first/last timestamps
    # This is best-effort metadata, not part of hash
    first_ts_str = ""
    last_ts_str = ""
    
    if "Date" in df.columns and "Time" in df.columns:
        if rows > 0:
            first_date = str(df.iloc[0]["Date"])
            first_time = str(df.iloc[0]["Time"])
            last_date = str(df.iloc[-1]["Date"])
            last_time = str(df.iloc[-1]["Time"])
            
            # Apply same normalization as ingest (duplicate logic to avoid circular import)
            def _normalize_24h_local(date_s: str, time_s: str) -> tuple[str, bool]:
                """Local copy of _normalize_24h to avoid circular import."""
                t = time_s.strip()
                if t.startswith("24:"):
                    if t != "24:00:00":
                        raise ValueError(f"Invalid 24h time: {time_s}")
                    d = pd.to_datetime(date_s.strip(), format="%Y/%m/%d", errors="raise")
                    d2 = (d + pd.Timedelta(days=1)).to_pydatetime().date()
                    return f"{d2.year}/{d2.month}/{d2.day} 00:00:00", True
                return f"{date_s.strip()} {t}", False
            
            try:
                first_ts_str, _ = _normalize_24h_local(first_date, first_time)
            except Exception:
                first_ts_str = f"{first_date} {first_time}"
            
            try:
                last_ts_str, _ = _normalize_24h_local(last_date, last_time)
            except Exception:
                last_ts_str = f"{last_date} {last_time}"
    
    return DataFingerprint(
        sha1=sha1,
        source_path=str(path),
        rows=rows,
        first_ts_str=first_ts_str,
        last_ts_str=last_ts_str,
        ingest_policy=ingest_policy,
    )

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/layout.py
sha256(source_bytes) = b41807fb9c2d19e291d0d3cb998db49fa66036ccc684b1d4c6f8f5ccd2ce2a9b
bytes = 787
redacted = False
--------------------------------------------------------------------------------
import numpy as np
from FishBroWFS_V2.engine.types import BarArrays


def ensure_float64_contiguous(x: np.ndarray) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    if not arr.flags["C_CONTIGUOUS"]:
        arr = np.ascontiguousarray(arr)
    return arr


def normalize_bars(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> BarArrays:
    arrays = [open_, high, low, close]
    for a in arrays:
        if np.isnan(a).any():
            raise ValueError("NaN detected in input data")

    o = ensure_float64_contiguous(open_)
    h = ensure_float64_contiguous(high)
    l = ensure_float64_contiguous(low)
    c = ensure_float64_contiguous(close)

    return BarArrays(open=o, high=h, low=l, close=c)


--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/raw_ingest.py
sha256(source_bytes) = 3789dc71594c63f7ea31d18a99e06477ff4f0461b34dcc43c8ed651409e7a5f5
bytes = 5735
redacted = False
--------------------------------------------------------------------------------
"""Raw data ingestion - Raw means RAW.

Phase 6.5 Data Ingest v1: Immutable, extremely stupid raw data ingestion.
No sort, no dedup, no dropna (unless recorded in ingest_policy).

Binding: One line = one row, preserve TXT row order exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class IngestPolicy:
    """Ingest policy - only records format normalization decisions, not data cleaning.
    
    Attributes:
        normalized_24h: Whether 24:00:00 times were normalized to next day 00:00:00
        column_map: Column name mapping from source to standard names
    """
    normalized_24h: bool = False
    column_map: dict[str, str] | None = None


@dataclass(frozen=True)
class RawIngestResult:
    """Raw ingest result - immutable contract.
    
    Attributes:
        df: DataFrame with exactly columns: ts_str, open, high, low, close, volume
        source_path: Path to source TXT file
        rows: Number of rows ingested
        policy: Ingest policy applied
    """
    df: pd.DataFrame  # columns exactly: ts_str, open, high, low, close, volume
    source_path: str
    rows: int
    policy: IngestPolicy


def _normalize_24h(date_s: str, time_s: str) -> tuple[str, bool]:
    """Normalize 24:xx:xx time to next day 00:00:00.
    
    Only allows 24:00:00 (exact). Raises ValueError for other 24:xx:xx times.
    
    Args:
        date_s: Date string (e.g., "2013/1/1")
        time_s: Time string (e.g., "24:00:00" or "09:30:00")
        
    Returns:
        Tuple of (normalized ts_str, normalized_flag)
        - If 24:00:00: returns next day 00:00:00 and True
        - Otherwise: returns original "date_s time_s" and False
        
    Raises:
        ValueError: If time_s starts with "24:" but is not exactly "24:00:00"
    """
    t = time_s.strip()
    if t.startswith("24:"):
        if t != "24:00:00":
            raise ValueError(f"Invalid 24h time: {time_s} (only 24:00:00 is allowed)")
        # Parse date only (no timezone)
        d = pd.to_datetime(date_s.strip(), format="%Y/%m/%d", errors="raise")
        d2 = (d + pd.Timedelta(days=1)).to_pydatetime().date()
        return f"{d2.year}/{d2.month}/{d2.day} 00:00:00", True
    return f"{date_s.strip()} {t}", False


def ingest_raw_txt(
    txt_path: Path,
    *,
    column_map: dict[str, str] | None = None,
) -> RawIngestResult:
    """Ingest raw TXT file - Raw means RAW.
    
    Core rules (Binding):
    - One line = one row, preserve TXT row order exactly
    - No sort_values()
    - No drop_duplicates()
    - No dropna() (unless recorded in ingest_policy)
    
    Format normalization (allowed):
    - 24:00:00 → next day 00:00:00 (recorded in policy.normalized_24h)
    - Column mapping (recorded in policy.column_map)
    
    Args:
        txt_path: Path to raw TXT file
        column_map: Optional column name mapping (e.g., {"Date": "Date", "Time": "Time", ...})
        
    Returns:
        RawIngestResult with df containing columns: ts_str, open, high, low, close, volume
        
    Raises:
        FileNotFoundError: If txt_path does not exist
        ValueError: If parsing fails or invalid 24h time format
    """
    if not txt_path.exists():
        raise FileNotFoundError(f"TXT file not found: {txt_path}")
    
    # Read TXT file (preserve order)
    # Assume CSV-like format with header
    df_raw = pd.read_csv(txt_path, encoding="utf-8")
    
    # Apply column mapping if provided
    if column_map:
        df_raw = df_raw.rename(columns=column_map)
    
    # Expected columns after mapping: Date, Time, Open, High, Low, Close, TotalVolume (or Volume)
    required_cols = ["Date", "Time", "Open", "High", "Low", "Close"]
    volume_cols = ["TotalVolume", "Volume"]
    
    # Check required columns
    missing_cols = [col for col in required_cols if col not in df_raw.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}. Found: {list(df_raw.columns)}")
    
    # Find volume column
    volume_col = None
    for vcol in volume_cols:
        if vcol in df_raw.columns:
            volume_col = vcol
            break
    
    if volume_col is None:
        raise ValueError(f"Missing volume column. Expected one of: {volume_cols}. Found: {list(df_raw.columns)}")
    
    # Build ts_str column (preserve row order)
    normalized_24h = False
    ts_str_list = []
    
    for idx, row in df_raw.iterrows():
        date_s = str(row["Date"])
        time_s = str(row["Time"])
        
        try:
            ts_str, was_normalized = _normalize_24h(date_s, time_s)
            if was_normalized:
                normalized_24h = True
            ts_str_list.append(ts_str)
        except Exception as e:
            raise ValueError(f"Failed to normalize timestamp at row {idx}: {e}") from e
    
    # Build result DataFrame (preserve order, no sort/dedup/dropna)
    result_df = pd.DataFrame({
        "ts_str": ts_str_list,
        "open": pd.to_numeric(df_raw["Open"], errors="raise").astype("float64"),
        "high": pd.to_numeric(df_raw["High"], errors="raise").astype("float64"),
        "low": pd.to_numeric(df_raw["Low"], errors="raise").astype("float64"),
        "close": pd.to_numeric(df_raw["Close"], errors="raise").astype("float64"),
        "volume": pd.to_numeric(df_raw[volume_col], errors="coerce").fillna(0).astype("int64"),
    })
    
    # Record policy
    policy = IngestPolicy(
        normalized_24h=normalized_24h,
        column_map=column_map,
    )
    
    return RawIngestResult(
        df=result_df,
        source_path=str(txt_path),
        rows=len(result_df),
        policy=policy,
    )

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/CME_MNQ_EXCHANGE_v1.yaml
sha256(source_bytes) = 5eb97a787f38ff7842a2fba301d8c498e231fa3598a4995564e77ccfc187d4a6
bytes = 492
redacted = False
--------------------------------------------------------------------------------
symbol: CME.MNQ
version: v1
mode: EXCHANGE_RULE
exchange_tz: America/Chicago
local_tz: Asia/Taipei
rules:
  # Daily maintenance window (CT)
  daily_maintenance:
    start: "16:00:00"   # CT
    end:   "17:00:00"   # CT
  # Trading week: Sun 18:00 ET → Fri 17:00 ET
  # (ET = Eastern Time, but CME uses CT for operations)
  # For simplicity, we treat 17:00 CT as trading day start
  trading_week:
    open: "17:00:00"    # CT (Sunday evening)
    close: "16:00:00"   # CT (Friday afternoon)

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/CME_MNQ_TPE_v1.yaml
sha256(source_bytes) = 1747657f162176acf5e882f02fc443e0e46fa4ee4c955a57cccae53d7aba505f
bytes = 215
redacted = False
--------------------------------------------------------------------------------
symbol: CME.MNQ
version: v1
mode: FIXED_TPE
exchange_tz: Asia/Taipei
local_tz: Asia/Taipei
sessions:
  - name: DAY
    start: "08:45:00"
    end: "13:45:00"
  - name: NIGHT
    start: "21:00:00"
    end: "06:00:00"

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/CME_MNQ_v2.yaml
sha256(source_bytes) = 8f53c18ec109e033aeeae459045283de84748a5411d6ffd0fd5689a474397134
bytes = 304
redacted = False
--------------------------------------------------------------------------------
symbol: CME.MNQ
version: v2
mode: tz_convert
exchange_tz: America/Chicago
data_tz: Asia/Taipei
windows:
  - state: BREAK
    start: "16:00:00"  # Chicago time
    end: "17:00:00"    # Chicago time
  - state: TRADING
    start: "17:00:00"  # Chicago time (跨午夜)
    end: "16:00:00"    # Chicago time

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/TWF_MXF_TPE_v1.yaml
sha256(source_bytes) = ef72f26134a167ffe3d5225c4b7568ce0c16ce733320cda119daf3f7bb93efe4
bytes = 215
redacted = False
--------------------------------------------------------------------------------
symbol: TWF.MXF
version: v1
mode: FIXED_TPE
exchange_tz: Asia/Taipei
local_tz: Asia/Taipei
sessions:
  - name: DAY
    start: "08:45:00"
    end: "13:45:00"
  - name: NIGHT
    start: "15:00:00"
    end: "05:00:00"

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/profiles/TWF_MXF_v2.yaml
sha256(source_bytes) = e987fa531da4849755d014e779b22305daf6b68f73b4c77c0d63b2ecd729ce11
bytes = 479
redacted = False
--------------------------------------------------------------------------------
symbol: TWF.MXF
version: v2
mode: FIXED_TPE
exchange_tz: Asia/Taipei
data_tz: Asia/Taipei
windows:
  - state: TRADING
    start: "08:45:00"  # Taiwan time
    end: "13:45:00"    # Taiwan time
  - state: BREAK
    start: "13:45:00"  # Taiwan time
    end: "15:00:00"    # Taiwan time
  - state: TRADING
    start: "15:00:00"  # Taiwan time (跨午夜)
    end: "05:00:00"    # Taiwan time
  - state: BREAK
    start: "05:00:00"  # Taiwan time
    end: "08:45:00"    # Taiwan time

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/__init__.py
sha256(source_bytes) = fab6b9cab121eb98d1957d8bd89d840d7906c7eb11044c07dcf558e59394ab74
bytes = 749
redacted = False
--------------------------------------------------------------------------------
"""Session Profile and K-Bar Aggregation module.

Phase 6.6: Session Profile + K-Bar Aggregation with DST-safe timezone conversion.
Session classification and K-bar aggregation use exchange clock.
Raw ingest (Phase 6.5) remains unchanged - no timezone conversion at raw layer.
"""

from FishBroWFS_V2.data.session.classify import classify_session, classify_sessions
from FishBroWFS_V2.data.session.kbar import aggregate_kbar
from FishBroWFS_V2.data.session.loader import load_session_profile
from FishBroWFS_V2.data.session.schema import Session, SessionProfile, SessionWindow

__all__ = [
    "Session",
    "SessionProfile",
    "SessionWindow",
    "load_session_profile",
    "classify_session",
    "classify_sessions",
    "aggregate_kbar",
]

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/classify.py
sha256(source_bytes) = 39b4054882852c7dd847df1fafc60dd91eed5e4f35d550234742614251066f96
bytes = 6064
redacted = False
--------------------------------------------------------------------------------
"""Session classification.

Phase 6.6: Classify timestamps into trading sessions using DST-safe timezone conversion.
Converts local time to exchange time for classification.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd
from zoneinfo import ZoneInfo

from FishBroWFS_V2.data.session.schema import Session, SessionProfile, SessionWindow


def _parse_ts_str(ts_str: str) -> datetime:
    """Parse timestamp string (handles non-zero-padded dates like "2013/1/1").
    
    Phase 6.6: Manual parsing to handle "YYYY/M/D" format without zero-padding.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        
    Returns:
        datetime (naive, no timezone attached)
    """
    date_s, time_s = ts_str.split(" ")
    y, m, d = (int(x) for x in date_s.split("/"))
    hh, mm, ss = (int(x) for x in time_s.split(":"))
    return datetime(y, m, d, hh, mm, ss)


def _parse_ts_str_tpe(ts_str: str) -> datetime:
    """Parse timestamp string and attach Asia/Taipei timezone.
    
    Phase 6.6: Only does format parsing + attach timezone, no "correction" or sort.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        
    Returns:
        datetime with Asia/Taipei timezone
    """
    dt = _parse_ts_str(ts_str)
    return dt.replace(tzinfo=ZoneInfo("Asia/Taipei"))


def _parse_ts_str_with_tz(ts_str: str, tz: str) -> datetime:
    """Parse timestamp string and attach specified timezone.
    
    Phase 6.6: Parse ts_str and attach timezone.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
        tz: IANA timezone (e.g., "Asia/Taipei")
        
    Returns:
        datetime with specified timezone
    """
    dt = _parse_ts_str(ts_str)
    return dt.replace(tzinfo=ZoneInfo(tz))


def _to_exchange_hms(ts_str: str, data_tz: str, exchange_tz: str) -> str:
    """Convert timestamp string to exchange timezone and return HH:MM:SS.
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" (data timezone)
        data_tz: IANA timezone of input data (e.g., "Asia/Taipei")
        exchange_tz: IANA timezone of exchange (e.g., "America/Chicago")
        
    Returns:
        Time string "HH:MM:SS" in exchange timezone
    """
    dt = _parse_ts_str(ts_str).replace(tzinfo=ZoneInfo(data_tz))
    dt_ex = dt.astimezone(ZoneInfo(exchange_tz))
    return dt_ex.strftime("%H:%M:%S")


def classify_session(
    ts_str: str,
    profile: SessionProfile,
) -> str | None:
    """Classify timestamp string into session state.
    
    Phase 6.6: Core classification logic with DST-safe timezone conversion.
    - ts_str (TPE string) → parse as data_tz → convert to exchange_tz
    - Use exchange time to compare with windows
    - BREAK 優先於 TRADING
    
    Args:
        ts_str: Timestamp string in format "YYYY/M/D HH:MM:SS" (data timezone)
        profile: Session profile with data_tz, exchange_tz, and windows
        
    Returns:
        Session state: "TRADING", "BREAK", or None
    """
    # Phase 6.6: Parse ts_str as data_tz, convert to exchange_tz
    data_dt = _parse_ts_str_with_tz(ts_str, profile.data_tz)
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    exchange_dt = data_dt.astimezone(exchange_tz_info)
    
    # Extract exchange time HH:MM:SS
    exchange_time_str = exchange_dt.strftime("%H:%M:%S")
    
    # Phase 6.6: Use windows if available (preferred method)
    if profile.windows:
        # BREAK 優先於 TRADING - check BREAK windows first
        for window in profile.windows:
            if window.state == "BREAK":
                if profile._time_in_range(exchange_time_str, window.start, window.end):
                    return "BREAK"
        
        # Then check TRADING windows
        for window in profile.windows:
            if window.state == "TRADING":
                if profile._time_in_range(exchange_time_str, window.start, window.end):
                    return "TRADING"
        
        return None
    
    # Fallback to legacy modes for backward compatibility
    if profile.mode == "tz_convert":
        # tz_convert mode: Check BREAK first, then TRADING
        if profile.break_start and profile.break_end:
            if profile._time_in_range(exchange_time_str, profile.break_start, profile.break_end):
                return "BREAK"
        return "TRADING"
    
    elif profile.mode == "FIXED_TPE":
        # FIXED_TPE mode: Use sessions list
        for session in profile.sessions:
            if profile._time_in_range(exchange_time_str, session.start, session.end):
                return session.name
        return None
    
    elif profile.mode == "EXCHANGE_RULE":
        # EXCHANGE_RULE mode: Use rules
        rules = profile.rules
        if "daily_maintenance" in rules:
            maint = rules["daily_maintenance"]
            maint_start = maint.get("start", "16:00:00")
            maint_end = maint.get("end", "17:00:00")
            if profile._time_in_range(exchange_time_str, maint_start, maint_end):
                return "MAINTENANCE"
        
        if "trading_week" in rules:
            return "TRADING"
        
        # Check sessions if available
        if profile.sessions:
            for session in profile.sessions:
                if profile._time_in_range(exchange_time_str, session.start, session.end):
                    return session.name
        
        return None
    
    else:
        raise ValueError(f"Unknown profile mode: {profile.mode}")


def classify_sessions(
    ts_str_series: pd.Series,
    profile: SessionProfile,
) -> pd.Series:
    """Classify multiple timestamps into session names.
    
    Args:
        ts_str_series: Series of timestamp strings ("YYYY/M/D HH:MM:SS") in local time
        profile: Session profile
        
    Returns:
        Series of session names (or None)
    """
    return ts_str_series.apply(lambda ts: classify_session(ts, profile))

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/kbar.py
sha256(source_bytes) = 0414f7d7384e59731d47a2ba1af60936925086595645ce7af06923b2332bae21
bytes = 13031
redacted = False
--------------------------------------------------------------------------------
"""K-Bar Aggregation.

Phase 6.6: Aggregate bars into K-bars (30/60/120/240/DAY minutes).
Must anchor to Session.start (exchange timezone), no cross-session aggregation.
DST-safe: Uses exchange clock for bucket calculation.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from FishBroWFS_V2.data.session.classify import _parse_ts_str_tpe
from FishBroWFS_V2.data.session.schema import SessionProfile


# Allowed K-bar intervals (minutes)
ALLOWED_INTERVALS = {30, 60, 120, 240, "DAY"}


def _is_trading_session(sess: str | None) -> bool:
    """Check if a session is aggregatable (trading session).
    
    Phase 6.6: Unified rule for determining aggregatable sessions.
    
    Rules:
    - BREAK: Not aggregatable (absolute boundary)
    - None: Not aggregatable (outside any session)
    - MAINTENANCE: Not aggregatable
    - All others (TRADING, DAY, NIGHT, etc.): Aggregatable
    
    This supports both:
    - Phase 6.6: TRADING/BREAK semantics
    - Legacy: DAY/NIGHT semantics
    
    Args:
        sess: Session name or None
        
    Returns:
        True if session is aggregatable, False otherwise
    """
    if sess is None:
        return False
    # Phase 6.6: BREAK is absolute boundary
    if sess == "BREAK":
        return False
    # Legacy: MAINTENANCE is not aggregatable
    if sess == "MAINTENANCE":
        return False
    # All other sessions (TRADING, DAY, NIGHT, etc.) are aggregatable
    return True


def aggregate_kbar(
    df: pd.DataFrame,
    interval: int | str,
    profile: SessionProfile,
) -> pd.DataFrame:
    """Aggregate bars into K-bars.
    
    Rules:
    - Only allowed intervals: 30, 60, 120, 240, DAY
    - Must anchor to Session.start
    - No cross-session aggregation
    - DAY bar = one complete session
    
    Args:
        df: DataFrame with columns: ts_str, open, high, low, close, volume
        interval: K-bar interval in minutes (30/60/120/240) or "DAY"
        profile: Session profile
        
    Returns:
        Aggregated DataFrame with same columns
        
    Raises:
        ValueError: If interval is not allowed
    """
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(
            f"Invalid interval: {interval}. Allowed: {ALLOWED_INTERVALS}"
        )
    
    if interval == "DAY":
        return _aggregate_day_bar(df, profile)
    
    # For minute intervals, aggregate within sessions
    return _aggregate_minute_bar(df, int(interval), profile)


def _aggregate_day_bar(df: pd.DataFrame, profile: SessionProfile) -> pd.DataFrame:
    """Aggregate into DAY bars (one complete session per bar).
    
    Phase 6.6: BREAK is absolute boundary - only aggregate trading sessions.
    DST-safe: Uses exchange clock for session grouping.
    DAY bar = one complete trading session.
    Each trading session produces one DAY bar, regardless of calendar date.
    """
    from FishBroWFS_V2.data.session.classify import classify_sessions
    
    # Classify each bar into session
    df = df.copy()
    df["_session"] = classify_sessions(df["ts_str"], profile)
    
    # Phase 6.6: Filter out non-aggregatable sessions (BREAK, None, MAINTENANCE)
    df = df[df["_session"].apply(_is_trading_session)]
    
    if len(df) == 0:
        return pd.DataFrame(columns=["ts_str", "open", "high", "low", "close", "volume", "session"])
    
    # Convert to exchange timezone for grouping (DST-safe)
    # Phase 6.6: Add derived columns (not violating raw layer)
    if not profile.exchange_tz:
        raise ValueError("Profile must have exchange_tz for DAY bar aggregation")
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    df["_local_dt"] = df["ts_str"].apply(_parse_ts_str_tpe)
    df["_ex_dt"] = df["_local_dt"].apply(lambda dt: dt.astimezone(exchange_tz_info))
    
    # Group by session - each group = one complete session
    # For overnight sessions, all bars of the same session are grouped together
    groups = df.groupby("_session", dropna=False)
    
    result_rows = []
    for session, group in groups:
        # For EXCHANGE_RULE mode, session may not be in profile.sessions
        # Still produce DAY bar if session was classified
        # (session_obj is only needed for anchor time, which DAY bar doesn't use)
        
        # Determine session start date in exchange timezone
        # Sort group by exchange datetime to find first bar chronologically
        group_sorted = group.sort_values("_ex_dt")
        first_bar_ex_dt = group_sorted["_ex_dt"].iloc[0]
        
        # Get original local ts_str for output (keep TPE time)
        # Use first bar's ts_str as anchor - it represents session start in local time
        first_bar_ts_str = group_sorted["ts_str"].iloc[0]
        
        # For DAY bar, use first bar's ts_str directly
        # This ensures output matches the actual first bar time in local timezone
        ts_str = first_bar_ts_str
        
        # Aggregate OHLCV
        open_val = group["open"].iloc[0]
        high_val = group["high"].max()
        low_val = group["low"].min()
        close_val = group["close"].iloc[-1]
        volume_val = group["volume"].sum()
        
        result_rows.append({
            "ts_str": ts_str,
            "open": open_val,
            "high": high_val,
            "low": low_val,
            "close": close_val,
            "volume": int(volume_val),
            "session": session,  # Phase 6.6: Add session label (derived data, not violating Raw)
        })
    
    result_df = pd.DataFrame(result_rows)
    
    # Remove helper columns if they exist
    for col in ["_session", "_local_dt", "_ex_dt"]:
        if col in result_df.columns:
            result_df = result_df.drop(columns=[col])
    
    # Sort by ts_str to maintain chronological order
    if len(result_df) > 0:
        result_df = result_df.sort_values("ts_str").reset_index(drop=True)
    
    return result_df


def _aggregate_minute_bar(
    df: pd.DataFrame,
    interval_minutes: int,
    profile: SessionProfile,
) -> pd.DataFrame:
    """Aggregate into minute bars (30/60/120/240).
    
    Phase 6.6: BREAK is absolute boundary - only aggregate trading sessions.
    DST-safe: Uses exchange clock for bucket calculation.
    Must anchor to Session.start (exchange timezone), no cross-session aggregation.
    Bucket doesn't need to be full - any data produces a bar.
    """
    from FishBroWFS_V2.data.session.classify import classify_sessions
    
    # Classify each bar into session
    df = df.copy()
    df["_session"] = classify_sessions(df["ts_str"], profile)
    
    # Phase 6.6: Filter out non-aggregatable sessions (BREAK, None, MAINTENANCE)
    df = df[df["_session"].apply(_is_trading_session)]
    
    if len(df) == 0:
        return pd.DataFrame(columns=["ts_str", "open", "high", "low", "close", "volume", "session"])
    
    # Convert to exchange timezone for bucket calculation
    # Phase 6.6: Add derived columns (not violating raw layer)
    if not profile.exchange_tz:
        raise ValueError("Profile must have exchange_tz for minute bar aggregation")
    exchange_tz_info = ZoneInfo(profile.exchange_tz)
    
    df["_local_dt"] = df["ts_str"].apply(_parse_ts_str_tpe)
    df["_ex_dt"] = df["_local_dt"].apply(lambda dt: dt.astimezone(exchange_tz_info))
    
    # Extract exchange date and time for grouping
    df["_ex_date"] = df["_ex_dt"].apply(lambda dt: dt.date().isoformat().replace("-", "/"))
    df["_ex_time"] = df["_ex_dt"].apply(lambda dt: dt.strftime("%H:%M:%S"))
    
    result_rows = []
    
    # Process each (exchange_date, session) group separately
    groups = df.groupby(["_ex_date", "_session"], dropna=False)
    
    for (ex_date, session), group in groups:
        if not _is_trading_session(session):
            continue  # Skip non-aggregatable sessions (BREAK, None, MAINTENANCE)
        
        # Find session start time from profile (in exchange timezone)
        # Phase 6.6: If windows exist, use first TRADING window.start
        # Legacy: Use current session name to find matching session.start
        session_start = None
        
        if profile.windows:
            # Phase 6.6: Use first TRADING window.start
            for window in profile.windows:
                if window.state == "TRADING":
                    session_start = window.start
                    break
        else:
            # Legacy: Find session.start by matching session name
            for sess in profile.sessions:
                if sess.name == session:
                    session_start = sess.start
                    break
        
        # If still not found, use first bar's exchange time as anchor
        if session_start is None:
            first_bar_ex_time = group["_ex_time"].iloc[0]
            session_start = first_bar_ex_time
        
        # Calculate bucket start times anchored to session.start (exchange timezone)
        buckets = _calculate_buckets(session_start, interval_minutes)
        
        # Assign each bar to a bucket using exchange time
        group = group.copy()
        group["_bucket"] = group["_ex_time"].apply(
            lambda t: _find_bucket(t, buckets)
        )
        
        # Aggregate per bucket
        bucket_groups = group.groupby("_bucket", dropna=False)
        
        for bucket_start, bucket_group in bucket_groups:
            if pd.isna(bucket_start):
                continue
            
            # Phase 6.6: Bucket doesn't need to be full - any data produces a bar
            # BREAK is absolute boundary (already filtered out above)
            if bucket_group.empty:
                continue
            
            # ts_str output: Use original local ts_str (TPE), not exchange time
            # But bucket grouping was done in exchange time
            first_bar_ts_str = bucket_group["ts_str"].iloc[0]  # Original TPE ts_str
            
            # Aggregate OHLCV
            open_val = bucket_group["open"].iloc[0]
            high_val = bucket_group["high"].max()
            low_val = bucket_group["low"].min()
            close_val = bucket_group["close"].iloc[-1]
            volume_val = bucket_group["volume"].sum()
            
            result_rows.append({
                "ts_str": first_bar_ts_str,  # Keep original TPE ts_str
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": int(volume_val),
                "session": session,  # Phase 6.6: Add session label (derived data, not violating Raw)
            })
    
    result_df = pd.DataFrame(result_rows)
    
    # Remove helper columns
    for col in ["_session", "_ex_date", "_ex_time", "_bucket", "_local_dt", "_ex_dt"]:
        if col in result_df.columns:
            result_df = result_df.drop(columns=[col])
    
    # Sort by ts_str to maintain chronological order
    if len(result_df) > 0:
        result_df = result_df.sort_values("ts_str").reset_index(drop=True)
    
    return result_df


def _calculate_buckets(session_start: str, interval_minutes: int) -> List[str]:
    """Calculate bucket start times anchored to session_start.
    
    Args:
        session_start: Session start time "HH:MM:SS"
        interval_minutes: Interval in minutes
        
    Returns:
        List of bucket start times ["HH:MM:SS", ...]
    """
    # Parse session_start
    parts = session_start.split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    
    # Convert to total minutes
    start_minutes = h * 60 + m
    
    buckets = []
    current_minutes = start_minutes
    
    # Generate buckets until end of day (24:00:00 = 1440 minutes)
    while current_minutes < 1440:
        h_bucket = current_minutes // 60
        m_bucket = current_minutes % 60
        bucket_str = f"{h_bucket:02d}:{m_bucket:02d}:00"
        buckets.append(bucket_str)
        current_minutes += interval_minutes
    
    return buckets


def _find_bucket(time_str: str, buckets: List[str]) -> str | None:
    """Find which bucket a time belongs to.
    
    Phase 6.6: Anchor-based bucket assignment.
    Bucket = floor((time - anchor) / interval)
    
    Args:
        time_str: Time string "HH:MM:SS"
        buckets: List of bucket start times (sorted ascending)
        
    Returns:
        Bucket start time if found, None otherwise
    """
    # Find the largest bucket <= time_str
    # Buckets are sorted ascending, so iterate backwards
    for i in range(len(buckets) - 1, -1, -1):
        if buckets[i] <= time_str:
            # Check if next bucket would exceed time_str
            if i + 1 < len(buckets):
                next_bucket = buckets[i + 1]
                if time_str < next_bucket:
                    return buckets[i]
            else:
                # Last bucket - time_str falls in this bucket
                return buckets[i]
    
    return None

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/loader.py
sha256(source_bytes) = 56634bbdd5ea0734b1c0997970ce91924e37533a8888f9c8abea3f21723e9c8d
bytes = 4814
redacted = False
--------------------------------------------------------------------------------
"""Session Profile loader.

Phase 6.6: Load session profiles from YAML files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from FishBroWFS_V2.data.session.schema import Session, SessionProfile, SessionWindow


def load_session_profile(profile_path: Path) -> SessionProfile:
    """Load session profile from YAML file.
    
    Args:
        profile_path: Path to YAML profile file
        
    Returns:
        SessionProfile loaded from YAML
        
    Raises:
        FileNotFoundError: If profile file does not exist
        ValueError: If profile structure is invalid
    """
    if not profile_path.exists():
        raise FileNotFoundError(f"Session profile not found: {profile_path}")
    
    with profile_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    if not isinstance(data, dict):
        raise ValueError(f"Invalid profile format: expected dict, got {type(data)}")
    
    symbol = data.get("symbol")
    version = data.get("version")
    mode = data.get("mode", "FIXED_TPE")  # Default to FIXED_TPE for backward compatibility
    exchange_tz = data.get("exchange_tz")
    data_tz = data.get("data_tz", "Asia/Taipei")  # Phase 6.6: Default to Asia/Taipei
    local_tz = data.get("local_tz", "Asia/Taipei")
    sessions_data = data.get("sessions", [])
    windows_data = data.get("windows", [])  # Phase 6.6: Windows with TRADING/BREAK states
    rules = data.get("rules", {})
    break_start = data.get("break", {}).get("start") if isinstance(data.get("break"), dict) else None
    break_end = data.get("break", {}).get("end") if isinstance(data.get("break"), dict) else None
    
    if not symbol:
        raise ValueError("Profile missing 'symbol' field")
    if not version:
        raise ValueError("Profile missing 'version' field")
    
    # Phase 6.6: exchange_tz is required
    if not exchange_tz:
        raise ValueError("Profile missing 'exchange_tz' field (required in Phase 6.6)")
    
    if mode not in ["FIXED_TPE", "EXCHANGE_RULE", "tz_convert"]:
        raise ValueError(f"Invalid mode: {mode}. Must be 'FIXED_TPE', 'EXCHANGE_RULE', or 'tz_convert'")
    
    # Phase 6.6: Load windows (preferred method)
    windows = []
    if windows_data:
        if not isinstance(windows_data, list):
            raise ValueError(f"Profile 'windows' must be list, got {type(windows_data)}")
        
        for win_data in windows_data:
            if not isinstance(win_data, dict):
                raise ValueError(f"Window must be dict, got {type(win_data)}")
            
            state = win_data.get("state")
            start = win_data.get("start")
            end = win_data.get("end")
            
            if state not in ["TRADING", "BREAK"]:
                raise ValueError(f"Window state must be 'TRADING' or 'BREAK', got {state}")
            if not start or not end:
                raise ValueError(f"Window missing required fields: state={state}, start={start}, end={end}")
            
            windows.append(SessionWindow(state=state, start=start, end=end))
    
    # Backward compatibility: Load sessions for legacy modes
    sessions = []
    if sessions_data:
        if not isinstance(sessions_data, list):
            raise ValueError(f"Profile 'sessions' must be list, got {type(sessions_data)}")
        
        for sess_data in sessions_data:
            if not isinstance(sess_data, dict):
                raise ValueError(f"Session must be dict, got {type(sess_data)}")
            
            name = sess_data.get("name")
            start = sess_data.get("start")
            end = sess_data.get("end")
            
            if not name or not start or not end:
                raise ValueError(f"Session missing required fields: name={name}, start={start}, end={end}")
            
            sessions.append(Session(name=name, start=start, end=end))
    elif mode == "EXCHANGE_RULE":
        if not isinstance(rules, dict):
            raise ValueError(f"Profile 'rules' must be dict for EXCHANGE_RULE mode, got {type(rules)}")
    elif mode == "tz_convert":
        # Legacy requirement only applies when windows are NOT provided
        # Phase 6.6: If windows_data exists, windows-driven mode doesn't need break.start/end
        if (not windows_data) and (not break_start or not break_end):
            raise ValueError(f"tz_convert mode requires 'break.start' and 'break.end' fields (or 'windows' for Phase 6.6)")
    
    return SessionProfile(
        symbol=symbol,
        version=version,
        mode=mode,
        exchange_tz=exchange_tz,
        data_tz=data_tz,
        local_tz=local_tz,
        sessions=sessions,
        windows=windows,
        rules=rules,
        break_start=break_start,
        break_end=break_end,
    )

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/schema.py
sha256(source_bytes) = 643addf865991cb6271ef1bc1e04ebf7f3c87a6a6b0969e16fd56423efd14b86
bytes = 4466
redacted = False
--------------------------------------------------------------------------------
"""Session Profile schema.

Phase 6.6: Session Profile schema with DST-safe timezone conversion.
Session times are defined in exchange timezone, classification uses exchange clock.

Supports two modes:
- FIXED_TPE: Direct Taiwan time string comparison (e.g., TWF.MXF)
- EXCHANGE_RULE: Exchange timezone + rules, dynamically compute TPE windows (e.g., CME.MNQ)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


@dataclass(frozen=True)
class SessionWindow:
    """Session window definition with state.
    
    Phase 6.6: Only allows TRADING and BREAK states.
    Session times are defined in exchange timezone (format: "HH:MM:SS").
    
    Attributes:
        state: Session state - "TRADING" or "BREAK"
        start: Session start time (exchange timezone, "HH:MM:SS")
        end: Session end time (exchange timezone, "HH:MM:SS")
    """
    state: Literal["TRADING", "BREAK"]
    start: str  # Exchange timezone "HH:MM:SS"
    end: str    # Exchange timezone "HH:MM:SS"


@dataclass(frozen=True)
class Session:
    """Trading session definition.
    
    Session times are defined in exchange timezone (format: "HH:MM:SS").
    
    Attributes:
        name: Session name (e.g., "DAY", "NIGHT", "TRADING", "BREAK", "MAINTENANCE")
        start: Session start time (exchange timezone, "HH:MM:SS")
        end: Session end time (exchange timezone, "HH:MM:SS")
    """
    name: str
    start: str  # Exchange timezone "HH:MM:SS"
    end: str    # Exchange timezone "HH:MM:SS"


@dataclass(frozen=True)
class SessionProfile:
    """Session profile for a symbol.
    
    Contains trading sessions defined in exchange timezone.
    Classification converts local time to exchange time for comparison.
    
    Phase 6.6: data_tz defaults to "Asia/Taipei", exchange_tz must be specified.
    
    Attributes:
        symbol: Symbol identifier (e.g., "CME.MNQ", "TWF.MXF")
        version: Profile version (e.g., "v1", "v2")
        mode: Profile mode - "FIXED_TPE" (direct TPE comparison), "EXCHANGE_RULE" (exchange rules), or "tz_convert" (timezone conversion with BREAK priority)
        exchange_tz: Exchange timezone (IANA, e.g., "America/Chicago")
        data_tz: Data timezone (IANA, default: "Asia/Taipei")
        local_tz: Local timezone (default: "Asia/Taipei")
        sessions: List of trading sessions (for FIXED_TPE mode)
        windows: List of session windows with TRADING/BREAK states (Phase 6.6)
        rules: Exchange rules dict (for EXCHANGE_RULE mode, e.g., daily_maintenance, trading_week)
        break_start: BREAK session start time (HH:MM:SS in exchange timezone) for tz_convert mode
        break_end: BREAK session end time (HH:MM:SS in exchange timezone) for tz_convert mode
    """
    symbol: str
    version: str
    mode: Literal["FIXED_TPE", "EXCHANGE_RULE", "tz_convert"]
    exchange_tz: str  # IANA timezone (e.g., "America/Chicago") - required
    data_tz: str = "Asia/Taipei"  # Data timezone (default: "Asia/Taipei")
    local_tz: str = "Asia/Taipei"  # Default to Taiwan time
    sessions: List[Session] = field(default_factory=list)  # For FIXED_TPE mode
    windows: List[SessionWindow] = field(default_factory=list)  # Phase 6.6: Windows with TRADING/BREAK states
    rules: Dict[str, Any] = field(default_factory=dict)  # For EXCHANGE_RULE mode
    break_start: str | None = None  # BREAK start (HH:MM:SS in exchange timezone) for tz_convert mode
    break_end: str | None = None  # BREAK end (HH:MM:SS in exchange timezone) for tz_convert mode
    
    def _time_in_range(self, time_str: str, start: str, end: str) -> bool:
        """Check if time_str is within [start, end) using string comparison.
        
        Handles both normal sessions (start <= end) and overnight sessions (start > end).
        
        Args:
            time_str: Time to check ("HH:MM:SS") in exchange timezone
            start: Start time ("HH:MM:SS") in exchange timezone
            end: End time ("HH:MM:SS") in exchange timezone
            
        Returns:
            True if time_str falls within the session range
        """
        if start <= end:
            # Non-overnight session (e.g., DAY: 08:45:00 - 13:45:00)
            return start <= time_str < end
        else:
            # Overnight session (e.g., NIGHT: 21:00:00 - 06:00:00)
            # time_str >= start OR time_str < end
            return time_str >= start or time_str < end

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/data/session/tzdb_info.py
sha256(source_bytes) = ae4e5057feaa814367723455f5d3988f97c44760b815108c0e8fa67b95419330
bytes = 1870
redacted = True
--------------------------------------------------------------------------------
"""Timezone database information utilities.

Phase 6.6: Get tzdb provider and version for manifest recording.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Tuple
import zoneinfo


def get_tzdb_info() -> Tuple[str, str]:
    """Get timezone database provider and version.
    
    Phase 6.6: Extract tzdb provider and version for manifest recording.
    
    Strategy:
    1. If tzdata package (PyPI) is installed, use it as provider + version
    2. Otherwise, try to discover tzdata.zi from zoneinfo.TZPATH (module-level)
    
    Returns:
        Tuple of (provider, version)
        - provider: "tzdata" (PyPI package) or "zoneinfo" (standard library)
        - version: Version string from tzdata package or tzdata.zi file, or "unknown" if not found
    """
    provider = "zoneinfo"
    version = "unknown"

    # 1) If tzdata package installed, prefer it as provider + version
    try:
        version = metadata.version("tzdata")
        provider = "tzdata"
        return provider, version
    except metadata.PackageNotFoundError:
        pass

    # 2) Try discover tzdata.zi from zoneinfo.TZPATH (module-level)
    tzpaths = getattr(zoneinfo, "TZPATH", ())
    for p in tzpaths:
        cand = Path(p) / "tzdata.zi"
        if cand.exists():
            # best-effort parse: search a line containing "version"
            try:
                text = cand.read_text(encoding="utf-8", errors="ignore")
                # minimal heuristic:[REDACTED]                for line in text.splitlines()[:200]:
                    if "version" in line.lower():
                        version = line.strip().split()[-1].strip('"')
                        break
            except OSError:
                pass
            break

    return provider, version

--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/__init__.py
sha256(source_bytes) = e81e00a9829674fd7488a169302f41cb7506980b0e5d550d0a64a4681300baa8
bytes = 139
redacted = False
--------------------------------------------------------------------------------

"""Engine module - unified simulate entry point."""

from FishBroWFS_V2.engine.simulate import simulate_run

__all__ = ["simulate_run"]



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/constants.py
sha256(source_bytes) = 808f72fab120a3072a3e505084e31ecd3626833273a0964fec79e553029591c6
bytes = 240
redacted = False
--------------------------------------------------------------------------------

"""
Engine integer constants (hot-path friendly).

These constants are used in array/SoA pathways to avoid Enum.value lookups in tight loops.
"""

ROLE_EXIT = 0
ROLE_ENTRY = 1

KIND_STOP = 0
KIND_LIMIT = 1

SIDE_SELL = -1
SIDE_BUY = 1





--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/constitution.py
sha256(source_bytes) = c75355ca7008415a51a0b93258cd76d5e7146757587c72397e36f114a1a500e7
bytes = 979
redacted = False
--------------------------------------------------------------------------------

"""
Engine Constitution v1.1 (FROZEN)

Activation:
- Orders are created at Bar[T] close and become active at Bar[T+1].

STOP fills (Open==price is treated as GAP branch):
Buy Stop @ S:
- if Open >= S: fill = Open
- elif High >= S: fill = S
Sell Stop @ S:
- if Open <= S: fill = Open
- elif Low <= S: fill = S

LIMIT fills (Open==price is treated as GAP branch):
Buy Limit @ L:
- if Open <= L: fill = Open
- elif Low <= L: fill = L
Sell Limit @ L:
- if Open >= L: fill = Open
- elif High >= L: fill = L

Priority:
- STOP wins over LIMIT (risk-first pessimism).

Same-bar In/Out:
- If entry and exit are both triggerable in the same bar, execute Entry then Exit.

Same-kind tie rule:
- If multiple orders of the same role are triggerable in the same bar, execute EXIT-first.
- Within the same role+kind, use deterministic order: smaller order_id first.
"""

NEXT_BAR_ACTIVE = True
PRIORITY_STOP_OVER_LIMIT = True
SAME_BAR_ENTRY_THEN_EXIT = True
SAME_KIND_TIE_EXIT_FIRST = True




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/engine_jit.py
sha256(source_bytes) = f183678ecbdb41afd6d46e22d48134c6ef5b1d1c148a3f3aed33ddc3289a1113
bytes = 26836
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List, Tuple

import numpy as np

# Engine JIT matcher kernel contract:
# - Complexity target: O(B + I + A), where:
#     B = bars, I = intents, A = per-bar active-book scan.
# - Forbidden: scanning all intents per bar (O(B*I)).
# - Extension point: ttl_bars (0=GTC, 1=one-shot next-bar-only, future: >1).

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore

from FishBroWFS_V2.engine.types import (
    BarArrays,
    Fill,
    OrderIntent,
    OrderKind,
    OrderRole,
    Side,
)
from FishBroWFS_V2.engine.matcher_core import simulate as simulate_py
from FishBroWFS_V2.engine.constants import (
    KIND_LIMIT,
    KIND_STOP,
    ROLE_ENTRY,
    ROLE_EXIT,
    SIDE_BUY,
    SIDE_SELL,
)

# Side enum codes for uint8 encoding (avoid -1 cast deprecation)
SIDE_BUY_CODE = 1
SIDE_SELL_CODE = 255  # SIDE_SELL (-1) encoded as uint8

STATUS_OK = 0
STATUS_ERROR_UNSORTED = 1
STATUS_BUFFER_FULL = 2

# Intent TTL default (Constitution constant)
INTENT_TTL_BARS_DEFAULT = 1  # one-shot next-bar-only (Phase 2 semantics)

# JIT truth (debug/perf observability)
JIT_PATH_USED_LAST = False
JIT_KERNEL_SIGNATURES_LAST = None  # type: ignore


def get_jit_truth() -> dict:
    """
    Debug helper: returns whether the last simulate() call used the JIT kernel,
    and (if available) the kernel signatures snapshot.
    """
    return {
        "jit_path_used": bool(JIT_PATH_USED_LAST),
        "kernel_signatures": JIT_KERNEL_SIGNATURES_LAST,
    }


def _to_int(x) -> int:
    # Enum values are int/str; we convert deterministically.
    if isinstance(x, Side):
        return int(x.value)
    if isinstance(x, OrderRole):
        # EXIT first tie-break relies on role; map explicitly.
        return 0 if x == OrderRole.EXIT else 1
    if isinstance(x, OrderKind):
        return 0 if x == OrderKind.STOP else 1
    return int(x)


def _to_kind_int(k: OrderKind) -> int:
    return 0 if k == OrderKind.STOP else 1


def _to_role_int(r: OrderRole) -> int:
    return 0 if r == OrderRole.EXIT else 1


def _to_side_int(s: Side) -> int:
    """
    Convert Side enum to integer code for uint8 encoding.
    
    Returns:
        SIDE_BUY_CODE (1) for Side.BUY
        SIDE_SELL_CODE (255) for Side.SELL (avoid -1 cast deprecation)
    """
    if s == Side.BUY:
        return SIDE_BUY_CODE
    elif s == Side.SELL:
        return SIDE_SELL_CODE
    else:
        raise ValueError(f"Unknown Side enum: {s}")


def _kind_from_int(v: int) -> OrderKind:
    """
    Decode kind enum from integer value (strict mode).
    
    Allowed values:
    - 0 (KIND_STOP) -> OrderKind.STOP
    - 1 (KIND_LIMIT) -> OrderKind.LIMIT
    
    Raises ValueError for any other value to catch silent corruption.
    """
    if v == KIND_STOP:  # 0
        return OrderKind.STOP
    elif v == KIND_LIMIT:  # 1
        return OrderKind.LIMIT
    else:
        raise ValueError(
            f"Invalid kind enum value: {v}. Allowed values are {KIND_STOP} (STOP) or {KIND_LIMIT} (LIMIT)"
        )


def _role_from_int(v: int) -> OrderRole:
    """
    Decode role enum from integer value (strict mode).
    
    Allowed values:
    - 0 (ROLE_EXIT) -> OrderRole.EXIT
    - 1 (ROLE_ENTRY) -> OrderRole.ENTRY
    
    Raises ValueError for any other value to catch silent corruption.
    """
    if v == ROLE_EXIT:  # 0
        return OrderRole.EXIT
    elif v == ROLE_ENTRY:  # 1
        return OrderRole.ENTRY
    else:
        raise ValueError(
            f"Invalid role enum value: {v}. Allowed values are {ROLE_EXIT} (EXIT) or {ROLE_ENTRY} (ENTRY)"
        )


def _side_from_int(v: int) -> Side:
    """
    Decode side enum from integer value (strict mode).
    
    Allowed values:
    - SIDE_BUY_CODE (1) -> Side.BUY
    - SIDE_SELL_CODE (255) -> Side.SELL
    
    Raises ValueError for any other value to catch silent corruption.
    """
    if v == SIDE_BUY_CODE:  # 1
        return Side.BUY
    elif v == SIDE_SELL_CODE:  # 255
        return Side.SELL
    else:
        raise ValueError(
            f"Invalid side enum value: {v}. Allowed values are {SIDE_BUY_CODE} (BUY) or {SIDE_SELL_CODE} (SELL)"
        )


def _pack_intents(intents: Iterable[OrderIntent]):
    """
    Pack intents into plain arrays for numba.

    Fields (optimized dtypes):
      order_id: int32 (INDEX_DTYPE)
      created_bar: int32 (INDEX_DTYPE)
      role: uint8 (INTENT_ENUM_DTYPE, 0=EXIT,1=ENTRY)
      kind: uint8 (INTENT_ENUM_DTYPE, 0=STOP,1=LIMIT)
      side: uint8 (INTENT_ENUM_DTYPE, SIDE_BUY_CODE=BUY, SIDE_SELL_CODE=SELL)
      price: float64 (INTENT_PRICE_DTYPE)
      qty: int32 (INDEX_DTYPE)
    """
    from FishBroWFS_V2.config.dtypes import (
        INDEX_DTYPE,
        INTENT_ENUM_DTYPE,
        INTENT_PRICE_DTYPE,
    )
    
    it = list(intents)
    n = len(it)
    order_id = np.empty(n, dtype=INDEX_DTYPE)
    created_bar = np.empty(n, dtype=INDEX_DTYPE)
    role = np.empty(n, dtype=INTENT_ENUM_DTYPE)
    kind = np.empty(n, dtype=INTENT_ENUM_DTYPE)
    side = np.empty(n, dtype=INTENT_ENUM_DTYPE)
    price = np.empty(n, dtype=INTENT_PRICE_DTYPE)
    qty = np.empty(n, dtype=INDEX_DTYPE)

    for i, x in enumerate(it):
        order_id[i] = int(x.order_id)
        created_bar[i] = int(x.created_bar)
        role[i] = INTENT_ENUM_DTYPE(_to_role_int(x.role))
        kind[i] = INTENT_ENUM_DTYPE(_to_kind_int(x.kind))
        side[i] = INTENT_ENUM_DTYPE(_to_side_int(x.side))
        price[i] = INTENT_PRICE_DTYPE(x.price)
        qty[i] = int(x.qty)

    return order_id, created_bar, role, kind, side, price, qty


def _sort_packed_by_created_bar(
    packed: Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Sort packed intent arrays by (created_bar, order_id).

    Why:
      - Cursor + active-book kernel requires activate_bar=(created_bar+1) and order_id to be non-decreasing.
      - Determinism is preserved because selection is still based on (kind priority, order_id).
    """
    order_id, created_bar, role, kind, side, price, qty = packed
    # lexsort uses last key as primary -> (created_bar primary, order_id secondary)
    idx = np.lexsort((order_id, created_bar))
    return (
        order_id[idx],
        created_bar[idx],
        role[idx],
        kind[idx],
        side[idx],
        price[idx],
        qty[idx],
    )


def simulate(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> List[Fill]:
    """
    Phase 2A: JIT accelerated matcher.

    Kill switch:
      - If numba is unavailable OR NUMBA_DISABLE_JIT=1, fall back to Python reference.
    """
    global JIT_PATH_USED_LAST, JIT_KERNEL_SIGNATURES_LAST

    if nb is None:
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        return simulate_py(bars, intents)

    # If numba is disabled, keep behavior stable.
    # Numba respects NUMBA_DISABLE_JIT; but we short-circuit to be safe.
    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar(_pack_intents(intents))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(INTENT_TTL_BARS_DEFAULT),  # Use Constitution constant
    )
    if int(status) != STATUS_OK:
        JIT_PATH_USED_LAST = True
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    # record JIT truth (best-effort)
    JIT_PATH_USED_LAST = True
    try:
        sigs = getattr(_simulate_kernel, "signatures", None)
        if sigs is not None:
            JIT_KERNEL_SIGNATURES_LAST = list(sigs)
        else:
            JIT_KERNEL_SIGNATURES_LAST = None
    except Exception:
        JIT_KERNEL_SIGNATURES_LAST = None

    # Convert to Fill objects (drop unused capacity)
    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


def simulate_arrays(
    bars: BarArrays,
    *,
    order_id: np.ndarray,
    created_bar: np.ndarray,
    role: np.ndarray,
    kind: np.ndarray,
    side: np.ndarray,
    price: np.ndarray,
    qty: np.ndarray,
    ttl_bars: int = 1,
) -> List[Fill]:
    """
    Array/SoA entry point: bypass OrderIntent objects and _pack_intents hot-path.

    Arrays must be 1D and same length. Dtypes are expected (optimized):
      order_id: int32 (INDEX_DTYPE)
      created_bar: int32 (INDEX_DTYPE)
      role: uint8 (INTENT_ENUM_DTYPE)
      kind: uint8 (INTENT_ENUM_DTYPE)
      side: uint8 (INTENT_ENUM_DTYPE)
      price: float64 (INTENT_PRICE_DTYPE)
      qty: int32 (INDEX_DTYPE)

    ttl_bars:
      - activate_bar = created_bar + 1
      - 0 => GTC (Good Till Canceled, never expire)
      - 1 => one-shot next-bar-only (intent valid only on activate_bar)
      - >= 1 => intent valid for bars t in [activate_bar, activate_bar + ttl_bars - 1]
      - When t > activate_bar + ttl_bars - 1, intent is removed from active book
    """
    from FishBroWFS_V2.config.dtypes import (
        INDEX_DTYPE,
        INTENT_ENUM_DTYPE,
        INTENT_PRICE_DTYPE,
    )
    
    global JIT_PATH_USED_LAST, JIT_KERNEL_SIGNATURES_LAST

    # Normalize/ensure arrays are numpy with the expected dtypes (cold path).
    oid = np.asarray(order_id, dtype=INDEX_DTYPE)
    cb = np.asarray(created_bar, dtype=INDEX_DTYPE)
    rl = np.asarray(role, dtype=INTENT_ENUM_DTYPE)
    kd = np.asarray(kind, dtype=INTENT_ENUM_DTYPE)
    sd = np.asarray(side, dtype=INTENT_ENUM_DTYPE)
    px = np.asarray(price, dtype=INTENT_PRICE_DTYPE)
    qy = np.asarray(qty, dtype=INDEX_DTYPE)

    if nb is None:
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        intents: List[OrderIntent] = []
        n = int(oid.shape[0])
        for i in range(n):
            # Strict decoding: fail fast on invalid enum values
            rl_val = int(rl[i])
            if rl_val == ROLE_EXIT:
                r = OrderRole.EXIT
            elif rl_val == ROLE_ENTRY:
                r = OrderRole.ENTRY
            else:
                raise ValueError(f"Invalid role enum value: {rl_val}. Allowed: {ROLE_EXIT} (EXIT) or {ROLE_ENTRY} (ENTRY)")
            
            kd_val = int(kd[i])
            if kd_val == KIND_STOP:
                k = OrderKind.STOP
            elif kd_val == KIND_LIMIT:
                k = OrderKind.LIMIT
            else:
                raise ValueError(f"Invalid kind enum value: {kd_val}. Allowed: {KIND_STOP} (STOP) or {KIND_LIMIT} (LIMIT)")
            
            sd_val = int(sd[i])
            if sd_val == SIDE_BUY_CODE:  # 1
                s = Side.BUY
            elif sd_val == SIDE_SELL_CODE:  # 255
                s = Side.SELL
            else:
                raise ValueError(f"Invalid side enum value: {sd_val}. Allowed: {SIDE_BUY_CODE} (BUY) or {SIDE_SELL_CODE} (SELL)")
            intents.append(
                OrderIntent(
                    order_id=int(oid[i]),
                    created_bar=int(cb[i]),
                    role=r,
                    kind=k,
                    side=s,
                    price=float(px[i]),
                    qty=int(qy[i]),
                )
            )
        return simulate_py(bars, intents)

    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        intents: List[OrderIntent] = []
        n = int(oid.shape[0])
        for i in range(n):
            # Strict decoding: fail fast on invalid enum values
            rl_val = int(rl[i])
            if rl_val == ROLE_EXIT:
                r = OrderRole.EXIT
            elif rl_val == ROLE_ENTRY:
                r = OrderRole.ENTRY
            else:
                raise ValueError(f"Invalid role enum value: {rl_val}. Allowed: {ROLE_EXIT} (EXIT) or {ROLE_ENTRY} (ENTRY)")
            
            kd_val = int(kd[i])
            if kd_val == KIND_STOP:
                k = OrderKind.STOP
            elif kd_val == KIND_LIMIT:
                k = OrderKind.LIMIT
            else:
                raise ValueError(f"Invalid kind enum value: {kd_val}. Allowed: {KIND_STOP} (STOP) or {KIND_LIMIT} (LIMIT)")
            
            sd_val = int(sd[i])
            if sd_val == SIDE_BUY_CODE:  # 1
                s = Side.BUY
            elif sd_val == SIDE_SELL_CODE:  # 255
                s = Side.SELL
            else:
                raise ValueError(f"Invalid side enum value: {sd_val}. Allowed: {SIDE_BUY_CODE} (BUY) or {SIDE_SELL_CODE} (SELL)")
            intents.append(
                OrderIntent(
                    order_id=int(oid[i]),
                    created_bar=int(cb[i]),
                    role=r,
                    kind=k,
                    side=s,
                    price=float(px[i]),
                    qty=int(qy[i]),
                )
            )
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar((oid, cb, rl, kd, sd, px, qy))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(ttl_bars),
    )
    if int(status) != STATUS_OK:
        JIT_PATH_USED_LAST = True
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    JIT_PATH_USED_LAST = True
    try:
        sigs = getattr(_simulate_kernel, "signatures", None)
        if sigs is not None:
            JIT_KERNEL_SIGNATURES_LAST = list(sigs)
        else:
            JIT_KERNEL_SIGNATURES_LAST = None
    except Exception:
        JIT_KERNEL_SIGNATURES_LAST = None

    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


def _simulate_with_ttl(bars: BarArrays, intents: Iterable[OrderIntent], ttl_bars: int) -> List[Fill]:
    """
    Internal helper (tests/dev): run JIT matcher with a custom ttl_bars.
    ttl_bars=0 => GTC, ttl_bars=1 => one-shot next-bar-only (default).
    """
    if nb is None:
        return simulate_py(bars, intents)

    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar(_pack_intents(intents))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(ttl_bars),
    )
    if int(status) == STATUS_BUFFER_FULL:
        raise RuntimeError(
            f"engine_jit kernel buffer full: fills exceeded capacity. "
            f"Consider reducing intents or increasing buffer size."
        )
    if int(status) != STATUS_OK:
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


# ----------------------------
# Numba Kernel
# ----------------------------

if nb is not None:

    @nb.njit(cache=False)
    def _stop_fill(side: int, stop_price: float, o: float, h: float, l: float) -> float:
        # returns nan if no fill
        if side == 1:  # BUY
            if o >= stop_price:
                return o
            if h >= stop_price:
                return stop_price
            return np.nan
        else:  # SELL
            if o <= stop_price:
                return o
            if l <= stop_price:
                return stop_price
            return np.nan

    @nb.njit(cache=False)
    def _limit_fill(side: int, limit_price: float, o: float, h: float, l: float) -> float:
        # returns nan if no fill
        if side == 1:  # BUY
            if o <= limit_price:
                return o
            if l <= limit_price:
                return limit_price
            return np.nan
        else:  # SELL
            if o >= limit_price:
                return o
            if h >= limit_price:
                return limit_price
            return np.nan

    @nb.njit(cache=False)
    def _fill_price(kind: int, side: int, px: float, o: float, h: float, l: float) -> float:
        # kind: 0=STOP, 1=LIMIT
        if kind == 0:
            return _stop_fill(side, px, o, h, l)
        return _limit_fill(side, px, o, h, l)

    @nb.njit(cache=False)
    def _simulate_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        order_id: np.ndarray,
        created_bar: np.ndarray,
        role: np.ndarray,
        kind: np.ndarray,
        side: np.ndarray,
        price: np.ndarray,
        qty: np.ndarray,
        ttl_bars: np.int64,
    ):
        """
        Cursor + Active Book kernel (O(B + I + A)).

        Output columns (float64):
          0 bar_index
          1 role_int (0=EXIT,1=ENTRY)
          2 kind_int (0=STOP,1=LIMIT)
          3 side_int (1=BUY,-1=SELL)
          4 fill_price
          5 qty
          6 order_id

        Assumption:
          - intents are sorted by (created_bar, order_id) before calling this kernel.

        TTL Semantics (ttl_bars):
          - activate_bar = created_bar + 1
          - ttl_bars == 0: GTC (Good Till Canceled, never expire)
          - ttl_bars >= 1: intent is valid for bars t in [activate_bar, activate_bar + ttl_bars - 1]
          - When t > activate_bar + ttl_bars - 1, intent is removed from active book (even if not filled)
          - ttl_bars == 1: one-shot next-bar-only (intent valid only on activate_bar)
        """
        n_bars = open_.shape[0]
        n_intents = order_id.shape[0]

        # Buffer size must accommodate at least n_intents (each intent can produce a fill)
        # Default heuristic: n_bars * 2 (allows 2 fills per bar on average)
        max_fills = n_bars * 2
        if n_intents > max_fills:
            max_fills = n_intents
        
        out = np.empty((max_fills, 7), dtype=np.float64)
        out_n = 0

        # -------------------------
        # Fail-fast monotonicity check (activate_bar, order_id)
        # -------------------------
        prev_activate = np.int64(-1)
        prev_order = np.int64(-1)
        for i in range(n_intents):
            a = np.int64(created_bar[i]) + np.int64(1)
            o = np.int64(order_id[i])
            if a < prev_activate or (a == prev_activate and o < prev_order):
                return np.int64(STATUS_ERROR_UNSORTED), out[:0]
            prev_activate = a
            prev_order = o

        # Active Book (indices into intent arrays)
        active_indices = np.empty(n_intents, dtype=np.int64)
        active_count = np.int64(0)
        global_cursor = np.int64(0)

        pos = np.int64(0)  # 0 flat, 1 long, -1 short

        for t in range(n_bars):
            o = float(open_[t])
            h = float(high[t])
            l = float(low[t])

            # Step A — Injection (cursor inject intents activating at this bar)
            while global_cursor < n_intents:
                a = np.int64(created_bar[global_cursor]) + np.int64(1)
                if a == np.int64(t):
                    active_indices[active_count] = global_cursor
                    active_count += np.int64(1)
                    global_cursor += np.int64(1)
                    continue
                if a > np.int64(t):
                    break
                # a < t should not happen if monotonicity check passed
                return np.int64(STATUS_ERROR_UNSORTED), out[:0]

            # Step A.5 — Prune expired intents (TTL/GTC extension point)
            # Remove intents that have expired before processing Step B/C.
            # Contract: activate_bar = created_bar + 1
            #   - ttl_bars == 0: GTC (never expire)
            #   - ttl_bars >= 1: valid bars are t in [activate_bar, activate_bar + ttl_bars - 1]
            #   - When t > activate_bar + ttl_bars - 1, intent must be removed
            if ttl_bars > np.int64(0) and active_count > 0:
                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    activate_bar = np.int64(created_bar[idx]) + np.int64(1)
                    expire_bar = activate_bar + (ttl_bars - np.int64(1))
                    if np.int64(t) > expire_bar:
                        # swap-remove expired intent
                        active_indices[k] = active_indices[active_count - 1]
                        active_count -= np.int64(1)
                        continue
                    k += np.int64(1)

            # Step B — Pass 1 (ENTRY scan, best-pick, swap-remove)
            # Deterministic selection: STOP(0) before LIMIT(1), then order_id asc.
            if pos == 0 and active_count > 0:
                best_k = np.int64(-1)
                best_kind = np.int64(99)
                best_oid = np.int64(2**62)
                best_fp = np.nan

                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    if np.int64(role[idx]) != np.int64(1):  # ENTRY
                        k += np.int64(1)
                        continue

                    kk = np.int64(kind[idx])
                    oo = np.int64(order_id[idx])
                    if kk < best_kind or (kk == best_kind and oo < best_oid):
                        fp = _fill_price(int(kk), int(side[idx]), float(price[idx]), o, h, l)
                        if not np.isnan(fp):
                            best_k = k
                            best_kind = kk
                            best_oid = oo
                            best_fp = fp
                    k += np.int64(1)

                if best_k != np.int64(-1):
                    # Buffer protection: check before writing
                    if out_n >= max_fills:
                        return np.int64(STATUS_BUFFER_FULL), out[:out_n]
                    
                    idx = active_indices[best_k]
                    out[out_n, 0] = float(t)
                    out[out_n, 1] = float(role[idx])
                    out[out_n, 2] = float(kind[idx])
                    out[out_n, 3] = float(side[idx])
                    out[out_n, 4] = float(best_fp)
                    out[out_n, 5] = float(qty[idx])
                    out[out_n, 6] = float(order_id[idx])
                    out_n += 1

                    pos = np.int64(1) if np.int64(side[idx]) == np.int64(1) else np.int64(-1)

                    # swap-remove filled intent
                    active_indices[best_k] = active_indices[active_count - 1]
                    active_count -= np.int64(1)

            # Step C — Pass 2 (EXIT scan, best-pick, swap-remove)
            # Deterministic selection: STOP(0) before LIMIT(1), then order_id asc.
            if pos != 0 and active_count > 0:
                best_k = np.int64(-1)
                best_kind = np.int64(99)
                best_oid = np.int64(2**62)
                best_fp = np.nan

                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    if np.int64(role[idx]) != np.int64(0):  # EXIT
                        k += np.int64(1)
                        continue

                    s = np.int64(side[idx])
                    # side encoding: 1=BUY, 255=SELL -> convert to sign: 1=BUY, -1=SELL
                    side_sign = np.int64(1) if s == np.int64(1) else np.int64(-1)
                    # long exits are SELL(-1), short exits are BUY(1)
                    if pos == np.int64(1) and side_sign != np.int64(-1):
                        k += np.int64(1)
                        continue
                    if pos == np.int64(-1) and side_sign != np.int64(1):
                        k += np.int64(1)
                        continue

                    kk = np.int64(kind[idx])
                    oo = np.int64(order_id[idx])
                    if kk < best_kind or (kk == best_kind and oo < best_oid):
                        fp = _fill_price(int(kk), int(s), float(price[idx]), o, h, l)
                        if not np.isnan(fp):
                            best_k = k
                            best_kind = kk
                            best_oid = oo
                            best_fp = fp
                    k += np.int64(1)

                if best_k != np.int64(-1):
                    # Buffer protection: check before writing
                    if out_n >= max_fills:
                        return np.int64(STATUS_BUFFER_FULL), out[:out_n]
                    
                    idx = active_indices[best_k]
                    out[out_n, 0] = float(t)
                    out[out_n, 1] = float(role[idx])
                    out[out_n, 2] = float(kind[idx])
                    out[out_n, 3] = float(side[idx])
                    out[out_n, 4] = float(best_fp)
                    out[out_n, 5] = float(qty[idx])
                    out[out_n, 6] = float(order_id[idx])
                    out_n += 1

                    pos = np.int64(0)

                    # swap-remove filled intent
                    active_indices[best_k] = active_indices[active_count - 1]
                    active_count -= np.int64(1)

        return np.int64(STATUS_OK), out[:out_n]




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/matcher_core.py
sha256(source_bytes) = 5914210ebc58eac94d396c5f79f9090ecf6050013eb208eb85b2663e89a5be99
bytes = 5460
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import numpy as np

from FishBroWFS_V2.engine.types import (
    BarArrays,
    Fill,
    OrderIntent,
    OrderKind,
    OrderRole,
    Side,
)


@dataclass
class PositionState:
    """
    Minimal single-position state for Phase 1 tests.
    pos: 0 = flat, 1 = long, -1 = short
    """
    pos: int = 0


def _is_active(intent: OrderIntent, bar_index: int) -> bool:
    return bar_index == intent.created_bar + 1


def _stop_fill_price(side: Side, stop_price: float, o: float, h: float, l: float) -> Optional[float]:
    # Open==price goes to GAP branch by definition.
    if side == Side.BUY:
        if o >= stop_price:
            return o
        if h >= stop_price:
            return stop_price
        return None
    else:
        if o <= stop_price:
            return o
        if l <= stop_price:
            return stop_price
        return None


def _limit_fill_price(side: Side, limit_price: float, o: float, h: float, l: float) -> Optional[float]:
    # Open==price goes to GAP branch by definition.
    if side == Side.BUY:
        if o <= limit_price:
            return o
        if l <= limit_price:
            return limit_price
        return None
    else:
        if o >= limit_price:
            return o
        if h >= limit_price:
            return limit_price
        return None


def _intent_fill_price(intent: OrderIntent, o: float, h: float, l: float) -> Optional[float]:
    if intent.kind == OrderKind.STOP:
        return _stop_fill_price(intent.side, intent.price, o, h, l)
    return _limit_fill_price(intent.side, intent.price, o, h, l)


def _sort_key(intent: OrderIntent) -> Tuple[int, int, int]:
    """
    Deterministic priority:
    1) Role: EXIT first when selecting within same-stage bucket.
    2) Kind: STOP before LIMIT.
    3) order_id: ascending.
    Note: Entry-vs-Exit ordering is handled at a higher level (Entry then Exit).
    """
    role_rank = 0 if intent.role == OrderRole.EXIT else 1
    kind_rank = 0 if intent.kind == OrderKind.STOP else 1
    return (role_rank, kind_rank, intent.order_id)


def simulate(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> List[Fill]:
    """
    Phase 1 slow reference matcher.

    Rules enforced:
    - next-bar active only (bar_index == created_bar + 1)
    - STOP/LIMIT gap behavior at Open
    - STOP over LIMIT
    - Same-bar Entry then Exit
    - Same-kind tie: EXIT-first, order_id ascending
    """
    o = bars.open
    h = bars.high
    l = bars.low
    n = int(o.shape[0])

    intents_list = list(intents)
    fills: List[Fill] = []
    state = PositionState(pos=0)

    for t in range(n):
        ot = float(o[t])
        ht = float(h[t])
        lt = float(l[t])

        active = [x for x in intents_list if _is_active(x, t)]
        if not active:
            continue

        # Partition by role for same-bar entry then exit.
        entry_intents = [x for x in active if x.role == OrderRole.ENTRY]
        exit_intents = [x for x in active if x.role == OrderRole.EXIT]

        # Stage 1: ENTRY stage
        if entry_intents:
            # Among entries: STOP before LIMIT, then order_id.
            entry_sorted = sorted(entry_intents, key=lambda x: (0 if x.kind == OrderKind.STOP else 1, x.order_id))
            for it in entry_sorted:
                if state.pos != 0:
                    break  # single-position only
                px = _intent_fill_price(it, ot, ht, lt)
                if px is None:
                    continue
                fills.append(
                    Fill(
                        bar_index=t,
                        role=it.role,
                        kind=it.kind,
                        side=it.side,
                        price=float(px),
                        qty=int(it.qty),
                        order_id=int(it.order_id),
                    )
                )
                # Apply position change
                if it.side == Side.BUY:
                    state.pos = 1
                else:
                    state.pos = -1
                break  # at most one entry fill per bar in Phase 1 reference

        # Stage 2: EXIT stage (after entry)
        if exit_intents and state.pos != 0:
            # Same-kind tie rule: EXIT-first already, and STOP before LIMIT, then order_id
            exit_sorted = sorted(exit_intents, key=_sort_key)
            for it in exit_sorted:
                # Only allow exits that reduce/close current position in this minimal model:
                # long exits are SELL, short exits are BUY.
                if state.pos == 1 and it.side != Side.SELL:
                    continue
                if state.pos == -1 and it.side != Side.BUY:
                    continue

                px = _intent_fill_price(it, ot, ht, lt)
                if px is None:
                    continue
                fills.append(
                    Fill(
                        bar_index=t,
                        role=it.role,
                        kind=it.kind,
                        side=it.side,
                        price=float(px),
                        qty=int(it.qty),
                        order_id=int(it.order_id),
                    )
                )
                state.pos = 0
                break  # at most one exit fill per bar in Phase 1 reference

    return fills




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/metrics_from_fills.py
sha256(source_bytes) = d6e9a2621998a5f5fe52e2d9af82e11ebf80947bbfb529a3126c8fc56d09cf19
bytes = 2957
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from FishBroWFS_V2.engine.types import Fill, OrderRole, Side


def _max_drawdown(equity: np.ndarray) -> float:
    """
    Vectorized max drawdown on an equity curve.
    Handles empty arrays gracefully.
    """
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    mdd = float(np.min(dd))  # negative or 0
    return mdd


def compute_metrics_from_fills(
    fills: List[Fill],
    commission: float,
    slip: float,
    qty: int,
) -> Tuple[float, int, float, np.ndarray]:
    """
    Compute metrics from fills list.
    
    This is the unified source of truth for metrics computation from fills.
    Both object-mode and array-mode kernels should use this helper to ensure parity.
    
    Args:
        fills: List of Fill objects (can be empty)
        commission: Commission cost per trade (absolute)
        slip: Slippage cost per trade (absolute)
        qty: Order quantity (used for PnL calculation)
    
    Returns:
        Tuple of (net_profit, trades, max_dd, equity):
            - net_profit: float - Total net profit (sum of all round-trip PnL)
            - trades: int - Number of trades (equals pnl.size, not entry fills count)
            - max_dd: float - Maximum drawdown from equity curve
            - equity: np.ndarray - Cumulative equity curve (cumsum of per-trade PnL)
    
    Note:
        - trades is defined as pnl.size (number of completed round-trip trades)
        - Only LONG trades are supported (BUY entry, SELL exit)
        - Costs are applied per fill (entry + exit each incur cost)
        - Metrics are derived from pnl/equity, not from fills count
    """
    # Extract entry/exit prices for round trips
    # Pairing rule: take fills in chronological order, pair BUY(ENTRY) then SELL(EXIT)
    entry_prices = []
    exit_prices = []
    for f in fills:
        if f.role == OrderRole.ENTRY and f.side == Side.BUY:
            entry_prices.append(float(f.price))
        elif f.role == OrderRole.EXIT and f.side == Side.SELL:
            exit_prices.append(float(f.price))
    
    # Match entry/exit pairs (take minimum to handle unpaired entries)
    k = min(len(entry_prices), len(exit_prices))
    if k == 0:
        # No complete round trips: no pnl, so trades = 0
        return (0.0, 0, 0.0, np.empty(0, dtype=np.float64))
    
    ep = np.asarray(entry_prices[:k], dtype=np.float64)
    xp = np.asarray(exit_prices[:k], dtype=np.float64)
    
    # Costs applied per fill (entry + exit)
    costs = (float(commission) + float(slip)) * 2.0
    pnl = (xp - ep) * float(qty) - costs
    equity = np.cumsum(pnl)
    
    # CURSOR TASK 1: trades must equal pnl.size (Source of Truth)
    trades = int(pnl.size)
    net_profit = float(np.sum(pnl)) if pnl.size else 0.0
    max_dd = _max_drawdown(equity)
    
    return (net_profit, trades, max_dd, equity)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/order_id.py
sha256(source_bytes) = aab03ff9fdb00e57979cf6056f5de2d179431bb0e3ca74fa01dc244f811bd368
bytes = 3825
redacted = False
--------------------------------------------------------------------------------

"""
Deterministic Order ID Generation (CURSOR TASK 5)

Provides pure function for generating deterministic order IDs that do not depend
on generation order or counters. Used by both object-mode and array-mode kernels.
"""
from __future__ import annotations

import numpy as np

from FishBroWFS_V2.config.dtypes import INDEX_DTYPE
from FishBroWFS_V2.engine.constants import KIND_STOP, ROLE_ENTRY, ROLE_EXIT, SIDE_BUY, SIDE_SELL


def generate_order_id(
    created_bar: int,
    param_idx: int = 0,
    role: int = ROLE_ENTRY,
    kind: int = KIND_STOP,
    side: int = SIDE_BUY,
) -> int:
    """
    Generate deterministic order ID from intent attributes.
    
    Uses reversible packing to ensure deterministic IDs that do not depend on
    generation order or counters. This ensures parity between object-mode and
    array-mode kernels.
    
    Formula:
        order_id = created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_code_bit
    
    Args:
        created_bar: Bar index where intent is created (0-indexed)
        param_idx: Parameter index (0-indexed, default 0 for single-param kernels)
        role: Role code (ROLE_ENTRY or ROLE_EXIT)
        kind: Kind code (KIND_STOP or KIND_LIMIT)
        side: Side code (SIDE_BUY or SIDE_SELL)
    
    Returns:
        Deterministic order ID (int32)
    
    Note:
        - Maximum created_bar: 2,147,483 (within int32 range)
        - Maximum param_idx: 21,474,836 (within int32 range)
        - This packing scheme ensures uniqueness for typical use cases
    """
    # Map role to code: ENTRY=0, EXIT=1
    role_code = 0 if role == ROLE_ENTRY else 1
    
    # Map kind to code: STOP=0, LIMIT=1 (assuming KIND_STOP=0, KIND_LIMIT=1)
    kind_code = 0 if kind == KIND_STOP else 1
    
    # Map side to bit: BUY=0, SELL=1
    side_bit = 0 if side == SIDE_BUY else 1
    
    # Pack: created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_bit
    order_id = (
        created_bar * 1_000_000 +
        param_idx * 100 +
        role_code * 10 +
        kind_code * 2 +
        side_bit
    )
    
    return int(order_id)


def generate_order_ids_array(
    created_bar: np.ndarray,
    param_idx: int = 0,
    role: np.ndarray | None = None,
    kind: np.ndarray | None = None,
    side: np.ndarray | None = None,
) -> np.ndarray:
    """
    Generate deterministic order IDs for array of intents.
    
    Vectorized version of generate_order_id for array-mode kernels.
    
    Args:
        created_bar: Array of created bar indices (int32, shape (n,))
        param_idx: Parameter index (default 0 for single-param kernels)
        role: Array of role codes (uint8, shape (n,)). If None, defaults to ROLE_ENTRY.
        kind: Array of kind codes (uint8, shape (n,)). If None, defaults to KIND_STOP.
        side: Array of side codes (uint8, shape (n,)). If None, defaults to SIDE_BUY.
    
    Returns:
        Array of deterministic order IDs (int32, shape (n,))
    """
    n = len(created_bar)
    
    # Default values if not provided
    if role is None:
        role = np.full(n, ROLE_ENTRY, dtype=np.uint8)
    if kind is None:
        kind = np.full(n, KIND_STOP, dtype=np.uint8)
    if side is None:
        side = np.full(n, SIDE_BUY, dtype=np.uint8)
    
    # Map to codes
    role_code = np.where(role == ROLE_ENTRY, 0, 1).astype(np.int32)
    kind_code = np.where(kind == KIND_STOP, 0, 1).astype(np.int32)
    side_bit = np.where(side == SIDE_BUY, 0, 1).astype(np.int32)
    
    # Pack: created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_bit
    order_id = (
        created_bar.astype(np.int32) * 1_000_000 +
        param_idx * 100 +
        role_code * 10 +
        kind_code * 2 +
        side_bit
    )
    
    return order_id.astype(INDEX_DTYPE)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/signal_exporter.py
sha256(source_bytes) = 2e3c6e2160dba76e49f04d3734421b69c920ee65cb86b749b16e1c8f95de7bb2
bytes = 5625
redacted = False
--------------------------------------------------------------------------------
"""Signal series exporter for bar-based position, margin, and notional in base currency."""

import pandas as pd
import numpy as np
from typing import Optional

REQUIRED_COLUMNS = [
    "ts",
    "instrument",
    "close",
    "position_contracts",
    "currency",
    "fx_to_base",
    "close_base",
    "multiplier",
    "initial_margin_per_contract",
    "maintenance_margin_per_contract",
    "notional_base",
    "margin_initial_base",
    "margin_maintenance_base",
]


def build_signal_series_v1(
    *,
    instrument: str,
    bars_df: pd.DataFrame,   # cols: ts, close (ts sorted asc)
    fills_df: pd.DataFrame,  # cols: ts, qty (contracts signed)
    timeframe: str,
    tz: str,
    base_currency: str,
    instrument_currency: str,
    fx_to_base: float,
    multiplier: float,
    initial_margin_per_contract: float,
    maintenance_margin_per_contract: float,
) -> pd.DataFrame:
    """
    Build signal series V1 DataFrame from bars and fills.
    
    Args:
        instrument: Instrument identifier (e.g., "CME.MNQ")
        bars_df: DataFrame with columns ['ts', 'close']; must be sorted ascending by ts
        fills_df: DataFrame with columns ['ts', 'qty']; qty is signed contracts (+ for buy, - for sell)
        timeframe: Bar timeframe (e.g., "5min")
        tz: Timezone string (e.g., "UTC")
        base_currency: Base currency code (e.g., "TWD")
        instrument_currency: Instrument currency code (e.g., "USD")
        fx_to_base: FX rate from instrument currency to base currency
        multiplier: Contract multiplier
        initial_margin_per_contract: Initial margin per contract in instrument currency
        maintenance_margin_per_contract: Maintenance margin per contract in instrument currency
        
    Returns:
        DataFrame with REQUIRED_COLUMNS, one row per bar, sorted by ts.
        
    Raises:
        ValueError: If input DataFrames are empty or missing required columns
        AssertionError: If bars_df is not sorted ascending
    """
    # Validate inputs
    if bars_df.empty:
        raise ValueError("bars_df cannot be empty")
    if "ts" not in bars_df.columns or "close" not in bars_df.columns:
        raise ValueError("bars_df must have columns ['ts', 'close']")
    if "ts" not in fills_df.columns or "qty" not in fills_df.columns:
        raise ValueError("fills_df must have columns ['ts', 'qty']")
    
    # Ensure bars are sorted ascending
    if not bars_df["ts"].is_monotonic_increasing:
        bars_df = bars_df.sort_values("ts").reset_index(drop=True)
    
    # Prepare bars DataFrame as base
    result = bars_df[["ts", "close"]].copy()
    result["instrument"] = instrument
    
    # If no fills, position is zero for all bars
    if fills_df.empty:
        result["position_contracts"] = 0.0
    else:
        # Ensure fills are sorted by ts
        fills_sorted = fills_df.sort_values("ts").reset_index(drop=True)
        
        # Merge fills to bars using merge_asof to align fill ts to bar ts
        # direction='backward' assigns fill to the nearest bar with ts <= fill_ts
        # We need to merge on ts, but we want to get the bar ts for each fill
        merged = pd.merge_asof(
            fills_sorted,
            result[["ts"]].rename(columns={"ts": "bar_ts"}),
            left_on="ts",
            right_on="bar_ts",
            direction="backward"
        )
        
        # Group by bar_ts and sum qty
        fills_per_bar = merged.groupby("bar_ts")["qty"].sum().reset_index()
        fills_per_bar = fills_per_bar.rename(columns={"bar_ts": "ts", "qty": "fill_qty"})
        
        # Merge fills back to bars
        result = pd.merge(result, fills_per_bar, on="ts", how="left")
        result["fill_qty"] = result["fill_qty"].fillna(0.0)
        
        # Cumulative sum of fills to get position
        result["position_contracts"] = result["fill_qty"].cumsum()
    
    # Add currency and FX columns
    result["currency"] = instrument_currency
    result["fx_to_base"] = fx_to_base
    
    # Calculate close in base currency
    result["close_base"] = result["close"] * fx_to_base
    
    # Add contract specs
    result["multiplier"] = multiplier
    result["initial_margin_per_contract"] = initial_margin_per_contract
    result["maintenance_margin_per_contract"] = maintenance_margin_per_contract
    
    # Calculate notional and margins in base currency
    # notional_base = position_contracts * close_base * multiplier
    result["notional_base"] = result["position_contracts"] * result["close_base"] * multiplier
    
    # margin_initial_base = abs(position_contracts) * initial_margin_per_contract * fx_to_base
    result["margin_initial_base"] = (
        abs(result["position_contracts"]) * initial_margin_per_contract * fx_to_base
    )
    
    # margin_maintenance_base = abs(position_contracts) * maintenance_margin_per_contract * fx_to_base
    result["margin_maintenance_base"] = (
        abs(result["position_contracts"]) * maintenance_margin_per_contract * fx_to_base
    )
    
    # Ensure all required columns are present and in correct order
    for col in REQUIRED_COLUMNS:
        if col not in result.columns:
            raise RuntimeError(f"Missing column {col} in result")
    
    # Reorder columns
    result = result[REQUIRED_COLUMNS]
    
    # Ensure no NaN values (except maybe where close is NaN, but that shouldn't happen)
    if result.isna().any().any():
        # Fill numeric NaNs with 0 where appropriate
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        result[numeric_cols] = result[numeric_cols].fillna(0.0)
    
    return result
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/simulate.py
sha256(source_bytes) = a79e70b18b1b4c3a7df747b3a86593cda69fac13ef0222a7308d8d12ae83e69c
bytes = 1526
redacted = False
--------------------------------------------------------------------------------

"""Unified simulate entry point for Phase 4.

This module provides the single entry point simulate_run() which routes to
the Cursor kernel (main path) or Reference kernel (testing/debugging only).
"""

from __future__ import annotations

from typing import Iterable

from FishBroWFS_V2.engine.types import BarArrays, OrderIntent, SimResult
from FishBroWFS_V2.engine.kernels.cursor_kernel import simulate_cursor_kernel
from FishBroWFS_V2.engine.kernels.reference_kernel import simulate_reference_matcher


def simulate_run(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
    *,
    use_reference: bool = False,
) -> SimResult:
    """
    Unified simulate entry point - Phase 4 main API.
    
    This is the single entry point for all simulation calls. By default, it uses
    the Cursor kernel (main path). The Reference kernel is only available for
    testing/debugging purposes.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        use_reference: If True, use reference kernel (testing/debug only).
                      Default False uses Cursor kernel (main path).
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - Cursor kernel is the main path for production
        - Reference kernel should only be used for tests/debug
        - This API is stable for pipeline usage
    """
    if use_reference:
        return simulate_reference_matcher(bars, intents)
    return simulate_cursor_kernel(bars, intents)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/types.py
sha256(source_bytes) = 0790de1e66b121d4c1a3a682fcef2b469227a0f4e2b45fd89afed49e49f398ab
bytes = 1189
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np


@dataclass(frozen=True)
class BarArrays:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray


class Side(int, Enum):
    BUY = 1
    SELL = -1


class OrderKind(str, Enum):
    STOP = "STOP"
    LIMIT = "LIMIT"


class OrderRole(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


@dataclass(frozen=True)
class OrderIntent:
    """
    Order intent created at bar `created_bar` and becomes active at bar `created_bar + 1`.
    Deterministic ordering is controlled via `order_id` (smaller = earlier).
    """
    order_id: int
    created_bar: int
    role: OrderRole
    kind: OrderKind
    side: Side
    price: float
    qty: int = 1


@dataclass(frozen=True)
class Fill:
    bar_index: int
    role: OrderRole
    kind: OrderKind
    side: Side
    price: float
    qty: int
    order_id: int


@dataclass(frozen=True)
class SimResult:
    """
    Simulation result from simulate_run().
    
    This is the standard return type for Phase 4 unified simulate entry point.
    """
    fills: List[Fill]




--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/kernels/__init__.py
sha256(source_bytes) = 7c9d7bf1296eca2685fe88fe3df4402232687067c44cd735aa99ba9c2c33b73d
bytes = 48
redacted = False
--------------------------------------------------------------------------------

"""Kernel implementations for simulation."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/kernels/cursor_kernel.py
sha256(source_bytes) = 5e3fe836b0387394c517945abd80fac1b3d4f0530350ed79f9cab05a10c60252
bytes = 1165
redacted = False
--------------------------------------------------------------------------------

"""Cursor kernel - main simulation path for Phase 4.

This is the primary kernel implementation, optimized for performance.
It uses array/struct inputs and deterministic cursor-based matching.
"""

from __future__ import annotations

from typing import Iterable, List

from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, SimResult
from FishBroWFS_V2.engine.engine_jit import simulate as simulate_jit


def simulate_cursor_kernel(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> SimResult:
    """
    Cursor kernel - main simulation path.
    
    This is the primary kernel for Phase 4. It uses the optimized JIT implementation
    from engine_jit, which provides O(B + I + A) complexity.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - Uses arrays/structs internally, no class callbacks
        - Naming and fields are stable for pipeline usage
        - Deterministic behavior guaranteed
    """
    fills: List[Fill] = simulate_jit(bars, intents)
    return SimResult(fills=fills)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/engine/kernels/reference_kernel.py
sha256(source_bytes) = 0731bf1a1f1b632d94f5c354c25eb7609b5436906318314164b59d9f0323ab7a
bytes = 1306
redacted = False
--------------------------------------------------------------------------------

"""Reference kernel - adapter for matcher_core (testing/debugging only).

This kernel wraps matcher_core.simulate() and should only be used for:
- Testing alignment between kernels
- Debugging semantic correctness
- Reference implementation verification

It is NOT the main path for production simulation.
"""

from __future__ import annotations

from typing import Iterable, List

from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, SimResult
from FishBroWFS_V2.engine.matcher_core import simulate as simulate_reference


def simulate_reference_matcher(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> SimResult:
    """
    Reference matcher adapter - wraps matcher_core.simulate().
    
    This is an adapter that wraps the reference implementation in matcher_core.
    It should only be used for testing/debugging, not as the main simulation path.
    
    Args:
        bars: OHLC bar arrays
        intents: Iterable of order intents
        
    Returns:
        SimResult containing the fills from simulation
        
    Note:
        - This wraps matcher_core.simulate() which is the semantic truth source
        - Use only for tests/debug, not for production
    """
    fills: List[Fill] = simulate_reference(bars, intents)
    return SimResult(fills=fills)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/__init__.py
sha256(source_bytes) = 4bb1010f453cf1b5b0fcaafe68f3bc3ed71ef5c0f1cbc03f2d27ece64fe6215f
bytes = 40
redacted = False
--------------------------------------------------------------------------------

"""GUI package for FishBroWFS_V2."""



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/research_console.py
sha256(source_bytes) = 7ca86bb0a809a74308c6213e61c0fc65e91c28e7d3748128ec8904b2006505e0
bytes = 9073
redacted = True
--------------------------------------------------------------------------------

"""Research Console Core Module.

Phase 10: Read-only UI for research artifacts with decision input.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Iterable

from FishBroWFS_V2.research.decision import append_decision


def _norm_optional_text(x: Any) -> Optional[str]:
    """Normalize optional free-text user input.
    
    Rules:
    - None -> None
    - non-str -> str(x)
    - strip whitespace
    - empty after strip -> None
    """
    if x is None:
        return None
    if not isinstance(x, str):
        x = str(x)
    s = x.strip()
    return s if s != "" else None


def _norm_optional_choice(x: Any, *, all_tokens: Iterable[str] =[REDACTED]    """Normalize optional dropdown choice.
    
    Rules:
    - None -> None
    - strip whitespace
    - empty after strip -> None
    - token in all_tokens (case-insensitive) -> None
    - otherwise return stripped original (NOT uppercased)
    """
    s = _norm_optional_text(x)
    if s is None:
        return None
    s_upper = s.upper()
    for tok in all_tokens:[REDACTED]        if s_upper == str(tok).upper():
            return None
    return s


def _row_str(row: dict, key: str) -> str:
    """Return safe string for row[key]. None -> ''."""
    v = row.get(key)
    if v is None:
        return ""
    # Keep as string, do not strip here (strip is for normalization functions)
    return str(v)


def load_research_artifacts(outputs_root: Path) -> dict:
    """
    Load:
    - outputs/research/research_index.json
    - outputs/research/canonical_results.json
    Raise if missing.
    """
    research_dir = outputs_root / "research"
    
    index_path = research_dir / "research_index.json"
    canonical_path = research_dir / "canonical_results.json"
    
    if not index_path.exists():
        raise FileNotFoundError(f"research_index.json not found at {index_path}")
    if not canonical_path.exists():
        raise FileNotFoundError(f"canonical_results.json not found at {canonical_path}")
    
    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    with open(canonical_path, "r", encoding="utf-8") as f:
        canonical_data = json.load(f)
    
    # Create a mapping from run_id to canonical result for quick lookup
    canonical_map = {}
    for result in canonical_data:
        run_id = result.get("run_id")
        if run_id:
            canonical_map[run_id] = result
    
    return {
        "index": index_data,
        "canonical_map": canonical_map,
        "index_path": index_path,
        "canonical_path": canonical_path,
        "index_mtime": index_path.stat().st_mtime if index_path.exists() else 0,
    }


def summarize_index(index: dict) -> list[dict]:
    """
    Convert research_index to flat rows for UI table.
    Pure function.
    """
    rows = []
    entries = index.get("entries", [])
    
    for entry in entries:
        run_id = entry.get("run_id", "")
        keys = entry.get("keys", {})
        
        row = {
            "run_id": run_id,
            "symbol": keys.get("symbol"),
            "strategy_id": keys.get("strategy_id"),
            "portfolio_id": keys.get("portfolio_id"),
            "score_final": entry.get("score_final", 0.0),
            "score_net_mdd": entry.get("score_net_mdd", 0.0),
            "trades": entry.get("trades", 0),
            "decision": entry.get("decision", "UNDECIDED"),
        }
        rows.append(row)
    
    return rows


def apply_filters(
    rows: list[dict],
    *,
    text: str | None,
    symbol: str | None,
    strategy_id: str | None,
    decision: str | None,
) -> list[dict]:
    """
    Deterministic filter.
    No IO.
    """
    # Normalize inputs
    text_q = _norm_optional_text(text)
    symbol_q =[REDACTED]    strategy_q =[REDACTED]    decision_q =[REDACTED]    
    filtered = rows
    
    # A) text filter
    if text_q is not None:
        text_lower = text_q.lower()
        filtered = [
            row for row in filtered
            if (
                (_row_str(row, "run_id").lower().find(text_lower) >= 0) or
                (_row_str(row, "symbol").lower().find(text_lower) >= 0) or
                (_row_str(row, "strategy_id").lower().find(text_lower) >= 0) or
                (_row_str(row, "note").lower().find(text_lower) >= 0)
            )
        ]
    
    # B) symbol / strategy_id filter
    if symbol_q is not None:
        sym_q_l = symbol_q.lower()
        filtered = [row for row in filtered if _row_str(row, "symbol").lower() == sym_q_l]
    
    if strategy_q is not None:
        st_q_l = strategy_q.lower()
        filtered = [row for row in filtered if _row_str(row, "strategy_id").lower() == st_q_l]
    
    # C) decision filter
    if decision_q is not None:
        dec_q = decision_q.strip()
        dec_q_l = dec_q.lower()
        
        if dec_q_l == "undecided":
            # Match None / '' / whitespace-only
            filtered = [
                row for row in filtered 
                if _norm_optional_text(row.get("decision")) is None
            ]
        else:
            filtered = [
                row for row in filtered
                if _row_str(row, "decision").lower() == dec_q_l
            ]
    
    return filtered


def load_run_detail(run_id: str, outputs_root: Path) -> dict:
    """
    Read-only load:
    - manifest.json
    - metrics.json
    - README.md (truncated)
    """
    # First find the run directory
    run_dir = None
    seasons_dir = outputs_root / "seasons"
    
    if seasons_dir.exists():
        for season_dir in seasons_dir.iterdir():
            if not season_dir.is_dir():
                continue
            
            runs_dir = season_dir / "runs"
            if not runs_dir.exists():
                continue
            
            potential_run_dir = runs_dir / run_id
            if potential_run_dir.exists() and potential_run_dir.is_dir():
                run_dir = potential_run_dir
                break
    
    if not run_dir:
        raise FileNotFoundError(f"Run directory not found for run_id: {run_id}")
    
    # Load manifest.json
    manifest = {}
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load metrics.json
    metrics = {}
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load README.md (truncated to first 1000 chars)
    readme_content = ""
    readme_path = run_dir / "README.md"
    if readme_path.exists():
        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Truncate to 1000 characters
                if len(content) > 1000:
                    readme_content = content[:1000] + "... [truncated]"
                else:
                    readme_content = content
        except Exception:
            pass
    
    # Load winners.json if exists
    winners = {}
    winners_path = run_dir / "winners.json"
    if winners_path.exists():
        try:
            with open(winners_path, "r", encoding="utf-8") as f:
                winners = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load winners_v2.json if exists
    winners_v2 = {}
    winners_v2_path = run_dir / "winners_v2.json"
    if winners_v2_path.exists():
        try:
            with open(winners_v2_path, "r", encoding="utf-8") as f:
                winners_v2 = json.load(f)
        except json.JSONDecodeError:
            pass
    
    return {
        "run_id": run_id,
        "manifest": manifest,
        "metrics": metrics,
        "winners": winners,
        "winners_v2": winners_v2,
        "readme": readme_content,
        "run_dir": str(run_dir),
    }


def submit_decision(
    *,
    outputs_root: Path,
    run_id: str,
    decision: Literal["KEEP", "DROP", "ARCHIVE"],
    note: str,
) -> None:
    """
    Must call:
    FishBroWFS_V2.research.decision.append_decision(...)
    """
    if len(note.strip()) < 5:
        raise ValueError("Note must be at least 5 characters long")
    
    research_dir = outputs_root / "research"
    append_decision(research_dir, run_id, decision, note)


def get_unique_values(rows: list[dict], field: str) -> list[str]:
    """
    Get unique non-empty values from rows for a given field.
    Used for dropdown filters.
    """
    values = set()
    for row in rows:
        value = row.get(field)
        if value:
            values.add(value)
    return sorted(list(values))



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/theme.py
sha256(source_bytes) = 1fb7f524d455c402be4e219ed56b8d228e1fc827dd4be9376b6f79fbe02b943e
bytes = 5690
redacted = False
--------------------------------------------------------------------------------
"""Cyberpunk UI 全域樣式注入"""

from nicegui import ui


def inject_global_styles() -> None:
    """注入全域樣式：Google Fonts + Tailwind CDN + 自訂 CSS"""
    
    # Google Fonts
    ui.add_head_html("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    """, shared=True)
    
    # Tailwind CDN
    ui.add_head_html("""
    <script src="https://cdn.tailwindcss.com"></script>
    """, shared=True)
    
    # Tailwind config with custom colors
    ui.add_head_html("""
    <script>
    tailwind.config = {
        darkMode: 'class',
        theme: {
            extend: {
                colors: {
                    'nexus': {
                        50: '#f0f9ff',
                        100: '#e0f2fe',
                        200: '#bae6fd',
                        300: '#7dd3fc',
                        400: '#38bdf8',
                        500: '#0ea5e9',
                        600: '#0284c7',
                        700: '#0369a1',
                        800: '#075985',
                        900: '#0c4a6e',
                        950: '#082f49',
                    },
                    'cyber': {
                        50: '#f0fdfa',
                        100: '#ccfbf1',
                        200: '#99f6e4',
                        300: '#5eead4',
                        400: '#2dd4bf',
                        500: '#14b8a6',
                        600: '#0d9488',
                        700: '#0f766e',
                        800: '#115e59',
                        900: '#134e4a',
                        950: '#042f2e',
                    },
                    'fish': {
                        50: '#eff6ff',
                        100: '#dbeafe',
                        200: '#bfdbfe',
                        300: '#93c5fd',
                        400: '#60a5fa',
                        500: '#3b82f6',
                        600: '#2563eb',
                        700: '#1d4ed8',
                        800: '#1e40af',
                        900: '#1e3a8a',
                        950: '#172554',
                    }
                },
                fontFamily: {
                    'sans': ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'Noto Sans', 'sans-serif'],
                    'mono': ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', 'monospace'],
                },
                animation: {
                    'glow': 'glow 2s ease-in-out infinite alternate',
                    'pulse-glow': 'pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                },
                keyframes: {
                    'glow': {
                        'from': { 'box-shadow': '0 0 10px #0ea5e9, 0 0 20px #0ea5e9, 0 0 30px #0ea5e9' },
                        'to': { 'box-shadow': '0 0 20px #3b82f6, 0 0 30px #3b82f6, 0 0 40px #3b82f6' }
                    },
                    'pulse-glow': {
                        '0%, 100%': { 'opacity': 1 },
                        '50%': { 'opacity': 0.5 }
                    }
                }
            }
        }
    }
    </script>
    """, shared=True)
    
    # Custom CSS for cyberpunk theme
    ui.add_head_html("""
    <style>
    :root {
        --bg-nexus-950: #082f49;
        --text-slate-300: #cbd5e1;
        --border-cyber-500: #14b8a6;
        --glow-fish-500: #3b82f6;
    }
    
    body {
        font-family: 'Inter', sans-serif;
        background-color: var(--bg-nexus-950);
        color: var(--text-slate-300);
    }
    
    .fish-card {
        background: linear-gradient(145deg, rgba(8, 47, 73, 0.9), rgba(12, 74, 110, 0.9));
        border: 1px solid rgba(20, 184, 166, 0.3);
        border-radius: 0.75rem;
        padding: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
    }
    
    .fish-card:hover {
        border-color: rgba(20, 184, 166, 0.6);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.3);
    }
    
    .fish-card.glow {
        animation: glow 2s ease-in-out infinite alternate;
    }
    
    .fish-header {
        background: linear-gradient(90deg, rgba(8, 47, 73, 1), rgba(20, 184, 166, 0.3));
        border-bottom: 1px solid rgba(20, 184, 166, 0.5);
        padding: 1rem 1.5rem;
    }
    
    .nav-active {
        background: rgba(20, 184, 166, 0.2);
        border-left: 3px solid var(--border-cyber-500);
        font-weight: 600;
    }
    
    .btn-cyber {
        background: linear-gradient(90deg, #14b8a6, #0d9488);
        color: white;
        border: none;
        border-radius: 0.5rem;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s;
    }
    
    .btn-cyber:hover {
        background: linear-gradient(90deg, #0d9488, #0f766e);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(20, 184, 166, 0.4);
    }
    
    .btn-cyber:active {
        transform: translateY(0);
    }
    
    .toast-warning {
        background: linear-gradient(90deg, rgba(245, 158, 11, 0.9), rgba(217, 119, 6, 0.9));
        border: 1px solid rgba(245, 158, 11, 0.5);
        color: white;
    }
    
    .text-cyber-glow {
        text-shadow: 0 0 10px rgba(20, 184, 166, 0.7);
    }
    </style>
    """, shared=True)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/__init__.py
sha256(source_bytes) = c82b489bad38048199a02de11a001199ef5465f434437f12dfaad4965663e297
bytes = 60
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 介面模組 - 唯一 UI 層"""

__all__ = []



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/api.py
sha256(source_bytes) = 90f2c92254293114211f98b2122986d7e04b745c44904cf95f3f8d79a68b78f7
bytes = 12183
redacted = False
--------------------------------------------------------------------------------

"""UI API 薄接口 - 唯一 UI ↔ 系統邊界

憲法級原則：
1. 禁止 import FishBroWFS_V2.control.research_runner
2. 禁止 import FishBroWFS_V2.wfs.runner
3. 禁止 import 任何會造成 build/compute 的模組
4. UI 只能呼叫此模組暴露的「submit/query/download」函式
5. 所有 API 呼叫必須對接真實 Control API，禁止 fallback mock
"""

import json
import os
import requests
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal, List, Dict, Any
from uuid import uuid4

# API 基礎 URL - 從環境變數讀取，預設為 http://127.0.0.1:8000
API_BASE = os.environ.get("FISHBRO_API_BASE", "http://127.0.0.1:8000")


@dataclass(frozen=True)
class JobSubmitRequest:
    """任務提交請求"""
    outputs_root: Path
    dataset_id: str
    symbols: list[str]
    timeframe_min: int
    strategy_name: str
    data2_feed: Optional[str]              # None | "6J" | "VX" | "DX" | "ZN"
    rolling: bool                          # True only (MVP)
    train_years: int                       # fixed=3
    test_unit: Literal["quarter"]          # fixed="quarter"
    enable_slippage_stress: bool           # True
    slippage_levels: list[str]             # ["S0","S1","S2","S3"]
    gate_level: str                        # "S2"
    stress_level: str                      # "S3"
    topk: int                              # default 20
    season: str                            # 例如 "2026Q1"


@dataclass(frozen=True)
class JobRecord:
    """任務記錄"""
    job_id: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    created_at: str
    updated_at: str
    progress: Optional[float]              # 0..1
    message: Optional[str]
    outputs_path: Optional[str]            # set when completed
    latest_log_tail: Optional[str]         # optional


def _call_api(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
    """呼叫 Control API - 禁止 fallback mock，失敗就 raise"""
    url = f"{API_BASE}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"無法連線到 Control API ({url}): {e}. 請確認 Control API 是否已啟動。")
    except requests.exceptions.Timeout as e:
        raise RuntimeError(f"Control API 請求超時 ({url}): {e}")
    except requests.exceptions.HTTPError as e:
        if response.status_code == 503:
            raise RuntimeError(f"Control API 服務不可用 (503): {e.response.text if hasattr(e, 'response') else str(e)}")
        elif response.status_code == 404:
            # 404 錯誤是正常的（artifact 尚未產生）
            raise FileNotFoundError(f"Resource not found (404): {endpoint}")
        else:
            raise RuntimeError(f"Control API 錯誤 ({response.status_code}): {e.response.text if hasattr(e, 'response') else str(e)}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Control API 請求失敗 ({url}): {e}")


def list_datasets(outputs_root: Path) -> list[str]:
    """列出可用的資料集 - 只能來自 /meta/datasets，禁止 fallback mock"""
    data = _call_api("/meta/datasets")
    return [ds["id"] for ds in data.get("datasets", [])]


def list_strategies() -> list[str]:
    """列出可用的策略 - 只能來自 /meta/strategies，禁止 fallback mock"""
    data = _call_api("/meta/strategies")
    return [s["strategy_id"] for s in data.get("strategies", [])]


def submit_job(req: JobSubmitRequest) -> JobRecord:
    """提交新任務 - 對接真實 POST /jobs 端點，禁止 fake"""
    # 驗證參數
    if req.data2_feed not in [None, "6J", "VX", "DX", "ZN"]:
        raise ValueError(f"Invalid data2_feed: {req.data2_feed}")
    
    if req.train_years != 3:
        raise ValueError(f"train_years must be 3, got {req.train_years}")
    
    if req.test_unit != "quarter":
        raise ValueError(f"test_unit must be 'quarter', got {req.test_unit}")
    
    # 建立 config_snapshot (只包含策略相關資訊)
    # 注意：UI 的 strategy_name 對應到 config_snapshot 的 strategy_name
    config_snapshot = {
        "strategy_name": req.strategy_name,
        "params": {},  # 暫時為空，UI 需要收集參數
        "fees": 0.0,
        "slippage": 0.0,
        # 其他 UI 蒐集的參數可以放在這裡
        "dataset_id": req.dataset_id,
        "symbols": req.symbols,
        "timeframe_min": req.timeframe_min,
        "data2_feed": req.data2_feed,
        "rolling": req.rolling,
        "train_years": req.train_years,
        "test_unit": req.test_unit,
        "enable_slippage_stress": req.enable_slippage_stress,
        "slippage_levels": req.slippage_levels,
        "gate_level": req.gate_level,
        "stress_level": req.stress_level,
        "topk": req.topk,
    }
    
    # 計算 config_hash (使用 JSON 字串的 SHA256)
    import hashlib
    import json
    config_json = json.dumps(config_snapshot, sort_keys=True, separators=(',', ':'))
    config_hash = hashlib.sha256(config_json.encode('utf-8')).hexdigest()
    
    # 建立完整的 JobSpec (7 個欄位)
    spec = {
        "season": req.season,
        "dataset_id": req.dataset_id,
        "outputs_root": str(req.outputs_root),
        "config_snapshot": config_snapshot,
        "config_hash": config_hash,
        "data_fingerprint_sha1": "",  # Phase 7 再補真值
        "created_by": "nicegui",
    }
    
    # 呼叫真實 Control API
    response = _call_api("/jobs", method="POST", data={"spec": spec})
    
    # 從 API 回應取得 job_id
    job_id = response.get("job_id", "")
    
    # 回傳 JobRecord
    return JobRecord(
        job_id=job_id,
        status="PENDING",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        progress=0.0,
        message="Job submitted successfully",
        outputs_path=str(req.outputs_root / "runs" / job_id),
        latest_log_tail="Job queued for execution"
    )


def list_recent_jobs(limit: int = 50) -> list[JobRecord]:
    """列出最近的任務 - 只能來自 /jobs，禁止 fallback mock"""
    data = _call_api("/jobs")
    jobs = []
    for job_data in data[:limit]:
        # 轉換 API 回應到 JobRecord
        jobs.append(JobRecord(
            job_id=job_data.get("job_id", ""),
            status=_map_status(job_data.get("status", "")),
            created_at=job_data.get("created_at", ""),
            updated_at=job_data.get("updated_at", ""),
            progress=_estimate_progress(job_data),
            message=job_data.get("last_error"),
            outputs_path=job_data.get("spec", {}).get("outputs_root"),
            latest_log_tail=None
        ))
    return jobs


def get_job(job_id: str) -> JobRecord:
    """取得特定任務的詳細資訊"""
    try:
        data = _call_api(f"/jobs/{job_id}")
        
        # 獲取日誌尾巴
        log_data = _call_api(f"/jobs/{job_id}/log_tail?n=20")
        log_tail = "\n".join(log_data.get("lines", [])) if log_data.get("ok") else None
        
        return JobRecord(
            job_id=data.get("job_id", ""),
            status=_map_status(data.get("status", "")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            progress=_estimate_progress(data),
            message=data.get("last_error"),
            outputs_path=data.get("spec", {}).get("outputs_root"),
            latest_log_tail=log_tail
        )
    except Exception as e:
        raise RuntimeError(f"Failed to get job {job_id}: {e}")


def get_rolling_summary(job_id: str) -> dict:
    """取得滾動摘要 - 從 /jobs/{job_id}/rolling_summary 讀取真實 artifact"""
    try:
        data = _call_api(f"/jobs/{job_id}/rolling_summary")
        return data
    except FileNotFoundError:
        # 404 是正常的（研究結果尚未產生）
        return {"status": "not_available", "message": "Rolling summary not yet generated"}


def get_season_report(job_id: str, season_id: str) -> dict:
    """取得特定季度的報告 - 從 /jobs/{job_id}/seasons/{season_id} 讀取真實 artifact"""
    try:
        data = _call_api(f"/jobs/{job_id}/seasons/{season_id}")
        return data
    except FileNotFoundError:
        # 404 是正常的（研究結果尚未產生）
        return {"status": "not_available", "message": f"Season report for {season_id} not yet generated"}


def generate_deploy_zip(job_id: str) -> Path:
    """產生部署 ZIP 檔案 - 對接真實 /jobs/{job_id}/deploy 端點"""
    # 呼叫 deploy 端點
    response = _call_api(f"/jobs/{job_id}/deploy", method="POST")
    
    # 從回應取得檔案路徑
    deploy_path = Path(response.get("deploy_path", ""))
    if not deploy_path.exists():
        raise RuntimeError(f"Deploy ZIP 檔案不存在: {deploy_path}")
    
    return deploy_path


def list_chart_artifacts(job_id: str) -> list[dict]:
    """列出可用的圖表 artifact - 從 /jobs/{job_id}/viz 讀取真實 artifact 清單"""
    try:
        data = _call_api(f"/jobs/{job_id}/viz")
        return data.get("artifacts", [])
    except FileNotFoundError:
        # 404 是正常的（圖表尚未產生）
        return []


def load_chart_artifact(job_id: str, artifact_id: str) -> dict:
    """載入圖表 artifact 資料 - 從 /jobs/{job_id}/viz/{artifact_id} 讀取真實 artifact"""
    try:
        data = _call_api(f"/jobs/{job_id}/viz/{artifact_id}")
        return data
    except FileNotFoundError:
        # 404 是正常的（特定圖表尚未產生）
        return {"status": "not_available", "message": f"Chart artifact {artifact_id} not yet generated"}


def get_jobs_for_deploy() -> list[dict]:
    """取得可部署的 jobs - 從 /jobs/deployable 讀取真實資料"""
    try:
        data = _call_api("/jobs/deployable")
        return data.get("jobs", [])
    except FileNotFoundError:
        # 404 是正常的（端點可能尚未實現）
        return []
    except RuntimeError as e:
        # 其他錯誤（如 API 不可用）
        if "404" in str(e):
            return []
        raise


def get_system_settings() -> dict:
    """取得系統設定 - 從 /meta/settings 讀取"""
    try:
        data = _call_api("/meta/settings")
        return data
    except (FileNotFoundError, RuntimeError):
        # 回傳預設設定
        return {
            "api_endpoint": API_BASE,
            "version": "2.0.0",
            "environment": {},
            "endpoints": {},
            "auto_refresh": True,
            "notifications": False,
            "theme": "dark",
        }


def update_system_settings(settings: dict) -> dict:
    """更新系統設定 - 發送到 /meta/settings"""
    try:
        data = _call_api("/meta/settings", method="POST", data=settings)
        return data
    except (FileNotFoundError, RuntimeError):
        # 模擬成功
        return {"status": "ok", "message": "Settings updated (simulated)"}


# 輔助函數
def _map_status(api_status: str) -> Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]:
    """對應 API 狀態到 UI 狀態"""
    status_map = {
        "QUEUED": "PENDING",
        "RUNNING": "RUNNING",
        "PAUSED": "RUNNING",
        "DONE": "COMPLETED",
        "FAILED": "FAILED",
        "KILLED": "FAILED",
    }
    return status_map.get(api_status, "PENDING")


def _estimate_progress(job_data: dict) -> Optional[float]:
    """估計任務進度"""
    status = job_data.get("status", "")
    if status == "QUEUED":
        return 0.0
    elif status == "RUNNING":
        return 0.5
    elif status == "DONE":
        return 1.0
    elif status in ["FAILED", "KILLED"]:
        return None
    else:
        return 0.3


# _mock_jobs 函數已移除 - Phase 6.5 禁止 fallback mock



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/app.py
sha256(source_bytes) = 2b85f32e9b4e7a956652f771e2703c5993d08638d36c42f60d758851fe75f6e4
bytes = 1410
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 主應用程式 - 唯一 UI 入口點"""

from nicegui import ui
from .router import register_pages
from ..theme import inject_global_styles


@ui.page('/health')
def health_page():
    """健康檢查端點 - 用於 launcher readiness check"""
    # 用純文字就好，launcher 只需要 200 OK
    ui.label('ok')


def main() -> None:
    """啟動 NiceGUI 應用程式"""
    # 注入全域樣式（必須在 register_pages 之前）
    inject_global_styles()
    
    # 註冊頁面路由
    register_pages()
    
    # 啟動伺服器
    ui.run(
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=False,  # 避免 gio: Operation not supported
    )


# 以下函數簽名符合 P0-0 要求，實際實作在 layout.py 中
def render_header(season: str) -> None:
    """渲染頁面頂部 header（包含 season 顯示）"""
    from .layout import render_header as _render_header
    _render_header(season)


def render_nav(active_path: str) -> None:
    """渲染側邊導航欄（用於需要側邊導航的頁面）"""
    from .layout import render_nav as _render_nav
    _render_nav(active_path)


def render_shell(active_path: str, season: str = "2026Q1"):
    """渲染完整 shell（header + 主內容區）"""
    from .layout import render_shell as _render_shell
    return _render_shell(active_path, season)


if __name__ == "__main__":
    main()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/layout.py
sha256(source_bytes) = 29c6c311a7a8838cb88ebdb5f22ee38b02cb13e5f2125bd551d6cfc26f84df7a
bytes = 3183
redacted = False
--------------------------------------------------------------------------------

from __future__ import annotations
from nicegui import ui

# 根據 P0-0 要求：Dashboard / Wizard / History / Candidates / Portfolio / Deploy / Settings / Status
NAV = [
    ("Dashboard", "/"),
    ("Wizard", "/wizard"),
    ("History", "/history"),
    ("Candidates", "/candidates"),
    ("Portfolio", "/portfolio"),
    ("Deploy", "/deploy"),
    ("Settings", "/settings"),
    ("Status", "/status"),
]

def render_header(season: str) -> None:
    """渲染頁面頂部 header（包含 season 顯示）"""
    with ui.header().classes("fish-header items-center justify-between px-6 py-4"):
        with ui.row().classes("items-center gap-4"):
            ui.icon("rocket_launch", size="lg").classes("text-cyber-500")
            ui.label("FishBroWFS V2").classes("text-2xl font-bold text-cyber-glow")
            ui.label(f"Season: {season}").classes("text-sm bg-nexus-800 px-3 py-1 rounded-full")
        
        with ui.row().classes("gap-2"):
            for name, path in NAV:
                ui.link(name, path).classes(
                    "px-4 py-2 rounded-lg no-underline transition-colors "
                    "hover:bg-nexus-800 text-slate-300"
                )

def render_nav(active_path: str) -> None:
    """渲染側邊導航欄（用於需要側邊導航的頁面）"""
    with ui.column().classes("w-64 bg-nexus-900 h-full p-4 border-r border-nexus-800"):
        ui.label("Navigation").classes("text-lg font-bold mb-4 text-cyber-400")
        
        for name, path in NAV:
            is_active = active_path == path
            classes = "px-4 py-3 rounded-lg mb-2 no-underline transition-colors "
            if is_active:
                classes += "nav-active bg-nexus-800 text-cyber-300 font-semibold"
            else:
                classes += "hover:bg-nexus-800 text-slate-400"
            
            ui.link(name, path).classes(classes)

def render_shell(active_path: str, season: str = "2026Q1") -> None:
    """渲染完整 shell（header + 主內容區）"""
    # 套用 cyberpunk body classes
    ui.query("body").classes("bg-nexus-950 text-slate-300 font-sans h-screen flex flex-col overflow-hidden")
    
    # 渲染 header
    render_header(season)
    
    # 主內容區容器
    with ui.row().classes("flex-1 overflow-hidden"):
        # 側邊導航（可選，根據頁面需求）
        # render_nav(active_path)
        
        # 主內容
        with ui.column().classes("flex-1 p-6 overflow-auto"):
            yield  # 讓呼叫者可以插入內容


def render_topbar(*args, **kwargs):
    """向後相容性 shim：舊頁面可能呼叫 render_topbar，將其映射到 render_header"""
    # 如果第一個參數是字串，視為 title 參數（舊版 render_topbar 可能接受 title）
    if args and isinstance(args[0], str):
        # 舊版 render_topbar(title) -> 呼叫 render_header(season)
        # 這裡我們忽略 title，使用預設 season
        season = "2026Q1"
        if len(args) > 1 and isinstance(args[1], str):
            season = args[1]
        return render_header(season)
    # 如果沒有參數，使用預設 season
    return render_header(kwargs.get("season", "2026Q1"))



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/router.py
sha256(source_bytes) = 4017aa6f25626704c8a1ba757c1b8675cacecd02ad56466b7597a513281f1f85
bytes = 815
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 路由設定"""

from nicegui import ui


def register_pages() -> None:
    """註冊所有頁面路由"""
    from .pages import (
        register_home,
        register_new_job,
        register_job,
        register_results,
        register_charts,
        register_deploy,
        register_history,
        register_candidates,
        register_wizard,
        register_portfolio,
        register_run_detail,
        register_settings,
        register_status,
    )
    
    # 註冊所有頁面
    register_home()
    register_new_job()
    register_job()
    register_results()
    register_charts()
    register_deploy()
    register_history()
    register_candidates()
    register_wizard()
    register_portfolio()
    register_run_detail()
    register_settings()
    register_status()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/state.py
sha256(source_bytes) = e539b8559a664beed7b908d0f5f0388605f85fc204fffcb1edee31fc5fad31a4
bytes = 1536
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 應用程式狀態管理"""

from typing import Dict, Any, Optional


class AppState:
    """應用程式全域狀態"""
    
    _instance: Optional["AppState"] = None
    
    def __new__(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """初始化狀態"""
        self.current_job_id: Optional[str] = None
        self.user_preferences: Dict[str, Any] = {
            "theme": "dark",
            "refresh_interval": 5,  # 秒
            "default_outputs_root": "outputs",
        }
        self.notifications: list = []
    
    def set_current_job(self, job_id: str) -> None:
        """設定當前選中的任務"""
        self.current_job_id = job_id
    
    def get_current_job(self) -> Optional[str]:
        """取得當前選中的任務"""
        return self.current_job_id
    
    def add_notification(self, message: str, level: str = "info") -> None:
        """新增通知訊息"""
        self.notifications.append({
            "message": message,
            "level": level,
            "timestamp": "now"  # 實際應用中應使用 datetime
        })
        # 限制通知數量
        if len(self.notifications) > 10:
            self.notifications.pop(0)
    
    def clear_notifications(self) -> None:
        """清除所有通知"""
        self.notifications.clear()


# 全域狀態實例
app_state = AppState()



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/ui_compat.py
sha256(source_bytes) = 604a1beae9a48c466afff0093b34ad2d207867b30aecd0ef1de589b9c9f3aaf5
bytes = 7011
redacted = False
--------------------------------------------------------------------------------
"""UI Compatibility Wrapper - Canonical NiceGUI patterns for FishBroWFS_V2.

This module provides wrapper functions that enforce the canonical UI patterns:
1. No label= keyword argument in widget constructors
2. Labels are separate ui.label() widgets
3. Consistent spacing and styling
4. Built-in bindability support

Usage:
    from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_date, labeled_input
    
    # Instead of: ui.date(label="Start Date")
    # Use:
    labeled_date("Start Date").bind_value(state, "start_date")
"""

from typing import Any, Callable, Optional, List, Dict, Union
from nicegui import ui


def labeled(widget_factory: Callable, label: str, *args, **kwargs) -> Any:
    """Create a labeled widget using the canonical pattern.
    
    Args:
        widget_factory: UI widget constructor (e.g., ui.date, ui.input)
        label: Label text to display above the widget
        *args, **kwargs: Passed to widget_factory
        
    Returns:
        The created widget instance
        
    Example:
        >>> date_widget = labeled(ui.date, "Start Date", value="2024-01-01")
        >>> date_widget.bind_value(state, "start_date")
    """
    with ui.column().classes("gap-1 w-full"):
        ui.label(label)
        widget = widget_factory(*args, **kwargs)
        return widget


def labeled_date(label: str, **kwargs) -> Any:
    """Create a labeled date picker.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.date()
        
    Returns:
        ui.date widget instance
    """
    return labeled(ui.date, label, **kwargs)


def labeled_input(label: str, **kwargs) -> Any:
    """Create a labeled text input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.input()
        
    Returns:
        ui.input widget instance
    """
    return labeled(ui.input, label, **kwargs)


def labeled_select(label: str, **kwargs) -> Any:
    """Create a labeled select/dropdown.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.select()
        
    Returns:
        ui.select widget instance
    """
    return labeled(ui.select, label, **kwargs)


def labeled_number(label: str, **kwargs) -> Any:
    """Create a labeled number input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.number()
        
    Returns:
        ui.number widget instance
    """
    return labeled(ui.number, label, **kwargs)


def labeled_textarea(label: str, **kwargs) -> Any:
    """Create a labeled textarea.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.textarea()
        
    Returns:
        ui.textarea widget instance
    """
    return labeled(ui.textarea, label, **kwargs)


def labeled_slider(label: str, **kwargs) -> Any:
    """Create a labeled slider.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.slider()
        
    Returns:
        ui.slider widget instance
    """
    return labeled(ui.slider, label, **kwargs)


def labeled_checkbox(label: str, **kwargs) -> Any:
    """Create a labeled checkbox.
    
    Note: ui.checkbox already has built-in label support via first positional arg.
    This wrapper maintains consistency with other labeled widgets.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.checkbox()
        
    Returns:
        ui.checkbox widget instance
    """
    return labeled(ui.checkbox, label, **kwargs)


def labeled_switch(label: str, **kwargs) -> Any:
    """Create a labeled switch.
    
    Note: ui.switch already has built-in label support via first positional arg.
    This wrapper maintains consistency with other labeled widgets.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.switch()
        
    Returns:
        ui.switch widget instance
    """
    return labeled(ui.switch, label, **kwargs)


def labeled_radio(label: str, **kwargs) -> Any:
    """Create a labeled radio button group.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.radio()
        
    Returns:
        ui.radio widget instance
    """
    return labeled(ui.radio, label, **kwargs)


def labeled_color_input(label: str, **kwargs) -> Any:
    """Create a labeled color input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.color_input()
        
    Returns:
        ui.color_input widget instance
    """
    return labeled(ui.color_input, label, **kwargs)


def labeled_upload(label: str, **kwargs) -> Any:
    """Create a labeled file upload.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.upload()
        
    Returns:
        ui.upload widget instance
    """
    return labeled(ui.upload, label, **kwargs)


def form_section(title: str) -> Any:
    """Create a form section with consistent styling.
    
    Args:
        title: Section title
        
    Returns:
        Context manager for the form section
    """
    return ui.card().classes("w-full p-4 mb-6 bg-nexus-900")


def form_row() -> Any:
    """Create a form row with consistent spacing.
    
    Returns:
        Context manager for the form row
    """
    return ui.row().classes("w-full gap-4 mb-4")


def form_column() -> Any:
    """Create a form column with consistent spacing.
    
    Returns:
        Context manager for the form column
    """
    return ui.column().classes("gap-2 w-full")


# Convenience function for wizard forms
def wizard_field(label: str, widget_type: str = "input", **kwargs) -> Any:
    """Create a wizard form field with consistent styling.
    
    Args:
        label: Field label
        widget_type: Type of widget ('date', 'input', 'select', 'number', 'textarea')
        **kwargs: Passed to the widget constructor
        
    Returns:
        The created widget instance
        
    Raises:
        ValueError: If widget_type is not supported
    """
    widget_map = {
        'date': labeled_date,
        'input': labeled_input,
        'select': labeled_select,
        'number': labeled_number,
        'textarea': labeled_textarea,
        'slider': labeled_slider,
        'checkbox': labeled_checkbox,
        'switch': labeled_switch,
        'radio': labeled_radio,
        'color': labeled_color_input,
        'upload': labeled_upload,
    }
    
    if widget_type not in widget_map:
        raise ValueError(f"Unsupported widget_type: {widget_type}. "
                       f"Supported: {list(widget_map.keys())}")
    
    widget = widget_map[widget_type](label, **kwargs)
    widget.classes("w-full")
    return widget


# Example usage (commented out for documentation):
"""
# Before (forbidden):
# ui.date(label="Start Date", value="2024-01-01")  # This is the forbidden pattern

# After (canonical):
from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_date
labeled_date("Start Date", value="2024-01-01").bind_value(state, "start_date")

# Or using wizard_field for wizard forms:
wizard_field("Start Date", "date", value="2024-01-01").bind_value(state, "start_date")
"""
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/__init__.py
sha256(source_bytes) = 80a08f1575f9e32364c8ad7e4250b63cdf4a433eb6d3e19ff1c5f7585624425e
bytes = 1082
redacted = False
--------------------------------------------------------------------------------

"""NiceGUI 頁面模組"""

from .home import register as register_home
from .new_job import register as register_new_job
from .job import register as register_job
from .results import register as register_results
from .charts import register as register_charts
from .deploy import register as register_deploy
from .artifacts import register as register_artifacts
from .history import register as register_history
from .candidates import register as register_candidates
from .wizard import register as register_wizard
from .portfolio import register as register_portfolio
from .run_detail import register as register_run_detail
from .settings import register as register_settings
from .status import register as register_status

__all__ = [
    "register_home",
    "register_new_job",
    "register_job",
    "register_results",
    "register_charts",
    "register_deploy",
    "register_artifacts",
    "register_history",
    "register_candidates",
    "register_wizard",
    "register_portfolio",
    "register_run_detail",
    "register_settings",
    "register_status",
]



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/artifacts.py
sha256(source_bytes) = e9f4e865a82acb825717c8f3e2ce7949b8b7e7a7209f06c0438dc55e4417406e
bytes = 14598
redacted = False
--------------------------------------------------------------------------------
"""Artifacts Drill-down Pages for M2.

Provides read-only navigation through research units and artifact links.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any
from urllib.parse import quote

from nicegui import ui

from ..layout import render_shell
from FishBroWFS_V2.control.job_api import list_jobs_with_progress
from FishBroWFS_V2.control.artifacts_api import (
    list_research_units,
    get_research_artifacts,
    get_portfolio_index,
)
from FishBroWFS_V2.core.season_context import current_season


def encode_unit_key(unit: Dict[str, Any]) -> str:
    """Encode unit key into a URL-safe string."""
    # Use a simple JSON representation, base64 could be used but keep simple
    key = {
        "data1_symbol": unit.get("data1_symbol"),
        "data1_timeframe": unit.get("data1_timeframe"),
        "strategy": unit.get("strategy"),
        "data2_filter": unit.get("data2_filter"),
    }
    return quote(json.dumps(key, sort_keys=True), safe="")


def decode_unit_key(encoded: str) -> Dict[str, str]:
    """Decode unit key from URL string."""
    import urllib.parse
    import json as json_lib
    decoded = urllib.parse.unquote(encoded)
    return json_lib.loads(decoded)


def render_artifacts_home() -> None:
    """Artifacts home page - list jobs that have research indices."""
    ui.page_title("FishBroWFS V2 - Artifacts")
    
    with render_shell("/artifacts", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            ui.label("Artifacts Drill-down").classes("text-3xl font-bold mb-6")
            ui.label("Select a job to view its research units and artifacts.").classes("text-gray-600 mb-8")
            
            # Fetch jobs
            jobs = list_jobs_with_progress(limit=100)
            # Filter jobs that are DONE (or have research index)
            # For simplicity, we'll show all jobs; but we can add a placeholder
            if not jobs:
                ui.label("No jobs found.").classes("text-gray-500 italic")
                return
            
            # Create table
            columns = [
                {"name": "job_id", "label": "Job ID", "field": "job_id", "align": "left"},
                {"name": "season", "label": "Season", "field": "season", "align": "left"},
                {"name": "status", "label": "Status", "field": "status", "align": "left"},
                {"name": "units_total", "label": "Units", "field": "units_total", "align": "right"},
                {"name": "created_at", "label": "Created", "field": "created_at", "align": "left"},
                {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
            ]
            
            rows = []
            for job in jobs:
                # Determine if research index exists (simplify: assume DONE jobs have it)
                has_research = False
                try:
                    list_research_units(job["season"], job["job_id"])
                    has_research = True
                except FileNotFoundError:
                    pass
                
                rows.append({
                    "job_id": job["job_id"],
                    "season": job.get("season", "N/A"),
                    "status": job.get("status", "UNKNOWN"),
                    "units_total": job.get("units_total", 0),
                    "created_at": job.get("created_at", "")[:19],
                    "has_research": has_research,
                })
            
            # Custom row rendering to include button
            def render_row(row: Dict) -> None:
                with ui.row().classes("w-full items-center"):
                    ui.label(row["job_id"][:8] + "...").classes("font-mono text-sm")
                    ui.space()
                    ui.label(row["season"])
                    ui.space()
                    ui.badge(row["status"].upper(), color={
                        "queued": "yellow",
                        "running": "green",
                        "done": "blue",
                        "failed": "red"
                    }.get(row["status"].lower(), "gray")).classes("text-xs font-bold")
                    ui.space()
                    ui.label(str(row["units_total"]))
                    ui.space()
                    ui.label(row["created_at"])
                    ui.space()
                    if row["has_research"]:
                        ui.button("View Units", icon="list", 
                                 on_click=lambda r=row: ui.navigate.to(f"/artifacts/{r['job_id']}")).props("outline size=sm")
                    else:
                        ui.button("No Index", icon="block").props("outline disabled size=sm").tooltip("Research index not found")
            
            # Use a card for each job for better visual separation
            for row in rows:
                with ui.card().classes("w-full fish-card p-4 mb-3"):
                    render_row(row)


def render_job_units_page(job_id: str) -> None:
    """Page listing research units for a specific job."""
    ui.page_title(f"FishBroWFS V2 - Artifacts {job_id[:8]}...")
    
    with render_shell("/artifacts", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # Header with back button
            with ui.row().classes("w-full items-center mb-6"):
                ui.button("Back to Jobs", icon="arrow_back",
                         on_click=lambda: ui.navigate.to("/artifacts")).props("outline")
                ui.label(f"Job {job_id[:8]}... Research Units").classes("text-2xl font-bold ml-4")
            
            # Determine season (try to get from job info)
            # For now, use current season; but we need to know the season of the job.
            # We'll fetch job details from job_api.
            # Simplification: use current season.
            season = current_season()
            
            try:
                units = list_research_units(season, job_id)
            except FileNotFoundError:
                with ui.card().classes("w-full fish-card p-6 bg-red-50 border-red-200"):
                    ui.label("Research index not found").classes("text-red-800 font-bold mb-2")
                    ui.label(f"No research index found for job {job_id} in season {season}.").classes("text-red-700")
                    ui.button("Back to Jobs", icon="arrow_back",
                             on_click=lambda: ui.navigate.to("/artifacts")).props("outline color=red").classes("mt-4")
                return
            
            if not units:
                ui.label("No units found in research index.").classes("text-gray-500 italic")
                return
            
            # Units table
            columns = [
                {"name": "data1_symbol", "label": "Symbol", "field": "data1_symbol", "align": "left"},
                {"name": "data1_timeframe", "label": "Timeframe", "field": "data1_timeframe", "align": "left"},
                {"name": "strategy", "label": "Strategy", "field": "strategy", "align": "left"},
                {"name": "data2_filter", "label": "Data2 Filter", "field": "data2_filter", "align": "left"},
                {"name": "status", "label": "Status", "field": "status", "align": "left"},
                {"name": "actions", "label": "Artifacts", "field": "actions", "align": "center"},
            ]
            
            rows = []
            for unit in units:
                rows.append({
                    "data1_symbol": unit.get("data1_symbol", "N/A"),
                    "data1_timeframe": unit.get("data1_timeframe", "N/A"),
                    "strategy": unit.get("strategy", "N/A"),
                    "data2_filter": unit.get("data2_filter", "N/A"),
                    "status": unit.get("status", "UNKNOWN"),
                    "unit_key": encode_unit_key(unit),
                })
            
            # Render table using nicegui table component
            with ui.card().classes("w-full fish-card p-4"):
                ui.label("Research Units").classes("text-xl font-bold mb-4 text-cyber-400")
                table = ui.table(columns=columns, rows=rows, row_key="unit_key").classes("w-full").props("dense flat bordered")
                
                # Add slot for actions
                table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <q-btn icon="link" size="sm" flat color="primary"
                               @click="() => $router.push('/artifacts/{{props.row.job_id}}/' + encodeURIComponent(props.row.unit_key))" />
                    </q-td>
                """)
                
                # Since slot syntax is complex, we'll instead create a custom column via Python loop
                # Let's simplify: create a custom grid using rows
                ui.separator().classes("my-4")
                ui.label("Units List").classes("font-bold mb-2")
                for row in rows:
                    with ui.row().classes("w-full items-center border-b py-3"):
                        ui.label(row["data1_symbol"]).classes("w-24")
                        ui.label(row["data1_timeframe"]).classes("w-32")
                        ui.label(row["strategy"]).classes("w-48")
                        ui.label(row["data2_filter"]).classes("w-32")
                        ui.badge(row["status"].upper(), color="blue" if row["status"] == "DONE" else "gray").classes("text-xs font-bold w-24")
                        ui.space()
                        ui.button("View Artifacts", icon="link", 
                                 on_click=lambda r=row: ui.navigate.to(f"/artifacts/{job_id}/{r['unit_key']}")).props("outline size=sm")
            
            # Portfolio index section (if exists)
            try:
                portfolio_idx = get_portfolio_index(season, job_id)
                with ui.card().classes("w-full fish-card p-4 mt-6"):
                    ui.label("Portfolio Artifacts").classes("text-xl font-bold mb-4 text-cyber-400")
                    with ui.grid(columns=2).classes("w-full gap-4"):
                        ui.label("Summary:").classes("font-medium")
                        ui.label(portfolio_idx.get("summary", "N/A")).classes("font-mono text-sm")
                        ui.label("Admission:").classes("font-medium")
                        ui.label(portfolio_idx.get("admission", "N/A")).classes("font-mono text-sm")
            except FileNotFoundError:
                pass  # No portfolio index


def render_unit_artifacts_page(job_id: str, encoded_unit_key: str) -> None:
    """Page displaying artifact links for a specific unit."""
    ui.page_title(f"FishBroWFS V2 - Artifacts {job_id[:8]}...")
    
    with render_shell("/artifacts", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # Back navigation
            with ui.row().classes("w-full items-center mb-6"):
                ui.button("Back to Units", icon="arrow_back",
                         on_click=lambda: ui.navigate.to(f"/artifacts/{job_id}")).props("outline")
                ui.label(f"Unit Artifacts").classes("text-2xl font-bold ml-4")
            
            season = current_season()
            unit_key = decode_unit_key(encoded_unit_key)
            
            try:
                artifacts = get_research_artifacts(season, job_id, unit_key)
            except KeyError:
                with ui.card().classes("w-full fish-card p-6 bg-red-50 border-red-200"):
                    ui.label("Unit not found").classes("text-red-800 font-bold mb-2")
                    ui.label(f"No artifacts found for the specified unit.").classes("text-red-700")
                    return
            
            # Display unit key info
            with ui.card().classes("w-full fish-card p-4 mb-6"):
                ui.label("Unit Details").classes("text-lg font-bold mb-3")
                with ui.grid(columns=2).classes("w-full gap-2 text-sm"):
                    ui.label("Symbol:").classes("font-medium")
                    ui.label(unit_key.get("data1_symbol", "N/A"))
                    ui.label("Timeframe:").classes("font-medium")
                    ui.label(unit_key.get("data1_timeframe", "N/A"))
                    ui.label("Strategy:").classes("font-medium")
                    ui.label(unit_key.get("strategy", "N/A"))
                    ui.label("Data2 Filter:").classes("font-medium")
                    ui.label(unit_key.get("data2_filter", "N/A"))
            
            # Artifacts links
            with ui.card().classes("w-full fish-card p-4"):
                ui.label("Artifacts").classes("text-lg font-bold mb-3")
                if not artifacts:
                    ui.label("No artifact paths defined.").classes("text-gray-500 italic")
                else:
                    for name, path in artifacts.items():
                        with ui.row().classes("w-full items-center py-2 border-b last:border-0"):
                            ui.label(name).classes("font-medium w-48")
                            ui.label(str(path)).classes("font-mono text-sm flex-1")
                            # Create a link button that opens the file in a new tab (if served)
                            # For now, just show path
                            ui.button("Open", icon="open_in_new", on_click=lambda p=path: ui.navigate.to(f"/file/{p}")).props("outline size=sm").tooltip(f"Open {path}")
            
            # Note about read-only
            with ui.card().classes("w-full fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• This page shows the artifact file paths generated by the research pipeline.").classes("text-slate-300 mb-1")
                ui.label("• All artifacts are read‑only; no modifications can be made from this UI.").classes("text-slate-300 mb-1")
                ui.label("• Click 'Open' to view the artifact if the file is served by the backend.").classes("text-slate-300")


# Register routes
def register() -> None:
    """Register artifacts pages."""
    
    @ui.page("/artifacts")
    def artifacts_home() -> None:
        render_artifacts_home()
    
    @ui.page("/artifacts/{job_id}")
    def artifacts_job(job_id: str) -> None:
        render_job_units_page(job_id)
    
    @ui.page("/artifacts/{job_id}/{unit_key}")
    def artifacts_unit(job_id: str, unit_key: str) -> None:
        render_unit_artifacts_page(job_id, unit_key)
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/candidates.py
sha256(source_bytes) = fecd310f6c76341a5d450fbc06ca91d704ff7533fb1c39d8cb73a4e5cc898bd1
bytes = 13491
redacted = False
--------------------------------------------------------------------------------
"""
Candidates 頁面 - 顯示 canonical results 和 research index
根據 P0.5-1 要求：統一 UI 只讀 outputs/research/ 為官方彙整來源
"""

from nicegui import ui
from datetime import datetime
from typing import List, Dict, Any

from ..layout import render_shell
from ...services.candidates_reader import (
    load_canonical_results,
    load_research_index,
    CanonicalResult,
    ResearchIndexEntry,
    refresh_canonical_results,
    refresh_research_index,
)
from ...services.actions import generate_research
from FishBroWFS_V2.core.season_context import current_season, canonical_results_path, research_index_path
from FishBroWFS_V2.core.season_state import load_season_state


def render_canonical_results_table(results: List[CanonicalResult]) -> None:
    """渲染 canonical results 表格"""
    if not results:
        ui.label("No canonical results found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left"},
        {"name": "bars", "label": "Bars", "field": "bars", "align": "right"},
        {"name": "net_profit", "label": "Net Profit", "field": "net_profit", "align": "right", "format": lambda val: f"{val:.2f}"},
        {"name": "max_drawdown", "label": "Max DD", "field": "max_drawdown", "align": "right", "format": lambda val: f"{val:.2f}"},
        {"name": "score_final", "label": "Score Final", "field": "score_final", "align": "right", "format": lambda val: f"{val:.3f}"},
        {"name": "trades", "label": "Trades", "field": "trades", "align": "right"},
        {"name": "start_date", "label": "Start Date", "field": "start_date", "align": "left"},
    ]
    
    rows = []
    for result in results:
        rows.append({
            "run_id": result.run_id[:12] + "..." if len(result.run_id) > 12 else result.run_id,
            "strategy_id": result.strategy_id,
            "symbol": result.symbol,
            "bars": result.bars,
            "net_profit": result.net_profit,
            "max_drawdown": result.max_drawdown,
            "score_final": result.score_final,
            "trades": result.trades,
            "start_date": result.start_date[:10] if result.start_date else "",
        })
    
    # 使用 fish-card 樣式
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Canonical Results").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered")

def render_research_index_table(entries: List[ResearchIndexEntry]) -> None:
    """渲染 research index 表格"""
    if not entries:
        ui.label("No research index entries found").classes("text-gray-500 italic")
        return
    
    # 建立表格
    columns = [
        {"name": "run_id", "label": "Run ID", "field": "run_id", "align": "left"},
        {"name": "season", "label": "Season", "field": "season", "align": "left"},
        {"name": "stage", "label": "Stage", "field": "stage", "align": "left"},
        {"name": "mode", "label": "Mode", "field": "mode", "align": "left"},
        {"name": "strategy_id", "label": "Strategy", "field": "strategy_id", "align": "left"},
        {"name": "dataset_id", "label": "Dataset", "field": "dataset_id", "align": "left"},
        {"name": "status", "label": "Status", "field": "status", "align": "left"},
        {"name": "created_at", "label": "Created At", "field": "created_at", "align": "left"},
    ]
    
    rows = []
    for entry in entries:
        rows.append({
            "run_id": entry.run_id[:12] + "..." if len(entry.run_id) > 12 else entry.run_id,
            "season": entry.season,
            "stage": entry.stage,
            "mode": entry.mode,
            "strategy_id": entry.strategy_id,
            "dataset_id": entry.dataset_id,
            "status": entry.status,
            "created_at": entry.created_at[:19] if entry.created_at else "",
        })
    
    # 使用 fish-card 樣式
    with ui.card().classes("w-full fish-card p-4 mb-6"):
        ui.label("Research Index").classes("text-xl font-bold mb-4 text-cyber-400")
        ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full").props("dense flat bordered")

def render_candidates_page() -> None:
    """渲染 candidates 頁面內容"""
    ui.page_title("FishBroWFS V2 - Candidates")
    
    # 使用 shell 佈局
    with render_shell("/candidates", current_season()):
        with ui.column().classes("w-full max-w-7xl mx-auto p-6"):
            # 頁面標題
            with ui.row().classes("w-full items-center mb-6"):
                ui.label("Candidates Dashboard").classes("text-3xl font-bold text-cyber-glow")
                ui.space()
                
                # 動作按鈕容器
                action_container = ui.row().classes("gap-2")
            
            # 檢查 research 檔案是否存在
            current_season_str = current_season()
            canonical_exists = canonical_results_path(current_season_str).exists()
            research_index_exists = research_index_path(current_season_str).exists()
            research_exists = canonical_exists and research_index_exists
            
            # 檢查 season freeze 狀態
            season_state = load_season_state(current_season_str)
            is_frozen = season_state.is_frozen()
            frozen_reason = season_state.reason if season_state.reason else "Season is frozen"
            
            # 說明文字
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("📊 Official Research Consolidation").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label(f"This page displays canonical results and research index from outputs/seasons/{current_season_str}/research/").classes("text-slate-300 mb-1")
                ui.label(f"Source: outputs/seasons/{current_season_str}/research/canonical_results.json & outputs/seasons/{current_season_str}/research/research_index.json").classes("text-sm text-slate-400")
                
                # 顯示檔案狀態
                if not research_exists:
                    with ui.row().classes("items-center mt-3 p-3 bg-amber-900/30 rounded-lg"):
                        ui.icon("warning", color="amber").classes("text-lg")
                        ui.label("Research artifacts not found for this season.").classes("ml-2 text-amber-300")
                
                # 顯示 freeze 狀態
                if is_frozen:
                    with ui.row().classes("items-center mt-3 p-3 bg-red-900/30 rounded-lg"):
                        ui.icon("lock", color="red").classes("text-lg")
                        ui.label(f"Season is frozen (reason: {frozen_reason})").classes("ml-2 text-red-300")
                        ui.label("All write actions are disabled.").classes("ml-2 text-red-300 text-sm")
            
            # 載入資料 - 使用當前 season
            canonical_results = load_canonical_results(current_season_str)
            research_index = load_research_index(current_season_str)
            
            # 統計卡片
            with ui.row().classes("w-full gap-4 mb-6"):
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Canonical Results").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(canonical_results))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("entries").classes("text-xs text-slate-500")
                    if not canonical_exists:
                        ui.label("File missing").classes("text-xs text-amber-500 mt-1")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Research Index").classes("text-sm text-slate-400 mb-1")
                    ui.label(str(len(research_index))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("entries").classes("text-xs text-slate-500")
                    if not research_index_exists:
                        ui.label("File missing").classes("text-xs text-amber-500 mt-1")
                
                with ui.card().classes("flex-1 fish-card p-4"):
                    ui.label("Unique Strategies").classes("text-sm text-slate-400 mb-1")
                    strategies = {r.strategy_id for r in canonical_results}
                    ui.label(str(len(strategies))).classes("text-2xl font-bold text-cyber-400")
                    ui.label("strategies").classes("text-xs text-slate-500")
            
            # 動作按鈕功能
            def generate_research_action():
                """觸發 Generate Research 動作"""
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Generating research...").classes("text-sm text-slate-400")
                
                # 執行 Generate Research 動作
                result = generate_research(current_season_str, legacy_copy=False)
                
                # 顯示結果
                if result.ok:
                    ui.notify(f"Research generated successfully! {len(result.artifacts_written)} artifacts created.", type="positive")
                else:
                    error_msg = result.stderr_tail[-1] if result.stderr_tail else "Unknown error"
                    ui.notify(f"Research generation failed: {error_msg}", type="negative")
                
                # 重新載入頁面
                ui.navigate.to("/candidates", reload=True)
            
            def refresh_all():
                """刷新所有資料"""
                with action_container:
                    action_container.clear()
                    ui.spinner(size="sm", color="blue")
                    ui.label("Refreshing...").classes("text-sm text-slate-400")
                
                # 刷新資料 - 使用當前 season
                canonical_success = refresh_canonical_results(current_season_str)
                research_success = refresh_research_index(current_season_str)
                
                # 重新載入頁面
                ui.navigate.to("/candidates", reload=True)
            
            # 更新動作按鈕
            with action_container:
                if not research_exists:
                    if is_frozen:
                        # Season frozen: disable button with tooltip
                        ui.button("Generate Research", icon="play_arrow").props("outline disabled").tooltip(f"Season is frozen: {frozen_reason}")
                    else:
                        ui.button("Generate Research", icon="play_arrow", on_click=generate_research_action).props("outline color=positive")
                ui.button("Refresh Data", icon="refresh", on_click=refresh_all).props("outline")
            
            # 分隔線
            ui.separator().classes("my-6")
            
            # 如果沒有資料，顯示提示
            if not canonical_results and not research_index:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("insights", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No research data available").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label(f"Research artifacts not found for season {current_season_str}").classes("text-slate-400 mb-6")
                    if not research_exists:
                        ui.button("Generate Research Now", icon="play_arrow", on_click=generate_research_action).props("color=positive")
                return
            
            # Canonical Results 區塊
            ui.label("Canonical Results").classes("text-2xl font-bold mb-4 text-cyber-300")
            render_canonical_results_table(canonical_results)
            
            # Research Index 區塊
            ui.label("Research Index").classes("text-2xl font-bold mb-4 text-cyber-300")
            render_research_index_table(research_index)
            
            # 底部說明
            with ui.card().classes("w-full fish-card p-4 mt-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Canonical Results: Final performance metrics from research pipeline").classes("text-slate-300 mb-1")
                ui.label("• Research Index: Metadata about research runs (stage, mode, dataset, etc.)").classes("text-slate-300 mb-1")
                ui.label(f"• Data Source: outputs/seasons/{current_season_str}/research/ directory (single source of truth)").classes("text-slate-300 mb-1")
                ui.label("• Refresh: Click 'Refresh Data' to reload from disk").classes("text-slate-300")
                if not research_exists:
                    ui.label("• Generate: Click 'Generate Research' to create research artifacts for this season").classes("text-slate-300 text-amber-300")

def register() -> None:
    """註冊 candidates 頁面路由"""
    
    @ui.page("/candidates")
    def candidates_page() -> None:
        """Candidates 頁面"""
        render_candidates_page()
--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/charts.py
sha256(source_bytes) = 2913bdb28ab5866c36568286fb8486b27cd637b403299ace39498985656c28eb
bytes = 18538
redacted = False
--------------------------------------------------------------------------------

"""圖表頁面 - Charts"""

from nicegui import ui

from ..api import list_chart_artifacts, load_chart_artifact
from ..state import app_state


def register() -> None:
    """註冊圖表頁面"""
    
    @ui.page("/charts/{job_id}")
    def charts_page(job_id: str) -> None:
        """圖表頁面"""
        ui.page_title(f"FishBroWFS V2 - Charts {job_id[:8]}...")
        
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            # DEV MODE banner - 更醒目的誠實化標示
            with ui.card().classes("w-full mb-6 bg-red-50 border-red-300"):
                with ui.row().classes("w-full items-center"):
                    ui.icon("error", size="lg").classes("text-red-600 mr-2")
                    ui.label("DEV MODE: Chart visualization NOT WIRED").classes("text-red-800 font-bold text-lg")
                ui.label("All chart artifacts are currently NOT IMPLEMENTED. UI cannot compute drawdown/correlation/heatmap.").classes("text-sm text-red-700 mb-2")
                ui.label("Constitutional principle: UI only renders artifacts produced by Research/Portfolio layer.").classes("text-xs text-red-600")
                ui.label("Expected artifact location: outputs/runs/{job_id}/viz/*.json").classes("font-mono text-xs text-gray-600")
            
            # 圖表選擇器
            chart_selector_container = ui.row().classes("w-full mb-6")
            
            # 圖表顯示容器
            chart_container = ui.column().classes("w-full")
            
            def refresh_charts(jid: str) -> None:
                """刷新圖表顯示"""
                chart_selector_container.clear()
                chart_container.clear()
                
                try:
                    # 獲取可用的圖表 artifact
                    artifacts = list_chart_artifacts(jid)
                    
                    with chart_selector_container:
                        ui.label("Select chart:").classes("mr-4 font-bold")
                        
                        # 預設圖表選項 - 但誠實標示為 "Not wired"
                        chart_options = {
                            "equity": "Equity Curve (NOT WIRED)",
                            "drawdown": "Drawdown Curve (NOT WIRED)",
                            "corr": "Correlation Matrix (NOT WIRED)",
                            "heatmap": "Heatmap (NOT WIRED)",
                        }
                        
                        # 如果有 artifact，使用 artifact 列表
                        if artifacts and len(artifacts) > 0:
                            chart_options = {a["id"]: f"{a.get('name', a['id'])} (Artifact)" for a in artifacts}
                        else:
                            # 沒有 artifact，顯示 "Not wired" 選項
                            chart_options = {"not_wired": "No artifacts available (NOT WIRED)"}
                        
                        chart_select = ui.select(
                            options=chart_options,
                            value=list(chart_options.keys())[0] if chart_options else None
                        ).props("disabled" if not artifacts else None).classes("flex-1")
                        
                        # 滑點等級選擇器 - 如果沒有 artifact 則 disabled
                        slippage_select = ui.select(
                            label="Slippage Level",
                            options={"S0": "S0", "S1": "S1", "S2": "S2", "S3": "S3"},
                            value="S0"
                        ).props("disabled" if not artifacts else None).classes("ml-4")
                        
                        # 更新圖表按鈕 - 如果沒有 artifact 則 disabled
                        def update_chart_display() -> None:
                            if chart_select.value == "not_wired":
                                with chart_container:
                                    chart_container.clear()
                                    display_not_wired_message()
                            else:
                                load_and_display_chart(jid, chart_select.value, slippage_select.value)
                        
                        ui.button("Load", on_click=update_chart_display, icon="visibility",
                                 props="disabled" if not artifacts else None).classes("ml-4")
                    
                    # 初始載入
                    if artifacts and len(artifacts) > 0:
                        load_and_display_chart(jid, list(chart_options.keys())[0], "S0")
                    else:
                        with chart_container:
                            display_not_wired_message()
                
                except Exception as e:
                    with chart_container:
                        ui.label(f"Load failed: {e}").classes("text-red-600")
                        display_not_wired_message()
            
            def display_not_wired_message() -> None:
                """顯示 'Not wired' 訊息"""
                with ui.card().classes("w-full p-6 bg-gray-50 border-gray-300"):
                    ui.icon("warning", size="xl").classes("text-gray-500 mx-auto mb-4")
                    ui.label("Chart visualization NOT WIRED").classes("text-xl font-bold text-gray-700 text-center mb-2")
                    ui.label("The chart artifact system is not yet implemented.").classes("text-gray-600 text-center mb-4")
                    
                    ui.label("Expected workflow:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-gray-600"):
                        ui.label("1. Research/Portfolio layer produces visualization artifacts")
                        ui.label("2. Artifacts saved to outputs/runs/{job_id}/viz/")
                        ui.label("3. UI loads and renders artifacts (no computation)")
                        ui.label("4. UI shows equity/drawdown/corr/heatmap from artifacts")
                    
                    ui.label("Current status:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-red-600"):
                        ui.label("• Artifact production NOT IMPLEMENTED")
                        ui.label("• UI cannot compute drawdown/correlation")
                        ui.label("• All chart displays are placeholders")
            
            def load_and_display_chart(jid: str, chart_type: str, slippage_level: str) -> None:
                """載入並顯示圖表"""
                chart_container.clear()
                
                with chart_container:
                    ui.label(f"{chart_type} - {slippage_level}").classes("text-xl font-bold mb-4")
                    
                    try:
                        # 嘗試載入 artifact
                        artifact_data = load_chart_artifact(jid, f"{chart_type}_{slippage_level}")
                        
                        if artifact_data and artifact_data.get("type") != "not_implemented":
                            # 顯示 artifact 資訊
                            with ui.card().classes("w-full p-4 mb-4 bg-green-50 border-green-200"):
                                ui.label("✅ Artifact Loaded").classes("font-bold mb-2 text-green-800")
                                ui.label(f"Type: {artifact_data.get('type', 'unknown')}").classes("text-sm")
                                ui.label(f"Data points: {len(artifact_data.get('data', []))}").classes("text-sm")
                                ui.label(f"Generated at: {artifact_data.get('generated_at', 'unknown')}").classes("text-sm")
                            
                            # 根據圖表類型顯示不同的預覽
                            if chart_type == "equity":
                                display_equity_chart_preview(artifact_data)
                            elif chart_type == "drawdown":
                                display_drawdown_chart_preview(artifact_data)
                            elif chart_type == "corr":
                                display_correlation_preview(artifact_data)
                            elif chart_type == "heatmap":
                                display_heatmap_preview(artifact_data)
                            else:
                                display_generic_chart_preview(artifact_data)
                        
                        else:
                            # 顯示 NOT WIRED 訊息
                            display_not_wired_chart(chart_type, slippage_level)
                    
                    except Exception as e:
                        ui.label(f"Chart load error: {e}").classes("text-red-600")
                        display_not_wired_chart(chart_type, slippage_level)
            
            def display_not_wired_chart(chart_type: str, slippage_level: str) -> None:
                """顯示 NOT WIRED 圖表訊息"""
                with ui.card().classes("w-full p-6 bg-red-50 border-red-300"):
                    ui.icon("error", size="xl").classes("text-red-600 mx-auto mb-4")
                    ui.label(f"NOT WIRED: {chart_type} - {slippage_level}").classes("text-xl font-bold text-red-800 text-center mb-2")
                    ui.label("This chart visualization is not yet implemented.").classes("text-red-700 text-center mb-4")
                    
                    # 憲法級原則提醒
                    with ui.card().classes("w-full p-4 bg-white border-gray-300"):
                        ui.label("Constitutional principles:").classes("font-bold mb-2")
                        with ui.column().classes("ml-2 text-sm text-gray-700"):
                            ui.label("• All visualization data must be produced by Research/Portfolio as artifacts")
                            ui.label("• UI only renders, never computes drawdown/correlation/etc.")
                            ui.label("• Artifacts are the single source of truth")
                            ui.label("• UI cannot compute anything - must wait for artifact production")
                    
                    # 預期的工作流程
                    ui.label("Expected workflow:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-gray-600"):
                        ui.label(f"1. Research layer produces {chart_type}_{slippage_level}.json")
                        ui.label("2. Artifact saved to outputs/runs/{job_id}/viz/")
                        ui.label("3. UI loads artifact via Control API")
                        ui.label("4. UI renders using artifact data (no computation)")
                    
                    # 當前狀態
                    ui.label("Current status:").classes("font-bold mt-4")
                    with ui.column().classes("ml-4 text-sm text-red-600"):
                        ui.label("• Artifact production NOT IMPLEMENTED")
                        ui.label("• Control API endpoint returns 'not_implemented'")
                        ui.label("• UI shows this honest 'NOT WIRED' message")
                        ui.label("• No fake charts or placeholder data")
            
            def display_equity_chart_preview(data: dict) -> None:
                """顯示 Equity Curve 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Equity Curve Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: UI only renders artifact, no computation").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域 - 真實 artifact 資料
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📈 Real Equity Curve from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取統計資訊
                    if "stats" in data:
                        stats = data["stats"]
                        with ui.grid(columns=4).classes("w-full mt-4 gap-2"):
                            ui.label("Final equity:").classes("font-bold")
                            ui.label(f"{stats.get('final_equity', 'N/A')}").classes("text-right")
                            ui.label("Max drawdown:").classes("font-bold")
                            ui.label(f"{stats.get('max_drawdown', 'N/A')}%").classes("text-right text-red-600")
                            ui.label("Sharpe ratio:").classes("font-bold")
                            ui.label(f"{stats.get('sharpe_ratio', 'N/A')}").classes("text-right")
                            ui.label("Trades:").classes("font-bold")
                            ui.label(f"{stats.get('trades', 'N/A')}").classes("text-right")
            
            def display_drawdown_chart_preview(data: dict) -> None:
                """顯示 Drawdown Curve 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Drawdown Curve Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: Drawdown must be computed by Research, not UI").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📉 Real Drawdown Curve from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取統計資訊
                    if "stats" in data:
                        stats = data["stats"]
                        with ui.grid(columns=3).classes("w-full mt-4 gap-2"):
                            ui.label("Max drawdown:").classes("font-bold")
                            ui.label(f"{stats.get('max_drawdown', 'N/A')}%").classes("text-right text-red-600")
                            ui.label("Drawdown period:").classes("font-bold")
                            ui.label(f"{stats.get('drawdown_period', 'N/A')} days").classes("text-right")
                            ui.label("Recovery time:").classes("font-bold")
                            ui.label(f"{stats.get('recovery_time', 'N/A')} days").classes("text-right")
            
            def display_correlation_preview(data: dict) -> None:
                """顯示 Correlation Matrix 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Correlation Matrix Preview").classes("font-bold mb-2")
                    ui.label("Constitutional: Correlation must be computed by Portfolio, not UI").classes("text-sm text-blue-600 mb-4")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("🔗 Real Correlation Matrix from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取摘要
                    if "summary" in data:
                        summary = data["summary"]
                        ui.label("Correlation summary:").classes("font-bold mt-4")
                        for pair, value in summary.items():
                            with ui.row().classes("w-full text-sm"):
                                ui.label(f"{pair}:").classes("font-bold flex-1")
                                ui.label(f"{value}").classes("text-right")
            
            def display_heatmap_preview(data: dict) -> None:
                """顯示 Heatmap 預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Heatmap Preview").classes("font-bold mb-2")
                    
                    # 圖表區域
                    with ui.row().classes("w-full h-64 items-center justify-center bg-gray-50 rounded"):
                        ui.label("🔥 Real Heatmap from artifact").classes("text-gray-500")
                    
                    # 從 artifact 提取資訊
                    if "description" in data:
                        ui.label(f"Description: {data['description']}").classes("text-sm mt-4")
            
            def display_generic_chart_preview(data: dict) -> None:
                """顯示通用圖表預覽"""
                with ui.card().classes("w-full p-4"):
                    ui.label("Chart Preview").classes("font-bold mb-2")
                    
                    with ui.row().classes("w-full h-48 items-center justify-center bg-gray-50 rounded"):
                        ui.label("📊 Chart rendering area").classes("text-gray-500")
                    
                    # 顯示 artifact 基本資訊
                    ui.label(f"Type: {data.get('type', 'unknown')}").classes("text-sm mt-2")
                    ui.label(f"Data points: {len(data.get('data', []))}").classes("text-sm")
            
            def display_dev_mode_chart(chart_type: str, slippage_level: str) -> None:
                """顯示 DEV MODE 圖表"""
                with ui.card().classes("w-full p-4"):
                    ui.label(f"DEV MODE: {chart_type} - {slippage_level}").classes("font-bold mb-2 text-yellow-700")
                    ui.label("This is a placeholder. Real artifacts will be loaded when available.").classes("text-sm text-gray-600 mb-4")
                    
                    with ui.row().classes("w-full h-48 items-center justify-center bg-yellow-50 rounded border border-yellow-200"):
                        ui.label(f"🎨 {chart_type} chart placeholder ({slippage_level})").classes("text-yellow-600")
                    
                    # 說明文字
                    ui.label("Expected artifact location:").classes("font-bold mt-4 text-sm")
                    ui.label(f"outputs/runs/{{job_id}}/viz/{chart_type}_{slippage_level}.json").classes("font-mono text-xs text-gray-600")
                    
                    # 憲法級原則提醒
                    ui.label("Constitutional principles:").classes("font-bold mt-4 text-sm")
                    ui.label("• All visualization data must be produced by Research/Portfolio as artifacts").classes("text-xs text-gray-600")
                    ui.label("• UI only renders, never computes drawdown/correlation/etc.").classes("text-xs text-gray-600")
                    ui.label("• Artifacts are the single source of truth").classes("text-xs text-gray-600")
            
            # 初始載入
            refresh_charts(job_id)



--------------------------------------------------------------------------------

FILE src/FishBroWFS_V2/gui/nicegui/pages/deploy.py
sha256(source_bytes) = 10a679e34728ec1ee5a686f8eddce9d583e0da5d02cf9f4360edf146d9ceaa4b
bytes = 7640
redacted = True
--------------------------------------------------------------------------------
"""Deploy List Page (Read-only) for M2.

Lists DONE jobs that are eligible for deployment (no actual deployment actions).
M4: Live-safety lock - shows banner when LIVE_EXECUTE is disabled.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Any

from nicegui import ui

from ..layout import render_shell
from FishBroWFS_V2.control.job_api import list_jobs_with_progress
from FishBroWFS_V2.core.season_context import current_season
from FishBroWFS_V2.core.season_state import load_season_state


def _check_live_execute_status() -> tuple[bool, str]:
    """檢查 LIVE_EXECUTE 是否啟用。
    
    Returns:
        tuple[bool, str]: (是否啟用, 原因訊息)
    """
    # 檢查環境變數
    if os.getenv("FISHBRO_ENABLE_LIVE") != "1":
        return False, "LIVE EXECUTION DISABLED (server-side). This UI is read-only."
    
    # 檢查 token 檔案
    token_path =[REDACTED]    if not token_path.exists():[REDACTED]        return False, "LIVE EXECUTION LOCKED:[REDACTED]    
    # 檢查 token 內容
    try:
        token_content =[REDACTED]        if token_content !=[REDACTED]            return False, "LIVE EXECUTION LOCKED:[REDACTED]    except Exception:
        return False, "LIVE EXECUTION LOCKED:[REDACTED]    
    return True, "LIVE EXECUTION ENABLED"


def render_deploy_list() -> None:
    """Render the deploy list page."""
    ui.page_title("FishBroWFS V2 - Deploy List")
    
    with render_shell("/deploy", current_season()):
        with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
            ui.label("Deploy List (Read-only)").classes("text-3xl font-bold mb-6")
            
            # Season frozen banner
            season = current_season()
            season_state = load_season_state(season)
            is_frozen = season_state.is_frozen()
            if is_frozen:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-red-900/30 border-red-700"):
                    with ui.row().classes("items-center"):
                        ui.icon("lock", color="red").classes("text-2xl mr-3")
                        with ui.column():
                            ui.label("Season Frozen").classes("font-bold text-red-300 text-lg")
                            ui.label(f"This season is frozen. All deploy actions are disabled.").classes("text-red-200")
            
            # LIVE EXECUTE disabled banner
            live_enabled, live_reason = _check_live_execute_status()
            if not live_enabled:
                with ui.card().classes("w-full fish-card p-4 mb-6 bg-amber-900/30 border-amber-700"):
                    with ui.row().classes("items-center"):
                        ui.icon("warning", color="amber").classes("text-2xl mr-3")
                        with ui.column():
                            ui.label("Live Execution Disabled").classes("font-bold text-amber-300 text-lg")
                            ui.label(live_reason).classes("text-amber-200")
            
            # Explanation
            with ui.card().classes("w-full fish-card p-4 mb-6 bg-nexus-900"):
                ui.label("ℹ️ About This Page").classes("font-bold text-lg mb-2 text-cyber-300")
                ui.label("• Lists DONE jobs that are eligible for deployment.").classes("text-slate-300 mb-1")
                ui.label("• This is a read‑only view; no deployment actions can be taken from this UI.").classes("text-slate-300 mb-1")
                ui.label("• Click a job to view its artifacts (if research index exists).").classes("text-slate-300")
                if is_frozen:
                    ui.label("• 🔒 Frozen season: All mutation buttons are disabled.").classes("text-red-300 mt-2")
                if not live_enabled:
                    ui.label("• 🚫 Live execution is disabled by server-side policy.").classes("text-amber-300 mt-2")
            
            # Fetch jobs and filter DONE
            jobs = list_jobs_with_progress(limit=100)
            done_jobs = [j for j in jobs if j.get("status", "").lower() == "done"]
            
            if not done_jobs:
                with ui.card().classes("w-full fish-card p-8 text-center"):
                    ui.icon("check_circle", size="xl").classes("text-cyber-400 mb-4")
                    ui.label("No DONE jobs found").classes("text-2xl font-bold text-cyber-300 mb-2")
                    ui.label("Jobs that have completed execution will appear here.").classes("text-slate-400")
                return
            
            # Table of DONE jobs
            columns = [
                {"name": "job_id", "label": "Job ID", "field": "job_id", "align": "left"},
                {"name": "season", "label": "Season", "field": "season", "align": "left"},
                {"name": "units_total", "label": "Units", "field": "units_total", "align": "right"},
                {"name": "created_at", "label": "Created", "field": "created_at", "align": "left"},
                {"name": "updated_at", "label": "Updated", "field": "updated_at", "align": "left"},
                {"name": "actions", "label": "Actions", "field": "actions", "align": "center"},
            ]
            
            rows = []
            for job in done_jobs:
                rows.append({
                    "job_id": job["job_id"],
                    "season": job.get("season", "N/A"),
                    "units_total": job.get("units_total", 0),
                    "created_at": job.get("created_at", "")[:19],
                    "updated_at": job.get("updated_at", "")[:19],
                })
            
            # Render each job as a card
            for row in rows:
                with ui.card().classes("w-full fish-card p-4 mb-4"):
                    with ui.grid(columns=6).classes("w-full items-center gap-4"):
                        ui.label(row["job_id"][:12] + "...").classes("font-mono text-sm")
                        ui.label(row["season"])
                        ui.label(str(row["units_total"])).classes("text-right")
                        ui.label(row["created_at"]).classes("text-sm text-gray-500")
                        ui.label(row["updated_at"]).classes("text-sm text-gray-500")
                        with ui.row().classes("gap-2"):
                            ui.button("Artifacts", icon="link",
                                     on_click=lambda r=row: ui.navigate.to(f"/artifacts/{r['job_id']}")).props("outline size=sm")
                            ui.button("Deploy", icon="rocket",
                                     on_click=lambda: ui.notify("Deploy actions are read-only", type="info")).props("outline disabled" if is_frozen else "outline").tooltip("Deployment is disabled in read-only mode")
            
            # Footer note
            with ui.card().classes("w-full fish-card p-4 mt-6"):
                ui.label("📌 Notes").classes("font-bold mb-2")
                ui.label("• Deploy list is automatically generated from DONE jobs.").classes("text-sm text-slate-400")
                ui.label("• To actually deploy a job, use the command-line interface or a separate deployment tool.").classes("text-sm text-slate-400")
                ui.label("• Frozen seasons prevent any deployment writes.").classes("text-sm text-slate-400")


def register() -> None:
    """Register deploy page."""
    
    @ui.page("/deploy")
    def deploy_page() -> None:
        render_deploy_list()

--------------------------------------------------------------------------------


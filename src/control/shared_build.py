
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

from contracts.dimensions import canonical_json
from contracts.fingerprint import FingerprintIndex
from contracts.features import FeatureRegistry, FeatureSpec, default_feature_registry
from core.fingerprint import (
    build_fingerprint_index_from_raw_ingest,
    compare_fingerprint_indices,
)
from control.fingerprint_store import (
    fingerprint_index_path,
    load_fingerprint_index_if_exists,
    write_fingerprint_index,
)
from core.data.raw_ingest import RawIngestResult, ingest_raw_txt
from control.shared_manifest import write_shared_manifest
from control.bars_store import (
    bars_dir,
    normalized_bars_path,
    resampled_bars_path,
    write_npz_atomic,
    load_npz,
    sha256_file,
)
from core.resampler import (
    get_session_spec_for_dataset,
    normalize_raw_bars,
    resample_ohlcv,
    compute_safe_recompute_start,
    SessionSpecTaipei,
)
from core.bars_contract import (
    validate_bars_with_raise,
    BarsValidationResult,
    BarsManifestEntry,
    create_bars_manifest_entry,
)
from core.features import compute_features_for_tf
from control.features_store import (
    features_dir,
    features_path,
    write_features_npz_atomic,
    load_features_npz,
    compute_features_sha256_dict,
)
from control.features_manifest import (
    features_manifest_path,
    write_features_manifest,
    build_features_manifest_data,
    feature_spec_to_dict,
)
from core.paths import get_shared_cache_root


BuildMode = Literal["FULL", "INCREMENTAL"]

# V1 SSOT: resample/feature timeline anchor start (inclusive).
# We intentionally drop any raw data earlier than this to ensure a consistent
# dataset horizon across instruments.
RESAMPLE_ANCHOR_START = pd.Timestamp("2019-01-01 00:00:00")


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
    feature_scope: str = "BASELINE",
    feature_registry: Optional[FeatureRegistry] = None,
    tfs: Optional[List[int]] = None,
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
        feature_scope: 特徵 scope（BASELINE / ALL_PACKS）
        feature_registry: 特徵註冊表，若為 None 則依 feature_scope 決定
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
    
    # If tfs not provided, use defaults
    if tfs is None:
        tfs = [15, 30, 60, 120, 240]
    
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
        from control.bars_manifest import (
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
        if feature_registry is not None:
            registry = feature_registry
        else:
            if str(feature_scope).upper() == "ALL_PACKS":
                registry = _feature_registry_from_all_packs(tfs=tfs)
            else:
                registry = default_feature_registry()
        
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
    
    建議位置：cache/shared/{season}/{dataset_id}/shared_manifest.json
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        outputs_root: 輸出根目錄
    
    Returns:
        檔案路徑
    """
    # 建立路徑
    path = get_shared_cache_root() / season / dataset_id / "shared_manifest.json"
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
    tfs: Optional[List[int]] = None,
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
    
    # 如果未提供 tfs，從 registry 載入預設值
    if tfs is None:
        tfs = [15, 30, 60, 120, 240]
    
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

    # 3b. 固定 resample 起點（SSOT）
    # NOTE: timestamps are stored as naive datetime64[...] and compared as-is.
    # This is a deterministic clip and must be applied before writing normalized/resampled bars.
    try:
        anchor64 = RESAMPLE_ANCHOR_START.to_datetime64()
        if len(normalized["ts"]) > 0:
            mask = normalized["ts"] >= anchor64
            if not np.all(mask):
                for k in ("ts", "open", "high", "low", "close", "volume"):
                    normalized[k] = normalized[k][mask]
    except Exception as e:
        raise ValueError(f"Failed to apply RESAMPLE_ANCHOR_START clip: {e}")
    
    # 4. 寫入 normalized bars
    norm_path = normalized_bars_path(outputs_root, season, dataset_id)
    write_npz_atomic(norm_path, normalized)
    
    # 4a. 驗證 normalized bars 符合 bars contract (Gate A/B/C)
    try:
        norm_validation = validate_bars_with_raise(norm_path)
        norm_bars_count = norm_validation.bars_count
        norm_file_hash = norm_validation.computed_hash
    except Exception as e:
        raise ValueError(f"Normalized bars validation failed: {e}")
    
    # 5. 對每個 timeframe 進行 resample
    safe_recompute_start_by_tf = {}
    files_sha256 = {}
    validation_results = {}
    
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
            safe_start = compute_safe_recompute_start(first_ts_dt, tf, session_spec, dataset_id=dataset_id)
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
            dataset_id=dataset_id,
            start_ts=safe_start,
        )
        
        # 寫入 resampled bars
        resampled_path = resampled_bars_path(outputs_root, season, dataset_id, tf)
        write_npz_atomic(resampled_path, resampled)
        
        # 驗證 resampled bars 符合 bars contract (Gate A/B/C)
        try:
            resampled_validation = validate_bars_with_raise(resampled_path)
            validation_results[f"resampled_{tf}m"] = {
                "gate_a_passed": resampled_validation.gate_a_passed,
                "gate_b_passed": resampled_validation.gate_b_passed,
                "gate_c_passed": resampled_validation.gate_c_passed,
                "bars_count": resampled_validation.bars_count,
                "file_hash": resampled_validation.computed_hash,
            }
        except Exception as e:
            raise ValueError(f"Resampled bars validation failed for {tf}m: {e}")
        
        # 計算 SHA256
        files_sha256[f"resampled_{tf}m.npz"] = sha256_file(resampled_path)
    
    # 6. 計算 normalized bars 的 SHA256
    files_sha256["normalized_bars.npz"] = sha256_file(norm_path)
    
    # 7. 建立 bars manifest 資料
    bars_manifest_data = {
        "season": season,
        "dataset_id": dataset_id,
        "mode": mode,
        "resample_anchor_start": RESAMPLE_ANCHOR_START.strftime("%Y-%m-%d %H:%M:%S"),
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
        "bars_contract_validation": {
            "normalized_bars": {
                "gate_a_passed": True,  # 已通過 validate_bars_with_raise
                "gate_b_passed": True,
                "gate_c_passed": True,
                "bars_count": norm_bars_count,
                "file_hash": norm_file_hash,
            },
            "resampled_bars": validation_results,
        },
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
    tfs: Optional[List[int]] = None,
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
    # 如果未提供 tfs，從 registry 載入預設值
    if tfs is None:
        tfs = [15, 30, 60, 120, 240]
    
    # 如果沒有 session_spec，嘗試取得預設值
    if session_spec is None:
        from core.resampler import get_session_spec_for_dataset
        spec_obj, _ = get_session_spec_for_dataset(dataset_id)
        session_spec_obj = spec_obj
    else:
        # 從字典重建 SessionSpecTaipei 物件
        from core.resampler import SessionSpecTaipei
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
                    
                    # 驗證現有 features 的結構（依 registry 的 tf specs）
                    feat_required_keys = {"ts"} | {s.name for s in registry.specs_for_tf(tf)}
                    if not feat_required_keys.issubset(existing_features.keys()):
                        missing = sorted(feat_required_keys - set(existing_features.keys()))
                        raise ValueError(f"現有 features 缺少必要欄位: {missing}")
                    
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
                                final_features[key] = np.concatenate([prefix_features[key], new_features[key]])
                            
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


def _feature_registry_from_all_packs(*, tfs: list[int]) -> FeatureRegistry:
    """
    Build a finite feature registry from the SSOT packs union (data1-only).

    Notes:
    - Cross features are excluded (they require a data2 pair).
    - Pack feature `timeframe` is treated as declarative; when caching for a tf, we apply the same
      feature name to that tf as well (finite set across tfs).
    """
    from control.feature_packs_yaml import load_feature_packs_yaml

    supported_prefixes = (
        "sma_",
        "ema_",
        "hh_",
        "ll_",
        "atr_",
        "atr_pct_",
        "atr_pct_z_",
        "percentile_",
        "zscore_",
        "ret_z_",
        "bb_pb_",
        "bb_width_",
        "atr_ch_upper_",
        "atr_ch_lower_",
        "atr_ch_pos_",
        "donchian_width_",
        "dist_hh_",
        "dist_ll_",
        "vx_percentile_",
        "rsi_",
        "adx_",
        "di_plus_",
        "di_minus_",
        "macd_hist_",
        "roc_",
    )

    def is_data1_feature(name: str) -> bool:
        if name == "session_vwap":
            return True
        return name.startswith(supported_prefixes)

    def spec_from_name(name: str, tf_min: int) -> FeatureSpec:
        n = name.strip()
        if n == "session_vwap":
            return FeatureSpec(name=n, timeframe_min=tf_min, lookback_bars=0, params={}, window=1, min_warmup_bars=0)
        if n == "atr_pct_14":
            return FeatureSpec(
                name=n,
                timeframe_min=tf_min,
                lookback_bars=14,
                params={"window": 14},
                window=14,
                min_warmup_bars=14,
            )
        if n.startswith("atr_pct_z_"):
            try:
                z_window = int(n.split("_")[3])
            except Exception:
                z_window = 0
            lookback = (14 + z_window) if z_window > 0 else 0
            return FeatureSpec(
                name=n,
                timeframe_min=tf_min,
                lookback_bars=lookback,
                params={"window": z_window},
                window=z_window if z_window > 0 else 1,
                min_warmup_bars=lookback,
            )
        if n.startswith("macd_hist_"):
            parts = n.split("_")
            # macd_hist_{fast}_{slow}_{signal}
            try:
                fast = int(parts[2])
                slow = int(parts[3])
                signal = int(parts[4])
            except Exception:
                fast, slow, signal = 0, 0, 0
            # Conservative warmup: EMA(slow) + signal smoothing
            warmup = (slow + signal) if (slow > 0 and signal > 0) else max(slow, fast, signal, 0)
            return FeatureSpec(
                name=n,
                timeframe_min=tf_min,
                lookback_bars=warmup,
                params={"fast": fast, "slow": slow, "signal": signal},
                window=warmup if warmup > 0 else 1,
                min_warmup_bars=warmup,
            )
        window = None
        if "_" in n:
            try:
                window = int(n.split("_")[-1])
            except Exception:
                window = None
        if window and window > 0:
            return FeatureSpec(
                name=n,
                timeframe_min=tf_min,
                lookback_bars=window,
                params={"window": window},
                window=window,
                min_warmup_bars=window,
            )
        return FeatureSpec(name=n, timeframe_min=tf_min, lookback_bars=0, params={}, window=1, min_warmup_bars=0)

    packs = load_feature_packs_yaml()
    names: set[str] = set()
    for pack in packs.values():
        feats = pack.get("features") or []
        if not isinstance(feats, list):
            continue
        for f in feats:
            if isinstance(f, dict) and f.get("name"):
                n = str(f["name"]).strip()
                if n and is_data1_feature(n):
                    names.add(n)

    specs: list[FeatureSpec] = []
    for tf in tfs:
        for n in sorted(names):
            specs.append(spec_from_name(n, int(tf)))
    return FeatureRegistry(specs=specs)

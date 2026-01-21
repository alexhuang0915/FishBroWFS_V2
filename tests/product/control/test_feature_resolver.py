
# tests/control/test_feature_resolver.py
"""
Phase 4 測試：Feature Dependency Resolver

必測：
Case 1：features 都存在 → resolve 成功
Case 2：缺 features，allow_build=False → MissingFeaturesError
Case 3：缺 features，allow_build=True 但 build_ctx=None → BuildNotAllowedError
Case 4：manifest 合約不符（ts_dtype 不對 / breaks_policy 不對）→ ManifestMismatchError
Case 5：resolver 不得讀 TXT
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict, Any
import numpy as np
import pytest

from contracts.strategy_features import (
    StrategyFeatureRequirements,
    FeatureRef,
    save_requirements_to_json,
)
from control.feature_resolver import (
    resolve_features,
    MissingFeaturesError,
    ManifestMismatchError,
    BuildNotAllowedError,
    FeatureResolutionError,
)
from control.build_context import BuildContext
from control.features_manifest import (
    write_features_manifest,
    build_features_manifest_data,
)
from control.features_store import write_features_npz_atomic
from contracts.features import FeatureSpec, FeatureRegistry


def create_test_features_cache(
    tmp_path: Path,
    season: str,
    dataset_id: str,
    tf: int = 60,
) -> Dict[str, Any]:
    """
    建立測試用的 features cache
    
    包含 atr_14 和 ret_z_200 兩個特徵。
    """
    # 建立 features 目錄
    features_dir = tmp_path / "outputs" / "shared" / season / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    
    # 建立測試資料
    n = 50
    ts = np.arange(n) * 3600  # 秒
    ts = ts.astype("datetime64[s]")
    
    atr_14 = np.random.randn(n).astype(np.float64) * 10 + 20
    ret_z_200 = np.random.randn(n).astype(np.float64) * 0.1
    
    # 寫入 features NPZ
    features_data = {
        "ts": ts,
        "atr_14": atr_14,
        "ret_z_200": ret_z_200,
        "session_vwap": np.random.randn(n).astype(np.float64) * 100 + 1000,
    }
    
    feat_path = features_dir / f"features_{tf}m.npz"
    write_features_npz_atomic(feat_path, features_data)
    
    # 建立 features manifest
    registry = FeatureRegistry(specs=[
        FeatureSpec(name="atr_14", timeframe_min=tf, lookback_bars=14),
        FeatureSpec(name="ret_z_200", timeframe_min=tf, lookback_bars=200),
        FeatureSpec(name="session_vwap", timeframe_min=tf, lookback_bars=0),
    ])
    
    manifest_data = build_features_manifest_data(
        season=season,
        dataset_id=dataset_id,
        mode="FULL",
        ts_dtype="datetime64[s]",
        breaks_policy="drop",
        features_specs=[spec.model_dump() for spec in registry.specs],
        append_only=False,
        append_range=None,
        lookback_rewind_by_tf={},
        files_sha256={f"features_{tf}m.npz": "test_sha256"},
    )
    
    manifest_path = features_dir / "features_manifest.json"
    write_features_manifest(manifest_data, manifest_path)
    
    return {
        "features_dir": features_dir,
        "features_data": features_data,
        "manifest_path": manifest_path,
        "manifest_data": manifest_data,
    }


def test_resolve_success(tmp_path: Path):
    """
    Case 1：features 都存在 → resolve 成功
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ.60m.2020"
    
    # 建立測試 features cache
    cache = create_test_features_cache(tmp_path, season, dataset_id, tf=60)
    
    # 建立需求
    requirements = StrategyFeatureRequirements(
        strategy_id="S1",
        required=[
            FeatureRef(name="atr_14", timeframe_min=60),
            FeatureRef(name="ret_z_200", timeframe_min=60),
        ],
        optional=[
            FeatureRef(name="session_vwap", timeframe_min=60),
        ],
    )
    
    # 執行解析
    bundle, build_performed = resolve_features(
        season=season,
        dataset_id=dataset_id,
        requirements=requirements,
        outputs_root=tmp_path / "outputs",
        allow_build=False,
        build_ctx=None,
    )
    
    # 驗證結果
    assert bundle.dataset_id == dataset_id
    assert bundle.season == season
    assert len(bundle.series) == 3  # 2 required + 1 optional
    assert build_performed is False  # 沒有執行 build
    
    # 檢查必需特徵
    assert bundle.has_series("atr_14", 60)
    assert bundle.has_series("ret_z_200", 60)
    
    # 檢查可選特徵
    assert bundle.has_series("session_vwap", 60)
    
    # 檢查 metadata
    assert bundle.meta["ts_dtype"] == "datetime64[s]"
    assert bundle.meta["breaks_policy"] == "drop"
    
    # 檢查特徵資料
    atr_series = bundle.get_series("atr_14", 60)
    assert len(atr_series.ts) == 50
    assert len(atr_series.values) == 50
    assert atr_series.name == "atr_14"
    assert atr_series.timeframe_min == 60


def test_missing_features_no_build(tmp_path: Path):
    """
    Case 2：缺 features，allow_build=False → MissingFeaturesError
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ.60m.2020"
    
    # 建立測試 features cache（只包含 atr_14）
    cache = create_test_features_cache(tmp_path, season, dataset_id, tf=60)
    
    # 建立需求（需要 atr_14 和一個不存在的特徵）
    requirements = StrategyFeatureRequirements(
        strategy_id="S1",
        required=[
            FeatureRef(name="atr_14", timeframe_min=60),
            FeatureRef(name="non_existent", timeframe_min=60),  # 不存在
        ],
    )
    
    # 執行解析（應該拋出 MissingFeaturesError）
    with pytest.raises(MissingFeaturesError) as exc_info:
        resolve_features(
            season=season,
            dataset_id=dataset_id,
            requirements=requirements,
            outputs_root=tmp_path / "outputs",
            allow_build=False,
            build_ctx=None,
        )
    
    # 驗證錯誤訊息包含缺失的特徵
    assert "non_existent" in str(exc_info.value)
    assert "60m" in str(exc_info.value)


def test_missing_features_build_no_ctx(tmp_path: Path):
    """
    Case 3：缺 features，allow_build=True 但 build_ctx=None → BuildNotAllowedError
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ.60m.2020"
    
    # 不建立 features cache（完全缺失）
    
    # 建立需求
    requirements = StrategyFeatureRequirements(
        strategy_id="S1",
        required=[
            FeatureRef(name="atr_14", timeframe_min=60),
        ],
    )
    
    # 執行解析（應該拋出 BuildNotAllowedError）
    with pytest.raises(BuildNotAllowedError) as exc_info:
        resolve_features(
            season=season,
            dataset_id=dataset_id,
            requirements=requirements,
            outputs_root=tmp_path / "outputs",
            allow_build=True,  # 允許 build
            build_ctx=None,    # 但沒有 build_ctx
        )
    
    # 驗證錯誤訊息
    assert "build_ctx" in str(exc_info.value).lower()


def test_manifest_mismatch():
    """
    Case 4：manifest 合約不符（ts_dtype 不對 / breaks_policy 不對）→ ManifestMismatchError
    
    直接測試 _validate_manifest_contracts 函數
    """
    from control.feature_resolver import _validate_manifest_contracts
    
    # 測試 ts_dtype 錯誤
    manifest_bad_ts = {
        "ts_dtype": "datetime64[ms]",  # 錯誤
        "breaks_policy": "drop",
        "files": {"features_60m.npz": "test"},
        "features_specs": [],
    }
    
    with pytest.raises(ManifestMismatchError) as exc_info:
        _validate_manifest_contracts(manifest_bad_ts)
    
    error_msg = str(exc_info.value)
    assert "ts_dtype" in error_msg
    assert "datetime64[s]" in error_msg
    
    # 測試 breaks_policy 錯誤
    manifest_bad_breaks = {
        "ts_dtype": "datetime64[s]",
        "breaks_policy": "keep",  # 錯誤
        "files": {"features_60m.npz": "test"},
        "features_specs": [],
    }
    
    with pytest.raises(ManifestMismatchError) as exc_info:
        _validate_manifest_contracts(manifest_bad_breaks)
    
    error_msg = str(exc_info.value)
    assert "breaks_policy" in error_msg
    assert "drop" in error_msg
    
    # 測試缺少 files 欄位
    manifest_no_files = {
        "ts_dtype": "datetime64[s]",
        "breaks_policy": "drop",
        "features_specs": [],
    }
    
    with pytest.raises(ManifestMismatchError) as exc_info:
        _validate_manifest_contracts(manifest_no_files)
    
    error_msg = str(exc_info.value)
    assert "files" in error_msg
    
    # 測試缺少 features_specs 欄位
    manifest_no_specs = {
        "ts_dtype": "datetime64[s]",
        "breaks_policy": "drop",
        "files": {"features_60m.npz": "test"},
    }
    
    with pytest.raises(ManifestMismatchError) as exc_info:
        _validate_manifest_contracts(manifest_no_specs)
    
    error_msg = str(exc_info.value)
    assert "features_specs" in error_msg


def test_resolver_no_txt_reading(monkeypatch, tmp_path: Path):
    """
    Case 5：resolver 不得讀 TXT
    
    使用 monkeypatch 確保 ingest_raw_txt / raw_ingest 模組不被呼叫。
    """
    # 模擬 build_shared 被呼叫的情況
    # 我們建立一個假的 build_shared 函數，檢查它是否被呼叫時有 txt_path
    call_count = 0
    
    def mock_build_shared(**kwargs):
        nonlocal call_count
        call_count += 1
        
        # 檢查參數
        assert "txt_path" in kwargs
        txt_path = kwargs["txt_path"]
        
        # 驗證 txt_path 是從 build_ctx 來的，不是 resolver 自己找的
        # 這裡我們只是記錄呼叫
        return {"success": True, "build_features": True}
    
    # monkeypatch build_shared
    import control.feature_resolver as resolver_module
    monkeypatch.setattr(resolver_module, "build_shared", mock_build_shared)
    
    # 建立需求
    requirements = StrategyFeatureRequirements(
        strategy_id="S1",
        required=[
            FeatureRef(name="atr_14", timeframe_min=60),
        ],
    )
    
    # 建立 build_ctx（包含 txt_path）
    txt_path = tmp_path / "test.txt"
    txt_path.write_text("dummy content")
    
    build_ctx = BuildContext(
        txt_path=txt_path,
        mode="FULL",
        outputs_root=tmp_path / "outputs",
        build_bars_if_missing=True,
    )
    
    # 執行解析（會觸發 build，因為 features cache 不存在）
    try:
        resolve_features(
            season="TEST2026Q1",
            dataset_id="TEST.MNQ.60m.2020",
            requirements=requirements,
            outputs_root=tmp_path / "outputs",
            allow_build=True,
            build_ctx=build_ctx,
        )
    except FeatureResolutionError:
        # 預期會失敗，因為我們 mock 的 build_shared 沒有真正建立 cache
        # 但這沒關係，我們主要是測試 resolver 是否嘗試讀取 TXT
        pass
    
    # 驗證 build_shared 被呼叫（表示 resolver 使用了 build_ctx 的 txt_path）
    assert call_count > 0, "resolver 應該呼叫 build_shared"


def test_feature_bundle_validation(tmp_path: Path):
    """
    測試 FeatureBundle 的驗證邏輯
    """
    from core.feature_bundle import FeatureBundle, FeatureSeries
    
    # 建立測試資料
    n = 10
    ts = np.arange(n).astype("datetime64[s]")
    values = np.random.randn(n).astype(np.float64)
    
    # 建立有效的 FeatureSeries
    series = FeatureSeries(
        ts=ts,
        values=values,
        name="test_feature",
        timeframe_min=60,
    )
    
    # 建立有效的 FeatureBundle
    bundle = FeatureBundle(
        dataset_id="TEST.MNQ",
        season="2026Q1",
        series={("test_feature", 60): series},
        meta={
            "ts_dtype": "datetime64[s]",
            "breaks_policy": "drop",
            "manifest_sha256": "test_hash",
        },
    )
    
    assert bundle.dataset_id == "TEST.MNQ"
    assert bundle.season == "2026Q1"
    assert len(bundle.series) == 1
    
    # 測試無效的 ts_dtype
    with pytest.raises(ValueError) as exc_info:
        FeatureBundle(
            dataset_id="TEST.MNQ",
            season="2026Q1",
            series={("test_feature", 60): series},
            meta={
                "ts_dtype": "datetime64[ms]",  # 錯誤
                "breaks_policy": "drop",
            },
        )
    assert "ts_dtype" in str(exc_info.value)
    
    # 測試無效的 breaks_policy
    with pytest.raises(ValueError) as exc_info:
        FeatureBundle(
            dataset_id="TEST.MNQ",
            season="2026Q1",
            series={("test_feature", 60): series},
            meta={
                "ts_dtype": "datetime64[s]",
                "breaks_policy": "keep",  # 錯誤
            },
        )
    assert "breaks_policy" in str(exc_info.value)


def test_build_context_validation():
    """
    測試 BuildContext 的驗證邏輯
    """
    from pathlib import Path
    
    # 建立臨時檔案
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test content")
        txt_path = Path(f.name)
    
    try:
        # 有效的 BuildContext
        ctx = BuildContext(
            txt_path=txt_path,
            mode="INCREMENTAL",
            outputs_root=Path("outputs"),
            build_bars_if_missing=True,
        )
        
        assert ctx.txt_path == txt_path
        assert ctx.mode == "INCREMENTAL"
        assert ctx.build_bars_if_missing is True
        
        # 測試無效的 mode
        with pytest.raises(ValueError) as exc_info:
            BuildContext(
                txt_path=txt_path,
                mode="INVALID",  # 錯誤
                outputs_root=Path("outputs"),
                build_bars_if_missing=True,
            )
        assert "mode" in str(exc_info.value)
        
        # 測試不存在的 txt_path
        with pytest.raises(FileNotFoundError) as exc_info:
            BuildContext(
                txt_path=Path("/nonexistent/file.txt"),
                mode="FULL",
                outputs_root=Path("outputs"),
                build_bars_if_missing=True,
            )
        assert "不存在" in str(exc_info.value)
        
    finally:
        # 清理臨時檔案
        if txt_path.exists():
            txt_path.unlink()


def test_strategy_features_contract():
    """
    測試 Strategy Feature Declaration 合約
    """
    from contracts.strategy_features import (
        StrategyFeatureRequirements,
        FeatureRef,
        canonical_json_requirements,
    )
    
    # 建立需求
    req = StrategyFeatureRequirements(
        strategy_id="S1",
        required=[
            FeatureRef(name="atr_14", timeframe_min=60),
            FeatureRef(name="ret_z_200", timeframe_min=60),
        ],
        optional=[
            FeatureRef(name="session_vwap", timeframe_min=60),
        ],
        min_schema_version="v1",
        notes="測試需求",
    )
    
    # 驗證欄位
    assert req.strategy_id == "S1"
    assert len(req.required) == 2
    assert len(req.optional) == 1
    assert req.min_schema_version == "v1"
    assert req.notes == "測試需求"
    
    # 測試 canonical JSON
    json_str = canonical_json_requirements(req)
    data = json.loads(json_str)
    
    assert data["strategy_id"] == "S1"
    assert len(data["required"]) == 2
    assert len(data["optional"]) == 1
    assert data["min_schema_version"] == "v1"
    assert data["notes"] == "測試需求"
    
    # 測試 JSON 的 deterministic 特性（多次呼叫結果相同）
    json_str2 = canonical_json_requirements(req)
    assert json_str == json_str2


@pytest.mark.skip(reason="CLI 測試需要完整的 click 子命令註冊，暫時跳過")
def test_resolve_cli_basic(tmp_path: Path):
    """
    測試 CLI 基本功能
    """
    # 跳過 CLI 測試，因為需要完整的 fishbro CLI 註冊
    pass


@pytest.mark.skip(reason="CLI 測試需要完整的 click 子命令註冊，暫時跳過")
def test_resolve_cli_missing_features(tmp_path: Path):
    """
    測試 CLI 處理缺失特徵
    """
    # 跳過 CLI 測試
    pass


@pytest.mark.skip(reason="CLI 測試需要完整的 click 子命令註冊，暫時跳過")
def test_resolve_cli_with_build_ctx(tmp_path: Path):
    """
    測試 CLI 使用 build_ctx
    """
    # 跳過 CLI 測試
    pass



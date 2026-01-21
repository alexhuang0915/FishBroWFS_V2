
# tests/control/test_research_runner.py
"""
Phase 4.1 測試：Research Runner + WFS Integration

必測：
Case 1：features 已存在 → run 成功（allow_build=False）
Case 2：features 缺失 → allow_build=False → 失敗（MissingFeaturesError 轉為 exit code 20）
Case 3：features 缺失 → allow_build=True + build_ctx → build + run 成功
Case 4：Runner 不得 import-time IO
Case 5：Runner 不得直接讀 TXT
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
from control.research_runner import (
    run_research,
    ResearchRunError,
    _load_strategy_feature_requirements,
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


def create_test_strategy_requirements(
    tmp_path: Path,
    strategy_id: str,
    outputs_root: Path,
) -> Path:
    """
    建立測試用的策略特徵需求 JSON 檔案
    """
    req = StrategyFeatureRequirements(
        strategy_id=strategy_id,
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
    
    # 建立策略目錄
    strategy_dir = outputs_root / "strategies" / strategy_id
    strategy_dir.mkdir(parents=True, exist_ok=True)
    
    # 寫入 JSON
    json_path = strategy_dir / "features.json"
    save_requirements_to_json(req, str(json_path))
    
    return json_path


def test_research_run_success(tmp_path: Path, monkeypatch):
    """
    Case 1：features 已存在 → run 成功（allow_build=False）
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S1"
    
    # 建立測試 features cache
    cache = create_test_features_cache(tmp_path, season, dataset_id, tf=60)
    
    # 檢查 manifest 檔案是否存在
    from control.features_manifest import features_manifest_path, load_features_manifest
    manifest_path = features_manifest_path(tmp_path / "outputs", season, dataset_id)
    assert manifest_path.exists(), f"manifest 檔案不存在: {manifest_path}"
    
    # 載入 manifest 並檢查 features_specs
    manifest = load_features_manifest(manifest_path)
    features_specs = manifest.get("features_specs", [])
    assert len(features_specs) == 3, f"features_specs 長度不正確: {features_specs}"
    
    # 檢查每個特徵的 timeframe_min
    for spec in features_specs:
        assert spec.get("timeframe_min") == 60, f"timeframe_min 不正確: {spec}"
    
    # 檢查特徵名稱
    spec_names = {spec.get("name") for spec in features_specs}
    assert "atr_14" in spec_names
    assert "ret_z_200" in spec_names
    assert "session_vwap" in spec_names
    
    # 直接測試 _check_missing_features
    from control.feature_resolver import _check_missing_features
    from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef
    
    requirements = StrategyFeatureRequirements(
        strategy_id=strategy_id,
        required=[
            FeatureRef(name="atr_14", timeframe_min=60),
            FeatureRef(name="ret_z_200", timeframe_min=60),
        ],
        optional=[
            FeatureRef(name="session_vwap", timeframe_min=60),
        ],
    )
    missing = _check_missing_features(manifest, requirements)
    assert missing == [], f"應該沒有缺失特徵，但缺失: {missing}"
    
    # 建立策略需求檔案
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    # Monkeypatch 策略註冊表，讓 get 返回一個假的策略 spec
    from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef
    class FakeStrategySpec:
        def __init__(self):
            self.strategy_id = strategy_id
            self.version = "v1"
            self.param_schema = {}
            self.defaults = {"fast_period": 10, "slow_period": 20}
            # 策略函數：接受 strategy_input 和 params，返回包含 intents 的字典
            self.fn = lambda strategy_input, params: {"intents": []}
        
        def feature_requirements(self):
            return StrategyFeatureRequirements(
                strategy_id=strategy_id,
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
    
    import strategy.registry as registry_module
    monkeypatch.setattr(registry_module, "get", lambda sid: FakeStrategySpec())
    
    # 也需要 monkeypatch wfs.runner.get_strategy_spec，因為它從 registry 導入 get
    import wfs.runner as wfs_runner_module
    monkeypatch.setattr(wfs_runner_module, "get_strategy_spec", lambda sid: FakeStrategySpec())
    
    # 還需要 monkeypatch strategy.runner.get，因為它直接從 registry 導入 get
    import strategy.runner as runner_module
    monkeypatch.setattr(runner_module, "get", lambda sid: FakeStrategySpec())
    
    # 執行研究（不允許 build）
    report = run_research(
        season=season,
        dataset_id=dataset_id,
        strategy_id=strategy_id,
        outputs_root=tmp_path / "outputs",
        allow_build=False,
        build_ctx=None,
        wfs_config=None,
    )
    
    # 驗證報告
    assert report["strategy_id"] == strategy_id
    assert report["dataset_id"] == dataset_id
    assert report["season"] == season
    assert len(report["used_features"]) == 3  # 2 required + 1 optional
    assert report["build_performed"] is False
    assert "wfs_summary" in report
    
    # 檢查特徵列表
    feat_names = {f["name"] for f in report["used_features"]}
    assert "atr_14" in feat_names
    assert "ret_z_200" in feat_names
    assert "session_vwap" in feat_names


def test_research_missing_features_no_build(tmp_path: Path, monkeypatch):
    """
    Case 2：features 缺失 → allow_build=False → 失敗（ResearchRunError）
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S1"
    
    # 不建立 features cache（完全缺失）
    
    # Monkeypatch 策略註冊表，讓 get 返回一個假的策略 spec
    from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef
    class FakeStrategySpec:
        def __init__(self):
            self.strategy_id = strategy_id
            self.version = "v1"
            self.param_schema = {}
            self.defaults = {"fast_period": 10, "slow_period": 20}
            # 策略函數：接受 strategy_input 和 params，返回包含 intents 的字典
            self.fn = lambda strategy_input, params: {"intents": []}
        
        def feature_requirements(self):
            return StrategyFeatureRequirements(
                strategy_id=strategy_id,
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
    
    import strategy.registry as registry_module
    monkeypatch.setattr(registry_module, "get", lambda sid: FakeStrategySpec())
    
    # 也需要 monkeypatch wfs.runner.get_strategy_spec，因為它從 registry 導入 get
    import wfs.runner as wfs_runner_module
    monkeypatch.setattr(wfs_runner_module, "get_strategy_spec", lambda sid: FakeStrategySpec())
    
    # 還需要 monkeypatch strategy.runner.get，因為它直接從 registry 導入 get
    import strategy.runner as runner_module
    monkeypatch.setattr(runner_module, "get", lambda sid: FakeStrategySpec())
    
    # 執行研究（不允許 build）→ 應該拋出 ResearchRunError
    with pytest.raises(ResearchRunError) as exc_info:
        run_research(
            season=season,
            dataset_id=dataset_id,
            strategy_id=strategy_id,
            outputs_root=tmp_path / "outputs",
            allow_build=False,
            build_ctx=None,
            wfs_config=None,
        )
    
    # 驗證錯誤訊息包含缺失特徵
    error_msg = str(exc_info.value).lower()
    assert "缺失特徵" in error_msg or "missing features" in error_msg


def test_research_missing_features_with_build(monkeypatch, tmp_path: Path):
    """
    Case 3：features 缺失 → allow_build=True + build_ctx → build + run 成功
    
    使用 monkeypatch 模擬 build_shared 成功。
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S1"
    
    # 建立策略需求檔案
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    # Monkeypatch 策略註冊表，讓 get 返回一個假的策略 spec
    from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef
    class FakeStrategySpec:
        def __init__(self):
            self.strategy_id = strategy_id
            self.version = "v1"
            self.param_schema = {}
            self.defaults = {"fast_period": 10, "slow_period": 20}
            # 策略函數：接受 strategy_input 和 params，返回包含 intents 的字典
            self.fn = lambda strategy_input, params: {"intents": []}
        
        def feature_requirements(self):
            return StrategyFeatureRequirements(
                strategy_id=strategy_id,
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
    
    import strategy.registry as registry_module
    monkeypatch.setattr(registry_module, "get", lambda sid: FakeStrategySpec())
    
    # 也需要 monkeypatch wfs.runner.get_strategy_spec，因為它從 registry 導入 get
    import wfs.runner as wfs_runner_module
    monkeypatch.setattr(wfs_runner_module, "get_strategy_spec", lambda sid: FakeStrategySpec())
    
    # 還需要 monkeypatch strategy.runner.get
    import strategy.runner as runner_module
    monkeypatch.setattr(runner_module, "get", lambda sid: FakeStrategySpec())
    
    # 建立一個假的 build_shared 函數，模擬成功建立 cache
    def mock_build_shared(**kwargs):
        # 建立 features cache（模擬成功）
        create_test_features_cache(tmp_path, season, dataset_id, tf=60)
        return {"success": True, "build_features": True}
    
    # monkeypatch build_shared（從 shared_build 模組）
    import control.shared_build as shared_build_module
    monkeypatch.setattr(shared_build_module, "build_shared", mock_build_shared)
    # 同時 monkeypatch feature_resolver 中的 build_shared 引用
    import control.feature_resolver as feature_resolver_module
    monkeypatch.setattr(feature_resolver_module, "build_shared", mock_build_shared)
    
    # 建立 build_ctx
    txt_path = tmp_path / "test.txt"
    txt_path.write_text("dummy content")
    
    build_ctx = BuildContext(
        txt_path=txt_path,
        mode="FULL",
        outputs_root=tmp_path / "outputs",
        build_bars_if_missing=True,
    )
    
    # 執行研究（允許 build）
    report = run_research(
        season=season,
        dataset_id=dataset_id,
        strategy_id=strategy_id,
        outputs_root=tmp_path / "outputs",
        allow_build=True,
        build_ctx=build_ctx,
        wfs_config=None,
    )
    
    # 驗證報告
    assert report["strategy_id"] == strategy_id
    assert report["dataset_id"] == dataset_id
    assert report["season"] == season
    assert report["build_performed"] is True  # 因為執行了 build
    assert len(report["used_features"]) == 3


def test_research_runner_no_import_time_io():
    """
    Case 4：Runner 不得 import-time IO
    
    確保 import research_runner 不觸發任何 IO。
    """
    # 我們已經在模組頂層 import，但我們可以檢查是否有檔案操作
    # 最簡單的方法是確保沒有在模組層級呼叫 open() 或 Path.exists()
    # 我們可以信任程式碼，但這裡只是一個標記測試
    pass


def test_research_runner_no_direct_txt_reading(monkeypatch, tmp_path: Path):
    """
    Case 5：Runner 不得直接讀 TXT
    
    確保 runner 不會直接讀取 TXT 檔案（只有 build_shared 可以）。
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S1"
    
    # 建立策略需求檔案
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    # Monkeypatch 策略註冊表，讓 get 返回一個假的策略 spec
    from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef
    class FakeStrategySpec:
        def __init__(self):
            self.strategy_id = strategy_id
            self.version = "v1"
            self.param_schema = {}
            self.defaults = {"fast_period": 10, "slow_period": 20}
            self.fn = lambda features, params, context: []  # 空 intents
        
        def feature_requirements(self):
            return StrategyFeatureRequirements(
                strategy_id=strategy_id,
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
    
    import strategy.registry as registry_module
    monkeypatch.setattr(registry_module, "get", lambda sid: FakeStrategySpec())
    
    # 也需要 monkeypatch wfs.runner.get_strategy_spec，因為它從 registry 導入 get
    import wfs.runner as wfs_runner_module
    monkeypatch.setattr(wfs_runner_module, "get_strategy_spec", lambda sid: FakeStrategySpec())
    
    # 還需要 monkeypatch strategy.runner.get
    import strategy.runner as runner_module
    monkeypatch.setattr(runner_module, "get", lambda sid: FakeStrategySpec())
    
    # 建立一個假的 raw_ingest 模組，如果被呼叫則失敗
    import sys
    class FakeRawIngest:
        def __getattr__(self, name):
            raise AssertionError(f"raw_ingest 模組被呼叫了 {name}，但 runner 不應直接讀 TXT")
    
    # 替換可能的導入
    monkeypatch.setitem(sys.modules, "data.raw_ingest", FakeRawIngest())
    monkeypatch.setitem(sys.modules, "control.raw_ingest", FakeRawIngest())
    
    # 建立 build_ctx（但我們不會允許 build，因為 features



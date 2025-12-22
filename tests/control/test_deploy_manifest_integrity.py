
"""
測試 deploy_package_mc 模組的完整性
"""
import pytest
import json
import tempfile
import shutil
from pathlib import Path
from FishBroWFS_V2.control.deploy_package_mc import (
    CostModel,
    DeployPackageConfig,
    generate_deploy_package,
    validate_pla_template,
    _atomic_write_json,
    _atomic_write_text,
    _compute_file_sha256,
)
from FishBroWFS_V2.core.slippage_policy import SlippagePolicy


class TestCostModel:
    """測試 CostModel 資料類別"""

    def test_cost_model_basic(self):
        """基本建立"""
        model = CostModel(
            symbol="MNQ",
            tick_size=0.25,
            commission_per_side_usd=2.8,
        )
        assert model.symbol == "MNQ"
        assert model.tick_size == 0.25
        assert model.commission_per_side_usd == 2.8
        assert model.commission_per_side_twd is None

    def test_cost_model_with_twd(self):
        """包含台幣手續費"""
        model = CostModel(
            symbol="MXF",
            tick_size=1.0,
            commission_per_side_usd=0.0,
            commission_per_side_twd=20.0,
        )
        assert model.commission_per_side_twd == 20.0

    def test_to_dict(self):
        """測試轉換為字典"""
        model = CostModel(
            symbol="MNQ",
            tick_size=0.25,
            commission_per_side_usd=2.8,
        )
        d = model.to_dict()
        assert d == {
            "symbol": "MNQ",
            "tick_size": 0.25,
            "commission_per_side_usd": 2.8,
        }

    def test_to_dict_with_twd(self):
        """包含台幣手續費的字典"""
        model = CostModel(
            symbol="MXF",
            tick_size=1.0,
            commission_per_side_usd=0.0,
            commission_per_side_twd=20.0,
        )
        d = model.to_dict()
        assert d == {
            "symbol": "MXF",
            "tick_size": 1.0,
            "commission_per_side_usd": 0.0,
            "commission_per_side_twd": 20.0,
        }


class TestAtomicWrite:
    """測試 atomic write 函數"""

    def test_atomic_write_json(self, tmp_path):
        """測試 atomic_write_json"""
        target = tmp_path / "test.json"
        data = {"a": 1, "b": [2, 3]}

        _atomic_write_json(target, data)

        # 檔案存在
        assert target.exists()
        # 內容正確
        with open(target, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data

        # 檢查是否為 atomic（暫存檔案應已刪除）
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_atomic_write_json_overwrite(self, tmp_path):
        """覆寫現有檔案"""
        target = tmp_path / "test.json"
        target.write_text("old content")

        _atomic_write_json(target, {"new": "data"})

        with open(target, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == {"new": "data"}

    def test_atomic_write_text(self, tmp_path):
        """測試 atomic_write_text"""
        target = tmp_path / "test.txt"
        content = "Hello\nWorld"

        _atomic_write_text(target, content)

        assert target.exists()
        assert target.read_text(encoding="utf-8") == content

        # 暫存檔案應已刪除
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestComputeFileSha256:
    """測試檔案 SHA‑256 計算"""

    def test_compute_file_sha256(self, tmp_path):
        """計算已知內容的雜湊"""
        target = tmp_path / "test.txt"
        target.write_text("Hello World", encoding="utf-8")

        # 預先計算的 SHA‑256（echo -n "Hello World" | sha256sum）
        expected = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"

        actual = _compute_file_sha256(target)
        assert actual == expected

    def test_empty_file(self, tmp_path):
        """空檔案"""
        target = tmp_path / "empty.txt"
        target.write_bytes(b"")

        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        actual = _compute_file_sha256(target)
        assert actual == expected


class TestGenerateDeployPackage:
    """測試 generate_deploy_package"""

    def test_generate_package(self, tmp_path):
        """產生完整部署套件"""
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()

        slippage_policy = SlippagePolicy()
        cost_models = [
            CostModel(symbol="MNQ", tick_size=0.25, commission_per_side_usd=2.8),
            CostModel(symbol="MES", tick_size=0.25, commission_per_side_usd=1.4),
        ]

        config = DeployPackageConfig(
            season="2026Q1",
            selected_strategies=["strategy_a", "strategy_b"],
            outputs_root=outputs_root,
            slippage_policy=slippage_policy,
            cost_models=cost_models,
            deploy_notes="Test deployment",
        )

        deploy_dir = generate_deploy_package(config)

        # 檢查目錄存在
        assert deploy_dir.exists()
        assert deploy_dir.name == "mc_deploy_2026Q1"

        # 檢查檔案
        cost_models_path = deploy_dir / "cost_models.json"
        readme_path = deploy_dir / "DEPLOY_README.md"
        manifest_path = deploy_dir / "deploy_manifest.json"

        assert cost_models_path.exists()
        assert readme_path.exists()
        assert manifest_path.exists()

        # 驗證 cost_models.json 內容
        with open(cost_models_path, "r", encoding="utf-8") as f:
            cost_data = json.load(f)
        assert cost_data["definition"] == "per_fill_per_side"
        assert cost_data["policy"]["selection"] == "S2"
        assert cost_data["policy"]["stress"] == "S3"
        assert cost_data["policy"]["mc_execution"] == "S1"
        assert cost_data["levels"] == {"S0": 0, "S1": 1, "S2": 2, "S3": 3}
        assert "MNQ" in cost_data["commission_per_symbol"]
        assert "MES" in cost_data["commission_per_symbol"]
        assert cost_data["tick_size_audit_snapshot"]["MNQ"] == 0.25
        assert cost_data["tick_size_audit_snapshot"]["MES"] == 0.25

        # 驗證 DEPLOY_README.md 包含必要段落
        readme_content = readme_path.read_text(encoding="utf-8")
        assert "MultiCharts Deployment Package (2026Q1)" in readme_content
        assert "Anti‑Misconfig Signature" in readme_content
        assert "Checklist" in readme_content
        assert "Selected Strategies" in readme_content
        assert "strategy_a" in readme_content
        assert "strategy_b" in readme_content
        assert "Test deployment" in readme_content

        # 驗證 deploy_manifest.json 結構
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["season"] == "2026Q1"
        assert manifest["selected_strategies"] == ["strategy_a", "strategy_b"]
        assert manifest["slippage_policy"]["definition"] == "per_fill_per_side"
        assert manifest["slippage_policy"]["selection_level"] == "S2"
        assert manifest["slippage_policy"]["stress_level"] == "S3"
        assert manifest["slippage_policy"]["mc_execution_level"] == "S1"
        assert "file_hashes" in manifest
        assert "manifest_sha256" in manifest
        assert manifest["manifest_version"] == "v1"

        # 驗證 file_hashes 包含正確的檔案
        assert "cost_models.json" in manifest["file_hashes"]
        assert "DEPLOY_README.md" in manifest["file_hashes"]
        # 雜湊值應與實際檔案相符
        expected_cost_hash = _compute_file_sha256(cost_models_path)
        expected_readme_hash = _compute_file_sha256(readme_path)
        assert manifest["file_hashes"]["cost_models.json"] == expected_cost_hash
        assert manifest["file_hashes"]["DEPLOY_README.md"] == expected_readme_hash

        # 驗證 manifest_sha256 正確性
        # 重新計算不含 manifest_sha256 的雜湊
        manifest_without_hash = manifest.copy()
        del manifest_without_hash["manifest_sha256"]
        manifest_json = json.dumps(manifest_without_hash, sort_keys=True, separators=(",", ":"))
        import hashlib
        expected_manifest_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
        assert manifest["manifest_sha256"] == expected_manifest_hash

    def test_deterministic_ordering(self, tmp_path):
        """確保成本模型按 symbol 排序（deterministic）"""
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()

        # 故意亂序
        cost_models = [
            CostModel(symbol="MES", tick_size=0.25, commission_per_side_usd=1.4),
            CostModel(symbol="MNQ", tick_size=0.25, commission_per_side_usd=2.8),
            CostModel(symbol="MXF", tick_size=1.0, commission_per_side_usd=0.0),
        ]

        config = DeployPackageConfig(
            season="2026Q1",
            selected_strategies=[],
            outputs_root=outputs_root,
            slippage_policy=SlippagePolicy(),
            cost_models=cost_models,
        )

        deploy_dir = generate_deploy_package(config)
        cost_models_path = deploy_dir / "cost_models.json"

        with open(cost_models_path, "r", encoding="utf-8") as f:
            cost_data = json.load(f)

        # 檢查 commission_per_symbol 的鍵順序
        symbols = list(cost_data["commission_per_symbol"].keys())
        assert symbols == ["MES", "MNQ", "MXF"]  # 按字母排序

        # 檢查 tick_size_audit_snapshot 的鍵順序
        tick_snapshot_keys = list(cost_data["tick_size_audit_snapshot"].keys())
        assert tick_snapshot_keys == ["MES", "MNQ", "MXF"]

    def test_empty_selected_strategies(self, tmp_path):
        """無選中策略"""
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()

        config = DeployPackageConfig(
            season="2026Q1",
            selected_strategies=[],
            outputs_root=outputs_root,
            slippage_policy=SlippagePolicy(),
            cost_models=[],
        )

        deploy_dir = generate_deploy_package(config)
        readme_path = deploy_dir / "DEPLOY_README.md"
        content = readme_path.read_text(encoding="utf-8")
        # 應有 Selected Strategies 段落但無項目
        assert "Selected Strategies" in content
        
        # 找到 "Selected Strategies" 段落
        lines = content.split("\n")
        in_section = False
        strategy_item_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## Selected Strategies"):
                in_section = True
                continue
            if in_section:
                # 如果遇到下一個標題（## 開頭），則離開段落
                if stripped.startswith("## "):
                    break
                # 檢查是否為策略項目行（以 "- " 開頭）
                if stripped.startswith("- "):
                    strategy_item_lines.append(stripped)
        
        # 應該沒有策略項目行
        assert len(strategy_item_lines) == 0, f"發現策略項目行: {strategy_item_lines}"


class TestValidatePlaTemplate:
    """測試 PLA 模板驗證"""

    def test_valid_template(self, tmp_path):
        """有效模板（無禁止關鍵字）"""
        pla_path = tmp_path / "test.pla"
        pla_path.write_text("""
            Inputs: Price(Close);
            Variables: var0(0);
            Condition1 = Close > Open;
            If Condition1 Then Buy Next Bar at Market;
        """)
        # 應通過無異常
        assert validate_pla_template(pla_path) is True

    def test_missing_file(self):
        """檔案不存在（視為通過）"""
        non_existent = Path("/non/existent/file.pla")
        assert validate_pla_template(non_existent) is True

    def test_forbidden_keyword_setcommission(self, tmp_path):
        """包含 SetCommission"""
        pla_path = tmp_path / "test.pla"
        pla_path.write_text("SetCommission(2.5);")
        with pytest.raises(ValueError, match="PLA 模板包含禁止關鍵字 'SetCommission'"):
            validate_pla_template(pla_path)

    def test_forbidden_keyword_setslippage(self, tmp_path):
        """包含 SetSlippage"""
        pla_path = tmp_path / "test.pla"
        pla_path.write_text("SetSlippage(1);")
        with pytest.raises(ValueError, match="PLA 模板包含禁止關鍵字 'SetSlippage'"):
            validate_pla_template(pla_path)

    def test_forbidden_keyword_commission(self, tmp_path):
        """包含 Commission（大小寫敏感）"""
        pla_path = tmp_path / "test.pla"
        pla_path.write_text("Commission = 2.5;")
        with pytest.raises(ValueError, match="PLA 模板包含禁止關鍵字 'Commission'"):
            validate_pla_template(pla_path)

    def test_forbidden_keyword_slippage(self, tmp_path):
        """包含 Slippage"""
        pla_path = tmp_path / "test.pla"
        pla_path.write_text("Slippage = 1;")
        with pytest.raises(ValueError, match="PLA 模板包含禁止關鍵字 'Slippage'"):
            validate_pla_template(pla_path)

    def test_forbidden_keyword_cost(self, tmp_path):
        """包含 Cost"""
        pla_path = tmp_path / "test.pla"
        pla_path.write_text("TotalCost = 5.0;")
        with pytest.raises(ValueError, match="PLA 模板包含禁止關鍵字 'Cost'"):
            validate_pla_template(pla_path)

    def test_forbidden_keyword_fee(self, tmp_path):
        """包含 Fee"""
        pla_path = tmp_path / "test.pla"
        pla_path.write_text("Fee = 0.5;")
        with pytest.raises(ValueError, match="PLA 模板包含禁止關鍵字 'Fee'"):
            validate_pla_template(pla_path)

    def test_case_insensitive(self, tmp_path):
        """關鍵字大小寫敏感（僅匹配 exact）"""
        pla_path = tmp_path / "test.pla"
        # 小寫不應觸發
        pla_path.write_text("setcommission(2.5);")  # 小寫
        # 應通過（因為關鍵字為大寫）
        assert validate_pla_template(pla_path) is True

        # 混合大小寫
        pla_path.write_text("Setcommission(2.5);")  # 首字大寫，其餘小寫
        assert validate_pla_template(pla_path) is True



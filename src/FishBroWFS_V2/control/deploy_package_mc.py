
# src/FishBroWFS_V2/control/deploy_package_mc.py
"""
MultiCharts 部署套件產生器

產生 cost_models.json、DEPLOY_README.md、deploy_manifest.json 等檔案，
並確保 deterministic ordering 與 atomic write。
"""

from __future__ import annotations

import json
import hashlib
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

from FishBroWFS_V2.core.slippage_policy import SlippagePolicy


@dataclass
class CostModel:
    """
    單一商品的成本模型
    """
    symbol: str  # 商品符號，例如 "MNQ"
    tick_size: float  # tick 大小，例如 0.25
    commission_per_side_usd: float  # 每邊手續費（USD），例如 2.8
    commission_per_side_twd: Optional[float] = None  # 每邊手續費（TWD），例如 20.0（台幣商品）
    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "symbol": self.symbol,
            "tick_size": self.tick_size,
            "commission_per_side_usd": self.commission_per_side_usd,
        }
        if self.commission_per_side_twd is not None:
            d["commission_per_side_twd"] = self.commission_per_side_twd
        return d


@dataclass
class DeployPackageConfig:
    """
    部署套件配置
    """
    season: str  # 季節標記，例如 "2026Q1"
    selected_strategies: List[str]  # 選中的策略 ID 列表
    outputs_root: Path  # 輸出根目錄
    slippage_policy: SlippagePolicy  # 滑價政策
    cost_models: List[CostModel]  # 成本模型列表
    deploy_notes: Optional[str] = None  # 部署備註


def generate_deploy_package(config: DeployPackageConfig) -> Path:
    """
    產生 MC 部署套件

    Args:
        config: 部署配置

    Returns:
        部署套件目錄路徑
    """
    # 建立部署目錄
    deploy_dir = config.outputs_root / f"mc_deploy_{config.season}"
    deploy_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 產生 cost_models.json
    cost_models_path = deploy_dir / "cost_models.json"
    _write_cost_models(cost_models_path, config.cost_models, config.slippage_policy)
    
    # 2. 產生 DEPLOY_README.md
    readme_path = deploy_dir / "DEPLOY_README.md"
    _write_deploy_readme(readme_path, config)
    
    # 3. 產生 deploy_manifest.json
    manifest_path = deploy_dir / "deploy_manifest.json"
    _write_deploy_manifest(manifest_path, deploy_dir, config)
    
    return deploy_dir


def _write_cost_models(
    path: Path,
    cost_models: List[CostModel],
    slippage_policy: SlippagePolicy,
) -> None:
    """
    寫入 cost_models.json，包含滑價政策與成本模型
    """
    # 建立成本模型字典（按 symbol 排序以確保 deterministic）
    models_dict = {}
    for model in sorted(cost_models, key=lambda m: m.symbol):
        models_dict[model.symbol] = model.to_dict()
    
    data = {
        "definition": slippage_policy.definition,
        "policy": {
            "selection": slippage_policy.selection_level,
            "stress": slippage_policy.stress_level,
            "mc_execution": slippage_policy.mc_execution_level,
        },
        "levels": slippage_policy.levels,
        "commission_per_symbol": models_dict,
        "tick_size_audit_snapshot": {
            model.symbol: model.tick_size for model in cost_models
        },
    }
    
    # 使用 atomic write
    _atomic_write_json(path, data)


def _write_deploy_readme(path: Path, config: DeployPackageConfig) -> None:
    """
    寫入 DEPLOY_README.md，包含 anti-misconfig signature 段落
    """
    content = f"""# MultiCharts Deployment Package ({config.season})

## Anti‑Misconfig Signature

This package has passed the S2 survive gate (selection slippage = {config.slippage_policy.selection_level}).
Recommended MC slippage setting: **{config.slippage_policy.mc_execution_level}**.
Commission and slippage are applied **per side** (definition: "{config.slippage_policy.definition}").

## Checklist

- [ ] Configured by: FishBroWFS_V2 research pipeline
- [ ] Configured at: {config.season}
- [ ] MC slippage level: {config.slippage_policy.mc_execution_level} ({config.slippage_policy.get_mc_execution_ticks()} ticks)
- [ ] MC commission: see cost_models.json per symbol
- [ ] Tick sizes: audit snapshot included in cost_models.json
- [ ] PLA rule: UNIVERSAL SIGNAL.PLA does NOT receive slippage/commission via Inputs
- [ ] PLA must NOT contain SetCommission/SetSlippage or any hardcoded cost logic

## Selected Strategies

{chr(10).join(f"- {s}" for s in config.selected_strategies)}

## Files

- `cost_models.json` – cost models (slippage levels, commission, tick sizes)
- `deploy_manifest.json` – SHA‑256 hashes for all files + manifest chain
- `DEPLOY_README.md` – this file

## Notes

{config.deploy_notes or "No additional notes."}
"""
    _atomic_write_text(path, content)


def _write_deploy_manifest(
    path: Path,
    deploy_dir: Path,
    config: DeployPackageConfig,
) -> None:
    """
    寫入 deploy_manifest.json，包含所有檔案的 SHA‑256 雜湊與 manifest chain
    """
    # 收集需要雜湊的檔案（排除 manifest 本身）
    files_to_hash = [
        deploy_dir / "cost_models.json",
        deploy_dir / "DEPLOY_README.md",
    ]
    
    file_hashes = {}
    for file_path in files_to_hash:
        if file_path.exists():
            file_hashes[file_path.name] = _compute_file_sha256(file_path)
    
    # 計算 manifest 內容的雜湊（不含 manifest_sha256 欄位）
    manifest_data = {
        "season": config.season,
        "selected_strategies": config.selected_strategies,
        "slippage_policy": {
            "definition": config.slippage_policy.definition,
            "selection_level": config.slippage_policy.selection_level,
            "stress_level": config.slippage_policy.stress_level,
            "mc_execution_level": config.slippage_policy.mc_execution_level,
        },
        "file_hashes": file_hashes,
        "manifest_version": "v1",
    }
    
    # 計算 manifest 雜湊
    manifest_json = json.dumps(manifest_data, sort_keys=True, separators=(",", ":"))
    manifest_sha256 = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    
    # 加入 manifest_sha256
    manifest_data["manifest_sha256"] = manifest_sha256
    
    # atomic write
    _atomic_write_json(path, manifest_data)


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """
    Atomic write JSON 檔案（tmp + replace）
    """
    # 建立暫存檔案
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=2)
        temp_path = Path(f.name)
    
    # 替換目標檔案
    shutil.move(temp_path, path)


def _atomic_write_text(path: Path, content: str) -> None:
    """
    Atomic write 文字檔案
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    shutil.move(temp_path, path)


def _compute_file_sha256(path: Path) -> str:
    """
    計算檔案的 SHA‑256 雜湊
    """
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_pla_template(pla_template_path: Path) -> bool:
    """
    驗證 PLA 模板是否包含禁止的關鍵字（SetCommission, SetSlippage 等）

    Args:
        pla_template_path: PLA 模板檔案路徑

    Returns:
        bool: 是否通過驗證（True 表示無禁止關鍵字）

    Raises:
        ValueError: 如果發現禁止關鍵字
    """
    if not pla_template_path.exists():
        return True  # 沒有模板，視為通過
    
    forbidden_keywords = [
        "SetCommission",
        "SetSlippage",
        "Commission",
        "Slippage",
        "Cost",
        "Fee",
    ]
    
    content = pla_template_path.read_text(encoding="utf-8", errors="ignore")
    for keyword in forbidden_keywords:
        if keyword in content:
            raise ValueError(
                f"PLA 模板包含禁止關鍵字 '{keyword}'。"
                "UNIVERSAL SIGNAL.PLA 不得包含任何硬編碼的成本邏輯。"
            )
    
    return True



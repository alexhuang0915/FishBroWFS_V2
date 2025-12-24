"""Clone to Wizard 服務 - 從現有 run 預填 Wizard 欄位"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


def load_config_snapshot(run_dir: Path) -> Optional[Dict[str, Any]]:
    """
    從 run_dir 載入 config snapshot
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Optional[Dict[str, Any]]: config snapshot 字典，如果不存在則返回 None
    """
    # 嘗試讀取 config_snapshot.json
    config_path = run_dir / "config_snapshot.json"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    
    # 嘗試讀取 manifest.json
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            # 從 manifest 提取 config 相關欄位
            config_snapshot = {
                "season": manifest.get("season"),
                "dataset_id": manifest.get("dataset_id"),
                "strategy_id": manifest.get("strategy_id"),
                "mode": manifest.get("mode"),
                "stage": manifest.get("stage"),
                "timestamp": manifest.get("timestamp"),
                "run_id": manifest.get("run_id"),
            }
            
            # 嘗試提取 wfs_config
            if "wfs_config" in manifest:
                config_snapshot["wfs_config"] = manifest["wfs_config"]
            
            return config_snapshot
        except (json.JSONDecodeError, OSError, KeyError):
            pass
    
    return None


def build_wizard_prefill(run_dir: Path) -> Dict[str, Any]:
    """
    建立 Wizard 預填資料
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Dict[str, Any]: Wizard 預填資料
    """
    # 載入 config snapshot
    config = load_config_snapshot(run_dir)
    
    if config is None:
        # 如果無法載入 config，返回基本資訊
        return {
            "season": "2026Q1",
            "dataset_id": None,
            "strategy_id": None,
            "mode": "smoke",
            "note": f"Cloned from {run_dir.name}",
        }
    
    # 建立預填資料
    prefill: Dict[str, Any] = {
        "season": config.get("season", "2026Q1"),
        "dataset_id": config.get("dataset_id"),
        "strategy_id": config.get("strategy_id"),
        "mode": _map_mode(config.get("mode")),
        "note": f"Cloned from {run_dir.name}",
    }
    
    # 添加 wfs_config（如果存在）
    if "wfs_config" in config:
        prefill["wfs_config"] = config["wfs_config"]
    
    # 添加 grid preset（如果可推斷）
    grid_preset = _infer_grid_preset(config)
    if grid_preset:
        prefill["grid_preset"] = grid_preset
    
    # 添加 stage 資訊
    stage = config.get("stage")
    if stage:
        prefill["stage"] = stage
    
    return prefill


def _map_mode(mode: Optional[str]) -> str:
    """
    映射 mode 到 Wizard 可用的選項
    
    Args:
        mode: 原始 mode
    
    Returns:
        str: 映射後的 mode
    """
    if not mode:
        return "smoke"
    
    mode_lower = mode.lower()
    
    # 映射規則
    if "smoke" in mode_lower:
        return "smoke"
    elif "lite" in mode_lower:
        return "lite"
    elif "full" in mode_lower:
        return "full"
    elif "incremental" in mode_lower:
        return "incremental"
    else:
        # 預設回退
        return "smoke"


def _infer_grid_preset(config: Dict[str, Any]) -> Optional[str]:
    """
    從 config 推斷 grid preset
    
    Args:
        config: config snapshot
    
    Returns:
        Optional[str]: grid preset 名稱
    """
    # 檢查是否有 wfs_config
    wfs_config = config.get("wfs_config")
    if isinstance(wfs_config, dict):
        # 檢查是否有 grid 相關設定
        if "grid" in wfs_config or "param_grid" in wfs_config:
            return "custom"
    
    # 檢查 stage
    stage = config.get("stage")
    if stage:
        if "stage0" in stage:
            return "coarse"
        elif "stage1" in stage:
            return "topk"
        elif "stage2" in stage:
            return "confirm"
    
    # 檢查 mode
    mode = config.get("mode", "").lower()
    if "full" in mode:
        return "full_grid"
    elif "lite" in mode:
        return "lite_grid"
    
    return None


def get_clone_summary(run_dir: Path) -> Dict[str, Any]:
    """
    獲取 clone 摘要資訊（用於 UI 顯示）
    
    Args:
        run_dir: run 目錄路徑
    
    Returns:
        Dict[str, Any]: 摘要資訊
    """
    config = load_config_snapshot(run_dir)
    
    if config is None:
        return {
            "success": False,
            "error": "無法載入 config snapshot 或 manifest",
            "run_id": run_dir.name,
        }
    
    prefill = build_wizard_prefill(run_dir)
    
    return {
        "success": True,
        "run_id": run_dir.name,
        "season": prefill.get("season"),
        "dataset_id": prefill.get("dataset_id"),
        "strategy_id": prefill.get("strategy_id"),
        "mode": prefill.get("mode"),
        "stage": prefill.get("stage"),
        "grid_preset": prefill.get("grid_preset"),
        "has_wfs_config": "wfs_config" in prefill,
        "note": prefill.get("note"),
    }
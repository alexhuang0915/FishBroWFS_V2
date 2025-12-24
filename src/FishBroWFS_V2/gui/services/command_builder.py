"""Generate Command 與 ui_command_snapshot.json 服務"""

import json
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass(frozen=True)
class CommandBuildResult:
    """命令建構結果"""
    argv: List[str]
    shell: str
    snapshot: Dict[str, Any]


def build_research_command(snapshot: Dict[str, Any]) -> CommandBuildResult:
    """
    從 UI snapshot 建構可重現的 CLI command
    
    Args:
        snapshot: UI 設定 snapshot
    
    Returns:
        CommandBuildResult: 命令建構結果
    """
    # 基礎命令
    argv = ["python", "-m", "src.FishBroWFS_V2.research"]
    
    # 添加必要參數
    required_fields = ["season", "dataset_id", "strategy_id", "mode"]
    for field in required_fields:
        if field in snapshot and snapshot[field]:
            argv.extend([f"--{field}", str(snapshot[field])])
    
    # 添加可選參數
    optional_fields = [
        "stage", "grid_preset", "note", "wfs_config_path",
        "param_grid", "max_workers", "timeout_hours"
    ]
    for field in optional_fields:
        if field in snapshot and snapshot[field]:
            argv.extend([f"--{field}", str(snapshot[field])])
    
    # 添加 wfs_config（如果是檔案路徑）
    if "wfs_config" in snapshot and isinstance(snapshot["wfs_config"], str):
        argv.extend(["--wfs-config", snapshot["wfs_config"]])
    
    # 構建 shell 命令字串
    shell_parts = []
    for arg in argv:
        if " " in arg or any(c in arg for c in ["'", '"', "\\", "$", "`"]):
            # 需要引號
            shell_parts.append(json.dumps(arg))
        else:
            shell_parts.append(arg)
    
    shell = " ".join(shell_parts)
    
    return CommandBuildResult(
        argv=argv,
        shell=shell,
        snapshot=snapshot
    )


def write_ui_snapshot(outputs_root: Path, season: str, snapshot: Dict[str, Any]) -> str:
    """
    將 UI snapshot 寫入檔案（append-only，不覆寫）
    
    Args:
        outputs_root: outputs 根目錄
        season: season 名稱
        snapshot: UI snapshot 資料
    
    Returns:
        str: 寫入的檔案路徑
    """
    # 建立目錄結構
    snapshots_dir = outputs_root / "seasons" / season / "ui_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    # 產生時間戳和 hash
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_str = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    snapshot_hash = hashlib.sha256(snapshot_str.encode()).hexdigest()[:8]
    
    # 檔案名稱
    filename = f"{timestamp}-{snapshot_hash}.json"
    filepath = snapshots_dir / filename
    
    # 確保不覆寫現有檔案（如果存在，添加計數器）
    counter = 1
    while filepath.exists():
        filename = f"{timestamp}-{snapshot_hash}-{counter}.json"
        filepath = snapshots_dir / filename
        counter += 1
    
    # 添加 metadata
    full_snapshot = {
        "_metadata": {
            "created_at": time.time(),
            "created_at_iso": datetime.now().isoformat(),
            "version": "1.0",
            "source": "ui_wizard",
            "snapshot_hash": snapshot_hash,
            "filename": filename,
        },
        "data": snapshot
    }
    
    # 寫入檔案
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(full_snapshot, f, indent=2, ensure_ascii=False)
    
    return str(filepath)


def load_ui_snapshot(filepath: Path) -> Optional[Dict[str, Any]]:
    """
    載入 UI snapshot 檔案
    
    Args:
        filepath: snapshot 檔案路徑
    
    Returns:
        Optional[Dict[str, Any]]: snapshot 資料，如果載入失敗則返回 None
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 返回實際資料（不含 metadata）
        if "data" in data:
            return data["data"]
        else:
            return data
    except (json.JSONDecodeError, OSError):
        return None


def list_ui_snapshots(outputs_root: Path, season: str, limit: int = 50) -> List[dict]:
    """
    列出指定 season 的 UI snapshots
    
    Args:
        outputs_root: outputs 根目錄
        season: season 名稱
        limit: 返回的數量限制
    
    Returns:
        List[dict]: snapshot 資訊清單
    """
    snapshots_dir = outputs_root / "seasons" / season / "ui_snapshots"
    
    if not snapshots_dir.exists():
        return []
    
    snapshots = []
    
    for filepath in sorted(snapshots_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not filepath.is_file() or not filepath.name.endswith('.json'):
            continue
        
        try:
            stat = filepath.stat()
            
            # 讀取 metadata（不讀取完整資料以提高效能）
            with open(filepath, 'r', encoding='utf-8') as f:
                metadata = json.load(f).get("_metadata", {})
            
            snapshots.append({
                "filename": filepath.name,
                "path": str(filepath),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created_at": metadata.get("created_at", stat.st_mtime),
                "created_at_iso": metadata.get("created_at_iso"),
                "snapshot_hash": metadata.get("snapshot_hash"),
                "source": metadata.get("source", "unknown"),
            })
            
            if len(snapshots) >= limit:
                break
        except (json.JSONDecodeError, OSError):
            continue
    
    return snapshots


def create_snapshot_from_wizard(wizard_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    從 Wizard 資料建立標準化的 snapshot
    
    Args:
        wizard_data: Wizard 表單資料
    
    Returns:
        Dict[str, Any]: 標準化的 snapshot
    """
    # 基礎欄位
    snapshot = {
        "season": wizard_data.get("season", "2026Q1"),
        "dataset_id": wizard_data.get("dataset_id"),
        "strategy_id": wizard_data.get("strategy_id"),
        "mode": wizard_data.get("mode", "smoke"),
        "note": wizard_data.get("note", ""),
        "created_from": "wizard",
        "created_at": time.time(),
        "created_at_iso": datetime.now().isoformat(),
    }
    
    # 可選欄位
    optional_fields = [
        "stage", "grid_preset", "wfs_config_path",
        "param_grid", "max_workers", "timeout_hours"
    ]
    for field in optional_fields:
        if field in wizard_data and wizard_data[field]:
            snapshot[field] = wizard_data[field]
    
    # wfs_config（如果是字典）
    if "wfs_config" in wizard_data and isinstance(wizard_data["wfs_config"], dict):
        snapshot["wfs_config"] = wizard_data["wfs_config"]
    
    # txt_paths（如果是清單）
    if "txt_paths" in wizard_data and isinstance(wizard_data["txt_paths"], list):
        snapshot["txt_paths"] = wizard_data["txt_paths"]
    
    return snapshot


def validate_snapshot_for_command(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    驗證 snapshot 是否可用於建構命令
    
    Args:
        snapshot: 要驗證的 snapshot
    
    Returns:
        Dict[str, Any]: 驗證結果
    """
    errors = []
    warnings = []
    
    # 檢查必要欄位
    required_fields = ["season", "dataset_id", "strategy_id", "mode"]
    for field in required_fields:
        if field not in snapshot or not snapshot[field]:
            errors.append(f"缺少必要欄位: {field}")
    
    # 檢查 season 格式
    if "season" in snapshot:
        season = snapshot["season"]
        if not isinstance(season, str) or len(season) < 4:
            warnings.append(f"season 格式可能不正確: {season}")
    
    # 檢查 mode 有效性
    valid_modes = ["smoke", "lite", "full", "incremental"]
    if "mode" in snapshot and snapshot["mode"] not in valid_modes:
        warnings.append(f"mode 可能無效: {snapshot['mode']}，有效值: {valid_modes}")
    
    # 檢查 wfs_config_path 是否存在（如果是檔案路徑）
    if "wfs_config_path" in snapshot and snapshot["wfs_config_path"]:
        path = Path(snapshot["wfs_config_path"])
        if not path.exists():
            warnings.append(f"wfs_config_path 不存在: {path}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "has_warnings": len(warnings) > 0,
        "required_fields_present": all(field in snapshot and snapshot[field] for field in required_fields),
    }
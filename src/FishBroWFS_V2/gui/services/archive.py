"""Archive 服務 - 軟刪除 + Audit log"""

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import hashlib

# 嘗試導入 season_state 模組（Phase 5 新增）
try:
    from FishBroWFS_V2.core.season_state import load_season_state
    SEASON_STATE_AVAILABLE = True
except ImportError:
    SEASON_STATE_AVAILABLE = False
    load_season_state = None


@dataclass(frozen=True)
class ArchiveResult:
    """歸檔結果"""
    archived_path: str
    audit_path: str


def archive_run(
    outputs_root: Path,
    run_dir: Path,
    reason: str,
    operator: str = "local"
) -> ArchiveResult:
    """
    歸檔 run（軟刪除）
    
    Args:
        outputs_root: outputs 根目錄
        run_dir: 要歸檔的 run 目錄
        reason: 歸檔原因（必須是 failed/garbage/disk/other 之一）
        operator: 操作者標識
    
    Returns:
        ArchiveResult: 歸檔結果
    
    Raises:
        ValueError: 如果 reason 不在允許的清單中
        OSError: 如果移動檔案失敗
    """
    # 驗證 reason
    allowed_reasons = ["failed", "garbage", "disk", "other"]
    if reason not in allowed_reasons:
        raise ValueError(f"reason 必須是 {allowed_reasons} 之一，得到: {reason}")
    
    # 確保 run_dir 存在
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir 不存在: {run_dir}")
    
    # 從 run_dir 路徑解析 season 和 run_id
    # 路徑格式: .../seasons/<season>/runs/<run_id>
    parts = run_dir.parts
    try:
        # 尋找 seasons 索引
        seasons_idx = parts.index("seasons")
        if seasons_idx + 2 >= len(parts):
            raise ValueError(f"無法從路徑解析 season 和 run_id: {run_dir}")
        
        season = parts[seasons_idx + 1]
        run_id = parts[-1]
    except ValueError:
        # 如果找不到 seasons，使用預設值
        season = "unknown"
        run_id = run_dir.name
    
    # Phase 5: 檢查 season 是否被凍結
    if SEASON_STATE_AVAILABLE and load_season_state is not None:
        try:
            state = load_season_state(season)
            if state and state.get("state") == "FROZEN":
                frozen_reason = state.get("reason", "Season is frozen")
                raise ValueError(f"Cannot archive run: season {season} is frozen ({frozen_reason})")
        except Exception:
            # 如果載入失敗，忽略錯誤（允許歸檔）
            pass
    
    # 建立目標目錄
    archive_root = outputs_root / ".archive"
    archive_root.mkdir(exist_ok=True)
    
    season_archive_dir = archive_root / season
    season_archive_dir.mkdir(exist_ok=True)
    
    target_dir = season_archive_dir / run_id
    
    # 如果目標目錄已存在，添加時間戳後綴
    if target_dir.exists():
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        target_dir = season_archive_dir / f"{run_id}_{timestamp}"
    
    # 計算原始 manifest 的 SHA256（如果存在）
    manifest_sha256 = None
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'rb') as f:
                manifest_sha256 = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            pass
    
    # 移動目錄
    shutil.move(str(run_dir), str(target_dir))
    
    # 寫入 audit log
    audit_dir = archive_root / "_audit"
    audit_dir.mkdir(exist_ok=True)
    
    audit_file = audit_dir / "archive_log.jsonl"
    
    audit_entry = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "operator": operator,
        "reason": reason,
        "original_path": str(run_dir),
        "archived_path": str(target_dir),
        "season": season,
        "run_id": run_id,
        "original_manifest_sha256": manifest_sha256,
    }
    
    with open(audit_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
    
    return ArchiveResult(
        archived_path=str(target_dir),
        audit_path=str(audit_file)
    )


def list_archived_runs(outputs_root: Path, season: Optional[str] = None) -> list[dict]:
    """
    列出已歸檔的 runs
    
    Args:
        outputs_root: outputs 根目錄
        season: 可選的 season 過濾
    
    Returns:
        list[dict]: 已歸檔 runs 的清單
    """
    archive_root = outputs_root / ".archive"
    if not archive_root.exists():
        return []
    
    archived_runs = []
    
    # 掃描所有 season 目錄
    for season_dir in archive_root.iterdir():
        if not season_dir.is_dir() or season_dir.name == "_audit":
            continue
        
        if season is not None and season_dir.name != season:
            continue
        
        for run_dir in season_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            # 讀取 run 資訊
            manifest_path = run_dir / "manifest.json"
            manifest = None
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass
            
            archived_runs.append({
                "season": season_dir.name,
                "run_id": run_dir.name,
                "path": str(run_dir),
                "manifest": manifest,
            })
    
    return archived_runs


def read_audit_log(outputs_root: Path, limit: int = 100) -> list[dict]:
    """
    讀取 audit log
    
    Args:
        outputs_root: outputs 根目錄
        limit: 返回的條目數量限制
    
    Returns:
        list[dict]: audit log 條目
    """
    audit_file = outputs_root / ".archive" / "_audit" / "archive_log.jsonl"
    
    if not audit_file.exists():
        return []
    
    entries = []
    try:
        with open(audit_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 從最新開始讀取
        for line in reversed(lines[-limit:]):
            try:
                entry = json.loads(line.strip())
                entries.append(entry)
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    
    return entries
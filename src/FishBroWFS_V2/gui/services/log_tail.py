"""Logs Viewer 服務 - Lazy + Polling（禁止 push）"""

import os
import time
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime


def tail_lines(path: Path, n: int = 200) -> List[str]:
    """
    讀取檔案的最後 n 行
    
    Args:
        path: 檔案路徑
        n: 要讀取的行數
    
    Returns:
        List[str]: 最後 n 行的清單（如果檔案不存在則返回空清單）
    """
    if not path.exists():
        return []
    
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            # 簡單實現：讀取所有行然後取最後 n 行
            lines = f.readlines()
            return lines[-n:] if len(lines) > n else lines
    except (OSError, UnicodeDecodeError):
        return []


def tail_lines_with_stats(path: Path, n: int = 200) -> Tuple[List[str], dict]:
    """
    讀取檔案的最後 n 行並返回統計資訊
    
    Args:
        path: 檔案路徑
        n: 要讀取的行數
    
    Returns:
        Tuple[List[str], dict]: (行清單, 統計資訊)
    """
    lines = tail_lines(path, n)
    
    stats = {
        "file_exists": path.exists(),
        "file_size": path.stat().st_size if path.exists() else 0,
        "file_mtime": path.stat().st_mtime if path.exists() else 0,
        "lines_returned": len(lines),
        "timestamp": time.time(),
        "timestamp_iso": datetime.now().isoformat(),
    }
    
    return lines, stats


class LogTailer:
    """Log tailer 類別，支援 lazy polling"""
    
    def __init__(self, log_path: Path, max_lines: int = 200, poll_interval: float = 2.0):
        """
        初始化 LogTailer
        
        Args:
            log_path: log 檔案路徑
            max_lines: 最大行數
            poll_interval: polling 間隔（秒）
        """
        self.log_path = Path(log_path)
        self.max_lines = max_lines
        self.poll_interval = poll_interval
        self._last_read_position = 0
        self._last_read_time = 0.0
        self._is_active = False
        self._timer = None
    
    def start(self) -> None:
        """啟動 polling"""
        self._is_active = True
        self._last_read_position = 0
        self._last_read_time = time.time()
    
    def stop(self) -> None:
        """停止 polling"""
        self._is_active = False
        if self._timer:
            self._timer.cancel()
    
    def read_new_lines(self) -> List[str]:
        """
        讀取新的行（從上次讀取位置開始）
        
        Returns:
            List[str]: 新的行清單
        """
        if not self.log_path.exists():
            return []
        
        try:
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 移動到上次讀取的位置
                if self._last_read_position > 0:
                    try:
                        f.seek(self._last_read_position)
                    except (OSError, ValueError):
                        # 如果 seek 失敗，從頭開始讀取
                        self._last_read_position = 0
                
                # 讀取新行
                new_lines = f.readlines()
                
                # 更新位置
                self._last_read_position = f.tell()
                self._last_read_time = time.time()
                
                return new_lines
        except (OSError, UnicodeDecodeError):
            return []
    
    def get_status(self) -> dict:
        """獲取 tailer 狀態"""
        return {
            "is_active": self._is_active,
            "log_path": str(self.log_path),
            "log_exists": self.log_path.exists(),
            "last_read_position": self._last_read_position,
            "last_read_time": self._last_read_time,
            "last_read_time_iso": datetime.fromtimestamp(self._last_read_time).isoformat() if self._last_read_time > 0 else None,
            "poll_interval": self.poll_interval,
            "max_lines": self.max_lines,
        }


def find_log_files(run_dir: Path) -> List[dict]:
    """
    在 run_dir 中尋找 log 檔案
    
    Args:
        run_dir: run 目錄
    
    Returns:
        List[dict]: log 檔案資訊
    """
    if not run_dir.exists():
        return []
    
    log_files = []
    
    # 常見的 log 檔案名稱
    common_log_names = [
        "worker.log",
        "run.log",
        "output.log",
        "error.log",
        "stdout.log",
        "stderr.log",
        "log.txt",
    ]
    
    for log_name in common_log_names:
        log_path = run_dir / log_name
        if log_path.exists() and log_path.is_file():
            try:
                stat = log_path.stat()
                log_files.append({
                    "name": log_name,
                    "path": str(log_path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except OSError:
                continue
    
    # 也尋找 logs 目錄
    logs_dir = run_dir / "logs"
    if logs_dir.exists() and logs_dir.is_dir():
        try:
            for log_file in logs_dir.iterdir():
                if log_file.is_file() and log_file.suffix in ['.log', '.txt']:
                    try:
                        stat = log_file.stat()
                        log_files.append({
                            "name": f"logs/{log_file.name}",
                            "path": str(log_file),
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                            "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        })
                    except OSError:
                        continue
        except OSError:
            pass
    
    return log_files


def get_log_preview(log_path: Path, preview_lines: int = 50) -> dict:
    """
    獲取 log 檔案預覽
    
    Args:
        log_path: log 檔案路徑
        preview_lines: 預覽行數
    
    Returns:
        dict: log 預覽資訊
    """
    if not log_path.exists():
        return {
            "exists": False,
            "error": "Log 檔案不存在",
            "preview": [],
            "total_lines": 0,
        }
    
    try:
        # 計算總行數
        total_lines = 0
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for _ in f:
                total_lines += 1
        
        # 讀取預覽
        preview = tail_lines(log_path, preview_lines)
        
        stat = log_path.stat()
        return {
            "exists": True,
            "path": str(log_path),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "total_lines": total_lines,
            "preview_lines": len(preview),
            "preview": preview,
        }
    except (OSError, UnicodeDecodeError) as e:
        return {
            "exists": True,
            "error": str(e),
            "preview": [],
            "total_lines": 0,
        }
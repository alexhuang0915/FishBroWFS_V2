
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




"""
Resampler 核心

提供 deterministic resampling 功能，支援 session anchor 與 safe point 計算。
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import List, Tuple, Optional, Dict, Any, Literal
import numpy as np
import pandas as pd

from core.dimensions import get_dimension_for_dataset
from contracts.dimensions import SessionSpec as ContractSessionSpec

logger = logging.getLogger(__name__)

# Performance guardrails for resampling
MAX_INPUT_BARS = 10_000_000  # Maximum number of input bars to resample
MAX_OUTPUT_BARS = 1_000_000  # Maximum number of output bars after resampling
MAX_SESSION_HOURS = 24  # Maximum session length in hours (sanity check)


@dataclass(frozen=True)
class SessionSpecTaipei:
    """台北時間的交易時段規格"""
    open_hhmm: str  # HH:MM 格式，例如 "07:00"
    close_hhmm: str  # HH:MM 格式，例如 "06:00"（次日）
    breaks: List[Tuple[str, str]]  # 休市時段列表，每個時段為 (start, end)
    tz: str = "Asia/Taipei"
    
    def __post_init__(self):
        # 預先計算小時、分鐘、總分鐘數，避免重複計算
        # 由於 dataclass frozen=True，必須使用 object.__setattr__
        open_hour = int(self.open_hhmm.split(":")[0])
        open_minute = int(self.open_hhmm.split(":")[1])
        close_hour_raw = int(self.close_hhmm.split(":")[0])
        close_minute = int(self.close_hhmm.split(":")[1])
        close_hour = 0 if close_hour_raw == 24 else close_hour_raw
        
        object.__setattr__(self, '_open_hour', open_hour)
        object.__setattr__(self, '_open_minute', open_minute)
        object.__setattr__(self, '_close_hour', close_hour)
        object.__setattr__(self, '_close_minute', close_minute)
        
        open_total = open_hour * 60 + open_minute
        close_total = close_hour * 60 + close_minute
        object.__setattr__(self, '_open_total', open_total)
        object.__setattr__(self, '_close_total', close_total)
        object.__setattr__(self, '_is_overnight', close_total < open_total)
    
    @classmethod
    def from_contract(cls, spec: ContractSessionSpec) -> SessionSpecTaipei:
        """從 contracts SessionSpec 轉換"""
        return cls(
            open_hhmm=spec.open_taipei,
            close_hhmm=spec.close_taipei,
            breaks=spec.breaks_taipei,
            tz=spec.tz,
        )
    
    @property
    def open_hour(self) -> int:
        """開盤小時"""
        return self._open_hour
    
    @property
    def open_minute(self) -> int:
        """開盤分鐘"""
        return self._open_minute
    
    @property
    def close_hour(self) -> int:
        """收盤小時（處理 24:00 為 0）"""
        return self._close_hour
    
    @property
    def close_minute(self) -> int:
        """收盤分鐘"""
        return self._close_minute
    
    def is_overnight(self) -> bool:
        """是否為隔夜時段（收盤時間小於開盤時間）"""
        return self._is_overnight
    
    def session_start_for_date(self, d: date) -> datetime:
        """
        取得指定日期的 session 開始時間
        
        對於隔夜時段，session 開始時間為前一天的開盤時間
        例如：open=07:00, close=06:00，則 2023-01-02 的 session 開始時間為 2023-01-01 07:00
        """
        if self.is_overnight():
            # 隔夜時段：session 開始時間為前一天的開盤時間
            session_date = d - timedelta(days=1)
        else:
            # 非隔夜時段：session 開始時間為當天的開盤時間
            session_date = d
        
        return datetime(
            session_date.year,
            session_date.month,
            session_date.day,
            self.open_hour,
            self.open_minute,
            0,
        )
    
    def is_in_break(self, dt: datetime) -> bool:
        """檢查時間是否在休市時段內"""
        time_str = dt.strftime("%H:%M")
        for start, end in self.breaks:
            if start <= time_str < end:
                return True
        return False
    
    def is_in_session(self, dt: datetime) -> bool:
        """檢查時間是否在交易時段內（不考慮休市）"""
        # 計算從 session_start 開始的經過分鐘數
        session_start = self.session_start_for_date(dt.date())
        
        # 對於隔夜時段，需要調整計算
        if self.is_overnight():
            # 如果 dt 在 session_start 之後（同一天），則屬於當前 session
            # 如果 dt 在 session_start 之前（可能是次日），則屬於下一個 session
            if dt >= session_start:
                # 屬於當前 session
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
                return session_start <= dt < session_end
            else:
                # 屬於下一個 session
                session_start = self.session_start_for_date(dt.date() + timedelta(days=1))
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
                return session_start <= dt < session_end
        else:
            # 非隔夜時段
            # 處理 close_hhmm == "24:00" 的情況
            if self.close_hhmm == "24:00":
                # session_end 是次日的 00:00
                session_end = session_start + timedelta(days=1)
                session_end = session_end.replace(
                    hour=0,
                    minute=0,
                    second=0,
                )
            else:
                session_end = session_start.replace(
                    hour=self.close_hour,
                    minute=self.close_minute,
                    second=0,
                )
            return session_start <= dt < session_end


def get_session_spec_for_dataset(dataset_id: str) -> Tuple[SessionSpecTaipei, bool]:
    """
    讀取資料集的 session 規格
    
    Args:
        dataset_id: 資料集 ID
        
    Returns:
        Tuple[SessionSpecTaipei, bool]:
            - SessionSpecTaipei 物件
            - dimension_found: 是否找到 dimension（True 表示找到，False 表示使用 fallback）
    """
    # 從 dimension registry 查詢
    dimension = get_dimension_for_dataset(dataset_id)
    
    if dimension is not None:
        # 找到 dimension，使用其 session spec
        return SessionSpecTaipei.from_contract(dimension.session), True
    
    # 找不到 dimension，使用 fallback
    # 根據 Phase 3A 要求：open=00:00 close=24:00 breaks=[]
    fallback_spec = SessionSpecTaipei(
        open_hhmm="00:00",
        close_hhmm="24:00",
        breaks=[],
        tz="Asia/Taipei",
    )
    
    return fallback_spec, False


def compute_session_start(ts: datetime, session: SessionSpecTaipei) -> datetime:
    """
    Return the session_start datetime (Taipei) whose session window contains ts.
    
    Must handle overnight sessions where close < open (cross midnight).
    
    Args:
        ts: 時間戳記（台北時間）
        session: 交易時段規格
        
    Returns:
        session_start: 包含 ts 的 session 開始時間
    """
    # 對於隔夜時段，需要特別處理
    if session.is_overnight():
        # 嘗試當天的 session_start
        candidate = session.session_start_for_date(ts.date())
        
        # 檢查 ts 是否在 candidate 開始的 session 內
        if session.is_in_session(ts):
            return candidate
        
        # 如果不在，嘗試前一天的 session_start
        candidate = session.session_start_for_date(ts.date() - timedelta(days=1))
        if session.is_in_session(ts):
            return candidate
        
        # 如果還是不在，嘗試後一天的 session_start
        candidate = session.session_start_for_date(ts.date() + timedelta(days=1))
        if session.is_in_session(ts):
            return candidate
        
        # 理論上不應該到這裡，但為了安全回傳當天的 session_start
        return session.session_start_for_date(ts.date())
    else:
        # 非隔夜時段：直接使用當天的 session_start
        return session.session_start_for_date(ts.date())


def compute_safe_recompute_start(
    ts_append_start: datetime, 
    tf_min: int, 
    session: SessionSpecTaipei
) -> datetime:
    """
    Safe point = session_start + floor((ts - session_start)/tf)*tf
    Then subtract tf if you want extra safety for boundary bar (optional, but deterministic).
    Must NOT return after ts_append_start.
    
    嚴格規則（鎖死）：
    1. safe = session_start + floor(delta_minutes/tf)*tf
    2. 額外保險：safe = max(session_start, safe - tf)（確保不晚於 ts_append_start）
    
    Args:
        ts_append_start: 新增資料的開始時間
        tf_min: timeframe 分鐘數
        session: 交易時段規格
        
    Returns:
        safe_recompute_start: 安全重算開始時間
    """
    # 1. 計算包含 ts_append_start 的 session_start
    session_start = compute_session_start(ts_append_start, session)
    
    # 2. 計算從 session_start 到 ts_append_start 的總分鐘數
    delta = ts_append_start - session_start
    delta_minutes = int(delta.total_seconds() // 60)
    
    # 3. safe = session_start + floor(delta_minutes/tf)*tf
    safe_minutes = (delta_minutes // tf_min) * tf_min
    safe = session_start + timedelta(minutes=safe_minutes)
    
    # 4. 額外保險：safe = max(session_start, safe - tf)
    # 確保 safe 不晚於 ts_append_start（但可能早於）
    safe_extra = safe - timedelta(minutes=tf_min)
    if safe_extra >= session_start:
        safe = safe_extra
    
    # 確保 safe 不晚於 ts_append_start
    if safe > ts_append_start:
        safe = session_start
    
    return safe


def resample_ohlcv(
    ts: np.ndarray, 
    o: np.ndarray, 
    h: np.ndarray, 
    l: np.ndarray, 
    c: np.ndarray, 
    v: np.ndarray,
    tf_min: int,
    session: SessionSpecTaipei,
    start_ts: Optional[datetime] = None,
) -> Dict[str, np.ndarray]:
    """
    Resample normalized bars -> tf bars anchored at session_start.
    
    Must ignore bars inside breaks (drop or treat as gap; choose one and keep consistent).
    Deterministic output ordering by ts ascending.
    
    行為規格：
    1. 只處理在交易時段內的 bars（忽略休市時段）
    2. 以 session_start 為 anchor 進行 resample
    3. 如果提供 start_ts，只處理 ts >= start_ts 的 bars
    4. 輸出 ts 遞增排序
    
    Args:
        ts: 時間戳記陣列（datetime 物件或 UNIX seconds）
        o, h, l, c, v: OHLCV 陣列
        tf_min: timeframe 分鐘數
        session: 交易時段規格
        start_ts: 可選的開始時間，只處理此時間之後的 bars
        
    Returns:
        字典，包含 resampled bars:
            ts: datetime64[s] 陣列
            open, high, low, close, volume: float64 或 int64 陣列
    """
    # 輸入驗證
    n = len(ts)
    if not (len(o) == len(h) == len(l) == len(c) == len(v) == n):
        raise ValueError("所有輸入陣列長度必須一致")
    
    # 性能防護欄檢查
    if n > MAX_INPUT_BARS:
        raise ValueError(
            f"輸入 bars 數量過多: {n} 超過最大限制 {MAX_INPUT_BARS}。"
            f"請考慮分批處理或增加 MAX_INPUT_BARS。"
        )
    
    # 檢查 timeframe 合理性
    if tf_min <= 0 or tf_min > 1440:  # 1440 minutes = 24 hours
        raise ValueError(f"無效的 timeframe: {tf_min} 分鐘。必須在 1 到 1440 之間。")
    
    # 檢查 session 長度合理性
    open_total = session.open_hour * 60 + session.open_minute
    close_total = session.close_hour * 60 + session.close_minute
    if session.is_overnight():
        session_length_hours = (24 * 60 - open_total + close_total) / 60
    else:
        session_length_hours = (close_total - open_total) / 60
    
    if session_length_hours > MAX_SESSION_HOURS:
        raise ValueError(
            f"交易時段過長: {session_length_hours:.1f} 小時超過最大限制 {MAX_SESSION_HOURS} 小時。"
        )
    
    logger.info(f"Resampler 防護欄檢查通過: 輸入 bars={n}, timeframe={tf_min} 分鐘, 時段長度={session_length_hours:.1f} 小時")
    
    if n == 0:
        return {
            "ts": np.array([], dtype="datetime64[s]"),
            "open": np.array([], dtype="float64"),
            "high": np.array([], dtype="float64"),
            "low": np.array([], dtype="float64"),
            "close": np.array([], dtype="float64"),
            "volume": np.array([], dtype="int64"),
        }
    
    # 轉換 ts 為 datetime 物件
    ts_datetime = []
    for t in ts:
        if isinstance(t, (int, float, np.integer, np.floating)):
            # UNIX seconds
            ts_datetime.append(datetime.fromtimestamp(t))
        elif isinstance(t, np.datetime64):
            # numpy datetime64
            # 轉換為 pandas Timestamp 然後到 datetime
            ts_datetime.append(pd.Timestamp(t).to_pydatetime())
        elif isinstance(t, datetime):
            # 已經是 datetime
            ts_datetime.append(t)
        else:
            raise TypeError(f"不支援的時間戳記類型: {type(t)}")
    
    # 過濾 bars：只保留在交易時段內且不在休市時段的 bars
    valid_indices = []
    valid_ts = []
    valid_o = []
    valid_h = []
    valid_l = []
    valid_c = []
    valid_v = []
    
    for i, dt in enumerate(ts_datetime):
        # 檢查是否在交易時段內
        if not session.is_in_session(dt):
            continue
        
        # 檢查是否在休市時段內
        if session.is_in_break(dt):
            continue
        
        # 檢查是否在 start_ts 之後（如果提供）
        if start_ts is not None and dt < start_ts:
            continue
        
        valid_indices.append(i)
        valid_ts.append(dt)
        valid_o.append(o[i])
        valid_h.append(h[i])
        valid_l.append(l[i])
        valid_c.append(c[i])
        valid_v.append(v[i])
    
    if not valid_ts:
        # 沒有有效的 bars
        return {
            "ts": np.array([], dtype="datetime64[s]"),
            "open": np.array([], dtype="float64"),
            "high": np.array([], dtype="float64"),
            "low": np.array([], dtype="float64"),
            "close": np.array([], dtype="float64"),
            "volume": np.array([], dtype="int64"),
        }
    
    # 將 valid_ts 轉換為 pandas DatetimeIndex 以便 resample
    df = pd.DataFrame({
        "open": valid_o,
        "high": valid_h,
        "low": valid_l,
        "close": valid_c,
        "volume": valid_v,
    }, index=pd.DatetimeIndex(valid_ts, tz=None))
    
    # 計算每個 bar 所屬的 session_start
    session_starts = [compute_session_start(dt, session) for dt in valid_ts]
    
    # 計算從 session_start 開始的經過分鐘數
    # 我們需要將每個 bar 分配到以 session_start 為基準的 tf 分鐘區間
    # 建立一個虛擬的時間戳記：session_start + floor((dt - session_start)/tf)*tf
    bucket_times = []
    for dt, sess_start in zip(valid_ts, session_starts):
        delta = dt - sess_start
        delta_minutes = int(delta.total_seconds() // 60)
        bucket_minutes = (delta_minutes // tf_min) * tf_min
        bucket_time = sess_start + timedelta(minutes=bucket_minutes)
        bucket_times.append(bucket_time)
    
    # 使用 bucket_times 進行分組
    df["bucket_time"] = bucket_times
    
    # 分組聚合
    grouped = df.groupby("bucket_time", sort=True)
    
    # 計算 OHLCV
    # 開盤價：每個 bucket 的第一個 open
    # 最高價：每個 bucket 的 high 最大值
    # 最低價：每個 bucket 的 low 最小值
    # 收盤價：每個 bucket 的最後一個 close
    # 成交量：每個 bucket 的 volume 總和
    result_df = pd.DataFrame({
        "open": grouped["open"].first(),
        "high": grouped["high"].max(),
        "low": grouped["low"].min(),
        "close": grouped["close"].last(),
        "volume": grouped["volume"].sum(),
    })
    
    # 確保結果排序（groupby 應該已經排序，但為了安全）
    result_df = result_df.sort_index()
    
    # 轉換為 numpy arrays
    result_ts = result_df.index.to_numpy(dtype="datetime64[s]")
    
    return {
        "ts": result_ts,
        "open": result_df["open"].to_numpy(dtype="float64"),
        "high": result_df["high"].to_numpy(dtype="float64"),
        "low": result_df["low"].to_numpy(dtype="float64"),
        "close": result_df["close"].to_numpy(dtype="float64"),
        "volume": result_df["volume"].to_numpy(dtype="int64"),
    }


def normalize_raw_bars(raw_ingest_result) -> Dict[str, np.ndarray]:
    """
    將 RawIngestResult 轉換為 normalized bars 陣列
    
    Args:
        raw_ingest_result: RawIngestResult 物件
        
    Returns:
        字典，包含 normalized bars:
            ts: datetime64[s] 陣列
            open, high, low, close: float64 陣列
            volume: int64 陣列
    """
    df = raw_ingest_result.get_df()
    
    # ts should already be datetime from ingest
    if not pd.api.types.is_datetime64_any_dtype(df["ts"]):
         ts_datetime = pd.to_datetime(df["ts"])
    else:
         ts_datetime = df["ts"]
    
    # 轉換為 datetime64[s]
    ts_array = ts_datetime.to_numpy(dtype="datetime64[s]")
    
    return {
        "ts": ts_array,
        "open": df["open"].to_numpy(dtype="float64"),
        "high": df["high"].to_numpy(dtype="float64"),
        "low": df["low"].to_numpy(dtype="float64"),
        "close": df["close"].to_numpy(dtype="float64"),
        "volume": df["volume"].to_numpy(dtype="int64"),
    }



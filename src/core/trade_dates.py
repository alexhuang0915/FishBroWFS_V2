from __future__ import annotations

from functools import lru_cache
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

import yaml


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]

def _normalize_symbol(value: str) -> str:
    """
    Accept both instrument symbols (e.g. 'CME.MNQ') and legacy dataset ids
    (e.g. 'CME.MNQ.60m.2020-2024') and return a symbol-like key.
    """
    s = (value or "").strip()
    parts = s.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return s


@lru_cache(maxsize=512)
def _instrument_exchange_config(instrument: str) -> tuple[str, str, str] | None:
    """
    Return (exchange, exchange_tz, trade_date_roll_time_local) for an instrument id like 'CME.MNQ'.
    """
    instrument = _normalize_symbol(instrument)
    p = _workspace_root() / "configs" / "registry" / "instruments.yaml"
    if not p.exists():
        return None
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for item in doc.get("instruments", []) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "") == instrument:
                exchange = str(item.get("exchange") or "").strip()
                exchange_tz = str(item.get("timezone") or "").strip()
                roll = str(item.get("trade_date_roll_time_local") or "").strip()
                if exchange and exchange_tz and roll:
                    return exchange, exchange_tz, roll
    except Exception:
        return None
    return None


def _parse_roll_hhmm(value: str) -> tuple[int, int]:
    s = (value or "").strip()
    hh, mm = s.split(":", 1)
    return int(hh), int(mm)


def _parse_hms(value: str) -> time:
    s = (value or "").strip()
    parts = s.split(":")
    if len(parts) == 2:
        hh, mm = parts
        return time(int(hh), int(mm), 0)
    if len(parts) == 3:
        hh, mm, ss = parts
        return time(int(hh), int(mm), int(ss))
    raise ValueError(f"invalid time: {value}")


def _time_in_range(t: time, start: time, end: time) -> bool:
    # Non-overnight
    if end > start:
        return start <= t < end
    # Overnight (wrap midnight)
    return t >= start or t < end


@lru_cache(maxsize=256)
def _profile_windows_config_for_instrument(instrument: str) -> tuple[str, str, list[dict[str, Any]]] | None:
    """
    Return (windows_tz, data_tz, windows[]) for an instrument, derived from its default_profile.
    """
    instrument = _normalize_symbol(instrument)
    p = _workspace_root() / "configs" / "registry" / "instruments.yaml"
    if not p.exists():
        return None
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        default_profile: str | None = None
        for item in doc.get("instruments", []) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "") == instrument:
                default_profile = str(item.get("default_profile") or "").strip() or None
                break
        if not default_profile:
            return None

        prof_path = _workspace_root() / "configs" / "profiles" / f"{default_profile}.yaml"
        if not prof_path.exists():
            return None
        prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
        windows = prof.get("windows") or []
        if not isinstance(windows, list) or not windows:
            return None
        windows_tz = str(prof.get("windows_tz") or prof.get("data_tz") or "Asia/Taipei")
        data_tz = str(prof.get("data_tz") or "Asia/Taipei")
        normalized: list[dict[str, Any]] = []
        for w in windows:
            if not isinstance(w, dict):
                continue
            state = str(w.get("state") or "").strip().upper()
            start = str(w.get("start") or "").strip()
            end = str(w.get("end") or "").strip()
            if state in {"TRADING", "BREAK"} and start and end:
                normalized.append({"state": state, "start": start, "end": end})
        if not normalized:
            return None
        return windows_tz, data_tz, normalized
    except Exception:
        return None


def trade_days_for_ts(
    ts_arr: Any,
    *,
    data_tz: str,
    exchange_tz: str,
    trade_date_roll_time_local: str,
):
    """
    Compute trade-date day buckets (datetime64[D]) for timestamps in data_tz.

    Rule:
      - Convert each timestamp to exchange_tz.
      - If local time >= roll_time, trade_date = local_date + 1 day, else local_date.

    Returns:
      numpy array of dtype datetime64[D], aligned with ts_arr order.
    """
    import numpy as np
    import pandas as pd

    if len(ts_arr) == 0:
        return np.array([], dtype="datetime64[D]")

    roll_h, roll_m = _parse_roll_hhmm(trade_date_roll_time_local)

    idx = pd.to_datetime(ts_arr.astype("datetime64[ns]"))
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize(data_tz)
    else:
        idx = idx.tz_convert(data_tz)
    exch = idx.tz_convert(exchange_tz)

    after_roll = (exch.hour > roll_h) | ((exch.hour == roll_h) & (exch.minute >= roll_m))
    base = exch.normalize()
    trade_dates = base + pd.to_timedelta(after_roll.astype(int), unit="D")
    # Return as datetime64[D] for fast boundary detection.
    return trade_dates.tz_localize(None).values.astype("datetime64[D]")


def trade_days_for_instrument_ts(ts_arr: Any, instrument: str, *, data_tz: str = "Asia/Taipei"):
    """
    Convenience wrapper using configs/registry/instruments.yaml to resolve exchange roll config.
    Falls back to calendar days if config not found.
    """
    import numpy as np

    cfg = _instrument_exchange_config(_normalize_symbol(instrument))
    if cfg is None:
        return ts_arr.astype("datetime64[D]")
    _, exchange_tz, roll = cfg
    try:
        return trade_days_for_ts(
            ts_arr,
            data_tz=data_tz,
            exchange_tz=exchange_tz,
            trade_date_roll_time_local=roll,
        )
    except Exception:
        return ts_arr.astype("datetime64[D]")


def session_start_taipei_for_instrument(ts: datetime, instrument: str, *, data_tz: str = "Asia/Taipei") -> datetime | None:
    """
    Compute the session start (Taipei-local naive datetime) for a timestamp.

    Mainline: session opens at trade_date_roll_time_local in exchange_tz (e.g., 17:00 Chicago),
    converted to data_tz (typically Asia/Taipei). DST is handled by timezone conversion.
    """
    cfg = _instrument_exchange_config(_normalize_symbol(instrument))
    if cfg is None:
        return None
    exchange, exchange_tz, roll = cfg
    if not exchange_tz or not roll:
        return None

    # Localize ts as data_tz if it's naive.
    if ts.tzinfo is None:
        ts_local = ts.replace(tzinfo=ZoneInfo(data_tz))
    else:
        ts_local = ts.astimezone(ZoneInfo(data_tz))

    ts_exch = ts_local.astimezone(ZoneInfo(exchange_tz))
    roll_h, roll_m = _parse_roll_hhmm(roll)
    roll_time = ts_exch.replace(hour=roll_h, minute=roll_m, second=0, microsecond=0)

    # Session start is today's roll if ts >= roll else yesterday's roll.
    if ts_exch >= roll_time:
        start_exch = roll_time
    else:
        start_exch = roll_time - timedelta(days=1)

    start_tpe = start_exch.astimezone(ZoneInfo(data_tz))
    return start_tpe.replace(tzinfo=None)


def is_trading_time_for_instrument(ts: datetime, instrument: str, *, data_tz: str = "Asia/Taipei") -> bool | None:
    """
    Determine if a timestamp is within trading time (not a daily maintenance break).

    Mainline rule for CME/CFE-style futures:
      - daily break is [roll_time - 1h, roll_time) in exchange local time
      - trading otherwise
    """
    cfg = _instrument_exchange_config(_normalize_symbol(instrument))
    if cfg is None:
        return None
    exchange, exchange_tz, roll = cfg
    if not exchange_tz or not roll:
        return None

    if ts.tzinfo is None:
        ts_local = ts.replace(tzinfo=ZoneInfo(data_tz))
    else:
        ts_local = ts.astimezone(ZoneInfo(data_tz))

    # CME/CFE: enforce daily 1h maintenance break relative to exchange roll time.
    if exchange in {"CME", "CFE"}:
        ts_exch = ts_local.astimezone(ZoneInfo(exchange_tz))
        roll_h, roll_m = _parse_roll_hhmm(roll)
        roll_dt = ts_exch.replace(hour=roll_h, minute=roll_m, second=0, microsecond=0)

        def _in_break(anchor: datetime) -> bool:
            return (anchor - timedelta(hours=1)) <= ts_exch < anchor

        if _in_break(roll_dt) or _in_break(roll_dt + timedelta(days=1)) or _in_break(roll_dt - timedelta(days=1)):
            return False
        return True

    # Other exchanges: if profile windows exist, classify by those windows (DST-aware).
    win_cfg = _profile_windows_config_for_instrument(_normalize_symbol(instrument))
    if win_cfg is None:
        return None
    windows_tz, prof_data_tz, windows = win_cfg
    try:
        ts_in_data = ts_local.astimezone(ZoneInfo(prof_data_tz))
        ts_in_windows = ts_in_data.astimezone(ZoneInfo(windows_tz))
        t = ts_in_windows.timetz().replace(tzinfo=None)

        # BREAK wins over TRADING if overlaps exist.
        for w in windows:
            if w["state"] != "BREAK":
                continue
            if _time_in_range(t, _parse_hms(w["start"]), _parse_hms(w["end"])):
                return False
        for w in windows:
            if w["state"] != "TRADING":
                continue
            if _time_in_range(t, _parse_hms(w["start"]), _parse_hms(w["end"])):
                return True
        # Outside any trading/break window => not tradable at this time.
        return False
    except Exception:
        return None

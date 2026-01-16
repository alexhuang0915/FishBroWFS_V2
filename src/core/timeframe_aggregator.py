
from __future__ import annotations

from datetime import time

import pandas as pd


class TimeframeAggregationError(ValueError):
    '''Raised when aggregation inputs are invalid.'''
    pass


class TimeframeAggregator:
    '''Pure aggregator that buckets 1m bars into derived timeframes around a roll time.'''

    def __init__(self, timeframe_min: int, roll_time: time):
        if timeframe_min <= 0:
            raise TimeframeAggregationError('timeframe_min must be positive')
        self.timeframe_min = timeframe_min
        self.roll_time = roll_time

    def _compute_anchor_start(self, ts_series: pd.Series) -> pd.Series:
        local = ts_series.dt.tz_localize(None)
        dates = local.dt.date
        roll_seconds = (
            self.roll_time.hour * 3600 +
            self.roll_time.minute * 60 +
            self.roll_time.second
        )
        before_roll = local.dt.time < self.roll_time
        anchor_date = dates.where(~before_roll, dates - pd.to_timedelta(1, unit='d'))
        anchor_start = pd.to_datetime(anchor_date.astype(str)) + pd.to_timedelta(roll_seconds, unit='s')
        return anchor_start

    def aggregate(self, bars: pd.DataFrame) -> pd.DataFrame:
        '''Aggregate minute bars into `timeframe_min` windows with window-end timestamps.'''
        required_columns = {"ts", "open", "high", "low", "close", "volume"}
        if not required_columns.issubset(bars.columns):
            missing = required_columns - set(bars.columns)
            raise TimeframeAggregationError(f"Missing required columns: {sorted(missing)}")

        df = bars.copy()
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.sort_values("ts")
        anchor_start = self._compute_anchor_start(df["ts"])
        minutes_from_anchor = ((df["ts"] - anchor_start).dt.total_seconds() // 60).astype(int)
        bucket = minutes_from_anchor // self.timeframe_min
        df["window_end"] = anchor_start + pd.to_timedelta((bucket + 1) * self.timeframe_min, unit='m')
        df["anchor_date"] = anchor_start.dt.date
        df["bucket"] = bucket

        grouped = df.groupby(["anchor_date", "bucket"], sort=True).agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            window_end=("window_end", "max"),
        )
        grouped = grouped.reset_index(drop=True)
        result = grouped.rename(columns={"window_end": "ts"})
        return result[["ts", "open", "high", "low", "close", "volume"]]

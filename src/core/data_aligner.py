from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(frozen=True)
class DataAlignmentMetrics:
    data1_bars_total: int
    data2_updates_total: int
    data2_hold_bars_total: int
    data2_hold_ratio: float
    max_consecutive_hold_bars: int
    top_hold_runs: list[dict[str, str | int]]


class DataAlignerError(ValueError):
    """Raised when alignment inputs are invalid."""


class DataAligner:
    """Pure logic aligning DATA2 onto DATA1 and reporting hold metrics."""

    def __init__(self, ts_column: str = "ts"):
        self.ts_column = ts_column

    def align(self, data1: pd.DataFrame, data2: pd.DataFrame) -> tuple[pd.DataFrame, DataAlignmentMetrics]:
        if self.ts_column not in data1.columns or self.ts_column not in data2.columns:
            raise DataAlignerError(f"Missing '{self.ts_column}' column in input data")

        data1_sorted = data1.copy()
        data1_sorted["_ts_norm"] = pd.to_datetime(data1_sorted[self.ts_column])
        data1_sorted = data1_sorted.sort_values("_ts_norm")

        data2_sorted = data2.copy()
        data2_sorted["_ts_norm"] = pd.to_datetime(data2_sorted[self.ts_column])
        data2_sorted = data2_sorted.sort_values("_ts_norm")

        data2_indexed = data2_sorted.set_index("_ts_norm")
        aligned = data2_indexed.reindex(data1_sorted["_ts_norm"], method="ffill")
        aligned = aligned.reset_index().rename(columns={"_ts_norm": self.ts_column})

        updates_mask = data1_sorted["_ts_norm"].isin(data2_indexed.index)
        if "close" not in aligned.columns:
            raise DataAlignerError("DATA2 input must contain a 'close' column for hold detection")
        hold_mask = (~updates_mask) & aligned["close"].notna()

        metrics = self._compute_metrics(
            data1_ts=data1_sorted["_ts_norm"],
            updates_mask=updates_mask,
            hold_mask=hold_mask,
        )

        result_df = aligned[[self.ts_column] + [c for c in aligned.columns if c != self.ts_column]]
        return result_df, metrics

    def _compute_metrics(self, data1_ts: pd.Series, updates_mask: pd.Series, hold_mask: pd.Series) -> DataAlignmentMetrics:
        total = int(len(data1_ts))
        updates = int(updates_mask.sum())
        hold_bars = int(hold_mask.sum())
        ratio = hold_bars / total if total else 0.0

        longest = 0
        runs = []
        current_start = None
        current_count = 0

        for ts, hold in zip(data1_ts, hold_mask):
            if hold:
                if current_count == 0:
                    current_start = ts
                current_count += 1
                current_end = ts
            elif current_count > 0:
                runs.append((current_start, current_end, current_count))
                longest = max(longest, current_count)
                current_count = 0
        if current_count > 0:
            runs.append((current_start, current_end, current_count))
            longest = max(longest, current_count)

        runs.sort(key=lambda entry: entry[2], reverse=True)
        top_runs = [
            {
                "start_ts": self._format_ts(entry[0]),
                "end_ts": self._format_ts(entry[1]),
                "count": entry[2],
            }
            for entry in runs[:5]
        ]

        return DataAlignmentMetrics(
            data1_bars_total=total,
            data2_updates_total=updates,
            data2_hold_bars_total=hold_bars,
            data2_hold_ratio=ratio,
            max_consecutive_hold_bars=longest,
            top_hold_runs=top_runs,
        )

    @staticmethod
    def _format_ts(value: pd.Timestamp | datetime | None) -> str:
        if value is None:
            return ""
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        return value.isoformat()

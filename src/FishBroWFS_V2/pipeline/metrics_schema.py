from __future__ import annotations

"""
Metrics column schema (single source of truth).

Defines the column order for metrics arrays returned by run_grid().
"""

# Column indices for metrics array (n_params, 3)
METRICS_COL_NET_PROFIT = 0
METRICS_COL_TRADES = 1
METRICS_COL_MAX_DD = 2

# Column names (for documentation/debugging)
METRICS_COLUMN_NAMES = ["net_profit", "trades", "max_dd"]

# Number of columns
METRICS_N_COLUMNS = 3

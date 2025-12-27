
"""Dtype configuration for memory optimization.

Centralized dtype definitions to avoid hardcoding throughout the codebase.
These dtypes are optimized for memory bandwidth while maintaining precision where needed.
"""

import numpy as np

# Stage0: Use float32 for price arrays to reduce memory bandwidth
PRICE_DTYPE_STAGE0 = np.float32

# Stage2: Keep float64 for final PnL accumulation (conservative)
PRICE_DTYPE_STAGE2 = np.float64

# Intent arrays: Use float64 for prices (strict parity), uint8 for enums
INTENT_PRICE_DTYPE = np.float64
INTENT_ENUM_DTYPE = np.uint8  # For role, kind, side

# Index arrays: Use int32 instead of int64 where possible
INDEX_DTYPE = np.int32  # For bar_index, param_id (if within int32 range)



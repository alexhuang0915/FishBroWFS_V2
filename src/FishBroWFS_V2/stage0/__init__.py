"""
Stage 0 Funnel (Vector/Proxy Filter)

Design goal:
  - Extremely cheap scoring/ranking for massive parameter grids.
  - No matcher, no orders, no fills, no state machine.
  - Must be vectorizable / nopython friendly.
"""

from .ma_proxy import stage0_score_ma_proxy
from .proxies import trend_proxy, vol_proxy, activity_proxy



from __future__ import annotations

import numpy as np


class RegimeFilterV1:
    """
    V1 Regime Filter strategy.

    Uses cross features to decide:
      - allow_trade (gate)
      - bias direction (target_dir)

    Execution is market via target_dir (open(T+1)).
    """

    def __init__(self, params: dict):
        self.direction_mode = str(params.get("direction_mode", "spread_z"))
        self.corr_min = float(params.get("corr_min", 0.20))
        self.r2_min = float(params.get("r2_min", 0.05))
        self.rel_vol_ratio_max = float(params.get("rel_vol_ratio_max", 3.0))
        self.spread_z_abs_min = float(params.get("spread_z_abs_min", 0.3))
        self.beta_abs_max = float(params.get("beta_abs_max", 5.0))

    def compute_orders_ctx(self, ctx, df=None):
        tf = int(getattr(ctx, "timeframe_min", 60))
        x = ctx.x()
        if x is None:
            n = len(df) if df is not None else 0
            return {"target_dir": np.zeros(n, dtype=np.int64)}

        corr = x.get_series("corr_60", tf).values
        beta = x.get_series("beta_60", tf).values
        r2 = x.get_series("r2_60", tf).values
        rel_vol = x.get_series("rel_vol_ratio", tf).values
        spread_z = x.get_series("spread_log_z_60", tf).values

        n = len(corr)
        target = np.zeros(n, dtype=np.int64)

        for i in range(n):
            c = corr[i]
            b = beta[i]
            r = r2[i]
            v = rel_vol[i]
            sz = spread_z[i]
            if np.isnan(c) or np.isnan(b) or np.isnan(r) or np.isnan(v) or np.isnan(sz):
                continue

            if c < self.corr_min:
                continue
            if r < self.r2_min:
                continue
            if abs(b) > self.beta_abs_max:
                continue
            if v > self.rel_vol_ratio_max:
                continue

            if self.direction_mode == "fixed_long":
                target[i] = 1
                continue
            if self.direction_mode == "fixed_short":
                target[i] = -1
                continue

            if abs(sz) < self.spread_z_abs_min:
                continue

            if self.direction_mode == "beta_sign":
                target[i] = 1 if b > 0 else -1
                continue

            if self.direction_mode == "rel_mom":
                try:
                    mom = x.get_series("rel_mom_20", tf).values[i]
                except Exception:
                    mom = np.nan
                if np.isnan(mom):
                    continue
                target[i] = 1 if mom > 0 else -1
                continue

            # default: spread_z
            target[i] = 1 if sz > 0 else -1

        return {"target_dir": target}

# src/portfolio/gatekeeper.py
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel


class AdmissionResult(BaseModel):
    allowed: bool
    correlation: float
    reason: str


class AdmissionGate:
    """Enforces Article IV.1: Non-Correlation Mandate."""

    @staticmethod
    def check_correlation(
        candidate_returns: pd.Series,
        portfolio_returns: Optional[pd.Series],
        threshold: float = 0.7,
        min_overlap: int = 30,
    ) -> AdmissionResult:
        # Genesis: first strategy gets a free pass
        if portfolio_returns is None or portfolio_returns.empty:
            return AdmissionResult(
                allowed=True,
                correlation=0.0,
                reason="Genesis Strategy (Portfolio Empty)",
            )

        # Align on index (dates/timestamps) and drop NaNs
        try:
            df = pd.concat(
                [candidate_returns.rename("candidate"), portfolio_returns.rename("portfolio")],
                axis=1,
                join="inner",
            ).dropna()
        except Exception as e:  # pragma: no cover (rare)
            return AdmissionResult(
                allowed=False,
                correlation=0.0,
                reason=f"Data Alignment Error: {e}",
            )

        # Minimum overlap
        if len(df) < min_overlap:
            return AdmissionResult(
                allowed=False,
                correlation=0.0,
                reason=f"Insufficient Overlap: {len(df)} < {min_overlap} required",
            )

        # Pearson correlation
        corr = float(df["candidate"].corr(df["portfolio"]))

        # Zero-variance / NaN correlation
        if np.isnan(corr):
            return AdmissionResult(
                allowed=False,
                correlation=0.0,
                reason="Correlation is NaN (Zero Variance in Returns)",
            )

        # Mandate enforcement
        if corr > threshold:
            return AdmissionResult(
                allowed=False,
                correlation=corr,
                reason=f"Correlation Violation: {corr:.6f} > {threshold}",
            )

        return AdmissionResult(
            allowed=True,
            correlation=corr,
            reason="Pass: Sufficiently Uncorrelated",
        )
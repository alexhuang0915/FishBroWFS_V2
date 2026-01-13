# tests/portfolio/test_gatekeeper.py
import numpy as np
import pandas as pd

from portfolio.gatekeeper import AdmissionGate


def _series(values, start="2024-01-01"):
    idx = pd.date_range(start=start, periods=len(values), freq="D")
    return pd.Series(values, index=idx)


def test_genesis_allows_when_portfolio_empty():
    cand = _series(np.random.default_rng(0).normal(size=60))
    res = AdmissionGate.check_correlation(cand, None)
    assert res.allowed is True
    assert res.correlation == 0.0
    assert "Genesis" in res.reason


def test_high_correlation_denied():
    rng = np.random.default_rng(1)
    port = _series(rng.normal(size=60))
    cand = port + _series(rng.normal(scale=1e-6, size=60)).values
    cand = _series(cand.values)

    res = AdmissionGate.check_correlation(cand, port, threshold=0.7, min_overlap=30)
    assert res.allowed is False
    assert res.correlation > 0.7
    assert "Violation" in res.reason


def test_inverse_correlation_allowed():
    rng = np.random.default_rng(2)
    port = _series(rng.normal(size=60))
    cand = _series((-port).values)

    res = AdmissionGate.check_correlation(cand, port, threshold=0.7, min_overlap=30)
    assert res.allowed is True
    assert res.correlation < 0.0  # should be near -1
    assert "Pass" in res.reason


def test_low_correlation_allowed():
    # Construct two independent RNG streams; with 60 points Pearson corr should be near 0
    rng1 = np.random.default_rng(3)
    rng2 = np.random.default_rng(4)
    port = _series(rng1.normal(size=90))
    cand = _series(rng2.normal(size=90))

    res = AdmissionGate.check_correlation(cand, port, threshold=0.7, min_overlap=30)
    # allow small chance of fluke; enforce "not violating threshold"
    assert res.allowed is (res.correlation <= 0.7)
    assert res.correlation <= 0.7


def test_insufficient_overlap_denied():
    rng = np.random.default_rng(5)
    # Only 20 overlapping points => must deny (min_overlap=30)
    port = _series(rng.normal(size=20), start="2024-01-01")
    cand = _series(rng.normal(size=20), start="2024-01-01")

    res = AdmissionGate.check_correlation(cand, port, threshold=0.7, min_overlap=30)
    assert res.allowed is False
    assert res.correlation == 0.0
    assert "Insufficient" in res.reason
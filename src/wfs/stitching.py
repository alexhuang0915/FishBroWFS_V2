"""
Stitching logic for IS/OOS/B&H equity series — FIXED RULE.

Function required:
- stitch_equity_series(by_season: list[list[Point]]) -> (stitched: list[Point], diags: list[Diag])

Point format:
- {"t": ISO str, "v": float}

Rule:
- last_end starts at 0.0
- For season N:
  - stitched_v = last_end + season_v
  - after season done: last_end = stitched_last_v

Diagnostics per season:
- season
- jump_abs = abs(season_first_v)
- jump_pct = 0 if abs(last_end_before)==0 else jump_abs/abs(last_end_before)
"""

from __future__ import annotations

from typing import List, Dict, Any, Tuple, TypedDict
from datetime import datetime
import json


class EquityPoint(TypedDict):
    """Single equity point."""
    t: str  # ISO timestamp
    v: float  # equity value


class StitchDiagnostic(TypedDict):
    """Diagnostic for stitching."""
    season: str
    jump_abs: float
    jump_pct: float


def stitch_equity_series(
    by_season: List[List[EquityPoint]],
    season_labels: List[str] = None
) -> Tuple[List[EquityPoint], List[StitchDiagnostic]]:
    """
    Stitch multiple season equity series into a continuous series.
    
    Args:
        by_season: List of season equity series, each as list of EquityPoint
        season_labels: Optional list of season labels (e.g., ["2020Q1", "2020Q2", ...])
    
    Returns:
        Tuple of (stitched_series, diagnostics)
    
    Rule:
        - last_end starts at 0.0
        - For season N:
            - stitched_v = last_end + season_v
            - after season done: last_end = stitched_last_v
    
    Diagnostics per season:
        - season label or index
        - jump_abs = abs(season_first_v)
        - jump_pct = 0 if abs(last_end_before)==0 else jump_abs/abs(last_end_before)
    """
    if not by_season:
        return [], []
    
    if season_labels is None:
        season_labels = [f"season_{i}" for i in range(len(by_season))]
    
    if len(by_season) != len(season_labels):
        raise ValueError("Number of season series must match number of season labels")
    
    stitched: List[EquityPoint] = []
    diagnostics: List[StitchDiagnostic] = []
    
    last_end = 0.0
    
    for season_idx, (season_series, season_label) in enumerate(zip(by_season, season_labels)):
        if not season_series:
            # Empty season, skip but record diagnostic
            diagnostics.append({
                "season": season_label,
                "jump_abs": 0.0,
                "jump_pct": 0.0
            })
            continue
        
        # Calculate jump from previous season's end
        season_first_v = season_series[0]["v"] if season_series else 0.0
        jump_abs = abs(season_first_v)
        jump_pct = 0.0 if abs(last_end) == 0.0 else (jump_abs / abs(last_end)) * 100.0
        
        diagnostics.append({
            "season": season_label,
            "jump_abs": jump_abs,
            "jump_pct": jump_pct
        })
        
        # Stitch this season's series
        for point in season_series:
            stitched_point: EquityPoint = {
                "t": point["t"],
                "v": point["v"] + last_end
            }
            stitched.append(stitched_point)
        
        # Update last_end to the last stitched value of this season
        if season_series:
            last_end = stitched[-1]["v"]
    
    return stitched, diagnostics


def normalize_series_to_start_at_zero(series: List[EquityPoint]) -> List[EquityPoint]:
    """
    Normalize a series to start at zero by subtracting the first value.
    
    Useful for B&H series that might start at non-zero values.
    """
    if not series:
        return []
    
    first_value = series[0]["v"]
    normalized = []
    
    for point in series:
        normalized.append({
            "t": point["t"],
            "v": point["v"] - first_value
        })
    
    return normalized


def create_synthetic_season_series(
    season_count: int = 3,
    points_per_season: int = 10,
    base_value: float = 100.0,
    noise_scale: float = 10.0
) -> Tuple[List[List[EquityPoint]], List[str]]:
    """
    Create synthetic season series for testing.
    
    Returns:
        Tuple of (list_of_season_series, season_labels)
    """
    import random
    from datetime import datetime, timedelta
    
    all_seasons = []
    season_labels = []
    
    for season_idx in range(season_count):
        season_label = f"202{season_idx}Q{season_idx % 4 + 1}"
        season_labels.append(season_label)
        
        season_series = []
        start_time = datetime(2020 + season_idx, 1, 1)
        
        # Create a random walk within the season
        current_value = base_value + random.uniform(-noise_scale, noise_scale)
        
        for point_idx in range(points_per_season):
            timestamp = start_time + timedelta(days=point_idx * 7)  # weekly points
            # Add some random movement
            current_value += random.uniform(-noise_scale, noise_scale)
            
            season_series.append({
                "t": timestamp.isoformat() + "Z",
                "v": current_value
            })
        
        all_seasons.append(season_series)
    
    return all_seasons, season_labels


# -----------------------------------------------------------------------------
# Test functions
# -----------------------------------------------------------------------------

def test_stitching_basic() -> None:
    """Basic stitching test."""
    # Create simple test data: two seasons with clear offsets
    season1 = [
        {"t": "2020-01-01T00:00:00Z", "v": 100.0},
        {"t": "2020-01-02T00:00:00Z", "v": 110.0},
        {"t": "2020-01-03T00:00:00Z", "v": 105.0},
    ]
    
    season2 = [
        {"t": "2020-04-01T00:00:00Z", "v": 200.0},
        {"t": "2020-04-02T00:00:00Z", "v": 210.0},
        {"t": "2020-04-03T00:00:00Z", "v": 205.0},
    ]
    
    by_season = [season1, season2]
    season_labels = ["2020Q1", "2020Q2"]
    
    stitched, diags = stitch_equity_series(by_season, season_labels)
    
    print("Basic stitching test:")
    print(f"  Season 1: {len(season1)} points, starts at {season1[0]['v']}")
    print(f"  Season 2: {len(season2)} points, starts at {season2[0]['v']}")
    print(f"  Stitched: {len(stitched)} points")
    
    # Check stitching logic
    # Season1 should be unchanged (last_end starts at 0)
    assert stitched[0]["v"] == 100.0
    assert stitched[2]["v"] == 105.0
    
    # Season2 should be offset by Season1's last value (105.0)
    assert stitched[3]["v"] == 200.0 + 105.0  # 305.0
    assert stitched[5]["v"] == 205.0 + 105.0  # 310.0
    
    print("  ✓ Basic stitching logic correct")
    
    # Check diagnostics
    assert len(diags) == 2
    assert diags[0]["season"] == "2020Q1"
    assert diags[0]["jump_abs"] == 100.0  # abs(season1[0]["v"])
    assert diags[0]["jump_pct"] == 0.0    # last_end was 0
    
    assert diags[1]["season"] == "2020Q2"
    assert diags[1]["jump_abs"] == 200.0  # abs(season2[0]["v"])
    # jump_pct should be 200.0 / 105.0 * 100 ≈ 190.48
    expected_pct = (200.0 / 105.0) * 100.0
    assert abs(diags[1]["jump_pct"] - expected_pct) < 0.01
    
    print("  ✓ Diagnostics correct")
    print("  ✓ All tests passed")


def test_stitching_empty_season() -> None:
    """Test stitching with empty season."""
    season1 = [
        {"t": "2020-01-01T00:00:00Z", "v": 100.0},
        {"t": "2020-01-02T00:00:00Z", "v": 110.0},
    ]
    
    season2 = []  # Empty season
    
    season3 = [
        {"t": "2020-07-01T00:00:00Z", "v": 300.0},
        {"t": "2020-07-02T00:00:00Z", "v": 310.0},
    ]
    
    by_season = [season1, season2, season3]
    season_labels = ["2020Q1", "2020Q2", "2020Q3"]
    
    stitched, diags = stitch_equity_series(by_season, season_labels)
    
    print("\nEmpty season test:")
    print(f"  Total stitched points: {len(stitched)} (should be 4)")
    print(f"  Diagnostics: {len(diags)} (should be 3)")
    
    assert len(stitched) == 4  # 2 from season1 + 2 from season3
    assert len(diags) == 3
    
    # Season3 should be offset by Season1's last value (110.0)
    assert stitched[2]["v"] == 300.0 + 110.0  # 410.0
    assert stitched[3]["v"] == 310.0 + 110.0  # 420.0
    
    print("  ✓ Empty season handled correctly")


if __name__ == "__main__":
    test_stitching_basic()
    test_stitching_empty_season()
    
    # Run synthetic test
    print("\nSynthetic data test:")
    synthetic_series, labels = create_synthetic_season_series(
        season_count=3,
        points_per_season=5
    )
    
    stitched, diags = stitch_equity_series(synthetic_series, labels)
    
    print(f"  Created {len(synthetic_series)} seasons")
    print(f"  Stitched into {len(stitched)} points")
    print(f"  Generated {len(diags)} diagnostics")
    
    # Show first few stitched points
    print("\n  First 5 stitched points:")
    for i, point in enumerate(stitched[:5]):
        print(f"    {i}: t={point['t'][:10]} v={point['v']:.2f}")
    
    print("\n✓ All stitching tests completed")
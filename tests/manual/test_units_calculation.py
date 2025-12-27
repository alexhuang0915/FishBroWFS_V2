#!/usr/bin/env python3
"""Test Units calculation for M1 Wizard."""

import sys
sys.path.insert(0, "src")

from control.job_api import calculate_units

def test_units_calculation():
    """Test various scenarios for units calculation."""
    
    print("Testing Units calculation...")
    print("Formula: Units = |DATA1.symbols| × |DATA1.timeframes| × |strategies| × |DATA2.filters|")
    print()
    
    # Test 1: Basic case without DATA2
    payload1 = {
        "data1": {
            "symbols": ["MNQ", "MXF", "MES"],
            "timeframes": ["60m", "120m"]
        },
        "strategy_id": "sma_cross_v1",
        "params": {"window": 20}
    }
    
    units1 = calculate_units(payload1)
    expected1 = 3 * 2 * 1 * 1  # 3 symbols × 2 timeframes × 1 strategy × 1 filter (no DATA2)
    print(f"Test 1 - Basic (no DATA2):")
    print(f"  Symbols: {len(payload1['data1']['symbols'])}")
    print(f"  Timeframes: {len(payload1['data1']['timeframes'])}")
    print(f"  Strategies: 1")
    print(f"  Filters: 1 (DATA2 disabled)")
    print(f"  Calculated: {units1}")
    print(f"  Expected: {expected1}")
    print(f"  {'✓ PASS' if units1 == expected1 else '✗ FAIL'}")
    print()
    
    # Test 2: With DATA2 and single filter
    payload2 = {
        "data1": {
            "symbols": ["MNQ", "MXF"],
            "timeframes": ["60m", "120m", "240m"]
        },
        "data2": {
            "filters": ["momentum"]
        },
        "enable_data2": True,
        "strategy_id": "breakout_channel_v1",
        "params": {"channel_width": 20}
    }
    
    units2 = calculate_units(payload2)
    expected2 = 2 * 3 * 1 * 1  # 2 symbols × 3 timeframes × 1 strategy × 1 filter
    print(f"Test 2 - With DATA2 (single filter):")
    print(f"  Symbols: {len(payload2['data1']['symbols'])}")
    print(f"  Timeframes: {len(payload2['data1']['timeframes'])}")
    print(f"  Strategies: 1")
    print(f"  Filters: 1")
    print(f"  Calculated: {units2}")
    print(f"  Expected: {expected2}")
    print(f"  {'✓ PASS' if units2 == expected2 else '✗ FAIL'}")
    print()
    
    # Test 3: Empty symbols list
    payload3 = {
        "data1": {
            "symbols": [],
            "timeframes": ["60m"]
        },
        "strategy_id": "sma_cross_v1",
        "params": {}
    }
    
    units3 = calculate_units(payload3)
    expected3 = 0 * 1 * 1 * 1  # 0 symbols × 1 timeframe × 1 strategy × 1 filter
    print(f"Test 3 - Empty symbols:")
    print(f"  Symbols: {len(payload3['data1']['symbols'])}")
    print(f"  Timeframes: {len(payload3['data1']['timeframes'])}")
    print(f"  Calculated: {units3}")
    print(f"  Expected: {expected3}")
    print(f"  {'✓ PASS' if units3 == expected3 else '✗ FAIL'}")
    print()
    
    # Test 4: DATA2 enabled but no filters (should treat as 1)
    payload4 = {
        "data1": {
            "symbols": ["MNQ"],
            "timeframes": ["60m"]
        },
        "data2": {},
        "enable_data2": True,
        "strategy_id": "sma_cross_v1",
        "params": {}
    }
    
    units4 = calculate_units(payload4)
    expected4 = 1 * 1 * 1 * 1  # 1 symbol × 1 timeframe × 1 strategy × 1 filter
    print(f"Test 4 - DATA2 enabled but empty filters:")
    print(f"  Symbols: {len(payload4['data1']['symbols'])}")
    print(f"  Timeframes: {len(payload4['data1']['timeframes'])}")
    print(f"  Calculated: {units4}")
    print(f"  Expected: {expected4}")
    print(f"  {'✓ PASS' if units4 == expected4 else '✗ FAIL'}")
    print()
    
    # Test 5: Complex case with multiple filters (though M1 requires single filter)
    payload5 = {
        "data1": {
            "symbols": ["MNQ", "MXF", "MES", "MYM"],
            "timeframes": ["15m", "30m", "60m"]
        },
        "data2": {
            "filters": ["momentum", "volatility", "trend"]
        },
        "enable_data2": True,
        "strategy_id": "mean_revert_zscore_v1",
        "params": {"zscore_threshold": 2.0}
    }
    
    units5 = calculate_units(payload5)
    expected5 = 4 * 3 * 1 * 3  # 4 symbols × 3 timeframes × 1 strategy × 3 filters
    print(f"Test 5 - Multiple filters (for completeness):")
    print(f"  Symbols: {len(payload5['data1']['symbols'])}")
    print(f"  Timeframes: {len(payload5['data1']['timeframes'])}")
    print(f"  Filters: {len(payload5['data2']['filters'])}")
    print(f"  Calculated: {units5}")
    print(f"  Expected: {expected5}")
    print(f"  {'✓ PASS' if units5 == expected5 else '✗ FAIL'}")
    print()
    
    # Summary
    print("=" * 50)
    print("Summary:")
    all_passed = all([units1 == expected1, units2 == expected2, units3 == expected3, 
                      units4 == expected4, units5 == expected5])
    
    if all_passed:
        print("✅ All tests passed! Units calculation is working correctly.")
    else:
        print("❌ Some tests failed. Check the calculations above.")
        sys.exit(1)

if __name__ == "__main__":
    test_units_calculation()
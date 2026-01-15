#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')

from features.registry import get_default_registry

reg = get_default_registry()
print("Registry specs count:", len(reg.specs))
# Find features for timeframe 60
for spec in reg.specs:
    if spec.timeframe_min == 60:
        if spec.name.startswith("sma_") or spec.name.startswith("hh_") or spec.name.startswith("ll_") or spec.name.startswith("atr_") or spec.name.startswith("vx_percentile_") or spec.name.startswith("percentile_") or spec.name == "ret_z_200" or spec.name == "session_vwap":
            print(f"  {spec.name} (window {spec.params.get('window', '?')})")

# Check for specific missing features
missing = ["sma_5", "sma_10", "sma_20", "sma_40", "hh_5", "hh_10", "hh_20", "hh_40", "ll_5", "ll_10", "ll_20", "ll_40", "atr_10", "atr_14", "vx_percentile_126", "vx_percentile_252", "ret_z_200", "session_vwap"]
for name in missing:
    specs = reg.specs_for_name(name)
    if specs:
        print(f"{name}: found for timeframes {[s.timeframe_min for s in specs]}")
    else:
        print(f"{name}: NOT FOUND")
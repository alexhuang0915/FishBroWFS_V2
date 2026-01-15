#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')

from features.registry import get_default_registry

reg = get_default_registry()
# List all features with name containing 'zscore' or 'ret_z'
for spec in reg.specs:
    if 'zscore' in spec.name or 'ret_z' in spec.name:
        print(f"{spec.name} (tf {spec.timeframe_min})")
# List all features with name containing 'session'
for spec in reg.specs:
    if 'session' in spec.name:
        print(f"{spec.name} (tf {spec.timeframe_min})")
# List all features with name containing 'percentile'
for spec in reg.specs:
    if 'percentile' in spec.name:
        print(f"{spec.name} (tf {spec.timeframe_min})")
# Check if vx_percentile exists
for spec in reg.specs:
    if 'vx_percentile' in spec.name:
        print(f"vx_percentile found: {spec.name}")
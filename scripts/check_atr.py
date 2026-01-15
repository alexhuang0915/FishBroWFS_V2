#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')

from features.registry import get_default_registry

reg = get_default_registry()
for spec in reg.specs:
    if spec.name == "atr_14" and spec.timeframe_min == 60:
        print(f"Found atr_14 for tf 60: {spec}")
        break
else:
    print("atr_14 not found for tf 60")
    # list all atr_14
    for spec in reg.specs:
        if spec.name == "atr_14":
            print(f"  atr_14 tf {spec.timeframe_min}")
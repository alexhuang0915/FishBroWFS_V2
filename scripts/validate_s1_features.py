#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')

from contracts.strategy_features import load_requirements_from_yaml
from config.registry.strategy_catalog import load_strategy_catalog
from features.registry import get_default_registry

catalog = load_strategy_catalog()
# Find S1 config path
for s in catalog.strategies:
    if s.id == "s1_v1":
        config_file = s.config_file
        # config file relative to configs/strategies/
        import os
        config_path = os.path.join("configs", "strategies", config_file)
        break
else:
    print("S1 not found")
    sys.exit(1)

print(f"Loading requirements from {config_path}")
req = load_requirements_from_yaml(config_path)
print(f"Requirements: {req}")

reg = get_default_registry()
missing = []
for feat in req.required + req.optional:
    specs = [spec for spec in reg.specs if spec.name == feat.name and spec.timeframe_min == feat.timeframe_min]
    if not specs:
        missing.append(f"{feat.name}@{feat.timeframe_min}m")
    else:
        print(f"  Found {feat.name}@{feat.timeframe_min}m")

if missing:
    print("Missing features:", missing)
else:
    print("All features registered.")
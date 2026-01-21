# Research Template Mainline (V1)

## Overview
This document defines the standard structure for research configuration files in FishBro WFS. All new strategies should start by copying `configs/templates/research_mainline.yaml`.

## Key Components

### 1. Determinism
Explicit seed control is required for `make check` reproducibility.
```yaml
determinism:
  default_seed: 42
```

### 2. Parameters Schema
Inputs must be typed and bounded to support UI generation (Ops Tab) and optimization ranges.
```yaml
parameters:
  my_param:
    type: "int"
    default: 10
    min: 1
    max: 100
```

### 3. Feature Dependencies
 Explicitly list required features. The feature engine will validate availability before running.
```yaml
features:
  - name: "vol_20"
    timeframe: 60
```

### 4. Registry Compliance
Strategies are agnostic to margin data. Margin parameters are loaded from `configs/registry/margins.yaml` at runtime via `instrument_id`. DO NOT include `margin_per_contract` or `multiplier` in strategy configs.

## Usage
`cp configs/templates/research_mainline.yaml configs/strategies/my_new_strategy.yaml`

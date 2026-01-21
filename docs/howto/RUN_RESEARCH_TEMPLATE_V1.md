# How to Run Research Template V1

## Overview
The `research_template_v1.yaml` provides a standardized starting point for all new strategy development in FishBro WFS. It ensures compliance with Versioning and Governance requirements out of the box.

## Usage

### 1. Copy the Template
Do not edit the template directly. Copy it to your new strategy directory:

```bash
mkdir -p configs/strategies/my_new_strategy
cp configs/strategies/wfs/research_template_v1.yaml configs/strategies/my_new_strategy/v1.yaml
```

### 2. Customize
Edit `v1.yaml`:
- **strategy_id**: Change to `my_new_strategy`
- **parameters**: Define your hyperparameters schema.
- **features**: List required input features.

### 3. Launch via CLI
```bash
python -m src.product.runtime.launcher run --config configs/strategies/my_new_strategy/v1.yaml
```

### 4. Launch via UI
1. Open Research Tab
2. Select "Run from Config"
3. Choose `my_new_strategy/v1.yaml`

## Best Practices
- **Never** remove the `version: "1.0"` field.
- **Always** define a schema for every parameter.
- **Always** set a determinstic seed.

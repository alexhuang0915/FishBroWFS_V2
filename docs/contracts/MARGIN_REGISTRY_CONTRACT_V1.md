# Margin Registry Contract V1

> **Status**: ACTIVE (Stage B)
> **Enforced By**: `tests/contracts/hygiene/test_config_dry_policy.py`

## 1. Single Source of Truth
- **Physical Metadata**: `configs/registry/instruments.yaml` (Currency, Multiplier, Tick Size).
- **Margin Data**: `configs/registry/margins.yaml` (Initial/Maintenance/Basis).

## 2. Portfolio Configuration
- Portfolio files (e.g., `configs/portfolio/instruments.yaml`) **refer** to data by ID.
- They MUST NOT define numeric values for margins or physical traits.

### Example (Valid)
```yaml
instruments:
  CME.MNQ:
    margin_profile_id: "CME_MICRO_INDEX_V1"
```

### Example (Invalid)
```yaml
instruments:
  CME.MNQ:
    initial_margin_per_contract: 4000.0  # FORBIDDEN: Numeric margin
    currency: USD                        # FORBIDDEN: Physical metadata
```

## 3. Profiles
- Margin profiles are defined in `configs/registry/margins.yaml` under `margin_profiles`.
- Keys are typically `EXCHANGE_ASSETCLASS_APP_VERSION`.

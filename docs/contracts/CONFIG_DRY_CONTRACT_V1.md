# Config DRY Contract V1

## Objective
Prevent configuration duplication drift between **Registry**, **Profiles**, and **Portfolio**.
Establish Single Source of Truth (__SSOT__) for instrument metadata.

## 1. Registry (`configs/registry/instruments.yaml`)
**Role**: The Universe Definition. The ONLY place where an instrument's physical properties are defined.

**Allowed Fields**:
- `id` (Primary Key, e.g., "CME.MNQ")
- `display_name`
- `type` (future, stock, etc.)
- `currency`
- `exchange`
- `multiplier`
- `tick_size`
- `tick_value`
- `timezone`
- `trade_date_roll_time_local`
- `default_profile`
- `default_timeframe`

## 2. Profiles (`configs/profiles/*.yaml`)
**Role**: Trading Configuration. How we trade an instrument (or set of instruments).
**Constraint**: MUST NOT redefine instrument physical metadata.

**Allowed Fields**:
- `symbol` (Must match a Registry ID)
- `mode` (e.g., FIXED_TPE)
- `cost_model` (commission, slippage)
- `windows` (trading sessions)
- `memory` (resource limits)
- `exchange_tz` / `data_tz` (Operational timezones, may match registry but defined for system usage)

**Forbidden Fields** (Must derive from Registry):
- `multiplier`
- `tick_size`
- `tick_value`
- `currency`

## 3. Portfolio (`configs/portfolio/*.yaml`)
**Role**: Selection & Allocation. What we trade and how much.
**Constraint**: MUST NOT define any instrument properties. ONLY references.

**Allowed Fields**:
- `instrument_ids` (List of strings matching Registry IDs)
- `strategy_ids` (List of strings)
- `seasons` (List of strings)
- `start_date` / `end_date`
- `policy_sha256` / `spec_sha256` (Integrity)
- `version`

**Forbidden Fields**:
- `instruments` (Block definition) - *Exception: `portfolio/instruments.yaml` (legacy margin config)*
- `profiles` (Block definition)
- Any physical metadata (`tick_size`, `tick_value`, `display_name`, `type`, `exchange`) under any key.
- *Note: `multiplier` and `currency` are temporarily allowed in `portfolio/instruments.yaml` only.*

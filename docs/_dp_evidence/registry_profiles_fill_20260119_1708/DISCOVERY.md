# DISCOVERY: Profile Registry Mismatch

## 1. Profile Loader Schema

Using `codebase_search` for "load_profiles", "ProfileSpec", "configs/profiles", "profile_id", we found:

- Profile loading is performed by `portfolio.instruments.load_instruments_config` (via `portfolio.instruments.ProfileSpec`).
- Profile YAML files are located under `configs/profiles/` and must match the schema defined by `ProfileSpec`.
- Required keys observed in existing profiles (`CME_MNQ_TPE_v1.yaml`, `TWF_MXF_TPE_v1.yaml`):
  - `profile_id`: string matching filename
  - `session.timezone`: string (e.g., "America/Chicago")
  - `session.trading_hours`: list of dicts with `day_of_week`, `start`, `end`, `halt`
  - `session.break_hours`: list of dicts with `day_of_week`, `start`, `end`
  - `bar.trade_date_roll_time_local`: string (e.g., "17:00")
  - `bar.period_minutes`: integer
  - `bar.first_tick_offset_minutes`: integer
  - `bar.max_lookback_bars`: integer
  - `bar.tz_aware`: boolean
  - `bar.timezone`: string (must match session.timezone)
- The loader uses `extra='forbid'` (no extra keys allowed).

## 2. Missing Profile IDs

Read `configs/registry/instruments.yaml` and extracted `default_profile` values.

Existing profiles:
- `CME_MNQ_TPE_v1.yaml`
- `TWF_MXF_TPE_v1.yaml`

Missing profiles (IDs referenced by instruments):
1. `CFE_VX_TPE_v1`
2. `CME_CL_TPE_v1`
3. `CME_ES_TPE_v1`
4. `CME_6J_TPE_v1`
5. `CME_MGC_TPE_v1`
6. `OSE_NK225M_TPE_v1`

These missing profiles caused the backend registry to expose only two instruments (CME.MNQ and TWF.MXF), leading to UI mismatch and BarPrepare build gating.

## 3. Root Cause

The `/api/v1/registry/instruments` endpoint loads instruments config, which filters out instruments whose `default_profile` cannot be resolved. Because the six profile YAMLs were missing, those instruments were omitted from the registry, causing the BarPrepare "Registry Mismatch" panel to flag missing instruments (especially CFE.VX).
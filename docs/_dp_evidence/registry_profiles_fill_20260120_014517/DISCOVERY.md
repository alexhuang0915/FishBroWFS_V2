# Discovery: Missing Profiles Causing Registry Unblock

## 1. Profile Loader Schema
- Profile files are YAML under `configs/profiles/` with schema defined by `ProfileSpec`.
- Required keys: `profile_id`, `session`, `bar`, `trade_date_roll_time_local`, `timezone`.
- Existing profiles: `CME_MNQ_TPE_v1.yaml` (Chicago timezone, roll 17:00), `TWF_MXF_TPE_v1.yaml` (Asia/Taipei, roll 15:00).

## 2. Missing Profile IDs
From `configs/registry/instruments.yaml`, each instrument references a `default_profile`. The following profiles were missing from `configs/profiles/`:

- CFE_VX_TPE_v1
- CME_CL_TPE_v1
- CME_ES_TPE_v1
- CME_6J_TPE_v1
- CME_MGC_TPE_v1
- OSE_NK225M_TPE_v1

## 3. Impact on Registry Endpoint
The API endpoint `/api/v1/registry/instruments` loads instruments from `configs/portfolio/instruments.yaml` (8 instruments). However the registry cache (`_INSTRUMENTS_CONFIG`) was stale because the prime endpoint did not reload after adding missing profiles. The backend had only two instruments (CME.MNQ, TWF.MXF) exposed because the cache was populated before the missing profiles existed, causing validation to filter? Actually the portfolio/instruments.yaml includes all 8 instruments regardless of profiles, but the cache may have been filtered by profile existence in some earlier validation. The exact cause is unclear, but after adding missing profiles and restarting the backend, the endpoint returns all eight instruments.

## 4. BarPrepare Registry Mismatch
The BarPrepare UI panel compares instruments in `configs/registry/instruments.yaml` with available profiles. Missing profiles cause the mismatch panel to flag instruments (specifically CFE.VX). Adding the missing profiles resolves the mismatch.

## 5. Verification
- `make check` passes (tests updated).
- HTTP endpoint `/api/v1/registry/instruments` now returns all eight instrument IDs.
- BarPrepare mismatch panel should no longer flag missing instruments.
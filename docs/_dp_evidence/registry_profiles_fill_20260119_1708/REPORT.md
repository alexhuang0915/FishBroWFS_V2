# REPORT: Missing Profile YAML Creation

## Files Created

Under `configs/profiles/`:

1. `CFE_VX_TPE_v1.yaml` – CFE VX (CBOE Volatility Index) Chicago timezone, roll 17:00
2. `CME_CL_TPE_v1.yaml` – CME CL (Crude Oil) Chicago timezone, roll 17:00
3. `CME_ES_TPE_v1.yaml` – CME ES (E‑mini S&P 500) Chicago timezone, roll 17:00
4. `CME_6J_TPE_v1.yaml` – CME 6J (Japanese Yen) Chicago timezone, roll 17:00
5. `CME_MGC_TPE_v1.yaml` – CME MGC (Micro Gold) Chicago timezone, roll 17:00
6. `OSE_NK225M_TPE_v1.yaml` – OSE NK225M (Nikkei 225 Mini) Tokyo timezone, roll 15:00

## Rationale

- Used `CME_MNQ_TPE_v1.yaml` as template for all Chicago‑time products (CME.*, CFE.*).
- Used `TWF_MXF_TPE_v1.yaml` as reference for Asia timezone formatting (OSE.*).
- Each profile sets `profile_id` exactly matching the filename and the `default_profile` reference in `configs/registry/instruments.yaml`.
- Session timezone and `bar.trade_date_roll_time_local` are consistent with the instrument’s exchange:
  - Chicago products: `America/Chicago`, `17:00`
  - OSE (Tokyo): `Asia/Tokyo`, `15:00`
- All other keys (trading hours, break hours, bar period, etc.) are copied from the corresponding template, preserving the same session structure.
- No new semantics introduced; profiles are minimal and compatible with the existing loader.

## Verification of Schema Compliance

Each new YAML file passes the `ProfileSpec` validation (extra='forbid'), ensuring they will be accepted by the profile loader.

## Impact

With these six profiles added, the backend registry can now resolve all eight instruments listed in `configs/registry/instruments.yaml`:

- CME.MNQ
- TWF.MXF
- CFE.VX
- CME.CL
- CME.ES
- CME.6J
- CME.MGC
- OSE.NK225M

The `/api/v1/registry/instruments` endpoint will return all eight symbols, eliminating the “Registry Mismatch” warning in BarPrepare and unblocking the BUILD gate.
# Dev Log (Project Notes)

Purpose: a lightweight, append-friendly log for **human + AI** collaboration.

- This is **not** SSOT; it points to the SSOT docs.
- Keep entries short and link to the spec that changed.

## 2026-01-25

- Locked V1 execution semantics + WFS search + stops + cross features in `docs/SPEC_ENGINE_V1.md`.
- Unified base currency to **TWD** and fixed FX constants in `configs/registry/fx.yaml`.
- Moved trading costs SSOT into `configs/registry/instruments.yaml`:
  - `cost_model.commission_per_side` (instrument currency)
  - `cost_model.slippage_per_side_ticks` (V1 fixed = 1)
  - Profiles must not define `cost_model` (fail-closed guard enforced in code).
- Started implementation of V1 cross features:
  - Added deterministic compute module `src/core/features/cross.py`
  - Added unit test `tests/core/test_cross_features_v1.py`

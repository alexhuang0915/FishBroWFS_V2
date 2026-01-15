# Feature Universe Manifest v1 – Scope Document

## Purpose
This document clarifies the scope and guarantees of the Feature Universe Manifest v1 (`feature_universe_manifest_v1.json`). It is a **read‑only, deterministic** artifact that makes the feature universe visible and auditable.

## What v1 Guarantees

### 1. **Canonical Window Sets**
The manifest includes exactly two window‑set categories, as defined by the Constitution:

- **general**: `[5, 10, 20, 40, 80, 160, 252]`
- **stats**: `[63, 126, 252]`

Every feature variant’s `window_applicability` field indicates whether its window belongs to the *general* set, the *stats* set, both, or neither.

### 2. **Feature Families G1–G10**
All ten feature families (G1–G10) are listed, each with:
- A stable `id` (e.g., `"G1"`)
- A human‑readable `family` name (e.g., `"ma"`)
- A list of variants (or an empty list for placeholder families)

### 3. **Variant Metadata**
For each variant the manifest records:
- `name` – the feature’s internal identifier (e.g., `"ema_10"`)
- `window` – the look‑back window used by the feature
- `lookback_bars` – the number of bars required to compute the feature (equal to `window`)
- `timeframe_min` – the minimum bar size (in minutes) for which the variant is defined
- `implementation_source` – the Python module and symbol that implements the feature
- `params` – any parameters passed to the feature constructor (currently only `window`)
- `window_applicability` – a boolean flag for each window‑set category

### 4. **Determinism**
The manifest is **byte‑identical** across repeated runs on the same codebase and data. No caching or random elements affect its content.

### 5. **Read‑Only**
The manifest is never written as a cache; it is generated fresh each time the script `scripts/generate_feature_universe_manifest.py` is executed. The output is stored solely in:
```
outputs/_dp_evidence/feature_universe_manifest_v1/
```

## What v1 Does **Not** Guarantee

### 1. **Complete Implementation of All Families**
- **G6 (structural)** – fully implemented (`daily_pivot`, `swing_high(N)`, `swing_low(N)`)
- **G9 (volume)** – **placeholder only**. The manifest lists the family but contains **zero variants**. Implementation is deferred to a later phase.
- **G10 (correlation)** – **placeholder only**. The manifest lists the family but contains **zero variants**. Implementation is deferred to a later phase.

### 2. **Runtime Correctness**
The manifest describes the *registered* feature universe, not whether features work correctly at runtime. It does not guarantee:
- That the underlying implementation functions are bug‑free
- That the feature can be computed for all instruments/timeframes
- That the feature’s output matches any external specification

### 3. **Performance or Scalability**
The manifest does not provide any performance metrics (e.g., computation speed, memory footprint) or scalability guarantees.

### 4. **Cross‑Series Features**
G10 (correlation) is intended to be a **cross‑series** feature. The v1 manifest does **not** implement cross‑series logic; it merely reserves the family identifier.

### 5. **Window‑Set Extensibility**
The window sets are **fixed** to the values listed above. New windows (e.g., 14, 30, 50) are not part of the canonical sets and will be marked as `"general": false, "stats": false`.

## Usage Notes

- **Auditing**: The manifest can be used to verify that the feature universe matches the Constitution’s window‑set definitions.
- **Integration**: Downstream tools (e.g., strategy builders, feature selectors) may rely on the manifest to know which windows are considered “general” or “stats”.
- **Placeholder Families**: Code that expects G9 or G10 variants must handle empty variant lists gracefully.

## Future Versions

- **v2** may add G9 and G10 implementations, cross‑series support, and additional metadata (e.g., feature stability scores).
- **v2** may extend the window‑set definitions if the Constitution is amended.

---

*Generated as part of the HARD DELETE + FORCED REPAIR cycle (2026‑01‑15).*
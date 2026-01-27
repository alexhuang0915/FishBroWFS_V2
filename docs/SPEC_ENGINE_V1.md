# Alignment: Data2 / Features / Execution (SSOT Draft)

This document records the decisions aligned in chat. It is **the SSOT** for:
- Strategy inputs (`data1` + `data2`)
- Feature packaging (`B1` bundles)
- Cross-asset feature structure
- Execution + stop-entry semantics (spec only; not necessarily implemented yet)

Status: **Aligned / Not Implemented (unless stated otherwise)**.

---

## 0) Quick Summary (Aligned)

This section is a snapshot of the aligned SSOT, to reduce scrolling. Details remain in the sections below.

- **Data model (V1):** strategies support `data1 + data2`, where `data2` is **optional and at most one** (no engine auto-pick).
- **Features (B1):** strategy consumes bundles via `ctx.d1()`, `ctx.d2()`, `ctx.x()` (where `x` is data1 vs data2 cross bundle).
- **Data2 alignment:** align data2 onto data1 timeline (same timeframe + rollover), then forward-fill as permitted; compute coverage missing_ratio%.
  - Coverage thresholds (V1): `WARN >= 2%`, `HIGH >= 5%` (warnings only; never fail-closed).
  - Warnings stored both run-level and window-level.
- **Execution (V1):** signal at `T`, fill at `open(T+1)`; fixed **1 contract**; fixed slippage ticks per fill per side; fixed commission per fill per side (fills only).
- **PnL (V1):** mark-to-market using bar `close`; PnL unit is **money** in base currency (**TWD**).
  - FX model (V1): **fixed constants** only (no time-series FX); SSOT is `configs/registry/fx.yaml`; actual values used must be written into result/manifest.
  - Default `initial_equity = 10_000.0` (TWD).
- **Stops (V1):** stop-entry + protective stop-loss exit; gap-through fills at `open`, otherwise fill at stop price; ambiguities => `ambiguous_fill` => **do not trade**.
- **WFS search (V1):** two-phase (cheap → rich), aggregate across windows then select:
  - `N_total = 120`, `top_k = 100`
  - screening score: `net / max(abs(mdd), mdd_floor)`, where `mdd_floor = 0.02 * initial_equity`
  - `top_k` scope is per `(strategy_id, instrument, timeframe, data2_id/None)`.

## 0.1 Open Decisions (Only: Cross Features)

Everything else is aligned. Cross-features are locked for V1 as described in section **3.3**.
Future expansion is allowed only as an explicit version bump (e.g., V2), not as a silent change.

---

## 1) Strategy Data Model (All Strategies)

### 1.1 Data1 + Data2
- **Data1**: primary tradable instrument (the one we trade).
- **Data2**: reference instrument (read-only input).
- All strategies must support **`data1 + data2`** (no “single-instrument only” assumption).

### 1.2 Data2 Selection Policy
- **Explicit (V1)**: strategy config declares **at most one** `data2` instrument.
  - Example concept: `use_data2 = ["CFE.VX"]` (length must be `0` or `1`)
- No “auto-pick” of `data2` at engine level (for reproducibility + debuggability).

> Note: We may lift this restriction later (0..N), but V1 keeps it 0..1 to reduce complexity.

### 1.3 Strategy Registry (SSOT)
- The only supported source of available strategies is `configs/registry/strategies.yaml`.
  - Engine/TUI must resolve `strategy_id -> config_file` via this registry.
- Legacy strategy configs may exist under `configs/strategies/_legacy/` for reference, but **must not** be selectable or runnable.

### 1.4 Feature Packs (SSOT)
- Feature packs are stored in `configs/registry/feature_packs.yaml`.
- Strategy configs should reference packs using **pack + overrides** to stay concise:
  - `features.<group>.pack` (pack id)
  - `features.<group>.add` (list of feature refs)
  - `features.<group>.remove` (list of feature names)
- Engine must expand packs deterministically and record the final feature list in results/manifest for auditability.

---

## 2) Feature Packaging (B1: Bundles + Helper API)

Strategies consume a `FeatureContext` (name may vary) with three partitions:
- `data1`: **one** bundle
- `data2`: optional bundle (V1: 0..1)
- `cross`: optional bundle (V1: data1 vs the single data2)

### 2.1 Helper API (Strategy-Side Only)
Strategies should not concatenate/flatten columns manually. They should use helpers:
- `ctx.d1()` → data1 bundle
- `ctx.d2()` → data2 bundle (or None if not present)
- `ctx.x()` → cross bundle (or None if not present)

> Note: Internally we may still represent data2/cross as maps keyed by `data2_id` for forward-compat,
> but V1 strategy code should treat them as single optional bundles.

---

## 3) Cross-Asset Feature Structure (Option A)

### 3.1 Cross Map Layout
- `cross` is a single bundle for **data1 vs the configured data2** (V1: 0..1).

### 3.2 Naming Convention (Prefix Groups)
Cross features are grouped by name prefixes (single bundle, internally grouped):
- `spread_*`  (ratio/log-ratio/spread related)
- `corr_*`    (rolling correlation / dependency)
- `beta_*`    (rolling beta / regression-like dependency)
- `rel_*`     (relative return / relative momentum)

### 3.3 Cross Features V1 (Chosen: B / Core Pack)

V1 locks a **deterministic, testable** cross feature set for speed and reproducibility. The `cross` bundle is built
for **data1 vs the single configured data2** (V1: 0..1).

#### 3.3.1 Alignment Rule (MUST)
- Always **align + forward-fill** `data2` to the `data1` timeline first, then compute all returns/ATR/corr.
- Do **not** compute on raw `data2` then align (prevents off-by-one and window inconsistency).

#### 3.3.2 Base Series (Fixed)
Let `c1,o1,h1,l1` be data1 OHLC; and `c2,o2,h2,l2` be **aligned + ffilled** data2 OHLC.

- **Log returns (V1)**:
  - `ret1[t] = ln(c1[t] / c1[t-1])`
  - `ret2[t] = ln(c2[t] / c2[t-1])`
  - `ret*[0] = NaN`

- **True Range (standard)**:
  - `tr[t] = max(h[t]-l[t], abs(h[t]-c[t-1]), abs(l[t]-c[t-1]))`
  - `tr[0] = h[0]-l[0]`

- **ATR smoothing (V1: SMA, locked)**:
  - `atr_14[t] = mean(tr[t-13:t])` (SMA over 14 points)
  - First 13 bars are `NaN` due to lookback.

#### 3.3.3 Rolling / Missing Rules (Deterministic)
- Lookback不足 → `NaN` (no partial windows).
- Rolling windows containing any `NaN` → output `NaN` (no `dropna`).
- Any division by zero / std==0 → output `NaN`.
- Rolling z-score uses **population std** (`ddof=0`) for consistency with current deterministic numpy implementation.
- ATR (V1) is **NaN-aware and strict**:
  - If there is a missing segment (e.g., aligned Data2 is `NaN` before first bar), ATR remains `NaN` until it sees
    **14 consecutive valid TR points**, then it resumes producing values.

#### 3.3.4 V1 Column List (Fixed)

All columns live in `cross` bundle as fixed names.

Window set (V1 fixed): `N ∈ {20, 60, 120}` and momentum windows `N ∈ {5, 20, 60, 120}`.

**spread_***
- `spread_log[t] = ln(c1[t] / c2[t])` (if `c1<=0` or `c2<=0` → `NaN`)
- `spread_log_z_20`, `spread_log_z_60`, `spread_log_z_120`

**rel_***
- `rel_ret_1[t] = ret1[t] - ret2[t]`
- `rel_mom_5`, `rel_mom_20`, `rel_mom_60`, `rel_mom_120`
- `rel_vol_ratio[t] = (atr1_14[t] / c1[t]) / (atr2_14[t] / c2[t])` (ATR% ratio; dimensionless, cross-asset safe)
- `rel_vol_z_20`, `rel_vol_z_60`, `rel_vol_z_120`

**corr_***
- `corr_20`, `corr_60`, `corr_120` (Pearson correlation on log-returns)
- `corr_abs_20`, `corr_abs_60`, `corr_abs_120`

**beta_*** (rolling OLS with intercept; strict windows)
- `beta_20`, `beta_60`, `beta_120`
- `alpha_60`, `alpha_120`
- `r2_60`, `r2_120`
- `resid_std_60`, `resid_std_120` (population std of residuals)

**vol_***
- `vol_atr1_14_pct = atr1_14 / c1`
- `vol_atr2_14_pct = atr2_14 / c2`
- `vol_atr_pct_spread = vol_atr1_14_pct - vol_atr2_14_pct`
- `vol_atr_pct_spread_z_20`, `vol_atr_pct_spread_z_60`, `vol_atr_pct_spread_z_120`

#### 3.3.5 Naming Decision (V1)
- `rel_ret_1` is the only canonical name. `spread_ret_1` does **not** exist in V1 to avoid duplicate synonyms.

---

## 4) Data2 Alignment + Coverage Policy

### 4.1 Alignment
- Data2 is aligned onto the **data1 timeline** (same timeframe + same rollover rules).
- Missing bars are handled via **forward-fill** (when permitted).

### 4.1b Resample Anchor Start (SSOT)
- Shared bars resample is **clipped** to start at **`2019-01-01 00:00:00`** (inclusive) for all instruments.
  - Any raw data earlier than this is dropped before writing `normalized_bars.npz` and `resampled_*.npz`.
  - Purpose: keep a consistent dataset horizon across instruments and reduce unnecessary historical baggage.

### 4.2 Coverage Warning (Not Fail-Closed)
- Coverage is measured as **missing ratio (%)** of aligned data2 points.
- **Do not fail** the job/run due to coverage; instead, write warnings to the result.
- Coverage is computed **per window** (WFS windows).
- **MultiCharts-style definition (V1):**
  - Data1 drives the timeline.
  - Data2 “no update at this timestamp” is **not** missing; it is **hold** (forward-filled last known value).
  - `missing_ratio%` counts only bars where Data2 is still unavailable **after alignment + forward-fill**
    (i.e., aligned Data2 is `NaN`, typically before the first Data2 bar exists).
- For auditability, we also record:
  - `data2_update_ratio%`: ratio of bars where Data2 had a real update at the exact timestamp.
  - `data2_hold_ratio%`: ratio of bars that are hold/ffill (not missing).
- Warning thresholds (V1):
  - `WARN` if missing_ratio ≥ **2.0%**
  - `HIGH` if missing_ratio ≥ **5.0%**
- When threshold is exceeded, emit a human-readable warning/risk flag, e.g.:
  - `DATA2_COVERAGE_LOW: CFE.VX missing_ratio=3.2% (threshold=2.0%)`

### 4.3 Data2 Pairing SSOT (Matrix Runs)

V1 runtime still uses **0..1** `data2` per run, but orchestration supports a **matrix**:
- Same strategy + same parameter candidates + same data1
- Different `data2` candidates
- Each `(data1, data2)` is an **independent run** (independent grading, `top_k`, and portfolio candidacy)

SSOT: `configs/registry/data2_pairs.yaml`.

---

## 5) Execution Logic Alignment (Spec)

These rules define the intended execution semantics (even if current code is still vectorized).

### 5.1 Base Fill Model
- Signal computed at **T**.
- Entry/adjustment fill occurs at **`open(T+1)`**.
- Position sizing: **fixed 1 contract**.
- Slippage: **fixed per fill per side** (charged **only on fills**; cancel/replace is free).
- Commission: **fixed per fill per side** (charged **only on fills**; cancel/replace is free).
- Tick size / multiplier / currency / exchange roll rules: loaded from **instrument registry** (SSOT).
  - V1 rule: **missing tick_size/multiplier/currency is fail-closed** (invalid instrument spec).

### 5.2 Position-Target Mode (A)
- Strategy outputs `target_dir ∈ {-1, 0, +1}` each bar.
- Engine adjusts to target using the fill model above.

### 5.3 PnL / Mark-to-Market (V1)
- **Event-based fills**: entry/exit realized using the defined fill price rules.
- **Mark-to-market**: while holding a position, equity is updated each bar using **close** (for MDD / underwater-days).
- PnL unit: **money in base currency** (V1 base currency is **TWD**).
- If instrument currency != TWD, convert using **fixed FX constants** (not a time series).

### 5.4 Base Currency + FX (V1)
- Base currency: **TWD**
- FX model: **fixed constants only** (no time-series FX alignment in V1)
- SSOT: `configs/registry/fx.yaml`
- The actual FX constants used must be written into result/manifest for auditability.

### 5.5 Default Initial Equity (V1)
- `initial_equity = 10_000.0` (base currency, TWD)

### 5.6 Costs SSOT (V1)

V1 locks a simple, deterministic cash-cost model:

- Commission is specified in the **instrument currency** and converted to base currency (TWD) via `configs/registry/fx.yaml`.
- Slippage is specified in **ticks per side**, then converted to cash using `tick_value` (instrument currency), then converted to base currency via `configs/registry/fx.yaml`.
- SSOT source: **instrument registry** `configs/registry/instruments.yaml` under each instrument:
  - `cost_model.commission_per_side`
  - `cost_model.slippage_per_side_ticks`
- Charging rule:
  - charged **per fill per side**
  - charged **only on fills** (cancel/replace is free)

V1 rule: if an instrument is missing `cost_model` fields, the run is **fail-closed** (invalid instrument spec).
Profiles must **not** define `cost_model` (if present, treat as invalid config).

---

## 6) Stop-Entry (Breakout) Alignment (Spec)

Stop orders are used for **entry** (not just exit).

### 6.1 Trigger Source
- Use **`high/low(T+1)`** to determine stop trigger.
  - Long stop triggers if `high(T+1) >= long_stop`.
  - Short stop triggers if `low(T+1) <= short_stop`.

### 6.2 Gap-Through Fill
- If `open(T+1)` crosses the stop price (gap through):
  - Fill price is **`open(T+1)`** (not the stop price).

### 6.2b Non-Gap Trigger Fill (V1)
- If the stop triggers intrabar (not a gap-through):
  - Fill price is **the stop price** (`long_stop` / `short_stop`).

### 6.3 Ambiguous Same-Bar Multi-Trigger (Pessimistic)
- If both sides would trigger in the same bar:
  - Mark as **ambiguous_fill** and **do not trade**.
  - Record a reason in the result.

### 6.4 Stop Price Unit
- Stop prices are **absolute prices** (same scale as OHLC).

---

## 7) Strategy Stop Output Contract (Spec)

Per bar, strategies output:
- `target_dir ∈ {-1, 0, +1}`
- `long_stop` (absolute price) or `None`
- `short_stop` (absolute price) or `None`

Hard rules:
- If `target_dir = +1`: `long_stop` required, `short_stop = None`
- If `target_dir = -1`: `short_stop` required, `long_stop = None`
- If `target_dir = 0`: both stops must be `None`

---

## 8) Stop Order Lifecycle (Spec)

### 8.1 Condition-Type Determines Order TTL
- **Cross over / under** (event condition): stop is valid for **1 bar** only.
- **>= / <=** (state condition): stop may remain **active across bars** until changed or triggered.

### 8.2 One Stop Per Direction
- At any time, there can be **at most one** stop order per direction.

### 8.3 Replace Policy
- If a new same-direction stop is produced while one exists: **Replace** the old stop with the new stop.

### 8.4 Direction Change Cancels Old Orders
- If `target_dir` changes direction or becomes `0`:
  - Cancel all **old-direction** pending stop orders immediately.

---

## 9) WFS Two-Phase Search (B: Cheap → Rich)

We will use a **two-stage** WFS parameter search:

### 9.1 Phase 1: Cheap Screening
- Run cheap evaluation for all parameter candidates.
- **Aggregate across windows first**, then select `top_k` once.
- Hard filters:
  - `net > 0`
  - `trades_total >= N_total` (**total across all windows**)
- Screening score (**clamped ratio**, deterministic):
  - `score = net / max(abs(mdd), mdd_floor)`
  - `mdd_floor = 0.02 * initial_equity` (2% equity floor, prevents ratio blow-up)

**V1 defaults (aligned):**
- `N_total = 120`
- `top_k = 100`

### 9.1b Cheap Aggregation (V1)
Cheap metrics are computed per window, then aggregated across windows before ranking:
- `net = sum(window.net)` (in base currency)
- `mdd = max(abs(window.mdd))` (conservative, cheap; rich phase may recompute stitched MDD)
- `trades_total = sum(window.trades)`

### 9.2 Phase 2: Rich Evaluation
- Evaluate only the Phase 1 `top_k` candidates with full outputs and governance scoring.
- Final verdict/grade is based on the WFS policy metrics (pass_rate, trades, wfe, ulcer, underwater-days, etc.).

**V1 rich output (aligned, 5A):**
- Per-window: `net`, `mdd`, `trades`, `pass`, `fail_reasons`, `data2_missing_ratio%`
- Stitched OOS equity: **daily downsample**
  - Daily definition (V1): **trade-day bucket**, take the **last bar close** of that trade day.
  - Trade-day identity uses the instrument calendar logic (see `core.trade_dates`).
- Verdict: grade + hard_gates_triggered + summary

### 9.5 WFS Policy SSOT (V1)

WFS gating + grading is controlled by a single SSOT policy file:
- `configs/policies/wfs/policy_v1_default.yaml`

V1 policy values currently locked in that file:
- `pass_rate >= 0.60`
- `trades >= 50`
- `wfe >= 0.50`
- `ulcer_index <= 20.0`
- `max_underwater_days <= 90` (trading days; see section 13)

### 9.3 Observability / Audit
Results must record:
- Phase 1: candidate count, `N_total`, `top_k`, score formula, `mdd_floor`, and window aggregation method.
- Phase 2: chosen params and final evaluation summary.

### 9.4 `top_k` Scope (V1)
- `top_k` is selected **per (strategy_id, instrument, timeframe, data2_id/None)** to avoid cross-contamination.

---

## 10) Data2 Coverage Warning Placement (V1)

Coverage warnings are written in two layers (aligned):
- Run-level: `result.warnings[]` (summary)
- Window-level: `windows[i].warnings[]` (includes numeric `missing_ratio%`)

---

## 11) Stop-Exit (Protective Stop-Loss) (V1)

V1 supports **stop-loss exits** in addition to stop-entry.

### 11.1 Scope
- Stop-exit is **protective stop-loss only** (no take-profit / no OCO in V1).

### 11.2 Strategy Output Additions (Exit Stops)
Add two optional, absolute-price fields (meaningful only when in position):
- `exit_long_stop`: used only while holding **long**
- `exit_short_stop`: used only while holding **short**

Hard rules:
- While holding long: `exit_long_stop` required, `exit_short_stop = None`
- While holding short: `exit_short_stop` required, `exit_long_stop = None`
- While flat: both exit stops must be `None`

### 11.3 Trigger + Fill Rules
- Long stop-loss triggers if `low(i) <= exit_long_stop`.
- Short stop-loss triggers if `high(i) >= exit_short_stop`.
- Gap-through:
  - Long: if `open(i) <= exit_long_stop` → fill at `open(i)`
  - Short: if `open(i) >= exit_short_stop` → fill at `open(i)`
- Non-gap trigger fill: fill at the **stop price**.
- Priority (V1): if both a stop-exit and a `target_dir`-based market exit are possible in the same bar,
  **stop-exit wins** (protective risk control first).

### 11.4 Same-Bar Entry/Exit Ambiguity (V1)
If an intrabar stop-entry and an intrabar stop-exit could both occur in the same bar:
- Treat as **ambiguous_fill** and **do not trade** (no entry, no exit).
- Record an `ambiguous_fill` reason in the result.

### 11.5 Exit Stop Lifecycle
- One exit stop per direction while in position.
- New same-direction exit stop replaces old (**Replace**).
- Direction change / flat cancels old-direction pending orders (same as entry lifecycle).

---

## 12) Trades Counting (V1)

To make `N_total = 120` stable and intuitive:
- `trades` is counted as **round-trip trades** (entry + exit = 1 trade).
- `fills` (per side) may be recorded separately for cost accounting, but `trades` is the round-trip unit.

---

## 13) Trade-Day SSOT (V1)

Several metrics and series definitions depend on "trading days" (not calendar days).

### 13.1 SSOT Source

Trade-day bucketing is defined by:
- `configs/registry/instruments.yaml`:
  - `timezone` (exchange timezone)
  - `trade_date_roll_time_local` (exchange local roll time, e.g. `17:00`)
- Canonical implementation: `src/core/trade_dates.py:trade_days_for_instrument_ts`

### 13.2 Definition (Deterministic)

For each bar timestamp (stored in `data_tz`, typically Asia/Taipei):
- Convert the timestamp to the instrument `timezone` (exchange local).
- If exchange local time `>= trade_date_roll_time_local`:
  - `trade_date = local_date + 1 day`
  - else `trade_date = local_date`

### 13.3 Usage (V1)

- **Daily downsample** of stitched OOS equity uses trade-day buckets:
  - take the **last bar close** within each trade-day bucket.
- `max_underwater_days` is computed over an equity series sampled at **1 point per trade-day**,
  so it represents **trading days** (not bars, not calendar days).

---

## 14) Result Schema SSOT (V1)

The canonical rich result output is `result.json` with a strict, versioned schema:

- SSOT schema definition: `src/contracts/research_wfs/result_schema.py`
- `result.json.version` is locked to **`"1.0"`** in V1.
- Policy schema is separately versioned and locked at `schema_version: "1.0"` (see `configs/policies/wfs/policy_v1_default.yaml`).

### 14.1 JSON Safety Rule (V1)

All values written to JSON must be JSON-serializable:
- no `NaN` / `inf` in outputs
- convert to `null` (or a safe numeric) and emit warnings if needed

### 14.2 Trades Ledger (V1)

To support report/debug without re-simulating, V1 records a **window-scoped OOS trade ledger**:

- `windows[i].oos_trades[]` — list of round-trip trades (entry→exit) for the **OOS** segment only.
- Each record is in **base currency** (TWD) and includes:
  - `entry_t`, `exit_t` (ISO `...Z`)
  - `direction` (`long`/`short`)
  - `entry_price`, `exit_price`
  - `gross_pnl`, `commission`, `net_pnl`
  - `entry_reason`, `exit_reason`
  - `bars_held`

Design rules:
- Trades are stored only for the **final OOS run** (best params), not for grid-search candidates (size control).

# Stage 2 Entry-Fill Pipeline: White‑Box Line‑Accurate Flowchart

**Date**: 2026-01-02  
**Git HEAD**: $(git rev-parse HEAD)  
**Scope**: Stage 2 kernel entry‑intent → fill → exit → equity pipeline  
**Mode Split**: `FISHBRO_KERNEL_INTENT_MODE` = "objects" | "arrays" (default "arrays")

---

## 0. Scope & Definitions

### 0.1 Core Concepts

- **Entry Intent**: A buy‑stop order placed at the previous bar's Donchian high (`donch_hi[t-1]`), active from bar `t`.
- **Exit Intent**: A sell‑stop order placed at `entry_fill_price - stop_mult * ATR(entry_bar)`, active from the bar after entry fill.
- **Fill**: A matched order that becomes a trade. For stop orders, fill occurs when bar's high ≥ stop price (buy stop) or low ≤ stop price (sell stop).
- **Trade**: A round‑trip pair of entry fill + exit fill (both must occur).
- **Equity**: Cumulative profit/loss curve, computed from fills after applying commission & slippage.
- **Warmup**: The first `channel_len` bars where no intents are generated (indicator warm‑up period).

### 0.2 Mode Split: Objects vs Arrays

- **Objects Mode** (`FISHBRO_KERNEL_INTENT_MODE=objects`):
  - Builds `OrderIntent` Python objects (list).
  - Calls `simulate_matcher(bars, intents)`.
  - Used for correctness reference and debugging.

- **Arrays Mode** (default):
  - Builds intent arrays (`created_bar`, `price`, `role`, `kind`, `side`, `qty`).
  - Calls `simulate_matcher_arrays()`.
  - Supports sparse‑masking and trigger‑rate sampling.

**Branch Point**: [`src/strategy/kernel.py` L873‑L891](src/strategy/kernel.py:873-891) – `run_kernel()` reads env var and dispatches.

---

## 1. Parameter Mapping Truth Table

Stage2 receives a `params_matrix` of shape `(n_params, >=3)` where columns are:

| Column | Variable | Type | Mapping Code |
|--------|----------|------|--------------|
| 0 | `channel_len` | `int` | `channel_len = int(params_row[0])` ([L119](src/pipeline/stage2_runner.py:119)) |
| 1 | `atr_len` | `int` | `atr_len = int(params_row[1])` ([L120](src/pipeline/stage2_runner.py:120)) |
| 2 | `stop_mult` | `float` | `stop_mult = float(params_row[2])` ([L121](src/pipeline/stage2_runner.py:121)) |

These are packed into a `DonchianAtrParams` dataclass ([L124‑L128](src/pipeline/stage2_runner.py:124-128)) and passed to `run_kernel()`.

---

## 2. Pipeline Overview Diagram (Text Flowchart)

```
[Stage2Runner.run_stage2] (src/pipeline/stage2_runner.py:L53‑L160)
├── normalize_bars + ensure contiguous (L88‑L97)
├── for each param_id in param_ids:
│   ├── extract params_row → channel_len, atr_len, stop_mult (L118‑L121)
│   ├── build DonchianAtrParams (L124‑L128)
│   ├── dispatch to kernel via run_kernel() (L131‑L137)
│   │   ├── mode = os.environ.get("FISHBRO_KERNEL_INTENT_MODE") (L874)
│   │   ├── if mode == "objects": run_kernel_object_mode() (L875‑L882)
│   │   └── else: run_kernel_arrays() (L883‑L891)
│   │
│   │   [OBJECTS PATH] run_kernel_object_mode() (L154‑L350)
│   │   ├── compute indicators: donch_hi = rolling_max(high, ch), atr = atr_wilder(...) (L213‑L214)
│   │   ├── build entry intents as OrderIntent objects (L225‑L247)
│   │   ├── simulate_matcher() → entry_fills (L251)
│   │   ├── generate exit intents from entry fills (L261‑L290)
│   │   ├── simulate_matcher() on exit intents → exit_fills (L294)
│   │   ├── merge & sort fills (L296‑L300)
│   │   ├── compute_metrics_from_fills() → net_profit, trades, max_dd, equity (L304‑L309)
│   │   └── assemble output with _obs (L324‑L336)
│   │
│   │   [ARRAYS PATH] run_kernel_arrays() (L353‑L857)
│   │   ├── compute/pre‑load indicators (L424‑L445)
│   │   ├── shift donch_hi → donch_prev[1:] = donch_hi[:-1] (L453‑L455)
│   │   ├── build entry intents via builder (L485‑L519):
│   │   │   ├── use_numba_builder → build_entry_intents_numba()
│   │   │   ├── use_dense_builder → _build_entry_intents_from_trigger()
│   │   │   └── default → build_intents_sparse()
│   │   ├── simulate_matcher_arrays() → entry_fills (L617‑L627)
│   │   ├── build exit intents from entry fills (L633‑L663)
│   │   ├── simulate_matcher_arrays() on exit intents → exit_fills (L702‑L712)
│   │   ├── merge & sort fills (L715‑L725)
│   │   ├── compute_metrics_from_fills() → net_profit, trades, max_dd, equity (L760‑L765)
│   │   └── assemble output with _obs (L809‑L826)
│   │
│   ├── extract metrics from kernel_result (L140‑L142)
│   ├── extract optional fills, equity (L145‑L146)
│   └── create Stage2Result (L148‑L158)
└── return list of Stage2Result (L160)
```

---

## 3. Entry Intent Generation (White‑Box)

### 3.1 Common Setup (Both Modes)

- **Indicator**: `donch_hi = rolling_max(bars.high, channel_len)` ([L438](src/strategy/kernel.py:438))
- **Shift**: `donch_prev[0] = NaN; donch_prev[1:] = donch_hi[:-1]` ([L453‑L455](src/strategy/kernel.py:453-455))
  - Intent created at bar `t-1`, price = `donch_hi[t-1]`, active at bar `t`.
- **Warmup**: Bars with index `t < channel_len` are skipped ([L74](src/strategy/kernel.py:74) in dense builder).

### 3.2 Objects‑Mode Entry Intent Builder

**Function**: `run_kernel_object_mode()` loop ([L225‑L247](src/strategy/kernel.py:225-247))

```python
for t in range(n):
    px = float(donch_hi[t])
    if np.isnan(px):
        continue
    # ... generate order_id
    intents.append(OrderIntent(...))
```

**Guards/Killers**:
1. **KILLER**: `np.isnan(px)` – NaN price check (L227)
2. **KILLER**: `t` loop implicitly skips warmup? No, but indicator `donch_hi[t]` is NaN for `t < channel_len` due to rolling_max, caught by NaN check.

**Output**: List of `OrderIntent` objects.

### 3.3 Arrays‑Mode Entry Intent Builders

Three implementations selected by environment flags:

#### 3.3.1 Dense Reference Builder (`_build_entry_intents_from_trigger`)
**File**: [`src/strategy/kernel.py` L33‑L131](src/strategy/kernel.py:33-131)  
**Line Range**: 33‑131  
**Purpose**: Build all valid intents (no sampling).

**Logic**:
- Create index array `i = np.arange(1, n)` (L69)
- Valid mask: `(~np.isnan(donch_prev[1:])) & (i >= warmup)` (L74)
- Gather sparse entries where mask is True.

**Guards/Killers**:
1. **KILLER**: `np.isnan(donch_prev[1:])` – NaN price filter (L74)
2. **KILLER**: `i >= warmup` – warmup skip (L74)
3. **KILLER**: `n_entry == 0` early return (L91‑L102)

#### 3.3.2 Sparse Builder (`build_intents_sparse`)
**File**: [`src/strategy/builder_sparse.py`](src/strategy/builder_sparse.py)  
**Line Range**: 22‑150 (approx)  
**Purpose**: Apply trigger‑rate sampling to reduce intent count.

**Logic**:
- Same valid mask as dense builder.
- Apply `trigger_rate` via random sampling (if `trigger_rate < 1.0`).
- Output arrays sized by sampled count.

**Guards/Killers**: Same as dense builder plus:
4. **KILLER**: Random sampling may reduce intents to zero even if valid_mask non‑zero.

#### 3.3.3 Numba Builder (`build_entry_intents_numba`)
**File**: [`src/strategy/entry_builder_nb.py`](src/strategy/entry_builder_nb.py)  
**Purpose**: Numba‑accelerated sparse builder.

**Guards**: Same as sparse builder.

### 3.4 Entry Intent Count Zero Causes

If `n_entry == 0`, kernel returns early with empty fills and zero metrics. Causes:

1. **Invalid parameters**: `channel_len <= 0` or `atr_len <= 0` ([L394](src/strategy/kernel.py:394))
2. **All donch_prev NaN**: Indicator warmup longer than bars, or all high prices NaN.
3. **Valid mask empty**: No bar passes `t >= warmup` and `~np.isnan(donch_prev[t])`.
4. **Trigger‑rate sampling**: Sparse builder with `trigger_rate` may sample zero intents.

---

## 4. Fill / Matcher Logic (White‑Box)

### 4.1 Matcher Entry Points

- **Objects**: `simulate_matcher(bars, intents)` ([L251](src/strategy/kernel.py:251)) → [`engine/engine_jit.py` L10‑L600](engine/engine_jit.py:10-600)
- **Arrays**: `simulate_matcher_arrays(...)` ([L617](src/strategy/kernel.py:617)) → [`engine/engine_jit.py` L313‑L550](engine/engine_jit.py:313-550)

### 4.2 Stop‑Fill Condition

**Function**: `_stop_fill()` in [`engine/engine_jit.py` L542‑L557](engine/engine_jit.py:542-557)

```python
def _stop_fill(side: int, stop_price: float, o: float, h: float, l: float) -> float:
    # returns nan if no fill
    if side == SIDE_BUY_CODE:          # BUY stop
        if h >= stop_price:            # high triggers stop
            return max(o, stop_price)  # fill price = max(open, stop)
    else:                              # SELL stop  
        if l <= stop_price:            # low triggers stop
            return min(o, stop_price)  # fill price = min(open, stop)
    return np.nan
```

**Key Points**:
- Uses **High** for buy‑stop, **Low** for sell‑stop.
- **Fill price** = `max(open, stop)` for buy, `min(open, stop)` for sell.
- **Strict inequality**: `>=` for buy, `<=` for sell.
- Returns `np.nan` if no trigger.

### 4.3 Order of Operations Per Bar

Inside `_simulate_kernel` ([engine/engine_jit.py L619‑L800](engine/engine_jit.py:619-800)):

1. **Intent activation**: Intents with `created_bar <= t < created_bar + ttl_bars` are active.
2. **Fill evaluation**: For each active intent, call `_fill_price()`.
3. **If filled**: Record fill, remove intent from active book (swap‑remove).
4. **Position state**: Not tracked in matcher; fills are independent.

**TTL (Time‑To‑Live)**: Default `INTENT_TTL_BARS_DEFAULT = 1` ([L47](engine/engine_jit.py:47)) → one‑shot next‑bar‑only.

### 4.4 "No Fill" Structural Conditions

- **Buy stop**: `high < stop_price` (strict).
- **Sell stop**: `low > stop_price` (strict).
- **Same‑bar entry‑exit**: Possible if entry fills at bar `t` and exit intent created at same `t` (active next bar).

---

## 5. Exit Intent & Exit Fill Logic

### 5.1 Exit Stop Price Calculation

**Objects Mode**: [`src/strategy/kernel.py` L264‑L271](src/strategy/kernel.py:264-271)

```python
a = float(atr[ebar])
stop_px = float(f.price - stop_mult * a)
```

**Arrays Mode**: [`src/strategy/kernel.py` L649‑L656](src/strategy/kernel.py:649-656)

```python
atr_e = float(atr[ebar])
if np.isnan(atr_e):
    continue
exit_stop = float(f.price - stop_mult * atr_e)
```

**ATR Source**: `atr[ebar]` where `ebar` = entry fill's `bar_index`.  
**Guard**: `np.isnan(atr_e)` → skip exit intent (no exit generated for that entry).

### 5.2 Exit Intent Generation

- **Created bar** = entry fill bar (`ebar`) ([L658](src/strategy/kernel.py:658) arrays, L283 objects).
- **Active next bar** (TTL=1).
- **Deterministic order ID** generated via `generate_order_id()`.

### 5.3 Exit Fill

Same matcher logic as entry (sell‑stop).  
**Condition**: `low <= exit_stop_price` triggers fill at `min(open, stop)`.

---

## 6. Result Assembly (trades/equity/net_profit)

### 6.1 Trade Counting

**Function**: `compute_metrics_from_fills()` ([`engine/metrics_from_fills.py`](engine/metrics_from_fills.py))

- **Trade**: A matched pair of BUY entry fill + SELL exit fill with same `order_id` linkage? Actually, trades are counted by pairing entry and exit fills sequentially based on fill order.
- **Implementation**: The function processes fills sorted by `bar_index`, `role`, `kind`, `order_id` and pairs entry→exit.

**Line Reference**: Need to examine `metrics_from_fills.py` for exact logic.

### 6.2 Equity Curve Generation

- **Equity** = cumulative sum of per‑trade P&L after costs.
- **Commission**: Applied per fill (both entry and exit).
- **Slippage**: Applied per fill via `apply_slippage_to_price()`.

**Allocation**: Equity array length = number of bars with at least one fill? Actually equity is per‑trade cumulative, not per‑bar. The returned `equity` array has length = number of trades + 1 (starting at 0).

### 6.3 Open Positions at End‑of‑Series

- **Ignored**: No forced close; open positions do not affect `net_profit` or `trades`.
- **Mark‑to‑market**: Not performed; equity curve ends at last closed trade.

---

## 7. "Zero Trades" Root Cause Checklist

### 7.1 Zero Entry Intents (`n_entry == 0`)

**Code Guards**:
1. `channel_len <= 0 or atr_len <= 0` ([L394](src/strategy/kernel.py:394))
2. `np.isnan(donch_prev[t])` for all `t >= warmup` ([L74](src/strategy/kernel.py:74))
3. `t < warmup` for all bars (warmup ≥ n_bars)
4. Sparse builder with `trigger_rate` sampling yields zero sampled intents.

### 7.2 Entry Intents > 0 but Zero Fills

**Matcher Conditions**:
1. **Buy‑stop never triggers**: `high[t] < stop_price` for all active intents.
2. **TTL expiry**: Intent active for only one bar (`ttl_bars=1`), next bar's high does not trigger.
3. **Same‑bar fill**? Entry intent created at `t-1`, active at `t`. If `high[t] < stop_price`, no fill.

### 7.3 Fills > 0 but Zero Trades

**Pairing Failure**:
1. **Exit intent not generated**: ATR at entry bar is NaN ([L651‑L654](src/strategy/kernel.py:651-654)).
2. **Exit fill never triggers**: `low > exit_stop_price` for all bars after entry.
3. **Exit TTL expiry**: Exit intent active for one bar only, not triggered.

###
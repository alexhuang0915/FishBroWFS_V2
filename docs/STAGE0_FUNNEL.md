# Stage 0 Funnel (v0)

## What Stage 0 is

Stage 0 is a **vector/proxy filter** that ranks massive parameter grids **without**:
- matcher / fills / orders
- strategy state machine
- per-trade PnL

It exists to prevent Stage 2 (full semantics) from being used as a brute-force grinder.

## What Stage 0 is not

Stage 0 is **not** a backtest.
It is allowed to be imprecise. Funnel philosophy is **Recall > Precision**.

## v0 Proxy: MA Directional Efficiency

For each parameter set (fast, slow, ...):

1) Compute SMA_fast and SMA_slow
2) Direction proxy:
   - dir[t] = sign(SMA_fast[t] - SMA_slow[t])
3) Return proxy:
   - ret[t] = close[t] - close[t-1]
4) Score:
   - score = sum(dir[t] * ret[t]) / (std(ret) + eps)

This is a cheap ranking score that correlates with “being on the right side of the move”.

## Contracts (non-negotiable)

Stage 0 modules MUST NOT import:
- FishBroWFS_V2.engine.*
- FishBroWFS_V2.strategy.*
- FishBroWFS_V2.pipeline.*

This is enforced by `tests/test_stage0_contract.py`.

## Capacity planner (why Funnel is mandatory)

Define:
- B = number of bars
- P = number of parameter sets
- T = throughput (ops/sec) for a given stage

Total “pair-bars” work (very rough) is:
  Work ≈ B × P

Estimated time:
  Time ≈ (B × P) / T

### Practical interpretation

- Stage 2 (full semantics) throughput is usually dominated by Python orchestration and object handling.
  Even if the matcher kernel is fast, the outer loop can dominate.

- Stage 0 is designed to be close to pure numeric kernels:
  It should operate in the 10^7–10^8 ops/sec regime on a single machine.

### Recommended funnel targets

As a starting point:
- Stage 0 keeps Top **0.1%–1%**
- Stage 1 keeps Top **1%–10%** of Stage 0 survivors
- Stage 2 runs only the remaining candidates

This turns impossible runs (10^8 params) into feasible runs (10^4–10^5 params).



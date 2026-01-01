# Portfolio Governance Constitution v1.1 (ENFORCED)

## Preamble

This constitution defines the machine‑enforced law governing the admission, lifecycle, allocation, and retirement of automated trading strategies within the FishBroWFS_V2 portfolio. It is the single source of truth for all governance logic; any deviation is a constitutional violation.

## Article 0 – Immutable Identity

Every strategy is identified by an immutable tuple `(strategy_id, version_hash, data_fingerprint)`. This identity is established at research compilation and cannot be altered thereafter. The identity key is `f"{strategy_id}:{version_hash}:{data_fingerprint}"`.

## Article I – Lifecycle State Machine

### 1.1 States
- **INCUBATION** – Strategy exists only in research artifacts; not yet evaluated for admission.
- **CANDIDATE** – Passed integrity gate; awaiting diversity & correlation evaluation.
- **PAPER_TRADING** – Admitted to portfolio but trading with zero capital (shadow execution).
- **LIVE** – Active in portfolio with real capital allocation.
- **PROBATION** – Live strategy that has breached a kill‑switch threshold; may be restored to LIVE or retired.
- **RETIRED** – Permanently removed from portfolio; no further capital.

### 1.2 Allowed Transitions
Only the following transitions are permitted (no skipping):
- INCUBATION → CANDIDATE
- CANDIDATE → PAPER_TRADING
- PAPER_TRADING → LIVE
- LIVE → PROBATION
- PROBATION → LIVE
- PROBATION → RETIRED
- LIVE → RETIRED

Any other transition attempt is a constitutional violation and must be rejected.

## Article II – Admission Gates

### 2.1 Integrity Gate
- **Purpose**: Ensure the strategy’s research artifacts are complete, reproducible, and free of known flaws.
- **Input**: Boolean `integrity_ok` from the research pipeline.
- **Rule**: If `integrity_ok == False`, admission is denied regardless of other gates.

### 2.2 Diversity Gate
- **Purpose**: Maintain style‑bucket diversification across the portfolio.
- **Input**: Candidate’s bucket tag (first matching tag among `GovernanceParams.bucket_slots` keys), current bucket occupancy.
- **Rule** (normal mode): Admission requires an available slot in the candidate’s bucket.
- **Rule** (replacement mode): Slot not required, but a replacement target must be specified.

### 2.3 Correlation Gate
- **Purpose**: Limit portfolio concentration risk.
- **Input**: Rolling correlation of candidate returns vs. portfolio returns, and vs. each existing member returns.
- **Thresholds** (configurable):
  - `corr_portfolio_hard_limit` (default 0.7)
  - `corr_member_hard_limit` (default 0.8)
- **Rule**: Both correlations must stay below their respective limits.
- **Exception**: In replacement mode, correlation limits may be exceeded if a dominance proof is provided (Article III).

## Article III – Replacement Mode

### 3.1 Purpose
Allow a new strategy to replace an existing one within the same bucket when the new strategy demonstrably dominates the old.

### 3.2 Requirements
- `replacement_mode = True`
- `replacement_target_key` must identify the strategy being replaced.
- A `dominance_proof` must be supplied containing at least:
  - `expected_score_new > expected_score_old`
  - `risk_adj_new >= risk_adj_old`

### 3.3 Effect
- Diversity gate is waived.
- Correlation gate thresholds may be exceeded (the dominance proof overrides them).
- The old strategy is immediately retired (state → RETIRED) upon admission of the new.

## Article IV – Risk Budgeting & Allocation

### 4.1 Risk Models
The portfolio may use one of the following risk models (configurable via `GovernanceParams.risk_model`):
- `vol_target` (default) – weight inversely proportional to volatility.
- `risk_parity` – iterative equal risk contribution (requires covariance matrix).

Only models listed in `GovernanceParams.allowed_risk_models` are permitted.

### 4.2 Vol‑Targeting Default
- Raw weight for strategy `i`: `raw_i = 1 / max(vol_est_i, vol_floor)`
- Normalize raw weights to sum = 1.
- Clamp each weight to `[w_min, w_max]` with proportional redistribution of surplus/deficit.
- Final weights must sum to 1.0 within 1e‑9.

### 4.3 Determinism
Allocation must be deterministic: same inputs → same outputs. Ordering is by sorted `strategy_keys`.

## Article V – Kill‑Switch Engine

### 5.1 Strategy‑Level Kill Switch
- **Trigger**: `dd_live > max(dd_reference * dd_k_multiplier, dd_absolute_cap)`
- **Action**: Transition LIVE/PROBATION → RETIRED, log `RETIRE_KILL_SWITCH`.
- **Artifact**: A `KillSwitchReport` is written.

### 5.2 Portfolio‑Level Circuit Breaker
- **Trigger**: `dd_portfolio > portfolio_dd_cap`
- **Action**: All live strategy weights are multiplied by `exposure_reduction_on_breaker`. Remainder is allocated to a `_CASH` bucket.
- **Log**: A `PORTFOLIO_CIRCUIT_BREAKER` event is recorded (strategy_key = None).

## Article VI – Governance Parameters

The following tunable parameters are defined in `GovernanceParams` (defaults in parentheses):

| Parameter | Type | Description |
|-----------|------|-------------|
| `corr_rolling_days` | int | Window for correlation calculation (30) |
| `corr_min_samples` | int | Minimum samples required for correlation (20) |
| `corr_portfolio_hard_limit` | float | Max correlation vs. portfolio (0.7) |
| `corr_member_hard_limit` | float | Max correlation vs. any member (0.8) |
| `bucket_slots` | dict[str, int] | Max number of strategies per style bucket |
| `allowed_risk_models` | list[str] | Permitted risk models (["vol_target", "risk_parity"]) |
| `risk_model` | str | Active risk model ("vol_target") |
| `portfolio_vol_target` | float | Target annualized portfolio volatility (0.10) |
| `vol_floor` | float | Minimum volatility used in weight calculation (0.02) |
| `w_max` | float | Maximum weight per strategy (0.35) |
| `w_min` | float | Minimum weight per strategy (0.0) |
| `dd_absolute_cap` | float | Absolute drawdown cap (0.35) |
| `dd_k_multiplier` | float | Multiplier on reference drawdown (1.0) |
| `portfolio_dd_cap` | float | Portfolio‑wide drawdown cap (0.20) |
| `exposure_reduction_on_breaker` | float | Fraction of exposure retained during circuit breaker (0.5) |

All parameters are validated on load; invalid values cause a constitutional violation.

## Article VII – Artifact Formats

### 7.1 Append‑Only Governance Log
- **File**: `outputs/governance/governance_log.jsonl`
- **Format**: One JSON object per line, each representing a `GovernanceLogEvent`.
- **Fields**: `timestamp_utc`, `actor`, `strategy_key`, `from_state`, `to_state`, `reason_code`, `attached_artifacts`, `data_fingerprint`, `extra`.
- **Rule**: Lines are only appended; existing lines are never modified or deleted.

### 7.2 Artifact Storage
- **Directory**: `outputs/governance/artifacts/`
- **Naming**: `{artifact_type}_{strategy_key}_{timestamp}.json` (or with hash suffix if conflict).
- **Immutability**: If an artifact with the same filename already exists but has different content, the new artifact is saved with a unique suffix (`-{shorthash}.json`).

### 7.3 Required Artifacts
- `AdmissionReport` – outcome of admission gates.
- `ReplacementReport` – dominance proof and replacement decision.
- `KillSwitchReport` – trigger details and retirement decision.

All artifacts are JSON‑serialized Pydantic models with `sort_keys=True, indent=2`.

## Article VIII – Acceptance Tests

The following tests must pass for the constitution to be considered correctly implemented:

1. **State‑machine transitions** – Only allowed transitions succeed; illegal transitions raise a defined error.
2. **Admission gates** – Integrity gate denial overrides all other gates; diversity gate respects bucket slots; correlation gate respects limits.
3. **Replacement mode** – Requires target and dominance proof; waives diversity and correlation limits when proof supplied.
4. **Allocation determinism** – Same inputs produce identical weights (within tolerance).
5. **Weight clamping** – Final weights respect `w_min`/`w_max` and sum to 1.
6. **Kill‑switch trigger** – Strategy kill triggered when `dd_live` exceeds threshold; portfolio breaker triggered when `dd_portfolio` exceeds cap.
7. **Artifact immutability** – Writing an artifact with conflicting content does not overwrite; a new file with hash suffix is created.
8. **Log append‑only** – Governance log is never truncated or rewritten.
9. **Parameter validation** – Invalid parameter values are rejected at load time.
10. **No side‑effects at import** – Importing governance modules does not write files or modify state.

These tests are implemented in `tests/portfolio/` and must be run as part of the CI pipeline.

---
*Constitution version: 1.1*  
*Effective date: 2026‑01‑01*  
*Enforcement: Machine‑enforced via code in `src/portfolio/governance/`*
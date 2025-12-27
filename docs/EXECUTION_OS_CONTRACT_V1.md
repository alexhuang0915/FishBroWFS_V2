# Execution OS Contract V1 (Governance‑First, Determinism‑Safe)

**Repo:** FishBroWFS_V2  
**Phase:** Execution OS (Contract + Minimal Deterministic Plumbing)  
**Goal:** Define and enforce a deterministic, auditable, governance‑first **Execution Plan** layer that converts **Portfolio governance decisions** into **execution‑ready plans** — **without** placing trades or integrating brokers yet.

This creates the “only legal exit” for future MultiCharts / broker integrations.

---

## 0) HARD CONSTITUTION (MUST PASS)

### 0.1 Determinism‑First

**FORBIDDEN**

* Real‑time feeds, websockets, timers, auto polling
* Client‑side computation of execution decisions
* Non‑deterministic IDs (random UUIDv4), non‑stable ordering
* Silent mutation of plans (no reason / no event)

**ALLOWED**

* Explicit manual actions to create/approve/commit plans
* Deterministic UUIDv5 IDs derived from stable fields
* Append‑only ledgers for all state transitions

### 0.2 Governance‑First

* Execution is a **state machine** (DRAFT → REVIEWED → APPROVED → COMMITTED)
* Every transition is an event with a mandatory reason
* Season / Freeze locks behavior (read‑only when frozen, except explicit administrative unfreeze path)

### 0.3 Zero‑Leakage

* UI pages call only Bridges
* Bridges call services/control; no transport in UI pages

---

## 1) DOMAIN MODEL (AUTHORITATIVE)

### 1.1 Identity & Deterministic IDs

All IDs are UUIDv5.

#### Namespaces (constants)

Fixed UUID namespaces defined in `src/FishBroWFS_V2/gui/contracts/execution_dto.py`:

* `EXECUTION_NS`
* `EXECUTION_EVENT_NS`

#### Deterministic ID rules

* `plan_id = uuidv5(EXECUTION_NS, season_id|risk_profile_id|sorted(item_ids))`
* `event_id = uuidv5(EXECUTION_EVENT_NS, plan_id|from_state|to_state|sequence_no)`

Sequence_no must be deterministic:

* Derived as `(len(existing_events_for_plan)+1)` at append time.

### 1.2 Execution States

Plan state machine:

* `DRAFT`
* `REVIEWED`
* `APPROVED`
* `COMMITTED`
* `CANCELLED`

Allowed transitions:

* DRAFT → REVIEWED
* REVIEWED → APPROVED
* APPROVED → COMMITTED
* Any non‑COMMITTED state → CANCELLED

**COMMITTED is terminal** (no further transitions).

### 1.3 ExecutionLeg

```python
@dataclass(frozen=True)
class ExecutionLeg:
    strategy_id: str
    instance_id: str
    side: str                 # "LONG" | "SHORT" | "BOTH" (future)
    symbol: str               # e.g. "MNQ", "MES" (string only)
    timeframe: str            # e.g. "60m" (string)
    risk_budget_r: float      # R allocation for this leg
```

### 1.4 ExecutionPlan

```python
@dataclass(frozen=True)
class ExecutionPlan:
    season_id: str
    plan_id: str
    state: str                # DRAFT/REVIEWED/APPROVED/COMMITTED/CANCELLED
    risk_profile_id: str
    portfolio_item_ids: tuple[str, ...]   # deterministic list of items
    legs: tuple[ExecutionLeg, ...]

    created_from_snapshot_ref: str        # link to SYSTEM snapshot or portfolio snapshot id
    last_event_id: str | None
```

#### Required constraints

* `portfolio_item_ids` must be sorted (lexicographically) and tuple
* `legs` must be deterministic ordering: `(symbol, strategy_id, instance_id)`

### 1.5 ExecutionEvent (Append‑Only)

```python
@dataclass(frozen=True)
class ExecutionEvent:
    event_id: str
    season_id: str
    plan_id: str
    action: str               # "CREATE" | "REVIEW" | "APPROVE" | "COMMIT" | "CANCEL"
    from_state: str
    to_state: str
    reason: str               # REQUIRED non‑empty
    actor: str                # REQUIRED
    snapshot_ref: str         # REQUIRED (tie to forensic snapshot)
    created_at_utc: str       # server generated
    sequence_no: int
```

Rules:

* Append‑only jsonl
* Never edited
* `reason` mandatory
* `created_at_utc` is server generated but must be stable ordering (see below)

### 1.6 ExecutionStateSnapshot (Derived)

```python
@dataclass(frozen=True)
class ExecutionStateSnapshot:
    season_id: str
    plans: tuple[ExecutionPlan, ...]
    events: tuple[ExecutionEvent, ...]
```

Ordering:

* Plans sorted by `(state, plan_id)`
* Events sorted by `(plan_id, sequence_no)` (NOT timestamps)

**No timestamp ordering in logic.**

---

## 2) STORAGE CONTRACT (STRICT)

### 2.1 Source of Truth

* Ledger file: `outputs/execution/{season_id}/execution_events.jsonl` is the only source‑of‑truth for state transitions.

### 2.2 Derived Snapshot

* `outputs/execution/{season_id}/execution_snapshot.json` is derived deterministically from the ledger.

### 2.3 Snapshot Reference

`snapshot_ref` must reference the current forensic snapshot id. If repo already has a “snapshot id” concept in `RUNTIME_CONTEXT.md` or similar, use that string. If not available, use `"UNKNOWN"` but keep field present.

---

## 3) EXECUTION BRIDGE (SINGLE ENTRY)

### 3.1 File

`src/FishBroWFS_V2/gui/nicegui/bridge/execution_bridge.py`

### 3.2 API

```python
class ExecutionBridge:
    def get_snapshot(self, season_id: str) -> ExecutionStateSnapshot: ...

    def create_plan_from_portfolio(
        self,
        season_id: str,
        portfolio_item_ids: list[str],
        risk_profile_id: str,
        reason: str,
        actor: str,
    ) -> ExecutionPlan: ...

    def transition_plan(
        self,
        season_id: str,
        plan_id: str,
        action: str,     # REVIEW/APPROVE/COMMIT/CANCEL
        reason: str,
        actor: str,
    ) -> ExecutionPlan: ...
```

### 3.3 Enforcement Rules

* Reject empty reason
* Reject unknown action
* Enforce state machine transitions
* If Season is frozen: allow only get_snapshot; reject create/transition

  * Use existing season freeze check (Phase 5). If not accessible here, add a minimal adapter calling the existing freeze service.

---

## 4) PLAN CREATION LOGIC (DETERMINISTIC)

### 4.1 Input

From Portfolio OS:

* Accept `portfolio_item_ids` only (string IDs)
* For now, plan creation does not require strategy metadata. It creates placeholder legs.

### 4.2 Deterministic Placeholder Legs (Minimum)

For each portfolio item id:

* parse stable fields if encoded, or store as strings
* create `ExecutionLeg` with:

  * `side="BOTH"` (or "LONG" if your system defaults)
  * `symbol="UNKNOWN"`
  * `timeframe="UNKNOWN"`
  * `risk_budget_r = 1.0 / N` (deterministic equal split)

This is a **contract stub**: later, symbol/timeframe will be filled from Strategy Registry.

---

## 5) UI PAGE (GOVERNANCE ONLY, MANUAL REFRESH)

### 5.1 File

`src/FishBroWFS_V2/gui/nicegui/pages/execution_governance.py`

### 5.2 Requirements

* Manual refresh button calls `ExecutionBridge.get_snapshot`
* Table shows:

  * plan_id (short)
  * state
  * risk_profile_id
  * item count
  * last_event_id
* “Create Plan” dialog:

  * input: season_id, risk_profile_id, portfolio_item_ids (multi‑line)
  * mandatory reason
* “Transition” dialog:

  * action dropdown (REVIEW/APPROVE/COMMIT/CANCEL)
  * mandatory reason

**No auto refresh, no timers.**

---

## 6) TESTS (MANDATORY)

Create: `tests/execution/test_execution_os_contract.py`

Must cover:

1. **Deterministic plan_id**

* Given same season_id, risk_profile_id, same item ids in different order → same plan_id

2. **Event sequencing**

* sequence_no increments deterministically
* events sorted by (plan_id, sequence_no)

3. **State machine**

* valid transitions pass
* invalid transitions rejected

4. **Frozen season protection**

* when season frozen, create/transition must raise

5. **Reason required**

* empty reason rejected for both create and transition

6. **Zero‑leakage**

* UI page imports only ExecutionBridge

---

## 7) SNAPSHOT / NO‑FOG INTEGRATION

* Update forensic snapshot collector (if exists) to include:

  * `outputs/execution/{season_id}/execution_events.jsonl`
  * `outputs/execution/{season_id}/execution_snapshot.json`
* Must not break flattening constraints.

If the repo’s snapshot system intentionally ignores outputs other than `outputs/snapshots/*`, then:

* include execution artifacts via explicit inclusion list in snapshot generator (do not create new snapshot directories).

---

## 8) ACCEPTANCE CRITERIA (FINAL)

* Execution events ledger append‑only with reasons
* Deterministic plan IDs
* Deterministic snapshot derived from ledger
* State machine enforced
* Frozen season blocks mutations
* UI manual refresh only
* All tests pass (`make check`)

---

## 9) IMPLEMENTATION NOTES

* All UUIDv5 IDs are generated using the fixed namespaces defined in the DTO module.
* The bridge must never crash; validation errors raise `ValueError` with clear messages.
* The UI page must follow Zero‑Leakage: import only the ExecutionBridge, no transport clients.
* The snapshot reference can be obtained from `RUNTIME_CONTEXT.md` or `SYSTEM_FULL_SNAPSHOT.md`; if not available, use `"UNKNOWN"`.
* Season freeze check should reuse existing `SeasonState` service; if not available, a stub can be used for now.

---

**Version:** V1  
**Date:** 2025‑12‑27  
**Status:** Enforced
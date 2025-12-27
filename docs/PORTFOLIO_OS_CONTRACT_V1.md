# Portfolio OS Contract V1 – Governance‑First, Determinism‑Safe

## 0. HARD CONSTITUTION (MUST PASS)

### 0.1 Determinism First

**FORBIDDEN**

- Client‑side decision logic
- Client clocks / timers / websockets / auto‑poll
- Non‑deterministic ordering (timestamps without stable keys)

**ALLOWED**

- Manual actions (explicit user intent)
- Server/bridge computed outcomes
- Snapshot‑based reads

### 0.2 Governance First

- Every portfolio change is an event with a reason.
- No silent mutation.
- Freeze means immutable (except explicit unfreeze admin path).

### 0.3 Zero‑Leakage

- Pages → Bridges → Control API (or composed bridges)
- Pages must not import transport (httpx, requests, socket, etc.)

## 1. DOMAIN MODEL (AUTHORITATIVE)

### 1.1 Portfolio Item Identity

A portfolio item is immutable in identity:

```
PortfolioItemID = (
    season_id: str,
    strategy_id: str,
    instance_id: str,
)
```

No renaming. No reuse across seasons.

### 1.2 PortfolioItem

```python
@dataclass(frozen=True)
class PortfolioItem:
    season_id: str
    strategy_id: str
    instance_id: str

    current_status: str     # "CANDIDATE" | "KEEP" | "DROP" | "FROZEN"
    last_decision_id: str | None
```

### 1.3 PortfolioDecisionEvent (Append‑Only Ledger)

```python
@dataclass(frozen=True)
class PortfolioDecisionEvent:
    decision_id: str            # deterministic UUIDv5
    season_id: str
    strategy_id: str
    instance_id: str

    action: str                 # "KEEP" | "DROP" | "FREEZE"
    reason: str                 # REQUIRED, non‑empty
    actor: str                  # e.g. "user:huang", "system:rule_x"

    snapshot_ref: str           # snapshot hash / id
    created_at_utc: str         # ISO string (server generated, stable)
```

**Rules**

- Append‑only, never edited.
- Deterministic `decision_id`:
  ```
  UUIDv5(namespace=PORTFOLIO_NS, name=concat(fields))
  ```

### 1.4 PortfolioStateSnapshot

```python
@dataclass(frozen=True)
class PortfolioStateSnapshot:
    season_id: str
    items: tuple[PortfolioItem, ...]          # deterministic ordering
    decisions: tuple[PortfolioDecisionEvent, ...]
```

**Ordering**

- Items sorted by `(strategy_id, instance_id)`
- Decisions sorted by `(created_at_utc, decision_id)`

## 2. STORAGE & LOCATION (STRICT)

### 2.1 Events Ledger

```
outputs/portfolio/{season_id}/decisions.jsonl
```

Each line is a JSON‑serialized `PortfolioDecisionEvent`.

### 2.2 State Snapshot (Derived, Deterministic)

```
outputs/portfolio/{season_id}/portfolio_snapshot.json
```

Snapshot is derived from the ledger, never hand‑edited.  
Ledger is the source of truth.

## 3. PORTFOLIO BRIDGE (SINGLE ENTRY)

### 3.1 File

`src/FishBroWFS_V2/gui/nicegui/bridge/portfolio_bridge.py`

### 3.2 API

```python
class PortfolioBridge:
    def get_snapshot(self, season_id: str) -> PortfolioStateSnapshot: ...

    def submit_decision(
        self,
        season_id: str,
        strategy_id: str,
        instance_id: str,
        action: str,          # "KEEP" | "DROP" | "FREEZE"
        reason: str,
        actor: str,
    ) -> PortfolioDecisionEvent:
        ...
```

### 3.3 Rules

- Validate season exists.
- Validate not frozen (unless action is `"FREEZE"`).
- Validate reason non‑empty.
- Write event only (append to ledger).
- Recompute snapshot deterministically after each write.

## 4. GOVERNANCE RULES (ENFORCED)

- No reason → reject.
- Frozen season → reject all except read.
- `DROP` after `KEEP` allowed (with reason).
- `FREEZE` locks item (no further decisions).

## 5. UI (DETERMINISM‑SAFE)

### 5.1 Portfolio Overview Page

- Table of `PortfolioItem`s.
- Columns: Strategy / Instance, Current Status, Last Decision.
- No auto‑refresh.
- Manual “Refresh Snapshot” button.

### 5.2 Decision Dialog

- Triggered by explicit button.
- Choose action (`KEEP` / `DROP` / `FREEZE`).
- Mandatory reason textarea.
- Confirm → calls `submit_decision`.
- After success → refresh snapshot.
- No client logic deciding validity.

## 6. TESTS (MANDATORY)

### 6.1 Determinism

- Two identical ledgers → identical snapshots.
- Decision IDs stable across runs.

### 6.2 Governance

- Reject empty reason.
- Reject decision on frozen season.
- `FREEZE` locks item.

### 6.3 Zero‑Leakage

- Pages import only `PortfolioBridge`.
- No transport in UI.

## 7. SNAPSHOT & NO‑FOG GUARANTEES

- `make snapshot` must include:
  - portfolio ledger files
  - portfolio snapshot
- No extra directories.
- Deterministic content hash.

## 8. COMMANDS (WSL zsh ONLY)

```bash
cd /home/fishbro/FishBroWFS_V2
make check
make snapshot
make dashboard
```

## 9. HINT CODE (DETERMINISTIC UUID)

```python
import uuid

PORTFOLIO_NS = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

def decision_uuid_v5(fields: list[str]) -> str:
    name = "|".join(fields)
    return str(uuid.uuid5(PORTFOLIO_NS, name))
```

## 10. ACCEPTANCE CRITERIA (FINAL)

- All decisions are append‑only with reasons.
- Snapshot derived deterministically.
- `make check` clean.
- UI performs no auto‑refresh.
- Portfolio history fully auditable.

---

**FINAL DIRECTIVE**

Implement exactly as specified.  
No shortcuts. No hidden state. No real‑time features.

This completes the transition from Research System to Governed Decision System.
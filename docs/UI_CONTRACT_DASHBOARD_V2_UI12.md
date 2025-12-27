# FishBroWFS_V2 – UI Contract Dashboard V2 (UI‑1/2 Combined, Determinism‑Safe)

This document defines the **UI‑1/2** (Determinism‑Safe) dashboard contract for the FishBroWFS_V2 NiceGUI interface. The contract extends UI‑0 with **intelligence fields** and **portfolio/deploy state machine** while maintaining **zero leakage**, **no auto‑polling**, and **deterministic rendering**.

---

## 1. UI‑1/2 Scope

**UI‑1/2** is the **dark‑purple Ops Dashboard** that adds **semantic intelligence** computed server‑side (or bridge‑side) from a **snapshot**—NOT via auto‑refresh. It satisfies the same non‑negotiable constraints as UI‑0:

- **No auto‑polling timers** (`ui.timer`, `setInterval`, `setTimeout` for data fetching)
- **No websocket streams** (no live updates, no push notifications)
- **No client‑derived ETA** (all timestamps must come from server‑supplied snapshot)
- **No auto‑refresh on page load** (no network calls triggered by `onload` or `mounted`)
- **No sorting based on unstable timestamps** (ordering must be deterministic, e.g., by `(-score, candidate_id)`)

**UI‑1/2 is a combined intelligence layer** that enriches the snapshot with deterministic explanations, stability flags, and plateau hints, while keeping the UI a **thin client** that only renders a snapshot.

---

## 2. UI Blocks (Dark Ops Grid Cards)

The dashboard must be composed of the following UI blocks, arranged in a responsive dark‑purple grid:

### 2.1 Topbar / Global Status
- **Season indicator** (e.g., “2026Q1”)
- **System online indicator** (green/red dot + “System Online” / “System Offline”)
- **Runs count** (total runs in current season)
- **Portfolio status** (e.g., “Portfolio: 3 candidates, 2 deployed”)
- **Deploy status** (e.g., “Deploy: Ready” / “Deploy: Pending”)

### 2.2 Primary CTA
- **New Operation** button (navigates to `/wizard`)
- **Go to Portfolio** button (navigates to `/portfolio`)

### 2.3 Active Ops / Progress
- List of currently running jobs (max 5)
- For each job: job ID, status, progress percentage, ETA (server‑supplied)
- **No progress animation** (static snapshot only)

### 2.4 Intelligence Snapshot
- **Candidate Insights** (top 3 candidates with explanations, stability flags, plateau hints)
- **Operation Summary** (scanned strategies, evaluated parameters, skipped metrics, notes)

### 2.5 Latest Candidates
- List of top‑5 candidates (sorted by score descending)
- Each candidate: candidate ID, score, strategy, dataset, timestamp, stability flag, plateau hint
- **Deterministic ordering** (`(-score, candidate_id)`)

### 2.6 System Logs
- Latest 10 lines from system logs (read from `outputs/logs/` via bridge)
- **No tail‑following** (static snapshot only)

### 2.7 Navigation Tabs
- Dashboard (current page)
- Wizard (`/wizard`)
- History (`/history`)
- Candidates (`/candidates`)
- Portfolio (`/portfolio`)
- Deploy (`/deploy`)
- Settings (`/settings`)

### 2.8 Refresh Button
- A single **Refresh** button that triggers a manual refresh of the entire dashboard.
- On click, calls `DashboardBridge.get_snapshot()` and re‑renders all UI blocks with the returned data.
- **No automatic refresh** after button click (no periodic timer).

---

## 3. Forbidden Behavior (UI‑1/2 Prohibitions)

The following are **strictly forbidden** in UI‑1/2 (same as UI‑0):

1. **Auto‑polling timers** – any use of `ui.timer`, `setInterval`, `setTimeout` for data fetching.
2. **Websocket connections** – any `websocket`, `socket.io`, `SSE` usage.
3. **Client‑side sorting by unstable timestamps** – sorting by `datetime.now()` or `time.time()`.
4. **Direct transport calls** – any import or use of `httpx`, `requests`, `aiohttp`, `socket` in UI pages.
5. **Database writes from UI** – any `INSERT`, `UPDATE`, `DELETE` executed by UI code.
6. **UI‑derived ETA calculations** – ETA must be supplied by server snapshot, not computed client‑side.
7. **Auto‑refresh on page load** – no network calls triggered by page load (except optional static data).
8. **Progress animations** – no CSS/JS animations that simulate progress (progress bar may be static).
9. **Import of `migrate_ui_imports()`** – UI pages must not call this function.
10. **Use of `label=` in NiceGUI constructors** – must follow existing `ui_compat` policy (use `ui.label()` externally).

---

## 4. Data Transfer Objects (DTOs)

All data displayed in the dashboard must be supplied via a **DashboardSnapshotDTO**, a frozen dataclass defined in `src/FishBroWFS_V2/gui/contracts/dashboard_dto.py`.

### 4.1 CandidateDTO (Extended with Intelligence)

```python
@dataclass(frozen=True)
class CandidateDTO:
    rank: int
    candidate_id: str
    instance: str
    score: float

    # UI‑1/2 intelligence (all deterministic, server/bridge computed)
    explanations: tuple[str, ...]       # "Why selected" bullets
    stability_flag: str                 # "OK" | "WARN" | "DROP"
    plateau_hint: str                   # one‑line summary
```

### 4.2 OperationSummaryDTO

```python
@dataclass(frozen=True)
class OperationSummaryDTO:
    scanned_strategies: int
    evaluated_params: int
    skipped_metrics: int
    notes: tuple[str, ...]              # optional summary bullets
```

### 4.3 PortfolioDeployStateDTO

```python
@dataclass(frozen=True)
class PortfolioDeployStateDTO:
    portfolio_status: str               # "Empty" | "Pending" | "Ready" | "Unknown"
    deploy_status: str                  # "Undeployed" | "Deployed" | "Unknown"
```

### 4.4 DashboardSnapshotDTO (Final v2)

```python
@dataclass(frozen=True)
class DashboardSnapshotDTO:
    season_id: str
    system_online: bool
    runs_count: int

    worker_effective: int
    ops_status: str                     # "IDLE" | "RUNNING"
    ops_progress_pct: int               # 0..100
    ops_eta_seconds: int | None

    portfolio_deploy: PortfolioDeployStateDTO
    operation_summary: OperationSummaryDTO

    top_candidates: tuple[CandidateDTO, ...]
    log_lines: tuple[str, ...]          # last N lines snapshot

    build_info: BuildInfoDTO | None
```

All DTOs must be **frozen** (immutable) and have **deterministic ordering** when represented as tuples.

---

## 5. Intelligence Generation (Deterministic Rules)

Intelligence must NOT use client time, randomness, or unstable ordering. Compute in bridge using deterministic rules from existing fields.

### 5.1 Candidate Sorting (Deterministic)

Bridge MUST sort candidates using:

1. primary: `-score`
2. tiebreaker: `candidate_id` (string ascending)

Then assign `rank = 1..N`.

### 5.2 “Why Selected” Explanations

Generate deterministic bullet points. Use only candidate numeric fields available now (score, rank, etc). If you don’t have deeper plateau data yet, produce conservative explanations:

Rules (example, deterministic):

* Always include: `"Top candidate by score."` for rank 1
* For rank <= 3: `"Top‑3 candidate in latest snapshot."`
* If score >= threshold: `"Score above threshold: {threshold}."` (threshold constant in code)
* Always include: `"Snapshot‑based; refresh to update."` (optional)

Thresholds must be constants (e.g., `SCORE_GOOD=1.0`), not env‑based.

### 5.3 Stability Flag

Deterministic mapping using score:

* If score >= 1.2 → `"OK"`
* If 0.9 <= score < 1.2 → `"WARN"`
* If score < 0.9 → `"DROP"`

(Constants must be defined in code, not config.)

### 5.4 Plateau Hint

If plateau metrics exist later, integrate. For now:

* rank 1: `"Primary candidate (highest score)."`
* else: `"Backup candidate (rank #{rank})."`

---

## 6. DashboardBridge Contract

A new bridge `DashboardBridge` must be implemented in `src/FishBroWFS_V2/gui/nicegui/bridge/dashboard_bridge.py` with the following interface:

```python
class DashboardBridge:
    def get_snapshot(self) -> DashboardSnapshotDTO:
        """
        Return a complete snapshot of dashboard data with intelligence.

        This method:
        - MUST be deterministic (same inputs → same output)
        - MUST NOT perform any side effects (read‑only)
        - MUST fetch data from Control API via existing bridges (JobsBridge, MetaBridge, etc.)
        - MUST NOT introduce any auto‑polling or timers
        - MUST return a frozen DTO with intelligence fields
        - MUST apply deterministic sorting and intelligence generation
        """
```

The bridge must compose data from existing bridges (JobsBridge, DeployBridge, WorkerBridge, etc.) and the Control API client. It must **not** make direct HTTP calls (must reuse existing bridges).

---

## 7. Acceptance Criteria

### 7.1 Functional
- [ ] Dashboard page (`/`) renders all UI blocks in a dark‑purple grid‑cards layout.
- [ ] Refresh button triggers a single bridge call and updates all UI blocks.
- [ ] No auto‑polling timers are present in the page (verified by test).
- [ ] No websocket connections are established (verified by test).
- [ ] All data is sourced from `DashboardBridge.get_snapshot()`.
- [ ] Ordering of candidates and logs is deterministic across refreshes.
- [ ] UI complies with Zero‑Leakage Architecture (no transport imports).
- [ ] Intelligence fields (explanations, stability flags, plateau hints) are displayed for top candidates.
- [ ] Operation summary stats are displayed.
- [ ] Portfolio/deploy state is displayed.

### 7.2 Non‑Functional
- [ ] `make check` passes (no test regressions).
- [ ] `make dashboard` starts the dashboard without errors.
- [ ] Snapshot flattening compliance: `make snapshot` produces only `SYSTEM_FULL_SNAPSHOT.md`.
- [ ] Runtime context flattened: `make dashboard` writes `RUNTIME_CONTEXT.md` directly under `outputs/snapshots/`.
- [ ] All policy tests (`test_pages_no_transport_or_http`, `test_ui_no_database_writes`) pass.

### 7.3 Tests
- [ ] `tests/gui/test_dashboard_no_autopoll.py` – verifies absence of timers/websockets/transport leakage.
- [ ] `tests/gui/test_dashboard_bridge_determinism.py` – verifies DTO determinism and intelligence generation.
- [ ] Existing policy tests updated if needed.

---

## 8. Implementation Phases (One‑Shot)

1. **Phase 1 – Write UI Contract Documentation** (this document)
2. **Phase 2 – DTO Contract Upgrade** (`src/FishBroWFS_V2/gui/contracts/dashboard_dto.py`)
3. **Phase 3 – DashboardBridge Upgrade** (`src/FishBroWFS_V2/gui/nicegui/bridge/dashboard_bridge.py`)
4. **Phase 4 – Dashboard Page UI Overhaul** (`src/FishBroWFS_V2/gui/nicegui/pages/home.py`)
5. **Phase 5 – Tests** (update/add tests for UI‑1/2 compliance)
6. **Phase 6 – Verification** (`make check`, `make dashboard`)

---

## 9. Rationale

**Why UI‑1/2?**  
UI‑0 established a deterministic, zero‑leakage foundation. UI‑1/2 adds **semantic intelligence** (explanations, stability flags, plateau hints) that makes the dashboard **operationally useful** without reintroducing non‑determinism. All intelligence is computed server‑side (or bridge‑side) from the same snapshot, preserving the thin‑client contract.

**Why deterministic intelligence?**  
Intelligence that depends on client time, random seeds, or unstable ordering would break snapshot comparability and forensic auditing. By using deterministic rules (score thresholds, rank‑based explanations), the dashboard remains a **forensic evidence package** that can be reproduced exactly from the same system state.

**Why keep manual refresh?**  
Auto‑polling timers are a source of non‑determinism and can cause cascading failures. Manual refresh puts the user in control and ensures that the UI does not generate unexpected network traffic. The “real‑time feel” is achieved by **semantic intelligence** computed from the snapshot, not by live updates.

**Why flattened snapshot artifacts?**  
As per ADR‑011, snapshot artifacts must be flattened to exactly two human‑facing files. This contract ensures that the dashboard respects that decision and does not create intermediate audit files.

---

**Status:** DRAFT (UI‑1/2 contract)

**Last Updated:** 2025‑12‑27

**Owner:** UI/UX Working Group
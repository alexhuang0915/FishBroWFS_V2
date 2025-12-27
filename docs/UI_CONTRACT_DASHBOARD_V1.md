# FishBroWFS_V2 – UI Contract Dashboard V1 (UI‑0)

This document defines the **UI‑0** (Determinism‑Safe) dashboard contract for the FishBroWFS_V2 NiceGUI interface. The contract ensures that the dashboard remains a **thin client** with **zero leakage**, **no auto‑polling**, and **deterministic rendering**.

---

## 1. UI‑0 Scope

**UI‑0** is the **first deterministic dashboard layout** that replaces the current home page (`/`) with a dark‑purple “Ops Dashboard” grid‑cards layout. It is a **snapshot‑based**, **manual‑refresh** interface that satisfies the following non‑negotiable constraints:

- **No auto‑polling timers** (`ui.timer`, `setInterval`, `setTimeout` for data fetching)
- **No websocket streams** (no live updates, no push notifications)
- **No client‑derived ETA** (all timestamps must come from server‑supplied snapshot)
- **No auto‑refresh on page load** (no network calls triggered by `onload` or `mounted`)
- **No sorting based on unstable timestamps** (ordering must be deterministic, e.g., by `(-score, instance)`)

**UI‑0 is a legislative step** that enforces the **Zero‑Leakage Architecture** (all backend access must go through Domain Bridges) and **Determinism‑First UI** (no environmental non‑determinism introduced by the UI layer).

---

## 2. UI Blocks (Dashboard Grid Cards)

The dashboard must be composed of the following UI blocks, arranged in a responsive grid:

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

### 2.4 Latest Candidates
- List of top‑5 candidates (sorted by score descending)
- Each candidate: candidate ID, score, strategy, dataset, timestamp
- **Deterministic ordering** (`(-score, candidate_id)`)

### 2.5 System Logs
- Latest 10 lines from system logs (read from `outputs/logs/` via bridge)
- **No tail‑following** (static snapshot only)

### 2.6 Navigation Tabs
- Dashboard (current page)
- Wizard (`/wizard`)
- History (`/history`)
- Candidates (`/candidates`)
- Portfolio (`/portfolio`)
- Deploy (`/deploy`)
- Settings (`/settings`)

### 2.7 Refresh Button
- A single **Refresh** button that triggers a manual refresh of the entire dashboard.
- On click, calls `DashboardBridge.get_snapshot()` and re‑renders all UI blocks with the returned data.
- **No automatic refresh** after button click (no periodic timer).

---

## 3. Forbidden Behavior (UI‑0 Prohibitions)

The following are **strictly forbidden** in UI‑0:

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

### 4.1 DashboardSnapshotDTO
```python
@dataclass(frozen=True)
class DashboardSnapshotDTO:
    season: str
    system_online: bool
    total_runs: int
    portfolio_status: PortfolioStatusDTO
    deploy_status: DeployStatusDTO
    active_ops: Tuple[ActiveOpDTO, ...]  # deterministic ordering
    latest_candidates: Tuple[CandidateDTO, ...]  # sorted by (-score, candidate_id)
    system_logs: Tuple[str, ...]  # latest 10 lines
    snapshot_timestamp: datetime  # server timestamp of snapshot generation
```

### 4.2 Supporting DTOs
- `PortfolioStatusDTO`: `candidates_count`, `deployed_count`, `pending_count`
- `DeployStatusDTO`: `ready`, `pending_jobs`, `last_deploy_time`
- `ActiveOpDTO`: `job_id`, `status`, `progress_pct`, `eta_seconds`, `start_time`
- `CandidateDTO`: `candidate_id`, `score`, `strategy_name`, `dataset`, `timestamp`

All DTOs must be **frozen** (immutable) and have **deterministic ordering** when represented as tuples.

---

## 5. DashboardBridge Contract

A new bridge `DashboardBridge` must be implemented in `src/FishBroWFS_V2/gui/nicegui/bridge/dashboard_bridge.py` with the following interface:

```python
class DashboardBridge:
    def get_snapshot(self) -> DashboardSnapshotDTO:
        """
        Return a complete snapshot of dashboard data.
        
        This method:
        - MUST be deterministic (same inputs → same output)
        - MUST NOT perform any side effects (read‑only)
        - MUST fetch data from Control API via existing bridges (JobsBridge, MetaBridge, etc.)
        - MUST NOT introduce any auto‑polling or timers
        - MUST return a frozen DTO
        """
```

The bridge must compose data from existing bridges (JobsBridge, MetaBridge, ArtifactsBridge, etc.) and the Control API client. It must **not** make direct HTTP calls (must reuse existing bridges).

---

## 6. Acceptance Criteria

### 6.1 Functional
- [ ] Dashboard page (`/`) renders all UI blocks in a dark‑purple grid‑cards layout.
- [ ] Refresh button triggers a single bridge call and updates all UI blocks.
- [ ] No auto‑polling timers are present in the page (verified by test).
- [ ] No websocket connections are established (verified by test).
- [ ] All data is sourced from `DashboardBridge.get_snapshot()`.
- [ ] Ordering of candidates and logs is deterministic across refreshes.
- [ ] UI complies with Zero‑Leakage Architecture (no transport imports).

### 6.2 Non‑Functional
- [ ] `make check` passes (no test regressions).
- [ ] `make dashboard` starts the dashboard without errors.
- [ ] Snapshot flattening compliance: `make snapshot` produces only `SYSTEM_FULL_SNAPSHOT.md`.
- [ ] Runtime context flattened: `make dashboard` writes `RUNTIME_CONTEXT.md` directly under `outputs/snapshots/`.
- [ ] All policy tests (`test_pages_no_transport_or_http`, `test_ui_no_database_writes`) pass.

### 6.3 Tests
- [ ] `tests/gui/test_dashboard_no_autopoll.py` – verifies absence of timers/websockets.
- [ ] `tests/gui/test_dashboard_bridge_determinism.py` – verifies DTO determinism.
- [ ] Existing policy tests updated if needed.

---

## 7. Implementation Phases

1. **Phase 1 – Write UI Contract Documentation** (this document)
2. **Phase 2 – Implement Dashboard DTOs** (`src/FishBroWFS_V2/gui/contracts/dashboard_dto.py`)
3. **Phase 3 – Implement DashboardBridge** (`src/FishBroWFS_V2/gui/nicegui/bridge/dashboard_bridge.py`)
4. **Phase 4 – Update Dashboard Page Layout** (`src/FishBroWFS_V2/gui/nicegui/pages/home.py`)
5. **Phase 5 – Add Tests** (`tests/gui/test_dashboard_no_autopoll.py`, `test_dashboard_bridge_determinism.py`)
6. **Phase 6 – Verify Determinism & Zero‑Leakage** (`make check`, `make dashboard`)

---

## 8. Rationale

**Why UI‑0?**  
The current dashboard uses `ui.timer` to fetch worker status on page load, which introduces environmental non‑determinism and violates the Zero‑Leakage principle. UI‑0 is a **legislative step** that enforces a strict contract before adding intelligence (UI‑1). This ensures that the UI layer remains a **thin client** and that all backend access is funneled through Domain Bridges, eliminating “whack‑a‑mole” runtime breakages.

**Why snapshot‑based?**  
Snapshots provide a **deterministic view** of system state at a point in time. They are **forensic evidence packages** that can be stored, compared, and audited. By rendering snapshots, the UI avoids live data streams that could introduce flakiness and non‑determinism.

**Why manual refresh only?**  
Auto‑polling timers are a source of non‑determinism and can cause cascading failures (e.g., network timeouts, rate limiting). Manual refresh puts the user in control and ensures that the UI does not generate unexpected network traffic.

**Why flattened snapshot artifacts?**  
As per ADR‑011, snapshot artifacts must be flattened to exactly two human‑facing files. This contract ensures that the dashboard respects that decision and does not create intermediate audit files.

---

**Status:** FROZEN (UI‑0 contract)

**Last Updated:** 2025‑12‑27

**Owner:** UI/UX Working Group
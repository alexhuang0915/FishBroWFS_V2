# FishBroWFS_V2 – Project Record (Authoritative)

Last updated: 2025-12-19  
Status: Phase 0 → Phase 8 MVP COMPLETED  
make check: PASS

---

## 專案一句話定位

FishBroWFS_V2 不是一個回測工具，而是一個
**不會對研究者說謊、可審計、可回放的量化研究平台**。

---

## Phase 0 – Foundation (Engine Constitution)

**目標：**
- 系統不可悄悄壞掉
- 所有結果必須可重現

**裁決：**

- Strategy / Engine / Data 嚴格分層
- MC-Exact 成交語義
- make check 為唯一安全入口
- 禁止隱性 state、bytecode 污染

**參考文件：**
- phase0_4/PHASE4_DEFINITION.md

**狀態：** FROZEN

---

## Phase 1–2 – Engine & Strategy Definition (ENGINE FREEZE)

**目標：**
- 先正確，再快
- Engine 語義一次鎖死

**裁決：**
- Strategy / Engine 完全分離
- MC-Exact 語義對齊
- Engine 已凍結（RED TEAM Approved）

**狀態：** FROZEN

---

## Phase 3 – Funnel Architecture & OOM Gate

**目標：**
- 防止 brute-force 回測
- 在 alloc 前阻止記憶體災難

**裁決：**
- Funnel 分 Stage0 / Stage1 / Stage2
- OOM Gate = 純函式（PASS / AUTO_DOWNSAMPLE / BLOCK）
- Auto-downsample 單調遞減

**參考文件：**
- phase0_4/STAGE0_FUNNEL.md
- phase5_governance/PHASE5_FUNNEL_B2.md
- phase5_governance/PHASE5_OOM_GATE_B3.md

**狀態：** FROZEN

---

## Phase 4 – Audit Schema & Viewer (B5)

**目標：**
- 結果必須可信、可回溯

**裁決：**
- Pydantic v2 Schema（manifest / winners_v2 / governance）
- EvidenceLink 指向來源
- Viewer 永不 raise

**狀態：** FROZEN

---

## Phase 5 – Governance / Audit / Artifacts

**目標：**
- 每一次 run 都可被審計、回放、比對

**裁決：**
- Manifest / Metrics / README 為一級公民
- EvidenceLink 指向來源
- Viewer 永不 raise

**參考文件：**
- phase5_governance/PHASE5_GOVERNANCE_B4.md
- phase5_governance/PHASE5_ARTIFACTS.md
- phase5_governance/PHASE5_AUDIT.md

**狀態：** FROZEN

---

## Phase 6 – Contract Enforcement (Completed)

**解決的關鍵問題：**
- TOCTOU race
- buffer overflow
- deadlock
- schema drift
- test / code 行為不一致

**狀態：** FROZEN（make check = 系統健康保證）

---

## Phase 6.5 – Raw Data Ingest Constitution

**目標：**
- 消除資料謊言的根源

**裁決（不可違反）：**
- Raw 不 sort / 不 dedup / 不 dropna / 不 parse datetime
- fingerprint = SHA1
- parquet 僅為 cache

**參考文件：**
- phase6_data/DATA_INGEST_V1.md

**狀態：** FROZEN

---

## Phase 6.6 – Derived Data (Session / DST / K-bar)

**目標：**
- 正確處理 DST / 交易所休市 / Session 邊界

**裁決：**
- 全系統輸入時間為 Asia/Taipei string
- DST 僅存在於 Derived 層
- Session state 僅允許 TRADING / BREAK
- BREAK 為 K-bar 絕對切斷邊界
- tzdb provider/version 記錄於 manifest

**狀態：** FROZEN（make check PASS）

---

## Phase 7 – Strategy System

**目標：**
- 策略可擴充但不可污染系統

**裁決：**
- Strategy Contract（純函式、deterministic）
- Registry / Runner 顯式載入
- Manifest 記錄 strategy metadata

**參考文件：**
- phase7_strategy/STRATEGY_CONTRACT_V1.md

**狀態：** FROZEN

---

## Phase 8 – Portfolio OS (MVP)

**目標：**
- 將 Strategy 組合提升為一級公民
- Portfolio 可版本化、可回放、可審計

**已完成能力：**
- PortfolioSpec（宣告式）
- Loader / Validator / Compiler
- Portfolio artifacts（spec snapshot / hash / index）
- 與 Phase 6.6 / Phase 7 完全相容

**裁決：**
- MNQ/MXF 僅為 MVP 驗證
- 更換策略/商品不影響架構

**狀態：** DONE

---

## Governance Completion

With Phase 8 completed, the system enters a governance-complete state.

The following documents define hard boundaries:
- **NON_GOALS.md** - What the system explicitly does NOT do
- **ARCHITECTURE_DECISIONS.md** - ADR (Architecture Decision Records) collection

From this point forward:
- Core behavior is frozen
- Extensions must respect all recorded decisions
- Any deviation must be explicitly documented as a new ADR

---

## Future Work (Optional Extensions)

**Phase 6.2 – Evidence UX**
- KPI → Evidence drill-down
- JSON highlighting
- Chart annotations
- Diff view

**Phase 6.3 – Multi-run Analysis**
- Regression detection
- Drift visualization
- Performance decay

---

## 總結裁決

FishBroWFS_V2 核心架構已完成並封印。
後續工作僅允許：
- 新策略（遵守 Strategy Contract）
- 新 Portfolio spec
- Read-only analysis / viewer

任何破壞既有 contract 的變更皆視為 invalid。

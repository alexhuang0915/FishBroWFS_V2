# FishBroWFS_V2 專案全紀錄與工程驗證報告

**版本**: v2025-12  
**狀態**: 可日用 × 可併發 × 可審計 × 可回歸驗證

---

## 一、專案總覽（Executive Summary）

FishBroWFS_V2 是一套以「**語義正確、可審計、可治理**」為最高優先的量化回測與 WFS（Walk-Forward Search）系統。

### 設計哲學

本系統的設計目標**不是「跑得快」**，而是：

- ✅ **不會悄悄壞掉**
- ✅ 每一個結果都能被追溯、被質疑、被驗證
- ✅ 能在長期演進中承受功能擴充與人員變動

### 當前狀態

截至目前（`make check` 全綠），系統已進入：

**可日用 × 可併發 × 可審計 × 可回歸驗證** 的成熟階段

---

## 二、Phase 0 — 憲法與工程地基（FOUNDATION）

### 🎯 目標

建立一個「**不能悄悄壞掉**」的量化研究系統。

### 🧱 核心機制

#### 1️⃣ Engine Constitution（成交語義憲法）

明確鎖死：

- Stop 成交價格
- Next-bar 生效規則
- 同 bar 先進後出是否允許
- **策略端只產生意圖，Engine 只負責成交**

#### 2️⃣ Repo 結構憲法

- 禁止 root 出現 `.py`
- Engine / Control / Viewer 強制分層
- `scripts/` 只能是 entrypoint，不得含核心邏輯

#### 3️⃣ `make check` = 唯一安全入口

- pre-commit
- pytest（`NUMBA_DISABLE_JIT`）
- 結構與契約測試

### ❌ 遇到的問題

- Python 專案容易因隱性 state（`__pycache__`、numba cache）產生不可重現 bug
- Repo 演進過程中結構容易「慢慢爛掉」

### ✅ 驗證方式

- 結構契約測試（`tests/test_repo_structure_contract.py`）
- CI 強制跑 `make check`
- 禁止 bytecode 產生（`PYTHONDONTWRITEBYTECODE`）

### 🛠 解決方案

- Engine Constitution + Repo Constitution 全面測試化
- 結構違規直接 CI fail

### 📌 狀態

**完成，且長期穩定**

---

## 三、Phase 1–2 — Engine & Strategy 定義（ENGINE FREEZE）

### 🎯 目標

**先正確，再快**

### 🧱 核心機制

#### 1️⃣ 策略 / 引擎完全分離

**Strategy：**
- 計算指標
- 產生 Orders（意圖）

**Engine：**
- 不知道指標
- 不知道策略
- 只處理成交

#### 2️⃣ 統一相對定義

所有 regime / gate：
- `rank` / `zscore` / `ratio`
- 避免硬門檻造成 regime shift 失效

### ❌ 遇到的問題

- Engine 行為若不一次鎖死，後續所有結果都不可比較
- 性能優化過早會破壞語義正確性

### ✅ 驗證方式

- 與 MultiCharts 對齊（MC-Exact）
- RED TEAM 審核並**正式 Freeze Engine**

### 📌 狀態

**Engine 已凍結（RED TEAM Approved）**

---

## 四、Phase 3 — Funnel & OOM Gate（SAFETY LAYER）

### 🎯 目標

避免「一按就爆 RAM」的災難性失敗。

### 🧱 核心機制

#### 1️⃣ OOM Gate（純函式）

**輸入：** `cfg + mem_limit`

**輸出：**
- `PASS`
- `AUTO_DOWNSAMPLE`
- `BLOCK`

#### 2️⃣ Auto-downsample（單調遞減）

- 永遠只會減少 subsample
- 可審計：
  - `original_subsample`
  - `final_subsample`
  - `mem_est / mem_limit`

### ❌ 遇到的問題

**In-place mutation 會導致：**
- `config_hash` 與實際跑的參數不一致

**Downsample 搜尋不嚴謹會出現：**
- 明明能降卻 BLOCK
- subsample 反而變大

### ✅ 驗證方式

- OOM Gate contract tests
- Funnel integration tests（驗 snapshot/hash 一致性）

### 🛠 解決方案

- OOM Gate 改為純函式
- 單調 step-search
- 所有估算統一走 `oom_cost_model`（可 monkeypatch）

### 📌 狀態

**完成，並有完整防回歸測試**

---

## 五、Phase 4 — Audit Schema & Viewer（B5）

### 🎯 目標

結果必須可信、可回溯

### 🧱 核心機制

#### 1️⃣ Pydantic v2 Schema

- `manifest`
- `winners_v2`
- `governance`

#### 2️⃣ EvidenceLink

- `source_path`
- `json_pointer`
- `render_hint`
- `render_payload`

#### 3️⃣ Viewer 永不 raise

- `OK` / `MISSING` / `INVALID(DIRTY)`
- `try_read_artifact()` 捕捉所有錯誤

### ❌ 遇到的問題

- UI 一旦因壞資料 crash，審計價值歸零
- Schema 若不鎖，Evidence UX 無法演進

### ✅ 驗證方式

- UI artifact validation tests
- Never-raise contract tests

### 📌 狀態

**Viewer-only 架構完成，可讀任何歷史 run**

---

## 六、Phase 5 — Dual Tower UI（Mission Control / Viewer）

### 🎯 目標

控與看分離，治理而非混用

### 🧱 核心機制

```
Mission Control (NiceGUI)  →  Worker
Audit Viewer (Streamlit)   →  Read-only outputs
```

**Control：**
- 建立 Job
- START / PAUSE / STOP

**Viewer：**
- 不碰 DB
- 不跑任務
- 只讀 artifacts

### ❌ 遇到的問題（Critical）

1. **Worker 使用 `subprocess.PIPE` 但不讀 → Deadlock**
2. **NiceGUI 讀 log 用 `readlines()` → RAM 爆炸**
3. **SQLite 併發 write → database locked**

### ✅ 驗證方式

- API worker spawn no-pipe test
- log tail test
- DB concurrency smoke test

### 🛠 解決方案

- `stdout/stderr` 重定向至檔案
- log tail 用 `deque`
- SQLite WAL + `busy_timeout` + retry
- 原子化狀態更新

### 📌 狀態

**Mission Control 可日用、可併發**

---

## 七、Phase 6 — Contract 地獄（已通關）

### 解決的關鍵問題

這一階段解掉了：

- ✅ **TOCTOU race**
- ✅ **buffer overflow**
- ✅ **deadlock**
- ✅ **schema drift**
- ✅ **test / code 行為不一致**

### 當前狀態

現在 **`make check` = 系統健康保證**

---

## 八、未來規劃（Now → Next）

### Phase 6.2 — Evidence UX

- KPI → Evidence drill-down
- JSON 高亮
- `chart_annotation`
- `diff view`

### Phase 6.3 — Multi-run Analysis

- Regression detection
- Drift visualization
- Performance decay

### Phase 7 — Portfolio OS

- KEEP / FREEZE / DROP
- Governance 影響下一輪 WFS
- Export → MultiCharts / Portfolio Trader

---

## 九、最終工程結論

> **FishBroWFS_V2 不是一套「寫完的程式」，  
> 而是一套「不容易被寫壞的系統」。**

這是工程上極少見、但最有價值的完成度。

### 核心價值

- 🔒 **可回歸驗證**：`make contract` 鎖死關鍵契約
- 🔍 **可審計**：每個結果都有完整證據鏈
- 🛡️ **可治理**：Governance 決策可追溯
- ⚡ **可併發**：WAL + retry + 原子更新
- 📊 **可日用**：Mission Control + Viewer 分離

### 關鍵測試

```bash
# 快速驗證關鍵契約
make contract

# 完整測試套件
make check
```

### 測試覆蓋

- ✅ Worker spawn deadlock 防護
- ✅ Engine fill buffer 容量保護
- ✅ Log tail 記憶體效率
- ✅ DB 併發安全性
- ✅ OOM Gate 單調性
- ✅ Schema 契約一致性

---

## 附錄：關鍵檔案索引

### 核心模組

- `src/FishBroWFS_V2/engine/engine_jit.py` - Engine 核心（已凍結）
- `src/FishBroWFS_V2/core/oom_gate.py` - OOM Gate 決策
- `src/FishBroWFS_V2/control/jobs_db.py` - 作業資料庫（WAL + retry）
- `src/FishBroWFS_V2/control/api.py` - Mission Control API

### 關鍵測試

- `tests/test_api_worker_spawn_no_pipes.py` - Worker deadlock 防護
- `tests/test_engine_fill_buffer_capacity.py` - Buffer 容量保護
- `tests/test_log_tail_reads_last_n_lines.py` - Log tail 效率
- `tests/test_jobs_db_concurrency_smoke.py` - DB 併發安全性
- `tests/test_oom_gate_contract.py` - OOM Gate 契約

### 文檔

- `docs/PHASE4_DEFINITION.md` - Phase 4 定義
- `docs/PHASE5_ARTIFACTS.md` - Phase 5 產物
- `docs/PHASE5_AUDIT.md` - Phase 5 審計
- `docs/STAGE0_FUNNEL.md` - Stage0 Funnel

---

**最後更新**: 2025-12  
**維護狀態**: 活躍開發中

# Phase 12: Research Job Wizard

## 目的

Phase 12 建立一個「配置專用」的研究工作精靈，讓使用者透過 GUI 介面組裝研究任務，輸出標準化的 `JobSpec` JSON 檔案。精靈嚴格遵守「配置唯一」原則，不觸碰執行階段狀態。

## 三條鐵律

### 1. Config-only（配置專用）
- **GUI 的唯一產出** = `JobSpec` JSON
- **禁止**呼叫 worker、存取 filesystem、啟動任何 job
- **只允許** `POST /jobs {JobSpec}`

### 2. Registry auto-gen（註冊表自動生成）
- **Dataset Registry**：自動掃描 `data/derived/` 生成 `datasets_index.json`
- **Strategy Registry**：從策略程式碼提取 `ParamSchema` 自動生成
- **禁止**手動維護註冊表，確保與實體檔案 1:1 對應

### 3. Strategy introspection（策略內省）
- **GUI 不得 hardcode** 任何策略參數
- 參數 UI 從 `ParamSchema` 動態生成：
  - `int/float` → slider
  - `enum` → dropdown  
  - `bool` → toggle
- 新增策略只需註冊 `StrategySpec`，GUI 自動適應

## 系統架構

### 核心元件

```
src/FishBroWFS_V2/
├── data/
│   └── dataset_registry.py      # DatasetRecord, DatasetIndex schema
├── strategy/
│   ├── param_schema.py          # ParamSpec for GUI introspection
│   └── registry.py              # Enhanced for Phase 12 (StrategySpecForGUI)
├── control/
│   ├── job_spec.py              # JobSpec, DataSpec, WFSSpec
│   ├── api.py                   # + /meta/datasets, /meta/strategies
│   └── wizard_nicegui.py        # Research Job Wizard UI
└── scripts/
    └── build_dataset_registry.py # Automated registry generation
```

### 資料流

```
User → Wizard UI → JobSpec JSON → POST /jobs → DB
       ↑           ↑              ↑
       Registry    Registry       API
       (datasets)  (strategies)   (meta endpoints)
```

## JobSpec 範例

```json
{
  "season": "2024Q1",
  "data1": {
    "dataset_id": "CME.MNQ.60m.2020-2024",
    "start_date": "2020-01-01",
    "end_date": "2024-12-31"
  },
  "data2": null,
  "strategy_id": "sma_cross_v1",
  "params": {
    "window": 20,
    "threshold": 0.5
  },
  "wfs": {
    "stage0_subsample": 1.0,
    "top_k": 100,
    "mem_limit_mb": 4096,
    "allow_auto_downsample": true
  }
}
```

## GUI 使用流程（功能版）

### Step 1: Data（資料選擇）
1. **Primary Dataset**：從 `/meta/datasets` 下拉選擇
2. **Date Range**：自動限制在 dataset 的 start/end 範圍內
3. **Secondary Dataset**（可選）：用於驗證的對照資料集

### Step 2: Strategy（策略選擇）
1. **Strategy**：從 `/meta/strategies` 下拉選擇
2. **Parameters**：根據 `ParamSchema` 動態生成 UI
   - 數值參數 → 滑桿（含 min/max/step）
   - 枚舉參數 → 下拉選單
   - 布林參數 → 開關

### Step 3: WFS Configuration（系統配置）
1. **Stage0 Subsample**：取樣比例 (0.01-1.0)
2. **Top K**：保留頂部策略數量 (1-1000)
3. **Memory Limit**：記憶體限制 MB (1024-32768)
4. **Allow Auto Downsample**：記憶體不足時自動降取樣

### Step 4: Preview & Submit（預覽與提交）
1. **JobSpec Preview**：即時顯示 JSON 預覽
2. **Submit**：`POST /jobs` 提交任務
3. **Copy JSON**：複製 JobSpec 到剪貼簿

## 技術實現細節

### Dataset Registry 自動生成

```bash
# 生成 dataset registry
python scripts/build_dataset_registry.py

# 輸出：outputs/datasets/datasets_index.json
```

**規則**：
- 掃描 `data/derived/{SYMBOL}/{TIMEFRAME}/{START}-{END}.parquet`
- 使用檔案內容 SHA1 作為 fingerprint（非 mtime/size）
- 刪除 index → 重跑 → 產出一模一樣（deterministic）

### Strategy Registry 內省

```python
# 策略註冊（builtin 策略自動載入）
from FishBroWFS_V2.strategy.registry import load_builtin_strategies
load_builtin_strategies()

# GUI 取得策略清單
response = requests.get("http://localhost:8000/meta/strategies")
# 返回 StrategySpecForGUI 列表，含 ParamSpec
```

### API 啟動依賴

```python
# API server 啟動時載入 registries
def lifespan(app: FastAPI):
    _dataset_index = load_dataset_index()      # 從 outputs/datasets/datasets_index.json
    _strategy_registry = load_strategy_registry()  # 從策略註冊表
    
    # 若 dataset index 不存在 → raise RuntimeError (fail fast)
```

## 測試覆蓋

### 單元測試
- `tests/data/test_dataset_registry.py`：Dataset Registry 建置與驗證
- `tests/strategy/test_strategy_registry.py`：Strategy Registry 與 ParamSchema
- `tests/control/test_meta_api.py`：Meta endpoints 回應驗證
- `tests/control/test_job_wizard.py`：JobSpec 結構與驗證

### 整合測試重點
1. **Dataset Registry**：給 fake fixture 能正確產出 id/symbol/timeframe/start/end
2. **Fingerprint**：不為空，content-based（非 mtime/size）
3. **start_date <= end_date**：自動驗證
4. **JobSpec schema**：必填欄位檢查，與 CLI job 結構一致

## 易踩雷點清單

### ❌ 禁止事項
1. **不准掃 filesystem 給 GUI** → 用 `/meta/datasets` API
2. **不准 hardcode strategy params** → 用 `ParamSchema` 動態生成
3. **不准動 core/engine/funnel** → GUI 只產出 JobSpec
4. **不准讓 GUI 直接跑 job** → 只允許 `POST /jobs`
5. **不准破壞 deterministic config_hash** → JobSpec 必須 immutable

### ✅ 必須事項
1. **Dataset Registry 可全自動生成**
2. **GUI 可選 Data1/Data2/期間/策略/WFS**
3. **Strategy 參數由 ParamSchema 自動生成**
4. **GUI 只輸出 JobSpec JSON**
5. **Submit 後 job 與 CLI 建的在 DB/Log 中無差異**

## Phase 12 MVP 完成判準

以下 **全部成立** 才算完成：

- [ ] Dataset Registry 可全自動生成（執行 script 即產出）
- [ ] GUI 可透過 `/meta/datasets` 選擇 Data1/Data2
- [ ] GUI 可透過 `/meta/strategies` 選擇策略
- [ ] Strategy 參數 UI 由 `ParamSchema` 動態生成
- [ ] GUI 只輸出 `JobSpec` JSON（無其他副作用）
- [ ] Submit 後 job 與 CLI 建立的無差異（DB/Log 一致）
- [ ] Job 完成後可一鍵 Open in Viewer

## 檔案清單

### 新增檔案
```
src/FishBroWFS_V2/data/dataset_registry.py
src/FishBroWFS_V2/strategy/param_schema.py
src/FishBroWFS_V2/control/job_spec.py
src/FishBroWFS_V2/control/wizard_nicegui.py
scripts/build_dataset_registry.py
tests/data/test_dataset_registry.py
tests/strategy/test_strategy_registry.py
tests/control/test_meta_api.py
tests/control/test_job_wizard.py
docs/PHASE12_RESEARCH_JOB_WIZARD.md
```

### 修改檔案
```
src/FishBroWFS_V2/strategy/registry.py      # + Phase 12 enhancements
src/FishBroWFS_V2/control/api.py           # + /meta endpoints
```

## 後續擴展方向

1. **Job Template**：儲存常用 JobSpec 為模板
2. **Batch Jobs**：一次提交多個相關任務
3. **Parameter Grid**：參數網格自動展開
4. **Validation Rules**：跨欄位驗證（如 data2 時間範圍需在 data1 內）
5. **Estimation**：根據配置預估執行時間/記憶體需求

---

**Phase 12 核心精神**：將複雜的研究任務配置標準化、自動化、可審計化，同時保持系統的簡潔與確定性。

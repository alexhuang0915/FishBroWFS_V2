# Phase 5 B2: Funnel Pipeline (Coarse → Fine)

## 概述

Funnel Pipeline 提供三階段管線：從粗粒度探索到精細確認。每個 stage 獨立執行並產出 artifacts，stage 之間只靠 artifacts 串接（不依賴 in-memory 共享狀態）。

## 核心原則

1. **禁止修改 kernel/engine**：Funnel 只能讀 config → 跑 → 寫 artifacts
2. **Artifacts 串接**：Stage 之間只靠 artifacts 串接，不靠 in-memory 狀態
3. **param_subsample_rate 一級公民**：每個 stage 的 manifest/metrics/README 必須顯示且一致
4. **Stage2 必須 1.0**：Stage2 的 subsample_rate 必須是 1.0（full confirm）

## Stage 定義

### Stage 0: Coarse Exploration

**目的**: 粗粒度探索，快速篩選參數空間

**輸入**:
- `param_subsample_rate`: 來自 config（例如 0.1 = 10%）
- `topk`: Top-K 數量（預設 50）

**輸出**:
- `manifest.json`: 包含 `param_subsample_rate`
- `metrics.json`: 包含 `param_subsample_rate` 和 `params_effective`
- `winners.json`: Top-K 參數列表（proxy_value 排序）

**Subsample 規則**: 使用 config 的 `param_subsample_rate`

### Stage 1: Top-K Refinement

**目的**: 在 Stage0 的 Top-K 基礎上，增加 subsample 密度進行精煉

**輸入**:
- `param_subsample_rate`: `min(1.0, stage0_rate * 2)`（例如 0.1 → 0.2）
- `topk`: Top-K 數量（預設 20）
- 可選：使用 Stage0 的 winners 作為候選

**輸出**:
- `manifest.json`: 包含 `param_subsample_rate`
- `metrics.json`: 包含 `param_subsample_rate` 和 `params_effective`
- `winners.json`: Top-K 參數列表（net_profit 排序）

**Subsample 規則**: `min(1.0, stage0_rate * 2)`

### Stage 2: Full Confirmation

**目的**: 完整確認，使用所有參數（subsample_rate = 1.0）

**輸入**:
- `param_subsample_rate`: **必須是 1.0**
- `topk`: None（使用所有參數）
- 使用 Stage1 的 winners 作為候選

**輸出**:
- `manifest.json`: 包含 `param_subsample_rate = 1.0`
- `metrics.json`: 包含 `param_subsample_rate = 1.0` 和 `params_effective = params_total`
- `winners.json`: 完整結果列表

**Subsample 規則**: **固定 1.0**（不可變更）

## Subsample 升級規則

**鎖死規則**（在 `pipeline/funnel_plan.py` 中定義）：

```python
s0_rate = config["param_subsample_rate"]  # Stage0: config rate
s1_rate = min(1.0, s0_rate * 2.0)          # Stage1: 加倍（上限 1.0）
s2_rate = 1.0                              # Stage2: 必須 1.0
```

**範例**:
- Config `param_subsample_rate = 0.1`:
  - Stage0: 0.1 (10%)
  - Stage1: 0.2 (20%)
  - Stage2: 1.0 (100%)

- Config `param_subsample_rate = 0.6`:
  - Stage0: 0.6 (60%)
  - Stage1: 1.0 (120% → capped at 100%)
  - Stage2: 1.0 (100%)

## Artifacts 產出

每個 stage 產出以下 artifacts（在 `outputs/seasons/{season}/runs/{run_id}/`）：

1. **manifest.json**: 完整 AuditSchema（包含 `param_subsample_rate`）
2. **config_snapshot.json**: Stage 配置快照（**不包含 raw arrays**）
3. **metrics.json**: 效能指標（必須包含 `param_subsample_rate`）
4. **winners.json**: Top-K 結果（固定 schema: `{"topk": [...], "notes": {"schema": "v1"}}`）
5. **README.md**: 人類可讀摘要（必須顯示 `param_subsample_rate`）
6. **logs.txt**: 執行日誌

### Config Snapshot 契約

**重要**: `config_snapshot.json` **永遠不包含 raw arrays**。

- **排除**: `open_`, `high`, `low`, `close`, `params_matrix` 等 ndarray
- **包含**: `season`, `dataset_id`, `bars`, `params_total`, `param_subsample_rate`, `stage_name`, `topk`, `commission`, `slip`, `order_qty` 等可 JSON 序列化的配置
- **Metadata**: 如需要資料指紋，只保留 shape/dtype（`*_meta` 鍵），不保留 bytes hash

**原因**:
- Raw arrays 會導致 JSON 序列化失敗或文件過大
- Config hash 計算需要可序列化的資料
- Raw data 由 `dataset_id` 指向，必要時可從資料集重新載入

**範例**:
```json
{
  "season": "2025Q4",
  "dataset_id": "synthetic_20k",
  "bars": 20000,
  "params_total": 1000,
  "param_subsample_rate": 0.1,
  "stage_name": "stage0_coarse",
  "topk": 50,
  "commission": 0.0,
  "slip": 0.0,
  "order_qty": 1,
  "open__meta": {
    "__ndarray__": true,
    "shape": [20000],
    "dtype": "float64"
  }
}
```

## Funnel 只依賴 Artifacts 串接

**原則**: Stage 之間不共享 in-memory 狀態，只讀取前一個 stage 的 artifacts。

**實現方式**:
- Stage1 可以讀取 Stage0 的 `winners.json` 作為候選
- Stage2 可以讀取 Stage1 的 `winners.json` 作為候選
- 所有 stage 都寫入自己的 artifacts

**優點**:
- 可追溯：每個 stage 的輸入輸出都有記錄
- 可重現：可以從任意 stage 重新開始
- 可審計：所有決策都有 artifacts 記錄

## Runner Adapter 契約

`pipeline/runner_adapter.py` 提供統一介面：

```python
def run_stage_job(stage_cfg: dict) -> dict:
    """
    Returns:
        {
            "metrics": {...},
            "winners": {"topk": [...], "notes": {"schema": "v1"}}
        }
    """
```

**重要**: Adapter **不寫檔**，只回傳資料。所有寫檔由 `core/artifacts.py` 統一處理。

## Winners Schema

**固定 schema**（不可變更）：

```json
{
  "topk": [
    {
      "param_id": 42,
      "net_profit": 1234.56,
      "trades": 100,
      "max_dd": -50.0
    }
  ],
  "notes": {
    "schema": "v1",
    "stage": "stage2_confirm",
    "full_confirm": true
  }
}
```

## 使用方式

### 基本使用

```python
from pathlib import Path
from FishBroWFS_V2.pipeline.funnel_runner import run_funnel

cfg = {
    "season": "2025Q4",
    "dataset_id": "synthetic_20k",
    "bars": 20000,
    "params_total": 1000,
    "param_subsample_rate": 0.1,
    "open_": open_array,
    "high": high_array,
    "low": low_array,
    "close": close_array,
    "params_matrix": params_matrix,
    "commission": 0.0,
    "slip": 0.0,
    "order_qty": 1,
}

outputs_root = Path("outputs")
result_index = run_funnel(cfg, outputs_root)

# Access stage run directories
for stage_idx in result_index.stages:
    print(f"{stage_idx.stage.value}: {stage_idx.run_dir}")
```

### CLI 使用

```bash
python scripts/run_funnel.py --config config.json --outputs-root outputs
```

## 測試要求

所有測試必須驗證：

1. Funnel plan 有三個 stages
2. Stage2 subsample 是 1.0
3. 每個 stage 都產出 artifacts
4. `param_subsample_rate` 在所有 artifacts 中可見
5. `params_effective` 計算規則一致
6. Runner adapter 不寫檔
7. Winners schema 穩定

## OOM Gate 整合（B3）

Funnel 已整合 OOM Gate（見 `docs/PHASE5_OOM_GATE_B3.md`）。

**重要**: `oom_gate_original_subsample` 定義為「該 stage 進入 gate 前的 planned subsample」，不是全域初始 subsample。

- Stage0: `oom_gate_original_subsample` = config 的 `param_subsample_rate`
- Stage1: `oom_gate_original_subsample` = `min(1.0, stage0_rate * 2)`
- Stage2: `oom_gate_original_subsample` = `1.0`

## 易錯點

### ❌ 不要讓 adapter 寫檔

```python
# ❌ 錯誤：adapter 直接寫檔
def run_stage_job(cfg):
    result = run_grid(...)
    with open("output.json", "w") as f:
        json.dump(result, f)  # 不應該在這裡寫檔
    return result

# ✅ 正確：adapter 只回傳資料
def run_stage_job(cfg):
    result = run_grid(...)
    return {"metrics": ..., "winners": ...}  # 只回傳資料
```

### ❌ Stage2 必須 1.0

```python
# ❌ 錯誤：Stage2 不是 1.0
s2_rate = 0.9  # 這會被視為作弊

# ✅ 正確：Stage2 必須 1.0
s2_rate = 1.0  # 固定值
```

### ❌ Winners schema 不可漂

```python
# ❌ 錯誤：不同 stage 回傳不同格式
stage0_winners = [1, 2, 3]  # list
stage1_winners = {"top": [1, 2, 3]}  # dict

# ✅ 正確：所有 stage 回傳相同 schema
winners = {
    "topk": [...],
    "notes": {"schema": "v1"}
}
```

## 文件結構

- `pipeline/funnel_schema.py`: Stage 定義和結果索引
- `pipeline/funnel_plan.py`: Plan builder（決定三階段如何跑）
- `pipeline/runner_adapter.py`: Runner adapter（統一介面）
- `pipeline/funnel_runner.py`: Funnel orchestrator（執行管線）
- `scripts/run_funnel.py`: CLI 入口
- `tests/test_funnel_contract.py`: Funnel 契約測試
- `tests/test_runner_adapter_contract.py`: Adapter 契約測試

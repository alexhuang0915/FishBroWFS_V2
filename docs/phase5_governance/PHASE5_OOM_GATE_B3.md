# Phase 5 B3: OOM Gate (Memory/Cost Precheck + Failsafe)

## 概述

OOM Gate 在每個 Funnel stage 執行前進行記憶體和成本預檢查，防止 OOM 失敗。Gate 行為完全可審計，所有決策都記錄在 artifacts 中。

## 核心原則

1. **禁止修改 kernel/engine**：OOM Gate 只做預檢查，不修改核心邏輯
2. **Gate 在 stage 執行前**：必須在 `run_stage_job()` 之前執行
3. **完全可審計**：所有決策記錄在 `metrics.json` 和 `README.md`
4. **Subsample 一級公民**：任何調整都要寫入 manifest/metrics/README

## Gate 三種 Action

### PASS

**條件**: `mem_est_mb <= mem_limit_mb`

**行為**: 允許照原 subsample 執行

**記錄**:
- `oom_gate_action`: "PASS"
- `oom_gate_reason`: "mem_est_mb=X.X <= limit=Y.Y"
- `mem_est_mb`, `mem_limit_mb`, `ops_est`

### BLOCK

**條件**: `mem_est_mb > mem_limit_mb` 且 `allow_auto_downsample=False`，或即使降到 `auto_downsample_min` 仍超標

**行為**: 直接拒絕執行，丟出 `RuntimeError`

**記錄**:
- `oom_gate_action`: "BLOCK"
- `oom_gate_reason`: 詳細說明（需要多少 mem、限制是多少）
- `mem_est_mb`, `mem_limit_mb`, `ops_est`

### AUTO_DOWNSAMPLE

**條件**: `mem_est_mb > mem_limit_mb` 且 `allow_auto_downsample=True`，且可以通過降低 subsample 達到限制內

**行為**: 自動降低 `param_subsample_rate` 直到符合限制

**記錄**:
- `oom_gate_action`: "AUTO_DOWNSAMPLE"
- `oom_gate_reason`: 說明調整原因
- `oom_gate_original_subsample`: 原始 subsample
- `oom_gate_final_subsample`: 調整後 subsample
- `mem_est_mb`, `mem_limit_mb`, `ops_est`

**重要**: AUTO_DOWNSAMPLE 必須同步更新：
- `stage_cfg_runtime["param_subsample_rate"]`
- `stage_snapshot["param_subsample_rate"]`
- `AuditSchema.param_subsample_rate` (manifest)
- `metrics["param_subsample_rate"]`
- `README.md`

## Memory 估算策略

### 保守上界（Conservative Upper Bound）

Memory 估算包含：

1. **Price arrays**: `open_`, `high`, `low`, `close`
   - 計算: `bars * 8 bytes * num_arrays` (float64)

2. **Params matrix**: `params_matrix`
   - 計算: `params_total * param_dim * 8 bytes`

3. **Working buffers**: 保守倍數
   - `work_factor = 2.0` (鎖死可調)
   - 用於: 中間計算緩衝區、指標陣列、intent 陣列、fill 陣列等

### 注意事項

- **不因 subsample 降低估算**：保守策略不考慮 subsample，因為：
  - 某些分配是 per-bar（非 per-param）
  - Working buffers 可能以不同方式縮放
  - 保守估算對 OOM 預防更安全

- **未來可精緻化**：當前模型可能導致 AUTO 永遠不 PASS，這是允許的。後續可精緻化模型（但不碰 kernel）。

## Auto-Downsample 規則

### 參數（鎖死，可通過 cfg 調整）

- `auto_downsample_step`: 每次乘數（預設: 0.5）
- `auto_downsample_min`: 最低 subsample（預設: 0.02）

### 流程

1. 從原始 `param_subsample_rate` 開始
2. 每次乘以 `step`（例如 0.5）
3. 重新估算記憶體
4. 如果 `mem_est_mb <= mem_limit_mb` → PASS
5. 如果降到 `min` 仍超標 → BLOCK

### 範例

```
原始: 0.5
Step 1: 0.5 * 0.5 = 0.25 → 仍超標
Step 2: 0.25 * 0.5 = 0.125 → PASS
最終: 0.125
```

## Artifacts 欄位

### metrics.json 必含欄位

```json
{
  "oom_gate_action": "PASS" | "BLOCK" | "AUTO_DOWNSAMPLE",
  "oom_gate_reason": "...",
  "mem_est_mb": 123.45,
  "mem_limit_mb": 2048.0,
  "ops_est": 1000000
}
```

### AUTO_DOWNSAMPLE 額外欄位

```json
{
  "stage_planned_subsample": 0.5,
  "oom_gate_original_subsample": 0.5,
  "oom_gate_final_subsample": 0.125
}
```

**重要**: `oom_gate_original_subsample` 定義為「該 stage 進入 gate 前的 planned subsample」，不是全域初始 subsample。

- Stage0: `oom_gate_original_subsample` = config 的 `param_subsample_rate`
- Stage1: `oom_gate_original_subsample` = `min(1.0, stage0_rate * 2)`
- Stage2: `oom_gate_original_subsample` = `1.0`

`stage_planned_subsample` 與 `oom_gate_original_subsample` 應該相等（都是該 stage 的 planned subsample）。

### README.md 必含區塊

```markdown
## OOM Gate

- action: AUTO_DOWNSAMPLE
- reason: auto-downsample from 0.500 to 0.125 to fit mem_limit_mb=2048.0
- mem_est_mb: 123.4
- mem_limit_mb: 2048.0
- ops_est: 1000000
- original_subsample: 0.5
- final_subsample: 0.125
```

## 使用方式

### 基本使用（使用預設 limit）

```python
cfg = {
    "season": "2025Q4",
    "dataset_id": "synthetic_20k",
    "bars": 20000,
    "params_total": 1000,
    "param_subsample_rate": 0.1,
    # ... other fields
    # mem_limit_mb defaults to 2048.0 if not specified
}
```

### 自訂 limit

```python
cfg = {
    # ... other fields
    "mem_limit_mb": 4096.0,  # 4GB limit
    "allow_auto_downsample": True,
    "auto_downsample_step": 0.5,
    "auto_downsample_min": 0.01,
}
```

### 禁用 auto-downsample

```python
cfg = {
    # ... other fields
    "allow_auto_downsample": False,  # Will BLOCK if over limit
}
```

## 測試要求

所有測試必須驗證：

1. Gate PASS 當記憶體估算在限制內
2. Gate BLOCK 當超過限制且不允許 auto-downsample
3. Gate AUTO_DOWNSAMPLE 當允許且可調整
4. AUTO_DOWNSAMPLE 的一致性（runtime/snapshot/manifest/metrics/README）
5. BLOCK 動作丟出 RuntimeError

**重要**: 測試不應依賴實體 RAM，使用 monkeypatch 控制估算結果。

## 易錯點

### ❌ Gate 放錯位置

```python
# ❌ 錯誤：在 run_stage_job 之後
stage_out = run_stage_job(stage_cfg)
gate_result = decide_oom_action(stage_cfg)  # 太晚了

# ✅ 正確：在 run_stage_job 之前
gate_result = decide_oom_action(stage_cfg)
if gate_result["action"] == "BLOCK":
    raise RuntimeError(...)
stage_out = run_stage_job(stage_cfg)
```

### ❌ AUTO 一致性沒更新

```python
# ❌ 錯誤：只更新 runtime
stage_cfg["param_subsample_rate"] = final_subsample
# 忘記更新 snapshot/manifest/metrics

# ✅ 正確：同步更新所有
stage_cfg["param_subsample_rate"] = final_subsample
stage_snapshot = make_config_snapshot(stage_cfg)  # 包含 final_subsample
audit = AuditSchema(..., param_subsample_rate=final_subsample, ...)
metrics["param_subsample_rate"] = final_subsample
```

### ❌ 把 mem_limit 寫死

```python
# ❌ 錯誤：寫死 limit
mem_limit_mb = 2048.0

# ✅ 正確：允許 cfg 參數控制
mem_limit_mb = float(cfg.get("mem_limit_mb", 2048.0))
```

## 文件結構

- `core/oom_cost_model.py`: 記憶體和運算量估算
- `core/oom_gate.py`: Gate 決策器
- `pipeline/funnel_runner.py`: 整合 OOM gate（在 stage 執行前）
- `tests/test_oom_gate_contract.py`: Gate 單元測試
- `tests/test_funnel_oom_integration.py`: Funnel 整合測試

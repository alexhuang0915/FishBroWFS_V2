# Phase 5 B0: Audit Schema (Single Source of Truth)

## 概述

Audit Schema 是審計資料的唯一來源（SSOT），確保任何一次 run 都能被完整追溯。

## 核心概念

### AuditSchema 類別

`AuditSchema` 是 `core/audit_schema.py` 中定義的 frozen dataclass，包含所有必要的審計欄位。

### 欄位定義

#### 必填欄位

- **run_id** (`str`): 可排序、可讀的執行 ID
  - 格式: `{prefix-}YYYYMMDDTHHMMSSZ-{token}`
  - 範例: `20251218T135221Z-a1b2c3d4` 或 `test-20251218T135221Z-a1b2c3d4`
  - 由 `core/run_id.py` 的 `make_run_id()` 產生

- **created_at** (`str`): ISO8601 格式的時間戳記（UTC，Z 結尾）
  - 範例: `2025-12-18T13:52:21.123456Z`
  - 必須使用 UTC timezone，確保可比較、可排序

- **git_sha** (`str`): Git commit SHA
  - 至少 12 個字元
  - 如果不在 git repo 中，值為 `"unknown"`

- **dirty_repo** (`bool`): 是否有未提交的變更
  - `True`: 有未提交變更
  - `False`: 乾淨的 repo

- **param_subsample_rate** (`float`): 參數子採樣率
  - 範圍: `[0.0, 1.0]`
  - `1.0` 表示使用所有參數
  - 這是**一級公民**，必須在所有輸出中可見

- **config_hash** (`str`): 配置的穩定雜湊值
  - 64 字元 hex 字串（SHA256）
  - 用於驗證配置一致性
  - 由 `core/config_hash.py` 的 `stable_config_hash()` 產生

- **season** (`str`): 季節識別碼
  - 例如: `"2025Q4"`, `"2025-12"`

- **dataset_id** (`str`): 資料集識別碼
  - 例如: `"dataset_v1"`, `"synthetic_20k"`

- **bars** (`int`): 處理的 bar 數量

- **params_total** (`int`): 子採樣前的總參數數

- **params_effective** (`int`): 子採樣後的有效參數數
  - 計算規則: `int(params_total * param_subsample_rate)`（向下取整）
  - **此規則已鎖死**，在 code/docs/tests 三處一致

- **artifact_version** (`str`): Artifact 版本號
  - 預設: `"v1"`

## 使用方式

### 建立 AuditSchema

```python
from FishBroWFS_V2.core.audit_schema import AuditSchema, compute_params_effective
from FishBroWFS_V2.core.run_id import make_run_id
from FishBroWFS_V2.core.config_hash import stable_config_hash
from datetime import datetime, timezone

config = {
    "n_bars": 20000,
    "n_params": 1000,
    "commission": 0.0,
    "slip": 0.0,
}

param_subsample_rate = 0.1
params_total = 1000
params_effective = compute_params_effective(params_total, param_subsample_rate)

audit = AuditSchema(
    run_id=make_run_id(),
    created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    git_sha="a1b2c3d4e5f6",
    dirty_repo=False,
    param_subsample_rate=param_subsample_rate,
    config_hash=stable_config_hash(config),
    season="2025Q4",
    dataset_id="synthetic_20k",
    bars=20000,
    params_total=params_total,
    params_effective=params_effective,
    artifact_version="v1",
)
```

### 序列化

```python
# 轉換為字典
audit_dict = audit.to_dict()

# JSON 序列化
import json
audit_json = json.dumps(audit_dict)
```

## 契約（Contract）

1. **不可變性**: AuditSchema 是 frozen dataclass，一旦建立不可修改
2. **JSON 序列化**: 所有欄位必須可 JSON 序列化
3. **獨立性**: 不依賴外部狀態（不讀取全域變數）
4. **型別安全**: 所有欄位都有 type hints

## Run ID 格式

Run ID 由 `core/run_id.py` 產生：

- **格式**: `{prefix-}YYYYMMDDTHHMMSSZ-{token}`
- **可排序**: 時間戳記確保時間順序（UTC）
- **唯一性**: Token（8 hex chars）確保唯一性
- **可讀性**: 人類可讀的時間戳記

### 範例

```
20251218T135221Z-a1b2c3d4
test-20251218T140530Z-f9e8d7c6
```

## Config Hash 計算

`stable_config_hash()` 函數：

1. 將 config 字典排序鍵值（`sort_keys=True`）
2. 使用固定分隔符（`separators=(",", ":")`）
3. 轉換為 JSON 字串（`ensure_ascii=False`）
4. 計算 SHA256 hash

這確保相同配置會產生相同的 hash。

## params_effective 計算規則

**鎖死規則**: `int(params_total * param_subsample_rate)`

- 向下取整（floor）
- 在 `core/audit_schema.py` 的 `compute_params_effective()` 中實現
- 在 docs 和 tests 中保持一致

### 範例

```python
compute_params_effective(1000, 0.1)  # -> 100
compute_params_effective(1000, 0.15)  # -> 150
compute_params_effective(1000, 0.99)  # -> 990
```

## 範例輸出

### manifest.json

```json
{
  "artifact_version": "v1",
  "bars": 20000,
  "config_hash": "f9e8d7c6b5a4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8",
  "created_at": "2025-12-18T13:52:21.123456Z",
  "dataset_id": "synthetic_20k",
  "dirty_repo": false,
  "git_sha": "a1b2c3d4e5f6",
  "param_subsample_rate": 0.1,
  "params_effective": 100,
  "params_total": 1000,
  "run_id": "20251218T135221Z-a1b2c3d4",
  "season": "2025Q4"
}
```

## 測試要求

所有測試必須驗證：

1. JSON 序列化/反序列化正確性
2. Run ID 格式穩定性
3. Config hash 一致性
4. params_effective 計算規則一致性

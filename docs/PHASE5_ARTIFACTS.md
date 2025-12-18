# Phase 5 B1: Artifact System (統一留證)

## 概述

Artifact System 提供統一的輸出工廠，確保任何 run 都輸出一致結構，且 `param_subsample_rate` 強制揭露。

## 目錄結構契約

所有 run 的輸出遵循固定目錄結構：

```
outputs/
  seasons/{season}/runs/{run_id}/
    manifest.json
    config_snapshot.json
    metrics.json
    winners.json
    README.md
    logs.txt
```

### 路徑管理

路徑管理由 `core/paths.py` 集中處理：

- `get_run_dir(outputs_root, season, run_id)`: 取得 run 目錄路徑
- `ensure_run_dir(outputs_root, season, run_id)`: 確保目錄存在並返回路徑

**重要**: 所有輸出路徑只允許走 `core/paths.py`，不可分散在各處自己拼 path。

## Artifact 檔案定義

### 1. manifest.json

包含完整的 `AuditSchema` 欄位。

**必填欄位**:
- `run_id`: 執行 ID
- `created_at`: ISO8601 時間戳記（UTC，Z 結尾）
- `git_sha`: Git SHA（至少 12 chars）
- `dirty_repo`: 是否有未提交變更
- **`param_subsample_rate`**: 參數子採樣率（一級公民）
- `config_hash`: 配置雜湊值
- `season`: 季節識別碼
- `dataset_id`: 資料集識別碼
- `bars`: Bar 數量
- `params_total`: 總參數數（子採樣前）
- `params_effective`: 有效參數數（子採樣後）
- `artifact_version`: Artifact 版本號

**範例**:
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

### 2. config_snapshot.json

原始輸入 config（或 normalize 後），用來復現。

**內容**: 完整的配置字典，JSON 序列化（sorted keys）

**範例**:
```json
{
  "commission": 0.0,
  "n_bars": 20000,
  "n_params": 1000,
  "order_qty": 1,
  "slip": 0.0,
  "sort_params": true
}
```

### 3. metrics.json

效能指標。

**必填欄位**:
- 必須包含 `param_subsample_rate` 的可見性（一級公民）

**選填欄位**:
- `runtime_s`: 執行時間（秒）
- `throughput`: 吞吐量
- 其他自訂指標

**範例**:
```json
{
  "param_subsample_rate": 0.1,
  "runtime_s": 12.345,
  "throughput": 27777777.78
}
```

### 4. winners.json

Top-K 結果（v2 schema，自動升級）。

**v2 Schema 結構**:
```json
{
  "schema": "v2",
  "stage_name": "stage1_topk",
  "generated_at": "2025-12-18T00:00:00Z",
  "topk": [
    {
      "candidate_id": "donchian_atr:123",
      "strategy_id": "donchian_atr",
      "symbol": "CME.MNQ",
      "timeframe": "60m",
      "params": {"LE": 8, "LX": 4, "Z": -0.4},
      "score": 1.234,
      "metrics": {
        "net_profit": 100.0,
        "max_dd": -10.0,
        "trades": 10,
        "param_id": 123
      },
      "source": {
        "param_id": 123,
        "run_id": "stage1_topk-20251218T000000Z-12345678",
        "stage_name": "stage1_topk"
      }
    }
  ],
  "notes": {
    "schema": "v2",
    "candidate_id_mode": "strategy_id:param_id"
  }
}
```

**必填欄位**:
- `schema`: "v2"（頂層）
- `stage_name`: Stage 識別碼
- `generated_at`: ISO8601 時間戳記（UTC，Z 結尾）
- `topk`: WinnerItemV2 列表
- `notes.schema`: "v2"

**WinnerItemV2 必填欄位**:
- `candidate_id`: 穩定識別碼（格式：`{strategy_id}:{param_id}` 暫時，未來升級為 `{strategy_id}:{params_hash[:12]}`）
- `strategy_id`: 策略識別碼
- `symbol`: 商品識別碼（"UNKNOWN" 如果不可用）
- `timeframe`: 時間框架（"UNKNOWN" 如果不可用）
- `params`: 參數字典（可能為空 `{}` 如果參數不可用）
- `score`: 排名分數（finalscore, net_profit, 或 proxy_value）
- `metrics`: 效能指標（必須包含 legacy 欄位：net_profit, max_dd, trades, param_id）
- `source`: 來源元數據（param_id, run_id, stage_name）

**向後兼容**:
- Legacy winners（v1）會自動升級到 v2
- Legacy 欄位（net_profit, max_dd, trades, param_id）保留在 `metrics` 中
- Governance 系統同時支持 v2 和 legacy 格式

**candidate_id 暫時模式**:
- 當前使用 `{strategy_id}:{param_id}`（可追溯但非最優）
- 未來升級到 `{strategy_id}:{params_hash[:12]}`（當 params 完整可用時）
- 升級路線在 `notes.candidate_id_mode` 中記錄

### 5. README.md

人類可讀的摘要（Markdown）。

**必須顯示**:
- `run_id`
- `git_sha`
- **`param_subsample_rate`**（必須突出顯示）
- `season`
- `dataset_id`
- `bars`
- `params_total`
- `params_effective`
- `config_hash`

**範例**:
```markdown
# FishBroWFS_V2 Run

- run_id: 20251218T135221Z-a1b2c3d4
- git_sha: a1b2c3d4e5f6
- param_subsample_rate: 0.1
- season: 2025Q4
- dataset_id: synthetic_20k
- bars: 20000
- params_total: 1000
- params_effective: 100
- config_hash: f9e8d7c6b5a4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8
```

### 6. logs.txt

執行日誌（純文字）。

初始為空檔案，後續可追加日誌。

## 使用方式

### 基本使用

```python
from pathlib import Path
from FishBroWFS_V2.core.artifacts import write_run_artifacts
from FishBroWFS_V2.core.paths import ensure_run_dir
from FishBroWFS_V2.core.audit_schema import AuditSchema, compute_params_effective
from FishBroWFS_V2.core.run_id import make_run_id
from FishBroWFS_V2.core.config_hash import stable_config_hash
from datetime import datetime, timezone

# 準備資料
config = {"n_bars": 20000, "n_params": 1000}
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
)

# 建立 run 目錄
outputs_root = Path("outputs")
run_dir = ensure_run_dir(outputs_root, audit.season, audit.run_id)

# 寫入 artifacts
write_run_artifacts(
    run_dir=run_dir,
    manifest=audit.to_dict(),
    config_snapshot=config,
    metrics={
        "param_subsample_rate": param_subsample_rate,
        "runtime_s": 12.345,
    },
)
```

## 契約（Contract）

### 結構契約

1. **固定目錄結構**: 所有 run 必須遵循 `outputs/seasons/{season}/runs/{run_id}/` 結構
2. **固定檔案名稱**: 使用標準檔案名稱（manifest.json, config_snapshot.json, etc.）
3. **JSON 格式**: 所有 JSON 檔案使用 `sort_keys=True` + 固定 `separators=(",", ":")` + 2 空格縮排
4. **README 格式**: Markdown 格式，UTF-8 編碼

### 內容契約

1. **manifest.json 必須包含 `param_subsample_rate`**: 這是**一級公民**，不可隱藏
2. **metrics.json 必須包含 `param_subsample_rate`**: 確保可見性
3. **README.md 必須顯示 `param_subsample_rate`**: 人類可讀格式
4. **config_snapshot.json 必須可復現**: 使用相同 config 應能復現結果
5. **winners.json 結構固定**: 自動升級到 v2 schema，即使為空也必須是 v2 格式

### 測試要求

所有測試必須驗證：

1. 目錄結構正確性
2. 檔案存在性
3. JSON 格式正確性（sorted keys）
4. `param_subsample_rate` 在所有相關檔案中的存在性
5. README.md 中 `param_subsample_rate` 的可見性

## UI 契約

**重要**: UI 只能讀 artifact，不碰 engine。

- UI 從 `manifest.json` 讀取審計資訊
- UI 從 `metrics.json` 讀取效能指標
- UI 從 `winners.json` 讀取結果
- UI **不得**直接讀取或修改 engine/kernel 相關檔案

此契約確保 UI 與核心邏輯解耦。

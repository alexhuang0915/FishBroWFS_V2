# Phase 5 B4: WFS Governance（決策制度化 + 可審計）

## 目標

將決策制度化，確保每個決策都可追溯、可審計。Governance 系統讀取 artifacts（manifest/metrics/winners/config_snapshot），應用規則，產出治理決策（KEEP/FREEZE/DROP）。

## 核心原則

### 全域硬規則（Non-Negotiable）

1. **Governance 只能讀 artifacts**：不准直接跑 engine
2. **輸出必須是 artifacts**：機器可讀 + 人可審
3. **每個決策都必須可追溯**：能指出是「哪個 run_id / 哪個 stage / 哪些 metrics」導致決策
4. **Subsample 一級公民**：任何決策報告必須包含 subsample（至少：stage_planned_subsample、final subsample、params_effective）
5. **MVP 最小可用治理**：規則鎖死、測試鎖死；不做 UI、不做 fancy ranking

## 交付物

### A) Governance Schema（決策輸出格式 SSOT）

統一輸出 `governance.json`，包含：
- 決策（KEEP/FREEZE/DROP）
- 理由（reasons）
- 證據鏈（evidence）

**Schema 定義**：
- `Decision`: Enum（KEEP/FREEZE/DROP）
- `EvidenceRef`: dataclass（run_id, stage_name, artifact_paths, key_metrics）
- `GovernanceItem`: dataclass（candidate_id, decision, reasons, evidence, created_at, git_sha）
- `GovernanceReport`: dataclass（items + metadata）

**candidate_id 格式**：
```
{strategy_id}:{params_hash[:12]}
```
例如：`donchian_atr:abc123def456`

⚠️ **易錯點**：candidate_id 必須可重現，不能使用 list index 或隨機值。

### B) Governance Evaluator（讀 artifacts → 產生決策）

**介面**：
```python
def evaluate_governance(
    *,
    stage0_dir: Path,
    stage1_dir: Path,
    stage2_dir: Path,
) -> GovernanceReport:
    ...
```

**輸入**：三個 stage 的 run_dir（包含 manifest/metrics/winners/config_snapshot）

**輸出**：`GovernanceReport`，每個候選參數組都有治理決策

### C) Governance Writer（寫 artifacts）

**輸出路徑**：
```
outputs/seasons/{season}/governance/{governance_id}/
  governance.json      # 機器可讀 SSOT
  README.md            # 人類可讀摘要
  evidence_index.json  # 證據索引（可選但推薦）
```

**README.md 必須包含**：
- KEEP/FREEZE/DROP 數量
- 每個 FREEZE 的理由（精簡）
- subsample/params_effective 重點

### D) Tests + Docs

- Schema 測試：驗證 JSON 序列化
- 規則測試：用假 artifacts fixture 驗證 R1/R2/R3
- Writer 測試：驗證輸出路徑和文件結構

## 治理對象

B4 MVP 先治理「候選參數組（candidate params）」，來源於：
- **Stage0 / Stage1 的 winners.json（topk list）**

⚠️ **重要**：Stage2（full confirm）是用來「驗證」候選，而不是產生候選。

## 規則（MVP - 鎖死）

### Rule R1 — Evidence completeness（證據完整性）

若候選在 Stage1 winners 出現，但：
- 找不到對應 Stage2 metrics（或 Stage2 未跑成功）
- → **DROP**（理由：unverified）

### Rule R2 — Confirm stability（確認一致性）

若候選在 Stage2 的關鍵指標相對於 Stage1 劣化超過閾值 → **DROP**

**閾值**：20% degradation

**指標優先級**：
1. `finalscore` 或 `net_over_mdd`
2. Fallback：`net_profit / max_dd`（如果兩者都存在）

**計算**：
```
degradation_ratio = (stage1_val - stage2_val) / abs(stage1_val)
if degradation_ratio > 0.20:
    DROP
```

### Rule R3 — Plateau hint（高原提示，MVP 簡化版）

若 Stage1 topk 裡同一候選附近（例如同商品同策略、參數相近）出現密集集中 → **FREEZE**

**MVP 版本**：
- 同一 `strategy_id` 出現 >= 3 次 → **FREEZE**
- 否則 → **KEEP**

⚠️ **注意**：Plateau 真正幾何判斷（距離/聚類）先別做，MVP 用「密度代理」即可。

## 檔案清單

### 新增檔案

1. **core/governance_schema.py**
   - `Decision`: Enum
   - `EvidenceRef`: dataclass
   - `GovernanceItem`: dataclass
   - `GovernanceReport`: dataclass

2. **core/artifact_reader.py**
   - `read_manifest(run_dir) -> dict`
   - `read_metrics(run_dir) -> dict`
   - `read_winners(run_dir) -> dict`
   - `read_config_snapshot(run_dir) -> dict`

3. **pipeline/governance_eval.py**
   - `evaluate_governance()`: 主函數
   - `apply_rule_r1()`: R1 規則
   - `apply_rule_r2()`: R2 規則
   - `apply_rule_r3()`: R3 規則
   - `normalize_candidate()`: 候選標準化
   - `generate_candidate_id()`: 生成穩定 candidate_id

4. **core/governance_writer.py**
   - `write_governance_artifacts()`: 寫入治理結果

5. **scripts/run_governance.py**
   - CLI 入口：讀取三個 stage run_dir，輸出 governance_dir path

6. **tests/test_governance_schema_contract.py**
   - Schema JSON 序列化測試

7. **tests/test_governance_eval_rules.py**
   - R1/R2/R3 規則測試（用假 artifacts）

8. **tests/test_governance_writer_contract.py**
   - Writer 輸出路徑和文件結構測試

9. **docs/PHASE5_GOVERNANCE_B4.md**
   - 本文檔

## governance.json Schema 範例

```json
{
  "items": [
    {
      "candidate_id": "donchian_atr:abc123def456",
      "decision": "KEEP",
      "reasons": [],
      "evidence": [
        {
          "run_id": "stage1-20251218T000000Z-12345678",
          "stage_name": "stage1_topk",
          "artifact_paths": [
            "manifest.json",
            "metrics.json",
            "winners.json",
            "config_snapshot.json"
          ],
          "key_metrics": {
            "param_id": 0,
            "net_profit": 100.0,
            "trades": 10,
            "max_dd": -10.0,
            "stage_planned_subsample": 0.1,
            "param_subsample_rate": 0.1,
            "params_effective": 100
          }
        }
      ],
      "created_at": "2025-12-18T00:00:00Z",
      "git_sha": "abc123def456"
    }
  ],
  "metadata": {
    "governance_id": "gov-20251218T000000Z-12345678",
    "season": "test_season",
    "created_at": "2025-12-18T00:00:00Z",
    "git_sha": "abc123def456",
    "stage0_run_id": "stage0-20251218T000000Z-12345678",
    "stage1_run_id": "stage1-20251218T000000Z-12345678",
    "stage2_run_id": "stage2-20251218T000000Z-12345678",
    "total_candidates": 1,
    "decisions": {
      "KEEP": 1,
      "FREEZE": 0,
      "DROP": 0
    }
  }
}
```

## 輸出路徑契約

**固定路徑結構**：
```
outputs/seasons/{season}/governance/{governance_id}/
```

**governance_id 格式**：
```
gov-{timestamp}-{token}
```
例如：`gov-20251218T000000Z-12345678`

## 測試設計

### Schema 測試
- `test_governance_report_json_serializable`: 驗證 JSON 序列化
- `test_evidence_ref_contains_subsample_fields`: 驗證 subsample 欄位

### 規則測試（用假 artifacts）
- `test_r1_drop_when_stage2_missing`: R1 測試
- `test_r2_drop_when_metric_degrades_over_threshold`: R2 測試
- `test_r3_freeze_when_density_over_threshold`: R3 測試
- `test_keep_when_all_rules_pass`: KEEP 測試

### Writer 測試
- `test_governance_writer_creates_expected_tree`: 驗證目錄結構
- `test_governance_json_contains_subsample_fields_in_evidence`: 驗證 subsample 欄位
- `test_readme_contains_freeze_reasons`: 驗證 README 內容

## 易錯點檢查清單

- ✅ 不使用 README 當資料來源（只用 JSON）
- ✅ candidate_id 穩定（strategy_id + params_hash）
- ✅ subsample 記進 evidence
- ✅ 規則測試鎖死
- ✅ Governance 不跑 engine（只讀 artifacts）

## Winners.json v2 支持

### v2 格式優先路徑

Governance evaluator 優先讀取 v2 格式的 winners.json：

1. **Fast Path（v2）**：
   - 直接讀取 `candidate_id`, `strategy_id`, `params`, `metrics`, `score`
   - 無需 fallback 邏輯
   - 更高效且更準確

2. **Legacy Path（向後兼容）**：
   - 如果 winners.json 是 legacy 格式，使用 fallback 邏輯
   - 從 `param_id` 重建 `candidate_id`（暫時模式）
   - 從 `metrics` 或 top-level 提取指標

### candidate_id 匹配

**v2 格式**：
- 使用 `candidate_id` 進行 Stage1/Stage2 匹配
- 格式：`{strategy_id}:{param_id}`（暫時）或 `{strategy_id}:{params_hash[:12]}`（未來）

**Legacy 格式**：
- 使用 `param_id` 進行匹配
- 從 `source.param_id` 或 `metrics.param_id` 提取

### 向後兼容保證

- Governance 同時支持 v2 和 legacy 格式
- Legacy 欄位（net_profit, max_dd, trades, param_id）保留在 v2 的 `metrics` 中
- 不會因為格式升級而導致舊資料無法處理

## 使用範例

### CLI 使用

```bash
python scripts/run_governance.py \
  --stage0-dir outputs/seasons/test_season/runs/stage0-123 \
  --stage1-dir outputs/seasons/test_season/runs/stage1-123 \
  --stage2-dir outputs/seasons/test_season/runs/stage2-123 \
  --outputs-root outputs \
  --season test_season
```

輸出：`outputs/seasons/test_season/governance/gov-20251218T000000Z-12345678`

### Python API 使用

```python
from pathlib import Path
from FishBroWFS_V2.pipeline.governance_eval import evaluate_governance
from FishBroWFS_V2.core.governance_writer import write_governance_artifacts

# 評估治理
report = evaluate_governance(
    stage0_dir=Path("outputs/seasons/test_season/runs/stage0-123"),
    stage1_dir=Path("outputs/seasons/test_season/runs/stage1-123"),
    stage2_dir=Path("outputs/seasons/test_season/runs/stage2-123"),
)

# 寫入 artifacts
governance_dir = Path("outputs/seasons/test_season/governance/gov-123")
write_governance_artifacts(governance_dir, report)
```

## 後續擴充

MVP 完成後，可考慮：
1. 幾何距離/聚類判斷（R3 進階版）
2. 更多規則（R4, R5, ...）
3. 策略 ID 自動提取（從 config_snapshot）
4. 參數完整重建（從 params_matrix）

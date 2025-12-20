# Phase 9: Research Governance Layer

## 概述

Research Governance Layer 提供標準化摘要、橫向比較和正式封存功能，讓每一次 Portfolio Run 的結果可以被系統化管理。

## 核心原則

1. **只讀不寫**：只讀取 artifacts，不重新計算交易
2. **不影響既有 pipeline**：不改 Phase 0-8 任一 contract
3. **標準化格式**：所有結果使用 CanonicalMetrics schema
4. **決策追蹤**：所有決策（KEEP/DROP/ARCHIVE）都有完整記錄

## 目錄結構

```
outputs/research/
├── canonical_results.json    # 所有 runs 的標準化指標
├── research_index.json       # 研究結果索引（含決策狀態）
└── decisions.log            # 決策記錄（JSONL 格式）
```

## 核心模組

### 1. metrics.py - Canonical Metrics Schema

定義標準化的研究結果格式：

```python
@dataclass(frozen=True)
class CanonicalMetrics:
    run_id: str
    portfolio_id: str
    portfolio_version: str
    net_profit: float
    max_drawdown: float
    profit_factor: float
    sharpe: float
    trades: int
    win_rate: float
    avg_trade: float
    score_net_mdd: float
    score_final: float
    bars: int
    start_date: str
    end_date: str
```

### 2. extract.py - Result Extractor

從 artifacts 提取標準化指標：

- 讀取 `manifest.json`、`metrics.json`、`winners.json`
- 聚合 topk 結果為標準化指標
- 如果缺少必要欄位，會 raise `ExtractionError`

### 3. registry.py - Result Registry

掃描 `outputs/` 目錄並建立研究索引：

- 掃描所有 `outputs/seasons/{season}/runs/{run_id}/`
- 提取每個 run 的標準化指標
- 建立 `research_index.json` 索引

### 4. decision.py - Research Decision

管理研究決策（KEEP/DROP/ARCHIVE）：

- 決策是 append-only，不可覆蓋歷史決策
- 每個決策包含 `note` 和 `decided_at` 時間戳
- 決策記錄在 `decisions.log`（JSONL 格式）

## 使用方式

### 生成 Research Artifacts

```bash
# 方法 1: 使用 Python 模組
PYTHONPATH=src python -m FishBroWFS_V2.research

# 方法 2: 使用腳本
PYTHONPATH=src python scripts/generate_research.py
```

### 記錄決策

```python
from FishBroWFS_V2.research.decision import record_decision
from pathlib import Path

research_dir = Path("outputs/research")
record_decision(
    research_dir,
    run_id="test-run-123",
    decision="KEEP",
    note="Good performance, low drawdown"
)
```

### 查詢決策

```python
from FishBroWFS_V2.research.decision import get_decision, list_decisions

# 查詢單一 run 的決策
decision = get_decision(research_dir, "test-run-123")

# 列出所有決策
all_decisions = list_decisions(research_dir)
```

## 檔案格式

### canonical_results.json

```json
{
  "results": [
    {
      "run_id": "...",
      "portfolio_id": "...",
      "net_profit": 100.0,
      "max_drawdown": 50.0,
      ...
    }
  ],
  "total_runs": 1
}
```

### research_index.json

```json
{
  "entries": [
    {
      "run_id": "...",
      "portfolio_id": "...",
      "score_final": 10.0,
      "decision": "UNDECIDED"
    }
  ],
  "total_runs": 1
}
```

### decisions.log (JSONL)

```json
{"run_id": "test-run-123", "decision": "KEEP", "note": "...", "decided_at": "2025-01-01T00:00:00Z"}
{"run_id": "test-run-456", "decision": "DROP", "note": "...", "decided_at": "2025-01-02T00:00:00Z"}
```

## 測試

```bash
# 運行所有 research 測試
PYTHONPATH=src pytest tests/test_research_*.py -v
```

## 注意事項

1. **只讀不寫**：research 層不修改任何既有 artifacts
2. **缺失欄位**：如果 artifacts 缺少必要欄位，會 raise `ExtractionError`
3. **決策不可覆蓋**：一旦設定決策，不可更改（append-only）
4. **聚合限制**：從 `winners.json` 的 topk 聚合，可能不包含所有交易


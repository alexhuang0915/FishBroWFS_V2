# Phase 4 Definition (Funnel v1)

## Scope (Only 3 Deliverables)

Phase 4 只做三件事：

1. **Cursor kernel 成為唯一主 simulate path**
   - `matcher_core.simulate()` 是唯一語義真理來源
   - 所有其他 kernel 必須對齊此參考實現

2. **Stage0 → Top-K → Stage2 pipeline 自動化（禁止人為介入）**
   - Stage0 執行 proxy ranking
   - Top-K 選擇基於 Stage0 proxy_value（deterministic）
   - Stage2 只跑 Top-K 參數（full backtest）

3. **Runner_grid/perf 變成可預期成本模型**
   - 性能定義明確且可預測
   - 成本模型可計算

## Non-goals (Forbidden List)

Phase 4 **不准碰**以下功能：

- **short side**：不處理空方
- **multi-symbol**：不處理多標的
- **portfolio**：不處理投資組合
- **GUI**：不處理圖形介面
- **ensemble proxy>3**：不處理超過 3 個的 ensemble proxy

## Single Source of Truth: matcher_core

**語義真理來源只有：`src/engine/matcher_core.py`**

- `matcher_core.simulate()` 是黃金參考實現
- 任何其他 kernel（如 `engine_jit`）必須與 `matcher_core` 對齊
- 所有語義變更必須先在 `matcher_core` 定義，再傳播到其他實現

## Stage0 vs Stage2 Contract

### Stage0 職責

- **只做 proxy ranking**：計算 proxy_value 用於參數排序
- **不算 PnL 指標**：禁止計算 Net/MDD/SQN/WinRate 等任何 PnL 相關指標
- 輸出：參數 ID 與對應的 proxy_value

### Stage2 職責

- **full backtest**：執行完整的策略回測（使用 matcher_core）
- **只跑 Top-K params**：僅對 Top-K 篩選後的參數執行
- 輸出：完整的回測結果（包含 PnL 指標）

### 契約邊界

- Stage0 不得依賴 Stage2 的結果
- Stage2 不得重複執行 Stage0 的計算
- 兩階段必須可獨立執行

## Top-K Rule (No Human In-the-loop)

### Top-K 規則

1. **只看 Stage0 proxy_value**：排序依據僅為 Stage0 輸出的 proxy_value
2. **tie-break deterministic**：當 proxy_value 相同時，使用 `param_id` 作為確定性排序鍵
3. **禁止人為介入**：Top-K 選擇必須完全自動化，不允許人工篩選或調整

### Deterministic 要求

- **同輸入跑兩次 Top-K 一樣**：相同輸入必須產生相同的 Top-K 結果
- 排序規則：先按 `proxy_value` 降序，再按 `param_id` 升序（作為 tie-break）

### 實現要求

- Top-K 選擇邏輯必須可重現
- 不允許隨機性或非確定性行為
- 所有排序規則必須明確文檔化

## Performance Definition (Predictable Cost Model)

### 成本模型定義

Runner_grid/perf 必須提供可預期的成本模型：

1. **Stage0 成本**：可根據參數數量、bar 數量預測執行時間
2. **Top-K 成本**：排序與選擇的計算成本（通常可忽略）
3. **Stage2 成本**：可根據 Top-K 數量、bar 數量預測執行時間

### 可預期性要求

- 成本模型必須文檔化
- 實際執行時間應與預測模型一致（允許合理誤差）
- 性能瓶頸必須可識別與優化

## Exit Criteria (Gate to Phase 5)

Phase 4 完成標準（必須全部滿足才能進入 Phase 5）：

1. **Cursor kernel 主路徑**
   - `matcher_core.simulate()` 成為唯一主 simulate path
   - 所有其他 kernel 已對齊並驗證

2. **Pipeline 自動化**
   - Stage0 → Top-K → Stage2 pipeline 完全自動化
   - 無需人為介入即可執行完整流程

3. **Spearman 正相關穩定**
   - Stage0 proxy_value 與 Stage2 最終指標（如 Net PnL）的 Spearman 相關性穩定
   - 相關性必須為正且達到可接受閾值（具體閾值待定義）

### 驗收檢查清單

- [ ] `matcher_core.simulate()` 是唯一語義真理來源
- [ ] Stage0 只做 proxy ranking，不算 PnL
- [ ] Top-K 規則 deterministic（同輸入同輸出）
- [ ] Pipeline 完全自動化（無人工介入）
- [ ] Runner_grid/perf 成本模型可預期
- [ ] Spearman 相關性穩定且為正

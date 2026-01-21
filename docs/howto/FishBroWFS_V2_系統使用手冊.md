# FishBroWFS_V2 系統使用手冊（含技術規格）

> **版本**：V1.0
> **生成時間**：2026-01-09
> **適用對象**：系統操作員、開發者、審計人員
> **文件狀態**：正式發布

## 快速導航

- [🎯 系統全貌](#系統全貌) - 系統目標、架構、設計哲學
- [🔄 端到端流程](#端到端流程) - 從策略研究到實單部署的完整流程
- [🏗️ 各子系統角色](#各子系統在整體中的角色) - 各層級的職責邊界
- [⚖️ 重要技術裁定](#重要技術裁定) - 關鍵設計決策的「為什麼」
- [👨‍💼 使用者操作流程](#使用者操作流程operator-視角) - 操作員的日常工作
- [📦 系統產物](#系統會產出哪些東西artifacts) - 系統生成的文件和數據
- [🔍 可驗收性與可回溯性](#可驗收性與可回溯性) - 如何審計和重現結果
- [📋 技術規格細節](#附錄技術規格細節) - 詳細技術規格

## 目錄

1. [系統全貌](#系統全貌)
2. [端到端流程](#端到端流程)
3. [各子系統在整體中的角色](#各子系統在整體中的角色)
4. [重要技術裁定](#重要技術裁定)
5. [使用者操作流程（Operator 視角）](#使用者操作流程operator-視角)
6. [系統會產出哪些東西（Artifacts）](#系統會產出哪些東西artifacts)
7. [可驗收性與可回溯性](#可驗收性與可回溯性)
8. [附錄：技術規格細節](#附錄技術規格細節)

---

## 系統全貌

### 系統要解決什麼問題

FishBroWFS_V2 是一套**量化交易策略研究與部署系統**，旨在解決以下核心問題：

1. **策略研究流程標準化**：將策略開發從隨意腳本轉變為可重現、可審計的標準化流程
2. **研究到部署的無縫銜接**：建立從策略研究、驗證、組合構建到 MultiCharts 部署的完整管道
3. **可回溯性保證**：確保任何實單交易的結果都能追溯到原始研究決策和參數
4. **風險控制與治理**：在策略進入實單前實施多層次准入檢查和風險評估

### 為什麼要分 Python / Portfolio / MultiCharts

系統採用**三層架構**，每層有明確的職責邊界：

| 層級 | 技術棧 | 主要職責 | 為什麼分離 |
|------|--------|----------|------------|
| **Python 層** | Python + Numpy | 策略研究、特徵計算、回測引擎 | 研究靈活性、快速迭代、複雜計算 |
| **Portfolio 層** | Python + JSON/YAML | 組合構建、風險管理、准入治理 | 策略組合、風險分散、部署準備 |
| **MultiCharts 層** | PowerLanguage + EL | 實單執行、訂單管理、市場連線 | 交易所連線、低延遲執行、行業標準 |

這種分離確保：
- **職責單一**：每層只做最適合自己的工作
- **技術棧最佳化**：Python 適合研究，PowerLanguage 適合交易執行
- **風險隔離**：研究錯誤不會直接影響實單執行

### 系統設計的核心哲學

1. **Determinism First（確定性優先）**
   - 所有計算必須可重現
   - 使用內容哈希（content hash）確保一致性
   - 避免隨機性和非確定性操作

2. **Immutable Artifacts（不可變產物）**
   - 所有中間產物一旦產生就不可修改
   - 使用哈希鏈（hash chain）建立信任鏈
   - 審計追蹤完整保留

3. **Explicit Over Implicit（顯式優於隱式）**
   - 所有配置必須明確聲明
   - 避免魔法數字和隱式假設
   - 參數邊界清晰定義

4. **Gate-Based Governance（基於門檻的治理）**
   - 多層次准入檢查（pre-flight policies）
   - 失敗快速（fail fast）原則
   - 風險在早期階段被攔截

---

## 端到端流程

### 策略怎麼產生

1. **策略定義**：
   - 在 `src/strategy/builtin/` 中定義策略函數
   - 使用 `StrategySpec` 註冊策略（ID、版本、參數模式、預設值）
   - 策略必須是**純函數**，只依賴輸入特徵和參數

2. **特徵計算**：
   - 特徵在 `src/indicators/` 中定義
   - 使用 Numba 加速計算
   - 特徵可來自 Data1（原始數據）或 Data2（衍生數據）

3. **研究執行**：
   - 透過 Supervisor 提交 `RUN_RESEARCH_V2` 任務
   - 任務參數：策略ID、時間框架、季節（season）、數據集
   - 系統自動計算特徵、執行策略、產生意圖（intents）

### 怎麼驗證

1. **回測驗證**：
   - WFS（Walk-Forward Simulation）引擎執行策略
   - 產生績效指標：淨利潤、最大回撤、交易次數等
   - 與基準（Buy & Hold）比較

2. **准入檢查（Admission Gates）**：
   - **重複檢查**：相同參數哈希的任務會被拒絕
   - **時間框架檢查**：只允許特定時間框架（15, 30, 60, 120, 240）
   - **季節格式檢查**：必須符合 YYYYQ# 格式（如 2026Q1）

3. **治理評估**：
   - 使用 `configs/portfolio/governance_params.json` 中的門檻
   - 檢查：夏普比率、最大回撤、交易次數等
   - 失敗的策略不會進入下一階段

### 怎麼被選進組合

1. **決策記錄**：
   - 研究結果寫入 `decisions.log`（僅追加，不可修改）
   - 每個決策包含：run_id、策略ID、參數、績效指標
   - **最後決策獲勝**：相同 run_id 的後續決策覆蓋先前決策

2. **組合構建**：
   - 提交 `BUILD_PORTFOLIO_V2` 任務
   - 系統讀取 `decisions.log`，應用符號白名單過濾
   - 根據治理規則選擇策略進入組合

3. **組合規格生成**：
   - 產生 `PortfolioSpec` 數據類
   - 寫入 `portfolio_spec.json`、`portfolio_manifest.json`、`README.md`
   - 組合ID基於輸入哈希確定性生成

### 怎麼被「凍結成可部署狀態」

1. **季節凍結**：
   - 提交 `RUN_FREEZE_V2` 任務
   - 將組合規格「凍結」為不可變的季節快照
   - 產生 `season_manifest.json` 包含所有元數據

2. **編譯部署包**：
   - 提交 `RUN_COMPILE_V2` 任務
   - 將策略轉換為 PowerLanguage 代碼
   - 遵守 **non-IOG** 和 **no Set*** 約束

3. **Master Wrapper 生成**：
   - Phase 4-C Titanium Master 生成器
   - 將多個策略合併為單一 Master 文件
   - 使用 switch-case 邏輯根據 `i_Strategy_ID` 選擇策略

### 最後怎麼進 MultiCharts 做實單

1. **手動部署**：
   - 將生成的 `Titanium_Master_{Quarter}_Part{X}.txt` 複製到 MultiCharts
   - 按照 `Deployment_Guide.html` 配置策略參數
   - 在 Portfolio Trader 中設置組合權重

2. **執行監控**：
   - MultiCharts 負責實際訂單執行
   - 系統不參與實時決策（僅提供策略邏輯）
   - 實單結果可與研究預期對比驗證

---

## 各子系統在整體中的角色

### Research / WFS 引擎

**負責什麼**：
- 策略回測和績效評估
- 特徵計算和數據準備
- 產生交易意圖（OrderIntents）

**不負責什麼**：
- 實單訂單執行
- 風險管理和資金分配
- 部署代碼生成

**產出給下一層**：
- `decisions.log`（決策記錄）
- `canonical_results.json`（標準化結果）
- 績效指標和統計數據

### Portfolio Admission / Governance

**負責什麼**：
- 策略准入檢查和風險評估
- 組合構建和權重分配
- 治理規則執行

**不負責什麼**：
- 策略邏輯實現
- 特徵計算
- 部署代碼轉換

**產出給下一層**：
- `PortfolioSpec`（組合規格）
- `portfolio_manifest.json`（組合清單）
- 准入/拒絕決策記錄

### Deployment / 轉換層

**負責什麼**：
- 將 Python 策略轉換為 PowerLanguage 代碼
- 生成 Master Wrapper 文件
- 確保語法兼容性和約束遵守

**不負責什麼**：
- 策略研究
- 風險評估
- 實單執行

**產出給下一層**：
- `Titanium_Master_*.txt`（Master 策略文件）
- `Deployment_Guide.html`（部署指南）
- 驗證報告和錯誤日誌

### MultiCharts / Portfolio Trader

**負責什麼**：
- 實單訂單執行和市場連線
- 實時風險監控
- 組合再平衡

**不負責什麼**：
- 策略研究
- 歷史回測
- 代碼生成

**產出給系統**：
- 實單交易記錄
- 實際績效數據
- 用於後續驗證的市場數據

---

## 重要技術裁定

### 為什麼要 non-IOG

**IOG（IntraBar Order Generation）** 允許在 K 線內生成訂單，但會導致：
1. **回測與實單不一致**：回測難以精確模擬 IOG 行為
2. **增加複雜性**：需要 tick 級數據和精確時間戳
3. **重現性問題**：微小時間差異可能導致不同結果

**系統裁定**：僅支持 **Bar Close** 語義（IOG=False）
- 所有訂單在 K 線結束時評估
- 確保回測與實單一致性
- 簡化系統複雜度

### 為什麼不用 Set*

**Set* 語法**（SetStopLoss, SetProfitTarget, SetBreakEven 等）問題：
1. **隱式狀態管理**：Set* 在後台維護隱式狀態，難以追蹤
2. **Ghost Trades**：可能產生未預期的「幽靈交易」
3. **審計困難**：訂單邏輯分散在多個 Set* 調用中

**系統裁定**：**絕對禁止 Set* 語法**（ADR-4C-STOP-001）
- 所有訂單必須使用顯式語法：`Buy/Sell at Market/Stop`
- 確保每筆交易邏輯明確可見
- 避免隱式狀態和幽靈交易

### 為什麼是人工部署而不是全自動

**技術限制**：
1. **MultiCharts API 限制**：沒有可靠的編程接口自動部署策略
2. **交易所連線安全**：自動部署可能觸發風控機制
3. **驗證需求**：人工檢查可防止錯誤部署

**操作哲學**：
1. **Human-in-the-loop**：關鍵決策保留人工確認
2. **部署即儀式**：強制操作者審查部署內容
3. **責任明確**：部署者對實單結果負最終責任

### 為什麼 MultiCharts 不被視為決策引擎

**角色定位**：
1. **執行引擎**：MultiCharts 負責訂單執行，不負責策略生成
2. **被動角色**：僅執行預先定義的策略邏輯
3. **無狀態轉換**：不修改策略邏輯，僅轉發信號

**系統邊界**：
- 決策在 Python 層完成
- MultiCharts 是「啞執行器」
- 確保系統核心邏輯集中在單一位置

---

## 使用者操作流程（Operator 視角）

### 平常要跑哪些步驟

**典型工作流**：

```bash
# 1. 啟動系統
make up

# 2. 提交研究任務
python -m src.control.supervisor.cli submit \
  --job-type RUN_RESEARCH_V2 \
  --params-json '{"strategy_id": "sma_cross", "timeframe": 60, "season": "2026Q1"}'

# 3. 監控任務狀態
python -m src.control.supervisor.cli list --state RUNNING

# 4. 構建組合
python -m src.control.supervisor.cli submit \
  --job-type BUILD_PORTFOLIO_V2 \
  --params-json '{"season": "2026Q1", "symbols_allowlist": ["CME.MNQ"]}'

# 5. 凍結季節
python -m src.control.supervisor.cli submit \
  --job-type RUN_FREEZE_V2 \
  --params-json '{"season": "2026Q1"}'

# 6. 生成部署包
python -m src.control.supervisor.cli submit \
  --job-type RUN_COMPILE_V2 \
  --params-json '{"season": "2026Q1"}'
```

### 什麼時候要看輸出

**關鍵檢查點**：

1. **任務提交後**：檢查是否被准入控制器拒絕
2. **研究完成後**：查看 `outputs/seasons/{season}/research/` 中的結果
3. **組合構建後**：審查 `portfolio_manifest.json` 中的策略選擇
4. **部署生成後**：驗證 `Titanium_Master_*.txt` 語法正確性

### 哪些地方是人工決策

1. **策略選擇**：決定哪些策略進入研究流程
2. **參數範圍**：設定策略參數的搜索空間
3. **治理門檻**：調整准入標準（夏普比率、最大回撤等）
4. **組合權重**：決定策略在組合中的分配
5. **部署時機**：選擇何時將策略部署到實單

### 哪些地方不能亂改

1. **哈希計算邏輯**：修改會破壞所有現有產物的可追溯性
2. **決策日誌格式**：`decisions.log` 格式必須保持向後兼容
3. **准入檢查規則**：隨意放寬可能導致風險策略進入實單
4. **non-IOG 約束**：違反會導致回測與實單不一致
5. **Set* 語法禁令**：違反會引入幽靈交易風險

---

## 系統會產出哪些東西（Artifacts）

### 檔案/資料類型

| 產物類型 | 位置 | 用途 | 使用者 |
|----------|------|------|--------|
| **決策日誌** | `outputs/seasons/{season}/decisions.log` | 記錄所有研究決策 | 組合構建器 |
| **標準化結果** | `outputs/seasons/{season}/research/canonical_results.json` | 標準化績效指標 | 報告生成、分析 |
| **組合規格** | `outputs/seasons/{season}/portfolio/{portfolio_id}/portfolio_spec.json` | 定義組合內容 | 部署系統 |
| **組合清單** | `outputs/seasons/{season}/portfolio/{portfolio_id}/portfolio_manifest.json` | 組合元數據和哈希 | 審計、驗證 |
| **季節清單** | `outputs/seasons/{season}/season_manifest.json` | 凍結季節狀態 | 部署準備 |
| **Master 策略** | `outputs/deployments/{deploy_id}/Titanium_Master_*.txt` | MultiCharts 可執行代碼 | 交易員 |
| **部署指南** | `outputs/deployments/{deploy_id}/Deployment_Guide.html` | 部署說明和參數表 | 交易員 |
| **任務證據** | `outputs/_dp_evidence/` | 任務執行日誌和證據 | 開發者、審計員 |

### 產物生命週期

1. **臨時產物**：任務執行過程中的中間文件，可清理
2. **持久產物**：`decisions.log`、組合規格等，必須保留
3. **部署產物**：Master 策略文件，用於實單執行
4. **審計產物**：證據日誌，用於問題排查和合規

### 產物驗證

每個產物都包含：
- **內容哈希**：確保數據完整性
- **時間戳**：記錄生成時間
- **輸入引用**：指向生成該產物的輸入
- **版本信息**：標識格式版本

---

## 可驗收性與可回溯性

### 如何確保不是黑盒

1. **完整審計追蹤**：
   - 每個任務都有完整的證據鏈
   - 所有輸入和輸出都被記錄
   - 哈希鏈確保數據完整性

2. **決策透明**：
   - `decisions.log` 記錄每個決策的完整上下文
   - 准入檢查結果詳細記錄
   - 治理規則明確公開

3. **代碼可審查**：
   - 所有策略邏輯在 Python 中實現
   - 無隱藏邏輯或黑魔法
   - 測試覆蓋關鍵路徑

### 事後如何知道某一季實單是怎麼來的

**追溯路徑**：

```
實單交易記錄
    ↓
MultiCharts 策略ID (i_Strategy_ID)
    ↓
Titanium_Master_{Quarter}_Part{X}.txt
    ↓
部署ID (deploy_id) 和季節 (season)
    ↓
outputs/seasons/{season}/season_manifest.json
    ↓
portfolio_id 和組合規格
    ↓
decisions.log 中的原始研究決策
    ↓
研究任務參數和輸入數據
    ↓
原始策略代碼和特徵定義
```

**具體步驟**：
1. 從實單交易記錄中提取 `i_Strategy_ID` 和 `i_Lots`
2. 在對應季節的部署目錄中找到 Master 文件
3. 從 `season_manifest.json` 獲取 `portfolio_id`
4. 在組合目錄中查看 `portfolio_manifest.json` 了解組合構成
5. 從 `decisions.log` 中找到對應 run_id 的研究決策
6. 查看研究任務的參數和輸入數據哈希
7. 最終追溯到原始策略代碼版本

### 為什麼結果可以被重建

**關鍵機制**：

1. **確定性計算**：
   - 所有計算基於確定性算法
   - 無隨機種子或非確定性操作
   - 相同輸入必然產生相同輸出

2. **內容尋址存儲**：
   - 使用 SHA256 哈希標識所有產物
   - 哈希鏈確保數據完整性
   - 任何修改都會破壞哈希鏈

3. **不可變記錄**：
   - `decisions.log` 僅追加，不可修改
   - 所有產物一旦寫入就不可變更
   - 時間戳和簽名防止篡改

4. **完整依賴記錄**：
   - 每個產物都記錄其輸入依賴
   - 包括：數據版本、代碼提交、配置哈希
   - 確保所有必要元素都可重現

**重建流程**：
```bash
# 1. 恢復特定提交的代碼
git checkout <commit_hash>

# 2. 恢復對應版本的數據
# （數據版本由 dataset_id 和 config_hash 標識）

# 3. 使用相同參數重新提交研究任務
python -m src.control.supervisor.cli submit \
  --job-type RUN_RESEARCH_V2 \
  --params-json '{"strategy_id": "...", "timeframe": ..., "season": "..."}'

# 4. 驗證結果與原始記錄一致
# （比較 decisions.log 條目和績效指標）
```

---

## 附錄：技術規格細節

### 任務類型（Job Types）

| 任務類型 | 用途 | 關鍵參數 |
|----------|------|----------|
| `RUN_RESEARCH_V2` | 策略研究 | `strategy_id`, `timeframe`, `season`, `dataset_id` |
| `RUN_PLATEAU_V2` | 參數優化 | `strategy_id`, `timeframe`, `season`, `param_grid` |
| `RUN_FREEZE_V2` | 季節凍結 | `season` |
| `RUN_COMPILE_V2` | 編譯部署包 | `season` |
| `BUILD_PORTFOLIO_V2` | 構建組合 | `season`, `symbols_allowlist` |
| `GENERATE_REPORTS` | 生成報告 | `outputs_root`, `season`, `strict` |

### 數據結構

**StrategySpec**：
```python
@dataclass
class StrategySpec:
    strategy_id: str
    version: str
    param_schema: dict  # JSON Schema
    defaults: dict      # 默認參數值
    fn: Callable        # 策略函數
```

**PortfolioSpec**：
```python
@dataclass
class PortfolioSpec:
    portfolio_id: str
    version: str
    legs: List[PortfolioLeg]
    # ... 其他字段
```

**JobSpec**：
```python
@dataclass
class JobSpec:
    job_type: str      # 任務類型
    params: dict       # 任務參數
    metadata: dict     # 元數據（可選）
```

### 文件系統布局

```
outputs/
├── _dp_evidence/          # 任務證據和日誌
├── jobs/                  # 任務產物（按 job_id 組織）
├── seasons/               # 季節數據
│   ├── 2026Q1/
│   │   ├── decisions.log          # 決策日誌
│   │   ├── season_manifest.json   # 季節清單
│   │   ├── research/              # 研究結果
│   │   └── portfolio/             # 組合規格
│   └── ...
├── deployments/           # 部署包
│   └── {deploy_id}/
│       ├── Titanium_Master_2026Q1_Part1.txt
│       ├── Deployment_Guide.html
│       └── ...
└── jobs_v2.db            # 任務數據庫（SQLite）
```

### 哈希計算規則

1. **參數哈希**：
   ```python
   def stable_params_hash(params: dict) -> str:
       # 1. 規範化 JSON（排序鍵、固定分隔符）
       # 2. 計算 SHA256
       # 3. 返回十六進制字符串
   ```

2. **內容哈希**：
   ```python
   def compute_sha256(data: bytes) -> str:
       # 計算原始字節的 SHA256
   ```

3. **組合ID生成**：
   ```python
   def generate_portfolio_id(season: str, decisions_hash: str, symbols: list) -> str:
       # 基於輸入的確定性哈希
   ```

### 准入檢查（Pre-flight Policies）

1. **重複檢查**：防止相同參數的任務重複執行
2. **時間框架檢查**：只允許預定義的時間框架
3. **季節格式檢查**：確保季節格式正確
4. **資源限制檢查**：防止系統過載
5. **依賴檢查**：確保所需數據和特徵可用

### 治理規則（Governance Rules）

規則定義在 `configs/portfolio/governance_params.json`：
```json
{
  "min_sharpe_ratio": 0.5,
  "max_drawdown_pct": 20.0,
  "min_trades": 10,
  "max_position_size": 100,
  "correlation_threshold": 0.7
}
```

### 錯誤處理和恢復

1. **任務失敗**：
   - 狀態標記為 `FAILED`
   - 錯誤信息記錄到數據庫
   - 證據保存到 `_dp_evidence/`

2. **系統中斷**：
   - 心跳機制檢測僵屍任務
   - 超時任務自動標記為 `ORPHANED`
   - 可手動重試或清理

3. **數據損壞**：
   - 哈希驗證檢測數據完整性
   - 損壞數據觸發重新計算
   - 備份機制防止數據丟失

### 性能考量

1. **內存管理**：
   - 特徵數據使用內存映射文件
   - 分批處理大型數據集
   - 及時釋放不再需要的數據

2. **計算優化**：
   - 使用 Numba 加速數值計算
   - 並行處理獨立任務
   - 緩存常用特徵計算結果

3. **IO 優化**：
   - 原子寫入防止部分寫入
   - 批量讀寫減少磁盤操作
   - 使用二進制格式存儲大型數組

---

## 總結

FishBroWFS_V2 是一套**嚴謹、可審計、可重現**的量化交易策略研究與部署系統。它通過：

1. **標準化流程**將研究從隨意腳本轉變為工業級管道
2. **多層次治理**確保只有經過驗證的策略進入實單
3. **完整追溯**使每個實單交易都能追溯到原始研究決策
4. **確定性計算**保證結果可重現和驗證

系統的設計哲學是**信任但驗證**（Trust but Verify）：
- 信任自動化流程的效率
- 但通過哈希鏈、審計追蹤和人工檢查進行驗證

這套系統不僅是工具，更是**可理解的歷史**——它記錄了每個決策的「為什麼」和「如何」，確保即使在多年後，團隊仍能理解當初的設計選擇和結果來源。

**最後提醒**：系統的成功依賴於操作者的紀律。遵守流程、仔細檢查、保留記錄——這些人工實踐與自動化工具同等重要。
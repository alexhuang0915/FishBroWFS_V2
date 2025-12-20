# Strategy Contract V1

## 概述

Strategy Contract 定義策略系統的核心規則和約束，確保策略的可預測性、可測試性和可重現性。

## 硬規則（不可違反）

### 1. 輸入約束

Strategy 只能接收以下輸入：

- **bars/features arrays**: 價格資料和技術指標（numpy arrays）
- **params**: 策略參數（dict，key-value pairs）
- **context**: 執行上下文（dict，包含 bar_index、order_qty 等）

**禁止**：
- ❌ 讀取檔案（file I/O）
- ❌ 修改輸入資料（immutable inputs）
- ❌ 依賴 system time（datetime.now()、time.time() 等）
- ❌ 直接呼叫 engine fill（策略不負責執行，只產生意圖）

### 2. 輸出約束

Strategy 只能輸出：

- **OrderIntent[]**: 訂單意圖列表（遵循 `core/order_intent` schema）

**禁止**：
- ❌ 直接產生 Fill（由 Engine 負責）
- ❌ 直接計算 PnL（由 Engine 負責）
- ❌ 修改外部狀態

### 3. Deterministic（確定性）

**核心原則**：相同輸入必須產生相同輸出

- 策略函數必須是純函數（pure function）
- 不允許隨機數（除非作為參數傳入）
- 不允許依賴外部狀態
- 不允許依賴執行順序

### 4. 策略元資料要求

所有策略都必須提供：

- **strategy_id**: 策略唯一識別碼（string）
- **version**: 策略版本號（string，如 "v1"）
- **param_schema**: 參數結構定義（dict，jsonschema-like）
- **defaults**: 參數預設值（dict，key-value pairs）

## OrderIntent Schema

策略輸出的 OrderIntent 必須符合以下結構：

```python
@dataclass(frozen=True)
class OrderIntent:
    order_id: int          # 訂單 ID（確定性排序）
    created_bar: int       # 建立時 bar index
    role: OrderRole        # ENTRY 或 EXIT
    kind: OrderKind        # STOP 或 LIMIT
    side: Side             # BUY 或 SELL
    price: float           # 訂單價格
    qty: int = 1          # 數量（預設 1）
```

## 策略函數簽名

```python
StrategyFn = Callable[
    [Mapping[str, Any], Mapping[str, float]],  # (context/features, params)
    Mapping[str, Any]                          # {"intents": [...], "debug": {...}}
]
```

## 驗證規則

1. **參數驗證**：
   - 缺少參數時使用 defaults
   - Extra key 允許但需記錄（不拋錯）
   - 參數類型必須符合 param_schema

2. **輸出驗證**：
   - intents 必須是 OrderIntent 列表
   - 每個 OrderIntent 必須符合 schema
   - order_id 必須是確定性生成

## 測試要求

所有策略必須通過：

1. **Purity Test**: 相同輸入重複執行，輸出必須一致
2. **Schema Test**: 輸出 intents 必須符合 OrderIntent schema
3. **Deterministic Test**: 不依賴執行順序或外部狀態

## 違反後果

違反 Strategy Contract 的策略將被標記為 **INVALID**，並在以下情況被拒絕：

- 讀取檔案
- 修改輸入資料
- 依賴 system time
- 非確定性行為
- 輸出不符合 schema

## 範例

### ✅ 正確的策略

```python
def sma_cross_strategy(context: dict, params: dict) -> dict:
    """SMA Cross Strategy - 純函數，確定性"""
    # 只使用輸入的 features 和 params
    sma_fast = context["features"]["sma_fast"]
    sma_slow = context["features"]["sma_slow"]
    bar_index = context["bar_index"]
    
    # 確定性邏輯
    if sma_fast[bar_index] > sma_slow[bar_index]:
        intent = OrderIntent(
            order_id=generate_order_id(bar_index, ...),
            created_bar=bar_index,
            role=OrderRole.ENTRY,
            kind=OrderKind.STOP,
            side=Side.BUY,
            price=sma_fast[bar_index],
        )
        return {"intents": [intent], "debug": {}}
    return {"intents": [], "debug": {}}
```

### ❌ 錯誤的策略

```python
def bad_strategy(context: dict, params: dict) -> dict:
    # ❌ 讀取檔案
    with open("config.json") as f:
        config = json.load(f)
    
    # ❌ 依賴 system time
    if datetime.now().hour > 15:
        return {"intents": [], "debug": {}}
    
    # ❌ 使用隨機數
    if random.random() > 0.5:
        return {"intents": [], "debug": {}}
    
    # ❌ 修改輸入
    context["modified"] = True
    
    return {"intents": [], "debug": {}}
```

## 版本歷史

- **V1** (2025-12-19): 初始版本，定義核心規則和約束

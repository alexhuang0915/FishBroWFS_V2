# MNQ / MXF 合約規格來源

## 更新日期
2025-12-23 (Hotfix: 修正為交易所 maintenance 等級保守值)

## CME.MNQ (Micro E-mini Nasdaq-100)

### 基本規格
- **交易所**: CME (芝加哥商業交易所)
- **合約代號**: MNQ
- **合約乘數**: 2.0 USD (每指數點 2 美元)
- **最小跳動點**: 0.25 指數點 = 0.50 USD
- **Tick Value**: 0.5 USD
- **Margin Basis**: exchange_maintenance (交易所 maintenance 等級)

### 保證金要求 (Portfolio 風控用)
- **維持保證金**: 3,500 USD (交易所 maintenance 等級保守固定值)
- **初始保證金**: 4,000 USD (高於 maintenance 的保守值)

### 來源參考
- CME 交易所官方 maintenance margin 參考
- Portfolio OS 使用交易所 maintenance 等級，不使用券商 day margin
- 保守值選擇: 確保 Portfolio 不會低估 MNQ 的帳戶風險

### 計算說明
```
每口合約價值 = 指數點位 × 2.0 USD
以指數 15,000 點計算:
  合約價值 = 15,000 × 2 = 30,000 USD
  維持保證金率 ≈ 11.7%
  初始保證金率 ≈ 13.3%
```

## TWF.MXF (台股期貨 - 小型台指期 MTX)

### 基本規格
- **交易所**: 台灣期貨交易所 (TAIFEX)
- **合約代號**: MXF (MTX) - 小型台指期貨
- **合約乘數**: 50 TWD (每指數點 50 新台幣)
- **最小跳動點**: 1 指數點 = 50 TWD
- **Margin Basis**: conservative_over_exchange (高於交易所官方公告)

### 保證金要求 (保守值)
- **維持保證金**: 80,000 TWD (高於 TAIFEX 官方 64,750 TWD)
- **初始保證金**: 88,000 TWD (高於 TAIFEX 官方 84,500 TWD)

### 來源參考
- TAIFEX 官方公告 (2025年12月):
  - Initial: 84,500 TWD
  - Maintenance: 64,750 TWD
- Portfolio OS 使用高於官方公告的保守值
- 保守值選擇: 確保風險控管安全邊際

### 計算說明
```
每口合約價值 = 指數點位 × 50 TWD
以指數 18,000 點計算:
  合約價值 = 18,000 × 50 = 900,000 TWD
  維持保證金率 ≈ 8.9%
  初始保證金率 ≈ 9.8%
```

## 匯率設定
- **USD/TWD**: 32.0 (固定匯率)
- **TWD/TWD**: 1.0
- 匯率來源: 保守估計值，實際交易時應使用即時匯率

## Portfolio OS 保證金政策

### 不使用 Day Margin 的原因
Portfolio OS 負責的是**帳戶級風控與資金治理**，不是進場條件。因此：

1. **風險控管優先**: 使用交易所 maintenance 或更保守值
2. **避免低估風險**: Day margin 僅適用於交易端 (execution)，不適用於 Portfolio 層
3. **保守原則**: 確保極端市場條件下的資金安全

### Margin Basis 定義
- **exchange_maintenance**: 交易所 maintenance 等級的保守固定值
- **conservative_over_exchange**: 高於交易所官方公告的保守值
- **broker_day**: 券商 day margin (禁止在 Portfolio OS 中使用)

## 更新原則
1. 僅更新 `configs/portfolio/instruments.yaml`
2. 不硬寫在程式碼中
3. 變更時需更新此文件記錄來源與日期
4. 測試需使用更新後的值驗證

## 驗證方法
執行測試確認規格正確性：
```bash
python3 -m pytest tests/portfolio/test_signal_series_exporter_v1.py::test_instruments_config_loader -v
```

## 注意事項
- 保證金要求會隨市場波動調整，需定期檢視
- Portfolio OS 使用保守值，實際交易應以券商要求為準
- 此為風險控管專用值，確保資金安全邊際
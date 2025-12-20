# Phase 6.5 Data Ingest v1 - 專案憲法

## 概述

Phase 6.5 Data Ingest v1 實現「Raw means RAW」原則，確保原始資料的不可變性和可追溯性。本模組提供極度愚蠢（immutable, extremely stupid）的原始資料攝取，禁止任何資料清理操作，除非明確記錄在 `ingest_policy` 中。

## 四條鐵律（專案憲法）

### 1. Raw means RAW（禁止 sort/dedupe/dropna）

**核心原則**：一行不動保留 TXT 的 row order。

**禁止操作**：
- `dropna()` - 禁止刪除空值
- `sort_values()` - 禁止排序
- `drop_duplicates()` - 禁止去重

**允許操作**（僅格式標準化，需記錄在 `ingest_policy`）：
- 24:00:00 → 隔日 00:00:00（格式標準化）
- Column mapping（欄位名稱對齊）

**實作位置**：
- `src/FishBroWFS_V2/data/raw_ingest.py`
- `tests/test_data_ingest_raw_means_raw.py`（防回歸測試）

**測試鎖死**：
- `test_row_order_preserved()` - 確保 row order 不變
- `test_duplicate_ts_str_not_deduped()` - 確保重複不被去重
- `test_volume_zero_preserved()` - 確保 volume=0 不被刪除

### 2. Naive ts_str 契約（RED TEAM #2）

**核心原則**：ts 不要 parse 成 datetime（避免任何時區/本地環境影響）。

**v1 契約**：
- 直接存 `ts_str`：字面字串
- 格式必須等於 `Date + " " + Time` 經「允許的格式標準化」後的結果
- 後續若要 datetime，Phase 6.6 另開 canonicalization pipeline（不在 v1 做）

**欄位與型別**（固定）：
- `ts_str`: `str`（字面）
- `open/high/low/close`: `float64`
- `volume`: `int64`（允許 0，不得刪）

**24:00 parser 規則**（允許的格式標準化）：
- 若 Time 出現 `24:xx:xx`：
  - 只允許 `24:00:00`
  - 轉成隔日 `00:00:00`
  - `ts_str` 也要輸出標準化後的字面結果（例如 `2013/1/1 24:00:00` → `2013/1/2 00:00:00`）
  - `policy` 記錄：`normalized_24h=True`

**實作位置**：
- `src/FishBroWFS_V2/data/raw_ingest.py::_normalize_24h()`

### 3. Fingerprint 強制進入 Job + Governance（Binding #3）

**核心原則**：`data_fingerprint_sha1` 必須只依賴原始 TXT 的內容與 `ingest_policy`。

**Truth Fingerprint**：
- 基於 Raw TXT，不基於 parquet
- Parquet 是 cache，不是 truth
- 計算方式：逐行讀檔（bytes）計 SHA1 + `ingest_policy` JSON（穩定排序）

**強制進入點**：
1. **JobRecord / JobSpec**：
   - `jobs` table 新增欄位：`data_fingerprint_sha1 TEXT DEFAULT ''`
   - `create_job()` 必須寫入（若 spec 沒提供就存空字串，但後續標記 DIRTY）

2. **Governance Artifact**：
   - `GovernanceReport.metadata` 必含 `data_fingerprint_sha1`
   - `governance_eval.py` 從 manifest 讀取並寫入 metadata

3. **Viewer 驗證**：
   - 若 `governance` 或 `manifest` 缺 `data_fingerprint_sha1` 或空字串：
     - `status = INVALID(DIRTY)`
     - 顯示紅色警告：「Missing Data Fingerprint — report is untrustworthy」

**實作位置**：
- `src/FishBroWFS_V2/data/fingerprint.py`
- `src/FishBroWFS_V2/control/jobs_db.py`
- `src/FishBroWFS_V2/pipeline/governance_eval.py`
- `src/FishBroWFS_V2/core/artifact_status.py`

### 4. Parquet is Cache（clean-data + rebuild）（Binding #4）

**核心原則**：Parquet 是 cache，不是 truth。可刪可重建。

**Cache 結構**：
- `{symbol}.parquet` - 存 raw df（含 ts_str），不做排序、不做去重
- `{symbol}.meta.json` - 必含：
  - `data_fingerprint_sha1`
  - `source_path`
  - `ingest_policy`
  - `rows`, `first_ts_str`, `last_ts_str`

**清理機制**：
- `make clean-data` - 刪除所有 cache_root 下的 `*.parquet` 和對應 `meta.json`
- 只刪 cache，不刪 raw txt
- 重建後 fingerprint 必須不變（測試鎖死）

**實作位置**：
- `src/FishBroWFS_V2/data/cache.py`
- `scripts/clean_data_cache.py`
- `Makefile::clean-data`
- `tests/test_data_cache_rebuild_fingerprint_stable.py`

## API 簽名（固定契約）

### Raw Ingest

```python
from FishBroWFS_V2.data.raw_ingest import IngestPolicy, RawIngestResult, ingest_raw_txt

@dataclass(frozen=True)
class IngestPolicy:
    normalized_24h: bool = False
    column_map: dict[str, str] | None = None

@dataclass(frozen=True)
class RawIngestResult:
    df: pd.DataFrame  # columns exactly: ts_str, open, high, low, close, volume
    source_path: str
    rows: int
    policy: IngestPolicy

def ingest_raw_txt(
    txt_path: Path,
    *,
    column_map: dict[str, str] | None = None,
) -> RawIngestResult:
    ...
```

### Fingerprint

```python
from FishBroWFS_V2.data.fingerprint import DataFingerprint, compute_txt_fingerprint

@dataclass(frozen=True)
class DataFingerprint:
    sha1: str
    source_path: str
    rows: int
    first_ts_str: str
    last_ts_str: str
    ingest_policy: dict

def compute_txt_fingerprint(path: Path, *, ingest_policy: dict) -> DataFingerprint:
    ...
```

### Cache

```python
from FishBroWFS_V2.data.cache import CachePaths, cache_paths, write_parquet_cache, read_parquet_cache

@dataclass(frozen=True)
class CachePaths:
    parquet_path: Path
    meta_path: Path

def cache_paths(cache_root: Path, symbol: str) -> CachePaths: ...
def write_parquet_cache(paths: CachePaths, df: pd.DataFrame, meta: dict) -> None: ...
def read_parquet_cache(paths: CachePaths) -> tuple[pd.DataFrame, dict]: ...
```

## 測試鎖死

All data ingest invariants are enforced by pytest. Manual execution is not required nor supported.

### 防回歸測試（RED TEAM #1）

`tests/test_data_ingest_raw_means_raw.py`：
- `test_row_order_preserved()` - Row order 不變
- `test_duplicate_ts_str_not_deduped()` - Duplicate 不被去重
- `test_volume_zero_preserved()` - 空值不被丟掉
- `test_no_sort_values_called()` - 確保 sort 未被調用
- `test_no_drop_duplicates_called()` - 確保 dedup 未被調用
- `test_no_dropna_called()` - 確保 dropna 未被調用

### Fingerprint 穩定性測試

`tests/test_data_cache_rebuild_fingerprint_stable.py`：
- `test_cache_rebuild_fingerprint_stable()` - 刪 parquet 再重建 fingerprint 不變
- `test_cache_rebuild_with_24h_normalization()` - 24h 標準化後 fingerprint 穩定

### 端到端測試

`tests/test_data_ingest_e2e.py`：
- `test_ingest_cache_e2e()` - 完整流程：Ingest → Fingerprint → Cache
- `test_clean_rebuild_fingerprint_stable()` - Clean → Rebuild → Fingerprint 穩定

## 檔案清單

### 新增檔案

1. `src/FishBroWFS_V2/data/__init__.py`
2. `src/FishBroWFS_V2/data/raw_ingest.py`
3. `src/FishBroWFS_V2/data/fingerprint.py`
4. `src/FishBroWFS_V2/data/cache.py`
5. `scripts/clean_data_cache.py`
6. `tests/test_data_cache_rebuild_fingerprint_stable.py`
7. `tests/test_data_ingest_raw_means_raw.py`
8. `docs/DATA_INGEST_V1.md`（本文檔）

### 修改檔案

1. `src/FishBroWFS_V2/control/types.py` - 新增 `data_fingerprint_sha1` 到 `JobSpec` 和 `JobRecord`
2. `src/FishBroWFS_V2/control/jobs_db.py` - 新增 `data_fingerprint_sha1` 欄位到 jobs table
3. `src/FishBroWFS_V2/pipeline/governance_eval.py` - 新增 `data_fingerprint_sha1` 到 metadata
4. `src/FishBroWFS_V2/core/artifact_status.py` - 新增 fingerprint 驗證邏輯
5. `Makefile` - 新增 `clean-data` target

## 使用範例

### 基本使用

```python
from pathlib import Path
from FishBroWFS_V2.data import ingest_raw_txt, compute_txt_fingerprint, cache_paths, write_parquet_cache

# Ingest raw TXT
txt_path = Path("data/raw/CME.MNQ.txt")
result = ingest_raw_txt(txt_path)

# Compute fingerprint
policy_dict = {
    "normalized_24h": result.policy.normalized_24h,
    "column_map": result.policy.column_map,
}
fingerprint = compute_txt_fingerprint(txt_path, ingest_policy=policy_dict)

# Write cache
cache_root = Path("parquet_cache")
paths = cache_paths(cache_root, "CME.MNQ")
meta = {
    "data_fingerprint_sha1": fingerprint.sha1,
    "source_path": str(txt_path),
    "ingest_policy": policy_dict,
    "rows": result.rows,
    "first_ts_str": result.df.iloc[0]["ts_str"],
    "last_ts_str": result.df.iloc[-1]["ts_str"],
}
write_parquet_cache(paths, result.df, meta)
```

### 清理 Cache

```bash
make clean-data
```

## 注意事項

1. **RED TEAM 警告**：任何違反「Raw means RAW」原則的操作都會被標記為 DIRTY
2. **時區處理**：v1 不做 datetime parse，避免時區問題
3. **Fingerprint 穩定性**：fingerprint 必須只依賴 raw TXT + policy，不依賴 parquet
4. **Viewer 行為**：缺少 fingerprint 的報告會被標記為 INVALID(DIRTY)，顯示紅色警告
5. **測試 Fixtures 要求**：所有測試用的 artifact JSON fixtures（`manifest_valid.json`、`governance_valid.json` 等）必須包含 `data_fingerprint_sha1` 欄位且非空，否則驗證會標記為 DIRTY。建議使用測試用的固定值如 `"1111111111111111111111111111111111111111"`（40 hex 字元）。

## 未來擴展（Phase 6.6+）

- Canonicalization pipeline（datetime parse、時區處理）
- 資料清理 pipeline（sort/dedup/dropna，但必須記錄在 policy）
- 更多格式標準化規則（需記錄在 policy）

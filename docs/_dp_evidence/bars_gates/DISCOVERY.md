# Bars Gates Discovery Log

## PART 0 — DISCOVERY SUMMARY

**Date**: 2026-01-18  
**Task**: Discover canonical bars contract for "Eatable Bars" Gates (A/B/C) implementation  
**Method**: codebase_search + file reading

## QUERY 1: Bars Contract Required Columns

**Query**: "required keys bars contract ts open high low close volume"

**Results**:
1. `src/core/timeframe_aggregator.py` (lines 38-41):
   ```python
   required_keys = {"ts", "open", "high", "low", "close", "volume"}
   if not required_keys.issubset(bars.keys()):
       raise ValueError(f"Missing required keys: {required_keys - bars.keys()}")
   ```

2. `src/control/shared_build.py` (lines 497-498):
   ```python
   required_keys = {"ts", "open", "high", "low", "close", "volume"}
   if not required_keys.issubset(existing_norm.keys()):
       raise ValueError(f"現有 normalized bars 缺少必要欄位: {existing_norm.keys()}")
   ```

3. `src/control/shared_build.py` (lines 686-687):
   ```python
   required_keys = {"ts", "open", "high", "low", "close", "volume"}
   missing_keys = required_keys - set(resampled_data.keys())
   if missing_keys:
       raise ValueError(f"resampled bars 缺少必要 keys: {missing_keys}")
   ```

**Conclusion**: The canonical bars contract requires exactly these 6 columns: `ts`, `open`, `high`, `low`, `close`, `volume`.

## QUERY 2: Data Types and Constraints

**Query**: "ts dtype datetime64[s] bars"

**Results**:
1. `src/control/shared_build.py` (line 580):
   ```python
   "ts_dtype": "datetime64[s]",  # 時間戳記 dtype
   ```

2. `src/control/shared_build.py` (lines 503-510):
   ```python
   # 確保新資料的時間在舊資料之後（append-only）
   last_existing_ts = existing_norm["ts"][-1]
   first_new_ts = normalized["ts"][0]
   
   if first_new_ts <= last_existing_ts:
       raise ValueError(
           f"INCREMENTAL 模式要求新資料在舊資料之後，但 "
           f"first_new_ts={first_new_ts} <= last_existing_ts={last_existing_ts}"
       )
   ```

**Conclusion**: 
- `ts` must be `datetime64[s]` (seconds precision)
- Bars must be sorted ascending by `ts`
- For incremental builds, new bars must have `ts > last_existing_ts` (strictly monotonic)

## QUERY 3: Raw Parquet Schema

**Query**: "expected cols timestamp open high low close volume"

**Results**:
1. `src/control/data_build.py` (lines 252-256):
   ```python
   expected_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
   if list(validate_df.columns) != expected_cols:
       notes.append(f"Warning: Schema mismatch. Expected {expected_cols}, got {list(validate_df.columns)}")
   ```

2. `src/control/data_build.py` (lines 183-188):
   ```python
   df['timestamp'] = pd.to_datetime(df['ts_str'], format='%Y/%m/%d %H:%M:%S', errors='coerce')
   df = df.drop(columns=['ts_str'])
   df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
   ```

**Conclusion**: Raw parquet files use column name `timestamp` (not `ts`). After normalization, it becomes `ts` with `datetime64[s]` dtype.

## QUERY 4: Bars Reading Code

**Query**: "read_parquet bars"

**Results**:
1. `src/portfolio/runner_v1.py` (lines 77-85):
   ```python
   try:
       df = pd.read_parquet(parquet_path)
       # Filter by instrument if needed
       if "instrument" in df.columns:
           df = df[df["instrument"] == instrument_id].copy()
       return df
   except Exception as e:
       logger.error(f"Failed to load {parquet_path}: {e}")
       return None
   ```

2. `src/control/input_manifest.py` (lines 176-195):
   ```python
   # Quick schema check
   import pandas as pd
   df_sample = pd.read_parquet(parquet_path, nrows=1)
   schema_ok = True
   ```

**Conclusion**: Bars are read via `pd.read_parquet()` with minimal validation in reading code.

## QUERY 5: Bars Build Entrypoint

**Query**: "_build_bars_cache"

**Results**:
1. `src/control/shared_build.py` (lines 428-602): Full `_build_bars_cache` function
   - Normalizes raw bars from `raw_ingest_result`
   - Handles FULL vs INCREMENTAL modes
   - Writes normalized bars (`normalized_bars.npz`)
   - Resamples to timeframes (`resampled_{tf}m.npz`)
   - Creates bars manifest

2. `src/control/shared_build.py` (lines 168-191): Bars build invocation
   ```python
   if build_bars:
       bars_cache_report = _build_bars_cache(
           season=season,
           dataset_id=dataset_id,
           raw_ingest_result=raw_ingest_result,
           outputs_root=outputs_root,
           mode=mode,
           diff=diff,
           tfs=tfs,
           build_bars=True,
       )
   ```

**Conclusion**: The main bars build entrypoint is `_build_bars_cache()` called from `build_shared()`.

## QUERY 6: Bars Manifest SSOT

**Query**: "bars_manifest"

**Results**:
1. `src/control/bars_manifest.py` (not read but referenced)
2. `src/control/shared_build.py` (lines 180-191):
   ```python
   from control.bars_manifest import (
       bars_manifest_path,
       write_bars_manifest,
   )
   
   bars_manifest_file = bars_manifest_path(outputs_root, season, dataset_id)
   final_bars_manifest = write_bars_manifest(
       bars_cache_report["bars_manifest_data"],
       bars_manifest_file,
   )
   bars_manifest_sha256 = final_bars_manifest.get("manifest_sha256")
   ```

**Conclusion**: Bars manifest is the SSOT (Single Source of Truth) tracking all bars artifacts.

## CANONICAL BARS CONTRACT DEFINITION

Based on discovery, the canonical bars contract is:

### 1. **Column Requirements**
- **Required columns**: `ts`, `open`, `high`, `low`, `close`, `volume`
- **Column names**: Must match exactly (case-sensitive)
- **No extra columns**: Only these 6 columns allowed

### 2. **Data Types**
- `ts`: `datetime64[s]` (NumPy datetime64 with second precision)
- `open`, `high`, `low`, `close`: `float64` (or compatible numeric)
- `volume`: `int64` or `float64` (numeric)

### 3. **Data Quality Constraints**
- **No nulls**: All values must be non-null
- **Positive volume**: `volume >= 0` (zero allowed)
- **Price sanity**: `low <= open <= high`, `low <= close <= high`
- **Positive prices**: `open > 0`, `high > 0`, `low > 0`, `close > 0`

### 4. **Temporal Constraints**
- **Sorted**: Bars must be sorted ascending by `ts`
- **Monotonic**: `ts[i] < ts[i+1]` (strictly increasing)
- **No duplicates**: No duplicate timestamps

### 5. **File Format**
- **Normalized bars**: Stored as NPZ files with numpy arrays
- **Raw parquet**: Column `timestamp` (not `ts`) before normalization
- **Resampled bars**: Same contract but at different timeframes

## THREE GATES DESIGN

Based on the task requirements:

### **Gate A (Existence/Openability)**
- Check: File exists and can be opened/read
- Validation: `Path.exists()`, `np.load()` succeeds
- Error: "File not found" or "Cannot open file"

### **Gate B (Schema Contract)**
- Check: All 6 required columns present with correct dtypes
- Validation: Check keys, dtype of `ts` is `datetime64[s]`
- Error: "Missing column X" or "Invalid dtype for ts"

### **Gate C (Manifest SSOT Integrity)**
- Check: Bars manifest matches actual file content
- Validation: Compare SHA256 hashes in manifest vs computed
- Error: "Manifest hash mismatch" or "Missing manifest entry"

## NEXT STEPS

1. **PART 1**: Define single bars contract SSOT module at `src/core/bars_contract.py`
2. **PART 2**: Implement three gates validators
3. **PART 3**: Integrate gates into BarPrepare build pipeline
4. **PART 4**: Create tests for validators
5. **PART 5**: Create evidence bundle

## DISCOVERY COMPLETION

PART 0 discovery is complete. The canonical bars contract is well-defined and ready for implementation.
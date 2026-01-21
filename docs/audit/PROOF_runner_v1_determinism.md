# PROOF: Non-Determinism Analysis for runner_v1.py

## Objective
Confirm whether `src/portfolio/runner_v1.py` exhibits non-deterministic behavior when loading strategy artifacts.

## Findings

### 1. Code-Level Inspection
The function `load_signal_series` in `src/portfolio/runner_v1.py` contains the following logic:

```python
pattern = f"**/{strategy_id}/**/signal_series.parquet"
matches = list(outputs_root.glob(pattern))

if not matches:
    # ... handle missing ...
    return None

# Use first match
parquet_path = matches[0]
```

### 2. Determinism Violation
- **Unordered Glob**: The `pathlib.Path.glob` method returns a generator that does not guarantee any specific order. The order depends on the filesystem's directory entry sequence, which can vary across platforms or even between runs on the same platform if files are added/deleted.
- **Implicit Selection**: By taking `matches[0]`, the code picks an arbitrary file if multiple matches exist.

### 3. Data Layout Collision
In a production-like environment, multiple job runs for the same `strategy_id` can coexist:
- `outputs/jobs/{job_id_A}/artifacts/{strategy_id}/signal_series.parquet`
- `outputs/jobs/{job_id_B}/artifacts/{strategy_id}/signal_series.parquet`

The current glob pattern `**/{strategy_id}/**/signal_series.parquet` will find **both**. Because `matches[0]` is used without sorting (e.g., by timestamp or version) or explicit pinning (e.g., by `job_id`), the resulting portfolio build is non-deterministic.

### 4. Impact
Users attempting to rebuild a portfolio from a frozen season might get different results if the OS returns glob matches in a different order. This violates the core requirement of "reproducible research" and "deterministic selection" for governance.

## Conclusion: NON-DETERMINISTIC
The artifact loading mechanism in `runner_v1.py` is inherently non-deterministic. A minimal fix is required to ensure that artifact selection is pinned to a specific run or at least sorted to provide a stable choice.

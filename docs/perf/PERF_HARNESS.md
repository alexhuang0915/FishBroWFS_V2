# Performance Harness Usage

The performance harness provides three tiers for different use cases.

## Performance Tiers

### Baseline (`make perf`)
- **Configuration**: 20,000 bars × 1,000 params
- **Hot runs**: Default (5)
- **Timeout**: Default (600s)
- **Use case**: Fast, suitable for commit-to-commit comparison
- **Recommended**: Use this for regular performance checks

### Mid-tier (`make perf-mid`)
- **Configuration**: 20,000 bars × 10,000 params
- **Hot runs**: 3 (reduced to avoid timeout)
- **Timeout**: 1200s (extended to ensure completion)
- **Use case**: Medium-scale performance testing
- **When to use**: When you need more parameter coverage but still want reasonable runtime
- **Note**: Not for daily use; use when you need more comprehensive parameter testing

### Heavy-tier (`make perf-heavy`)
- **Configuration**: 200,000 bars × 10,000 params
- **Hot runs**: 1 (single hot run sufficient for throughput measurement)
- **Timeout**: 3600s (1 hour, extended for large-scale testing)
- **Use case**: Full-scale performance validation
- **Warning**: This is expensive and should be used intentionally, not as part of regular workflow
- **When to use**: Before releases or when investigating performance regressions
- **Note**: Not for daily use; heavy tier is for stress testing and release validation

## Usage

```bash
# Baseline (recommended for regular use)
make perf

# Mid-tier
make perf-mid

# Heavy-tier (use intentionally)
make perf-heavy
```

## Environment Variable Override

You can override bars and params via environment variables:

```bash
FISHBRO_PERF_BARS=50000 FISHBRO_PERF_PARAMS=5000 make perf
```

Other environment variables:
- `FISHBRO_PERF_HOTRUNS`: Number of hot runs (default: 5)
- `FISHBRO_PERF_TIMEOUT_S`: Timeout in seconds (default: 600)

## Output

The perf harness outputs:
- Performance metrics table
- Cost model estimation (bars, params, best_time_s, params_per_sec, cost_ms_per_param, estimated_time_for_50k_params)

## Sparse Intents (Stage P2-1)

Starting from Stage P2-1, entry intents are generated with sparse masking to reduce memory bandwidth and improve performance.

### Intent Count Reduction

**Dense → Sparse Intent Generation:**
- **Before (dense)**: Intent generated for every bar (after warmup), even if indicator value is invalid
- **After (sparse)**: Intent only generated for bars where:
  - Indicator value is finite (`~np.isnan(donch_hi)`)
  - Indicator value is positive (`donch_hi > 0`)
  - Bar index is past warmup (`i >= channel_len`)

**Expected Impact:**
- `intents_total` typically drops by 50-95% depending on data characteristics
- `intents_per_bar_avg` reflects the sparse count (significantly lower than dense)
- Performance improves due to reduced memory bandwidth and fewer intent processing operations

**MVP Scope:**
- Only entry intents use sparse masking (exit intents unchanged)
- Masking is applied at intent generation layer (`strategy/kernel.py`)
- Engine kernel (`engine_jit`) remains unchanged (receives pre-filtered sparse arrays)

### Example

For a typical run with 20,000 bars and `channel_len=20`:
- **Dense**: ~19,980 entry intents (all bars after warmup)
- **Sparse**: ~1,000-5,000 entry intents (only valid trigger points)
- **Reduction**: 75-95% fewer intents to process

## Notes

- All perf targets are stdout-only and non-CI
- Baseline tier is designed for quick feedback during development
- Heavy tier should not be run as part of regular CI/CD pipeline
- Sparse masking (P2-1) significantly reduces intent count and improves performance

# FishBroWFS_V2

Speed-first quantitative backtesting engine.

This repository uses tests as the primary specification.

## Testing tiers

- **`make check`**: Fast, CI-safe tests (excludes slow research-grade tests)
- **`make research`**: Slow, manual research-grade tests (full backtest + correlation validation)

## Performance tiers

- **`make perf`**: Baseline (20000×1000) - Fast, suitable for commit-to-commit comparison (hot_runs=5, timeout=600s)
- **`make perf-mid`**: Mid-tier (20000×10000) - Medium-scale performance testing (hot_runs=3, timeout=1200s)
- **`make perf-heavy`**: Heavy-tier (200000×10000) - Full-scale validation (hot_runs=1, timeout=3600s, expensive, use intentionally)

**Note**: Mid-tier and heavy-tier are not for daily use. Baseline is recommended for regular performance checks.

See `docs/PERF_HARNESS.md` for detailed usage.

## Funnel Architecture (WFS at scale)

This project uses a multi-stage funnel:

- **Stage 0**: vector/proxy ranking (no matcher, no orders) — see `docs/STAGE0_FUNNEL.md`
- Stage 1: light backtest (planned)
- Stage 2: full semantics (matcher + fills) for final candidates

Stage 0 v0 implementation:

- `FishBroWFS_V2.stage0.stage0_score_ma_proxy()`



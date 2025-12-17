# FishBroWFS_V2

Speed-first quantitative backtesting engine.

This repository uses tests as the primary specification.

## Testing tiers

- **`make check`**: Fast, CI-safe tests (excludes slow research-grade tests)
- **`make research`**: Slow, manual research-grade tests (full backtest + correlation validation)

## Funnel Architecture (WFS at scale)

This project uses a multi-stage funnel:

- **Stage 0**: vector/proxy ranking (no matcher, no orders) — see `docs/STAGE0_FUNNEL.md`
- Stage 1: light backtest (planned)
- Stage 2: full semantics (matcher + fills) for final candidates

Stage 0 v0 implementation:

- `FishBroWFS_V2.stage0.stage0_score_ma_proxy()`



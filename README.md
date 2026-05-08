# BTCUSDT Game Theory Engine v0.2

Minimalistic live GUI for BTCUSDT market-state monitoring using Binance websocket data.

## Run

```bash
python main.py
```

or bootstrap env:

```bash
./scripts/run.sh
```

## Architecture

- `app/` runtime orchestration
- `ui/` PySide6 adaptive dashboard
- `core/` integration pipeline to snapshot
- `ws/` Binance websocket feed (`aggTrade`, `depth20`, `bookTicker`, `miniTicker`)
- `metrics/` microstructure metrics (aggression, velocity, imbalance, spread behavior)
- `market_state/` finite-state market regime detector
- `game_theory/` long/short pressure + trap probability + edge score
- `simulation/` paper-mode virtual position block


## v0.8 Futures Paper Prep
- Pipeline audit documented: `docs/PIPELINE_AUDIT_v0.8.md`.
- Futures paper position manager and entry risk gate expanded.
- Added contract tests: `tests/test_pipeline_contracts.py`.
- Safety mode: paper-only, no live routing.

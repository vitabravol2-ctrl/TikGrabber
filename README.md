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

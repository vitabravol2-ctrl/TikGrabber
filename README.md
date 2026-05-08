# BTCUSDT Game Theory Engine v0.1

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
- `core/` state models + simple game-theory heuristics
- `market/` Binance websocket feed (`trade`, `depth`, `bookTicker`)
- `simulation/` paper-mode virtual position block

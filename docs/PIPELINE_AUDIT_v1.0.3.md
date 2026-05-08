# PIPELINE AUDIT v1.0.3

## Реальная цепочка
DATA -> WS cache (book/depth/mini) -> DataQualityGate -> Microstructure -> MarketState FSM -> GameTheory -> Decision + BreakEven -> Risk -> PaperSimulator -> ExecutionModel -> TP/SL/TIMEOUT -> Validation -> Replay -> GUI.

## Что было исправлено
- Добавлен честный cache в `ws/binance_ws.py` с bid/ask, qty, depth totals, imbalance, mini volume и timestamp-диагностикой.
- На каждом aggTrade теперь эмитится последний cached snapshot, а не нули.
- Добавлены diagnostics: `book_ready`, `depth_ready`, `mini_ready`, `book_age_ms`, `depth_age_ms`, `mini_age_ms`, `ws_streams_seen`, `last_stream`.
- В `core/engine.py` вынесен `DataQualityGate` с точными причинами: `MISSING_BOOK_TICKER`, `MISSING_DEPTH`, `STALE_BOOK`, `STALE_DEPTH`, `WARMUP_TRADES`, `WS_UNSTABLE`, `GOOD`, `LEGACY_REPLAY`.

## Где были обрывы
- Warmup мог маскировать missing book/depth.
- aggTrade мог приходить чаще bookTicker/depth и false-block сигналов.

## Блокеры входа
- Data quality missing/stale.
- No edge after fees (`NO_EDGE_AFTER_FEES`).
- Risk gate: spread/vol/liquidity/cooldown/leverage/margin/weak signal.

## Почему live trading заблокирован
- В проекте используется только `REALISTIC PAPER`, execution = `SIMULATED`; реальные API ордера не используются.

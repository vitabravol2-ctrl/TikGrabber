# PIPELINE AUDIT v0.8

## Что работает
- Binance WS agg_trade events доходят до AppController и обновляют MarketSnapshot.
- Microstructure metrics, Market State FSM, Game Theory score и Decision Engine связаны по цепочке.
- Paper Simulator открывает/закрывает paper-сделки через taker fill + fees/slippage.
- Validation принимает только accepted signals.
- GUI рендерит market/signal/simulation telemetry и flow терминалы.

## Что найдено
- Position layer был слишком минимальный (не хватало full futures полей для paper-model runtime).
- Risk gate был только как placeholder без полного набора блокировок.
- Контрактные проверки между модулями отсутствовали.

## Что исправлено
- Доработан `position/manager.py` до paper futures позиции с mark/notional/margin/liquidation/unrealized/realized pnl.
- Доработан `risk/controls.py` с единым `evaluate_entry` и причинами BLOCK/PASS.
- Добавлены контрактные тесты `tests/test_pipeline_contracts.py` по ключевым условиям целостности цепочки.

## Слабые места (остались)
- Order-book intelligence сейчас базовый; можно расширить стабильность стенок и memory по pull/add.
- GUI еще не показывает все новые риск/позиционные поля отдельными компакт-панелями.
- Quality grade логика частично завязана на validation history и может быть улучшена для A+.

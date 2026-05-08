# STATUS v0.8

## Реализовано
- Базовая честная цепочка futures paper microcycle сохранена.
- Усилен position layer для paper futures модели.
- Добавлен risk gate c блокировками входа по качеству/ликвидности/волатильности/позиции/cooldown/левереджу/сигналу.
- Добавлены pipeline contract tests.

## Проверено
- py_compile для `app/main.py`, `ui/dashboard.py`, `core/models.py`.
- `PYTHONPATH=. pytest -q`.

## Тесты
- `tests/test_pipeline_contracts.py`.
- Существующие regression-тесты lifecycle/paper simulation.

## Known issues
- GUI компакт-панели v0.8 можно еще донастроить визуально.
- Risk Gate reason в GUI пока не полностью отдельным блоком.

## Дальше (v0.9)
- Futures replay/backtest dataset-driven цикл.
- Расширение microstructure memory и статистики execution realism.

## Safety
- Только PAPER режим.
- Live trading / real orders / API keys не добавлялись.

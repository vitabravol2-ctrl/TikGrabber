from core.engine import DataQualityGate
from core.models import MarketSnapshot, SimulationState
from signal_engine.engine import TradeSignal
from simulation.execution_model import ExecutionFill
from simulation.paper import PaperSimulator


def _snap(**kwargs):
    s = MarketSnapshot(price=100.0, spread=1.0, buy_pressure=0.8, sell_pressure=0.2, trigger_strength=80.0)
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_trade_event_emitted_once_on_open():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=999, min_hold_ms=0)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(_snap(), TradeSignal.NO_SIGNAL)
    assert sim.state.trade_events.count("LONG_OPENED") == 1


def test_trade_event_emitted_once_on_sl():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=999, min_hold_ms=0, sl_ticks=1, tp_ticks=999)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.execution.exit_fill = lambda *args, **kwargs: ExecutionFill(side="Long", price=99.0, fee_paid=0.0)  # type: ignore
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=2)
    sim.step(_snap(price=98.5), TradeSignal.NO_SIGNAL)
    sim.step(_snap(price=98.0), TradeSignal.NO_SIGNAL)
    assert sim.state.trade_events.count("SL_CLOSED") == 1


def test_trade_event_emitted_once_on_timeout():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=0.0, min_hold_ms=0, sl_ticks=999, tp_ticks=999)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.execution.exit_fill = lambda *args, **kwargs: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=3)
    sim.step(_snap(price=100.01), TradeSignal.NO_SIGNAL)
    sim.step(_snap(price=100.02), TradeSignal.NO_SIGNAL)
    assert sim.state.trade_events.count("TIMEOUT_CLOSED") == 1


def test_ui_does_not_append_active_state_as_log_each_tick(monkeypatch):
    pytest = __import__("pytest")
    QApplication = pytest.importorskip("PySide6.QtWidgets").QApplication
    DashboardWindow = __import__("ui.dashboard", fromlist=["DashboardWindow"]).DashboardWindow
    app = QApplication.instance() or QApplication([])
    w = DashboardWindow()
    sim = SimulationState()
    sim.trade_events = ["LONG_OPENED"]
    snap = _snap(book_status="OK", depth_status="OK", can_trade_data=True, data_quality_reason="GOOD")
    w.render(snap, sim)
    before = w.trade_flow_terminal.toPlainText()
    sim.virtual_position = "Long"
    sim.active_trade_side = "Long"
    sim.hold_seconds = 5.0
    w.render(snap, sim)
    after = w.trade_flow_terminal.toPlainText()
    assert after == before
    app.quit()


def test_book_warmup_before_unknown():
    gate = DataQualityGate()
    out = gate.evaluate({"book_ready": True, "depth_ready": True, "book_age_ms": -1.0, "depth_age_ms": 10.0, "bid": 100.0, "ask": 101.0, "first_event_ts_ms": 1000.0, "now_ms": 3500.0}, tick_speed=8)
    assert out["data_quality_reason"] == "WARMUP_BOOK"


def test_bookticker_updates_book_age():
    gate = DataQualityGate()
    out = gate.evaluate({"book_ready": True, "depth_ready": True, "book_age_ms": 50.0, "depth_age_ms": 10.0, "bid": 100.0, "ask": 101.0}, tick_speed=8)
    assert out["book_age_ms"] == 50.0 and out["book_status"] == "OK"


def test_empty_bookticker_does_not_clear_cache():
    from ws.binance_ws import BinanceFeedWorker

    worker = BinanceFeedWorker()
    worker._book.bid = 100.0
    worker._book.ask = 101.0
    worker._on_message(None, '{"stream":"btcusdt@bookTicker","data":{"b":"","a":""}}')
    assert worker._book.bid == 100.0 and worker._book.ask == 101.0

from core.engine import DataQualityGate
from core.models import FuturesPositionModel, MarketSnapshot
from risk.controls import FuturesRiskControls
from signal_engine.engine import TradeSignal
from simulation.execution_model import ExecutionFill
from simulation.paper import PaperSimulator
from ws.binance_ws import BinanceFeedWorker


def _snap(**kwargs):
    s = MarketSnapshot(
        price=100.0,
        spread=1.0,
        velocity=0.1,
        buy_pressure=0.8,
        sell_pressure=0.2,
        trigger_strength=80.0,
        can_trade_data=True,
        data_quality_reason="GOOD",
        signal_quality="A",
        noise_level="LOW",
        edge_stability="STABLE",
        expected_move_ticks=5.0,
        min_profitable_ticks=2.0,
        net_edge_score=30.0,
        best_direction="LONG",
        ticks_per_second=8.0,
        book_status="OK",
        depth_status="OK",
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_depth_top_fallback_sets_book_ok_fallback():
    gate = DataQualityGate()
    out = gate.evaluate({"book_ready": True, "depth_ready": True, "book_status": "ok_fallback", "book_age_ms": -1.0, "depth_age_ms": 20.0, "bid": 100.0, "ask": 100.1}, tick_speed=7)
    assert out["book_status"] == "OK_FALLBACK"


def test_unknown_book_not_triggered_when_depth_top_available():
    gate = DataQualityGate()
    out = gate.evaluate({"book_ready": True, "depth_ready": True, "book_status": "ok_fallback", "book_age_ms": -1.0, "depth_age_ms": 22.0, "bid": 100.0, "ask": 100.1}, tick_speed=7)
    assert out["data_quality_reason"] != "UNKNOWN_BOOK"


def test_bookticker_stream_updates_book_cache():
    worker = BinanceFeedWorker()
    worker._on_message(None, '{"stream":"btcusdt@bookTicker","data":{"b":"100.1","a":"100.2","B":"1","A":"2"}}')
    assert worker._book.bid == 100.1 and worker._book.ask == 100.2


def test_profit_guard_blocks_low_expected_move():
    rc = FuturesRiskControls()
    ok, reason = rc.evaluate_entry(_snap(expected_move_ticks=2.5), FuturesPositionModel(), 1.0, False)
    assert not ok and reason == "MOVE_TOO_SMALL"


def test_profit_guard_allows_high_quality_edge():
    rc = FuturesRiskControls()
    ok, reason = rc.evaluate_entry(_snap(expected_move_ticks=6.0, net_edge_score=40.0), FuturesPositionModel(), 1.0, False)
    assert ok and reason == "PASS"


def test_timeout_can_extend_when_edge_still_valid():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=0.0, min_hold_ms=0, sl_ticks=999, tp_ticks=999)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.execution.exit_fill = lambda *args, **kwargs: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(_snap(price=100.5), TradeSignal.NO_SIGNAL)
    assert sim.state.virtual_position == "Long"


def test_exit_invalidated_when_edge_flips_against_position():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=0.0, min_hold_ms=0, sl_ticks=999, tp_ticks=999)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.execution.exit_fill = lambda *args, **kwargs: ExecutionFill(side="Long", price=99.9, fee_paid=0.0)  # type: ignore
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=2)
    sim.step(_snap(price=99.95, edge_stability="UNSTABLE", noise_level="HIGH", net_edge_score=-30.0), TradeSignal.NO_SIGNAL)
    assert sim.state.last_close_reason == "EXIT_INVALIDATED"


def test_stats_opened_closed_separated():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=999, min_hold_ms=0, sl_ticks=1, tp_ticks=999)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.execution.exit_fill = lambda *args, **kwargs: ExecutionFill(side="Long", price=99.0, fee_paid=0.0)  # type: ignore
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=3)
    sim.step(_snap(price=98.0), TradeSignal.NO_SIGNAL)
    assert sim.state.opened_trades == 1 and sim.state.closed_trades == 1

from core.models import FuturesPositionModel, MarketSnapshot
from risk.controls import FuturesRiskControls
from signal_engine.engine import TradeSignal
from simulation.paper import PaperSimulator
from simulation.execution_model import ExecutionFill


def snap(**kwargs):
    s = MarketSnapshot(
        price=100.0,
        spread=1.0,
        data_quality_reason="GOOD",
        can_trade_data=True,
        book_status="OK",
        depth_status="OK",
        signal_quality="A",
        noise_level="LOW",
        edge_stability="STABLE",
        market_regime="BALANCED",
        expected_move_ticks=5.0,
        min_profitable_ticks=2.0,
        long_probability=70.0,
        short_probability=30.0,
        buy_pressure=0.8,
        sell_pressure=0.2,
        smoothed_edge_score=25.0,
        trigger_strength=80.0,
        ticks_per_second=8.0,
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_long_opened_logged_once_per_trade():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=999, min_hold_ms=0)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore[method-assign]
    sim.step(snap(), TradeSignal.LONG_SIGNAL, signal_id=1)
    first = sim.state.last_event
    sim.step(snap(), TradeSignal.NO_SIGNAL)
    assert first == "LONG_OPENED"
    assert sim.state.last_event == "LONG_OPENED"


def test_timeout_logged_once_after_close():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=0.0, min_hold_ms=0, tp_ticks=99, sl_ticks=99)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore[method-assign]
    sim.execution.exit_fill = lambda *args, **kwargs: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore[method-assign]
    sim.step(snap(), TradeSignal.LONG_SIGNAL, signal_id=2)
    sim.step(snap(price=100.01), TradeSignal.NO_SIGNAL)
    assert sim.state.last_event == "TIMEOUT"
    sim.step(snap(), TradeSignal.NO_SIGNAL)
    assert sim.state.last_event == "TIMEOUT"


def test_no_entry_when_dead_market():
    ok, reason = FuturesRiskControls().evaluate_entry(snap(market_regime="DEAD_MARKET"), FuturesPositionModel(side="FLAT"), 1.0, False)
    assert not ok and reason == "DEAD_MARKET"


def test_no_entry_when_noise_high():
    ok, reason = FuturesRiskControls().evaluate_entry(snap(noise_level="HIGH"), FuturesPositionModel(side="FLAT"), 1.0, False)
    assert not ok and reason == "NOISE_NOT_LOW"


def test_no_entry_when_quality_b():
    ok, reason = FuturesRiskControls().evaluate_entry(snap(signal_quality="B"), FuturesPositionModel(side="FLAT"), 1.0, False)
    assert not ok and reason == "QUALITY_NOT_A"


def test_unknown_book_age_display_safe():
    out = __import__("core.engine", fromlist=["DataQualityGate"]).DataQualityGate().evaluate({"book_ready": True, "depth_ready": True, "book_age_ms": -1.0, "depth_age_ms": 10.0, "bid": 100.0, "ask": 101.0}, tick_speed=8)
    assert out["data_quality_reason"] == "UNKNOWN_BOOK"


def test_opened_closed_trade_counts_separated():
    sim = PaperSimulator(cooldown_seconds=0, timeout_seconds=0.0, min_hold_ms=0, tp_ticks=99, sl_ticks=99)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore[method-assign]
    sim.execution.exit_fill = lambda *args, **kwargs: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore[method-assign]
    sim.step(snap(), TradeSignal.LONG_SIGNAL, signal_id=3)
    assert sim.state.opened_trades == 1 and sim.state.closed_trades == 0
    sim.step(snap(price=100.01), TradeSignal.NO_SIGNAL)
    assert sim.state.closed_trades == 1

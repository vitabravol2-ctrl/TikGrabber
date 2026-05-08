from core.models import MarketSnapshot
from signal_engine import TradeSignal
from simulation.paper import PaperSimulator
from telemetry.event_guard import EventGuard


def _snap(price: float) -> MarketSnapshot:
    return MarketSnapshot(price=price, spread=1.0, market_intent="BALANCED", edge_score=10)


def test_duplicate_event_suppressed():
    guard = EventGuard()
    assert guard.should_emit("trade", "ENTRY")
    assert not guard.should_emit("trade", "ENTRY")
    assert guard.should_emit("trade", "TP")


def test_hold_persists_after_close():
    sim = PaperSimulator(timeout_seconds=0.0, min_hold_ms=0)
    sim.step(_snap(100), TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(_snap(102), TradeSignal.NO_SIGNAL)
    assert sim.state.virtual_position == "Flat"
    assert sim.state.hold_seconds == 0.0
    assert sim.state.last_hold_seconds > 0.0


def test_fees_and_default_notional():
    sim = PaperSimulator(timeout_seconds=0.0, min_hold_ms=0)
    sim.step(_snap(100), TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(_snap(101), TradeSignal.NO_SIGNAL)
    assert sim.default_notional_usdt == 100.0
    assert sim.state.fees_paid < 1.0


def test_realized_unrealized_separated_and_qty_impacts_pnl():
    low = PaperSimulator(timeout_seconds=0.0, min_hold_ms=0, default_notional_usdt=50)
    high = PaperSimulator(timeout_seconds=0.0, min_hold_ms=0, default_notional_usdt=200)
    low.step(_snap(100), TradeSignal.LONG_SIGNAL, signal_id=1)
    high.step(_snap(100), TradeSignal.LONG_SIGNAL, signal_id=1)
    low.step(_snap(101), TradeSignal.NO_SIGNAL)
    high.step(_snap(101), TradeSignal.NO_SIGNAL)
    assert low.state.unrealized_pnl == 0.0
    assert abs(high.state.realized_pnl) > abs(low.state.realized_pnl)


def test_trade_flow_emit_once_signature():
    guard = EventGuard()
    sig = "ENTRY:Long"
    assert guard.should_emit("trade_flow", sig)
    assert not guard.should_emit("trade_flow", sig)


def test_gui_state_model_fields_exist():
    sim = PaperSimulator()
    assert hasattr(sim.state, "realized_pnl")
    assert hasattr(sim.state, "unrealized_pnl")
    assert hasattr(sim.state, "last_trade_pnl")

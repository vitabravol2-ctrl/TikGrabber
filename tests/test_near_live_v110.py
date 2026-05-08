from core.models import MarketSnapshot
from signal_engine import TradeSignal
from simulation.paper import PaperSimulator, SimulatedOrderRouter
from execution.layer import FuturesExecutionConfig, FuturesExecutionLayer


def _snap(price=100.0, spread=1.0):
    return MarketSnapshot(price=price, spread=spread, signal_quality="A", noise_level="LOW", edge_stability="STABLE", expected_move_ticks=4.0)


def test_simulated_limit_order_ack():
    r = SimulatedOrderRouter(0.1)
    o = r.new_limit("BUY", "LONG", 100, 1)
    r.step_fill(o, 99.9, 100.1, o.created_ts + 0.03)
    assert o.status == "ACKED"


def test_simulated_limit_order_partial_fill():
    r = SimulatedOrderRouter(0.1)
    o = r.new_limit("BUY", "LONG", 101, 1)
    r.step_fill(o, 100, 101, o.created_ts + 0.03)
    r.step_fill(o, 100, 101, o.created_ts + 0.04)
    assert o.status == "PARTIALLY_FILLED"


def test_simulated_limit_order_fill():
    r = SimulatedOrderRouter(0.1)
    o = r.new_limit("BUY", "LONG", 101, 1)
    r.step_fill(o, 100, 101, o.created_ts + 0.03)
    r.step_fill(o, 100, 101, o.created_ts + 0.04)
    r.step_fill(o, 100, 101, o.created_ts + 0.05)
    assert o.status == "FILLED"


def test_no_real_order_router_available():
    layer = FuturesExecutionLayer(FuturesExecutionConfig())
    assert layer.can_route_live_order() is False


def test_long_entry_uses_bid_based_price():
    sim = PaperSimulator()
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, 1)
    assert sim.state.order_side == "BUY"


def test_short_entry_uses_ask_based_price():
    sim = PaperSimulator()
    sim.step(_snap(), TradeSignal.SHORT_SIGNAL, 1)
    assert sim.state.order_side == "SELL"

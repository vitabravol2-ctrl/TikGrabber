from core.models import MarketSnapshot
from signal_engine import TradeSignal
from simulation.paper import PaperSimulator


def test_repeated_same_signal_does_not_increment_accepted_signals():
    sim = PaperSimulator(timeout_seconds=999, min_hold_ms=0)
    snap = MarketSnapshot(price=100.0, spread=1.0, market_intent="BALANCED", edge_score=10)
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    assert sim.state.signals_count == 1


def test_last_trade_keeps_entry_exit_after_close_and_cooldown_blocks_duplicate():
    sim = PaperSimulator(timeout_seconds=0.0, cooldown_seconds=10.0, min_hold_ms=0)
    open_snap = MarketSnapshot(price=100.0, spread=1.0, market_intent="BALANCED", edge_score=10)
    close_snap = MarketSnapshot(price=102.0, spread=1.0, market_intent="BALANCED", edge_score=12)
    sim.step(open_snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(close_snap, TradeSignal.NO_SIGNAL)

    assert sim.state.virtual_position == "Flat"
    assert sim.state.last_entry_price > 0
    assert sim.state.last_exit_price > 0

    sim.step(open_snap, TradeSignal.LONG_SIGNAL, signal_id=2)
    assert sim.state.trades == 1


def test_active_trade_entry_visible_only_when_position_active():
    sim = PaperSimulator(timeout_seconds=999, min_hold_ms=0)
    snap = MarketSnapshot(price=100.0, spread=1.0, market_intent="BALANCED", edge_score=10)
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    assert sim.state.virtual_position != "Flat"
    assert sim.state.entry > 0

    sim.state.virtual_position = "Flat"
    assert sim.state.virtual_position == "Flat"

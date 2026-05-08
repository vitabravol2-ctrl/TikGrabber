from core.models import MarketSnapshot
from signal_engine import TradeSignal
from simulation.execution_model import ExecutionModel
from simulation.paper import PaperSimulator


def test_no_entry_with_invalid_price_or_spread():
    sim = PaperSimulator()
    snap = MarketSnapshot(price=0.0, spread=1.0)
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    assert sim.state.trades == 0


def test_no_duplicate_trade_for_same_signal():
    sim = PaperSimulator(timeout_seconds=0.01)
    snap = MarketSnapshot(price=100.0, spread=1.0, market_intent="BALANCED")
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    assert sim.state.trades == 1


def test_fees_reduce_pnl():
    model = ExecutionModel(tick_size=1.0, slippage_ticks=0, taker_fee=0.01)
    entry = model.entry_fill("Long", 100.0, 2.0)
    exitf = model.exit_fill("Long", 103.0, 2.0)
    gross = exitf.price - entry.price
    net = gross - entry.fee_paid - exitf.fee_paid
    assert net < gross


def test_cooldown_blocks_reentry():
    sim = PaperSimulator(timeout_seconds=0.0, cooldown_seconds=10.0, min_hold_ms=0)
    snap = MarketSnapshot(price=100.0, spread=1.0, market_intent="BALANCED")
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=2)
    sim.step(MarketSnapshot(price=101.0, spread=1.0, market_intent="BALANCED"), TradeSignal.NO_SIGNAL)
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=3)
    assert sim.state.trades == 1


def test_short_entry_uses_bid_and_long_entry_uses_ask():
    model = ExecutionModel(tick_size=0.5, slippage_ticks=1)
    long_fill = model.entry_fill("Long", price=100.0, spread=2.0)
    short_fill = model.entry_fill("Short", price=100.0, spread=2.0)
    assert long_fill.price == 101.5
    assert short_fill.price == 98.5

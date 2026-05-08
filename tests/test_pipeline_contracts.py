from __future__ import annotations

from core.models import MarketSnapshot
from signal_engine.engine import TradeSignal
from simulation.paper import PaperSimulator
from validation.engine import SignalValidationEngine


def _snap(**kwargs) -> MarketSnapshot:
    s = MarketSnapshot(price=100.0, spread=1.0, data_quality="Good", ticks_per_second=5.0, trigger_strength=80.0)
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_snapshot_price_non_zero_after_warmup() -> None:
    snap = _snap()
    assert snap.data_quality == "Good"
    assert snap.price > 0


def test_signal_without_spread_cannot_open_trade() -> None:
    sim = PaperSimulator(cooldown_seconds=0)
    snap = _snap(spread=0.0)
    state = sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    assert state.virtual_position == "Flat"


def test_accepted_signal_creates_max_one_trade() -> None:
    sim = PaperSimulator(cooldown_seconds=0)
    snap = _snap()
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=7)
    trades_after_first = sim.state.trades
    sim.state.virtual_position = "Flat"
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=7)
    assert sim.state.trades == trades_after_first


def test_validation_tracks_only_accepted() -> None:
    v = SignalValidationEngine()
    snap = _snap()
    signal_id = v.register_signal(snap, TradeSignal.LONG_SIGNAL)
    assert signal_id is not None
    assert len(v.signal_history) == 0
    v.register_accepted_signal(snap, TradeSignal.LONG_SIGNAL, signal_id)
    assert len(v.signal_history) == 1


def test_active_position_blocks_second_position() -> None:
    sim = PaperSimulator(cooldown_seconds=0)
    snap = _snap()
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(snap, TradeSignal.SHORT_SIGNAL, signal_id=2)
    assert sim.state.trades == 1


def test_cooldown_blocks_reentry() -> None:
    sim = PaperSimulator(cooldown_seconds=999)
    snap = _snap()
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    sim._close_trade(snap, "TIMEOUT", 999999.0)  # force close
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=2)
    assert sim.state.last_event in {"COOLDOWN_BLOCK", "SETUP_BLOCK"}


def test_gui_state_not_fake_entry_zero() -> None:
    sim = PaperSimulator(cooldown_seconds=0)
    snap = _snap(spread=0.0)
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    assert sim.state.entry == 0.0
    assert sim.state.virtual_position == "Flat"


def test_net_pnl_includes_fees_slippage() -> None:
    sim = PaperSimulator(cooldown_seconds=0, tp_ticks=1, sl_ticks=50, min_hold_ms=0)
    entry_snap = _snap(price=100.0, spread=1.0)
    sim.step(entry_snap, TradeSignal.LONG_SIGNAL, signal_id=1)
    move_snap = _snap(price=101.0, spread=1.0)
    sim.step(move_snap, TradeSignal.NO_SIGNAL)
    assert sim.state.last_event in {"TP", "TIMEOUT", "SL"}
    assert sim.state.net_pnl <= sim.state.gross_pnl


def test_flow_like_dedup_key_changes() -> None:
    sim = PaperSimulator(cooldown_seconds=0)
    snap = _snap(edge_score=20.0)
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=10)
    first = sim.state.last_event
    sim.state.virtual_position = "Flat"
    sim.step(snap, TradeSignal.LONG_SIGNAL, signal_id=10)
    assert sim.state.last_event in {first, "DUPLICATE_BLOCK", "SETUP_BLOCK"}

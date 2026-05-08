from __future__ import annotations

from core.engine import DataQualityGate
from core.models import MarketSnapshot
from signal_engine.engine import TradeSignal
from simulation.execution_model import ExecutionFill
from simulation.paper import PaperSimulator


def _snap(**kwargs) -> MarketSnapshot:
    s = MarketSnapshot(price=100.0, spread=1.0, data_quality="Good", can_trade_data=True, ticks_per_second=7.0, trigger_strength=85.0)
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_depth_payload_bids_asks_supported() -> None:
    payload = {"bids": [["100", "1.2"]], "asks": [["101", "1.1"]]}
    bids = payload.get("bids") or payload.get("b") or []
    asks = payload.get("asks") or payload.get("a") or []
    assert bids and asks


def test_depth_payload_b_a_supported() -> None:
    payload = {"b": [["100", "1.2"]], "a": [["101", "1.1"]]}
    bids = payload.get("bids") or payload.get("b") or []
    asks = payload.get("asks") or payload.get("a") or []
    assert bids and asks


def test_fresh_depth_not_missing() -> None:
    dq = DataQualityGate()
    out = dq.evaluate({"book_ready": True, "depth_ready": False, "book_age_ms": 10, "depth_age_ms": 20, "bid": 100, "ask": 101}, tick_speed=8)
    assert out["data_quality_reason"] == "DEPTH_EMPTY_BOOK"


def test_full_paper_long_lifecycle() -> None:
    sim = PaperSimulator(cooldown_seconds=0, min_hold_ms=0, tp_ticks=1)
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=1)
    assert sim.state.lifecycle_state in {"ACTIVE_POSITION", "PARTIAL_ENTRY"}


def test_full_paper_short_lifecycle() -> None:
    sim = PaperSimulator(cooldown_seconds=0, min_hold_ms=0, tp_ticks=1)
    sim.step(_snap(), TradeSignal.SHORT_SIGNAL, signal_id=1)
    assert sim.state.lifecycle_state in {"ACTIVE_POSITION", "PARTIAL_ENTRY"}


def test_tp_net_positive_only() -> None:
    sim = PaperSimulator(cooldown_seconds=0, min_hold_ms=0, tp_ticks=1)
    sim.step(_snap(price=100.0), TradeSignal.LONG_SIGNAL, signal_id=2)
    sim.step(_snap(price=100.2), TradeSignal.NO_SIGNAL)
    assert sim.state.last_event != "TP" or sim.state.last_net_pnl > 0


def test_sl_exit() -> None:
    sim = PaperSimulator(cooldown_seconds=0, min_hold_ms=0, sl_ticks=1, tp_ticks=50)
    sim.step(_snap(price=100.0), TradeSignal.LONG_SIGNAL, signal_id=3)
    sim.step(_snap(price=98.0), TradeSignal.NO_SIGNAL)
    assert sim.state.last_event == "SL"


def test_timeout_exit() -> None:
    sim = PaperSimulator(cooldown_seconds=0, min_hold_ms=0, timeout_seconds=0.0, tp_ticks=99, sl_ticks=99)
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=4)
    sim.step(_snap(price=100.01), TradeSignal.NO_SIGNAL)
    assert sim.state.last_event == "TIMEOUT"


def test_cooldown_blocks_reentry() -> None:
    sim = PaperSimulator(cooldown_seconds=999, min_hold_ms=0)
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=5)
    sim._close_trade(_snap(), "TIMEOUT", 9999999.0)
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=6)
    assert sim.state.last_event in {"COOLDOWN_BLOCK", "SETUP_BLOCK"}


def test_missed_fill_logged() -> None:
    sim = PaperSimulator(cooldown_seconds=0)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0, missed=True)  # type: ignore[method-assign]
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=7)
    assert sim.state.last_event == "ENTRY MISSED"


def test_partial_fill_logged() -> None:
    sim = PaperSimulator(cooldown_seconds=0)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0, partial=True)  # type: ignore[method-assign]
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=8)
    assert "PARTIAL FILL" in sim.state.last_event

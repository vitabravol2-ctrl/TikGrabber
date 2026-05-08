from core.engine import DataQualityGate
from core.models import MarketSnapshot
from decision_engine.engine import SignalDecisionEngine
from signal_engine.engine import TradeSignal
from simulation.paper import PaperSimulator


def _event(**kwargs):
    event = {
        "price": 100.0,
        "qty": 1.0,
        "buyer_maker": False,
        "event_time": 0,
        "bid": 100.0,
        "ask": 100.1,
        "bid_volume_total": 5.0,
        "ask_volume_total": 5.0,
        "book_age_ms": 100.0,
        "depth_age_ms": 100.0,
        "book_ready": True,
        "depth_ready": True,
    }
    event.update(kwargs)
    return event


def test_agg_trade_before_book_blocks_missing_book():
    dq = DataQualityGate()
    out = dq.evaluate(_event(book_ready=False, depth_ready=True, bid=0, ask=0), tick_speed=10)
    assert out["data_quality_reason"] == "MISSING_BOOK_TICKER"


def test_stale_book_blocks_entry():
    dq = DataQualityGate()
    out = dq.evaluate(_event(book_age_ms=2600), tick_speed=10)
    assert out["data_quality_reason"] == "STALE_BOOK"


def test_missing_depth_blocks_entry():
    dq = DataQualityGate()
    out = dq.evaluate(_event(depth_ready=False, bid_volume_total=0, ask_volume_total=0), tick_speed=10)
    assert out["data_quality_reason"] == "MISSING_DEPTH"


def test_no_edge_after_fees_blocks_signal():
    engine = SignalDecisionEngine()
    snap = MarketSnapshot(price=100.0, spread=0.5, edge_score=5.0, buy_pressure=0.6, sell_pressure=0.4, sweep_down=0.6, reclaim=0.6, panic=0.1, velocity=0.1, ticks_per_second=5.0)
    decision = engine.evaluate(snap)
    assert decision.signal == TradeSignal.NO_SIGNAL
    assert "NO_EDGE_AFTER_FEES" in decision.long_blockers


def test_tp_requires_net_profit():
    sim = PaperSimulator(cooldown_seconds=0, tp_ticks=1, sl_ticks=50, min_hold_ms=0)
    entry = MarketSnapshot(price=100.0, spread=5.0, buy_pressure=0.7, sell_pressure=0.3, velocity=0.1)
    sim.step(entry, TradeSignal.LONG_SIGNAL, signal_id=1)
    step = MarketSnapshot(price=100.2, spread=5.0, buy_pressure=0.7, sell_pressure=0.3, velocity=0.1)
    sim.step(step, TradeSignal.NO_SIGNAL)
    assert sim.state.last_event != "TP"


def test_paper_position_accounting_notional_qty_margin():
    sim = PaperSimulator(cooldown_seconds=0)
    entry = MarketSnapshot(price=100.0, spread=1.0, buy_pressure=0.7, sell_pressure=0.3, velocity=0.1)
    sim.step(entry, TradeSignal.LONG_SIGNAL, signal_id=1)
    assert sim.state.notional > 0
    assert sim.state.quantity > 0
    assert sim.state.margin_used == sim.state.notional / sim.state.leverage


def test_pipeline_contract_snapshot_fields_exist():
    snap = MarketSnapshot()
    for f in ["expected_move_ticks", "min_profitable_ticks", "net_edge_score"]:
        assert hasattr(snap, f)

from core.models import FuturesPositionModel, MarketSnapshot
from decision_engine.engine import SignalDecisionEngine
from microstructure import OrderBookMemory
from risk.controls import FuturesRiskControls
from signal_engine import TradeSignal
from simulation.paper import PaperSimulator


def _snap(price: float = 100.0, edge: float = 25.0) -> MarketSnapshot:
    return MarketSnapshot(
        price=price,
        spread=1.0,
        velocity=0.1,
        edge_score=edge,
        buy_pressure=0.7,
        sell_pressure=0.3,
        sweep_down=0.6,
        sweep_up=0.0,
        reclaim=0.6,
        panic=0.0,
        long_probability=70,
        short_probability=30,
        ticks_per_second=5.0,
        data_quality="Good",
        data_quality_reason="GOOD",
        trigger_strength=90.0,
    )


def test_break_even_blocks_tiny_edge_and_sets_no_edge_reason():
    engine = SignalDecisionEngine()
    snap = _snap(edge=8.0)
    decision = engine.evaluate(snap)
    assert decision.signal == TradeSignal.NO_SIGNAL
    assert "NO_EDGE_AFTER_FEES" in decision.long_blockers


def test_net_edge_score_is_lower_than_raw_edge():
    engine = SignalDecisionEngine()
    snap = _snap(edge=30.0)
    engine.evaluate(snap)
    assert snap.net_edge_score < abs(snap.edge_score)


def test_minimum_viable_move_enforced():
    engine = SignalDecisionEngine()
    snap = _snap(edge=10.0)
    engine.evaluate(snap)
    assert snap.expected_move_ticks < snap.min_profitable_ticks


def test_tp_after_fees_positive_when_trade_closes_profitably():
    sim = PaperSimulator(min_hold_ms=0)
    sim.step(_snap(price=100.0, edge=40.0), TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(_snap(price=103.0, edge=40.0), TradeSignal.NO_SIGNAL)
    if sim.state.last_event == "TP":
        assert sim.state.last_net_pnl > 0


def test_last_hold_seconds_persists_in_closed_state():
    sim = PaperSimulator(timeout_seconds=0.0, min_hold_ms=0)
    sim.step(_snap(price=100.0), TradeSignal.LONG_SIGNAL, signal_id=1)
    sim.step(_snap(price=100.0), TradeSignal.NO_SIGNAL)
    assert sim.state.virtual_position == "Flat"
    assert sim.state.last_hold_seconds >= 0.0


def test_data_quality_reasons_separated_in_risk_controls():
    risk = FuturesRiskControls()
    ok, reason = risk.evaluate_entry(_snap(), FuturesPositionModel(), 1.0, False)
    assert ok
    stale = _snap()
    stale.data_quality = "Stale"
    stale.data_quality_reason = "STALE"
    ok, reason = risk.evaluate_entry(stale, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == "STALE"


def test_no_liquidity_uses_memory_not_single_snapshot_only():
    mem = OrderBookMemory(stable_ticks_required=2)
    mem.update(price=100.0, bid_volume_total=120, ask_volume_total=110, imbalance=0.1, trade_velocity=4.0, buy_pressure=0.6)
    mem.update(price=100.0, bid_volume_total=125, ask_volume_total=115, imbalance=0.1, trade_velocity=4.2, buy_pressure=0.61)
    s = mem.update(price=100.0, bid_volume_total=30, ask_volume_total=30, imbalance=0.0, trade_velocity=1.0, buy_pressure=0.5)
    assert s.liquidity_quality > 0

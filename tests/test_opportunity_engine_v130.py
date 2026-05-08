from core.models import FuturesPositionModel, MarketSnapshot
from core.opportunity_engine import RealOpportunityEngine
from risk.controls import FuturesRiskControls


def _base_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        price=100000,
        spread=1.0,
        velocity=1.2,
        buy_pressure=0.65,
        sell_pressure=0.35,
        sweep_up=0.7,
        trap=0.6,
        reclaim=0.2,
        edge_stability="STABLE",
        net_edge_score=40,
        ticks_per_second=8,
        noise_level="LOW",
        market_phase="BREAKOUT",
        market_regime="BUY_PRESSURE",
        reversal_probability=30,
        exhaustion_score=20,
        late_entry_risk="LOW",
        late_move_penalty=0.1,
        required_move_usdt=0.005,
        signal_quality="A",
        can_trade_data=True,
        data_quality_reason="GOOD",
        book_status="OK",
        depth_status="OK",
        trigger_strength=90,
        expected_move_ticks=6,
        min_profitable_ticks=1,
    )


def test_low_opportunity_blocked():
    risk = FuturesRiskControls()
    snap = _base_snapshot()
    snap.opportunity_score = 15
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == "LOW_OPPORTUNITY"


def test_continuation_opportunity_allowed():
    risk = FuturesRiskControls()
    snap = _base_snapshot()
    opp = RealOpportunityEngine().evaluate(snap, 100)
    snap.opportunity_score = opp.opportunity_score
    snap.continuation_strength = opp.continuation_strength
    snap.impulse_probability = opp.impulse_probability
    snap.microstructure_state = opp.microstructure_state
    snap.liquidation_potential = opp.liquidation_potential
    snap.real_opportunity = True
    snap.expected_move_usdt_real = 0.4
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert ok and reason == "PASS"


def test_dead_market_rejected():
    risk = FuturesRiskControls()
    snap = _base_snapshot()
    snap.market_regime = "DEAD_MARKET"
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == "DEAD_MARKET"


def test_trapped_shorts_increases_move():
    eng = RealOpportunityEngine()
    snap = _base_snapshot()
    snap.trap = 0.2
    a = eng.evaluate(snap, 100).expected_move_ticks_real
    snap.trap = 0.9
    snap.buy_pressure = 0.75
    snap.sell_pressure = 0.25
    b = eng.evaluate(snap, 100).expected_move_ticks_real
    assert b > a


def test_exhaustion_lowers_move():
    eng = RealOpportunityEngine()
    snap = _base_snapshot()
    low = eng.evaluate(snap, 100).expected_move_ticks_real
    snap.exhaustion_score = 90
    high = eng.evaluate(snap, 100).expected_move_ticks_real
    assert high < low


def test_reversal_risk_blocks_scalp_continuation():
    risk = FuturesRiskControls()
    snap = _base_snapshot()
    snap.opportunity_score = 80
    snap.continuation_strength = 70
    snap.impulse_probability = 70
    snap.microstructure_state = "CASCADE_SETUP"
    snap.liquidation_potential = 70
    snap.real_opportunity = True
    snap.expected_move_usdt_real = 1
    snap.reversal_probability = 80
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == "REVERSAL_RISK"


def test_expected_move_real_above_required():
    snap = _base_snapshot()
    opp = RealOpportunityEngine().evaluate(snap, 100)
    assert opp.expected_move_usdt_real > snap.required_move_usdt


def test_breakout_energy_increases_opportunity():
    eng = RealOpportunityEngine()
    snap = _base_snapshot()
    base = eng.evaluate(snap, 100).opportunity_score
    snap.sweep_up = 1.0
    snap.ticks_per_second = 12
    boosted = eng.evaluate(snap, 100).opportunity_score
    assert boosted > base


def test_micro_chop_rejected():
    risk = FuturesRiskControls()
    snap = _base_snapshot()
    snap.opportunity_score = 80
    snap.continuation_strength = 70
    snap.impulse_probability = 70
    snap.microstructure_state = "MICRO_RANGE_CHOP"
    snap.liquidation_potential = 70
    snap.real_opportunity = True
    snap.expected_move_usdt_real = 1
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == "MICRO_CHOP"


def test_cascade_setup_increases_score():
    eng = RealOpportunityEngine()
    snap = _base_snapshot()
    normal = eng.evaluate(snap, 100).opportunity_score
    snap.trap = 0.95
    snap.sweep_up = 1.0
    snap.ticks_per_second = 15
    boosted = eng.evaluate(snap, 100).opportunity_score
    assert boosted > normal


def test_strong_buy_pressure_opportunity_high():
    eng = RealOpportunityEngine()
    snap = _base_snapshot()
    snap.market_regime = "BUY_PRESSURE"
    snap.signal_quality = "A"
    snap.noise_level = "LOW"
    snap.net_edge_score = 72
    out = eng.evaluate(snap, 100)
    assert out.opportunity_score >= 50


def test_liquidity_trap_opportunity_high():
    eng = RealOpportunityEngine()
    snap = _base_snapshot()
    snap.market_regime = "LIQUIDITY_TRAP"
    snap.signal_quality = "A"
    snap.noise_level = "LOW"
    snap.net_edge_score = 78
    snap.trap = 0.9
    out = eng.evaluate(snap, 100)
    assert out.opportunity_score >= 60


def test_dead_market_opportunity_low():
    eng = RealOpportunityEngine()
    snap = _base_snapshot()
    snap.market_regime = "DEAD_MARKET"
    out = eng.evaluate(snap, 100)
    assert 0 <= out.opportunity_score <= 20


def test_real_move_exceeds_required_when_strong():
    eng = RealOpportunityEngine()
    snap = _base_snapshot()
    snap.market_regime = "SWEEP_HUNT"
    snap.signal_quality = "A"
    snap.noise_level = "LOW"
    snap.net_edge_score = 82
    snap.sweep_up = 0.95
    out = eng.evaluate(snap, 100)
    assert out.expected_move_ticks_real >= 5
    assert out.expected_move_usdt_real >= snap.required_move_usdt * 1.5


def test_book_conflict_not_blocking_with_fresh_bookticker():
    risk = FuturesRiskControls()
    snap = _base_snapshot()
    snap.book_status = "OK"
    snap.depth_status = "OK"
    snap.data_quality_reason = "GOOD"
    snap.real_opportunity = True
    snap.opportunity_score = 70
    snap.continuation_strength = 70
    snap.impulse_probability = 70
    snap.microstructure_state = "CASCADE_SETUP"
    snap.liquidation_potential = 70
    snap.expected_move_usdt_real = snap.required_move_usdt * 2.0
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert ok and reason == "PASS"

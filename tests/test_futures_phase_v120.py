from core.futures_costs import FuturesCostModel
from core.market_phase import MarketPhaseEngine
from core.models import MarketSnapshot, FuturesPositionModel
from risk.controls import FuturesRiskControls


def test_futures_fee_model_applied():
    c = FuturesCostModel()
    net, gross = c.net_profit_usdt(1000.0, 30.0)
    assert gross > net
    assert c.round_trip_cost_bps() > 0


def test_no_real_profit_blocks_trade():
    risk = FuturesRiskControls()
    snap = MarketSnapshot(signal_quality='A', noise_level='LOW', edge_stability='STABLE', market_regime='BUY_PRESSURE', expected_move_ticks=5, min_profitable_ticks=1, net_edge_score=40, spread=1, velocity=0.1, ticks_per_second=10, trigger_strength=90, can_trade_data=True, data_quality_reason='GOOD', book_status='OK', depth_status='OK', net_expected_profit_after_costs=-1, expected_move_usdt=10)
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == 'NO_REAL_PROFIT'


def test_exhaustion_detected_after_pressure_decay():
    p = MarketPhaseEngine()
    out = None
    for i in range(12):
        out = p.update(regime='BUY_PRESSURE', edge=80-i, buy_pressure=0.8-(i*0.03), sell_pressure=0.2, trap=0.6, sweep=0.6, reclaim=0.2, velocity=0.02 if i>8 else 0.4, spread=3.2)
    assert out.exhaustion_score > 60


def test_reversal_probability_rises_after_trap():
    p = MarketPhaseEngine()
    out = p.update(regime='BUY_PRESSURE', edge=70, buy_pressure=0.75, sell_pressure=0.2, trap=0.9, sweep=0.8, reclaim=0.1, velocity=0.01, spread=3.5)
    assert out.reversal_probability > 60


def test_late_entry_penalty_blocks_chasing():
    risk = FuturesRiskControls()
    snap = MarketSnapshot(signal_quality='A', noise_level='LOW', edge_stability='STABLE', market_regime='BUY_PRESSURE', expected_move_ticks=5, min_profitable_ticks=1, net_edge_score=40, spread=1, velocity=0.1, ticks_per_second=10, trigger_strength=90, can_trade_data=True, data_quality_reason='GOOD', book_status='OK', depth_status='OK', net_expected_profit_after_costs=10, expected_move_usdt=50, late_entry_risk='HIGH', late_move_penalty=0.8)
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == 'LATE_ENTRY_RISK_HIGH'


def test_reversal_setup_generated():
    p = MarketPhaseEngine()
    out = p.update(regime='BUY_PRESSURE', edge=85, buy_pressure=0.9, sell_pressure=0.1, trap=0.95, sweep=0.9, reclaim=0.1, velocity=0.01, spread=4.0)
    assert out.reversal_setup


def test_real_profit_after_costs_visible():
    snap = MarketSnapshot(expected_move_usdt=42, net_expected_profit_after_costs=18)
    assert snap.expected_move_usdt == 42
    assert snap.net_expected_profit_after_costs == 18

from core.futures_costs import FuturesCostModel
from core.models import MarketSnapshot, FuturesPositionModel
from risk.controls import FuturesRiskControls
from simulation.paper import PaperSimulator


def test_fee_calculated_from_notional_not_margin():
    c = FuturesCostModel()
    b = c.calculate(notional_usdt=100.0, expected_move_usdt=0.0, spread_usdt=0.0)
    assert b.round_trip_fee > 0


def test_bnb_discount_applied():
    c1 = FuturesCostModel(bnb_discount_enabled=True)
    c2 = FuturesCostModel(bnb_discount_enabled=False)
    b1 = c1.calculate(notional_usdt=100.0, expected_move_usdt=0.0, spread_usdt=0.0)
    b2 = c2.calculate(notional_usdt=100.0, expected_move_usdt=0.0, spread_usdt=0.0)
    assert b1.round_trip_fee < b2.round_trip_fee
    assert b1.bnb_discount > 0


def test_maker_taker_fee_mode():
    c = FuturesCostModel()
    mm = c.calculate(notional_usdt=100.0, expected_move_usdt=0.0, spread_usdt=0.0, fee_mode="MAKER_MAKER")
    mt = c.calculate(notional_usdt=100.0, expected_move_usdt=0.0, spread_usdt=0.0, fee_mode="MAKER_TAKER")
    tt = c.calculate(notional_usdt=100.0, expected_move_usdt=0.0, spread_usdt=0.0, fee_mode="TAKER_TAKER")
    assert mm.round_trip_fee <= mt.round_trip_fee <= tt.round_trip_fee


def test_required_move_includes_fees_slippage_spread():
    c = FuturesCostModel()
    b = c.calculate(notional_usdt=100.0, expected_move_usdt=0.0, spread_usdt=0.2)
    assert b.required_gross_move_usdt > (b.round_trip_fee + b.slippage_cost)


def test_one_tick_btcusdt_not_profitable():
    c = FuturesCostModel()
    b = c.calculate(notional_usdt=100.0, expected_move_usdt=0.1, spread_usdt=0.0)
    assert b.net_profit_after_costs < 0


def test_dynamic_tp_above_required_move():
    sim = PaperSimulator(cooldown_seconds=0, min_hold_ms=0)
    snap = MarketSnapshot(price=100000, spread=0.1, velocity=0.1, ticks_per_second=10, signal_quality="A", noise_level="LOW", edge_stability="STABLE", required_move_ticks=3.0)
    sim.scalp.tp_mode = "DYNAMIC_REQUIRED_MOVE"
    sim._open_position(snap, type("S", (), {"LONG_SIGNAL": object(), "NO_SIGNAL": object()}).LONG_SIGNAL, 0.0)
    assert sim.scalp.tp_ticks >= 3.0


def test_no_real_profit_message_has_exp_and_req():
    risk = FuturesRiskControls()
    snap = MarketSnapshot(signal_quality='A', noise_level='LOW', edge_stability='STABLE', market_regime='BUY_PRESSURE', expected_move_ticks=5, min_profitable_ticks=1, net_edge_score=40, spread=1, velocity=0.1, ticks_per_second=10, trigger_strength=90, can_trade_data=True, data_quality_reason='GOOD', book_status='OK', depth_status='OK', net_expected_profit_after_costs=-1, expected_move_usdt=0.01, required_move_usdt=0.06)
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == 'NO_REAL_PROFIT'


def test_conservative_profile_uses_dynamic_tp():
    sim = PaperSimulator()
    sim.apply_profile("CONSERVATIVE_FUTURES")
    assert sim.scalp.tp_mode == "DYNAMIC_REQUIRED_MOVE"

from core.models import FuturesPositionModel, MarketSnapshot
from risk.controls import FuturesRiskControls
from simulation.paper import PaperSimulator


def _snap(**kwargs) -> MarketSnapshot:
    s = MarketSnapshot(
        price=100000.0,
        spread=1.0,
        ticks_per_second=10.0,
        signal_quality="A",
        noise_level="LOW",
        edge_stability="STABLE",
        can_trade_data=True,
        data_quality_reason="GOOD",
        book_status="OK",
        depth_status="OK",
        trigger_strength=90.0,
        opportunity_score=75.0,
        expected_move_usdt_real=120.0,
        required_move_usdt=80.0,
        market_phase="TREND",
        market_regime="BUY_PRESSURE",
        best_direction="LONG",
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_realistic_profile_defaults() -> None:
    sim = PaperSimulator()
    sim.apply_profile("REALISTIC_FUTURES_1000")
    assert sim.scalp.budget_usdt == 1000
    assert sim.scalp.leverage == 3
    assert sim.scalp.max_notional_usdt == 3000
    assert sim.scalp.order_notional_usdt == 1000


def test_position_size_from_risk_and_sl() -> None:
    sim = PaperSimulator()
    sim.apply_profile("REALISTIC_FUTURES_1000")
    n, qty, risk = sim.calculate_position_size(entry_price=100000, sl_move_usdt=50)
    assert n == 3000
    assert qty > 0
    assert risk <= sim.scalp.max_loss_per_trade_usdt + 1e-6


def test_notional_capped_by_leverage() -> None:
    sim = PaperSimulator()
    sim.apply_profile("REALISTIC_FUTURES_1000")
    n, _, _ = sim.calculate_position_size(entry_price=100000, sl_move_usdt=10)
    assert n <= sim.scalp.budget_usdt * sim.scalp.leverage


def test_tp_sl_price_move_long() -> None:
    sim = PaperSimulator()
    tp, sl = sim.compute_tp_sl_prices(100000, "Long", 80, 45)
    assert tp == 100080
    assert sl == 99955


def test_tp_sl_price_move_short() -> None:
    sim = PaperSimulator()
    tp, sl = sim.compute_tp_sl_prices(100000, "Short", 80, 45)
    assert tp == 99920
    assert sl == 100045


def test_rr_minimum_enforced() -> None:
    sim = PaperSimulator()
    assert sim.enforce_rr(tp_move=60, sl_move=50) >= 1.3


def test_continuation_entry_3_of_5_allows() -> None:
    risk = FuturesRiskControls()
    snap = _snap(continuation_strength=70, impulse_probability=70, trapped_liquidity_score=70)
    ok, _ = risk.evaluate_entry(snap, FuturesPositionModel(side='FLAT'), 1.0, False, profile="REALISTIC_FUTURES_1000")
    assert ok


def test_reversal_entry_3_of_5_allows() -> None:
    risk = FuturesRiskControls()
    snap = _snap(best_direction="SHORT", market_phase="DISTRIBUTION", trap_score=70, exhaustion_score=75, reversal_probability=80, acceleration_score=10)
    ok, _ = risk.evaluate_entry(snap, FuturesPositionModel(side='FLAT'), 1.0, False, profile="REALISTIC_FUTURES_1000")
    assert ok


def test_strong_b_allowed_in_realistic_profile() -> None:
    risk = FuturesRiskControls()
    snap = _snap(signal_quality="B", opportunity_score=80, net_edge_score=45, buy_pressure=0.7, impulse_probability=70, trapped_liquidity_score=70)
    ok, _ = risk.evaluate_entry(snap, FuturesPositionModel(side='FLAT'), 1.0, False, profile="REALISTIC_FUTURES_1000")
    assert ok


def test_daily_loss_limit_blocks() -> None:
    sim = PaperSimulator()
    sim.apply_profile("REALISTIC_FUTURES_1000")
    sim.state.realized_pnl = -21.0
    ok, reason = sim._can_take_signal(_snap())
    assert not ok and reason == "DAILY_LOSS_LIMIT"

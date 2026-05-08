from core.engine import DataQualityGate
from core.models import MarketSnapshot
from risk.controls import FuturesRiskControls
from signal_engine import TradeSignal
from simulation.execution_model import ExecutionFill
from simulation.paper import PaperSimulator
from ws.binance_ws import BinanceFeedWorker


def _snap(**kwargs):
    s = MarketSnapshot(
        price=100.0,
        spread=1.0,
        velocity=0.1,
        trigger_strength=80.0,
        can_trade_data=True,
        data_quality_reason="GOOD",
        signal_quality="A",
        noise_level="LOW",
        edge_stability="STABLE",
        expected_move_ticks=5.0,
        min_profitable_ticks=2.0,
        net_edge_score=30.0,
        smoothed_edge_score=30.0,
        ticks_per_second=8.0,
        book_status="OK_FALLBACK",
        depth_status="OK",
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_fallback_book_allows_trade_when_depth_fresh():
    gate = DataQualityGate()
    out = gate.evaluate({"book_ready": True, "depth_ready": True, "book_status": "ok_fallback", "book_age_ms": -1.0, "depth_age_ms": 40.0, "bid": 100.0, "ask": 100.1}, tick_speed=6)
    assert out["can_trade_data"] is True


def test_fallback_book_is_warning_not_blocker():
    rc = FuturesRiskControls()
    ok, reason = rc.evaluate_entry(_snap(), position=type("P", (), {"side": "FLAT", "initial_margin": 0.0, "liquidation_distance_pct": 99.0})(), requested_leverage=1.0, cooldown_active=False)
    assert ok and reason == "PASS"


def test_price_source_depth_fallback_visible():
    worker = BinanceFeedWorker()
    worker._on_message(None, '{"stream":"btcusdt@depth20@100ms","data":{"bids":[["100.1","1"]],"asks":[["100.2","1"]]}}')
    got = {}
    worker.market_event.connect(lambda e: got.update(e))
    worker._on_message(None, '{"stream":"btcusdt@aggTrade","data":{"p":"100.1","q":"0.1","m":false,"E":1}}')
    assert got["price_source"] == "DEPTH_FALLBACK"


def test_scalp_config_visible_in_snapshot():
    sim = PaperSimulator()
    sim.step(_snap(), TradeSignal.NO_SIGNAL)
    assert "PROFILE" in sim.state.scalp_summary and "ORDER" in sim.state.scalp_summary


def test_order_notional_used_by_router():
    sim = PaperSimulator(default_notional_usdt=150.0)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=10)
    assert sim.state.notional == 150.0


def test_tp_sl_from_config_used_by_sim():
    sim = PaperSimulator(tp_ticks=3, sl_ticks=4, cooldown_seconds=0, timeout_seconds=999, min_hold_ms=0)
    sim.execution.entry_fill = lambda **_: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.execution.exit_fill = lambda *args, **kwargs: ExecutionFill(side="Long", price=100.0, fee_paid=0.0)  # type: ignore
    sim.step(_snap(), TradeSignal.LONG_SIGNAL, signal_id=11)
    sim.step(_snap(price=100.31), TradeSignal.NO_SIGNAL)
    assert sim.state.last_close_reason == "TP"

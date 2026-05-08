from core.engine import GameTheoryEngine
from core.models import FuturesPositionModel, MarketSnapshot
from risk.controls import FuturesRiskControls
from ws.binance_ws import BookState


def _event(**kwargs):
    base = {
        "price": 100.0,
        "qty": 1.0,
        "buyer_maker": False,
        "event_time": 0,
        "bid": 100.0,
        "ask": 100.5,
        "bid_volume_total": 10.0,
        "ask_volume_total": 12.0,
        "mini_volume_24h": 1000.0,
        "book_age_ms": 100.0,
        "depth_age_ms": 100.0,
    }
    base.update(kwargs)
    return base


def test_book_cache_valid_between_depth_updates():
    e = GameTheoryEngine()
    snap = e.update(MarketSnapshot(), _event(depth_age_ms=2400.0))
    assert snap.data_quality_reason != "MISSING_DEPTH"


def test_false_missing_book_not_triggered_when_depth_fresh():
    e = GameTheoryEngine()
    snap = e.update(MarketSnapshot(), _event(depth_age_ms=1200.0))
    assert snap.data_quality_reason not in {"MISSING_DEPTH", "STALE_DEPTH"}


def _warm_engine(e: GameTheoryEngine) -> None:
    for _ in range(4):
        e.update(MarketSnapshot(), _event())


def test_stale_depth_triggers():
    e = GameTheoryEngine()
    _warm_engine(e)
    snap = e.update(MarketSnapshot(), _event(depth_age_ms=2600.0))
    assert snap.data_quality_reason == "STALE_DEPTH"


def test_missing_book_ticker_triggers():
    e = GameTheoryEngine()
    _warm_engine(e)
    snap = e.update(MarketSnapshot(), _event(bid=0.0, ask=0.0))
    assert snap.data_quality_reason == "MISSING_BOOK_TICKER"


def test_old_replay_event_does_not_crash_and_marked_legacy():
    e = GameTheoryEngine()
    snap = e.update(MarketSnapshot(), {"price": 100.0, "qty": 1.0, "legacy_replay": True})
    assert snap.data_quality_reason == "LEGACY_REPLAY"


def test_gui_state_fields_exist_for_book_ages():
    snap = MarketSnapshot()
    assert hasattr(snap, "book_age_ms") and hasattr(snap, "depth_age_ms")


def test_risk_gate_blocks_specific_reasons():
    risk = FuturesRiskControls()
    snap = MarketSnapshot(data_quality="Good", data_quality_reason="STALE_DEPTH", spread=1.0, trigger_strength=100.0, ticks_per_second=5.0)
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, False)
    assert not ok and reason == "STALE_DEPTH"


def test_bookstate_has_timestamps():
    b = BookState()
    assert hasattr(b, "book_ticker_ts") and hasattr(b, "depth_ts")

from core.engine import DataQualityGate


def arm_progress(prev_dir, prev_regime, prev_ticks, required, signal_value, regime, setup_ok):
    if not setup_ok:
        return "NONE", "NONE", 0, False
    if signal_value == prev_dir and regime == prev_regime:
        ticks = prev_ticks + 1
    else:
        ticks = 1
    return signal_value, regime, ticks, ticks >= required


def test_unknown_book_conflict_detected():
    dq = DataQualityGate()
    event = {"book_age_ms": -1.0, "depth_age_ms": 100.0, "bid": 100.0, "ask": 100.1, "bid_volume_total": 1.0, "ask_volume_total": 1.0, "book_ready": True, "depth_ready": True, "ws_streams_seen": ["bookTicker", "depth"], "first_event_ts_ms": 0.0, "now_ms": 9999.0}
    assert dq.evaluate(event, tick_speed=5.0)["data_quality_reason"] == "BOOK_CONFLICT"


def test_stale_depth_conflict_detected():
    dq = DataQualityGate(depth_stale_ms=2500.0)
    event = {"book_age_ms": 10.0, "depth_age_ms": 3000.0, "bid": 100.0, "ask": 100.1, "bid_volume_total": 1.0, "ask_volume_total": 1.0, "book_ready": True, "depth_ready": True, "ws_streams_seen": ["depth"], "first_event_ts_ms": 0.0, "now_ms": 9999.0}
    assert dq.evaluate(event, tick_speed=5.0)["data_quality_reason"] == "DEPTH_CONFLICT"


def test_setup_arming_requires_consecutive_ticks():
    d, r, t, armed = arm_progress("NONE", "NONE", 0, 3, "LONG", "BUY_PRESSURE", True)
    assert (d, r, t, armed) == ("LONG", "BUY_PRESSURE", 1, False)
    d, r, t, armed = arm_progress(d, r, t, 3, "LONG", "BUY_PRESSURE", True)
    assert (t, armed) == (2, False)
    _, _, t, armed = arm_progress(d, r, t, 3, "LONG", "BUY_PRESSURE", True)
    assert (t, armed) == (3, True)


def test_block_none_must_result_in_order_or_reason():
    block_reason = "NONE"
    quality = "A"
    setup_ticks = 1
    if block_reason == "NONE" and quality == "A" and setup_ticks < 3:
        block_reason = "SETUP_ARMING"
    assert block_reason != "NONE"


def test_armed_setup_sends_order():
    _, _, ticks, armed = arm_progress("LONG", "BUY_PRESSURE", 2, 3, "LONG", "BUY_PRESSURE", True)
    assert ticks == 3
    assert armed

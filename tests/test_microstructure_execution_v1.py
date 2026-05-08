from microstructure import OrderBookMemory
from replay.engine import ReplayState
from simulation.execution_model import ExecutionModel


def test_wall_persistence_memory_and_pull_detection():
    mem = OrderBookMemory(wall_threshold=1.2, stable_ticks_required=2)
    s1 = mem.update(price=100.0, bid_volume_total=100, ask_volume_total=100, imbalance=0.0, trade_velocity=4.0, buy_pressure=0.5)
    s2 = mem.update(price=100.0, bid_volume_total=160, ask_volume_total=100, imbalance=0.2, trade_velocity=4.0, buy_pressure=0.45)
    s3 = mem.update(price=100.01, bid_volume_total=170, ask_volume_total=100, imbalance=0.2, trade_velocity=3.8, buy_pressure=0.35)
    s4 = mem.update(price=100.01, bid_volume_total=60, ask_volume_total=100, imbalance=-0.1, trade_velocity=3.0, buy_pressure=0.35)
    assert s3.stable_bid_wall
    assert s4.liquidity_pull == "LIQUIDITY_PULL_BID"


def test_absorption_and_exhaustion_detection():
    mem = OrderBookMemory(wall_threshold=1.1, stable_ticks_required=2)
    mem.update(price=100.00, bid_volume_total=180, ask_volume_total=100, imbalance=0.4, trade_velocity=6.0, buy_pressure=0.30)
    mem.update(price=100.01, bid_volume_total=190, ask_volume_total=100, imbalance=0.4, trade_velocity=6.2, buy_pressure=0.31)
    a = mem.update(price=100.00, bid_volume_total=185, ask_volume_total=100, imbalance=0.35, trade_velocity=5.8, buy_pressure=0.32)
    mem.update(price=100.00, bid_volume_total=170, ask_volume_total=100, imbalance=0.30, trade_velocity=3.0, buy_pressure=0.62)
    e = mem.update(price=100.00, bid_volume_total=160, ask_volume_total=100, imbalance=0.10, trade_velocity=1.5, buy_pressure=0.55)
    assert a.absorption in {"SELL_ABSORPTION", "NONE"}
    assert e.exhaustion != "NONE"


def test_queue_delay_and_slippage_depend_on_volatility():
    model = ExecutionModel(tick_size=1.0, slippage_ticks=1)
    calm = model.entry_fill("Long", price=100.0, spread=1.0, volatility=1.0, liquidity=0.9, aggression=0.5)
    fast = model.entry_fill("Long", price=100.0, spread=1.0, volatility=14.0, liquidity=0.3, aggression=0.9)
    assert fast.queue_delay_ms > calm.queue_delay_ms
    assert fast.slippage_paid > calm.slippage_paid
    assert fast.execution_quality < calm.execution_quality


def test_replay_analytics_fields_exist():
    state = ReplayState()
    assert state.best_liquidity_state == "N/A"
    assert state.worst_liquidity_state == "N/A"

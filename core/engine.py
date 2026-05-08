from __future__ import annotations

from time import time

from core.models import MarketSnapshot
from game_theory.engine import GameTheoryModule
from market_state.fsm import MarketState, MarketStateEngine
from metrics.microstructure import MicrostructureTracker


class GameTheoryEngine:
    def __init__(self) -> None:
        self._tracker = MicrostructureTracker()
        self._state_engine = MarketStateEngine()
        self._gt = GameTheoryModule()

    def update(self, snapshot: MarketSnapshot, event: dict) -> MarketSnapshot:
        now = time()
        price = float(event.get("price", 0.0))
        qty = float(event.get("qty", 0.0))
        buyer_maker = bool(event.get("buyer_maker", False))

        self._tracker.update_trade(price, qty, buyer_maker)
        m = self._tracker.calculate(
            bid=float(event.get("bid", 0.0)),
            ask=float(event.get("ask", 0.0)),
            bid_volume_total=float(event.get("bid_volume_total", 0.0)),
            ask_volume_total=float(event.get("ask_volume_total", 0.0)),
            mini_volume_24h=float(event.get("mini_volume_24h", 0.0)),
        )

        price_delta = price - snapshot.price if snapshot.price else 0.0
        state = self._state_engine.detect(m, price_delta)
        sig = self._gt.evaluate(m, state)

        snapshot.price = price
        snapshot.spread = m.spread
        snapshot.velocity = price_delta
        snapshot.buy_pressure = m.aggressive_buy_pressure
        snapshot.sell_pressure = m.aggressive_sell_pressure
        snapshot.sweep_up = 1.0 if state == MarketState.SWEEP_UP else 0.0
        snapshot.sweep_down = 1.0 if state == MarketState.SWEEP_DOWN else 0.0
        snapshot.reclaim = 1.0 if state == MarketState.RECLAIM else 0.0
        snapshot.trap = 1.0 if state == MarketState.TRAP else 0.2 if sig.trap_probability > 50 else 0.0
        snapshot.panic = 1.0 if state in {MarketState.PANIC_BUY, MarketState.PANIC_SELL} else 0.0
        snapshot.long_probability = sig.long_pressure
        snapshot.short_probability = sig.short_pressure
        snapshot.market_intent = state.value
        snapshot.edge_score = sig.edge_score
        snapshot.trap_probability = sig.trap_probability
        snapshot.volume_24h = m.mini_volume_24h
        snapshot.latency_ms = max(0.0, time() * 1000.0 - float(event.get("event_time", 0)))
        snapshot.ticks_per_second = m.tick_speed
        snapshot.data_quality = "Good" if m.tick_speed >= 4 else "Warmup"
        snapshot.ws_status = "Live"
        snapshot.timestamp = now
        return snapshot

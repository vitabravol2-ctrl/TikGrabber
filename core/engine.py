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
        impulse = abs(price_delta) / max(0.1, m.spread)
        sweep_score = min(1.0, (m.volume_burst * 0.45) + (min(1.0, impulse / 2.0) * 0.35) + (m.liquidity_shift * 0.2))
        snapshot.sweep_up = sweep_score if price_delta > 0 else 0.0
        snapshot.sweep_down = sweep_score if price_delta < 0 else 0.0

        reclaim_flow = 1.0 - min(1.0, abs(m.order_book_imbalance))
        reclaim_stability = m.spread_compression
        reclaim_score = min(1.0, reclaim_flow * 0.5 + reclaim_stability * 0.3 + (1.0 - min(1.0, m.volume_burst)) * 0.2)
        snapshot.reclaim = reclaim_score if state in {MarketState.RECLAIM, MarketState.BUY_PRESSURE, MarketState.SELL_PRESSURE} else reclaim_score * 0.6

        trap_score = min(1.0, m.volume_burst * 0.4 + min(1.0, abs(m.order_book_imbalance) * 2.0) * 0.35 + m.liquidity_shift * 0.25)
        snapshot.trap = max(trap_score, sig.trap_probability / 100.0)
        snapshot.panic = min(1.0, m.spread_widening * 0.5 + min(1.0, m.local_volatility / 2.2) * 0.5)
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

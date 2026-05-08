from __future__ import annotations

from collections import deque
from time import time

from core.models import MarketSnapshot


class GameTheoryEngine:
    def __init__(self) -> None:
        self._prices: deque[tuple[float, float]] = deque(maxlen=120)
        self._spreads: deque[float] = deque(maxlen=80)
        self._ticks: deque[float] = deque(maxlen=300)
        self._last_trade_ts = 0.0

    def update(
        self,
        snapshot: MarketSnapshot,
        *,
        price: float,
        bid: float,
        ask: float,
        buyer_maker: bool,
        event_time_ms: int,
        depth_imbalance: float,
    ) -> MarketSnapshot:
        now = time()
        self._ticks.append(now)
        spread = max(0.0, ask - bid)

        self._prices.append((now, price))
        self._spreads.append(spread)

        velocity = 0.0
        if len(self._prices) >= 2:
            t0, p0 = self._prices[0]
            dt = max(1e-4, now - t0)
            velocity = (price - p0) / dt

        buy_tick = 0.35 if not buyer_maker else -0.35
        pressure = min(1.0, max(0.0, 0.5 + depth_imbalance * 0.35 + buy_tick))

        delta = price - snapshot.price if snapshot.price else 0.0
        sweep_up = self._decay(snapshot.sweep_up, 0.91) + (0.3 if delta > spread * 2.0 and spread > 0 else 0)
        sweep_down = self._decay(snapshot.sweep_down, 0.91) + (0.3 if delta < -spread * 2.0 and spread > 0 else 0)

        trap_raw = abs(pressure - 0.5) * 2 * (0.4 if delta * velocity < 0 else 0.15)
        trap = min(1.0, self._decay(snapshot.trap, 0.9) + trap_raw)

        reclaim = min(1.0, self._decay(snapshot.reclaim, 0.88) + (0.25 if abs(delta) < spread * 0.8 and spread > 0 else 0))

        spread_mean = sum(self._spreads) / len(self._spreads) if self._spreads else spread
        panic_boost = 0.35 if spread > spread_mean * 1.8 and spread > 0 else 0.0
        panic = min(1.0, self._decay(snapshot.panic, 0.85) + panic_boost)

        long_probability = min(100.0, max(0.0, 50.0 + (pressure - 0.5) * 95.0 - panic * 25.0 + reclaim * 15.0))
        short_probability = 100.0 - long_probability

        edge_score = min(100.0, max(-100.0, (long_probability - short_probability) + (sweep_up - sweep_down) * 35.0))

        if panic > 0.65:
            intent = "Compression"
        elif sweep_up > 0.6 and trap > 0.35:
            intent = "Bull Trap"
        elif sweep_down > 0.6 and trap > 0.35:
            intent = "Bear Trap"
        elif abs(edge_score) > 40:
            intent = "Expansion"
        else:
            intent = "Neutral"

        alive_ticks = [t for t in self._ticks if now - t <= 1.0]
        self._ticks = deque(alive_ticks, maxlen=300)

        snapshot.price = price
        snapshot.spread = spread
        snapshot.velocity = velocity
        snapshot.buy_pressure = pressure
        snapshot.sell_pressure = 1 - pressure
        snapshot.sweep_up = min(1.0, sweep_up)
        snapshot.sweep_down = min(1.0, sweep_down)
        snapshot.trap = trap
        snapshot.reclaim = reclaim
        snapshot.panic = panic
        snapshot.long_probability = long_probability
        snapshot.short_probability = short_probability
        snapshot.market_intent = intent
        snapshot.edge_score = edge_score
        snapshot.latency_ms = max(0.0, (time() * 1000.0) - float(event_time_ms))
        snapshot.ticks_per_second = float(len(self._ticks))
        snapshot.data_quality = "Good" if len(self._ticks) >= 4 else "Warmup"
        snapshot.ws_status = "Live"
        snapshot.timestamp = now
        self._last_trade_ts = now
        return snapshot

    @staticmethod
    def _decay(value: float, factor: float) -> float:
        return max(0.0, value * factor)

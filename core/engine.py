from __future__ import annotations

from time import time

from core.models import MarketSnapshot
from game_theory.engine import GameTheoryModule
from market_state.fsm import MarketState, MarketStateEngine
from metrics.microstructure import MicrostructureTracker


class GameTheoryEngine:
    DEPTH_STALE_MS = 2500.0
    BOOK_STALE_MS = 2500.0

    def __init__(self) -> None:
        self._tracker = MicrostructureTracker()
        self._state_engine = MarketStateEngine()
        self._gt = GameTheoryModule()


    def _data_quality(self, event: dict, tick_speed: float) -> tuple[str, str, str, str, float, float]:
        if bool(event.get("legacy_replay", False)):
            return "Legacy", "LEGACY_REPLAY", "Missing", "Missing", float(event.get("book_age_ms", 0.0) or 0.0), float(event.get("depth_age_ms", 0.0) or 0.0)

        book_age_ms = float(event.get("book_age_ms", 1e9) or 1e9)
        depth_age_ms = float(event.get("depth_age_ms", 1e9) or 1e9)
        bid = float(event.get("bid", 0.0))
        ask = float(event.get("ask", 0.0))
        bid_vol = float(event.get("bid_volume_total", 0.0))
        ask_vol = float(event.get("ask_volume_total", 0.0))

        if tick_speed < 2:
            return "Warmup", "WARMUP_TRADES", "Missing", "Missing", book_age_ms, depth_age_ms
        if bid <= 0 or ask <= 0:
            return "BookMissing", "MISSING_BOOK_TICKER", "Missing", "Missing" if bid_vol <= 0 or ask_vol <= 0 else "OK", book_age_ms, depth_age_ms
        if book_age_ms >= self.BOOK_STALE_MS:
            return "Stale", "STALE_BOOK", "Stale", "OK" if bid_vol > 0 and ask_vol > 0 else "Missing", book_age_ms, depth_age_ms
        if bid_vol <= 0 or ask_vol <= 0:
            return "BookMissing", "MISSING_DEPTH", "OK", "Missing", book_age_ms, depth_age_ms
        if depth_age_ms >= self.DEPTH_STALE_MS:
            return "Stale", "STALE_DEPTH", "OK", "Stale", book_age_ms, depth_age_ms
        if tick_speed < 4:
            return "Unstable", "WS_UNSTABLE", "OK", "OK", book_age_ms, depth_age_ms
        return "Good", "GOOD", "OK", "OK", book_age_ms, depth_age_ms

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
        data_quality, quality_reason, book_status, depth_status, book_age_ms, depth_age_ms = self._data_quality(event, m.tick_speed)
        snapshot.data_quality = data_quality
        snapshot.data_quality_reason = quality_reason
        snapshot.book_status = book_status
        snapshot.depth_status = depth_status
        snapshot.book_age_ms = book_age_ms
        snapshot.depth_age_ms = depth_age_ms
        snapshot.ws_status = "Live"
        snapshot.timestamp = now
        return snapshot

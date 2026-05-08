from __future__ import annotations

from time import time

from core.models import MarketSnapshot
from game_theory.engine import GameTheoryModule
from market_state.fsm import MarketState, MarketStateEngine
from metrics.microstructure import MicrostructureTracker


class DataQualityGate:
    def __init__(self, book_stale_ms: float = 2500.0, depth_stale_ms: float = 2500.0) -> None:
        self.book_stale_ms = book_stale_ms
        self.depth_stale_ms = depth_stale_ms

    def evaluate(self, event: dict, tick_speed: float) -> dict:
        if bool(event.get("legacy_replay", False)):
            return {"data_quality": "Legacy", "data_quality_reason": "LEGACY_REPLAY", "book_status": "Missing", "depth_status": "Missing", "book_age_ms": float(event.get("book_age_ms", 0.0) or 0.0), "depth_age_ms": float(event.get("depth_age_ms", 0.0) or 0.0), "can_trade_data": True}
        book_age_ms = float(event.get("book_age_ms", 1e9) or 1e9)
        depth_age_ms = float(event.get("depth_age_ms", 1e9) or 1e9)
        bid = float(event.get("bid", 0.0))
        ask = float(event.get("ask", 0.0))
        bid_vol = float(event.get("bid_volume_total", 0.0))
        ask_vol = float(event.get("ask_volume_total", 0.0))
        book_ready = bool(event.get("book_ready", bid > 0 and ask > 0))
        depth_ready = bool(event.get("depth_ready", bid_vol > 0 and ask_vol > 0))
        if not book_ready:
            return {"data_quality": "BookMissing", "data_quality_reason": "MISSING_BOOK_TICKER", "book_status": "Missing", "depth_status": "OK" if depth_ready else "Missing", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if not depth_ready:
            return {"data_quality": "BookMissing", "data_quality_reason": "MISSING_DEPTH", "book_status": "OK", "depth_status": "Missing", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if book_age_ms >= self.book_stale_ms:
            return {"data_quality": "Stale", "data_quality_reason": "STALE_BOOK", "book_status": "Stale", "depth_status": "OK", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if depth_age_ms >= self.depth_stale_ms:
            return {"data_quality": "Stale", "data_quality_reason": "STALE_DEPTH", "book_status": "OK", "depth_status": "Stale", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if tick_speed < 2:
            return {"data_quality": "Warmup", "data_quality_reason": "WARMUP_TRADES", "book_status": "OK", "depth_status": "OK", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if tick_speed < 4:
            return {"data_quality": "Unstable", "data_quality_reason": "WS_UNSTABLE", "book_status": "OK", "depth_status": "OK", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": True}
        return {"data_quality": "Good", "data_quality_reason": "GOOD", "book_status": "OK", "depth_status": "OK", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": True}


class GameTheoryEngine:
    DEPTH_STALE_MS = 2500.0
    BOOK_STALE_MS = 2500.0

    def __init__(self) -> None:
        self._tracker = MicrostructureTracker()
        self._state_engine = MarketStateEngine()
        self._gt = GameTheoryModule()
        self._dq = DataQualityGate(self.BOOK_STALE_MS, self.DEPTH_STALE_MS)

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
        dq = self._dq.evaluate(event, m.tick_speed)
        snapshot.data_quality = dq["data_quality"]
        snapshot.data_quality_reason = dq["data_quality_reason"]
        snapshot.book_status = dq["book_status"]
        snapshot.depth_status = dq["depth_status"]
        snapshot.book_age_ms = dq["book_age_ms"]
        snapshot.depth_age_ms = dq["depth_age_ms"]
        snapshot.ws_status = "Live"
        snapshot.timestamp = now
        return snapshot

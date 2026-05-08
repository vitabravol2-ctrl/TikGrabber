from __future__ import annotations

from time import time

from core.models import MarketSnapshot
from game_theory.engine import GameTheoryModule
from market_state.fsm import MarketState, MarketStateEngine
from metrics.microstructure import MicrostructureTracker


class DataQualityGate:
    def __init__(self, book_stale_ms: float = 2500.0, depth_stale_ms: float = 2500.0, book_warmup_grace_ms: float = 3000.0) -> None:
        self.book_stale_ms = book_stale_ms
        self.depth_stale_ms = depth_stale_ms
        self.book_warmup_grace_ms = book_warmup_grace_ms

    def evaluate(self, event: dict, tick_speed: float) -> dict:
        if bool(event.get("legacy_replay", False)):
            return {"data_quality": "Legacy", "data_quality_reason": "LEGACY_REPLAY", "book_status": "Missing", "depth_status": "Missing", "book_age_ms": float(event.get("book_age_ms", 0.0) or 0.0), "depth_age_ms": float(event.get("depth_age_ms", 0.0) or 0.0), "can_trade_data": True}
        raw_book_age = float(event.get("book_age_ms", -1.0) or -1.0)
        book_age_ms = raw_book_age if raw_book_age >= 0 else -1.0
        depth_age_ms = float(event.get("depth_age_ms", 1e9) or 1e9)
        bid = float(event.get("bid", 0.0))
        ask = float(event.get("ask", 0.0))
        bid_vol = float(event.get("bid_volume_total", 0.0))
        ask_vol = float(event.get("ask_volume_total", 0.0))
        book_ready = bool(event.get("book_ready", bid > 0 and ask > 0))
        depth_ready_flag = event.get("depth_ready")
        depth_ready = bool(depth_ready_flag) if depth_ready_flag is not None else (depth_age_ms < self.depth_stale_ms or (bid_vol > 0 and ask_vol > 0))
        first_seen_ms = float(event.get("first_event_ts_ms", 0.0) or 0.0)
        now_ms = float(event.get("now_ms", 0.0) or 0.0)
        warmup_elapsed = max(0.0, now_ms - first_seen_ms) if first_seen_ms > 0 and now_ms > 0 else self.book_warmup_grace_ms + 1.0
        if not book_ready:
            return {"data_quality": "BookMissing", "data_quality_reason": "MISSING_BOOK_TICKER", "book_status": "Missing", "depth_status": "OK" if depth_ready else "Missing", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if str(event.get("book_status", "")).lower() == "ok_fallback":
            return {"data_quality": "Good", "data_quality_reason": "GOOD", "book_status": "OK_FALLBACK", "depth_status": "OK" if depth_ready else "Missing", "book_age_ms": depth_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": depth_ready}
        streams_seen = {str(s).lower() for s in event.get("ws_streams_seen", [])}
        if book_age_ms < 0 and "bookticker" in streams_seen and book_ready:
            return {"data_quality": "BookMissing", "data_quality_reason": "BOOK_CONFLICT", "book_status": "Unknown", "depth_status": "OK" if depth_ready else "Missing", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if book_age_ms < 0:
            if warmup_elapsed <= self.book_warmup_grace_ms:
                return {"data_quality": "Warmup", "data_quality_reason": "WARMUP_BOOK", "book_status": "Warmup", "depth_status": "OK" if depth_ready else "Missing", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
            return {"data_quality": "BookMissing", "data_quality_reason": "UNKNOWN_BOOK", "book_status": "Unknown", "depth_status": "OK" if depth_ready else "Missing", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if not depth_ready:
            reason = "DEPTH_EMPTY_BOOK" if depth_age_ms < self.depth_stale_ms else "MISSING_DEPTH"
            return {"data_quality": "BookMissing", "data_quality_reason": reason, "book_status": "OK", "depth_status": "Missing", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if book_age_ms >= self.book_stale_ms:
            return {"data_quality": "Stale", "data_quality_reason": "STALE_BOOK", "book_status": "Stale", "depth_status": "OK", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
        if depth_age_ms >= self.depth_stale_ms and "depth" in streams_seen and depth_ready:
            return {"data_quality": "Stale", "data_quality_reason": "DEPTH_CONFLICT", "book_status": "OK", "depth_status": "Stale", "book_age_ms": book_age_ms, "depth_age_ms": depth_age_ms, "can_trade_data": False}
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
        self._edge_ema = 0.0
        self._trap_cooldown_until = 0.0
        self._prev_imbalance = 0.0

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

        aggressive_failed = m.volume_burst > 0.55 and impulse > 0.9 and abs(price_delta) < m.spread * 0.5
        reclaim_failed = snapshot.reclaim < 0.45
        liquidity_pull = m.liquidity_shift > 0.35
        imbalance_flipped = (self._prev_imbalance * m.order_book_imbalance) < 0
        velocity_collapsed = abs(price_delta) < max(0.1, m.spread * 0.25)
        trap_score = min(
            1.0,
            (0.28 if aggressive_failed else 0.0)
            + (0.2 if reclaim_failed else 0.0)
            + (0.2 if liquidity_pull else 0.0)
            + (0.17 if imbalance_flipped else 0.0)
            + (0.15 if velocity_collapsed else 0.0),
        )
        trap_allowed = now >= self._trap_cooldown_until and trap_score > 0.72
        snapshot.trap = max(trap_score, sig.trap_probability / 100.0) if trap_allowed else min(0.34, trap_score)
        if trap_allowed:
            self._trap_cooldown_until = now + 2.5
        self._prev_imbalance = m.order_book_imbalance
        snapshot.panic = min(1.0, m.spread_widening * 0.5 + min(1.0, m.local_volatility / 2.2) * 0.5)
        snapshot.long_probability = sig.long_pressure
        snapshot.short_probability = sig.short_pressure
        snapshot.market_intent = state.value
        snapshot.edge_score = sig.edge_score
        self._edge_ema = (sig.edge_score * 0.2) + (self._edge_ema * 0.8)
        snapshot.smoothed_edge_score = self._edge_ema
        snapshot.market_regime = state.value
        edge_delta = abs(snapshot.edge_score - snapshot.smoothed_edge_score)
        snapshot.edge_stability = "STABLE" if edge_delta < 10.0 else "UNSTABLE"
        noise_score = (min(1.0, edge_delta / 35.0) * 0.5) + (min(1.0, m.local_volatility / 2.0) * 0.3) + (m.volume_burst * 0.2)
        snapshot.noise_level = "LOW" if noise_score < 0.35 else ("MID" if noise_score < 0.62 else "HIGH")
        quality_points = 0
        quality_points += 2 if snapshot.edge_stability == "STABLE" else 0
        quality_points += 1 if snapshot.noise_level == "LOW" else 0
        quality_points += 1 if m.spread < 2.5 else 0
        quality_points += 1 if snapshot.can_trade_data else 0
        quality_points += 1 if abs(snapshot.smoothed_edge_score) > 18 else 0
        quality_points -= 2 if snapshot.trap > 0.55 else 0
        snapshot.signal_quality = "A" if quality_points >= 5 else ("B" if quality_points >= 3 else ("C" if quality_points >= 1 else "D"))
        snapshot.no_trade_zone = (
            state.value in {"DEAD_MARKET", "COMPRESSION"}
            or snapshot.edge_stability == "UNSTABLE"
            or snapshot.noise_level == "HIGH"
            or snapshot.signal_quality in {"C", "D"}
        )
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
        snapshot.can_trade_data = dq["can_trade_data"]
        snapshot.price_source = str(event.get("price_source", "BOOKTICKER"))
        snapshot.ws_status = "Live"
        snapshot.timestamp = now
        return snapshot

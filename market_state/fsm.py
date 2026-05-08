from __future__ import annotations

from enum import Enum
from time import time

from metrics.microstructure import MicrostructureMetrics


class MarketState(str, Enum):
    BALANCED = "BALANCED"
    BUY_PRESSURE = "BUY_PRESSURE"
    SELL_PRESSURE = "SELL_PRESSURE"
    SWEEP_UP = "SWEEP_UP"
    SWEEP_DOWN = "SWEEP_DOWN"
    RECLAIM = "RECLAIM"
    TRAP = "TRAP"
    PANIC_BUY = "PANIC_BUY"
    PANIC_SELL = "PANIC_SELL"
    COMPRESSION = "COMPRESSION"
    EXPANSION = "EXPANSION"
    TRENDING = "TRENDING"
    SWEEP_HUNT = "SWEEP_HUNT"
    LIQUIDITY_TRAP = "LIQUIDITY_TRAP"
    ABSORPTION = "ABSORPTION"
    BREAKOUT_BUILDUP = "BREAKOUT_BUILDUP"
    DEAD_MARKET = "DEAD_MARKET"
    REVERSAL_ATTEMPT = "REVERSAL_ATTEMPT"


class MarketStateEngine:
    def __init__(self, min_state_seconds: float = 1.5, min_ticks_confirm: int = 3) -> None:
        self._state = MarketState.BALANCED
        self._candidate = MarketState.BALANCED
        self._candidate_ticks = 0
        self._last_switch_ts = 0.0
        self._min_state_seconds = min_state_seconds
        self._min_ticks_confirm = min_ticks_confirm

    def detect(self, m: MicrostructureMetrics, price_delta: float) -> MarketState:
        proposed = self._detect_candidate(m, price_delta)
        now = time()
        if proposed == self._state:
            self._candidate = proposed
            self._candidate_ticks = 0
            return self._state

        if proposed != self._candidate:
            self._candidate = proposed
            self._candidate_ticks = 1
            return self._state

        self._candidate_ticks += 1
        if (now - self._last_switch_ts) < self._min_state_seconds:
            return self._state
        if self._candidate_ticks < self._min_ticks_confirm:
            return self._state

        self._state = proposed
        self._last_switch_ts = now
        self._candidate_ticks = 0
        return self._state

    def _detect_candidate(self, m: MicrostructureMetrics, price_delta: float) -> MarketState:
        if m.spread_widening > 0.55 and m.local_volatility > 1.6:
            return MarketState.EXPANSION
        if (
            m.spread_compression > 0.6
            and m.local_volatility < 0.45
            and abs(m.order_book_imbalance) < 0.08
            and m.tick_speed < 6.0
        ):
            return MarketState.COMPRESSION

        impulse = abs(price_delta) / max(0.1, m.spread)
        if m.volume_burst > 0.55 and m.tick_speed > 4.5 and impulse > 1.0 and m.liquidity_shift > 0.2:
            return MarketState.SWEEP_HUNT

        if m.volume_burst > 0.6 and m.liquidity_shift > 0.35 and abs(m.order_book_imbalance) > 0.18 and impulse < 0.8:
            return MarketState.LIQUIDITY_TRAP
        if m.spread_compression > 0.45 and m.volume_burst < 0.45 and abs(m.order_book_imbalance) < 0.12:
            return MarketState.ABSORPTION
        if m.spread_compression > 0.5 and m.volume_burst > 0.45 and m.local_volatility < 0.9:
            return MarketState.BREAKOUT_BUILDUP

        if m.aggressive_sell_pressure > 0.7 and m.local_volatility > 1.35:
            return MarketState.PANIC_SELL
        if m.aggressive_buy_pressure > 0.7 and m.local_volatility > 1.35:
            return MarketState.PANIC_BUY
        if abs(m.order_book_imbalance) > 0.22 and m.local_volatility > 0.8 and impulse < 0.7:
            return MarketState.REVERSAL_ATTEMPT
        if m.tick_speed < 3.0 and m.local_volatility < 0.25 and m.volume_burst < 0.2:
            return MarketState.DEAD_MARKET
        if abs(price_delta) > m.spread and max(m.aggressive_buy_pressure, m.aggressive_sell_pressure) > 0.58:
            return MarketState.TRENDING
        if m.aggressive_buy_pressure > 0.57:
            return MarketState.BUY_PRESSURE
        if m.aggressive_sell_pressure > 0.57:
            return MarketState.SELL_PRESSURE
        return MarketState.BALANCED

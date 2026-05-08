from __future__ import annotations

from enum import Enum

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


class MarketStateEngine:
    def detect(self, m: MicrostructureMetrics, price_delta: float) -> MarketState:
        if m.spread_widening > 0.45 and m.local_volatility > 1.3:
            return MarketState.EXPANSION
        if m.spread_compression > 0.45 and m.local_volatility < 0.5:
            return MarketState.COMPRESSION
        if m.volume_burst > 0.75 and price_delta > m.spread * 1.8:
            return MarketState.SWEEP_UP
        if m.volume_burst > 0.75 and price_delta < -m.spread * 1.8:
            return MarketState.SWEEP_DOWN
        if m.aggressive_sell_pressure > 0.62 and price_delta > -m.spread * 0.5:
            return MarketState.RECLAIM
        if m.aggressive_buy_pressure > 0.62 and m.order_book_imbalance < -0.2:
            return MarketState.TRAP
        if m.aggressive_sell_pressure > 0.66 and m.local_volatility > 1.2:
            return MarketState.PANIC_SELL
        if m.aggressive_buy_pressure > 0.66 and m.local_volatility > 1.2:
            return MarketState.PANIC_BUY
        if m.aggressive_buy_pressure > 0.57:
            return MarketState.BUY_PRESSURE
        if m.aggressive_sell_pressure > 0.57:
            return MarketState.SELL_PRESSURE
        return MarketState.BALANCED

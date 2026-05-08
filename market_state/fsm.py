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
        if m.spread_widening > 0.55 and m.local_volatility > 1.6:
            return MarketState.EXPANSION
        if m.spread_compression > 0.5 and m.local_volatility < 0.45:
            return MarketState.COMPRESSION

        impulse = abs(price_delta) / max(0.1, m.spread)
        if m.volume_burst > 0.55 and m.tick_speed > 4.5 and impulse > 1.0 and m.liquidity_shift > 0.2:
            return MarketState.SWEEP_UP if price_delta > 0 else MarketState.SWEEP_DOWN

        if m.aggressive_sell_pressure > 0.56 and price_delta >= -m.spread * 0.7 and m.spread_compression > 0.2:
            return MarketState.RECLAIM
        if m.aggressive_buy_pressure > 0.56 and price_delta <= m.spread * 0.7 and m.spread_compression > 0.2:
            return MarketState.RECLAIM

        if m.volume_burst > 0.6 and m.liquidity_shift > 0.35 and abs(m.order_book_imbalance) > 0.18:
            return MarketState.TRAP

        if m.aggressive_sell_pressure > 0.7 and m.local_volatility > 1.35:
            return MarketState.PANIC_SELL
        if m.aggressive_buy_pressure > 0.7 and m.local_volatility > 1.35:
            return MarketState.PANIC_BUY
        if m.aggressive_buy_pressure > 0.57:
            return MarketState.BUY_PRESSURE
        if m.aggressive_sell_pressure > 0.57:
            return MarketState.SELL_PRESSURE
        return MarketState.BALANCED

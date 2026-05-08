from __future__ import annotations

from dataclasses import dataclass

from market_state.fsm import MarketState
from metrics.microstructure import MicrostructureMetrics


@dataclass
class GameTheorySignal:
    long_pressure: float
    short_pressure: float
    trap_probability: float
    edge_score: float


class GameTheoryModule:
    def evaluate(self, metrics: MicrostructureMetrics, state: MarketState) -> GameTheorySignal:
        long_p = 50.0 + metrics.order_book_imbalance * 35.0 + (metrics.aggressive_buy_pressure - 0.5) * 45.0
        short_p = 50.0 - metrics.order_book_imbalance * 35.0 + (metrics.aggressive_sell_pressure - 0.5) * 45.0

        if state in {MarketState.SWEEP_DOWN, MarketState.SWEEP_UP, MarketState.TRAP}:
            trap = min(100.0, 35.0 + metrics.volume_burst * 45.0 + metrics.liquidity_shift * 20.0)
        else:
            trap = min(100.0, metrics.liquidity_shift * 60.0 + metrics.spread_widening * 20.0)

        long_p = max(0.0, min(100.0, long_p))
        short_p = max(0.0, min(100.0, short_p))
        edge = max(-100.0, min(100.0, long_p - short_p - trap * 0.2))
        return GameTheorySignal(long_pressure=long_p, short_pressure=short_p, trap_probability=trap, edge_score=edge)

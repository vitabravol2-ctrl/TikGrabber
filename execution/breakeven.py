from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass
class BreakEvenModel:
    tick_size: float = 0.10
    fee_rate: float = 0.0004
    slippage_ticks: float = 0.8
    spread_ticks: float = 0.3
    execution_penalty_ticks: float = 0.2
    minimum_net_profit_ticks: float = 0.2
    minimum_viable_move_ticks: int = 2

    def min_profitable_ticks(self) -> int:
        # round-trip fees are converted to ticks using 1x notional price move.
        fee_ticks = (self.fee_rate * 2.0) / max(self.tick_size, 1e-9)
        total = fee_ticks + self.slippage_ticks + self.spread_ticks + self.execution_penalty_ticks + self.minimum_net_profit_ticks
        return max(self.minimum_viable_move_ticks, int(ceil(total)))

    def net_edge_score(self, raw_edge: float) -> float:
        return raw_edge - float(self.min_profitable_ticks())

    def has_edge_after_costs(self, expected_move_ticks: float) -> bool:
        return expected_move_ticks >= self.min_profitable_ticks()

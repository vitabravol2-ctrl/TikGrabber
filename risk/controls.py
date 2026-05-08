from __future__ import annotations

from dataclasses import dataclass

from core.models import FuturesPositionModel


@dataclass
class FuturesRiskControls:
    """Risk guardrails placeholder for futures workflow expansion."""

    max_leverage: float = 3.0
    min_liquidation_buffer_pct: float = 2.5

    def leverage_allowed(self, requested: float) -> bool:
        return requested <= self.max_leverage

    def liquidation_buffer_ok(self, position: FuturesPositionModel) -> bool:
        return position.liquidation_distance_pct >= self.min_liquidation_buffer_pct

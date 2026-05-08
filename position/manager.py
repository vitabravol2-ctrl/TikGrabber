from __future__ import annotations

from dataclasses import dataclass, field

from core.models import FuturesPositionModel


@dataclass
class PositionManager:
    """Maintains a futures position model for strategy/UI integration."""

    position: FuturesPositionModel = field(default_factory=FuturesPositionModel)

    def update_mark(self, mark_price: float) -> None:
        self.position.mark_price = mark_price

    def set_side(self, side: str) -> None:
        self.position.side = side.upper()

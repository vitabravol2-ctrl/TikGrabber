from __future__ import annotations

from dataclasses import dataclass, field

from core.models import FuturesPositionModel


@dataclass
class PositionManager:
    """Paper-only futures position manager."""

    position: FuturesPositionModel = field(default_factory=FuturesPositionModel)
    realized_pnl_total: float = 0.0

    def open_position(self, symbol: str, side: str, entry_price: float, quantity: float, leverage: float) -> None:
        side = side.upper()
        if side not in {"LONG", "SHORT"}:
            raise ValueError("side must be LONG/SHORT")
        if entry_price <= 0 or quantity <= 0 or leverage <= 0:
            raise ValueError("entry, quantity, leverage must be positive")

        notional = entry_price * quantity
        margin = notional / leverage
        self.position.symbol = symbol
        self.position.side = side
        self.position.entry_price = entry_price
        self.position.mark_price = entry_price
        self.position.quantity = quantity
        self.position.leverage = leverage
        self.position.notional_value = notional
        self.position.initial_margin = margin
        self.position.maintenance_margin = margin * 0.5
        self.position.unrealized_pnl = 0.0
        self.position.liquidation_price = self._estimate_liq_price(entry_price, side, leverage)
        self.position.liquidation_distance_pct = self._liq_distance_pct(entry_price)

    def close_position(self, exit_price: float) -> float:
        if self.position.side == "FLAT" or exit_price <= 0:
            return 0.0
        direction = 1.0 if self.position.side == "LONG" else -1.0
        pnl = (exit_price - self.position.entry_price) * self.position.quantity * direction
        self.realized_pnl_total += pnl
        self.position = FuturesPositionModel(symbol=self.position.symbol)
        return pnl

    def update_mark(self, mark_price: float) -> None:
        if mark_price <= 0:
            return
        self.position.mark_price = mark_price
        if self.position.side == "FLAT":
            return
        direction = 1.0 if self.position.side == "LONG" else -1.0
        self.position.unrealized_pnl = (mark_price - self.position.entry_price) * self.position.quantity * direction
        self.position.notional_value = mark_price * self.position.quantity
        self.position.initial_margin = self.position.notional_value / max(1.0, self.position.leverage)
        self.position.liquidation_distance_pct = self._liq_distance_pct(mark_price)

    def snapshot(self) -> dict[str, float | str]:
        return {
            "symbol": self.position.symbol,
            "side": self.position.side,
            "entry_price": self.position.entry_price,
            "mark_price": self.position.mark_price,
            "quantity": self.position.quantity,
            "leverage": self.position.leverage,
            "notional": self.position.notional_value,
            "margin_used": self.position.initial_margin,
            "unrealized_pnl": self.position.unrealized_pnl,
            "realized_pnl": self.realized_pnl_total,
            "liquidation_price": self.position.liquidation_price,
            "liquidation_distance_pct": self.position.liquidation_distance_pct,
        }

    def _estimate_liq_price(self, entry_price: float, side: str, leverage: float) -> float:
        buffer = 1.0 / leverage
        return entry_price * (1.0 - buffer) if side == "LONG" else entry_price * (1.0 + buffer)

    def _liq_distance_pct(self, mark_price: float) -> float:
        liq = self.position.liquidation_price
        if liq <= 0 or mark_price <= 0:
            return 0.0
        return abs(mark_price - liq) / mark_price * 100.0

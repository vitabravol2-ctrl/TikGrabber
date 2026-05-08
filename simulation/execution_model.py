from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionFill:
    side: str
    price: float
    fee_paid: float


class ExecutionModel:
    def __init__(
        self,
        tick_size: float = 0.10,
        slippage_ticks: int = 1,
        maker_fee: float = 0.0002,
        taker_fee: float = 0.0004,
        use_taker: bool = True,
    ) -> None:
        self.tick_size = tick_size
        self.slippage_ticks = slippage_ticks
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.use_taker = use_taker

    @property
    def slippage(self) -> float:
        return self.slippage_ticks * self.tick_size

    @property
    def fee_rate(self) -> float:
        return self.taker_fee if self.use_taker else self.maker_fee

    def bid_ask(self, price: float, spread: float) -> tuple[float | None, float | None]:
        if price <= 0 or spread <= 0:
            return None, None
        half = spread / 2.0
        bid = price - half
        ask = price + half
        if bid <= 0 or ask <= 0:
            return None, None
        return bid, ask

    def entry_fill(self, direction: str, price: float, spread: float) -> ExecutionFill | None:
        bid, ask = self.bid_ask(price, spread)
        if bid is None or ask is None:
            return None
        if direction == "Long":
            fill_price = ask + self.slippage
        else:
            fill_price = bid - self.slippage
        fee = fill_price * self.fee_rate
        return ExecutionFill(side=direction, price=fill_price, fee_paid=fee)

    def exit_fill(self, direction: str, price: float, spread: float) -> ExecutionFill | None:
        bid, ask = self.bid_ask(price, spread)
        if bid is None or ask is None:
            return None
        if direction == "Long":
            fill_price = bid - self.slippage
        else:
            fill_price = ask + self.slippage
        fee = fill_price * self.fee_rate
        return ExecutionFill(side=direction, price=fill_price, fee_paid=fee)

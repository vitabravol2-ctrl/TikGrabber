from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionFill:
    side: str
    price: float
    fee_paid: float
    queue_delay_ms: float = 0.0
    partial: bool = False
    missed: bool = False
    slippage_paid: float = 0.0
    execution_quality: float = 100.0


class ExecutionModel:
    def __init__(self, tick_size: float = 0.10, slippage_ticks: int = 1, maker_fee: float = 0.0002, taker_fee: float = 0.0004, use_taker: bool = True) -> None:
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

    def _market_penalty(self, spread: float, volatility: float, liquidity: float, aggression: float) -> tuple[float, float, bool, bool]:
        fast = volatility > 9.0 or aggression > 0.75
        queue_delay = min(800.0, 40.0 + volatility * 25.0 + spread * 30.0 + max(0.0, (1.0 - liquidity)) * 200.0)
        partial = queue_delay > 260.0 or liquidity < 0.35
        missed = fast and liquidity < 0.2
        slip_inputs = max(0.0, volatility / 8.0) + max(0.0, aggression - 0.6) + max(0.0, 0.7 - liquidity)
        slip_mult = 1.0 + min(2.4, slip_inputs)
        if fast:
            slip_mult *= 1.35
        return queue_delay, slip_mult, partial, missed

    def _quality(self, queue_delay_ms: float, slip_paid: float, spread: float, missed: bool) -> float:
        if missed:
            return 0.0
        delay_pen = min(35.0, queue_delay_ms / 22.0)
        slip_pen = min(45.0, slip_paid / max(self.tick_size, 1e-6) * 6.0)
        spread_pen = min(20.0, spread * 6.0)
        return max(1.0, 100.0 - delay_pen - slip_pen - spread_pen)

    def entry_fill(self, direction: str, price: float, spread: float, volatility: float = 0.0, liquidity: float = 1.0, aggression: float = 0.5) -> ExecutionFill | None:
        bid, ask = self.bid_ask(price, spread)
        if bid is None or ask is None:
            return None
        qd, slip_mult, partial, missed = self._market_penalty(spread, volatility, liquidity, aggression)
        side_px = ask if direction == "Long" else bid
        signed_slippage = self.slippage * slip_mult
        fill_price = side_px + signed_slippage if direction == "Long" else side_px - signed_slippage
        fee = fill_price * self.fee_rate
        quality = self._quality(qd, signed_slippage, spread, missed)
        return ExecutionFill(side=direction, price=fill_price, fee_paid=fee, queue_delay_ms=qd, partial=partial, missed=missed, slippage_paid=signed_slippage, execution_quality=quality)

    def exit_fill(self, direction: str, price: float, spread: float, volatility: float = 0.0, liquidity: float = 1.0, aggression: float = 0.5) -> ExecutionFill | None:
        bid, ask = self.bid_ask(price, spread)
        if bid is None or ask is None:
            return None
        qd, slip_mult, partial, missed = self._market_penalty(spread, volatility, liquidity, aggression)
        side_px = bid if direction == "Long" else ask
        signed_slippage = self.slippage * slip_mult
        fill_price = side_px - signed_slippage if direction == "Long" else side_px + signed_slippage
        fee = fill_price * self.fee_rate
        quality = self._quality(qd, signed_slippage, spread, missed)
        return ExecutionFill(side=direction, price=fill_price, fee_paid=fee, queue_delay_ms=qd, partial=partial, missed=missed, slippage_paid=signed_slippage, execution_quality=quality)

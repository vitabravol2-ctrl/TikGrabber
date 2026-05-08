from __future__ import annotations

from dataclasses import dataclass


FEE_MODES: dict[str, tuple[str, str]] = {
    "MAKER_MAKER": ("maker", "maker"),
    "MAKER_TAKER": ("maker", "taker"),
    "TAKER_TAKER": ("taker", "taker"),
}


@dataclass
class FuturesCostBreakdown:
    notional_usdt: float
    entry_fee: float
    exit_fee: float
    round_trip_fee: float
    bnb_discount: float
    slippage_cost: float
    spread_cost: float
    funding_buffer: float
    required_gross_move_usdt: float
    required_gross_move_bps: float
    required_price_move_usdt: float
    required_ticks: float
    net_profit_after_costs: float


@dataclass
class FuturesCostModel:
    maker_fee_bps: float = 1.8
    taker_fee_bps: float = 4.5
    bnb_discount_enabled: bool = True
    estimated_slippage_bps: float = 1.0
    funding_buffer_bps: float = 0.5
    minimum_net_profit_bps: float = 3.0
    min_desired_profit_usdt: float = 0.03
    slippage_buffer_bps: float = 1.0
    spread_buffer_bps: float = 0.0
    fee_mode: str = "MAKER_TAKER"
    tick_size: float = 0.10

    def _effective_fee_bps(self, side: str) -> float:
        base = self.maker_fee_bps if side == "maker" else self.taker_fee_bps
        return base * (0.9 if self.bnb_discount_enabled else 1.0)


    def round_trip_cost_bps(self, use_maker_entry: bool = False) -> float:
        mode = "MAKER_TAKER" if use_maker_entry else self.fee_mode
        entry_side, exit_side = FEE_MODES.get(mode, FEE_MODES["MAKER_TAKER"])
        return self._effective_fee_bps(entry_side) + self._effective_fee_bps(exit_side) + self.slippage_buffer_bps + self.funding_buffer_bps
    def calculate(
        self,
        *,
        notional_usdt: float,
        expected_move_usdt: float,
        spread_usdt: float,
        fee_mode: str | None = None,
        tick_size: float | None = None,
    ) -> FuturesCostBreakdown:
        mode = fee_mode or self.fee_mode
        entry_side, exit_side = FEE_MODES.get(mode, FEE_MODES["MAKER_TAKER"])
        entry_fee_bps = self._effective_fee_bps(entry_side)
        exit_fee_bps = self._effective_fee_bps(exit_side)
        raw_entry = notional_usdt * ((self.maker_fee_bps if entry_side == "maker" else self.taker_fee_bps) / 10_000.0)
        raw_exit = notional_usdt * ((self.maker_fee_bps if exit_side == "maker" else self.taker_fee_bps) / 10_000.0)
        entry_fee = notional_usdt * (entry_fee_bps / 10_000.0)
        exit_fee = notional_usdt * (exit_fee_bps / 10_000.0)
        round_trip_fee = entry_fee + exit_fee
        bnb_discount = (raw_entry + raw_exit) - round_trip_fee

        slippage_cost = notional_usdt * (self.slippage_buffer_bps / 10_000.0)
        spread_cost = max(0.0, spread_usdt) * (notional_usdt / max(1e-9, notional_usdt))
        funding_buffer = notional_usdt * (self.funding_buffer_bps / 10_000.0)

        required_gross_move_usdt = round_trip_fee + slippage_cost + spread_cost + funding_buffer + self.min_desired_profit_usdt
        required_gross_move_bps = (required_gross_move_usdt / max(notional_usdt, 1e-9)) * 10_000.0
        required_price_move_usdt = required_gross_move_usdt
        tick = tick_size if tick_size is not None else self.tick_size
        required_ticks = required_price_move_usdt / max(tick, 1e-9)
        net_profit_after_costs = expected_move_usdt - required_gross_move_usdt
        return FuturesCostBreakdown(
            notional_usdt=notional_usdt,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            round_trip_fee=round_trip_fee,
            bnb_discount=bnb_discount,
            slippage_cost=slippage_cost,
            spread_cost=spread_cost,
            funding_buffer=funding_buffer,
            required_gross_move_usdt=required_gross_move_usdt,
            required_gross_move_bps=required_gross_move_bps,
            required_price_move_usdt=required_price_move_usdt,
            required_ticks=required_ticks,
            net_profit_after_costs=net_profit_after_costs,
        )

    def net_profit_usdt(self, notional_usdt: float, expected_move_bps: float, spread_usdt: float = 0.0) -> tuple[float, float]:
        gross = notional_usdt * (expected_move_bps / 10_000.0)
        result = self.calculate(notional_usdt=notional_usdt, expected_move_usdt=gross, spread_usdt=spread_usdt)
        return result.net_profit_after_costs, gross

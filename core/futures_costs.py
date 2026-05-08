from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FuturesCostModel:
    maker_fee_bps: float = 1.8
    taker_fee_bps: float = 4.5
    bnb_discount_enabled: bool = True
    estimated_slippage_bps: float = 1.0
    funding_buffer_bps: float = 0.5
    minimum_net_profit_bps: float = 0.0
    minimum_real_move_usdt: float = 35.0

    def effective_taker_fee_bps(self) -> float:
        return self.taker_fee_bps * (0.9 if self.bnb_discount_enabled else 1.0)

    def round_trip_cost_bps(self, use_maker_entry: bool = False) -> float:
        entry_fee = self.maker_fee_bps if use_maker_entry else self.effective_taker_fee_bps()
        exit_fee = self.effective_taker_fee_bps()
        return entry_fee + exit_fee + self.estimated_slippage_bps + self.funding_buffer_bps

    def net_profit_usdt(self, notional_usdt: float, expected_move_bps: float, use_maker_entry: bool = False) -> tuple[float, float]:
        gross = notional_usdt * (expected_move_bps / 10_000.0)
        cost = notional_usdt * (self.round_trip_cost_bps(use_maker_entry) / 10_000.0)
        return gross - cost, gross

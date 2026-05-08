from __future__ import annotations

from dataclasses import dataclass

from core.models import FuturesPositionModel, MarketSnapshot


@dataclass
class FuturesRiskControls:
    max_leverage: float = 3.0
    max_margin: float = 10000.0
    max_spread: float = 3.0
    max_volatility: float = 8.0
    min_liquidity_tps: float = 2.0
    min_liquidation_buffer_pct: float = 2.5
    min_signal_strength: float = 70.0

    def evaluate_entry(
        self,
        snap: MarketSnapshot,
        position: FuturesPositionModel,
        requested_leverage: float,
        cooldown_active: bool,
    ) -> tuple[bool, str]:
        if snap.data_quality != "Good":
            return False, "DATA_QUALITY"
        if snap.spread <= 0 or snap.spread > self.max_spread:
            return False, "SPREAD"
        if abs(snap.velocity) > self.max_volatility:
            return False, "VOLATILITY"
        if snap.ticks_per_second < self.min_liquidity_tps:
            return False, "LIQUIDITY"
        if position.side != "FLAT":
            return False, "IN_POSITION"
        if cooldown_active:
            return False, "COOLDOWN"
        if requested_leverage > self.max_leverage:
            return False, "LEVERAGE"
        if position.initial_margin > self.max_margin:
            return False, "MARGIN"
        if position.side != "FLAT" and position.liquidation_distance_pct < self.min_liquidation_buffer_pct:
            return False, "LIQ_BUFFER"
        if snap.trigger_strength < self.min_signal_strength:
            return False, "WEAK_SIGNAL"
        return True, "PASS"

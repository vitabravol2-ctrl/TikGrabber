from __future__ import annotations

from dataclasses import dataclass

from core.models import MarketSnapshot


@dataclass
class OpportunityResult:
    continuation_strength: float
    breakout_energy: float
    trapped_liquidity_score: float
    impulse_probability: float
    acceleration_score: float
    liquidation_potential: float
    momentum_persistence: float
    expected_move_ticks_real: float
    expected_move_usdt_real: float
    opportunity_score: float
    real_opportunity: bool
    microstructure_state: str


class RealOpportunityEngine:
    def __init__(self, safety_multiplier: float = 1.5) -> None:
        self.safety_multiplier = safety_multiplier

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, value))

    def evaluate(self, snap: MarketSnapshot, order_notional_usdt: float) -> OpportunityResult:
        pressure = abs(snap.buy_pressure - snap.sell_pressure)
        continuation_strength = self._clamp((pressure * 120.0) + (max(0.0, snap.net_edge_score) * 0.7) + (20.0 if snap.edge_stability == "STABLE" else 0.0))
        breakout_energy = self._clamp((max(snap.sweep_up, snap.sweep_down) * 50.0) + (snap.ticks_per_second * 3.5) + (max(0.0, 2.5 - snap.spread) * 8.0))

        trapped_longs = snap.sell_pressure > snap.buy_pressure and snap.trap > 0.35
        trapped_shorts = snap.buy_pressure > snap.sell_pressure and snap.trap > 0.35
        trapped_liquidity_score = self._clamp((snap.trap * 55.0) + (15.0 if trapped_longs or trapped_shorts else 0.0) + (15.0 if snap.reclaim < 0.35 else 0.0))

        acceleration_score = self._clamp((abs(snap.velocity) / max(0.1, snap.spread)) * 35.0 + max(snap.sweep_up, snap.sweep_down) * 45.0)
        momentum_persistence = self._clamp((max(0.0, 1.0 - snap.late_move_penalty) * 45.0) + (35.0 if snap.noise_level == "LOW" else 10.0) + (15.0 if snap.market_phase in {"BREAKOUT", "TREND"} else 0.0))
        liquidation_potential = self._clamp(trapped_liquidity_score * 0.65 + breakout_energy * 0.35)
        impulse_probability = self._clamp((continuation_strength * 0.35) + (breakout_energy * 0.25) + (acceleration_score * 0.2) + (momentum_persistence * 0.2))

        reversal_probability = self._clamp(snap.reversal_probability)
        exhaustion_score = self._clamp(snap.exhaustion_score)
        late_entry_risk = 80.0 if snap.late_entry_risk == "HIGH" else (45.0 if snap.late_entry_risk == "MEDIUM" else 10.0)

        opportunity_score = (
            continuation_strength * 0.25
            + breakout_energy * 0.20
            + trapped_liquidity_score * 0.20
            + acceleration_score * 0.15
            + momentum_persistence * 0.10
            + liquidation_potential * 0.10
        ) - (reversal_probability * 0.25 + exhaustion_score * 0.20 + late_entry_risk * 0.20)

        liquidity_vacuum = snap.spread <= 2.0 and snap.ticks_per_second >= 3.0
        volatility_expansion = abs(snap.velocity) > (snap.spread * 0.5)
        base_move_ticks = (
            0.6
            + (acceleration_score / 100.0) * 4.0
            + (momentum_persistence / 100.0) * 3.0
            + (breakout_energy / 100.0) * 3.0
            + (trapped_liquidity_score / 100.0) * 2.5
            + (1.2 if liquidity_vacuum else 0.0)
            + (0.8 if volatility_expansion else 0.0)
        )
        if snap.market_regime in {"DEAD_MARKET", "COMPRESSION"}:
            base_move_ticks *= 0.25
        base_move_ticks *= max(0.15, 1.0 - (exhaustion_score / 160.0))
        base_move_ticks *= max(0.2, 1.0 - (reversal_probability / 170.0))
        if trapped_shorts:
            base_move_ticks += 1.2
        if trapped_longs:
            base_move_ticks += 0.8

        expected_move_ticks_real = max(0.0, round(base_move_ticks, 2))
        expected_move_usdt_real = expected_move_ticks_real * max(0.0, snap.spread) / max(snap.price, 1e-9) * order_notional_usdt
        real_opportunity = expected_move_usdt_real > (snap.required_move_usdt * self.safety_multiplier)

        if snap.market_regime in {"DEAD_MARKET", "COMPRESSION"}:
            state = "MICRO_RANGE_CHOP"
        elif trapped_shorts and breakout_energy >= 55:
            state = "CASCADE_SETUP"
        elif trapped_shorts:
            state = "TRAPPED_SHORTS"
        elif trapped_longs:
            state = "TRAPPED_LONGS"
        elif reversal_probability > 70:
            state = "FALSE_BREAKOUT"
        else:
            state = "FOMO_CONTINUATION" if continuation_strength >= 65 else "STOP_HUNT_ACTIVE"

        return OpportunityResult(
            continuation_strength=round(continuation_strength, 2),
            breakout_energy=round(breakout_energy, 2),
            trapped_liquidity_score=round(trapped_liquidity_score, 2),
            impulse_probability=round(impulse_probability, 2),
            acceleration_score=round(acceleration_score, 2),
            liquidation_potential=round(liquidation_potential, 2),
            momentum_persistence=round(momentum_persistence, 2),
            expected_move_ticks_real=expected_move_ticks_real,
            expected_move_usdt_real=round(expected_move_usdt_real, 4),
            opportunity_score=round(opportunity_score, 2),
            real_opportunity=real_opportunity,
            microstructure_state=state,
        )

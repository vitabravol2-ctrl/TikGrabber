from __future__ import annotations

from dataclasses import dataclass

from core.models import MarketSnapshot
from signal_engine.engine import TradeSignal


@dataclass
class ThresholdConfig:
    edge_threshold: float = 15.0
    spread_limit_bps: float = 0.6
    pressure_diff: float = 0.03
    min_trigger_strength: float = 70.0
    panic_block_threshold: float = 0.65


@dataclass
class ConditionResult:
    name: str
    passed: bool
    current: float
    target: float


@dataclass
class SignalDecision:
    signal: TradeSignal
    long_checks: list[ConditionResult]
    short_checks: list[ConditionResult]
    long_blockers: list[str]
    short_blockers: list[str]
    long_strength: float
    short_strength: float
    trigger_strength: float


class SignalDecisionEngine:
    def __init__(self, config: ThresholdConfig | None = None) -> None:
        self.config = config or ThresholdConfig()

    def evaluate(self, snap: MarketSnapshot) -> SignalDecision:
        spread_limit = max(2.2, snap.price * (self.config.spread_limit_bps / 10000.0))
        spread_ok = snap.spread > 0 and snap.spread <= spread_limit
        panic_state = snap.panic >= self.config.panic_block_threshold
        liquidity_ok = snap.ticks_per_second >= 2.0
        volatility_ok = abs(snap.velocity) <= max(4.0, spread_limit * 2.0)

        long_checks = [
            ConditionResult("EDGE", snap.edge_score >= self.config.edge_threshold, snap.edge_score, self.config.edge_threshold),
            ConditionResult("PRESSURE", snap.buy_pressure - snap.sell_pressure >= 0.04, snap.buy_pressure - snap.sell_pressure, 0.04),
            ConditionResult("SWEEP", snap.sweep_down >= 0.45, snap.sweep_down, 0.45),
            ConditionResult("RECLAIM", snap.reclaim >= 0.45, snap.reclaim, 0.45),
            ConditionResult("SPREAD", spread_ok, snap.spread, spread_limit),
        ]
        short_checks = [
            ConditionResult("EDGE", snap.edge_score <= -self.config.edge_threshold, snap.edge_score, -self.config.edge_threshold),
            ConditionResult("PRESSURE", snap.sell_pressure - snap.buy_pressure >= 0.04, snap.sell_pressure - snap.buy_pressure, 0.04),
            ConditionResult("SWEEP", snap.sweep_up >= 0.45, snap.sweep_up, 0.45),
            ConditionResult("RECLAIM", snap.reclaim >= 0.45, snap.reclaim, 0.45),
            ConditionResult("SPREAD", spread_ok, snap.spread, spread_limit),
        ]

        long_strength = self._weighted_strength(snap, long=True, spread_ok=spread_ok)
        short_strength = self._weighted_strength(snap, long=False, spread_ok=spread_ok)
        long_blockers = [c.name for c in long_checks if not c.passed]
        short_blockers = [c.name for c in short_checks if not c.passed]

        quality_blocks = []
        if not spread_ok:
            quality_blocks.append("HIGH_SPREAD")
        if panic_state:
            quality_blocks.append("PANIC")
        if not liquidity_ok:
            quality_blocks.append("NO_LIQUIDITY")
        if not volatility_ok:
            quality_blocks.append("INSANE_VOL")

        signal = TradeSignal.NO_SIGNAL
        if not quality_blocks:
            if long_strength >= self.config.min_trigger_strength and snap.long_probability >= snap.short_probability:
                signal = TradeSignal.LONG_SIGNAL
                long_blockers = []
            elif short_strength >= self.config.min_trigger_strength and snap.short_probability >= snap.long_probability:
                signal = TradeSignal.SHORT_SIGNAL
                short_blockers = []

        if signal == TradeSignal.NO_SIGNAL and quality_blocks:
            long_blockers.extend(quality_blocks)
            short_blockers.extend(quality_blocks)

        return SignalDecision(
            signal=signal,
            long_checks=long_checks,
            short_checks=short_checks,
            long_blockers=long_blockers,
            short_blockers=short_blockers,
            long_strength=long_strength,
            short_strength=short_strength,
            trigger_strength=max(long_strength, short_strength),
        )

    @staticmethod
    def _weighted_strength(snap: MarketSnapshot, long: bool, spread_ok: bool) -> float:
        edge_component = max(0.0, min(1.0, (snap.edge_score if long else -snap.edge_score) / 40.0)) * 40.0
        pressure_raw = (snap.buy_pressure - snap.sell_pressure) if long else (snap.sell_pressure - snap.buy_pressure)
        pressure_component = max(0.0, min(1.0, pressure_raw / 0.12)) * 25.0
        sweep_component = max(0.0, min(1.0, (snap.sweep_down if long else snap.sweep_up))) * 15.0
        reclaim_component = max(0.0, min(1.0, snap.reclaim)) * 10.0
        spread_component = 10.0 if spread_ok else 0.0
        return edge_component + pressure_component + sweep_component + reclaim_component + spread_component

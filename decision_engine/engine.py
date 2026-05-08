from __future__ import annotations

from dataclasses import dataclass

from core.models import MarketSnapshot
from signal_engine.engine import TradeSignal


@dataclass
class ThresholdConfig:
    edge_threshold: float = 15.0
    spread_limit_bps: float = 0.6
    pressure_diff: float = 0.03
    sweep_sensitivity: float = 1.0


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
        sellers_weak = snap.sell_pressure <= (0.55 - self.config.pressure_diff)
        buyers_weak = snap.buy_pressure <= (0.55 - self.config.pressure_diff)

        long_checks = [
            ConditionResult("SWEEP_DOWN", snap.sweep_down >= self.config.sweep_sensitivity, snap.sweep_down, self.config.sweep_sensitivity),
            ConditionResult("RECLAIM", snap.reclaim >= 1.0, snap.reclaim, 1.0),
            ConditionResult("EDGE > T", snap.edge_score >= self.config.edge_threshold, snap.edge_score, self.config.edge_threshold),
            ConditionResult("LOW_SPREAD", spread_ok, snap.spread, spread_limit),
            ConditionResult("SELLERS_WEAK", sellers_weak, snap.sell_pressure, 0.55 - self.config.pressure_diff),
        ]
        short_checks = [
            ConditionResult("SWEEP_UP", snap.sweep_up >= self.config.sweep_sensitivity, snap.sweep_up, self.config.sweep_sensitivity),
            ConditionResult("REJECTION", snap.velocity <= 0.0, snap.velocity, 0.0),
            ConditionResult("EDGE < -T", snap.edge_score <= -self.config.edge_threshold, snap.edge_score, -self.config.edge_threshold),
            ConditionResult("LOW_SPREAD", spread_ok, snap.spread, spread_limit),
            ConditionResult("BUYERS_WEAK", buyers_weak, snap.buy_pressure, 0.55 - self.config.pressure_diff),
        ]

        long_strength = self._strength(long_checks)
        short_strength = self._strength(short_checks)
        long_blockers = [c.name for c in long_checks if not c.passed]
        short_blockers = [c.name for c in short_checks if not c.passed]

        signal = TradeSignal.NO_SIGNAL
        if not long_blockers and snap.long_probability >= snap.short_probability:
            signal = TradeSignal.LONG_SIGNAL
        elif not short_blockers and snap.short_probability >= snap.long_probability:
            signal = TradeSignal.SHORT_SIGNAL

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
    def _strength(checks: list[ConditionResult]) -> float:
        return sum(1 for c in checks if c.passed) / len(checks) * 100.0

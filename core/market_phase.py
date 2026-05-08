from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class PhaseSignal:
    phase: str
    trap_score: float
    exhaustion_score: float
    reversal_probability: float
    late_entry_risk: str
    fomo_risk: float
    late_move_penalty: float
    reversal_setup: bool


@dataclass
class MarketPhaseEngine:
    edge_window: deque[float] = field(default_factory=lambda: deque(maxlen=12))
    pressure_window: deque[float] = field(default_factory=lambda: deque(maxlen=12))
    trap_window: deque[float] = field(default_factory=lambda: deque(maxlen=12))
    velocity_window: deque[float] = field(default_factory=lambda: deque(maxlen=12))

    def update(self, *, regime: str, edge: float, buy_pressure: float, sell_pressure: float, trap: float, sweep: float, reclaim: float, velocity: float, spread: float) -> PhaseSignal:
        self.edge_window.append(edge)
        p = max(buy_pressure, sell_pressure)
        self.pressure_window.append(p)
        self.trap_window.append(trap)
        self.velocity_window.append(abs(velocity))
        edge_slope = (self.edge_window[-1] - self.edge_window[0]) / max(1, len(self.edge_window) - 1)
        edge_decay = max(0.0, -edge_slope)
        pressure_decay = max(0.0, (self.pressure_window[0] - self.pressure_window[-1])) if len(self.pressure_window) > 2 else 0.0
        vel_slow = 1.0 if len(self.velocity_window) > 4 and self.velocity_window[-1] < (sum(self.velocity_window) / len(self.velocity_window)) * 0.6 else 0.0
        trap_score = min(100.0, (trap * 55.0) + (sweep * 20.0) + ((1.0 - reclaim) * 25.0))
        exhaustion = min(100.0, (min(1.0, abs(edge) / 90.0) * 30.0) + (vel_slow * 20.0) + (min(1.0, spread / 5.0) * 15.0) + (pressure_decay * 20.0) + (trap * 15.0))
        late_penalty = min(1.0, max(0.0, (len([x for x in self.pressure_window if x > 0.68]) - 4) / 8.0))
        late_risk = "HIGH" if late_penalty > 0.55 else ("MID" if late_penalty > 0.28 else "LOW")
        fomo_risk = min(100.0, (max(0.0, p - 0.62) * 100.0) * (0.5 + late_penalty * 0.5))
        reversal_prob = min(99.0, trap_score * 0.45 + exhaustion * 0.45 + (100.0 if reclaim < 0.3 else 20.0) * 0.10)
        reversal_setup = trap_score > 65 and exhaustion > 50 and reclaim < 0.35
        if regime == "DEAD_MARKET":
            phase = "DEAD_MARKET"
        elif reversal_setup or reversal_prob > 70:
            phase = "REVERSAL"
        elif exhaustion > 68:
            phase = "EXHAUSTION"
        elif trap_score > 60:
            phase = "LIQUIDITY_TRAP"
        elif edge_slope > 1.2 and p > 0.58:
            phase = "BREAKOUT"
        elif p > 0.55:
            phase = "PRESSURE_BUILDUP"
        elif abs(edge) < 12 and p < 0.54:
            phase = "ACCUMULATION"
        else:
            phase = "PRESSURE_BUILDUP"
        return PhaseSignal(phase, trap_score, exhaustion, reversal_prob, late_risk, fomo_risk, late_penalty, reversal_setup)

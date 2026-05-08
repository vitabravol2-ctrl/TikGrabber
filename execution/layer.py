from __future__ import annotations

from dataclasses import dataclass

from core.models import FuturesExecutionConfig, SimulationState


@dataclass
class FuturesExecutionLayer:
    """Execution adapter for future live-trading integration.

    Current scope is intentionally limited to realistic paper execution.
    """

    config: FuturesExecutionConfig

    def status_snapshot(self) -> dict[str, str]:
        return {
            "mode": self.config.mode,
            "leverage": f"{self.config.leverage:.0f}x",
            "execution": self.config.execution,
            "fees": "ON" if self.config.fees_enabled else "OFF",
            "slippage": "ON" if self.config.slippage_enabled else "OFF",
        }

    def can_route_live_order(self) -> bool:
        return False

    def bind_simulation(self, sim: SimulationState) -> SimulationState:
        return sim

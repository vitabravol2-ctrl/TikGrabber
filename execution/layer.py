from __future__ import annotations

from dataclasses import dataclass

from core.models import FuturesExecutionConfig, SimulationState

LIVE_TRADING_ENABLED = False
API_KEYS_ALLOWED = False
REAL_ORDERS_ALLOWED = False


@dataclass
class FuturesExecutionLayer:
    """Execution adapter for paper futures only."""

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
        return LIVE_TRADING_ENABLED and REAL_ORDERS_ALLOWED and API_KEYS_ALLOWED

    def assert_paper_only(self) -> None:
        if self.can_route_live_order():
            raise RuntimeError("Live trading is blocked in v0.8 paper-only mode")

    def bind_simulation(self, sim: SimulationState) -> SimulationState:
        self.assert_paper_only()
        return sim

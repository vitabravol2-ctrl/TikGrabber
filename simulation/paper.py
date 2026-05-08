from __future__ import annotations

from core.models import MarketSnapshot, SimulationState


class PaperSimulator:
    def __init__(self) -> None:
        self.state = SimulationState()

    def step(self, snap: MarketSnapshot) -> SimulationState:
        if self.state.virtual_position == "Flat" and abs(snap.edge_score) > 55:
            self.state.virtual_position = "Long" if snap.edge_score > 0 else "Short"
            self.state.entry = snap.price
            self.state.trades_count += 1
        elif self.state.virtual_position != "Flat":
            direction = 1 if self.state.virtual_position == "Long" else -1
            self.state.pnl_ticks = (snap.price - self.state.entry) * direction
            if abs(self.state.pnl_ticks) > max(20.0, snap.spread * 30):
                won = self.state.pnl_ticks > 0
                self.state.winrate = ((self.state.winrate * (self.state.trades_count - 1)) + (100.0 if won else 0.0)) / max(1, self.state.trades_count)
                self.state.virtual_position = "Flat"
                self.state.entry = 0.0
                self.state.pnl_ticks = 0.0
        return self.state

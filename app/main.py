from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from core.engine import GameTheoryEngine
from core.models import MarketSnapshot
from ws.binance_ws import BinanceFeedThread
from simulation.paper import PaperSimulator
from ui.dashboard import DashboardWindow


class AppController:
    def __init__(self) -> None:
        self.window = DashboardWindow()
        self.snapshot = MarketSnapshot()
        self.engine = GameTheoryEngine()
        self.sim = PaperSimulator()
        self.feed = BinanceFeedThread()
        self.feed.market_event.connect(self.on_market_event)
        self.feed.status.connect(self.on_status)

    def on_status(self, status: str) -> None:
        self.snapshot.ws_status = status
        self.window.render(self.snapshot, self.sim.state)

    def on_market_event(self, event: dict) -> None:
        if event.get("type") != "agg_trade":
            return
        self.snapshot = self.engine.update(self.snapshot, event)
        sim_state = self.sim.step(self.snapshot)
        self.window.render(self.snapshot, sim_state)

    def run(self) -> None:
        self.window.show()
        self.feed.start()


def run() -> None:
    app = QApplication(sys.argv)
    controller = AppController()
    controller.run()
    exit_code = app.exec()
    controller.feed.stop()
    sys.exit(exit_code)

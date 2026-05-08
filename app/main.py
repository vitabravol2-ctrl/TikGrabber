from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from core.engine import GameTheoryEngine
from core.models import MarketSnapshot
from ws.binance_ws import BinanceFeedThread
from simulation.paper import PaperSimulator
from signal_engine import SignalEngine
from validation import SignalValidationEngine
from ui.dashboard import DashboardWindow


class AppController:
    def __init__(self) -> None:
        self.window = DashboardWindow()
        self.snapshot = MarketSnapshot()
        self.engine = GameTheoryEngine()
        self.validator = SignalValidationEngine()
        self.sim = PaperSimulator(on_trade_closed=self.validator.resolve_signal)
        self.signals = SignalEngine()
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
        self.validator.register_event(self.snapshot)
        signal = self.signals.evaluate(self.snapshot)
        signal_id = self.validator.register_signal(self.snapshot, signal)
        sim_state = self.sim.step(self.snapshot, signal, signal_id)
        analytics = self.validator.analytics()
        sim_state.analytics.best_signal_type = analytics["best_signal_type"]
        sim_state.analytics.worst_signal_type = analytics["worst_signal_type"]
        sim_state.analytics.current_signal_quality = analytics["current_signal_quality"]
        sim_state.analytics.signal_confidence = analytics["signal_confidence"]
        sim_state.analytics.best_market_condition = analytics["best_market_condition"]
        sim_state.analytics.best_combo = analytics["best_combo"]
        sim_state.analytics.worst_combo = analytics["worst_combo"]
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

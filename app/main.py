from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from core.engine import GameTheoryEngine
from core.models import MarketSnapshot
from decision_engine import SignalDecisionEngine
from simulation.paper import PaperSimulator
from validation import SignalValidationEngine
from ws.binance_ws import BinanceFeedThread
from ui.dashboard import DashboardWindow


class AppController:
    def __init__(self) -> None:
        self.window = DashboardWindow()
        self.snapshot = MarketSnapshot()
        self.engine = GameTheoryEngine()
        self.validator = SignalValidationEngine()
        self.sim = PaperSimulator(on_trade_closed=self.validator.resolve_signal)
        self.decision_engine = SignalDecisionEngine()
        self.feed = BinanceFeedThread()
        self.feed.market_event.connect(self.on_market_event)
        self.feed.status.connect(self.on_status)
        self.log = logging.getLogger("signal_flow")
        if not self.log.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
            self.log.addHandler(handler)
        self.log.setLevel(logging.INFO)
        self._last_market_flow = ""
        self._last_trade_flow = ""

    def on_status(self, status: str) -> None:
        self.snapshot.ws_status = status
        self.window.render(self.snapshot, self.sim.state)

    def on_market_event(self, event: dict) -> None:
        if event.get("type") != "agg_trade":
            return
        self.snapshot = self.engine.update(self.snapshot, event)
        self.validator.register_event(self.snapshot)

        decision = self.decision_engine.evaluate(self.snapshot)
        signal = decision.signal
        self.snapshot.long_debug = " | ".join(f"{c.name}:{'YES' if c.passed else 'NO'}" for c in decision.long_checks)
        self.snapshot.short_debug = " | ".join(f"{c.name}:{'YES' if c.passed else 'NO'}" for c in decision.short_checks)
        blockers = decision.long_blockers if signal.value in {"LONG", "NONE"} else decision.short_blockers
        self.snapshot.block_reason = ", ".join(blockers) if blockers else "NONE"
        self.snapshot.trigger_strength = decision.trigger_strength

        signal_id = self.validator.register_signal(self.snapshot, signal) if signal.value != "NONE" else None
        sim_state = self.sim.step(self.snapshot, signal, signal_id)
        if sim_state.accepted_signal_id is not None:
            self.validator.register_accepted_signal(self.snapshot, signal, sim_state.accepted_signal_id)
        self._flow_log(signal.value, decision)
        analytics = self.validator.analytics()
        sim_state.analytics.best_signal_type = analytics["best_signal_type"]
        sim_state.analytics.worst_signal_type = analytics["worst_signal_type"]
        sim_state.analytics.current_signal_quality = analytics["current_signal_quality"]
        sim_state.analytics.signal_confidence = analytics["signal_confidence"]
        sim_state.analytics.best_market_condition = analytics["best_market_condition"]
        sim_state.analytics.best_combo = analytics["best_combo"]
        sim_state.analytics.worst_combo = analytics["worst_combo"]
        self.window.render(self.snapshot, sim_state)

    def _flow_log(self, signal: str, decision) -> None:
        state = self.snapshot.market_intent
        edge = self.snapshot.edge_score
        block = self.snapshot.block_reason
        bucket = round(edge / 10)
        market_flow = f"[MARKET] STATE {state} | EDGE {edge:+.1f}({bucket:+d}) | BLOCK {block} | SIGNAL {signal} | STRENGTH {decision.trigger_strength:.1f}"
        if market_flow != self._last_market_flow:
            self.log.info(market_flow)
            self._last_market_flow = market_flow

        sim = self.sim.state
        entry = f"{sim.entry:.2f}" if sim.virtual_position != "Flat" else "-"
        exit_price = f"{sim.last_exit_price:.2f}" if sim.last_exit_price > 0 else "-"
        trade_flow = (
            f"[TRADE] POS {sim.virtual_position} | EVENT {sim.last_event} | E {entry} | "
            f"X {exit_price} | NET {sim.last_net_pnl:+.2f} | FEES {sim.fees_paid:.2f} | HOLD {sim.hold_seconds:.1f}s"
        )
        if trade_flow != self._last_trade_flow:
            self.log.info(trade_flow)
            self._last_trade_flow = trade_flow

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

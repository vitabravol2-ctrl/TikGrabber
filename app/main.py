from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.engine import GameTheoryEngine
from core.models import FuturesPositionModel, MarketSnapshot
from decision_engine import SignalDecisionEngine
from replay import ReplayEngine, ReplayEventStore
from risk.controls import FuturesRiskControls
from simulation.paper import PaperSimulator
from validation import SignalValidationEngine
from ws.binance_ws import BinanceFeedThread
from ui.dashboard import DashboardWindow


class AppController:
    def __init__(self, replay_file: str | None = None) -> None:
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
        self.replay_file = replay_file
        self.risk = FuturesRiskControls()
        self.position = FuturesPositionModel()
        self.blocked_reasons = Counter()

    def on_status(self, status: str) -> None:
        self.snapshot.ws_status = status
        self.window.render(self.snapshot, self.sim.state)

    def on_market_event(self, event: dict) -> None:
        if event.get("type") != "agg_trade":
            return
        if not self.replay_file:
            ReplayEventStore.append_event("data/replay/btcusdt_events.jsonl", event)
        elif "book_age_ms" not in event or "depth_age_ms" not in event:
            event["legacy_replay"] = True
            event.setdefault("book_age_ms", 0.0)
            event.setdefault("depth_age_ms", 0.0)
            event.setdefault("bid", float(event.get("bid", 0.0)))
            event.setdefault("ask", float(event.get("ask", 0.0)))
            event.setdefault("bid_volume_total", float(event.get("bid_volume_total", 0.0)))
            event.setdefault("ask_volume_total", float(event.get("ask_volume_total", 0.0)))
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
        allowed = True
        reason = "PASS"
        if signal.value != "NONE":
            allowed, reason = self.risk.evaluate_entry(self.snapshot, self.position, 1.0, self.sim.state.cooldown_active)
            if not allowed:
                self.snapshot.block_reason = reason
                self.blocked_reasons[reason] += 1
        accepted_signal = signal if allowed else type(signal).NO_SIGNAL
        sim_state = self.sim.step(self.snapshot, accepted_signal, signal_id if allowed else None)
        if allowed and sim_state.accepted_signal_id is not None:
            self.validator.register_accepted_signal(self.snapshot, signal, sim_state.accepted_signal_id)

        self.sim.state.replay.mode = "REPLAY" if self.replay_file else "LIVE WS"
        self.sim.state.replay.events_processed += 1
        self.sim.state.replay.replay_speed = 1.0
        self.sim.state.replay.accepted_signals = self.sim.state.signals_count
        self.sim.state.replay.blocked_signals = sum(self.blocked_reasons.values())
        self.sim.state.replay.net_result = self.sim.state.net_pnl
        self.sim.state.replay.risk_block_reasons = dict(self.blocked_reasons)

        self._flow_log(signal.value, decision)
        analytics = self.validator.analytics()
        sim_state.analytics.best_signal_type = analytics["best_signal_type"]
        sim_state.analytics.worst_signal_type = analytics["worst_signal_type"]
        sim_state.analytics.current_signal_quality = analytics["current_signal_quality"]
        sim_state.analytics.signal_confidence = analytics["signal_confidence"]
        sim_state.analytics.best_market_condition = analytics["best_market_condition"]
        sim_state.analytics.best_combo = analytics["best_combo"]
        sim_state.analytics.worst_combo = analytics["worst_combo"]
        sim_state.replay.best_state = analytics["best_market_condition"]
        sim_state.replay.worst_state = analytics["worst_combo"]
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

    def run(self) -> None:
        self.window.show()
        if self.replay_file:
            replay = ReplayEngine(self.replay_file)
            for e in replay.events():
                self.on_market_event(e)
            self._write_report()
        else:
            self.feed.start()

    def _write_report(self) -> None:
        s = self.sim.state
        report = {
            "total_events": s.replay.events_processed,
            "accepted_signals": s.replay.accepted_signals,
            "blocked_signals": s.replay.blocked_signals,
            "trades": s.trades,
            "wins": s.wins,
            "losses": s.losses,
            "winrate": s.winrate,
            "net_pnl": s.net_pnl,
            "net_ticks": s.net_ticks,
            "avg_hold": s.avg_hold_seconds,
            "max_drawdown": min(0.0, s.last_net_ticks),
            "best_state": s.replay.best_state,
            "worst_state": s.replay.worst_state,
            "risk_block_reasons": s.replay.risk_block_reasons,
        }
        out = Path("reports")
        out.mkdir(parents=True, exist_ok=True)
        (out / "backtest_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (out / "backtest_summary.md").write_text("\n".join([f"- **{k}**: {v}" for k, v in report.items()]), encoding="utf-8")


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", default=None)
    args = parser.parse_args()

    app = QApplication(sys.argv)
    controller = AppController(replay_file=args.replay)
    controller.run()
    exit_code = app.exec()
    if not args.replay:
        controller.feed.stop()
    sys.exit(exit_code)

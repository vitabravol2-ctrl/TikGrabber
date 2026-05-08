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
        self._setup_arm_direction = "NONE"
        self._setup_arm_regime_family = "NONE"
        self._setup_arm_ticks = 0
        self._setup_arm_required = 3

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
        self.snapshot.ws_streams_seen = list(event.get("ws_streams_seen", []))
        self.validator.register_event(self.snapshot)

        decision = self.decision_engine.evaluate(self.snapshot)
        signal = decision.signal
        self.snapshot.long_debug = " | ".join(f"{c.name}:{'YES' if c.passed else 'NO'}" for c in decision.long_checks)
        self.snapshot.short_debug = " | ".join(f"{c.name}:{'YES' if c.passed else 'NO'}" for c in decision.short_checks)
        blockers = decision.long_blockers if signal.value in {"LONG", "NONE"} else decision.short_blockers
        self.snapshot.block_reason = ", ".join(blockers) if blockers else "NONE"
        self.snapshot.trigger_strength = decision.trigger_strength
        self.snapshot.best_direction = "LONG" if self.snapshot.long_probability >= self.snapshot.short_probability else "SHORT"

        signal_id = self.validator.register_signal(self.snapshot, signal) if signal.value != "NONE" else None
        candidate_direction = signal.value if signal.value != "NONE" else "NONE"
        self.snapshot.candidate_direction = candidate_direction
        self.snapshot.candidate_quality = self.snapshot.signal_quality
        self.snapshot.active_order = self.sim.state.active_order
        self.snapshot.active_position = self.sim.state.virtual_position != "Flat"
        self.snapshot.cooldown = self.sim.state.cooldown_active
        self.snapshot.data_can_trade = self.snapshot.can_trade_data
        allowed = True
        reason = "PASS"
        if signal.value != "NONE":
            allowed, reason = self.risk.evaluate_entry(self.snapshot, self.position, 1.0, self.sim.state.cooldown_active)
            if not allowed:
                self.snapshot.block_reason = reason
                self.blocked_reasons[reason] += 1
        self.snapshot.risk_allowed = allowed
        armed_signal = signal if self._arm_setup(signal.value, allowed) else type(signal).NO_SIGNAL
        self.snapshot.setup_armed = armed_signal.value != "NONE"
        self.snapshot.setup_armed_ticks = self._setup_arm_ticks
        accepted_signal = armed_signal if allowed else type(signal).NO_SIGNAL
        self.snapshot.sim_can_open = accepted_signal.value != "NONE" and self.sim.state.virtual_position == "Flat"
        self.snapshot.router_can_place = self.snapshot.sim_can_open and not self.sim.state.active_order
        sim_state = self.sim.step(self.snapshot, accepted_signal, signal_id if allowed else None)
        opened_events = {"LONG_OPENED", "SHORT_OPENED", "PARTIAL FILL LONG_OPENED", "PARTIAL FILL SHORT_OPENED"}
        if sim_state.last_event in opened_events:
            self.snapshot.final_entry_decision = "ORDER SENT"
        else:
            if self.snapshot.block_reason == "NONE" and self.snapshot.candidate_quality == "A":
                if not self.snapshot.risk_allowed:
                    self.snapshot.block_reason = reason
                elif self.sim.state.cooldown_active:
                    self.snapshot.block_reason = "COOLDOWN"
                elif self.snapshot.active_position:
                    self.snapshot.block_reason = "IN_POSITION"
                elif self._setup_arm_ticks < self._setup_arm_required:
                    self.snapshot.block_reason = "SETUP_ARMING"
                else:
                    self.snapshot.block_reason = "ORDER_REJECTED"
            self.snapshot.final_entry_decision = f"ENTRY BLOCKED: {self.snapshot.block_reason}"
        self.snapshot.entry_reason = sim_state.last_event
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

    def _arm_setup(self, signal_value: str, risk_allowed: bool) -> bool:
        regime_family = self.snapshot.market_regime
        setup_ok = all(
            [
                signal_value in {"LONG", "SHORT"},
                self.snapshot.signal_quality == "A",
                self.snapshot.noise_level == "LOW",
                self.snapshot.edge_stability == "STABLE",
                self.snapshot.can_trade_data,
                risk_allowed,
            ]
        )
        if not setup_ok:
            self._setup_arm_direction = "NONE"
            self._setup_arm_regime_family = "NONE"
            self._setup_arm_ticks = 0
            return False
        if signal_value == self._setup_arm_direction and regime_family == self._setup_arm_regime_family:
            self._setup_arm_ticks += 1
        else:
            self._setup_arm_direction = signal_value
            self._setup_arm_regime_family = regime_family
            self._setup_arm_ticks = 1
        return self._setup_arm_ticks >= self._setup_arm_required

    def _flow_log(self, signal: str, decision) -> None:
        state = self.snapshot.market_intent
        edge = self.snapshot.edge_score
        block = self.snapshot.block_reason
        bucket = round(edge / 10) * 10
        market_flow = f"REGIME -> {state} | QUALITY -> {self.snapshot.signal_quality} | EDGE BUCKET -> {bucket:+d} | NOISE -> {self.snapshot.noise_level} | BLOCK {block}"
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

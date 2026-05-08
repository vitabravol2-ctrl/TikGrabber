from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import MarketSnapshot, SimulationState
from telemetry.event_guard import EventGuard


class DashboardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BTCUSDT Game Theory Engine v1.0.6 — Compact Cockpit")
        self.resize(1920, 1080)
        self.setStyleSheet(
            "QWidget{background:#0a0f18;color:#d5def5;font-family:Consolas,Monaco,Segoe UI;}"
            "QFrame{border:1px solid #1b2b44;border-radius:7px;background:#0f1726;}"
            "QLabel.title{font-weight:700;color:#7f9ed8;letter-spacing:0.7px;font-size:10px;}"
            "QProgressBar{border:none;background:#1a2438;height:9px;border-radius:4px;text-align:center;}"
            "QProgressBar::chunk{border-radius:4px;background:#2b8fff;}"
            "QTextEdit{background:#090f1a;border:1px solid #1b2b44;border-radius:7px;font-size:11px;}"
        )
        self._event_guard = EventGuard()
        self._last_trade_event_idx = 0

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        outer.addWidget(self._build_market_header(), 0)

        center = QSplitter(Qt.Horizontal)
        center.setChildrenCollapsible(False)
        center.addWidget(self._build_market_control())
        center.addWidget(self._build_position_control())
        center.setStretchFactor(0, 6)
        center.setStretchFactor(1, 4)
        center.setSizes([1150, 720])
        outer.addWidget(center, 4)

        bottom = QSplitter(Qt.Horizontal)
        bottom.setChildrenCollapsible(False)
        bottom.addWidget(self._build_operator_logs())
        bottom.addWidget(self._build_engine_status())
        bottom.setStretchFactor(0, 7)
        bottom.setStretchFactor(1, 3)
        bottom.setSizes([1360, 500])
        outer.addWidget(bottom, 3)

        self.setCentralWidget(root)

    def _panel(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        if title:
            t = QLabel(title)
            t.setProperty("class", "title")
            lay.addWidget(t)
        return frame, lay

    def _build_market_header(self) -> QFrame:
        panel, lay = self._panel("MARKET HEADER")
        row = QHBoxLayout()
        row.setSpacing(4)
        self.price_label = QLabel("0.00")
        self.price_label.setStyleSheet("font-size:30px;font-weight:800;")
        row.addWidget(self.price_label)
        self.header_labels = {}
        for key in ["SPREAD", "VEL", "EDGE", "S.EDGE", "NET", "TPS", "WS"]:
            v = QLabel(f"{key}: -")
            v.setStyleSheet("font-size:11px;font-weight:600;padding:2px 5px;background:#111d31;border:1px solid #223656;border-radius:6px;")
            self.header_labels[key] = v
            row.addWidget(v)
        row.addStretch(1)
        lay.addLayout(row)

        strip = QHBoxLayout()
        strip.setSpacing(4)
        self.control_strip = {}
        for text in ["PAPER ON", "LIVE LOCKED", "AUTO ENTRY: OFF", "RISK GATE: ON", "KILL SWITCH: READY"]:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size:10px;padding:2px 6px;background:#17233a;border:1px solid #2a4068;border-radius:6px;color:#9bc1ff;")
            strip.addWidget(lbl)
            self.control_strip[text] = lbl
        strip.addStretch(1)
        lay.addLayout(strip)
        panel.setMaximumHeight(130)
        return panel

    def _build_market_control(self) -> QFrame:
        panel, lay = self._panel("MARKET / SIGNAL")
        probs = QFrame(); probs_l = QVBoxLayout(probs)
        probs_l.setContentsMargins(5, 5, 5, 5)
        self.long_prob = QLabel("LONG 50.0%")
        self.short_prob = QLabel("SHORT 50.0%")
        self.dom_bar = QProgressBar(); self.dom_bar.setRange(0, 100)
        probs_l.addWidget(self.long_prob); probs_l.addWidget(self.short_prob); probs_l.addWidget(self.dom_bar)
        lay.addWidget(probs)

        states, sl = self._panel("STATE LAMPS")
        grid = QGridLayout(); grid.setHorizontalSpacing(4); grid.setVerticalSpacing(4)
        self.state_badges = {}
        names = [("BUY", "BUY PRESSURE"), ("SELL", "SELL PRESSURE"), ("COMP", "COMPRESSION"), ("SWEEP", "SWEEP"), ("TRAP", "TRAP"), ("RCL", "RECLAIM"), ("PANIC", "PANIC")]
        for i, (short, key) in enumerate(names):
            b = QLabel(short); b.setAlignment(Qt.AlignCenter)
            self.state_badges[key] = b
            self._set_lamp(b, False)
            grid.addWidget(b, i // 4, i % 4)
        sl.addLayout(grid)
        lay.addWidget(states)

        checks, cl = self._panel("SIGNAL CHECK")
        self.check_labels = {}
        labels = [("EDGE", "EDGE"), ("PRESSURE", "PRS"), ("SWEEP", "SWP"), ("RECLAIM", "RCL"), ("BREAK EVEN", "BE"), ("LIQUIDITY", "LIQ"), ("SPREAD", "SPR"), ("RISK GATE", "RISK")]
        cgrid = QGridLayout(); cgrid.setSpacing(4)
        for i, (key, short) in enumerate(labels):
            lbl = QLabel(short)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumHeight(22)
            self._set_check_lamp(lbl, None)
            self.check_labels[key] = lbl
            cgrid.addWidget(lbl, i // 4, i % 4)
        cl.addLayout(cgrid)
        self.block_label = QLabel("BLOCK: -")
        self.block_label.setStyleSheet("font-size:11px;")
        cl.addWidget(self.block_label)
        lay.addWidget(checks)
        return panel

    def _build_position_control(self) -> QFrame:
        panel, lay = self._panel("POSITION CONTROL")
        self.position_status = QLabel("STATUS: WAITING SETUP")
        self.position_status.setStyleSheet("font-size:14px;font-weight:800;color:#87a7e1;")
        self.position_status.setWordWrap(True)
        lay.addWidget(self.position_status)
        self.position_rows = {}
        keys = ["BEST DIRECTION", "EDGE PACK", "TRIGGER", "EXPECTED MOVE", "BLOCK REASON", "SIDE", "ENTRY", "MARK", "UPNL", "NET TICKS", "HOLD", "TP %", "SL %", "FEES / SLIPPAGE"]
        for key in keys:
            lbl = QLabel(f"{key}: -")
            lbl.setStyleSheet("font-size:12px;")
            self.position_rows[key] = lbl
            lay.addWidget(lbl)
        lay.addStretch(1)
        return panel

    def _build_operator_logs(self) -> QFrame:
        panel, lay = self._panel("")
        split = QSplitter(Qt.Horizontal)
        self.flow_terminal = QTextEdit(); self.flow_terminal.setReadOnly(True); self.flow_terminal.document().setMaximumBlockCount(120)
        self.trade_flow_terminal = QTextEdit(); self.trade_flow_terminal.setReadOnly(True); self.trade_flow_terminal.document().setMaximumBlockCount(120)
        left_box, ll = self._panel("MARKET FLOW"); ll.addWidget(self.flow_terminal)
        right_box, rl = self._panel("TRADE FLOW"); rl.addWidget(self.trade_flow_terminal)
        split.addWidget(left_box); split.addWidget(right_box)
        split.setSizes([860, 500])
        lay.addWidget(split)
        return panel

    def _build_engine_status(self) -> QFrame:
        panel, lay = self._panel("ENGINE STATUS")
        grid = QGridLayout(); grid.setSpacing(4)
        self.engine_lamps = {}
        for i, key in enumerate(["WS", "BOOK", "DEPTH", "DATA", "RISK", "PAPER", "LIFECYCLE"]):
            lbl = QLabel(key + " ●")
            lbl.setAlignment(Qt.AlignCenter)
            self._set_status_lamp(lbl, "gray")
            self.engine_lamps[key] = lbl
            grid.addWidget(lbl, i // 3, i % 3)
        lay.addLayout(grid)
        self.engine_block = QLabel("BLOCK: -")
        self.engine_block.setStyleSheet("font-size:11px;")
        self.engine_volume = QLabel("VOL24: -")
        self.engine_volume.setStyleSheet("font-size:10px;color:#7f92b8;")
        self.engine_metrics = QLabel("EVT 0 | OPEN 0 | CLOSED 0 | WR 0%")
        self.engine_metrics.setStyleSheet("font-size:12px;font-weight:700;color:#b7cff7;")
        lay.addWidget(self.engine_block)
        lay.addWidget(self.engine_volume)
        lay.addWidget(self.engine_metrics)
        lay.addStretch(1)
        return panel

    def _set_lamp(self, label: QLabel, active: bool) -> None:
        label.setStyleSheet(
            "padding:3px 5px;border-radius:6px;font-size:10px;font-weight:700;"
            + ("background:#1fd37d;color:#03160d;" if active else "background:#1a2235;color:#5f7397;")
        )

    def _set_check_lamp(self, label: QLabel, state: bool | None) -> None:
        color = "#2a3348" if state is None else ("#1ecb70" if state else "#ff6b6b")
        text_color = "#7185aa" if state is None else ("#04180f" if state else "#2b0000")
        label.setStyleSheet(f"font-size:10px;font-weight:700;padding:2px 4px;border-radius:5px;background:{color};color:{text_color};")

    def _set_status_lamp(self, label: QLabel, level: str) -> None:
        colors = {
            "green": ("#1ecb70", "#04180f"),
            "yellow": ("#f0b44d", "#231500"),
            "red": ("#ff6b6b", "#290000"),
            "gray": ("#2b3448", "#7385a9"),
        }
        bg, fg = colors[level]
        label.setStyleSheet(f"font-size:10px;font-weight:700;padding:3px 5px;border-radius:6px;background:{bg};color:{fg};")

    def render(self, snap: MarketSnapshot, sim: SimulationState) -> None:
        self.price_label.setText(f"{snap.price:,.2f}")
        self.price_label.setStyleSheet(f"font-size:30px;font-weight:800;color:{'#1ecb70' if snap.velocity >= 0 else '#ff6b6b'};")
        self.header_labels["SPREAD"].setText(f"SPREAD: {snap.spread:.2f}")
        self.header_labels["VEL"].setText(f"VEL: {snap.velocity:+.2f}/s")
        self.header_labels["EDGE"].setText(f"EDGE: {snap.edge_score:+.1f}")
        self.header_labels["S.EDGE"].setText(f"S.EDGE: {snap.smoothed_edge_score:+.1f}")
        self.header_labels["NET"].setText(f"NET: {snap.net_edge_score:+.1f}")
        self.header_labels["TPS"].setText(f"TPS: {snap.ticks_per_second:.1f}")
        self.header_labels["WS"].setText(f"WS: {snap.ws_status}")

        self.long_prob.setText(f"LONG {snap.long_probability:.1f}%")
        self.short_prob.setText(f"SHORT {snap.short_probability:.1f}%")
        self.dom_bar.setValue(int(max(0.0, min(100.0, snap.long_probability))))

        self._set_lamp(self.state_badges["BUY PRESSURE"], snap.buy_pressure > 0.58)
        self._set_lamp(self.state_badges["SELL PRESSURE"], snap.sell_pressure > 0.58)
        self._set_lamp(self.state_badges["COMPRESSION"], snap.spread < 2.0)
        self._set_lamp(self.state_badges["SWEEP"], max(snap.sweep_up, snap.sweep_down) > 0.35)
        self._set_lamp(self.state_badges["TRAP"], snap.trap > 0.35)
        self._set_lamp(self.state_badges["RECLAIM"], snap.reclaim > 0.35)
        self._set_lamp(self.state_badges["PANIC"], snap.panic > 0.45)

        checks = {
            "EDGE": snap.edge_score > 10,
            "PRESSURE": max(snap.buy_pressure, snap.sell_pressure) > 0.56,
            "SWEEP": max(snap.sweep_up, snap.sweep_down) > 0.3,
            "RECLAIM": snap.reclaim > 0.3,
            "BREAK EVEN": sim.net_pnl >= 0,
            "LIQUIDITY": snap.depth_status == "OK",
            "SPREAD": snap.spread < 2.5,
            "RISK GATE": snap.can_trade_data,
        }
        for key, ok in checks.items():
            self._set_check_lamp(self.check_labels[key], ok)

        block = snap.block_reason.upper() if snap.block_reason else "NONE"
        self.block_label.setText(f"BLOCK: {block}")
        self.block_label.setStyleSheet("color:#ff6b6b;font-weight:700;" if block != "NONE" else "color:#7f92b8;")

        active = sim.virtual_position != "Flat"
        self.position_status.setText(f"STATUS: {sim.lifecycle_state} | {'ACTIVE ' + sim.active_trade_side if active else 'WAITING SETUP'}")
        best_dir = "LONG" if snap.long_probability >= snap.short_probability else "SHORT"
        edge_pack = f"{snap.edge_score:+.1f} / {snap.smoothed_edge_score:+.1f} / {snap.net_edge_score:+.1f}"
        hold = sim.hold_seconds if active else sim.last_hold_seconds

        self.position_rows["BEST DIRECTION"].setText(f"BEST DIRECTION: {best_dir}")
        self.position_rows["EDGE PACK"].setText(f"EDGE / S.EDGE / NET: {edge_pack}")
        self.position_rows["TRIGGER"].setText(f"TRIGGER: {snap.trigger_strength:.1f}")
        self.position_rows["EXPECTED MOVE"].setText(f"EXPECTED MOVE: {snap.expected_move_ticks:+.2f} ticks")
        self.position_rows["BLOCK REASON"].setText(f"BLOCK REASON: {block}")

        self.position_rows["SIDE"].setText(f"SIDE: {sim.active_trade_side if active else '-'}")
        self.position_rows["ENTRY"].setText(f"ENTRY: {sim.entry:.2f}" if active else "ENTRY: -")
        self.position_rows["MARK"].setText(f"MARK: {snap.price:.2f}")
        self.position_rows["UPNL"].setText(f"UPNL: {sim.unrealized_pnl:+.2f}")
        self.position_rows["NET TICKS"].setText(f"NET TICKS: {sim.net_ticks:+.2f}")
        self.position_rows["HOLD"].setText(f"HOLD: {hold:.1f}s")
        self.position_rows["TP %"].setText(f"TP %: {sim.tp_progress:.0f}%")
        self.position_rows["SL %"].setText(f"SL %: {sim.sl_progress:.0f}%")
        self.position_rows["FEES / SLIPPAGE"].setText(f"FEES / SLIPPAGE: {sim.fees_paid:.2f} / {sim.avg_slippage:.3f}")

        flat_keys = ["BEST DIRECTION", "EDGE PACK", "TRIGGER", "EXPECTED MOVE", "BLOCK REASON"]
        active_keys = ["SIDE", "ENTRY", "MARK", "UPNL", "NET TICKS", "HOLD", "TP %", "SL %", "FEES / SLIPPAGE"]
        for key in flat_keys:
            self.position_rows[key].setVisible(not active)
        for key in active_keys:
            self.position_rows[key].setVisible(active)

        edge_bucket = int(round(snap.smoothed_edge_score / 10.0) * 10)
        market_flow_line = f"REGIME -> {snap.market_regime} | QUALITY -> {snap.signal_quality} | EDGE BUCKET -> {edge_bucket:+d} | NOISE -> {snap.noise_level}"
        trade_flow_line = f"WAITING SETUP | BLOCK: {block} | LAST CANDIDATE: {best_dir} {snap.signal_quality}"
        dedup_key = f"{snap.market_regime}:{snap.signal_quality}:{edge_bucket}:{snap.noise_level}:{block}:{sim.lifecycle_state}"
        if self._event_guard.should_emit("market_flow", dedup_key):
            self.flow_terminal.append(market_flow_line)
        if self._event_guard.should_emit("trade_flow_waiting", f"{block}:{best_dir}:{sim.trades}") and self._last_trade_event_idx == 0:
            self.trade_flow_terminal.append(trade_flow_line)
        new_events = sim.trade_events[self._last_trade_event_idx :]
        for event in new_events:
            self.trade_flow_terminal.append(event)
        self._last_trade_event_idx = len(sim.trade_events)

        book_ok = snap.book_status in {"OK", "OK_FALLBACK"}
        depth_ok = snap.depth_status == "OK"
        data_level = "green" if snap.can_trade_data else "red"
        risk_level = "green" if snap.can_trade_data and block == "NONE" else "yellow" if snap.can_trade_data else "red"

        self._set_status_lamp(self.engine_lamps["WS"], "green" if snap.ws_status.lower() == "live" else "yellow")
        book_level = "green" if snap.book_status == "OK" else ("yellow" if snap.book_status == "OK_FALLBACK" or snap.data_quality_reason == "WARMUP_BOOK" else "red")
        self._set_status_lamp(self.engine_lamps["BOOK"], book_level)
        self._set_status_lamp(self.engine_lamps["DEPTH"], "green" if depth_ok else "red")
        self._set_status_lamp(self.engine_lamps["DATA"], data_level)
        self._set_status_lamp(self.engine_lamps["RISK"], risk_level)
        self._set_status_lamp(self.engine_lamps["PAPER"], "green")
        lifecycle_level = "green" if sim.lifecycle_state in {"ACTIVE_POSITION", "PARTIAL_ENTRY"} else ("yellow" if sim.lifecycle_state in {"SETUP_CANDIDATE", "ENTRY_PENDING", "COOLDOWN", "EXITING"} else "gray")
        self._set_status_lamp(self.engine_lamps["LIFECYCLE"], lifecycle_level)
        self.engine_block.setText(f"BLOCK: {block if block != 'NONE' else snap.data_quality_reason.upper()}")
        streams = ",".join(snap.ws_streams_seen) if snap.ws_streams_seen else "-"
        self.engine_volume.setText(f"VOL24: {snap.volume_24h:,.0f} | BOOK AGE {snap.book_age_ms:.0f} ms | DEPTH AGE {snap.depth_age_ms:.0f} ms | STREAMS {streams}")
        self.engine_metrics.setText(
            f"EVT {sim.replay.events_processed} | OPEN {sim.opened_trades} | CLOSED {sim.closed_trades} | WR {sim.winrate:.1f}% | SESSION {sim.realized_pnl + sim.unrealized_pnl:+.2f} | LAST {sim.last_net_pnl:+.2f} | AVG {sim.avg_pnl:+.2f} | NET {sim.net_ticks:+.1f}t"
        )

        if sim.last_event in {"ENTRY", "TP", "SL", "EXIT", "TIMEOUT"}:
            effect = QGraphicsOpacityEffect(self.position_status)
            self.position_status.setGraphicsEffect(effect)
            pulse = QPropertyAnimation(effect, b"opacity", self)
            pulse.setDuration(260)
            pulse.setStartValue(0.3)
            pulse.setEndValue(1.0)
            pulse.setEasingCurve(QEasingCurve.OutCubic)
            pulse.start()

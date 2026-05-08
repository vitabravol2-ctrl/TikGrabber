from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor
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
        self.setWindowTitle("BTCUSDT Game Theory Engine v1.0.5 — Futures Command Center")
        self.resize(1920, 1080)
        self.setStyleSheet(
            "QWidget{background:#0a0f18;color:#d5def5;font-family:Consolas,Inter,Segoe UI;}"
            "QFrame{border:1px solid #1b2b44;border-radius:8px;background:#0f1726;}"
            "QLabel.title{font-weight:700;color:#7f9ed8;letter-spacing:0.7px;font-size:11px;}"
            "QProgressBar{border:none;background:#1a2438;height:10px;border-radius:5px;text-align:center;}"
            "QProgressBar::chunk{border-radius:5px;background:#2b8fff;}"
            "QTextEdit{background:#090f1a;border:1px solid #1b2b44;border-radius:7px;}"
        )
        self._event_guard = EventGuard()

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        outer.addWidget(self._build_market_header())

        center = QSplitter(Qt.Horizontal)
        center.setChildrenCollapsible(False)
        center.addWidget(self._build_market_control())
        center.addWidget(self._build_position_control())
        center.setStretchFactor(0, 5)
        center.setStretchFactor(1, 4)
        center.setSizes([1080, 780])
        outer.addWidget(center, 4)

        bottom = QSplitter(Qt.Horizontal)
        bottom.setChildrenCollapsible(False)
        bottom.addWidget(self._build_operator_logs())
        bottom.addWidget(self._build_engine_status())
        bottom.setStretchFactor(0, 7)
        bottom.setStretchFactor(1, 3)
        bottom.setSizes([1320, 540])
        outer.addWidget(bottom, 3)

        self.setCentralWidget(root)

    def _panel(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        t = QLabel(title)
        t.setProperty("class", "title")
        lay.addWidget(t)
        return frame, lay

    def _build_market_header(self) -> QFrame:
        panel, lay = self._panel("MARKET HEADER")
        row = QHBoxLayout()
        self.price_label = QLabel("0.00")
        self.price_label.setStyleSheet("font-size:34px;font-weight:800;")
        row.addWidget(self.price_label)
        self.header_labels = {}
        for key in ["SPREAD", "VELOCITY", "VOLUME", "EDGE", "SMOOTH EDGE", "NET EDGE", "TPS", "WS"]:
            v = QLabel(f"{key}: -")
            v.setStyleSheet("font-size:14px;font-weight:600;padding:3px 6px;background:#111d31;border:1px solid #223656;border-radius:6px;")
            self.header_labels[key] = v
            row.addWidget(v)
        row.addStretch(1)
        lay.addLayout(row)
        return panel

    def _build_market_control(self) -> QFrame:
        panel, lay = self._panel("MARKET CONTROL")
        probs = QFrame(); probs_l = QVBoxLayout(probs)
        self.long_prob = QLabel("LONG 50.0%")
        self.short_prob = QLabel("SHORT 50.0%")
        self.dom_bar = QProgressBar(); self.dom_bar.setRange(0, 100)
        probs_l.addWidget(self.long_prob); probs_l.addWidget(self.short_prob); probs_l.addWidget(self.dom_bar)
        lay.addWidget(probs)

        states, sl = self._panel("MARKET STATE LAMPS")
        grid = QGridLayout()
        self.state_badges = {}
        names = ["BUY PRESSURE", "SELL PRESSURE", "COMPRESSION", "SWEEP", "TRAP", "RECLAIM", "PANIC"]
        for i, name in enumerate(names):
            b = QLabel(name); b.setAlignment(Qt.AlignCenter)
            self.state_badges[name] = b
            self._set_lamp(b, False)
            grid.addWidget(b, i // 4, i % 4)
        sl.addLayout(grid)
        lay.addWidget(states)

        checks, cl = self._panel("SIGNAL CHECKLIST")
        self.check_labels = {}
        for key in ["EDGE", "PRESSURE", "SWEEP", "RECLAIM", "BREAK EVEN", "LIQUIDITY", "SPREAD", "RISK GATE"]:
            lbl = QLabel(f"{key:<12} [ ]")
            self.check_labels[key] = lbl
            cl.addWidget(lbl)
        self.block_label = QLabel("BLOCK: -")
        cl.addWidget(self.block_label)
        lay.addWidget(checks)
        return panel

    def _build_position_control(self) -> QFrame:
        panel, lay = self._panel("POSITION CONTROL")
        self.position_status = QLabel("STATUS: WAITING SETUP")
        self.position_status.setStyleSheet("font-size:18px;font-weight:800;color:#87a7e1;")
        lay.addWidget(self.position_status)
        self.position_rows = {}
        for key in ["CURRENT INTENT", "CURRENT EDGE", "TRIGGER STRENGTH", "BEST DIRECTION", "EXPECTED MOVE", "MIN PROFIT TICKS",
                    "ENTRY", "MARK", "UPNL", "NET PNL", "NET TICKS", "HOLD TIME", "TP LEVEL", "SL LEVEL", "EXEC QUALITY", "SLIPPAGE", "FEES"]:
            lbl = QLabel(f"{key}: -")
            self.position_rows[key] = lbl
            lay.addWidget(lbl)
        return panel

    def _build_operator_logs(self) -> QFrame:
        panel, lay = self._panel("OPERATOR LOGS")
        split = QSplitter(Qt.Horizontal)
        self.flow_terminal = QTextEdit(); self.flow_terminal.setReadOnly(True); self.flow_terminal.document().setMaximumBlockCount(100)
        self.trade_flow_terminal = QTextEdit(); self.trade_flow_terminal.setReadOnly(True); self.trade_flow_terminal.document().setMaximumBlockCount(100)
        left_box, ll = self._panel("MARKET FLOW"); ll.addWidget(self.flow_terminal)
        right_box, rl = self._panel("TRADE FLOW"); rl.addWidget(self.trade_flow_terminal)
        split.addWidget(left_box); split.addWidget(right_box)
        split.setSizes([680, 680])
        lay.addWidget(split)
        return panel

    def _build_engine_status(self) -> QFrame:
        panel, lay = self._panel("ENGINE STATUS")
        self.engine_rows = {}
        for key in ["WS", "BOOK", "DEPTH", "LATENCY", "DATA QUALITY", "REGIME", "QUALITY", "EDGE STABILITY", "NOISE LEVEL", "REPLAY MODE", "EVENTS", "TRADES", "WINRATE", "NET PNL"]:
            lbl = QLabel(f"{key}: -")
            self.engine_rows[key] = lbl
            lay.addWidget(lbl)
        return panel

    def _set_lamp(self, label: QLabel, active: bool) -> None:
        if active:
            label.setStyleSheet("padding:4px 6px;border-radius:6px;background:#1fd37d;color:#03160d;font-size:11px;font-weight:700;")
        else:
            label.setStyleSheet("padding:4px 6px;border-radius:6px;background:#1a2235;color:#5f7397;font-size:11px;")

    def render(self, snap: MarketSnapshot, sim: SimulationState) -> None:
        self.price_label.setText(f"{snap.price:,.2f}")
        self.price_label.setStyleSheet(f"font-size:34px;font-weight:800;color:{'#1ecb70' if snap.velocity >= 0 else '#ff6b6b'};")
        self.header_labels["SPREAD"].setText(f"SPREAD: {snap.spread:.2f}")
        self.header_labels["VELOCITY"].setText(f"VELOCITY: {snap.velocity:+.2f}/s")
        self.header_labels["VOLUME"].setText(f"VOLUME: {snap.volume_24h:,.0f}")
        self.header_labels["EDGE"].setText(f"EDGE: {snap.edge_score:+.1f}")
        self.header_labels["SMOOTH EDGE"].setText(f"SMOOTH EDGE: {snap.smoothed_edge_score:+.1f}")
        self.header_labels["NET EDGE"].setText(f"NET EDGE: {snap.net_edge_score:+.1f}")
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
            mark = "✓" if ok else "X"
            color = "#1ecb70" if ok else "#ff6b6b"
            self.check_labels[key].setText(f"{key:<12} [{mark}]")
            self.check_labels[key].setStyleSheet(f"color:{color};font-weight:600;")
        block = snap.block_reason.upper() if snap.block_reason else "NONE"
        self.block_label.setText(f"BLOCK: {block}")
        self.block_label.setStyleSheet("color:#ff6b6b;font-weight:700;" if block != "NONE" else "color:#7f92b8;")

        active = sim.virtual_position != "Flat"
        self.position_status.setText(f"STATUS: {'ACTIVE ' + sim.active_trade_side if active else 'WAITING SETUP'}")
        self.position_rows["CURRENT INTENT"].setText(f"CURRENT INTENT: {snap.market_intent}")
        self.position_rows["CURRENT EDGE"].setText(f"CURRENT EDGE: {snap.edge_score:+.1f} / {snap.smoothed_edge_score:+.1f}")
        self.position_rows["TRIGGER STRENGTH"].setText(f"TRIGGER STRENGTH: {snap.trigger_strength:.1f}")
        best_dir = "LONG" if snap.long_probability >= snap.short_probability else "SHORT"
        self.position_rows["BEST DIRECTION"].setText(f"BEST DIRECTION: {best_dir}")
        self.position_rows["EXPECTED MOVE"].setText(f"EXPECTED MOVE: {snap.expected_move_ticks:+.2f} ticks")
        self.position_rows["MIN PROFIT TICKS"].setText(f"MIN PROFIT TICKS: {snap.min_profitable_ticks:.2f}")

        mark = snap.price
        self.position_rows["ENTRY"].setText(f"ENTRY: {sim.entry:.2f}" if active else "ENTRY: -")
        self.position_rows["MARK"].setText(f"MARK: {mark:.2f}")
        self.position_rows["UPNL"].setText(f"UPNL: {sim.unrealized_pnl:+.2f}")
        self.position_rows["NET PNL"].setText(f"NET PNL: {sim.net_pnl:+.2f}")
        self.position_rows["NET TICKS"].setText(f"NET TICKS: {sim.net_ticks:+.2f}")
        hold = sim.hold_seconds if active else sim.last_hold_seconds
        self.position_rows["HOLD TIME"].setText(f"HOLD TIME: {hold:.1f}s")
        self.position_rows["TP LEVEL"].setText(f"TP LEVEL: {sim.tp_progress:.0f}% progress")
        self.position_rows["SL LEVEL"].setText(f"SL LEVEL: {sim.sl_progress:.0f}% progress")
        self.position_rows["EXEC QUALITY"].setText(f"EXEC QUALITY: {sim.execution_quality:.1f}")
        self.position_rows["SLIPPAGE"].setText(f"SLIPPAGE: {sim.avg_slippage:.3f}")
        self.position_rows["FEES"].setText(f"FEES: {sim.fees_paid:.2f}")

        market_flow_line = f"REGIME -> {snap.market_regime} | EDGE STABILIZED {snap.smoothed_edge_score:+.0f} | QUALITY {snap.signal_quality} | {snap.edge_stability} | NOISE {snap.noise_level}"
        trade_flow_line = f"{sim.last_event} | {sim.virtual_position} | NET {sim.last_net_pnl:+.2f} | HOLD {hold:.1f}s"
        if self._event_guard.should_emit("market_flow", f"{snap.market_regime}:{snap.signal_quality}:{snap.edge_stability}:{snap.noise_level}"):
            self.flow_terminal.append(market_flow_line)
        if self._event_guard.should_emit("trade_flow", f"{sim.last_event}:{sim.virtual_position}"):
            self.trade_flow_terminal.append(trade_flow_line)

        book_age_text = "-" if snap.book_age_ms >= 1e8 else f"{snap.book_age_ms:.0f} ms"
        depth_age_text = "-" if snap.depth_age_ms >= 1e8 else f"{snap.depth_age_ms:.0f} ms"
        self.engine_rows["WS"].setText(f"WS: {snap.ws_status}")
        self.engine_rows["BOOK"].setText(f"BOOK: {snap.book_status} ({book_age_text})")
        self.engine_rows["DEPTH"].setText(f"DEPTH: {snap.depth_status} ({depth_age_text})")
        self.engine_rows["LATENCY"].setText(f"LATENCY: {snap.latency_ms:.0f} ms")
        self.engine_rows["DATA QUALITY"].setText(f"DATA QUALITY: {snap.data_quality} / {snap.data_quality_reason}")
        self.engine_rows["REGIME"].setText(f"REGIME: {snap.market_regime}")
        self.engine_rows["QUALITY"].setText(f"QUALITY: {snap.signal_quality}")
        self.engine_rows["EDGE STABILITY"].setText(f"EDGE STABILITY: {snap.edge_stability}")
        self.engine_rows["NOISE LEVEL"].setText(f"NOISE LEVEL: {snap.noise_level}")
        self.engine_rows["REPLAY MODE"].setText(f"REPLAY MODE: {sim.replay.mode}")
        self.engine_rows["EVENTS"].setText(f"EVENTS: {sim.replay.events_processed}")
        self.engine_rows["TRADES"].setText(f"TRADES: {sim.trades}")
        self.engine_rows["WINRATE"].setText(f"WINRATE: {sim.winrate:.1f}%")
        self.engine_rows["NET PNL"].setText(f"NET PNL: {sim.realized_pnl + sim.unrealized_pnl:+.2f}")

        if sim.last_event in {"ENTRY", "TP", "SL"}:
            effect = QGraphicsOpacityEffect(self.position_status)
            self.position_status.setGraphicsEffect(effect)
            pulse = QPropertyAnimation(effect, b"opacity", self)
            pulse.setDuration(260)
            pulse.setStartValue(0.3)
            pulse.setEndValue(1.0)
            pulse.setEasingCurve(QEasingCurve.OutCubic)
            pulse.start()

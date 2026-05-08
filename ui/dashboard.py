from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import MarketSnapshot, SimulationState


class EdgeGauge(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.value = 0.0
        self.animated_value = 0.0
        self.setMinimumHeight(150)
        self.anim = QPropertyAnimation(self, b"gauge_value")
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_gauge_value(self) -> float:
        return self.animated_value

    def set_gauge_value(self, value: float) -> None:
        self.animated_value = value
        self.update()

    gauge_value = property(get_gauge_value, set_gauge_value)

    def set_value(self, value: float) -> None:
        self.value = max(-100.0, min(100.0, value))
        self.anim.stop()
        self.anim.setStartValue(self.animated_value)
        self.anim.setEndValue(self.value)
        self.anim.start()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)
        center = rect.center()
        radius = min(rect.width(), rect.height()) / 2 - 8

        painter.setPen(QPen(QColor("#1f2533"), 12))
        painter.drawEllipse(center, radius, radius)

        ratio = (self.animated_value + 100.0) / 200.0
        angle = int(360 * 16 * ratio)
        edge_color = QColor("#1ecb70") if self.animated_value >= 0 else QColor("#ff5a67")
        painter.setPen(QPen(edge_color, 12))
        painter.drawArc(rect.adjusted(8, 8, -8, -8), 90 * 16, -angle)

        painter.setPen(QColor("#dfe6ff"))
        painter.drawText(rect, Qt.AlignCenter, f"EDGE\n{self.animated_value:+.1f}")


class DashboardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BTCUSDT Game Theory Engine v0.7.1")
        self.resize(1240, 760)
        self.setStyleSheet(
            "QWidget{background:#0f1117;color:#d8deef;font-family:Inter,Segoe UI;}"
            "QFrame{border:1px solid #222d42;border-radius:10px;background:#131a25;}"
            "QProgressBar{border:none;background:#1b2231;height:16px;border-radius:8px;text-align:center;}"
            "QProgressBar::chunk{border-radius:8px;background:#4a8bff;}"
            "QLabel.title{font-weight:700;color:#96a8d8;letter-spacing:0.6px;font-size:12px;}"
        )

        root = QWidget()
        main = QVBoxLayout(root)
        main.setSpacing(10)
        main.setContentsMargins(10, 10, 10, 10)

        main.addWidget(self._build_top_panel())

        mid_split = QSplitter(Qt.Horizontal)
        mid_split.setChildrenCollapsible(False)
        mid_split.addWidget(self._build_left_col())
        mid_split.addWidget(self._build_center_col())
        mid_split.addWidget(self._build_right_col())
        mid_split.setSizes([380, 360, 360])
        main.addWidget(mid_split, 1)

        bottom_split = QSplitter(Qt.Horizontal)
        bottom_split.setChildrenCollapsible(False)
        bottom_split.addWidget(self._build_signal_flow_panel())
        bottom_split.addWidget(self._build_simulation_panel())
        bottom_split.setSizes([660, 560])
        main.addWidget(bottom_split, 1)

        self.setCentralWidget(root)

    def _panel(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        lay = QVBoxLayout(frame)
        lay.setSpacing(6)
        t = QLabel(title)
        t.setProperty("class", "title")
        t.setWordWrap(True)
        lay.addWidget(t)
        return frame, lay

    def _build_top_panel(self) -> QFrame:
        frame, lay = self._panel("PRICE TAPE")
        row = QHBoxLayout()
        self.price_label = QLabel("0.00")
        self.price_label.setStyleSheet("font-size:30px;font-weight:700;")
        self.spread_label = QLabel("Spread 0.00")
        self.velocity_label = QLabel("Vel +0.00/s")
        self.volatility_label = QLabel("Vol 0.00")
        for w in [self.price_label, self.spread_label, self.velocity_label, self.volatility_label]:
            row.addWidget(w)
        row.addStretch(1)
        lay.addLayout(row)
        return frame

    def _build_left_col(self) -> QWidget:
        col = QWidget(); lay = QVBoxLayout(col); lay.setSpacing(8)
        gauge_panel, gl = self._panel("MARKET PRESSURE / EDGE")
        self.gauge = EdgeGauge()
        self.trigger_bar = QProgressBar(); self.trigger_bar.setRange(0, 100)
        gl.addWidget(self.gauge)
        gl.addWidget(QLabel("TRIGGER STRENGTH"))
        gl.addWidget(self.trigger_bar)
        lay.addWidget(gauge_panel)

        dbg, dl = self._panel("SIGNAL CHECKLIST")
        self.debug_checks = {k: QLabel(f"• {k}: -") for k in ["EDGE", "RECLAIM", "SWEEP", "LOW SPREAD"]}
        for lbl in self.debug_checks.values():
            dl.addWidget(lbl)
        lay.addWidget(dbg)
        return col

    def _build_center_col(self) -> QWidget:
        col = QWidget(); lay = QVBoxLayout(col); lay.setSpacing(8)
        p, pl = self._panel("PRICE / INTENT")
        self.intent_label = QLabel("INTENT: BALANCED")
        self.signal_status = QLabel("SIGNAL: WAIT")
        self.intent_label.setWordWrap(True)
        self.signal_status.setWordWrap(True)
        pl.addWidget(self.intent_label)
        pl.addWidget(self.signal_status)
        lay.addWidget(p)

        states, sl = self._panel("MARKET STATES")
        badge_grid = QGridLayout()
        self.state_badges = {}
        for i, name in enumerate(["BUY_PRESSURE", "SWEEP_DOWN", "TRAP", "RECLAIM", "COMPRESSION"]):
            badge = QLabel(name)
            badge.setAlignment(Qt.AlignCenter)
            badge.setWordWrap(True)
            badge.setStyleSheet("padding:3px 6px;border-radius:6px;background:#2a2f3d;color:#7f8aa7;font-size:11px;")
            self.state_badges[name] = badge
            badge_grid.addWidget(badge, i // 2, i % 2)
        sl.addLayout(badge_grid)
        lay.addWidget(states)
        return col

    def _build_right_col(self) -> QWidget:
        col = QWidget(); lay = QVBoxLayout(col); lay.setSpacing(8)
        pr, prl = self._panel("PROBABILITIES")
        self.long_bar = QProgressBar(); self.long_bar.setRange(0, 100)
        self.short_bar = QProgressBar(); self.short_bar.setRange(0, 100)
        prl.addWidget(QLabel("LONG")); prl.addWidget(self.long_bar)
        prl.addWidget(QLabel("SHORT")); prl.addWidget(self.short_bar)
        lay.addWidget(pr)

        q, ql = self._panel("SIGNAL QUALITY")
        self.quality_label = QLabel("D")
        self.quality_label.setAlignment(Qt.AlignCenter)
        self.quality_label.setStyleSheet("font-size:44px;font-weight:800;color:#ff6b6b;")
        self.validation_label = QLabel("Validation: warming up")
        self.validation_label.setWordWrap(True)
        ql.addWidget(self.quality_label)
        ql.addWidget(self.validation_label)
        lay.addWidget(q)
        return col

    def _build_signal_flow_panel(self) -> QFrame:
        panel, lay = self._panel("MARKET FLOW")
        self.flow_terminal = QTextEdit()
        self.flow_terminal.setReadOnly(True)
        self.flow_terminal.document().setMaximumBlockCount(80)
        self.flow_terminal.setStyleSheet("background:#0c1018;border:1px solid #1f2b3d;border-radius:8px;")
        self.flow_terminal.setLineWrapMode(QTextEdit.WidgetWidth)
        lay.addWidget(self.flow_terminal)

        self.trade_flow_terminal = QTextEdit()
        self.trade_flow_terminal.setReadOnly(True)
        self.trade_flow_terminal.document().setMaximumBlockCount(80)
        self.trade_flow_terminal.setStyleSheet("background:#0c1018;border:1px solid #1f2b3d;border-radius:8px;")
        self.trade_flow_terminal.setLineWrapMode(QTextEdit.WidgetWidth)
        lay.addWidget(QLabel("TRADE FLOW"))
        lay.addWidget(self.trade_flow_terminal)
        return panel

    def _build_simulation_panel(self) -> QFrame:
        panel, lay = self._panel("SIMULATION CARDS")
        cards = QGridLayout()
        cards.setHorizontalSpacing(8)
        cards.setVerticalSpacing(8)
        card_order = ["trades", "winrate", "net_pnl", "net_ticks", "active_trade", "hold", "cooldown", "sig_per_h"]
        self.sim_cards = {k: QLabel("-") for k in card_order}
        for i, k in enumerate(card_order):
            lbl = self.sim_cards[k]
            box = QFrame(); box.setStyleSheet("QFrame{background:#0e1521;border:1px solid #2a3650;border-radius:8px;}")
            bl = QVBoxLayout(box)
            title = QLabel(k.replace("_", " ").upper())
            title.setWordWrap(True)
            bl.addWidget(title)
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            lbl.setStyleSheet("font-size:16px;font-weight:700;")
            bl.addWidget(lbl)
            cards.addWidget(box, i // 4, i % 4)
        lay.addLayout(cards)
        lay.addWidget(self._build_active_trade_panel())
        lay.addWidget(self._build_futures_status_panel())
        return panel

    def _build_active_trade_panel(self) -> QFrame:
        panel, lay = self._panel("ACTIVE TRADE")
        self.active_trade_summary = QLabel("FLAT BTCUSDT")
        self.active_trade_details = QLabel("Entry - | PnL - | Hold 0.0s")
        self.tp_progress_label = QLabel("TP progress 0%")
        self.sl_progress_label = QLabel("SL progress 0%")
        for w in [self.active_trade_summary, self.active_trade_details, self.tp_progress_label, self.sl_progress_label]:
            w.setWordWrap(True)
            lay.addWidget(w)
        return panel

    def _build_futures_status_panel(self) -> QFrame:
        panel, lay = self._panel("FUTURES STATUS")
        self.futures_status = {
            "mode": QLabel("Mode: REALISTIC PAPER"),
            "leverage": QLabel("Leverage: 1x"),
            "execution": QLabel("Execution: SIMULATED"),
            "fees": QLabel("Fees: ON"),
            "slippage": QLabel("Slippage: ON"),
        }
        for lbl in self.futures_status.values():
            lbl.setWordWrap(True)
            lay.addWidget(lbl)
        return panel

    def _set_badge_state(self, label: QLabel, active: bool) -> None:
        if active:
            label.setStyleSheet("padding:3px 6px;border-radius:6px;background:#1ecb70;color:#02160a;font-weight:700;font-size:11px;")
        else:
            label.setStyleSheet("padding:3px 6px;border-radius:6px;background:#2a2f3d;color:#7f8aa7;font-size:11px;")

    def render(self, snap: MarketSnapshot, sim: SimulationState) -> None:
        self.price_label.setText(f"{snap.price:,.2f}")
        self.price_label.setStyleSheet(f"font-size:30px;font-weight:700;color:{'#1ecb70' if snap.velocity >= 0 else '#ff6b6b'};")
        self.spread_label.setText(f"Spread {snap.spread:.2f}")
        self.velocity_label.setText(f"Vel {snap.velocity:+.2f}/s")
        self.volatility_label.setText(f"Vol {abs(snap.sweep_up - snap.sweep_down):.2f}")

        self.long_bar.setValue(int(snap.long_probability))
        self.short_bar.setValue(int(snap.short_probability))
        self.intent_label.setText(f"INTENT: {snap.market_intent}")
        self.signal_status.setText(f"SIGNAL: {sim.last_signal}")
        self.gauge.set_value(snap.edge_score)
        self.trigger_bar.setValue(int(max(0, min(100, snap.trigger_strength))))

        quality = sim.analytics.current_signal_quality or "D"
        quality_colors = {"A+": "#00e08a", "A": "#1ecb70", "B": "#56d66f", "C": "#f5c542", "D": "#ff6b6b"}
        self.quality_label.setText(quality if quality in quality_colors else "D")
        self.quality_label.setStyleSheet(f"font-size:44px;font-weight:800;color:{quality_colors.get(quality, '#ff6b6b')};")
        self.validation_label.setText(f"Validation: conf {sim.analytics.signal_confidence:.1f}% | data {snap.data_quality}")

        self.sim_cards["trades"].setText(str(sim.trades))
        self.sim_cards["winrate"].setText(f"{sim.winrate:.1f}%")
        self.sim_cards["net_pnl"].setText(f"{sim.net_pnl:+.2f}")
        self.sim_cards["net_ticks"].setText(f"{sim.net_ticks:+.1f}")
        self.sim_cards["cooldown"].setText(f"{sim.cooldown_seconds_left:.1f}s" if sim.cooldown_active else "READY")
        self.sim_cards["active_trade"].setText(f"{sim.active_trade_side} @ {sim.entry:.2f}" if sim.active_trade_side != "-" else "-")
        self.sim_cards["hold"].setText(f"{sim.hold_seconds:.1f}s")
        self.sim_cards["sig_per_h"].setText(f"acc {sim.signals_per_hour:.1f} | trd {sim.trades_per_hour:.1f}")

        if sim.virtual_position != "Flat":
            self.active_trade_summary.setText(f"ACTIVE: {sim.active_trade_side} BTCUSDT")
            self.active_trade_details.setText(f"Entry {sim.entry:.2f} | Mark {snap.price:.2f} | Unrealized {sim.pnl_ticks:+.1f} ticks | Hold {sim.hold_seconds:.1f}s")
            self.tp_progress_label.setText(f"TP progress {sim.tp_progress:.0f}%")
            self.sl_progress_label.setText(f"SL progress {sim.sl_progress:.0f}%")
        else:
            self.active_trade_summary.setText("FLAT")
            self.active_trade_details.setText(f"Last {sim.last_closed_side} {sim.last_close_reason} | Entry {sim.last_entry_price:.2f} -> Exit {sim.last_exit_price:.2f} | Net {sim.last_net_pnl:+.2f}")
            self.tp_progress_label.setText(f"Cooldown {sim.cooldown_seconds_left:.1f}s" if sim.cooldown_active else "Ready")
            self.sl_progress_label.setText("Waiting setup")

        self._set_badge_state(self.state_badges["BUY_PRESSURE"], snap.buy_pressure > 0.58)
        self._set_badge_state(self.state_badges["SWEEP_DOWN"], snap.sweep_down > 0.35)
        self._set_badge_state(self.state_badges["TRAP"], snap.trap > 0.35)
        self._set_badge_state(self.state_badges["RECLAIM"], snap.reclaim > 0.35)
        self._set_badge_state(self.state_badges["COMPRESSION"], snap.spread < 2.0)

        checks = {
            "EDGE": snap.edge_score > 10,
            "RECLAIM": snap.reclaim > 0.3,
            "SWEEP": snap.sweep_down > 0.3,
            "LOW SPREAD": snap.spread < 2.5,
        }
        for key, ok in checks.items():
            mark = "✔" if ok else "✖"
            color = "#1ecb70" if ok else "#ff6b6b"
            self.debug_checks[key].setText(f"{mark} {key}")
            self.debug_checks[key].setStyleSheet(f"color:{color};font-weight:600;")

        block = snap.block_reason.upper() if snap.block_reason else "SHORT"
        entry_text = f"{sim.entry:.2f}" if sim.virtual_position != "Flat" else "-"
        market_flow_line = f"STATE {snap.market_intent[:12]} | EDGE {snap.edge_score:+.0f} | BLOCK {block[:14]} | SIGNAL {sim.last_signal} | STR {snap.trigger_strength:.1f}"
        trade_flow_line = f"EVENT {sim.last_event} | POS {sim.virtual_position} | E {entry_text} | LX {sim.last_exit_price:.2f if sim.last_exit_price else 0.0} | NET {sim.last_net_pnl:+.2f} | FEES {sim.fees_paid:.2f} | HOLD {sim.hold_seconds:.1f}s"
        trade_flow_line = trade_flow_line.replace("LX 0.00", "LX -")
        self.flow_terminal.append(market_flow_line)
        self.trade_flow_terminal.append(trade_flow_line)

        self.futures_status["mode"].setText("Mode: REALISTIC PAPER")
        self.futures_status["leverage"].setText("Leverage: 1x")
        self.futures_status["execution"].setText("Execution: SIMULATED")
        self.futures_status["fees"].setText("Fees: ON")
        self.futures_status["slippage"].setText("Slippage: ON")

        if sim.last_event in {"ENTRY", "TP", "SL"}:
            effect = QGraphicsOpacityEffect(self.signal_status)
            self.signal_status.setGraphicsEffect(effect)
            pulse = QPropertyAnimation(effect, b"opacity", self)
            pulse.setDuration(260)
            pulse.setStartValue(0.3)
            pulse.setEndValue(1.0)
            pulse.start()

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
        self.setWindowTitle("BTCUSDT Game Theory Engine v0.7")
        self.resize(1240, 760)
        self.setStyleSheet(
            "QWidget{background:#0f1117;color:#d8deef;font-family:Inter,Segoe UI;}"
            "QFrame{border:1px solid #232b3d;border-radius:10px;background:#131a25;}"
            "QProgressBar{border:none;background:#1b2231;height:16px;border-radius:8px;text-align:center;}"
            "QProgressBar::chunk{border-radius:8px;background:#4a8bff;}"
            "QLabel.title{font-weight:700;color:#96a8d8;letter-spacing:0.5px;}"
        )

        root = QWidget()
        main = QVBoxLayout(root)
        main.setSpacing(8)
        main.setContentsMargins(8, 8, 8, 8)

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
        bottom_split.setSizes([720, 500])
        main.addWidget(bottom_split, 1)

        self.setCentralWidget(root)

    def _panel(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        lay = QVBoxLayout(frame)
        lay.setSpacing(6)
        t = QLabel(title)
        t.setProperty("class", "title")
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
        pl.addWidget(self.intent_label)
        pl.addWidget(self.signal_status)
        lay.addWidget(p)

        states, sl = self._panel("MARKET STATES")
        badge_grid = QGridLayout()
        self.state_badges = {}
        for i, name in enumerate(["BUY_PRESSURE", "SWEEP_DOWN", "TRAP", "RECLAIM", "COMPRESSION"]):
            badge = QLabel(name)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet("padding:4px 6px;border-radius:6px;background:#2a2f3d;color:#7f8aa7;")
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
        ql.addWidget(self.quality_label)
        ql.addWidget(self.validation_label)
        lay.addWidget(q)
        return col

    def _build_signal_flow_panel(self) -> QFrame:
        panel, lay = self._panel("SIGNAL FLOW")
        self.flow_terminal = QTextEdit()
        self.flow_terminal.setReadOnly(True)
        self.flow_terminal.document().setMaximumBlockCount(80)
        self.flow_terminal.setStyleSheet("background:#0c1018;border:1px solid #1f2b3d;border-radius:8px;")
        lay.addWidget(self.flow_terminal)
        return panel

    def _build_simulation_panel(self) -> QFrame:
        panel, lay = self._panel("SIMULATION CARDS")
        cards = QGridLayout()
        self.sim_cards = {k: QLabel("-") for k in ["mode", "trades", "winrate", "pnl_ticks", "gross_pnl", "fees", "net_pnl", "net_ticks", "cooldown", "active_trade", "hold", "tp_sl", "sig_per_h", "avg_strength", "last_trade"]}
        for i, (k, lbl) in enumerate(self.sim_cards.items()):
            box = QFrame(); box.setStyleSheet("QFrame{background:#0e1521;border:1px solid #2a3650;border-radius:8px;}")
            bl = QVBoxLayout(box)
            bl.addWidget(QLabel(k.replace("_", " ").upper()))
            lbl.setStyleSheet("font-size:18px;font-weight:700;")
            bl.addWidget(lbl)
            cards.addWidget(box, i // 2, i % 2)
        lay.addLayout(cards)
        return panel

    def _set_badge_state(self, label: QLabel, active: bool) -> None:
        if active:
            label.setStyleSheet("padding:4px 6px;border-radius:6px;background:#1ecb70;color:#02160a;font-weight:700;")
        else:
            label.setStyleSheet("padding:4px 6px;border-radius:6px;background:#2a2f3d;color:#7f8aa7;")

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
        quality_colors = {"A": "#1ecb70", "B": "#56d66f", "C": "#f5c542", "D": "#ff6b6b"}
        self.quality_label.setText(quality)
        self.quality_label.setStyleSheet(f"font-size:44px;font-weight:800;color:{quality_colors.get(quality, '#ff6b6b')};")
        self.validation_label.setText(f"Validation: conf {sim.analytics.signal_confidence:.1f}% | data {snap.data_quality}")

        self.sim_cards["mode"].setText(sim.mode)
        self.sim_cards["trades"].setText(str(sim.trades))
        self.sim_cards["winrate"].setText(f"{sim.winrate:.1f}%")
        self.sim_cards["pnl_ticks"].setText(f"{sim.pnl_ticks:+.1f}")
        self.sim_cards["gross_pnl"].setText(f"{sim.gross_pnl:+.2f}")
        self.sim_cards["fees"].setText(f"-{sim.fees_paid:.2f}")
        self.sim_cards["net_pnl"].setText(f"{sim.net_pnl:+.2f}")
        self.sim_cards["net_ticks"].setText(f"{sim.net_ticks:+.1f}")
        self.sim_cards["cooldown"].setText(f"{sim.cooldown_seconds_left:.1f}s" if sim.cooldown_active else "READY")
        self.sim_cards["active_trade"].setText(f"{sim.active_trade_side} @ {sim.entry:.2f}" if sim.active_trade_side != "-" else "-")
        self.sim_cards["hold"].setText(f"{sim.hold_seconds:.1f}s")
        self.sim_cards["tp_sl"].setText(f"TP {sim.tp_progress:.0f}% / SL {sim.sl_progress:.0f}%")
        self.sim_cards["sig_per_h"].setText(f"{sim.signals_per_hour:.1f} / {sim.trades_per_hour:.1f}")
        self.sim_cards["avg_strength"].setText(f"{sim.avg_signal_strength:.1f}%")
        self.sim_cards["last_trade"].setText(sim.last_trade_result)

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

        flow_line = (
            f"[STATE:{snap.market_intent}] [EDGE:{snap.edge_score:+.1f}] [BLOCK:{snap.block_reason or '-'}] "
            f"[SIGNAL:{sim.last_signal}] [ENTRY:{sim.entry:.2f}] [EXIT:{sim.exit_price:.2f}]"
        )
        self.flow_terminal.append(flow_line)

        if sim.last_event in {"ENTRY", "TP", "SL"}:
            effect = QGraphicsOpacityEffect(self.signal_status)
            self.signal_status.setGraphicsEffect(effect)
            pulse = QPropertyAnimation(effect, b"opacity", self)
            pulse.setDuration(260)
            pulse.setStartValue(0.3)
            pulse.setEndValue(1.0)
            pulse.start()

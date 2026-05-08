from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from core.models import MarketSnapshot, SimulationState


class EdgeGauge(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.value = 0.0
        self.setMinimumHeight(130)

    def set_value(self, value: float) -> None:
        self.value = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)
        painter.setPen(QColor("#2d2d39"))
        painter.setBrush(QColor("#15171d"))
        painter.drawEllipse(rect)
        color = QColor("#1ecb70") if self.value >= 0 else QColor("#ff4d4d")
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignCenter, f"EDGE\n{self.value:+.1f}")


class DashboardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BTCUSDT Game Theory Engine v0.4")
        self.resize(1380, 900)
        self.setStyleSheet("QWidget{background:#0f1117;color:#e6e6e6;font-family:Inter,Segoe UI;} QFrame{border:1px solid #202535;border-radius:10px;background:#131722;} QProgressBar{border:none;background:#1a1f2c;height:22px;border-radius:10px;} QProgressBar::chunk{border-radius:10px;background:#1ecb70;}")

        root = QWidget()
        grid = QGridLayout(root)
        grid.setSpacing(12)

        self.price_label = QLabel("0.00")
        self.price_label.setStyleSheet("font-size:56px;font-weight:700;")
        self.spread_label = QLabel("Spread: 0.00")
        self.velocity_label = QLabel("Velocity: 0.00")
        grid.addWidget(self._panel("PRICE PANEL", [self.price_label, self.spread_label, self.velocity_label]), 0, 0, 1, 2)

        self.gauge = EdgeGauge()
        self.edge_history_bar = QProgressBar()
        self.edge_history_bar.setRange(0, 100)
        grid.addWidget(self._panel("EDGE PANEL", [self.gauge, QLabel("EDGE HISTORY"), self.edge_history_bar]), 1, 0)

        self.long_bar = QProgressBar()
        self.short_bar = QProgressBar()
        self.long_bar.setRange(0, 100)
        self.short_bar.setRange(0, 100)
        self.intent_label = QLabel("MARKET INTENT: Neutral")
        grid.addWidget(self._panel("GAME THEORY", [QLabel("LONG PROBABILITY"), self.long_bar, QLabel("SHORT PROBABILITY"), self.short_bar, self.intent_label]), 1, 1)

        self.sim_labels = {k: QLabel("-") for k in ["mode", "last_signal", "virtual_position", "entry", "exit_price", "last_trade_result", "winrate", "avg_pnl", "avg_hold_seconds", "long_winrate", "short_winrate", "trades", "wins", "losses"]}
        sim_widgets = []
        for key in ["mode", "last_signal", "virtual_position", "entry", "exit_price", "last_trade_result", "trades", "wins", "losses", "winrate", "avg_pnl", "avg_hold_seconds", "long_winrate", "short_winrate"]:
            sim_widgets += [QLabel(key.replace("_", " ").title()), self.sim_labels[key]]
        grid.addWidget(self._panel("SIMULATION STATUS", sim_widgets), 2, 0, 1, 2)

        self.analytics_labels = {k: QLabel("-") for k in ["best_signal", "worst_signal", "quality", "confidence", "best_market", "best_combo", "worst_combo"]}
        self.analytics_labels["quality"].setStyleSheet("font-size:34px;font-weight:700;color:#f5c542;")
        grid.addWidget(self._panel("SIGNAL ANALYTICS", [QLabel("BEST SIGNAL TYPE"), self.analytics_labels["best_signal"], QLabel("WORST SIGNAL TYPE"), self.analytics_labels["worst_signal"], QLabel("CURRENT SIGNAL QUALITY"), self.analytics_labels["quality"], QLabel("SIGNAL CONFIDENCE"), self.analytics_labels["confidence"], QLabel("BEST MARKET CONDITION"), self.analytics_labels["best_market"], QLabel("BEST CONDITIONS HEATMAP"), self.analytics_labels["best_combo"], QLabel("WORST CONDITIONS HEATMAP"), self.analytics_labels["worst_combo"]]), 3, 0)

        self.status_labels = {k: QLabel("-") for k in ["ws_status", "latency", "tps", "quality"]}
        grid.addWidget(self._panel("DATA STATUS", [QLabel("WS STATUS"), self.status_labels["ws_status"], QLabel("LATENCY"), self.status_labels["latency"], QLabel("TICKS/SEC"), self.status_labels["tps"], QLabel("DATA QUALITY"), self.status_labels["quality"]]), 3, 1)

        self.debug_labels = {k: QLabel("-") for k in ["long", "short", "block", "strength"]}
        grid.addWidget(self._panel("SIGNAL DEBUG PANEL", [QLabel("LONG CHECK"), self.debug_labels["long"], QLabel("SHORT CHECK"), self.debug_labels["short"], QLabel("BLOCKERS"), self.debug_labels["block"], QLabel("TRIGGER STRENGTH"), self.debug_labels["strength"]]), 4, 0, 1, 2)

        self.setCentralWidget(root)

    def _panel(self, title: str, widgets: list[QWidget]) -> QFrame:
        frame = QFrame()
        lay = QVBoxLayout(frame)
        lay.addWidget(QLabel(f"<b>{title}</b>"))
        for w in widgets:
            lay.addWidget(w)
        return frame

    def render(self, snap: MarketSnapshot, sim: SimulationState) -> None:
        self.price_label.setText(f"{snap.price:,.2f}")
        self.price_label.setStyleSheet(f"font-size:56px;font-weight:700;color:{'#1ecb70' if snap.velocity >=0 else '#ff4d4d'};")
        self.spread_label.setText(f"Spread: {snap.spread:.2f}")
        self.velocity_label.setText(f"Velocity: {snap.velocity:+.2f}/s")
        self.long_bar.setValue(int(snap.long_probability))
        self.short_bar.setValue(int(snap.short_probability))
        self.intent_label.setText(f"MARKET INTENT: {snap.market_intent}")
        self.gauge.set_value(snap.edge_score)

        self.sim_labels["mode"].setText(sim.mode)
        self.sim_labels["last_signal"].setText(sim.last_signal)
        self.sim_labels["virtual_position"].setText(sim.virtual_position)
        self.sim_labels["entry"].setText(f"{sim.entry:.2f}")
        self.sim_labels["exit_price"].setText(f"{sim.exit_price:.2f}")
        self.sim_labels["last_trade_result"].setText(sim.last_trade_result)
        self.sim_labels["trades"].setText(str(sim.trades))
        self.sim_labels["wins"].setText(str(sim.wins))
        self.sim_labels["losses"].setText(str(sim.losses))
        self.sim_labels["winrate"].setText(f"{sim.winrate:.1f}%")
        self.sim_labels["avg_pnl"].setText(f"{sim.avg_pnl:+.2f} ticks")
        self.sim_labels["avg_hold_seconds"].setText(f"{sim.avg_hold_seconds:.1f}s")
        self.sim_labels["long_winrate"].setText(f"{sim.long_winrate:.1f}%")
        self.sim_labels["short_winrate"].setText(f"{sim.short_winrate:.1f}%")

        edge_strength = min(100, int(abs(sum(sim.edge_history[-10:]) / max(1, len(sim.edge_history[-10:]))) ))
        self.edge_history_bar.setValue(edge_strength)

        self.analytics_labels["best_signal"].setText(sim.analytics.best_signal_type)
        self.analytics_labels["worst_signal"].setText(sim.analytics.worst_signal_type)
        self.analytics_labels["quality"].setText(sim.analytics.current_signal_quality)
        self.analytics_labels["confidence"].setText(f"{sim.analytics.signal_confidence:.1f}%")
        self.analytics_labels["best_market"].setText(sim.analytics.best_market_condition)
        self.analytics_labels["best_combo"].setText(sim.analytics.best_combo)
        self.analytics_labels["worst_combo"].setText(sim.analytics.worst_combo)

        self.status_labels["ws_status"].setText(snap.ws_status)
        self.status_labels["latency"].setText(f"{snap.latency_ms:.0f} ms")
        self.status_labels["tps"].setText(f"{snap.ticks_per_second:.1f}")
        self.status_labels["quality"].setText(snap.data_quality)

        self.debug_labels["long"].setText(snap.long_debug or "-")
        self.debug_labels["short"].setText(snap.short_debug or "-")
        self.debug_labels["block"].setText(snap.block_reason or "-")
        self.debug_labels["strength"].setText(f"{snap.trigger_strength:.1f}%")

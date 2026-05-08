from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
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
        self.setWindowTitle("BTCUSDT Game Theory Engine v0.1")
        self.resize(1200, 760)
        self.setStyleSheet("QWidget{background:#0f1117;color:#e6e6e6;font-family:Inter,Segoe UI;} QFrame{border:1px solid #202535;border-radius:10px;background:#131722;} QProgressBar{border:none;background:#1a1f2c;height:22px;border-radius:10px;} QProgressBar::chunk{border-radius:10px;background:#1ecb70;}")

        root = QWidget()
        grid = QGridLayout(root)
        grid.setSpacing(12)

        self.price_label = QLabel("0.00")
        self.price_label.setStyleSheet("font-size:56px;font-weight:700;")
        self.spread_label = QLabel("Spread: 0.00")
        self.velocity_label = QLabel("Velocity: 0.00")
        grid.addWidget(self._panel("PRICE PANEL", [self.price_label, self.spread_label, self.velocity_label]), 0, 0, 1, 2)

        self.pressure_bar = QProgressBar()
        self.pressure_bar.setRange(0, 100)
        self.pressure_bar.setValue(50)
        self.pressure_label = QLabel("SELL <=====> BUY | 50/50")
        grid.addWidget(self._panel("MARKET PRESSURE", [self.pressure_label, self.pressure_bar]), 1, 0, 1, 2)

        self.signal_labels = {k: QLabel(k.upper()) for k in ["sweep_down", "sweep_up", "trap", "reclaim", "panic"]}
        for label in self.signal_labels.values():
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumHeight(34)
            label.setStyleSheet("background:#1b2130;border-radius:8px;")
        grid.addWidget(self._panel("LIQUIDITY / TRAP", list(self.signal_labels.values())), 2, 0)

        self.long_bar = QProgressBar()
        self.short_bar = QProgressBar()
        self.long_bar.setRange(0, 100)
        self.short_bar.setRange(0, 100)
        self.intent_label = QLabel("MARKET INTENT: Neutral")
        grid.addWidget(self._panel("GAME THEORY", [QLabel("LONG PROBABILITY"), self.long_bar, QLabel("SHORT PROBABILITY"), self.short_bar, self.intent_label]), 2, 1)

        self.gauge = EdgeGauge()
        grid.addWidget(self._panel("EDGE PANEL", [self.gauge]), 3, 0)

        self.sim_labels = {k: QLabel("-") for k in ["virtual_position", "entry", "pnl_ticks", "winrate", "trades_count"]}
        sim_widgets = []
        for key, widget in self.sim_labels.items():
            sim_widgets += [QLabel(key.replace("_", " ").title()), widget]
        grid.addWidget(self._panel("SIMULATION", sim_widgets), 3, 1)

        self.status_labels = {k: QLabel("-") for k in ["ws_status", "latency", "tps", "quality"]}
        grid.addWidget(self._panel("DATA STATUS", [QLabel("WS STATUS"), self.status_labels["ws_status"], QLabel("LATENCY"), self.status_labels["latency"], QLabel("TICKS/SEC"), self.status_labels["tps"], QLabel("DATA QUALITY"), self.status_labels["quality"]]), 4, 0, 1, 2)

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

        buy = int(snap.buy_pressure * 100)
        self.pressure_bar.setValue(buy)
        self.pressure_label.setText(f"SELL <=====> BUY | {100-buy}/{buy}")

        for key, val in [("sweep_down", snap.sweep_down), ("sweep_up", snap.sweep_up), ("trap", snap.trap), ("reclaim", snap.reclaim), ("panic", snap.panic)]:
            alpha = int(30 + val * 200)
            color = "255,77,77" if key in {"panic", "sweep_down", "trap"} else "30,203,112"
            self.signal_labels[key].setStyleSheet(f"background:rgba({color},{alpha});border-radius:8px;")

        self.long_bar.setValue(int(snap.long_probability))
        self.short_bar.setValue(int(snap.short_probability))
        self.intent_label.setText(f"MARKET INTENT: {snap.market_intent}")
        self.gauge.set_value(snap.edge_score)

        self.sim_labels["virtual_position"].setText(sim.virtual_position)
        self.sim_labels["entry"].setText(f"{sim.entry:.2f}")
        self.sim_labels["pnl_ticks"].setText(f"{sim.pnl_ticks:+.2f}")
        self.sim_labels["winrate"].setText(f"{sim.winrate:.1f}%")
        self.sim_labels["trades_count"].setText(str(sim.trades_count))

        self.status_labels["ws_status"].setText(snap.ws_status)
        self.status_labels["latency"].setText(f"{snap.latency_ms:.0f} ms")
        self.status_labels["tps"].setText(f"{snap.ticks_per_second:.1f}")
        self.status_labels["quality"].setText(snap.data_quality)

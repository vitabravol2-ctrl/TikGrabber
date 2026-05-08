from __future__ import annotations

from time import time

from core.models import MarketSnapshot, SimulationState
from signal_engine import TradeSignal


class PaperSimulator:
    def __init__(self, tick_size: float = 0.10, tp_ticks: int = 2, sl_ticks: int = 2, timeout_seconds: float = 20.0) -> None:
        self.state = SimulationState()
        self.tick_size = tick_size
        self.tp_ticks = tp_ticks
        self.sl_ticks = sl_ticks
        self.timeout_seconds = timeout_seconds
        self._entry_ts = 0.0
        self._entry_side = ""
        self._pnl_sum = 0.0
        self._hold_sum = 0.0

    def step(self, snap: MarketSnapshot, signal: TradeSignal) -> SimulationState:
        now = time()
        self.state.last_signal = signal.value
        self.state.edge_history.append(snap.edge_score)
        self.state.edge_history = self.state.edge_history[-40:]

        if self.state.virtual_position == "Flat" and signal != TradeSignal.NO_SIGNAL:
            self._open_trade(snap.price, signal, now)
        elif self.state.virtual_position != "Flat":
            self._update_open_trade(snap.price, now)
        return self.state

    def _open_trade(self, price: float, signal: TradeSignal, now: float) -> None:
        is_long = signal == TradeSignal.LONG_SIGNAL
        self.state.virtual_position = "Long" if is_long else "Short"
        self.state.entry = price
        self._entry_ts = now
        self._entry_side = self.state.virtual_position
        self.state.trades += 1
        if is_long:
            self.state.long_trades += 1
        else:
            self.state.short_trades += 1

    def _update_open_trade(self, price: float, now: float) -> None:
        direction = 1 if self.state.virtual_position == "Long" else -1
        self.state.pnl_ticks = (price - self.state.entry) / self.tick_size * direction
        self.state.hold_seconds = now - self._entry_ts

        if self.state.pnl_ticks >= self.tp_ticks:
            self._close_trade(price, "TP", now)
        elif self.state.pnl_ticks <= -self.sl_ticks:
            self._close_trade(price, "SL", now)
        elif self.state.hold_seconds >= self.timeout_seconds:
            self._close_trade(price, "TIMEOUT", now)

    def _close_trade(self, price: float, reason: str, now: float) -> None:
        pnl_ticks = self.state.pnl_ticks
        won = pnl_ticks > 0
        hold = now - self._entry_ts

        self.state.exit_price = price
        self.state.last_trade_result = f"{self._entry_side} {reason} {pnl_ticks:+.1f} ticks"
        self.state.wins += 1 if won else 0
        self.state.losses += 0 if won else 1
        self.state.long_wins += 1 if won and self._entry_side == "Long" else 0
        self.state.short_wins += 1 if won and self._entry_side == "Short" else 0

        self._pnl_sum += pnl_ticks
        self._hold_sum += hold
        self.state.winrate = self.state.wins / self.state.trades * 100.0
        self.state.avg_pnl = self._pnl_sum / self.state.trades
        self.state.avg_hold_seconds = self._hold_sum / self.state.trades
        self.state.long_winrate = self.state.long_wins / self.state.long_trades * 100.0 if self.state.long_trades else 0.0
        self.state.short_winrate = self.state.short_wins / self.state.short_trades * 100.0 if self.state.short_trades else 0.0

        self.state.virtual_position = "Flat"
        self.state.entry = 0.0
        self.state.pnl_ticks = 0.0
        self.state.hold_seconds = 0.0

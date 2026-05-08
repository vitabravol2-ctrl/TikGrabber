from __future__ import annotations

from collections import defaultdict
from time import time

from core.models import MarketSnapshot, SimulationState
from signal_engine import TradeSignal
from simulation.execution_model import ExecutionModel


class PaperSimulator:
    def __init__(
        self,
        tick_size: float = 0.10,
        tp_ticks: int = 2,
        sl_ticks: int = 2,
        timeout_seconds: float = 20.0,
        cooldown_seconds: float = 4.0,
        min_hold_ms: int = 700,
        anti_spam_edge_delta: float = 1.0,
        on_trade_closed=None,
    ) -> None:
        self.state = SimulationState()
        self.tick_size = tick_size
        self.tp_ticks = tp_ticks
        self.sl_ticks = sl_ticks
        self.timeout_seconds = timeout_seconds
        self.cooldown_seconds = cooldown_seconds
        self.min_hold_seconds = min_hold_ms / 1000.0
        self.anti_spam_edge_delta = anti_spam_edge_delta
        self.execution = ExecutionModel(tick_size=tick_size)

        self._entry_ts = 0.0
        self._entry_side = ""
        self._entry_fees = 0.0
        self._pnl_sum = 0.0
        self._hold_sum = 0.0
        self._current_signal_id: int | None = None
        self._used_signal_ids: set[int] = set()
        self._on_trade_closed = on_trade_closed
        self._started_at = time()
        self._signal_strength_sum = 0.0
        self._strength_total: dict[str, int] = defaultdict(int)
        self._strength_wins: dict[str, int] = defaultdict(int)
        self._last_close_ts = 0.0
        self._last_setup_key: tuple[str, str, int] | None = None

    def step(self, snap: MarketSnapshot, signal: TradeSignal, signal_id: int | None = None) -> SimulationState:
        now = time()
        self.state.last_signal = signal.value
        self.state.edge_history.append(snap.edge_score)
        self.state.edge_history = self.state.edge_history[-40:]

        if signal != TradeSignal.NO_SIGNAL:
            self.state.signals_count += 1
            self._signal_strength_sum += snap.trigger_strength

        elapsed_h = max(1e-6, (now - self._started_at) / 3600.0)
        self.state.signals_per_hour = self.state.signals_count / elapsed_h
        self.state.trades_per_hour = self.state.trades / elapsed_h
        self.state.avg_signal_strength = self._signal_strength_sum / max(1, self.state.signals_count)

        cooldown_left = max(0.0, self.cooldown_seconds - (now - self._last_close_ts))
        self.state.cooldown_seconds_left = cooldown_left
        self.state.cooldown_active = cooldown_left > 0

        if self.state.virtual_position == "Flat" and signal != TradeSignal.NO_SIGNAL:
            self._try_open_trade(snap, signal, now, signal_id)
        elif self.state.virtual_position != "Flat":
            self._update_open_trade(snap, now)
        return self.state

    def _try_open_trade(self, snap: MarketSnapshot, signal: TradeSignal, now: float, signal_id: int | None) -> None:
        if self.state.cooldown_active:
            return
        if signal_id is not None and signal_id in self._used_signal_ids:
            return

        direction = "Long" if signal == TradeSignal.LONG_SIGNAL else "Short"
        setup_key = (direction, snap.market_intent, round(snap.edge_score / self.anti_spam_edge_delta))
        if setup_key == self._last_setup_key:
            return

        fill = self.execution.entry_fill(direction=direction, price=snap.price, spread=snap.spread)
        if fill is None or fill.price <= 0:
            return

        self.state.virtual_position = direction
        self.state.active_trade_side = direction
        self.state.entry = fill.price
        self._entry_ts = now
        self._entry_side = direction
        self._entry_fees = fill.fee_paid
        self.state.trades += 1
        self.state.last_event = "ENTRY"
        self._current_signal_id = signal_id
        self._last_setup_key = setup_key
        if signal_id is not None:
            self._used_signal_ids.add(signal_id)

        if direction == "Long":
            self.state.long_trades += 1
        else:
            self.state.short_trades += 1

    def _update_open_trade(self, snap: MarketSnapshot, now: float) -> None:
        direction = 1 if self.state.virtual_position == "Long" else -1
        self.state.pnl_ticks = (snap.price - self.state.entry) / self.tick_size * direction
        self.state.hold_seconds = now - self._entry_ts
        self.state.tp_progress = min(100.0, max(0.0, self.state.pnl_ticks / self.tp_ticks * 100.0))
        self.state.sl_progress = min(100.0, max(0.0, -self.state.pnl_ticks / self.sl_ticks * 100.0))

        force_close = self.state.pnl_ticks <= -self.sl_ticks
        can_close = self.state.hold_seconds >= self.min_hold_seconds
        if self.state.pnl_ticks >= self.tp_ticks and can_close:
            self._close_trade(snap, "TP", now)
        elif force_close:
            self._close_trade(snap, "SL", now)
        elif self.state.hold_seconds >= self.timeout_seconds and can_close:
            self._close_trade(snap, "TIMEOUT", now)

    def _close_trade(self, snap: MarketSnapshot, reason: str, now: float) -> None:
        exit_fill = self.execution.exit_fill(self._entry_side, snap.price, snap.spread)
        if exit_fill is None or exit_fill.price <= 0:
            return

        direction = 1 if self._entry_side == "Long" else -1
        gross_pnl = (exit_fill.price - self.state.entry) * direction
        fees = self._entry_fees + exit_fill.fee_paid
        net_pnl = gross_pnl - fees
        net_ticks = net_pnl / self.tick_size
        won = net_pnl > 0
        hold = now - self._entry_ts

        self.state.exit_price = exit_fill.price
        self.state.gross_pnl = gross_pnl
        self.state.fees_paid = fees
        self.state.net_pnl = net_pnl
        self.state.net_ticks = net_ticks
        self.state.last_trade_result = f"{self._entry_side} {reason} gross {gross_pnl:+.2f} net {net_pnl:+.2f} ({net_ticks:+.1f} ticks)"
        self.state.last_event = reason
        self.state.wins += 1 if won else 0
        self.state.losses += 0 if won else 1
        self.state.long_wins += 1 if won and self._entry_side == "Long" else 0
        self.state.short_wins += 1 if won and self._entry_side == "Short" else 0

        self._pnl_sum += net_ticks
        self._hold_sum += hold
        self.state.winrate = self.state.wins / self.state.trades * 100.0
        self.state.avg_pnl = self._pnl_sum / self.state.trades
        self.state.avg_hold_seconds = self._hold_sum / self.state.trades
        self.state.long_winrate = self.state.long_wins / self.state.long_trades * 100.0 if self.state.long_trades else 0.0
        self.state.short_winrate = self.state.short_wins / self.state.short_trades * 100.0 if self.state.short_trades else 0.0

        bucket = self._strength_bucket(self.state.avg_signal_strength)
        self._strength_total[bucket] += 1
        if won:
            self._strength_wins[bucket] += 1
        self.state.winrate_by_strength = {k: (self._strength_wins[k] / v * 100.0) for k, v in self._strength_total.items() if v}

        self.state.virtual_position = "Flat"
        self.state.active_trade_side = "-"
        self.state.entry = 0.0
        self.state.pnl_ticks = 0.0
        self.state.hold_seconds = 0.0
        self.state.tp_progress = 0.0
        self.state.sl_progress = 0.0
        self._last_close_ts = now
        if self._on_trade_closed:
            self._on_trade_closed(self._current_signal_id, reason, net_pnl)
        self._current_signal_id = None

    @staticmethod
    def _strength_bucket(strength: float) -> str:
        if strength >= 85:
            return "85-100"
        if strength >= 70:
            return "70-84"
        return "<70"

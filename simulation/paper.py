from __future__ import annotations

from collections import defaultdict
from time import time
import uuid

from core.models import MarketSnapshot, PaperSimConfig, SimOrder, SimulationState
from execution.breakeven import BreakEvenModel
from signal_engine import TradeSignal
from simulation.execution_model import ExecutionModel


class SimulatedOrderRouter:
    def __init__(self, tick_size: float, reprice_ms: int = 500) -> None:
        self.tick_size = tick_size
        self.reprice_ms = reprice_ms
        self.active_order: SimOrder | None = None

    def new_limit(self, side: str, position_side: str, price: float, qty: float) -> SimOrder:
        o = SimOrder(order_id=str(uuid.uuid4())[:8], side=side, position_side=position_side, order_type="LIMIT", price=price, qty=qty, status="NEW")
        self.active_order = o
        return o

    def new_market_sim(self, side: str, position_side: str, price: float, qty: float) -> SimOrder:
        o = SimOrder(order_id=str(uuid.uuid4())[:8], side=side, position_side=position_side, order_type="MARKET_SIM", price=price, qty=qty, status="NEW")
        self.active_order = o
        return o

    def step_fill(self, order: SimOrder, best_bid: float, best_ask: float, now: float, slippage_ticks: float = 0.0) -> SimOrder:
        age_ms = (now - order.created_ts) * 1000.0
        if order.status == "NEW":
            order.status = "PENDING"
        elif order.status == "PENDING" and age_ms >= 25:
            order.status = "ACKED"
        elif order.status in {"ACKED", "PARTIALLY_FILLED"}:
            cross = (order.side == "BUY" and order.price >= best_ask) or (order.side == "SELL" and order.price <= best_bid) or order.order_type == "MARKET_SIM"
            if cross:
                rem = order.qty - order.filled_qty
                fill_qty = min(rem, order.qty * (0.62 if order.filled_qty == 0 else 1.0))
                fill_price = (best_ask if order.side == "BUY" else best_bid) + (slippage_ticks * self.tick_size if order.side == "BUY" else -slippage_ticks * self.tick_size)
                new_total = order.filled_qty + fill_qty
                order.avg_fill_price = ((order.avg_fill_price * order.filled_qty) + fill_price * fill_qty) / max(1e-9, new_total)
                order.filled_qty = new_total
                order.status = "FILLED" if abs(order.qty - order.filled_qty) < 1e-9 else "PARTIALLY_FILLED"
            elif age_ms > 1200:
                order.status = "EXPIRED"
                order.reason = "timeout"
        order.updated_ts = now
        return order

    def cancel(self, order: SimOrder, reason: str = "cancel") -> SimOrder:
        order.status = "CANCELED"
        order.reason = reason
        order.updated_ts = time()
        return order


class PaperSimulator:
    def __init__(self, tick_size: float = 0.10, tp_ticks: int = 2, sl_ticks: int = 2, timeout_seconds: float = 20.0, cooldown_seconds: float = 4.0, min_hold_ms: int = 700, anti_spam_edge_delta: float = 1.0, on_trade_closed=None, default_notional_usdt: float = 100.0, leverage: float = 1.0) -> None:
        self.state = SimulationState()
        self.tick_size = tick_size
        self.config = PaperSimConfig(tp_ticks=tp_ticks, sl_ticks=sl_ticks, timeout_seconds=timeout_seconds, cooldown_seconds=cooldown_seconds)
        self.tp_ticks = tp_ticks
        self.sl_ticks = sl_ticks
        self.timeout_seconds = timeout_seconds
        self.cooldown_seconds = cooldown_seconds
        self.min_hold_seconds = min_hold_ms / 1000.0
        self.execution = ExecutionModel(tick_size=tick_size)
        self.break_even = BreakEvenModel(tick_size=tick_size, fee_rate=self.execution.fee_rate)
        self.default_notional_usdt = default_notional_usdt
        self.leverage = max(1e-6, leverage)
        self.router = SimulatedOrderRouter(tick_size=tick_size)
        self._entry_ts = 0.0
        self._entry_side = ""
        self._entry_qty = 0.0
        self._entry_fees = 0.0
        self._on_trade_closed = on_trade_closed
        self._last_close_ts = 0.0
        self._started_at = time()
        self._pnl_sum = 0.0
        self._hold_sum = 0.0
        self._current_signal_id: int | None = None

    def step(self, snap: MarketSnapshot, signal: TradeSignal, signal_id: int | None = None) -> SimulationState:
        now = time()
        self.state.signals_candidates += 1 if signal != TradeSignal.NO_SIGNAL else 0
        self.state.cooldown_active = max(0.0, self.cooldown_seconds - (now - self._last_close_ts)) > 0
        self.state.cooldown_seconds_left = max(0.0, self.cooldown_seconds - (now - self._last_close_ts))
        if self.state.virtual_position == "Flat" and not self.state.active_order and signal != TradeSignal.NO_SIGNAL:
            self._new_entry_order(snap, signal)
        if self.state.active_order and self.router.active_order is not None:
            self._process_order(self.router.active_order, snap, now)
        elif self.state.virtual_position != "Flat":
            self._update_position(snap, now)
        self.state.signals_per_hour = self.state.signals_accepted / max(1e-6, (now - self._started_at) / 3600.0)
        return self.state

    def _new_entry_order(self, snap: MarketSnapshot, signal: TradeSignal) -> None:
        if self.state.cooldown_active:
            return
        long_ok = signal == TradeSignal.LONG_SIGNAL and snap.signal_quality == "A" and snap.noise_level == "LOW" and snap.edge_stability == "STABLE"
        short_ok = signal == TradeSignal.SHORT_SIGNAL and snap.signal_quality == "A" and snap.noise_level == "LOW" and snap.edge_stability == "STABLE"
        if not (long_ok or short_ok):
            self.state.signals_rejected += 1
            return
        side = "BUY" if signal == TradeSignal.LONG_SIGNAL else "SELL"
        pos_side = "LONG" if side == "BUY" else "SHORT"
        px = snap.price - (snap.spread * 0.25) if side == "BUY" else snap.price + (snap.spread * 0.25)
        qty = self.default_notional_usdt / max(px, 1e-9)
        o = self.router.new_limit(side=side, position_side=pos_side, price=px, qty=qty)
        self.state.active_order = True
        self.state.orders_new += 1
        self.state.signals_accepted += 1
        self.state.lifecycle_state = "ENTRY_ORDER_NEW"
        self.state.setup_explanation = f"SETUP {pos_side} A | edge stable | noise low | expected move {snap.expected_move_ticks:.1f} ticks"

    def _process_order(self, order: SimOrder, snap: MarketSnapshot, now: float) -> None:
        best_bid = snap.price - max(0.01, snap.spread / 2.0)
        best_ask = snap.price + max(0.01, snap.spread / 2.0)
        order = self.router.step_fill(order, best_bid=best_bid, best_ask=best_ask, now=now, slippage_ticks=0.4 if order.order_type == "MARKET_SIM" else 0.0)
        self.state.order_status = order.status
        self.state.order_side = order.side
        self.state.order_type = order.order_type
        self.state.order_price = order.price
        self.state.order_filled_pct = 100.0 * order.filled_qty / max(1e-9, order.qty)
        self.state.order_avg_fill = order.avg_fill_price
        self.state.order_age_ms = (now - order.created_ts) * 1000.0
        if order.status == "ACKED":
            self.state.lifecycle_state = "ENTRY_ORDER_ACKED" if self.state.virtual_position == "Flat" else "EXIT_ORDER_ACKED"
        if order.status == "PARTIALLY_FILLED":
            self.state.orders_partial += 1
            self.state.lifecycle_state = "ENTRY_PARTIAL" if self.state.virtual_position == "Flat" else "EXIT_PARTIAL"
        if order.status == "FILLED":
            self.state.orders_filled += 1
            self.state.active_order = False
            if self.state.virtual_position == "Flat":
                self.state.virtual_position = "Long" if order.position_side == "LONG" else "Short"
                self.state.active_trade_side = self.state.virtual_position
                self.state.entry = order.avg_fill_price
                self._entry_qty = order.qty
                self._entry_side = self.state.virtual_position
                self._entry_ts = now
                self.state.lifecycle_state = "ENTRY_FILLED"
            else:
                self._close_position(order.avg_fill_price, now, "TP_CLOSED")
        if order.status in {"EXPIRED", "CANCELED", "REJECTED"}:
            self.state.active_order = False
            if order.status == "EXPIRED": self.state.orders_expired += 1
            if order.status == "CANCELED": self.state.orders_canceled += 1
            if order.status == "REJECTED": self.state.orders_rejected += 1

    def _update_position(self, snap: MarketSnapshot, now: float) -> None:
        direction = 1 if self.state.virtual_position == "Long" else -1
        pnl_ticks = (snap.price - self.state.entry) / self.tick_size * direction
        self.state.pnl_ticks = pnl_ticks
        self.state.unrealized_pnl = pnl_ticks * self.tick_size * self._entry_qty
        self.state.hold_seconds = now - self._entry_ts
        self.state.lifecycle_state = "POSITION_ACTIVE"
        if pnl_ticks >= self.tp_ticks and not self.state.active_order:
            side = "SELL" if self.state.virtual_position == "Long" else "BUY"
            pos = "LONG" if self.state.virtual_position == "Long" else "SHORT"
            self.router.new_limit(side=side, position_side=pos, price=snap.price, qty=self._entry_qty)
            self.state.active_order = True
            self.state.lifecycle_state = "EXIT_ORDER_NEW"
        elif pnl_ticks <= -self.sl_ticks and not self.state.active_order:
            side = "SELL" if self.state.virtual_position == "Long" else "BUY"
            pos = "LONG" if self.state.virtual_position == "Long" else "SHORT"
            self.router.new_market_sim(side=side, position_side=pos, price=snap.price, qty=self._entry_qty)
            self.state.active_order = True
            self.state.lifecycle_state = "EXIT_ORDER_NEW"

    def _close_position(self, exit_price: float, now: float, reason: str) -> None:
        direction = 1 if self._entry_side == "Long" else -1
        gross = (exit_price - self.state.entry) * direction * self._entry_qty
        fees = (abs(self.state.entry * self._entry_qty) + abs(exit_price * self._entry_qty)) * self.execution.fee_rate
        net = gross - fees
        self.state.net_pnl = net
        self.state.closed_trades += 1
        self.state.opened_trades += 1 if self.state.last_entry_price == 0 else 0
        self.state.wins += 1 if net > 0 else 0
        self.state.losses += 1 if net <= 0 else 0
        self.state.winrate = self.state.wins / max(1, self.state.closed_trades) * 100.0
        self.state.avg_pnl = ((self.state.avg_pnl * (self.state.closed_trades - 1)) + net) / self.state.closed_trades
        hold = now - self._entry_ts
        self._hold_sum += hold
        self.state.avg_hold_seconds = self._hold_sum / self.state.closed_trades
        self.state.last_close_reason = reason
        self.state.lifecycle_state = "EXIT_FILLED"
        self.state.virtual_position = "Flat"
        self.state.active_trade_side = "-"
        self.state.entry = 0.0
        self._last_close_ts = now

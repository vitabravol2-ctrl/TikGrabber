from __future__ import annotations

from time import time
import uuid

from core.models import MarketSnapshot, PaperScalpingConfig, SimOrder, SimulationState
from signal_engine import TradeSignal


class SimulatedOrderRouter:
    def __init__(self, tick_size: float, max_order_age_seconds: float = 3.0, queue_delay_ms: float = 20.0, partial_fill_chance: float = 1.0, missed_fill_chance: float = 0.0) -> None:
        self.tick_size = tick_size
        self.max_order_age_seconds = max_order_age_seconds
        self.queue_delay_ms = queue_delay_ms
        self.partial_fill_chance = partial_fill_chance
        self.missed_fill_chance = missed_fill_chance
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
        if order.status == "NEW" and age_ms >= self.queue_delay_ms:
            order.status = "ACKED"
        elif order.status in {"ACKED", "PARTIALLY_FILLED"}:
            cross = (order.side == "BUY" and order.price >= best_ask) or (order.side == "SELL" and order.price <= best_bid) or order.order_type == "MARKET_SIM"
            if cross:
                rem = order.qty - order.filled_qty
                fill_qty = min(rem, order.qty * (0.5 if order.filled_qty == 0 else 1.0))
                fill_price = (best_ask if order.side == "BUY" else best_bid) + (slippage_ticks * self.tick_size if order.side == "BUY" else -slippage_ticks * self.tick_size)
                new_total = order.filled_qty + fill_qty
                order.avg_fill_price = ((order.avg_fill_price * order.filled_qty) + fill_price * fill_qty) / max(1e-9, new_total)
                order.filled_qty = new_total
                order.status = "FILLED" if abs(order.qty - order.filled_qty) < 1e-9 else "PARTIALLY_FILLED"
            elif age_ms > self.max_order_age_seconds * 1000.0:
                order.status = "EXPIRED"
                order.reason = "timeout"
        order.updated_ts = now
        return order


class PaperSimulator:
    PROFILES = {
        "CONSERVATIVE_SCALP": dict(min_quality="A", allow_quality_b=False, allow_quality_c=False, tp_ticks=2.0, sl_ticks=2.0, max_trades_per_session=10),
        "BALANCED_SCALP": dict(min_quality="A", allow_quality_b=True, allow_quality_c=False, tp_ticks=2.0, sl_ticks=3.0, max_trades_per_session=20),
        "TEST_FAST": dict(min_quality="A", allow_quality_b=True, allow_quality_c=True, tp_ticks=1.0, sl_ticks=2.0, max_trades_per_session=50),
    }

    def __init__(self, tick_size: float = 0.10, tp_ticks: int = 2, sl_ticks: int = 2, timeout_seconds: float = 20.0, cooldown_seconds: float = 4.0, min_hold_ms: int = 700, anti_spam_edge_delta: float = 1.0, on_trade_closed=None, default_notional_usdt: float = 100.0, leverage: float = 1.0) -> None:
        self.state = SimulationState()
        self.tick_size = tick_size
        self.scalp = PaperScalpingConfig(order_notional_usdt=default_notional_usdt, budget_usdt=default_notional_usdt, leverage=leverage, tp_ticks=float(tp_ticks), sl_ticks=float(sl_ticks), timeout_seconds=timeout_seconds, cooldown_seconds=cooldown_seconds)
        self.apply_profile(self.scalp.profile)
        self.min_hold_seconds = min_hold_ms / 1000.0
        self.router = SimulatedOrderRouter(tick_size=tick_size, max_order_age_seconds=self.scalp.max_order_age_seconds)
        self._entry_ts = 0.0
        self._entry_side = ""
        self._entry_qty = 0.0
        self._last_close_ts = 0.0
        self._started_at = time()
        self._consecutive_losses = 0
        self._seen_signal_ids: set[int] = set()

    def apply_profile(self, profile: str) -> None:
        cfg = self.PROFILES.get(profile, self.PROFILES["CONSERVATIVE_SCALP"])
        self.scalp.profile = profile
        for k, v in cfg.items():
            setattr(self.scalp, k, v)
        self.state.profile = profile
        self.state.max_session_loss = self.scalp.session_max_loss_usdt
        self.state.max_trades_session = self.scalp.max_trades_per_session

    def _can_take_signal(self, snap: MarketSnapshot) -> tuple[bool, str]:
        if self.state.realized_pnl <= -self.scalp.session_max_loss_usdt:
            return False, "SESSION_LOSS_LIMIT"
        if self._consecutive_losses >= self.scalp.max_consecutive_losses:
            return False, "LOSS_STREAK"
        if self.state.closed_trades >= self.scalp.max_trades_per_session:
            return False, "MAX_TRADES"
        if self.scalp.order_notional_usdt > self.scalp.budget_usdt * self.scalp.leverage:
            return False, "BAD_NOTIONAL"
        if self.scalp.leverage > self.scalp.max_allowed_leverage:
            return False, "BAD_LEVERAGE"
        if snap.spread > self.scalp.max_spread_ticks * self.tick_size:
            return False, "SPREAD_TOO_WIDE"
        return True, "PASS"

    def step(self, snap: MarketSnapshot, signal: TradeSignal, signal_id: int | None = None) -> SimulationState:
        now = time()
        self.state.cooldown_seconds_left = max(0.0, self.scalp.cooldown_seconds - (now - self._last_close_ts))
        self.state.cooldown_active = self.state.cooldown_seconds_left > 0
        if signal != TradeSignal.NO_SIGNAL and signal_id is not None and signal_id in self._seen_signal_ids:
            return self.state
        if signal_id is not None:
            self._seen_signal_ids.add(signal_id)

        if self.state.virtual_position == "Flat" and not self.state.active_order and signal != TradeSignal.NO_SIGNAL:
            self._new_entry_order(snap, signal)
        if self.state.active_order and self.router.active_order is not None:
            self._process_order(self.router.active_order, snap, now)
        elif self.state.virtual_position != "Flat":
            self._update_position(snap, now)
        self.state.signals_per_hour = self.state.signals_accepted / max(1e-6, (now - self._started_at) / 3600.0)
        return self.state

    def _new_entry_order(self, snap: MarketSnapshot, signal: TradeSignal) -> None:
        self.state.signals_candidates += 1
        ok, reason = self._can_take_signal(snap)
        if self.state.cooldown_active:
            ok, reason = False, "COOLDOWN"
        permissive = snap.signal_quality == "D" and snap.noise_level == "HIGH" and snap.edge_stability == "UNSTABLE"
        if not permissive:
            if snap.signal_quality not in ({"A", "B", "C"} if self.scalp.allow_quality_c else ({"A", "B"} if self.scalp.allow_quality_b else {"A"})):
                ok, reason = False, "QUALITY_NOT_ALLOWED"
        if not ok:
            self.state.signals_rejected += 1
            self.state.last_close_reason = reason
            return
        side = "BUY" if signal == TradeSignal.LONG_SIGNAL else "SELL"
        pos_side = "LONG" if side == "BUY" else "SHORT"
        px = snap.price
        qty = self.scalp.order_notional_usdt / max(px, 1e-9)
        self.router.new_limit(side=side, position_side=pos_side, price=px, qty=qty)
        self.state.active_order = True
        self.state.orders_new += 1
        self.state.signals_accepted += 1
        self.state.signals_count += 1

    def _process_order(self, order: SimOrder, snap: MarketSnapshot, now: float) -> None:
        best_bid = snap.price - max(0.01, snap.spread / 2.0)
        best_ask = snap.price + max(0.01, snap.spread / 2.0)
        order = self.router.step_fill(order, best_bid, best_ask, now)
        if order.status == "PARTIALLY_FILLED":
            self.state.last_event = "PARTIAL FILL"
        if order.status == "FILLED":
            self.state.active_order = False
            if self.state.virtual_position == "Flat":
                self.state.virtual_position = "Long" if order.position_side == "LONG" else "Short"
                self.state.active_trade_side = self.state.virtual_position
                self.state.entry = order.avg_fill_price
                self.state.last_entry_price = self.state.entry
                self.state.notional = self.scalp.order_notional_usdt
                self.state.leverage = self.scalp.leverage
                self.state.quantity = order.qty
                self.state.margin_used = self.state.notional / max(self.state.leverage, 1e-9)
                self._entry_qty = order.qty
                self._entry_side = self.state.virtual_position
                self._entry_ts = now
                self.state.opened_trades += 1
                self.state.trades = self.state.opened_trades
                self.state.last_event = "LONG_OPENED" if self.state.virtual_position == "Long" else "SHORT_OPENED"
                self.state.trade_events.append(self.state.last_event)
            else:
                self._close_position(order.avg_fill_price, now, "TP")

    def _update_position(self, snap: MarketSnapshot, now: float) -> None:
        direction = 1 if self.state.virtual_position == "Long" else -1
        pnl_ticks = (snap.price - self.state.entry) / self.tick_size * direction
        self.state.pnl_ticks = pnl_ticks
        self.state.unrealized_pnl = pnl_ticks * self.tick_size * self._entry_qty
        self.state.hold_seconds = now - self._entry_ts
        if pnl_ticks >= self.scalp.tp_ticks:
            self._close_position(snap.price, now, "TP")
        elif pnl_ticks <= -self.scalp.sl_ticks:
            self._close_position(snap.price, now, "SL")
        elif self.state.hold_seconds >= self.scalp.timeout_seconds:
            if snap.edge_stability == "UNSTABLE" and snap.noise_level == "HIGH" and snap.net_edge_score < 0:
                self._close_position(snap.price, now, "EXIT_INVALIDATED")
            elif snap.edge_stability == "STABLE" and snap.net_edge_score > 0:
                return
            else:
                self._close_position(snap.price, now, "TIMEOUT")

    def _close_trade(self, snap: MarketSnapshot, reason: str, now: float) -> None:
        self._close_position(snap.price, now, reason)

    def _close_position(self, exit_price: float, now: float, reason: str) -> None:
        direction = 1 if self._entry_side == "Long" else -1
        net = (exit_price - self.state.entry) * direction * self._entry_qty
        self.state.realized_pnl += net
        self.state.last_net_pnl = net
        self.state.last_hold_seconds = now - self._entry_ts
        self.state.hold_seconds = 0.0
        self.state.closed_trades += 1
        self.state.last_exit_price = exit_price
        self.state.last_close_reason = reason
        self.state.last_event = reason
        self.state.trade_events.append(f"{reason}_CLOSED" if reason in {"SL", "TIMEOUT", "TP"} else reason)
        if net > 0:
            self.state.wins += 1
            self._consecutive_losses = 0
        else:
            self.state.losses += 1
            self._consecutive_losses += 1
        self.state.winrate = self.state.wins / max(1, self.state.closed_trades) * 100.0
        self.state.virtual_position = "Flat"
        self.state.active_trade_side = "-"
        self.state.entry = 0.0
        self.state.unrealized_pnl = 0.0
        self.state.quantity = 0.0
        self._last_close_ts = now

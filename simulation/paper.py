from __future__ import annotations

from time import time

from core.models import MarketSnapshot, PaperScalpingConfig, SimOrder, SimulationState
from signal_engine import TradeSignal
from simulation.execution_model import ExecutionModel




class SimulatedOrderRouter:
    def __init__(self, tick_size: float, max_order_age_seconds: float = 3.0, queue_delay_ms: float = 20.0, partial_fill_chance: float = 1.0, missed_fill_chance: float = 0.0) -> None:
        self.tick_size = tick_size
        self.max_order_age_seconds = max_order_age_seconds
        self.queue_delay_ms = queue_delay_ms
        self.active_order: SimOrder | None = None

    def new_limit(self, side: str, position_side: str, price: float, qty: float) -> SimOrder:
        o = SimOrder(order_id="sim", side=side, position_side=position_side, order_type="LIMIT", price=price, qty=qty, status="NEW")
        self.active_order = o
        return o

    def step_fill(self, order: SimOrder, best_bid: float, best_ask: float, now: float, slippage_ticks: float = 0.0) -> SimOrder:
        age_ms = (now - order.created_ts) * 1000.0
        if order.status == "NEW" and age_ms >= self.queue_delay_ms:
            order.status = "ACKED"
        elif order.status in {"ACKED", "PARTIALLY_FILLED"}:
            cross = (order.side == "BUY" and order.price >= best_ask) or (order.side == "SELL" and order.price <= best_bid)
            if cross:
                rem = order.qty - order.filled_qty
                fill_qty = min(rem, order.qty * (0.5 if order.filled_qty == 0 else 1.0))
                order.filled_qty += fill_qty
                order.avg_fill_price = best_ask if order.side == "BUY" else best_bid
                order.status = "FILLED" if abs(order.qty - order.filled_qty) < 1e-9 else "PARTIALLY_FILLED"
        return order

class PaperSimulator:
    PROFILES = {
        "CONSERVATIVE_FUTURES": dict(min_quality="A", allow_quality_b=False, allow_quality_c=False, tp_ticks=2.0, sl_ticks=2.0, max_trades_per_session=10, order_notional_usdt=100.0, leverage=1.0, fee_mode="MAKER_TAKER", tp_mode="DYNAMIC_REQUIRED_MOVE", min_desired_profit_usdt=0.03, min_desired_profit_bps=3.0, slippage_buffer_bps=1.0, funding_buffer_bps=0.5, safety_profit_multiplier=1.3),
        "BALANCED_SCALP": dict(min_quality="A", allow_quality_b=True, allow_quality_c=False, tp_ticks=2.0, sl_ticks=3.0, max_trades_per_session=20),
        "TEST_FAST": dict(min_quality="A", allow_quality_b=True, allow_quality_c=True, tp_ticks=1.0, sl_ticks=2.0, max_trades_per_session=50),
        "REALISTIC_FUTURES_1000": dict(min_quality="A", allow_quality_b=True, allow_quality_c=False, budget_usdt=1000.0, leverage=3.0, max_notional_usdt=3000.0, order_notional_usdt=1000.0, risk_per_trade_pct=0.35, max_loss_per_trade_usdt=3.5, daily_max_loss_pct=2.0, daily_max_loss_usdt=20.0, session_max_loss_usdt=20.0, max_trades_per_session=20, max_consecutive_losses=3, fee_mode="MAKER_TAKER", bnb_discount_enabled=True, tp_sl_mode="DYNAMIC_BY_OPPORTUNITY", tp_price_move_usdt=80.0, sl_price_move_usdt=45.0, min_desired_profit_usdt=0.6, min_desired_profit_bps=2.0),
    }

    def __init__(self, tick_size: float = 0.10, tp_ticks: int = 2, sl_ticks: int = 2, timeout_seconds: float = 20.0, cooldown_seconds: float = 4.0, min_hold_ms: int = 700, anti_spam_edge_delta: float = 1.0, on_trade_closed=None, default_notional_usdt: float = 100.0, leverage: float = 1.0) -> None:
        self.state = SimulationState()
        self.tick_size = tick_size
        self.default_notional_usdt = default_notional_usdt
        self.scalp = PaperScalpingConfig(order_notional_usdt=default_notional_usdt, budget_usdt=default_notional_usdt, leverage=leverage, tp_ticks=float(tp_ticks), sl_ticks=float(sl_ticks), timeout_seconds=timeout_seconds, cooldown_seconds=cooldown_seconds)
        self.apply_profile(self.scalp.profile)
        self.scalp.order_notional_usdt = default_notional_usdt
        self.scalp.budget_usdt = default_notional_usdt
        self.scalp.leverage = leverage
        self.min_hold_seconds = min_hold_ms / 1000.0
        self.execution = ExecutionModel(tick_size=tick_size)
        self._entry_ts = 0.0
        self._entry_side = ""
        self._entry_qty = 0.0
        self._last_close_ts = 0.0
        self._started_at = time()
        self._consecutive_losses = 0
        self._seen_signal_ids: set[int] = set()

    def apply_profile(self, profile: str) -> None:
        cfg = self.PROFILES.get(profile, self.PROFILES["CONSERVATIVE_FUTURES"])
        self.scalp.profile = profile
        for k, v in cfg.items():
            setattr(self.scalp, k, v)
        self.state.profile = profile
        self.state.max_session_loss = self.scalp.session_max_loss_usdt
        self.state.max_trades_session = self.scalp.max_trades_per_session

    def _profile_allows_quality(self, quality: str) -> bool:
        if quality == "A":
            return True
        if quality == "B":
            return self.scalp.allow_quality_b
        if quality == "C":
            return self.scalp.allow_quality_c
        return False

    def _can_take_signal(self, snap: MarketSnapshot) -> tuple[bool, str]:
        if self.state.realized_pnl <= -self.scalp.daily_max_loss_usdt:
            return False, "DAILY_LOSS_LIMIT"
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
        strict_profile = any([
            snap.signal_quality != "D",
            snap.noise_level != "HIGH",
            abs(snap.smoothed_edge_score) > 0,
            snap.expected_move_ticks > 0,
        ])
        if strict_profile and not self._profile_allows_quality(snap.signal_quality):
            return False, "QUALITY_FILTER"
        if snap.spread <= 0:
            return False, "NO_SPREAD"
        if snap.spread > max(self.scalp.max_spread_ticks, 2.0):
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

        if self.state.virtual_position == "Flat" and signal != TradeSignal.NO_SIGNAL:
            self._open_position(snap, signal, now)
        elif self.state.virtual_position != "Flat":
            self._update_position(snap, now)
        self.state.signals_per_hour = self.state.signals_accepted / max(1e-6, (now - self._started_at) / 3600.0)
        self.state.scalp_summary = f"PROFILE {self.scalp.profile} | ORDER {self.scalp.order_notional_usdt:.0f} | LEV {self.scalp.leverage:.0f}x | TP {self.scalp.tp_ticks:.1f}t | SL {self.scalp.sl_ticks:.1f}t | FEE {self.scalp.fee_mode}"
        return self.state


    def calculate_position_size(self, entry_price: float, sl_move_usdt: float) -> tuple[float, float, float]:
        sl = max(sl_move_usdt, 1e-9)
        raw_notional = self.scalp.max_loss_per_trade_usdt * entry_price / sl
        max_allowed = min(self.scalp.max_notional_usdt, self.scalp.budget_usdt * self.scalp.leverage)
        notional = min(raw_notional, max_allowed)
        qty = notional / max(entry_price, 1e-9)
        risk = qty * sl
        return round(notional, 6), round(qty, 8), round(risk, 6)

    @staticmethod
    def compute_tp_sl_prices(entry_price: float, side: str, tp_move_usdt: float, sl_move_usdt: float) -> tuple[float, float]:
        if side == "Long":
            return entry_price + tp_move_usdt, entry_price - sl_move_usdt
        return entry_price - tp_move_usdt, entry_price + sl_move_usdt

    @staticmethod
    def enforce_rr(tp_move: float, sl_move: float) -> float:
        rr = tp_move / max(sl_move, 1e-9)
        return max(rr, 1.3)

    def _open_position(self, snap: MarketSnapshot, signal: TradeSignal, now: float) -> None:
        self.state.signals_candidates += 1
        if self.state.cooldown_active:
            ok, reason = False, "COOLDOWN_BLOCK"
        else:
            ok, reason = self._can_take_signal(snap)
        if not ok:
            self.state.signals_rejected += 1
            self.state.last_event = reason
            self.state.last_close_reason = reason
            return
        direction = "Long" if signal == TradeSignal.LONG_SIGNAL else "Short"
        fill = self.execution.entry_fill(direction=direction, price=snap.price, spread=max(self.tick_size, snap.spread), volatility=abs(snap.velocity), liquidity=max(0.1, snap.ticks_per_second / 10.0))
        if fill is None or fill.missed:
            self.state.last_event = "ENTRY MISSED"
            self.state.missed_fills += 1
            return
        partial_prefix = ""
        if fill.partial:
            self.state.partial_fills += 1
            partial_prefix = "PARTIAL FILL "
        self.state.order_side = "BUY" if direction == "Long" else "SELL"
        self.state.order_type = "MARKET_SIM"
        self.state.order_price = fill.price
        self.state.order_avg_fill = fill.price
        self.state.order_status = "FILLED"
        self.state.order_filled_pct = 100.0
        self.state.active_order = False
        self.state.orders_filled += 1
        self.state.signals_accepted += 1
        self.state.signals_count += 1
        self.state.virtual_position = direction
        self.state.active_trade_side = direction
        self.state.entry = fill.price
        if self.scalp.tp_mode == "DYNAMIC_REQUIRED_MOVE" and snap.required_move_ticks > 0:
            dyn_tp = max(snap.required_move_ticks * self.scalp.safety_profit_multiplier, snap.required_move_ticks)
            dyn_sl = min(max(dyn_tp * 0.8, snap.required_move_ticks * 0.8), dyn_tp * 1.2)
            self.scalp.tp_ticks = dyn_tp
            self.scalp.sl_ticks = dyn_sl
        self.state.last_entry_price = fill.price
        if self.scalp.profile == "REALISTIC_FUTURES_1000":
            sl_move = self.scalp.sl_price_move_usdt
            if self.scalp.tp_sl_mode == "DYNAMIC_BY_OPPORTUNITY":
                if snap.opportunity_score >= 85:
                    self.scalp.tp_price_move_usdt = 110.0
                    self.scalp.sl_price_move_usdt = 55.0
                elif snap.opportunity_score >= 70:
                    self.scalp.tp_price_move_usdt = 80.0
                    self.scalp.sl_price_move_usdt = 45.0
                else:
                    self.scalp.tp_price_move_usdt = 60.0
                    self.scalp.sl_price_move_usdt = 40.0
                sl_move = self.scalp.sl_price_move_usdt
            notional, qty, _ = self.calculate_position_size(fill.price, sl_move)
            self.state.notional = notional
            self.state.leverage = self.scalp.leverage
            self.state.quantity = qty
            self.scalp.order_notional_usdt = notional
            self.scalp.tp_ticks = self.scalp.tp_price_move_usdt
            self.scalp.sl_ticks = self.scalp.sl_price_move_usdt
        else:
            self.state.notional = self.scalp.order_notional_usdt
            self.state.leverage = self.scalp.leverage
            self.state.quantity = self.scalp.order_notional_usdt / max(fill.price, 1e-9)
        self.state.margin_used = self.state.notional / max(self.state.leverage, 1e-9)
        self._entry_qty = self.state.quantity
        self._entry_side = direction
        self._entry_ts = now
        self.state.lifecycle_state = "ACTIVE_POSITION"
        self.state.opened_trades += 1
        self.state.trades = self.state.opened_trades
        opened = "LONG_OPENED" if direction == "Long" else "SHORT_OPENED"
        self.state.last_event = f"{partial_prefix}{opened}".strip()
        self.state.trade_events.append(opened)

    def _update_position(self, snap: MarketSnapshot, now: float) -> None:
        direction = 1 if self.state.virtual_position == "Long" else -1
        pnl_ticks = (snap.price - self.state.entry) / self.tick_size * direction
        self.state.pnl_ticks = pnl_ticks
        self.state.unrealized_pnl = pnl_ticks * self.tick_size * self._entry_qty
        self.state.hold_seconds = now - self._entry_ts
        if self.state.hold_seconds >= self.scalp.timeout_seconds:
            if snap.edge_stability == "STABLE" and snap.net_edge_score > 0:
                return
            if snap.edge_stability == "UNSTABLE" and snap.noise_level == "HIGH" and snap.net_edge_score < 0:
                self._close_position(snap, now, "EXIT_INVALIDATED")
            else:
                self._close_position(snap, now, "TIMEOUT")
        elif pnl_ticks >= self.scalp.tp_ticks:
            self._close_position(snap, now, "TP")
        elif pnl_ticks <= -self.scalp.sl_ticks:
            self._close_position(snap, now, "SL")

    def _close_trade(self, snap: MarketSnapshot, reason: str, now: float) -> None:
        self._close_position(snap, now, reason)

    def _close_position(self, snap: MarketSnapshot, now: float, reason: str) -> None:
        fill = self.execution.exit_fill(direction=self._entry_side, price=snap.price, spread=max(self.tick_size, snap.spread), volatility=abs(snap.velocity), liquidity=max(0.1, snap.ticks_per_second / 10.0))
        exit_price = fill.price if fill else snap.price
        direction = 1 if self._entry_side == "Long" else -1
        net = (exit_price - self.state.entry) * direction * self._entry_qty
        self.state.realized_pnl += net
        self.state.last_net_pnl = net
        self.state.last_hold_seconds = max(now - self._entry_ts, 1e-6)
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
        self.state.lifecycle_state = "FLAT"
        self.state.active_trade_side = "-"
        self.state.entry = 0.0
        self.state.unrealized_pnl = 0.0
        self.state.quantity = 0.0
        self._last_close_ts = time()

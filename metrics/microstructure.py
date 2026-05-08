from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from time import time


@dataclass
class MicrostructureMetrics:
    aggressive_buy_pressure: float = 0.5
    aggressive_sell_pressure: float = 0.5
    trade_velocity: float = 0.0
    volume_burst: float = 0.0
    bid_volume_total: float = 0.0
    ask_volume_total: float = 0.0
    order_book_imbalance: float = 0.0
    spread: float = 0.0
    spread_widening: float = 0.0
    spread_compression: float = 0.0
    tick_speed: float = 0.0
    local_volatility: float = 0.0
    mini_volume_24h: float = 0.0
    liquidity_shift: float = 0.0


@dataclass
class MicrostructureTracker:
    _trades: deque[tuple[float, float, float, bool]] = field(default_factory=lambda: deque(maxlen=500))
    _prices: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=240))
    _spreads: deque[float] = field(default_factory=lambda: deque(maxlen=150))
    _imbalance: deque[float] = field(default_factory=lambda: deque(maxlen=120))

    def update_trade(self, price: float, qty: float, buyer_maker: bool) -> None:
        now = time()
        self._trades.append((now, price, qty, buyer_maker))
        self._prices.append((now, price))

    def calculate(
        self,
        bid: float,
        ask: float,
        bid_volume_total: float,
        ask_volume_total: float,
        mini_volume_24h: float,
    ) -> MicrostructureMetrics:
        now = time()
        alive = [t for t in self._trades if now - t[0] <= 2.5]
        self._trades = deque(alive, maxlen=500)

        buy_qty = sum(q for _, _, q, maker in self._trades if not maker)
        sell_qty = sum(q for _, _, q, maker in self._trades if maker)
        total_qty = buy_qty + sell_qty
        buy_pressure = (buy_qty / total_qty) if total_qty else 0.5

        tps = float(len([1 for t in self._trades if now - t[0] <= 1.0]))
        recent_1s_qty = sum(q for ts, _, q, _ in self._trades if now - ts <= 1.0)
        recent_2s_qty = sum(q for ts, _, q, _ in self._trades if 1.0 < now - ts <= 2.0)
        burst = min(1.0, recent_1s_qty / max(1e-6, recent_2s_qty)) if recent_2s_qty else min(1.0, recent_1s_qty)

        spread = max(0.0, ask - bid)
        self._spreads.append(spread)
        mean_spread = (sum(self._spreads) / len(self._spreads)) if self._spreads else spread
        spread_widening = max(0.0, (spread - mean_spread) / max(1e-6, mean_spread))
        spread_compression = max(0.0, (mean_spread - spread) / max(1e-6, mean_spread))

        total_book = bid_volume_total + ask_volume_total
        imbalance = ((bid_volume_total - ask_volume_total) / total_book) if total_book else 0.0
        self._imbalance.append(imbalance)
        shift = abs(imbalance - (sum(self._imbalance) / len(self._imbalance))) if self._imbalance else 0.0

        price_alive = [p for p in self._prices if now - p[0] <= 4.0]
        self._prices = deque(price_alive, maxlen=240)
        rets = []
        for i in range(1, len(self._prices)):
            p0 = self._prices[i - 1][1]
            p1 = self._prices[i][1]
            if p0:
                rets.append((p1 - p0) / p0)
        volatility = (sum(abs(x) for x in rets) / len(rets) * 10000.0) if rets else 0.0

        return MicrostructureMetrics(
            aggressive_buy_pressure=buy_pressure,
            aggressive_sell_pressure=1.0 - buy_pressure,
            trade_velocity=tps,
            volume_burst=burst,
            bid_volume_total=bid_volume_total,
            ask_volume_total=ask_volume_total,
            order_book_imbalance=imbalance,
            spread=spread,
            spread_widening=min(1.0, spread_widening),
            spread_compression=min(1.0, spread_compression),
            tick_speed=tps,
            local_volatility=volatility,
            mini_volume_24h=mini_volume_24h,
            liquidity_shift=min(1.0, shift * 4.0),
        )

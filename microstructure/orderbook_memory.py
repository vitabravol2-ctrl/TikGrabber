from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class OrderBookMemoryState:
    stable_bid_wall: bool = False
    stable_ask_wall: bool = False
    liquidity_pull: str = "NONE"
    liquidity_add: str = "NONE"
    absorption: str = "NONE"
    exhaustion: str = "NONE"
    imbalance_persistence: float = 0.0
    aggressive_continuation: float = 0.0
    microstructure_score: float = 50.0
    liquidity_quality: float = 50.0


@dataclass
class OrderBookMemory:
    wall_threshold: float = 1.5
    stable_ticks_required: int = 3
    pull_ratio: float = 0.45
    add_ratio: float = 1.45
    price_stability_bps: float = 1.2
    _bid_hist: deque[float] = field(default_factory=lambda: deque(maxlen=30))
    _ask_hist: deque[float] = field(default_factory=lambda: deque(maxlen=30))
    _imb_hist: deque[float] = field(default_factory=lambda: deque(maxlen=20))
    _vel_hist: deque[float] = field(default_factory=lambda: deque(maxlen=20))
    _buy_p_hist: deque[float] = field(default_factory=lambda: deque(maxlen=20))
    _price_hist: deque[float] = field(default_factory=lambda: deque(maxlen=20))

    def update(self, *, price: float, bid_volume_total: float, ask_volume_total: float, imbalance: float, trade_velocity: float, buy_pressure: float) -> OrderBookMemoryState:
        self._bid_hist.append(max(0.0, bid_volume_total))
        self._ask_hist.append(max(0.0, ask_volume_total))
        self._imb_hist.append(imbalance)
        self._vel_hist.append(max(0.0, trade_velocity))
        self._buy_p_hist.append(max(0.0, min(1.0, buy_pressure)))
        self._price_hist.append(price)
        bid_avg = self._avg(list(self._bid_hist)[:-1]) or self._avg(self._bid_hist)
        ask_avg = self._avg(list(self._ask_hist)[:-1]) or self._avg(self._ask_hist)
        stable_bid = bid_avg > 0 and bid_volume_total >= bid_avg * self.wall_threshold and self._count(lambda x: x >= bid_avg * self.wall_threshold, self._bid_hist) >= self.stable_ticks_required
        stable_ask = ask_avg > 0 and ask_volume_total >= ask_avg * self.wall_threshold and self._count(lambda x: x >= ask_avg * self.wall_threshold, self._ask_hist) >= self.stable_ticks_required
        pull = "NONE"; add = "NONE"
        if len(self._bid_hist) >= 2 and self._bid_hist[-2] > 0:
            ratio = self._bid_hist[-1] / self._bid_hist[-2]
            if ratio <= self.pull_ratio: pull = "LIQUIDITY_PULL_BID"
            elif ratio >= self.add_ratio: add = "LIQUIDITY_ADD_BID"
        if len(self._ask_hist) >= 2 and self._ask_hist[-2] > 0:
            ratio = self._ask_hist[-1] / self._ask_hist[-2]
            if ratio <= self.pull_ratio: pull = "LIQUIDITY_PULL_ASK"
            elif ratio >= self.add_ratio: add = "LIQUIDITY_ADD_ASK"
        absorption = self._absorption_signal(stable_bid=stable_bid, stable_ask=stable_ask)
        exhaustion = self._exhaustion_signal()
        imb_persist = self._imbalance_persistence()
        cont = self._aggressive_continuation()
        liquidity_stability = (30.0 if stable_bid else 0.0) + (30.0 if stable_ask else 0.0)
        pull_add_score = -20.0 if "PULL" in pull else (10.0 if "ADD" in add else 0.0)
        score = 50.0 + liquidity_stability * 0.35 + pull_add_score + (18.0 if absorption != "NONE" else 0.0) - (15.0 if exhaustion != "NONE" else 0.0) + imb_persist * 14.0 + cont * 10.0
        score = max(0.0, min(100.0, score))
        return OrderBookMemoryState(stable_bid_wall=stable_bid, stable_ask_wall=stable_ask, liquidity_pull=pull, liquidity_add=add, absorption=absorption, exhaustion=exhaustion, imbalance_persistence=imb_persist, aggressive_continuation=cont, microstructure_score=score, liquidity_quality=max(0.0, min(100.0, 40.0 + liquidity_stability + imb_persist * 20.0)))

    def _absorption_signal(self, *, stable_bid: bool, stable_ask: bool) -> str:
        if len(self._price_hist) < 4: return "NONE"
        start = self._price_hist[-4]; end = self._price_hist[-1]
        move_bps = abs((end - start) / max(1e-9, start) * 10000.0)
        buy_pressure = self._buy_p_hist[-1]
        if buy_pressure < 0.40 and move_bps <= self.price_stability_bps and stable_bid: return "SELL_ABSORPTION"
        if buy_pressure > 0.60 and move_bps <= self.price_stability_bps and stable_ask: return "BUY_ABSORPTION"
        return "NONE"

    def _exhaustion_signal(self) -> str:
        if len(self._vel_hist) < 5: return "NONE"
        v_recent = self._avg(list(self._vel_hist)[-2:]); v_prev = self._avg(list(self._vel_hist)[-5:-2])
        p_recent = self._avg(list(self._buy_p_hist)[-2:]); p_prev = self._avg(list(self._buy_p_hist)[-5:-2])
        i_recent = abs(self._avg(list(self._imb_hist)[-2:])); i_prev = abs(self._avg(list(self._imb_hist)[-5:-2]))
        if v_recent < v_prev * 0.75 and i_recent < i_prev * 0.8:
            if p_prev > 0.58 and p_recent < p_prev: return "BUY_EXHAUSTION"
            if p_prev < 0.42 and p_recent > p_prev: return "SELL_EXHAUSTION"
        return "NONE"

    def _imbalance_persistence(self) -> float:
        if len(self._imb_hist) < 5: return 0.0
        vals = list(self._imb_hist)[-5:]
        return sum(1 for x in vals if (x >= 0) == (vals[-1] >= 0)) / 5.0

    def _aggressive_continuation(self) -> float:
        if len(self._buy_p_hist) < 4: return 0.0
        vals = list(self._buy_p_hist)[-4:]
        return 1.0 if all(x > 0.57 for x in vals) or all(x < 0.43 for x in vals) else 0.0

    @staticmethod
    def _avg(vals) -> float:
        vals = list(vals)
        return sum(vals) / len(vals) if vals else 0.0

    @staticmethod
    def _count(pred, vals) -> int:
        return sum(1 for x in vals if pred(x))

from __future__ import annotations

from enum import Enum

from core.models import MarketSnapshot


class TradeSignal(str, Enum):
    NO_SIGNAL = "NONE"
    LONG_SIGNAL = "LONG"
    SHORT_SIGNAL = "SHORT"


class SignalEngine:
    def evaluate(self, snap: MarketSnapshot) -> TradeSignal:
        if snap.no_trade_zone:
            return TradeSignal.NO_SIGNAL
        spread_ok = snap.spread > 0 and snap.spread <= max(3.0, snap.price * 0.00005)

        long_ready = (
            snap.sweep_down >= 1.0
            and snap.reclaim >= 1.0
            and snap.long_probability > snap.short_probability
            and snap.smoothed_edge_score > 20.0
            and spread_ok
            and snap.sell_pressure < 0.55
        )
        if long_ready:
            return TradeSignal.LONG_SIGNAL

        short_ready = (
            snap.sweep_up >= 1.0
            and snap.velocity <= 0.0
            and snap.short_probability > snap.long_probability
            and snap.smoothed_edge_score < -20.0
            and spread_ok
            and snap.buy_pressure < 0.55
        )
        if short_ready:
            return TradeSignal.SHORT_SIGNAL

        return TradeSignal.NO_SIGNAL

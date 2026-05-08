from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
from time import time

from core.models import MarketSnapshot
from signal_engine.engine import TradeSignal


class SignalOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    TIMEOUT = "TIMEOUT"


@dataclass
class SignalRecord:
    signal_id: int
    timestamp: float
    signal: str
    edge_score: float
    market_state: str
    spread: float
    imbalance: float
    aggression: float
    velocity: float
    volatility: float
    sweep: str
    reclaim: float
    trap_probability: float
    outcome: SignalOutcome | None = None


class SignalValidationEngine:
    def __init__(self, max_signals: int = 1000, max_events: int = 1000) -> None:
        self.signal_history: deque[SignalRecord] = deque(maxlen=max_signals)
        self.event_history: deque[dict] = deque(maxlen=max_events)
        self._active_signals: dict[int, SignalRecord] = {}
        self._seq = 0

    def register_event(self, snap: MarketSnapshot) -> None:
        self.event_history.append(
            {
                "timestamp": snap.timestamp,
                "market_state": snap.market_intent,
                "price": snap.price,
                "spread": snap.spread,
                "edge_score": snap.edge_score,
                "long_probability": snap.long_probability,
                "short_probability": snap.short_probability,
            }
        )

    def register_signal(self, snap: MarketSnapshot, signal: TradeSignal) -> int | None:
        if signal == TradeSignal.NO_SIGNAL:
            return None
        self._seq += 1
        return self._seq

    def register_accepted_signal(self, snap: MarketSnapshot, signal: TradeSignal, signal_id: int | None) -> None:
        if signal == TradeSignal.NO_SIGNAL or signal_id is None:
            return
        imbalance = snap.buy_pressure - snap.sell_pressure
        aggression = max(snap.buy_pressure, snap.sell_pressure)
        record = SignalRecord(
            signal_id=signal_id,
            timestamp=snap.timestamp or time(),
            signal=signal.value,
            edge_score=snap.edge_score,
            market_state=snap.market_intent,
            spread=snap.spread,
            imbalance=imbalance,
            aggression=aggression,
            velocity=snap.velocity,
            volatility=abs(snap.velocity),
            sweep="UP" if snap.sweep_up >= 1 else "DOWN" if snap.sweep_down >= 1 else "NONE",
            reclaim=snap.reclaim,
            trap_probability=snap.trap_probability,
        )
        self.signal_history.append(record)
        self._active_signals[record.signal_id] = record

    def resolve_signal(self, signal_id: int | None, reason: str, pnl_ticks: float) -> None:
        if signal_id is None:
            return
        rec = self._active_signals.pop(signal_id, None)
        if rec is None:
            return

        if reason == "TIMEOUT":
            rec.outcome = SignalOutcome.TIMEOUT
        elif pnl_ticks > 0:
            rec.outcome = SignalOutcome.WIN
        else:
            rec.outcome = SignalOutcome.LOSS

    def analytics(self) -> dict:
        resolved = [s for s in self.signal_history if s.outcome is not None]
        if not resolved:
            return {
                "best_signal_type": "N/A",
                "worst_signal_type": "N/A",
                "best_market_condition": "N/A",
                "signal_confidence": 0.0,
                "current_signal_quality": "D",
                "best_combo": "N/A",
                "worst_combo": "N/A",
            }

        by_type: dict[str, list[SignalRecord]] = {"LONG": [], "SHORT": []}
        for rec in resolved:
            by_type.setdefault(rec.signal, []).append(rec)

        def wr(records: list[SignalRecord]) -> float:
            if not records:
                return 0.0
            wins = sum(1 for r in records if r.outcome == SignalOutcome.WIN)
            return wins / len(records) * 100.0

        type_wr = {k: wr(v) for k, v in by_type.items() if v}
        best_signal = max(type_wr.items(), key=lambda x: x[1])[0] if type_wr else "N/A"
        worst_signal = min(type_wr.items(), key=lambda x: x[1])[0] if type_wr else "N/A"

        combo_stats = Counter()
        combo_wins = Counter()
        market_stats = Counter()
        market_wins = Counter()
        for rec in resolved:
            spread_tag = "LOW_SPREAD" if rec.spread <= 2.0 else "HIGH_SPREAD"
            edge_tag = "EDGE_HIGH" if abs(rec.edge_score) >= 40 else "EDGE_LOW"
            reclaim_tag = "RECLAIM" if rec.reclaim >= 1 else "NO_RECLAIM"
            combo = f"{rec.market_state}|{rec.sweep}|{spread_tag}|{edge_tag}|{reclaim_tag}"
            combo_stats[combo] += 1
            market_stats[rec.market_state] += 1
            if rec.outcome == SignalOutcome.WIN:
                combo_wins[combo] += 1
                market_wins[rec.market_state] += 1

        combo_wr = {k: combo_wins[k] / v * 100.0 for k, v in combo_stats.items() if v >= 3}
        market_wr = {k: market_wins[k] / v * 100.0 for k, v in market_stats.items() if v >= 3}

        best_combo = max(combo_wr.items(), key=lambda x: x[1])[0] if combo_wr else "N/A"
        worst_combo = min(combo_wr.items(), key=lambda x: x[1])[0] if combo_wr else "N/A"
        best_market = max(market_wr.items(), key=lambda x: x[1])[0] if market_wr else "N/A"

        total_wr = wr(resolved)
        confidence = min(99.0, (len(resolved) / 50.0) * 100.0)
        quality = "A" if total_wr >= 60 else "B" if total_wr >= 52 else "C" if total_wr >= 45 else "D"

        return {
            "best_signal_type": best_signal,
            "worst_signal_type": worst_signal,
            "best_market_condition": best_market,
            "signal_confidence": confidence,
            "current_signal_quality": quality,
            "best_combo": best_combo,
            "worst_combo": worst_combo,
        }

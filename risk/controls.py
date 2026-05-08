from __future__ import annotations

from dataclasses import dataclass

from core.models import FuturesPositionModel, MarketSnapshot


@dataclass
class FuturesRiskControls:
    max_leverage: float = 3.0
    max_margin: float = 10000.0
    max_spread: float = 3.0
    max_volatility: float = 8.0
    min_liquidity_tps: float = 2.0
    min_liquidation_buffer_pct: float = 2.5
    min_signal_strength: float = 70.0
    safety_buffer_ticks: float = 1.0

    def evaluate_entry(
        self,
        snap: MarketSnapshot,
        position: FuturesPositionModel,
        requested_leverage: float,
        cooldown_active: bool,
    ) -> tuple[bool, str]:
        if snap.data_quality_reason not in {"GOOD", "WS_UNSTABLE", "WARMUP", "STALE", ""}:
            return False, snap.data_quality_reason
        if not snap.can_trade_data:
            return False, snap.data_quality_reason
        if snap.book_status not in {"OK", "Missing", "OK_FALLBACK"}:
            return False, "UNKNOWN_BOOK" if snap.book_status == "Unknown" else "BOOK_NOT_OK"
        if snap.depth_status not in {"OK", "Missing"}:
            return False, "DEPTH_NOT_OK"
        block_reasons = {"MISSING_BOOK_TICKER", "MISSING_DEPTH", "STALE_BOOK", "STALE_DEPTH"}
        if snap.data_quality_reason in block_reasons:
            return False, snap.data_quality_reason
        strict_quality_mode = any(
            [
                snap.signal_quality != "D",
                snap.noise_level != "HIGH",
                snap.edge_stability != "UNSTABLE",
                snap.market_regime != "BALANCED",
            ]
        )
        if strict_quality_mode:
            if snap.market_regime == "DEAD_MARKET":
                return False, "DEAD_MARKET"
            if snap.signal_quality != "A":
                return False, "QUALITY_NOT_A"
            if snap.noise_level != "LOW":
                return False, "NOISE_NOT_LOW"
            if snap.edge_stability != "STABLE":
                return False, "EDGE_UNSTABLE"
            if snap.expected_move_ticks < (snap.min_profitable_ticks + self.safety_buffer_ticks):
                return False, "MOVE_TOO_SMALL"
            if snap.expected_move_usdt > 0 or snap.net_expected_profit_after_costs != 0:
                if snap.net_expected_profit_after_costs <= 0:
                    return False, "NO_REAL_PROFIT"
                if snap.expected_move_usdt < snap.minimum_real_move_usdt:
                    return False, "NO_REAL_PROFIT"
            if snap.late_entry_risk == "HIGH" or snap.late_move_penalty > 0.55:
                return False, "LATE_ENTRY_RISK_HIGH"
            if snap.net_edge_score < 25:
                return False, "EDGE_TOO_LOW"
            if snap.best_direction in {"LONG", "SHORT"}:
                signal_dir = "LONG" if snap.edge_score >= 0 else "SHORT"
                if signal_dir != snap.best_direction:
                    return False, "DIRECTION_CONFLICT"
        if snap.spread <= 0 or snap.spread > self.max_spread:
            return False, "SPREAD"
        if abs(snap.velocity) > self.max_volatility:
            return False, "VOLATILITY"
        if snap.ticks_per_second < self.min_liquidity_tps:
            return False, "LIQUIDITY"
        if position.side != "FLAT":
            return False, "IN_POSITION"
        if cooldown_active:
            return False, "COOLDOWN"
        if requested_leverage > self.max_leverage:
            return False, "LEVERAGE"
        if position.initial_margin > self.max_margin:
            return False, "MARGIN"
        if position.side != "FLAT" and position.liquidation_distance_pct < self.min_liquidation_buffer_pct:
            return False, "LIQ_BUFFER"
        if snap.trigger_strength < self.min_signal_strength:
            return False, "WEAK_SIGNAL"
        return True, "PASS"

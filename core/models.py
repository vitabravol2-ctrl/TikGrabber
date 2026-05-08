from __future__ import annotations

from dataclasses import dataclass, field

from replay import ReplayState
from time import time


@dataclass
class MarketSnapshot:
    price: float = 0.0
    spread: float = 0.0
    velocity: float = 0.0
    buy_pressure: float = 0.5
    sell_pressure: float = 0.5
    sweep_up: float = 0.0
    sweep_down: float = 0.0
    trap: float = 0.0
    reclaim: float = 0.0
    panic: float = 0.0
    long_probability: float = 50.0
    short_probability: float = 50.0
    market_intent: str = "BALANCED"
    edge_score: float = 0.0
    latency_ms: float = 0.0
    ticks_per_second: float = 0.0
    data_quality: str = "Warmup"
    ws_status: str = "Disconnected"
    timestamp: float = field(default_factory=time)
    trap_probability: float = 0.0
    volume_24h: float = 0.0
    long_debug: str = ""
    short_debug: str = ""
    block_reason: str = ""
    trigger_strength: float = 0.0
    data_quality_reason: str = "WARMUP"
    net_edge_score: float = 0.0
    expected_move_ticks: float = 0.0
    min_profitable_ticks: float = 0.0
    liquidity_regime_score: float = 0.0
    book_age_ms: float = 0.0
    depth_age_ms: float = 0.0
    book_status: str = "Missing"
    depth_status: str = "Missing"
    can_trade_data: bool = False


@dataclass
class SignalAnalyticsState:
    best_signal_type: str = "N/A"
    worst_signal_type: str = "N/A"
    current_signal_quality: str = "D"
    signal_confidence: float = 0.0
    best_market_condition: str = "N/A"
    best_combo: str = "N/A"
    worst_combo: str = "N/A"


@dataclass
class SimulationState:
    mode: str = "REALISTIC PAPER"
    last_signal: str = "NONE"
    virtual_position: str = "Flat"
    entry: float = 0.0
    exit_price: float = 0.0
    pnl_ticks: float = 0.0
    gross_pnl: float = 0.0
    fees_paid: float = 0.0
    net_pnl: float = 0.0
    net_ticks: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_trade_pnl: float = 0.0
    cooldown_seconds_left: float = 0.0
    cooldown_active: bool = False
    last_trade_result: str = "-"
    hold_seconds: float = 0.0
    last_hold_seconds: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    winrate: float = 0.0
    avg_pnl: float = 0.0
    avg_hold_seconds: float = 0.0
    long_trades: int = 0
    long_wins: int = 0
    short_trades: int = 0
    short_wins: int = 0
    long_winrate: float = 0.0
    short_winrate: float = 0.0
    edge_history: list[float] = field(default_factory=list)
    analytics: SignalAnalyticsState = field(default_factory=SignalAnalyticsState)
    active_trade_side: str = "-"
    quantity: float = 0.0
    notional: float = 100.0
    leverage: float = 1.0
    margin_used: float = 0.0
    tp_progress: float = 0.0
    sl_progress: float = 0.0
    last_event: str = "-"
    signals_count: int = 0
    raw_signal_ticks_count: int = 0
    signals_per_hour: float = 0.0
    raw_signal_ticks_per_hour: float = 0.0
    trades_per_hour: float = 0.0
    avg_signal_strength: float = 0.0
    winrate_by_strength: dict[str, float] = field(default_factory=dict)
    last_entry_price: float = 0.0
    last_exit_price: float = 0.0
    last_closed_side: str = "-"
    last_close_reason: str = "-"
    last_net_pnl: float = 0.0
    last_net_ticks: float = 0.0
    accepted_signal_id: int | None = None
    replay: ReplayState = field(default_factory=ReplayState)
    avg_slippage: float = 0.0
    avg_execution_quality: float = 0.0
    execution_quality: float = 100.0
    queue_delay_ms: float = 0.0
    partial_fills: int = 0
    missed_fills: int = 0


@dataclass
class FuturesExecutionConfig:
    mode: str = "REALISTIC PAPER"
    leverage: float = 1.0
    execution: str = "SIMULATED"
    fees_enabled: bool = True
    slippage_enabled: bool = True


@dataclass
class FuturesPositionModel:
    symbol: str = "BTCUSDT"
    side: str = "FLAT"
    leverage: float = 1.0
    margin_type: str = "ISOLATED"
    entry_price: float = 0.0
    mark_price: float = 0.0
    quantity: float = 0.0
    notional_value: float = 100.0
    initial_margin: float = 0.0
    margin_used: float = 0.0
    maintenance_margin: float = 0.0
    unrealized_pnl: float = 0.0
    liquidation_price: float = 0.0
    liquidation_distance_pct: float = 0.0

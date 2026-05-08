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
    expected_move_bps: float = 0.0
    expected_move_usdt: float = 0.0
    net_expected_profit_after_costs: float = 0.0
    minimum_real_move_usdt: float = 0.0
    required_move_usdt: float = 0.0
    required_move_ticks: float = 0.0
    required_move_bps: float = 0.0
    fee_cost_usdt: float = 0.0
    slippage_cost_usdt: float = 0.0
    spread_cost_usdt: float = 0.0
    funding_buffer_usdt: float = 0.0
    tp_target_usdt: float = 0.0
    sl_target_usdt: float = 0.0
    block_detail: str = ""
    market_phase: str = "ACCUMULATION"
    trap_score: float = 0.0
    exhaustion_score: float = 0.0
    reversal_probability: float = 0.0
    late_entry_risk: str = "LOW"
    fomo_risk: float = 0.0
    late_move_penalty: float = 0.0
    position_mode: str = "SCALP_CONTINUATION"
    liquidity_regime_score: float = 0.0
    book_age_ms: float = 0.0
    depth_age_ms: float = 0.0
    book_status: str = "Missing"
    depth_status: str = "Missing"
    can_trade_data: bool = False
    smoothed_edge_score: float = 0.0
    market_regime: str = "BALANCED"
    signal_quality: str = "D"
    edge_stability: str = "UNSTABLE"
    noise_level: str = "HIGH"
    no_trade_zone: bool = True
    best_direction: str = "FLAT"
    ws_streams_seen: list[str] = field(default_factory=list)
    price_source: str = "BOOKTICKER"
    candidate_direction: str = "NONE"
    candidate_quality: str = "D"
    risk_allowed: bool = False
    sim_can_open: bool = False
    router_can_place: bool = False
    active_order: bool = False
    active_position: bool = False
    cooldown: bool = False
    data_can_trade: bool = False
    final_entry_decision: str = "ENTRY BLOCKED"
    entry_reason: str = "-"
    setup_armed: bool = False
    setup_armed_ticks: int = 0
    continuation_strength: float = 0.0
    breakout_energy: float = 0.0
    trapped_liquidity_score: float = 0.0
    impulse_probability: float = 0.0
    acceleration_score: float = 0.0
    liquidation_potential: float = 0.0
    momentum_persistence: float = 0.0
    expected_move_ticks_real: float = 0.0
    expected_move_usdt_real: float = 0.0
    opportunity_score: float = 0.0
    real_opportunity: bool = False
    microstructure_state: str = "MICRO_RANGE_CHOP"


@dataclass
class PaperScalpingConfig:
    budget_usdt: float = 100.0
    leverage: float = 1.0
    order_notional_usdt: float = 100.0
    tp_ticks: float = 2.0
    sl_ticks: float = 2.0
    fee_mode: str = "MAKER_TAKER"
    tp_mode: str = "DYNAMIC_REQUIRED_MOVE"
    min_desired_profit_usdt: float = 0.03
    min_desired_profit_bps: float = 3.0
    slippage_buffer_bps: float = 1.0
    funding_buffer_bps: float = 0.5
    safety_profit_multiplier: float = 1.3
    timeout_seconds: float = 20.0
    cooldown_seconds: float = 4.0
    min_quality: str = "A"
    allow_quality_b: bool = False
    allow_quality_c: bool = False
    min_expected_move_ticks: float = 3.0
    min_profit_buffer_ticks: float = 1.0
    minimum_real_move_usdt: float = 0.0
    required_move_usdt: float = 0.0
    required_move_ticks: float = 0.0
    required_move_bps: float = 0.0
    fee_cost_usdt: float = 0.0
    slippage_cost_usdt: float = 0.0
    spread_cost_usdt: float = 0.0
    funding_buffer_usdt: float = 0.0
    tp_target_usdt: float = 0.0
    sl_target_usdt: float = 0.0
    block_detail: str = ""
    min_net_edge_score: float = 25.0
    max_spread_ticks: float = 2.0
    max_slippage_ticks: float = 1.0
    max_order_age_seconds: float = 3.0
    daily_max_loss_usdt: float = 3.0
    session_max_loss_usdt: float = 1.0
    max_trades_per_session: int = 10
    max_consecutive_losses: int = 3
    max_allowed_leverage: float = 3.0
    profile: str = "CONSERVATIVE_FUTURES"


@dataclass
class PaperSimConfig:
    tp_ticks: int = 2
    sl_ticks: int = 2
    timeout_seconds: float = 20.0
    cooldown_seconds: float = 4.0
    timeout_extension_seconds: float = 10.0
    timeout_neutral_ticks: float = 1.0


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
    mode: str = "NEAR_LIVE_PAPER"
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
    opened_trades: int = 0
    closed_trades: int = 0
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
    lifecycle_state: str = "FLAT"
    trade_events: list[str] = field(default_factory=list)
    close_latched: bool = False
    order_status: str = "-"
    order_side: str = "-"
    order_type: str = "-"
    order_price: float = 0.0
    order_filled_pct: float = 0.0
    order_avg_fill: float = 0.0
    order_age_ms: float = 0.0
    active_order: bool = False
    sequence_name: str = ""
    sequence_confidence: float = 0.0
    setup_explanation: str = ""
    profile: str = "CONSERVATIVE_FUTURES"
    max_session_loss: float = 1.0
    max_trades_session: int = 10
    signals_candidates: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0
    orders_new: int = 0
    orders_filled: int = 0
    orders_partial: int = 0
    orders_canceled: int = 0
    orders_expired: int = 0
    orders_rejected: int = 0
    scalp_summary: str = ""


@dataclass
class FuturesExecutionConfig:
    mode: str = "NEAR_LIVE_PAPER"
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


@dataclass
class SimOrder:
    order_id: str
    side: str
    position_side: str
    order_type: str
    price: float
    qty: float
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    created_ts: float = field(default_factory=time)
    updated_ts: float = field(default_factory=time)
    status: str = "NEW"
    reason: str = ""

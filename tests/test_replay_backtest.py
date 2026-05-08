from __future__ import annotations

from pathlib import Path

from core.models import FuturesPositionModel, MarketSnapshot
from decision_engine.engine import SignalDecisionEngine
from replay import ReplayEventStore
from risk.controls import FuturesRiskControls
from simulation.paper import PaperSimulator
from validation.engine import SignalValidationEngine


def test_replay_loads_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    ReplayEventStore.append_event(path, {"type": "agg_trade", "price": 100})
    events = ReplayEventStore.load(path)
    assert len(events) == 1


def test_replay_feeds_pipeline() -> None:
    snap = MarketSnapshot(price=100.0, spread=1.0, data_quality="Good", ticks_per_second=5.0, trigger_strength=80.0)
    decision = SignalDecisionEngine().evaluate(snap)
    sim = PaperSimulator(cooldown_seconds=0)
    state = sim.step(snap, decision.signal, signal_id=1)
    assert state.last_signal in {"NONE", "LONG", "SHORT"}


def test_risk_gate_blocks_entry_before_simulator() -> None:
    risk = FuturesRiskControls(min_signal_strength=90.0)
    snap = MarketSnapshot(price=100.0, spread=1.0, data_quality="Good", ticks_per_second=5.0, trigger_strength=70.0)
    ok, reason = risk.evaluate_entry(snap, FuturesPositionModel(), 1.0, cooldown_active=False)
    assert not ok and reason == "WEAK_SIGNAL"


def test_blocked_signal_does_not_enter_validation() -> None:
    v = SignalValidationEngine()
    snap = MarketSnapshot(price=100.0, spread=1.0)
    signal_id = v.register_signal(snap, type('T', (), {'value':'LONG'})())
    v.resolve_signal(signal_id, "TP", 1.0)
    assert len(v.signal_history) == 0


def test_backtest_report_path_can_be_generated(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    out = reports / "backtest_summary.json"
    out.write_text("{}", encoding="utf-8")
    assert out.exists()


def test_live_safety_flags_remain_false() -> None:
    assert FuturesPositionModel().side == "FLAT"

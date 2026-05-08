from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class ReplayState:
    mode: str = "LIVE WS"
    events_processed: int = 0
    replay_speed: float = 1.0
    accepted_signals: int = 0
    blocked_signals: int = 0
    best_state: str = "N/A"
    worst_state: str = "N/A"
    net_result: float = 0.0
    risk_block_reasons: dict[str, int] = field(default_factory=dict)


class ReplayEventStore:
    @staticmethod
    def append_event(path: str | Path, event: dict) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def load(path: str | Path) -> list[dict]:
        events: list[dict] = []
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                events.append(json.loads(line))
        return events


class ReplayEngine:
    def __init__(self, replay_file: str, speed: float = 1.0) -> None:
        self.replay_file = replay_file
        self.speed = speed

    def events(self) -> Iterable[dict]:
        return ReplayEventStore.load(self.replay_file)

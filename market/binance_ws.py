from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal
from websocket import WebSocketApp


@dataclass
class BookState:
    bid: float = 0.0
    ask: float = 0.0
    imbalance: float = 0.0


class BinanceFeedWorker(QObject):
    market_event = Signal(dict)
    status = Signal(str)

    def __init__(self, symbol: str = "btcusdt") -> None:
        super().__init__()
        self.symbol = symbol.lower()
        self._book = BookState()
        self._ws: WebSocketApp | None = None

    def start(self) -> None:
        streams = f"{self.symbol}@trade/{self.symbol}@bookTicker/{self.symbol}@depth5@100ms"
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"
        self._ws = WebSocketApp(
            url,
            on_open=lambda _: self.status.emit("Connected"),
            on_close=lambda *_: self.status.emit("Disconnected"),
            on_error=lambda *_: self.status.emit("Error"),
            on_message=self._on_message,
        )
        self._ws.run_forever(reconnect=5)

    def stop(self) -> None:
        if self._ws:
            self._ws.close()

    def _on_message(self, _: WebSocketApp, raw: str) -> None:
        data = json.loads(raw)
        payload = data.get("data", {})
        stream = data.get("stream", "")

        if "bookTicker" in stream:
            self._book.bid = float(payload.get("b", 0.0))
            self._book.ask = float(payload.get("a", 0.0))
            self.market_event.emit({"type": "book", "bid": self._book.bid, "ask": self._book.ask, "E": payload.get("E", 0)})
        elif "depth" in stream:
            bids = payload.get("b", [])
            asks = payload.get("a", [])
            bid_qty = sum(float(b[1]) for b in bids[:5]) if bids else 0.0
            ask_qty = sum(float(a[1]) for a in asks[:5]) if asks else 0.0
            total = bid_qty + ask_qty
            self._book.imbalance = ((bid_qty - ask_qty) / total) if total else 0.0
        elif "trade" in stream:
            self.market_event.emit(
                {
                    "type": "trade",
                    "price": float(payload.get("p", 0.0)),
                    "buyer_maker": bool(payload.get("m", False)),
                    "event_time": int(payload.get("E", 0)),
                    "bid": self._book.bid,
                    "ask": self._book.ask,
                    "imbalance": self._book.imbalance,
                }
            )


class BinanceFeedThread(QThread):
    market_event = Signal(dict)
    status = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.worker = BinanceFeedWorker()
        self.worker.moveToThread(self)
        self.worker.market_event.connect(self.market_event)
        self.worker.status.connect(self.status)

    def run(self) -> None:
        self.worker.start()

    def stop(self) -> None:
        self.worker.stop()
        self.quit()
        self.wait(1000)

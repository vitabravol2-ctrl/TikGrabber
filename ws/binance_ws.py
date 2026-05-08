from __future__ import annotations

import json
from dataclasses import dataclass
from time import time

from PySide6.QtCore import QObject, QThread, Signal
from websocket import WebSocketApp


@dataclass
class BookState:
    bid: float = 0.0
    ask: float = 0.0
    bid_volume_total: float = 0.0
    ask_volume_total: float = 0.0
    imbalance: float = 0.0
    mini_volume_24h: float = 0.0
    book_ticker_ts: float = 0.0
    depth_ts: float = 0.0
    mini_ticker_ts: float = 0.0
    last_event_ts: float = 0.0


class BinanceFeedWorker(QObject):
    market_event = Signal(dict)
    status = Signal(str)

    def __init__(self, symbol: str = "btcusdt") -> None:
        super().__init__()
        self.symbol = symbol.lower()
        self._book = BookState()
        self._ws: WebSocketApp | None = None

    def start(self) -> None:
        streams = f"{self.symbol}@aggTrade/{self.symbol}@bookTicker/{self.symbol}@depth20@100ms/{self.symbol}@miniTicker"
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"
        self._ws = WebSocketApp(url, on_open=lambda _: self.status.emit("Connected"), on_close=lambda *_: self.status.emit("Disconnected"), on_error=lambda *_: self.status.emit("Error"), on_message=self._on_message)
        self._ws.run_forever(reconnect=5)

    def stop(self) -> None:
        if self._ws:
            self._ws.close()

    def _on_message(self, _: WebSocketApp, raw: str) -> None:
        now_ms = time() * 1000.0
        data = json.loads(raw)
        payload = data.get("data", {})
        stream = data.get("stream", "")

        if "bookTicker" in stream:
            self._book.bid = float(payload.get("b", 0.0))
            self._book.ask = float(payload.get("a", 0.0))
            self._book.book_ticker_ts = now_ms
        elif "depth20" in stream:
            bids = payload.get("b", [])
            asks = payload.get("a", [])
            self._book.bid_volume_total = sum(float(b[1]) for b in bids)
            self._book.ask_volume_total = sum(float(a[1]) for a in asks)
            total = self._book.bid_volume_total + self._book.ask_volume_total
            self._book.imbalance = ((self._book.bid_volume_total - self._book.ask_volume_total) / total) if total else 0.0
            self._book.depth_ts = now_ms
        elif "miniTicker" in stream:
            self._book.mini_volume_24h = float(payload.get("v", 0.0))
            self._book.mini_ticker_ts = now_ms
        elif "aggTrade" in stream:
            self._book.last_event_ts = now_ms
            book_age_ms = max(0.0, now_ms - self._book.book_ticker_ts) if self._book.book_ticker_ts else 1e9
            depth_age_ms = max(0.0, now_ms - self._book.depth_ts) if self._book.depth_ts else 1e9
            self.market_event.emit(
                {
                    "type": "agg_trade",
                    "price": float(payload.get("p", 0.0)),
                    "qty": float(payload.get("q", 0.0)),
                    "buyer_maker": bool(payload.get("m", False)),
                    "event_time": int(payload.get("E", 0)),
                    "bid": self._book.bid,
                    "ask": self._book.ask,
                    "bid_volume_total": self._book.bid_volume_total,
                    "ask_volume_total": self._book.ask_volume_total,
                    "imbalance": self._book.imbalance,
                    "mini_volume_24h": self._book.mini_volume_24h,
                    "book_age_ms": book_age_ms,
                    "depth_age_ms": depth_age_ms,
                    "book_ready": self._book.bid > 0 and self._book.ask > 0,
                    "depth_ready": self._book.bid_volume_total > 0 and self._book.ask_volume_total > 0,
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

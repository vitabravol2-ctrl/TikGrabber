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
    bid_qty: float = 0.0
    ask_qty: float = 0.0
    bid_volume_total: float = 0.0
    ask_volume_total: float = 0.0
    imbalance: float = 0.0
    mini_volume_24h: float = 0.0
    book_ticker_ts: float = 0.0
    depth_ts: float = 0.0
    mini_ticker_ts: float = 0.0
    last_agg_trade_ts: float = 0.0
    ws_streams_seen: set[str] | None = None
    last_stream: str = ""


class BinanceFeedWorker(QObject):
    market_event = Signal(dict)
    status = Signal(str)

    def __init__(self, symbol: str = "btcusdt") -> None:
        super().__init__()
        self.symbol = symbol.lower()
        self._book = BookState()
        self._book.ws_streams_seen = set()
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
            self._book.bid_qty = float(payload.get("B", 0.0))
            self._book.ask_qty = float(payload.get("A", 0.0))
            self._book.book_ticker_ts = now_ms
        elif "depth20" in stream:
            bids = payload.get("bids") or payload.get("b") or []
            asks = payload.get("asks") or payload.get("a") or []
            self._book.bid_volume_total = sum(float(b[1]) for b in bids)
            self._book.ask_volume_total = sum(float(a[1]) for a in asks)
            total = self._book.bid_volume_total + self._book.ask_volume_total
            self._book.imbalance = ((self._book.bid_volume_total - self._book.ask_volume_total) / total) if total else 0.0
            self._book.depth_ts = now_ms
        elif "miniTicker" in stream:
            self._book.mini_volume_24h = float(payload.get("v", 0.0))
            self._book.mini_ticker_ts = now_ms
        elif "aggTrade" in stream:
            self._book.last_agg_trade_ts = now_ms
            self._book.last_stream = stream
            if self._book.ws_streams_seen is not None:
                self._book.ws_streams_seen.add("aggTrade")
            book_age_ms = max(0.0, now_ms - self._book.book_ticker_ts) if self._book.book_ticker_ts else 1e9
            depth_age_ms = max(0.0, now_ms - self._book.depth_ts) if self._book.depth_ts else 1e9
            mini_age_ms = max(0.0, now_ms - self._book.mini_ticker_ts) if self._book.mini_ticker_ts else 1e9
            book_ready = self._book.bid > 0 and self._book.ask > 0
            depth_ready = self._book.bid_volume_total > 0 and self._book.ask_volume_total > 0
            mini_ready = self._book.mini_ticker_ts > 0
            if not book_ready:
                book_status = "missing"
                book_reason = "MISSING_BOOK_TICKER"
            elif book_age_ms >= 2500.0:
                book_status = "stale"
                book_reason = "STALE_BOOK"
            else:
                book_status = "ok"
                book_reason = "GOOD"
            if not depth_ready:
                depth_status = "missing"
                depth_reason = "DEPTH_EMPTY_BOOK" if depth_age_ms < 2500.0 else "MISSING_DEPTH"
            elif depth_age_ms >= 2500.0:
                depth_status = "stale"
                depth_reason = "STALE_DEPTH"
            else:
                depth_status = "ok"
                depth_reason = "GOOD"
            self.market_event.emit(
                {
                    "type": "agg_trade",
                    "price": float(payload.get("p", 0.0)),
                    "qty": float(payload.get("q", 0.0)),
                    "buyer_maker": bool(payload.get("m", False)),
                    "event_time": int(payload.get("E", 0)),
                    "bid": self._book.bid,
                    "ask": self._book.ask,
                    "bid_qty": self._book.bid_qty,
                    "ask_qty": self._book.ask_qty,
                    "bid_volume_total": self._book.bid_volume_total,
                    "ask_volume_total": self._book.ask_volume_total,
                    "imbalance": self._book.imbalance,
                    "mini_volume_24h": self._book.mini_volume_24h,
                    "book_age_ms": book_age_ms,
                    "depth_age_ms": depth_age_ms,
                    "mini_age_ms": mini_age_ms,
                    "book_ready": book_ready,
                    "depth_ready": depth_ready,
                    "mini_ready": mini_ready,
                    "book_status": book_status,
                    "depth_status": depth_status,
                    "book_reason": book_reason,
                    "depth_reason": depth_reason,
                    "ws_streams_seen": sorted(list(self._book.ws_streams_seen or set())),
                    "last_stream": self._book.last_stream,
                }
            )
        else:
            self._book.last_stream = stream
        if self._book.ws_streams_seen is not None:
            stream_name = "bookTicker" if "bookTicker" in stream else "depth20" if "depth20" in stream else "miniTicker" if "miniTicker" in stream else "aggTrade" if "aggTrade" in stream else stream
            self._book.ws_streams_seen.add(stream_name)


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

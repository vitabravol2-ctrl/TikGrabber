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
    fallback_active: bool = False


class BinanceFeedWorker(QObject):
    market_event = Signal(dict)
    status = Signal(str)

    def __init__(self, symbol: str = "btcusdt") -> None:
        super().__init__()
        self.symbol = symbol.lower()
        self._book = BookState()
        self._book.ws_streams_seen = set()
        self._ws: WebSocketApp | None = None
        self._first_event_ts_ms = 0.0

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
        if self._first_event_ts_ms <= 0:
            self._first_event_ts_ms = now_ms
        data = json.loads(raw)
        payload = data.get("data", {})
        stream = data.get("stream", "")

        stream_lower = stream.lower()
        if "bookticker" in stream_lower:
            bid = float(payload.get("b", 0.0) or 0.0)
            ask = float(payload.get("a", 0.0) or 0.0)
            if bid > 0 and ask > 0:
                self._book.bid = bid
                self._book.ask = ask
                self._book.bid_qty = float(payload.get("B", self._book.bid_qty) or self._book.bid_qty)
                self._book.ask_qty = float(payload.get("A", self._book.ask_qty) or self._book.ask_qty)
                self._book.book_ticker_ts = now_ms
        elif "depth20" in stream_lower or "@depth" in stream_lower:
            bids = payload.get("bids") or payload.get("b") or []
            asks = payload.get("asks") or payload.get("a") or []
            self._book.bid_volume_total = sum(float(b[1]) for b in bids)
            self._book.ask_volume_total = sum(float(a[1]) for a in asks)
            total = self._book.bid_volume_total + self._book.ask_volume_total
            self._book.imbalance = ((self._book.bid_volume_total - self._book.ask_volume_total) / total) if total else 0.0
            self._book.depth_ts = now_ms
            if bids and asks:
                top_bid = float(bids[0][0])
                top_ask = float(asks[0][0])
                if (self._book.book_ticker_ts <= 0) or (now_ms - self._book.book_ticker_ts >= 5000.0):
                    if top_bid > 0 and top_ask > 0:
                        self._book.bid = top_bid
                        self._book.ask = top_ask
                        self._book.fallback_active = True
        elif "miniticker" in stream_lower:
            self._book.mini_volume_24h = float(payload.get("v", 0.0))
            self._book.mini_ticker_ts = now_ms
        elif "aggtrade" in stream_lower:
            self._book.last_agg_trade_ts = now_ms
            self._book.last_stream = stream
            if self._book.ws_streams_seen is not None:
                self._book.ws_streams_seen.add("aggTrade")
            book_age_ms = max(0.0, now_ms - self._book.book_ticker_ts) if self._book.book_ticker_ts else None
            depth_age_ms = max(0.0, now_ms - self._book.depth_ts) if self._book.depth_ts else 1e9
            mini_age_ms = max(0.0, now_ms - self._book.mini_ticker_ts) if self._book.mini_ticker_ts else 1e9
            fallback_book = self._book.fallback_active
            book_ready = self._book.bid > 0 and self._book.ask > 0
            depth_ready = self._book.bid_volume_total > 0 and self._book.ask_volume_total > 0
            mini_ready = self._book.mini_ticker_ts > 0
            if not book_ready:
                book_status = "missing"
                book_reason = "MISSING_BOOK_TICKER"
            elif fallback_book:
                book_status = "ok_fallback"
                book_reason = "BOOK_FALLBACK_DEPTH_TOP"
                book_age_ms = depth_age_ms
            elif (book_age_ms is not None) and book_age_ms >= 2500.0:
                book_status = "stale"
                book_reason = "STALE_BOOK"
            else:
                book_status = "ok"
                book_reason = "GOOD"
                self._book.fallback_active = False
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
                    "book_age_ms": -1.0 if book_age_ms is None else book_age_ms,
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
                    "first_event_ts_ms": self._first_event_ts_ms,
                    "now_ms": now_ms,
                }
            )
        else:
            self._book.last_stream = stream
        if self._book.ws_streams_seen is not None:
            stream_name = "bookTicker" if "bookticker" in stream_lower else "depth" if "depth" in stream_lower else "miniTicker" if "miniticker" in stream_lower else "aggTrade" if "aggtrade" in stream_lower else stream
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

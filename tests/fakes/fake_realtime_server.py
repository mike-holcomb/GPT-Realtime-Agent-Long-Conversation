from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from contextlib import asynccontextmanager


class _FakeConnection:
    def __init__(self, events: list[dict], received: list[dict], *, close: bool):
        self._events = asyncio.Queue[str | None]()
        for ev in events:
            self._events.put_nowait(json.dumps(ev))
        if close:
            self._events.put_nowait(None)
        self._received = received

    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - no cleanup needed
        return None

    def __aiter__(self) -> _FakeConnection:
        return self

    async def __anext__(self) -> str:
        msg = await self._events.get()
        if msg is None:
            raise StopAsyncIteration
        return msg

    async def send(self, msg: str) -> None:
        self._received.append(json.loads(msg))

    async def close(self) -> None:  # pragma: no cover - no-op for compatibility
        return None


class FakeRealtimeServer:
    """In-memory stand-in for the OpenAI Realtime server."""

    def __init__(self, events: Iterable[dict] | Iterable[Iterable[dict]]):
        events_list = list(events)
        if events_list and isinstance(events_list[0], dict):
            self._sequences = [events_list]
        else:
            self._sequences = [list(seq) for seq in events_list]
        self.received_batches: list[list[dict]] = []

    @property
    def received(self) -> list[dict]:
        return [msg for batch in self.received_batches for msg in batch]

    @asynccontextmanager
    async def connect(self, *args, **kwargs):  # pragma: no cover - simple context
        events = self._sequences.pop(0)
        close = bool(self._sequences)
        received: list[dict] = []
        self.received_batches.append(received)
        conn = _FakeConnection(events, received, close=close)
        yield conn

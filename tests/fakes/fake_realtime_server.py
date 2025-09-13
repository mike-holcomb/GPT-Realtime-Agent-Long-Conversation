from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from contextlib import asynccontextmanager


class _FakeConnection:
    def __init__(self, events: list[dict], received: list[dict]):
        self._events = asyncio.Queue[str | None]()
        for ev in events:
            self._events.put_nowait(json.dumps(ev))
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

    def __init__(self, events: Iterable[dict]):
        self.events = list(events)
        self.received: list[dict] = []

    @asynccontextmanager
    async def connect(self, *args, **kwargs):  # pragma: no cover - simple context
        conn = _FakeConnection(self.events, self.received)
        yield conn

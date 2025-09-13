from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable


EventHandler = Callable[[dict], Awaitable[None]]


class RealtimeClient:
    """Minimal client skeleton for the OpenAI Realtime API.

    This is a scaffold only; it does not open a real websocket connection yet.
    It shows the intended API surface for the app and handlers.
    """

    def __init__(self, url: str, headers: dict[str, str], on_event: EventHandler):
        self.url = url
        self.headers = headers
        self.on_event = on_event
        self._stop = asyncio.Event()

        # Outbound audio queue (bytes)
        self._audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)

    async def connect(self) -> None:
        """Connect and start recv/send loops (stub)."""
        # In a future iteration, open websockets.connect(...) here and run
        # a recv loop that calls self.on_event for each JSON message.
        await asyncio.sleep(0)

    async def close(self) -> None:
        self._stop.set()

    async def append_audio(self, chunk: bytes) -> None:
        """Queue audio to be sent to the server."""
        try:
            self._audio_q.put_nowait(chunk)
        except asyncio.QueueFull:
            # Metrics handled by app/metrics in a later iteration
            pass

    async def send_json(self, payload: dict) -> None:
        # Placeholder for a generic send method
        _ = json.dumps(payload)
        await asyncio.sleep(0)


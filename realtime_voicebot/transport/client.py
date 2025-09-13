from __future__ import annotations

import asyncio
import base64
import json
import logging
from contextlib import suppress

import websockets

from .events import EventHandler


class RealtimeClient:
    """Minimal WebSocket client for the OpenAI Realtime API."""

    def __init__(self, url: str, headers: dict[str, str], on_event: EventHandler):
        self.url = url
        self.headers = headers
        self.on_event = on_event
        self._stop = asyncio.Event()
        self._ws: websockets.WebSocketClientProtocol | None = None

        # Outbound audio queue (bytes)
        self._audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)

    async def connect(self) -> None:
        """Connect and start recv/send loops."""
        async with websockets.connect(self.url, extra_headers=self.headers) as ws:
            self._ws = ws
            send_task = asyncio.create_task(self._send_audio(ws))
            recv_task = asyncio.create_task(self._recv_loop(ws))
            await self._stop.wait()
            recv_task.cancel()
            send_task.cancel()
            await asyncio.gather(recv_task, send_task, return_exceptions=True)

    async def _recv_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        async for raw in ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                logging.getLogger(__name__).debug("invalid_json", extra={"raw": raw})
                continue
            await self.on_event(event)

    async def _send_audio(self, ws: websockets.WebSocketClientProtocol) -> None:
        while not self._stop.is_set():
            chunk = await self._audio_q.get()
            payload = {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("ascii"),
            }
            await ws.send(json.dumps(payload))

    async def close(self) -> None:
        self._stop.set()
        if self._ws is not None:
            await self._ws.close()

    async def append_audio(self, chunk: bytes) -> None:
        """Queue audio to be sent to the server."""
        with suppress(asyncio.QueueFull):
            self._audio_q.put_nowait(chunk)
        # TODO: surface backpressure metrics when drops occur

    async def send_json(self, payload: dict) -> None:
        if not self._ws:
            raise RuntimeError("WebSocket is not connected")
        await self._ws.send(json.dumps(payload))

from __future__ import annotations

import asyncio
import base64
import json
import logging

import websockets

from ..metrics import (
    audio_frames_dropped_total,
    eos_to_first_delta_ms,
)
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
        self.active_response_id: str | None = None
        self._canceled: set[str] = set()

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
        log = logging.getLogger(__name__)
        async for raw in ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                log.debug("invalid_json", extra={"event_type": "invalid_json", "raw": raw})
                continue
            log.info(
                event.get("type", "unknown"),
                extra={
                    "event_type": event.get("type"),
                    "turn_id": event.get("turn_id"),
                    "response_id": event.get("response_id"),
                    "latency_ms": eos_to_first_delta_ms.last_ms,
                    "tokens_total": event.get("usage", {}).get("total_tokens"),
                    "dropped_frames": audio_frames_dropped_total.value,
                },
            )
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
        try:
            self._audio_q.put_nowait(chunk)
        except asyncio.QueueFull:
            audio_frames_dropped_total.inc()

    async def send_json(self, payload: dict) -> None:
        if not self._ws:
            raise RuntimeError("WebSocket is not connected")
        await self._ws.send(json.dumps(payload))

    async def response_cancel(self, response_id: str) -> None:
        # Mark as canceled locally first to immediately drop further deltas
        # even before the server processes the cancel message.
        self._canceled.add(response_id)
        if self.active_response_id == response_id:
            self.active_response_id = None
        await self.send_json({"type": "response.cancel", "response_id": response_id})

    async def cancel_active_response(self) -> None:
        if self.active_response_id:
            await self.response_cancel(self.active_response_id)

    def is_canceled(self, response_id: str) -> bool:
        return response_id in self._canceled

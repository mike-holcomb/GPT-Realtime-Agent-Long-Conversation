from __future__ import annotations

import asyncio
import base64
import importlib
import json
import logging
import random
import sys
from typing import Any

from ..errors import ErrorCategory
from ..metrics import (
    audio_frames_dropped_total,
    eos_to_first_delta_ms,
    audio_input_queue_depth,
    reconnections_total,
)
from .events import EventHandler


class ConnectionLost(Exception):
    """Internal signal indicating the transport connection dropped."""


class RealtimeClient:
    """Minimal WebSocket client for the OpenAI Realtime API."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str],
        on_event: EventHandler,
        *,
        session_config: dict | None = None,
        backoff_base: float = 0.5,
        backoff_max: float = 8.0,
        ping_interval: float | None = 10.0,
        ping_timeout: float = 20.0,
    ):
        self.url = url
        self.headers = headers
        self.on_event = on_event
        self.session_config = session_config or {}
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self._stop = asyncio.Event()
        self._ws: Any | None = None

        # Outbound audio queue (bytes)
        self._audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)
        self.active_response_id: str | None = None
        self._canceled: set[str] = set()

    async def connect(self) -> None:
        """Connect and maintain the WebSocket with retries.

        Only network/WebSocket failures trigger reconnect. Any other exception
        (e.g. a bug in an event handler) is propagated to the caller so it can
        fail fast with a useful traceback.
        """
        ws_mod = sys.modules.get("websockets") or importlib.import_module("websockets")
        # Build a tuple of exception types that indicate transport-level failure.
        network_excs: tuple[type[BaseException], ...]
        exc_types: list[type[BaseException]] = [ConnectionLost, OSError, ConnectionError]
        ws_exc_mod = getattr(ws_mod, "exceptions", None)
        for name in (
            "ConnectionClosed",
            "WebSocketException",
            "InvalidStatus",
            "InvalidURI",
            "PayloadTooBig",
        ):
            exc = getattr(ws_exc_mod, name, None) if ws_exc_mod else None
            if isinstance(exc, type) and issubclass(exc, BaseException):
                exc_types.append(exc)
        network_excs = tuple(exc_types)

        backoff = self.backoff_base
        connected_once = False
        while not self._stop.is_set():
            try:
                async with ws_mod.connect(self.url, extra_headers=self.headers) as ws:
                    self._ws = ws
                    connected_once = True
                    backoff = self.backoff_base
                    if self.session_config:
                        await ws.send(
                            json.dumps({"type": "session.update", "session": self.session_config})
                        )
                    await self._run_ws(ws)
                    # _run_ws only returns on explicit close; honor stop flag.
                    if self._stop.is_set():
                        break
            except asyncio.CancelledError:
                # Never swallow cancellation; propagate immediately.
                raise
            except network_excs:
                logging.getLogger(__name__).warning(
                    "connection_error",
                    extra={"error_category": ErrorCategory.NETWORK.value},
                )
                if self._stop.is_set():
                    break
                if connected_once:
                    reconnections_total.inc()
                await asyncio.sleep(backoff + random.uniform(0, backoff))
                backoff = min(backoff * 2, self.backoff_max)
            else:
                break

    async def _recv_loop(self, ws: Any) -> None:
        log = logging.getLogger(__name__)
        async for raw in ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                log.debug(
                    "invalid_json",
                    extra={
                        "event_type": "invalid_json",
                        "raw": raw,
                        "error_category": ErrorCategory.PROTOCOL.value,
                    },
                )
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

    async def _send_audio(self, ws: Any) -> None:
        while not self._stop.is_set():
            chunk = await self._audio_q.get()
            payload = {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("ascii"),
            }
            await ws.send(json.dumps(payload))

    async def _keepalive(self, ws: Any) -> None:
        if not self.ping_interval:
            await self._stop.wait()
            return
        while not self._stop.is_set():
            await asyncio.sleep(self.ping_interval)
            try:
                pong = await ws.ping()
                await asyncio.wait_for(pong, timeout=self.ping_timeout)
            except Exception:
                break

    async def _run_ws(self, ws: Any) -> None:
        send_task = asyncio.create_task(self._send_audio(ws))
        recv_task = asyncio.create_task(self._recv_loop(ws))
        tasks = [send_task, recv_task]
        if self.ping_interval:
            tasks.append(asyncio.create_task(self._keepalive(ws)))
        stop_task = asyncio.create_task(self._stop.wait())

        done, pending = await asyncio.wait(tasks + [stop_task], return_when=asyncio.FIRST_COMPLETED)

        # If we were asked to stop, cancel workers and return cleanly.
        if stop_task in done:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return

        # Some worker finished first (either cleanly or with an error).
        # Cancel the rest and propagate the right exception semantics.
        for t in tasks:
            if t not in done:
                t.cancel()
        stop_task.cancel()
        await asyncio.gather(*tasks, stop_task, return_exceptions=True)

        # Prefer to surface the original exception if any worker failed.
        worker_done = next((t for t in done if t is not stop_task), None)
        if worker_done:
            exc = worker_done.exception()
            if exc is not None:
                # Never convert CancelledError; just bubble up.
                if isinstance(exc, asyncio.CancelledError):
                    raise exc
                raise exc

        # Otherwise, treat it as a transport-level connection loss.
        raise ConnectionLost()

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
            logging.getLogger(__name__).warning(
                "audio_input_queue_full",
                extra={
                    "event_type": "audio_input_queue_full",
                    "turn_id": None,
                    "response_id": None,
                    "latency_ms": None,
                    "tokens_total": None,
                    "dropped_frames": audio_frames_dropped_total.value,
                    "queue_depth": self._audio_q.qsize(),
                },
            )
        audio_input_queue_depth.set(self._audio_q.qsize())
        logging.getLogger(__name__).debug(
            "audio_input_queue_depth",
            extra={
                "event_type": "audio_input_queue_depth",
                "turn_id": None,
                "response_id": None,
                "latency_ms": None,
                "tokens_total": None,
                "dropped_frames": audio_frames_dropped_total.value,
                "queue_depth": audio_input_queue_depth.value,
            },
        )

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

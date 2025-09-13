from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

import sounddevice as sd

from ..metrics import (
    audio_frames_dropped_total,
    first_delta_to_playback_ms,
)


@dataclass
class PlayerConfig:
    sample_rate_hz: int = 24_000
    jitter_ms: int = 120
    device_id: int | None = None


class AudioPlayer:
    """Stream PCM16 audio using ``sounddevice``.

    Audio chunks are queued via :meth:`feed` and played back on a background
    task. A small jitter buffer is filled before playback starts to minimize
    underruns.
    """

    def __init__(self, cfg: PlayerConfig):
        self.cfg = cfg
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=128)
        self._task: asyncio.Task | None = None
        self.stream: sd.RawOutputStream | None = None
        self._start_lock = asyncio.Lock()
        self.log = logging.getLogger(__name__)

    async def start(self) -> None:
        self.stream = sd.RawOutputStream(
            samplerate=self.cfg.sample_rate_hz,
            dtype="int16",
            channels=1,
            device=self.cfg.device_id,
        )
        self.stream.start()
        self._task = asyncio.create_task(self._run())
        self.log.info(
            "audio_output_start",
            extra={
                "event_type": "audio_output_start",
                "turn_id": None,
                "response_id": None,
                "latency_ms": first_delta_to_playback_ms.last_ms,
                "tokens_total": None,
                "dropped_frames": audio_frames_dropped_total.value,
            },
        )

    def _is_running(self) -> bool:
        return self.stream is not None and self._task is not None and not self._task.done()

    async def _run(self) -> None:
        assert self.stream is not None
        loop = asyncio.get_running_loop()

        # 2 bytes/sample for int16, mono channel
        jitter_bytes = int(self.cfg.sample_rate_hz * self.cfg.jitter_ms / 1_000) * 2
        buffer = bytearray()
        while len(buffer) < jitter_bytes:
            chunk = await self._queue.get()
            if chunk is None:
                self.stream.stop()
                self.stream.close()
                return
            buffer.extend(chunk)
        await loop.run_in_executor(None, self.stream.write, bytes(buffer))
        first_delta_to_playback_ms.stop()
        self.log.info(
            "playback_start",
            extra={
                "event_type": "playback_start",
                "turn_id": None,
                "response_id": None,
                "latency_ms": first_delta_to_playback_ms.last_ms,
                "tokens_total": None,
                "dropped_frames": audio_frames_dropped_total.value,
            },
        )

        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            await loop.run_in_executor(None, self.stream.write, chunk)

        self.stream.stop()
        self.stream.close()
        self.stream = None

    async def stop(self, barge_in: bool = False) -> None:
        # Only signal the background task if it's running.
        if self._task is not None:
            await self._queue.put(None)
            await self._task
            self._task = None
        event = "barge_in" if barge_in else "audio_output_stop"
        self.log.info(
            event,
            extra={
                "event_type": event,
                "turn_id": None,
                "response_id": None,
                "latency_ms": None,
                "tokens_total": None,
                "dropped_frames": audio_frames_dropped_total.value,
            },
        )

    async def flush(self) -> None:
        """Drop pending audio and stop playback immediately."""
        while not self._queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
        await self.stop()

    async def feed(self, chunk: bytes) -> None:
        # If previously flushed/stopped (e.g., barge-in), lazily restart so
        # subsequent deltas resume playback without external coordination.
        if not self._is_running():
            async with self._start_lock:
                if not self._is_running():
                    await self.start()
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            audio_frames_dropped_total.inc()

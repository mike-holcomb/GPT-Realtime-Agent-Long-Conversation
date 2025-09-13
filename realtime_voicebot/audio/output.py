from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class PlayerConfig:
    sample_rate_hz: int = 24_000
    jitter_ms: int = 120
    device_id: int | None = None


class AudioPlayer:
    """Stub streaming audio player.

    Real implementation will use sounddevice.RawOutputStream and start
    playback on the first delta. This stub exposes the same interface.
    """

    def __init__(self, cfg: PlayerConfig):
        self.cfg = cfg
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        async def _run():
            while True:
                chunk = await self._queue.get()
                if chunk is None:  # type: ignore[comparison-overlap]
                    break
        self._task = asyncio.create_task(_run())

    async def stop(self) -> None:
        await self._queue.put(None)  # type: ignore[arg-type]
        if self._task:
            await self._task

    async def feed(self, chunk: bytes) -> None:
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            # In a later iteration, count drops via metrics
            pass


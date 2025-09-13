from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class MicConfig:
    sample_rate_hz: int = 24_000
    chunk_ms: int = 40
    device_id: int | None = None


class MicStreamer:
    """Stub mic streamer that would push PCM16 chunks into a queue.

    Real implementation will use sounddevice.RawInputStream. This stub keeps
    the API surface for orchestration and tests.
    """

    def __init__(self, cfg: MicConfig, q: asyncio.Queue[bytes]):
        self.cfg = cfg
        self.q = q
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        # Placeholder: no-op start
        await asyncio.sleep(0)

    async def stop(self) -> None:
        # Signal end of stream
        await self.q.put(b"")


from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass

import sounddevice as sd


@dataclass
class MicConfig:
    sample_rate_hz: int = 24_000
    chunk_ms: int = 40
    device_id: int | None = None


class MicStreamer:
    """Stream microphone audio into an asyncio.Queue.

    Uses ``sounddevice.RawInputStream`` to capture mono PCM16 audio and pushes
    fixed-size chunks into ``q``.
    """

    def __init__(self, cfg: MicConfig, q: asyncio.Queue[bytes]):
        self.cfg = cfg
        self.q = q
        self.stream: sd.RawInputStream | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _on_audio(self, data: bytes) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            self.q.put_nowait(data)

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        blocksize = int(self.cfg.sample_rate_hz * self.cfg.chunk_ms / 1_000)

        def callback(
            indata, frames, time, status
        ) -> None:  # pragma: no cover - sounddevice callback
            if status:
                # For now we ignore status flags; they can be surfaced via logging later.
                pass
            if self._loop:
                self._loop.call_soon_threadsafe(self._on_audio, bytes(indata))

        self.stream = sd.RawInputStream(
            samplerate=self.cfg.sample_rate_hz,
            blocksize=blocksize,
            dtype="int16",
            channels=1,
            callback=callback,
            device=self.cfg.device_id,
        )
        self.stream.start()

    async def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        # Signal end of stream to consumers
        await self.q.put(b"")

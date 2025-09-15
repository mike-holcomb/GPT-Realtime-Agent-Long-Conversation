import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

dummy_sd = types.ModuleType("sounddevice")


class _Stub:
    def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - stub
        pass

    def start(self) -> None:  # pragma: no cover - stub
        pass

    def stop(self) -> None:  # pragma: no cover - stub
        pass

    def close(self) -> None:  # pragma: no cover - stub
        pass

    def write(self, data: bytes) -> None:  # pragma: no cover - stub
        pass


dummy_sd.RawOutputStream = _Stub
sys.modules["sounddevice"] = dummy_sd

from realtime_voicebot.audio.output import AudioPlayer, PlayerConfig  # noqa: E402
from realtime_voicebot.metrics import (  # noqa: E402
    audio_frames_dropped_total,
    audio_output_queue_depth,
)


class DummyStream:
    def __init__(self, *args, **kwargs):
        self.start_calls = 0
        self.stopped = False
        self.write_calls: list[bytes] = []

    def start(self) -> None:
        self.start_calls += 1

    def write(self, data: bytes) -> None:  # pragma: no cover - stub
        self.write_calls.append(data)

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:  # pragma: no cover - stub
        pass


def test_flush_stops_player(monkeypatch):
    import sounddevice as sd

    async def run() -> None:
        dummy = DummyStream()
        monkeypatch.setattr(sd, "RawOutputStream", lambda *a, **k: dummy)
        player = AudioPlayer(PlayerConfig(jitter_ms=0))
        await player.start()
        await player.feed(b"1234")
        await player.flush()
        assert player.stream is None
        assert player._queue.empty()

    asyncio.run(run())


def test_feed_queue_full_increments_metric(monkeypatch):
    import sounddevice as sd

    async def run() -> None:
        dummy = DummyStream()
        monkeypatch.setattr(sd, "RawOutputStream", lambda *a, **k: dummy)
        audio_frames_dropped_total.value = 0
        audio_output_queue_depth.value = 0
        player = AudioPlayer(PlayerConfig(jitter_ms=0))
        player._queue = asyncio.Queue(maxsize=1)
        await player.start()
        await player.feed(b"1")
        await player.feed(b"2")
        assert audio_frames_dropped_total.value == 1
        assert audio_output_queue_depth.value == 1
        await player.stop()

    asyncio.run(run())

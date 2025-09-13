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


class DummyStream:
    def __init__(self, *args, **kwargs):
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def write(self, data: bytes) -> None:  # pragma: no cover - stub
        pass

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

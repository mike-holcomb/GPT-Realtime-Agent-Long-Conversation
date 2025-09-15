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


def test_restart_after_flush_respects_jitter(monkeypatch):
    import sounddevice as sd

    async def run() -> None:
        dummy = DummyStream()
        monkeypatch.setattr(sd, "RawOutputStream", lambda *a, **k: dummy)
        player = AudioPlayer(PlayerConfig(sample_rate_hz=1000, jitter_ms=10))

        loop = asyncio.get_running_loop()

        async def fake_run_in_executor(executor, func, *args):
            func(*args)
            return None

        monkeypatch.setattr(loop, "run_in_executor", fake_run_in_executor)

        jitter_bytes = int(player.cfg.sample_rate_hz * player.cfg.jitter_ms / 1_000) * 2

        await player.start()
        await player.feed(b"a" * (jitter_bytes // 2))
        await player.flush()
        assert dummy.start_calls == 1

        await player.feed(b"b" * (jitter_bytes // 2))
        await asyncio.sleep(0)
        assert dummy.start_calls == 2
        assert dummy.write_calls == []

        await player.feed(b"c" * (jitter_bytes // 2))
        await asyncio.sleep(0)
        assert len(dummy.write_calls) == 1
        assert len(dummy.write_calls[0]) == jitter_bytes

        await player.flush()

    asyncio.run(run())

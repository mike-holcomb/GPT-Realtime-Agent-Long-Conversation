import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeStream:
    def __init__(self, *args, **kwargs):
        self.written = []

    def start(self):
        pass

    def write(self, data: bytes):
        self.written.append(data)

    def stop(self):
        pass

    def close(self):
        pass


def test_audio_player_jitter_and_flush(monkeypatch):
    async def main():
        # Provide fake sounddevice module before importing player
        import types

        fake_sd = types.SimpleNamespace(RawOutputStream=FakeStream)
        monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

        from realtime_voicebot.audio.output import AudioPlayer, PlayerConfig

        cfg = PlayerConfig(sample_rate_hz=1000, jitter_ms=10)
        player = AudioPlayer(cfg)
        await player.start()

        stream = player.stream  # type: ignore[assignment]

        await player.feed(b"a" * 10)  # below jitter
        await asyncio.sleep(0)
        assert stream.written == []

        await player.feed(b"a" * 10)  # reach jitter (20 bytes)
        await asyncio.sleep(0)
        assert len(stream.written) == 1 and len(stream.written[0]) == 20

        await player.feed(b"b" * 5)
        for _ in range(5):
            if len(stream.written) >= 2:
                break
            await asyncio.sleep(0.01)
        assert len(stream.written) == 2 and len(stream.written[1]) == 5

        await player.feed(b"c" * 5)
        await player.stop()
        await asyncio.sleep(0)
        # last chunk should be flushed, no new writes after stop
        assert len(stream.written) == 2

    asyncio.run(main())

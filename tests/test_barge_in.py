import asyncio
import base64
import logging
import sys
import types
from pathlib import Path

import pytest

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


dummy_sd.RawOutputStream = _Stub
sys.modules["sounddevice"] = dummy_sd
sys.modules["websockets"] = types.ModuleType("websockets")

from realtime_voicebot.handlers.core import (  # noqa: E402
    handle_conversation_item_created,
    handle_response_audio_delta,
    handle_response_created,
)
from realtime_voicebot.handlers.dispatcher import Dispatcher  # noqa: E402
from realtime_voicebot.transport.client import RealtimeClient  # noqa: E402
from tests.fakes.fake_realtime_server import FakeRealtimeServer  # noqa: E402


class DummyPlayer:
    def __init__(self) -> None:
        self.flush_called = False
        self.feed_chunks: list[bytes] = []

    async def feed(self, chunk: bytes) -> None:
        self.feed_chunks.append(chunk)

    async def flush(self) -> None:
        self.flush_called = True


def test_barge_in_sends_cancel_and_stops_player(caplog: pytest.LogCaptureFixture) -> None:
    async def run() -> None:
        client = RealtimeClient("ws://example", {}, lambda e: None)
        sent: list[dict] = []

        async def fake_send_json(payload: dict) -> None:
            sent.append(payload)

        client.send_json = fake_send_json  # type: ignore[method-assign]
        player = DummyPlayer()

        await handle_response_audio_delta(
            {
                "type": "response.audio.delta",
                "response_id": "r1",
                "audio": base64.b64encode(b"hi").decode(),
            },
            client,
            player,
        )
        assert client.active_response_id == "r1"
        assert player.feed_chunks == [b"hi"]

        with caplog.at_level(logging.INFO):
            await handle_conversation_item_created(
                {"type": "conversation.item.created", "item": {"role": "user", "id": "u1"}},
                client,
                player,
            )

        assert sent == [{"type": "response.cancel", "response_id": "r1"}]
        assert player.flush_called
        assert any(record.message == "barge_in" for record in caplog.records)

        await handle_response_audio_delta(
            {
                "type": "response.audio.delta",
                "response_id": "r1",
                "audio": base64.b64encode(b"again").decode(),
            },
            client,
            player,
        )
        assert player.feed_chunks == [b"hi"]

    asyncio.run(run())


def test_barge_in_before_audio_sends_cancel(monkeypatch) -> None:
    async def run() -> None:
        events = [
            {"type": "response.created", "response": {"id": "r1"}},
            {"type": "conversation.item.created", "item": {"role": "user", "id": "u1"}},
            {
                "type": "response.audio.delta",
                "response_id": "r1",
                "audio": base64.b64encode(b"after").decode(),
            },
        ]
        server = FakeRealtimeServer(events)
        import types
        fake_ws = types.SimpleNamespace(connect=server.connect, WebSocketClientProtocol=object)
        monkeypatch.setitem(sys.modules, "websockets", fake_ws)

        dispatcher = Dispatcher()
        player = DummyPlayer()
        client = RealtimeClient("ws://fake", {}, dispatcher.dispatch, ping_interval=None)

        dispatcher.register("response.created", lambda e: handle_response_created(e, client))
        dispatcher.register(
            "conversation.item.created",
            lambda e: handle_conversation_item_created(e, client, player),
        )
        dispatcher.register(
            "response.audio.delta",
            lambda e: handle_response_audio_delta(e, client, player),
        )

        task = asyncio.create_task(client.connect())
        await asyncio.sleep(0.1)
        await client.close()
        await task

        assert server.received == [{"type": "response.cancel", "response_id": "r1"}]
        assert player.feed_chunks == []

    asyncio.run(run())

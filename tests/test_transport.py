import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.handlers.dispatcher import Dispatcher
from tests.fakes.fake_realtime_server import FakeRealtimeServer


class DummyPlayer:
    async def feed(self, chunk: bytes) -> None:  # pragma: no cover - stub
        return None

    async def flush(self) -> None:  # pragma: no cover - stub
        return None


def test_transport_barge_in_response_cancel(monkeypatch):
    async def main():
        events = [
            {"type": "session.created"},
            {"type": "response.created", "response": {"id": "r1"}},
            {"type": "conversation.item.created", "item": {"role": "user", "id": "u1"}},
        ]

        server = FakeRealtimeServer(events)

        import types

        fake_ws = types.SimpleNamespace(connect=server.connect, WebSocketClientProtocol=object)
        monkeypatch.setitem(sys.modules, "websockets", fake_ws)

        from realtime_voicebot.handlers.core import (
            handle_conversation_item_created,
            handle_response_created,
        )
        from realtime_voicebot.transport.client import RealtimeClient

        dispatcher = Dispatcher()
        player = DummyPlayer()

        async def on_response_created(event):
            await handle_response_created(event, client)

        async def on_item_created(event):
            await handle_conversation_item_created(event, client, player)

        dispatcher.register("response.created", on_response_created)
        dispatcher.register("conversation.item.created", on_item_created)

        client = RealtimeClient("ws://fake", {}, dispatcher.dispatch)
        task = asyncio.create_task(client.connect())
        await asyncio.sleep(0.1)
        await client.close()
        await task

        assert server.received == [{"type": "response.cancel", "response_id": "r1"}]

    asyncio.run(main())


def test_reconnect_resends_session_update(monkeypatch, caplog):
    async def main():
        events = [
            [{"type": "session.created"}],
            [{"type": "session.created"}, {"type": "response.audio.delta", "audio": ""}],
        ]
        server = FakeRealtimeServer(events)

        import types

        fake_ws = types.SimpleNamespace(connect=server.connect, WebSocketClientProtocol=object)
        monkeypatch.setitem(sys.modules, "websockets", fake_ws)

        from realtime_voicebot.metrics import reconnections_total
        from realtime_voicebot.transport.client import RealtimeClient

        reconnections_total.value = 0

        received: list[str] = []

        async def on_event(event):
            received.append(event["type"])

        client = RealtimeClient(
            "ws://fake",
            {},
            on_event,
            session_config={"voice": "test"},
            backoff_base=0.01,
            backoff_max=0.02,
            ping_interval=None,
        )

        caplog.set_level(logging.WARNING)
        task = asyncio.create_task(client.connect())
        await asyncio.sleep(0.2)
        await client.close()
        await task

        assert received == ["session.created", "session.created", "response.audio.delta"]
        assert [msg["type"] for batch in server.received_batches for msg in batch] == [
            "session.update",
            "session.update",
        ]
        assert reconnections_total.value == 1
        assert any(rec.error_category == "network" for rec in caplog.records)

    asyncio.run(main())

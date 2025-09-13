import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.handlers.dispatcher import Dispatcher
from tests.fakes.fake_realtime_server import FakeRealtimeServer


def test_transport_event_dispatch_and_barge_in_response_cancel(monkeypatch):
    async def main():
        events = [
            {"type": "session.created"},
            {"type": "response.audio.delta", "audio": ""},
            {"type": "conversation.item.created", "item": {"role": "user"}},
            {"type": "response.done"},
        ]

        server = FakeRealtimeServer(events)

        import types

        fake_ws = types.SimpleNamespace(connect=server.connect, WebSocketClientProtocol=object)
        monkeypatch.setitem(sys.modules, "websockets", fake_ws)

        from realtime_voicebot.transport.client import RealtimeClient

        received = []
        dispatcher = Dispatcher()

        async def record(event):
            received.append(event["type"])

        for etype in ["session.created", "response.audio.delta", "response.done"]:
            dispatcher.register(etype, record)

        async def on_item_created(event):
            received.append(event["type"])
            if event["item"]["role"] == "user":
                await client.send_json({"type": "response.cancel"})

        dispatcher.register("conversation.item.created", on_item_created)

        client = RealtimeClient("ws://fake", {}, dispatcher.dispatch)
        task = asyncio.create_task(client.connect())
        await asyncio.sleep(0.1)
        await client.close()
        await task

        assert received == [e["type"] for e in events]
        assert {msg["type"] for msg in server.received} == {"response.cancel"}

    asyncio.run(main())

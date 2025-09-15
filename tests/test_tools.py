import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.handlers.core import handle_response_done
from realtime_voicebot.handlers.dispatcher import Dispatcher
from realtime_voicebot.handlers.tools import (
    ToolRegistry,
    clock_tool,
    handle_tool_call,
    http_tool,
)
from realtime_voicebot.state.conversation import ConversationState, SummaryPolicy
from realtime_voicebot.transport.client import RealtimeClient
from tests.fakes.fake_realtime_server import FakeRealtimeServer


def test_tool_call_roundtrip(monkeypatch):
    async def main():
        events = [
            {"type": "session.created"},
            {
                "type": "response.output_item.create",
                "response_id": "r1",
                "item": {
                    "type": "tool_call",
                    "name": "clock",
                    "call_id": "c1",
                    "arguments": {},
                },
            },
            {
                "type": "response.done",
                "response": {
                    "output": [
                        {
                            "id": "a1",
                            "role": "assistant",
                            "content": [{"transcript": "time is noon"}],
                        }
                    ],
                    "usage": {},
                },
            },
        ]
        server = FakeRealtimeServer(events)
        import types

        fake_ws = types.SimpleNamespace(connect=server.connect, WebSocketClientProtocol=object)
        monkeypatch.setitem(sys.modules, "websockets", fake_ws)

        registry = ToolRegistry()
        registry.register(clock_tool)
        registry.register(http_tool)
        monkeypatch.setattr(clock_tool, "func", lambda: "noon")

        dispatcher = Dispatcher()
        state = ConversationState()
        policy = SummaryPolicy(threshold_tokens=10_000, keep_last_turns=2)

        client = RealtimeClient(
            "ws://fake",
            {},
            dispatcher.dispatch,
            session_config={"tools": registry.specs()},
        )

        dispatcher.register(
            "response.output_item.create",
            lambda ev: handle_tool_call(ev, client, registry),
        )
        dispatcher.register(
            "response.done",
            lambda ev: handle_response_done(ev, client, state, DummySummarizer(), policy),
        )

        task = asyncio.create_task(client.connect())
        await asyncio.sleep(0.1)
        await client.close()
        await task

        first_msg = server.received[0]
        assert first_msg["type"] == "session.update"
        assert {t["name"] for t in first_msg["session"]["tools"]} == {"clock", "http_get"}

        result_msg = next(
            msg for msg in server.received if msg["type"] == "response.output_item.create"
        )
        assert result_msg["item"]["type"] == "tool_result"
        assert result_msg["item"]["content"][0]["text"] == "noon"

        assert state.history[0].text == "time is noon"

    class DummySummarizer:
        async def summarize(self, turns, language=None):
            return ""

    asyncio.run(main())


def test_http_tool_fetches():
    import http.server
    import socketserver
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # pragma: no cover - trivial
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format, *args):  # pragma: no cover - silence
            return

    with socketserver.TCPServer(("localhost", 0), Handler) as srv:
        thread = threading.Thread(target=srv.serve_forever)
        thread.start()
        url = f"http://localhost:{srv.server_address[1]}"
        try:
            text = http_tool.func(url=url)
            assert text == "ok"
        finally:
            srv.shutdown()
            thread.join()

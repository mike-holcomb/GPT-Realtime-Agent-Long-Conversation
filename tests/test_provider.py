from __future__ import annotations

import asyncio
import sys
import types

from realtime_voicebot.config import Settings
from realtime_voicebot.transport.client import RealtimeClient, build_ws_url_headers
from tests.fakes.fake_realtime_server import FakeRealtimeServer


def _fake_ws(monkeypatch, server):
    fake_ws = types.SimpleNamespace(connect=server.connect, WebSocketClientProtocol=object)
    monkeypatch.setitem(sys.modules, "websockets", fake_ws)


def test_build_openai_ws(monkeypatch):
    settings = Settings(openai_api_key="sk")
    url, headers = build_ws_url_headers(settings)
    assert url == "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"
    assert headers == {
        "Authorization": "Bearer sk",
        "OpenAI-Beta": "realtime=v1",
    }
    server = FakeRealtimeServer([{"type": "session.created"}])
    _fake_ws(monkeypatch, server)

    async def on_event(ev):
        await client.close()

    client = RealtimeClient(url, headers, on_event, session_config={"voice": "test"})
    asyncio.run(client.connect())
    assert server.received == [{"type": "session.update", "session": {"voice": "test"}}]


def test_build_azure_ws(monkeypatch):
    settings = Settings(
        provider="azure",
        azure_openai_api_key="key",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_version="2024-06-01",
        azure_openai_deployment="realtime",
    )
    url, headers = build_ws_url_headers(settings)
    assert (
        url
        == "wss://example.openai.azure.com/openai/realtime?api-version=2024-06-01&deployment=realtime"
    )
    assert headers == {"api-key": "key"}
    server = FakeRealtimeServer([{"type": "session.created"}])
    _fake_ws(monkeypatch, server)

    async def on_event(ev):
        await client.close()

    client = RealtimeClient(url, headers, on_event, session_config={"voice": "test"})
    asyncio.run(client.connect())
    assert server.received == [{"type": "session.update", "session": {"voice": "test"}}]

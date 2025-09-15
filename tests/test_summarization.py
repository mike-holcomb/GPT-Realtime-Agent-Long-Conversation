import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.handlers.core import handle_response_done
from realtime_voicebot.transport.events import Dispatcher
from realtime_voicebot.state.conversation import (
    ConversationState,
    SummaryPolicy,
    Turn,
)
from realtime_voicebot.summarization.openai_impl import OpenAISummarizer
from realtime_voicebot.transport.client import RealtimeClient
from tests.fakes.fake_realtime_server import FakeRealtimeServer


def test_summarize_and_prune_inserts_summary_and_keeps_last_turns():
    async def main():
        state = ConversationState(latest_tokens=200)
        for i in range(5):
            state.append(Turn(role="user", item_id=str(i), text=f"t{i}"))

        class DummySummarizer:
            async def summarize(self, turns, language=None):
                return "Summary: dummy"

        await state.summarize_and_prune(DummySummarizer(), keep_last_turns=2)

        assert len(state.history) == 3
        assert state.history[0].role == "system"
        assert state.history[0].text.startswith("Summary:")
        assert [t.item_id for t in state.history[1:]] == ["3", "4"]
        assert state.summary_count == 1

    asyncio.run(main())


def test_openai_summarizer_returns_non_empty_string():
    async def main():
        summarizer = OpenAISummarizer()
        text = await summarizer.summarize([Turn(role="user", item_id="1", text="hello")])
        assert text.strip() != ""

    asyncio.run(main())


def test_e2e_summary_added_and_prunes_history(monkeypatch):
    async def main():
        events = [
            {
                "type": "response.done",
                "response": {
                    "output": [
                        {
                            "id": "a2",
                            "role": "assistant",
                            "content": [{"transcript": "resp"}],
                        }
                    ],
                    "usage": {"total_tokens": 5000},
                },
            }
        ]

        server = FakeRealtimeServer(events)

        import types

        fake_ws = types.SimpleNamespace(connect=server.connect, WebSocketClientProtocol=object)
        monkeypatch.setitem(sys.modules, "websockets", fake_ws)

        state = ConversationState()
        state.append(Turn(role="user", item_id="u1", text="hola"))
        state.append(Turn(role="assistant", item_id="a1", text="hola"))
        state.append(Turn(role="user", item_id="u2", text="gracias"))

        summarizer = OpenAISummarizer()
        policy = SummaryPolicy(threshold_tokens=1000, keep_last_turns=2, language_policy="auto")

        dispatcher = Dispatcher()

        client = RealtimeClient("ws://fake", {}, dispatcher.dispatch)
        dispatcher.on(
            "response.done",
            lambda ev: handle_response_done(ev, client, state, summarizer, policy),
        )

        task = asyncio.create_task(client.connect())
        await asyncio.sleep(0.1)
        await client.close()
        await task

        # Summary inserted and history pruned
        assert state.history[0].role == "system"
        assert [t.item_id for t in state.history[1:]] == ["u2", "a2"]

        # Server received summary creation and deletes of old items
        types_sent = {msg["type"] for msg in server.received}
        assert "conversation.item.create" in types_sent
        delete_ids = {
            msg.get("item_id")
            for msg in server.received
            if msg["type"] == "conversation.item.delete"
        }
        assert {"u1", "a1"} == delete_ids

    asyncio.run(main())

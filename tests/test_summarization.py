import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.handlers.core import (
    handle_conversation_item_created,
    handle_conversation_item_retrieved,
    handle_response_done,
)
from realtime_voicebot.state.conversation import (
    ConversationState,
    SummaryPolicy,
    Turn,
)
from realtime_voicebot.summarization.openai_impl import OpenAISummarizer
from realtime_voicebot.transport.client import RealtimeClient
from realtime_voicebot.transport.events import Dispatcher
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


def test_conversation_item_retrieved_backfills_text():
    async def main():
        state = ConversationState()

        class DummyClient:
            def __init__(self) -> None:
                self.active_response_id: str | None = None

            async def cancel_active_response(self) -> None:  # pragma: no cover - not used
                raise AssertionError("cancel should not be called")

        class DummyPlayer:
            async def flush(self) -> None:  # pragma: no cover - not used
                raise AssertionError("flush should not be called")

        await handle_conversation_item_created(
            {
                "type": "conversation.item.created",
                "item": {"id": "u1", "role": "user"},
            },
            DummyClient(),
            DummyPlayer(),
            state,
        )

        assert state.history[0].text is None

        class DummySummarizer:
            async def summarize(self, turns, language=None):  # pragma: no cover - unused
                raise AssertionError("summarize should not be called")

        policy = SummaryPolicy(threshold_tokens=1000, keep_last_turns=2)
        await handle_conversation_item_retrieved(
            {
                "type": "conversation.item.retrieved",
                "item": {
                    "id": "u1",
                    "role": "user",
                    "content": [{"type": "input_text", "transcript": "hola"}],
                },
            },
            None,
            state,
            DummySummarizer(),
            policy,
        )

        assert state.history[0].text == "hola"

        # Retrieval without a pre-existing placeholder appends a new turn.
        state2 = ConversationState()
        await handle_conversation_item_retrieved(
            {
                "type": "conversation.item.retrieved",
                "item": {
                    "id": "u2",
                    "role": "user",
                    "content": [{"type": "input_text", "transcript": "bonjour"}],
                },
            },
            None,
            state2,
            DummySummarizer(),
            policy,
        )

        assert [turn.item_id for turn in state2.history] == ["u2"]
        assert state2.history[0].text == "bonjour"

    asyncio.run(main())


def test_summary_defers_until_transcript_backfilled():
    async def main():
        state = ConversationState()
        state.append(Turn(role="user", item_id="u1"))
        state.append(Turn(role="assistant", item_id="a1", text="ack"))
        state.append(Turn(role="user", item_id="u2", text="next"))

        class DummySummarizer:
            def __init__(self) -> None:
                self.calls = 0

            async def summarize(self, turns, language=None):
                self.calls += 1
                return "Summary stub"

        summarizer = DummySummarizer()
        policy = SummaryPolicy(threshold_tokens=10, keep_last_turns=3)

        class DummyClient:
            def __init__(self) -> None:
                self.active_response_id: str | None = None
                self.sent: list[dict] = []

            def clear_canceled(self, response_id: str | None) -> None:  # pragma: no cover - trivial
                return None

            async def send_json(self, payload: dict) -> None:
                self.sent.append(payload)

        client = DummyClient()

        await handle_response_done(
            {
                "type": "response.done",
                "response": {
                    "id": "r1",
                    "output": [
                        {
                            "id": "a2",
                            "role": "assistant",
                            "content": [{"transcript": "resp"}],
                        }
                    ],
                    "usage": {"total_tokens": 50},
                },
            },
            client,
            state,
            summarizer,
            policy,
        )

        assert summarizer.calls == 0
        assert state.summary_count == 0
        assert state.pending_summary_tokens == 50
        assert client.sent == []
        assert [t.item_id for t in state.history] == ["u1", "a1", "u2", "a2"]

        await handle_response_done(
            {
                "type": "response.done",
                "response": {
                    "id": "r2",
                    "output": [
                        {
                            "id": "a3",
                            "role": "assistant",
                            "content": [{"transcript": "second"}],
                        }
                    ],
                    "usage": {"total_tokens": 5},
                },
            },
            client,
            state,
            summarizer,
            policy,
        )

        assert summarizer.calls == 0
        assert state.pending_summary_tokens == 50
        assert state.latest_tokens == 5
        assert [t.item_id for t in state.history] == ["u1", "a1", "u2", "a2", "a3"]

        await handle_conversation_item_retrieved(
            {
                "type": "conversation.item.retrieved",
                "item": {
                    "id": "u1",
                    "role": "user",
                    "content": [{"type": "input_text", "transcript": "hola"}],
                },
            },
            client,
            state,
            summarizer,
            policy,
        )

        assert summarizer.calls == 1
        assert state.summary_count == 1
        assert state.pending_summary_tokens == 0
        assert state.history[0].role == "system"
        assert [t.item_id for t in state.history[1:]] == ["u2", "a2", "a3"]
        assert [msg["type"] for msg in client.sent] == [
            "conversation.item.create",
            "conversation.item.delete",
            "conversation.item.delete",
        ]
        delete_ids = [
            msg.get("item_id") for msg in client.sent if msg["type"] == "conversation.item.delete"
        ]
        assert delete_ids == ["u1", "a1"]

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
            },
            {
                "type": "conversation.item.retrieved",
                "item": {
                    "id": "u1",
                    "role": "user",
                    "content": [{"type": "input_text", "transcript": "hola"}],
                },
            },
        ]

        server = FakeRealtimeServer(events)

        import types

        fake_ws = types.SimpleNamespace(connect=server.connect, WebSocketClientProtocol=object)
        monkeypatch.setitem(sys.modules, "websockets", fake_ws)

        state = ConversationState()
        state.append(Turn(role="user", item_id="u1"))
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
        dispatcher.on(
            "conversation.item.retrieved",
            lambda ev: handle_conversation_item_retrieved(ev, client, state, summarizer, policy),
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

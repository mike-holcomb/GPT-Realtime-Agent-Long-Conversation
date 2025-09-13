import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.state.conversation import ConversationState, Turn


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

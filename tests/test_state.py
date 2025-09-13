import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.state.conversation import ConversationState, Turn
from realtime_voicebot.state.memory import MemoryStore


def test_append_adds_turn_to_history():
    state = ConversationState()
    turn = Turn(role="user", item_id="1", text="hi")
    state.append(turn)
    assert state.history == [turn]


def test_should_summarize_when_threshold_reached_and_history_long_enough():
    state = ConversationState(latest_tokens=120)
    for i in range(6):
        state.append(Turn(role="user", item_id=str(i)))
    assert state.should_summarize(threshold_tokens=100, keep_last_turns=5)


def test_should_not_summarize_if_conditions_not_met():
    state = ConversationState(latest_tokens=50)
    for i in range(6):
        state.append(Turn(role="user", item_id=str(i)))
    assert not state.should_summarize(threshold_tokens=100, keep_last_turns=5)

    state = ConversationState(latest_tokens=150)
    for i in range(5):
        state.append(Turn(role="user", item_id=str(i)))
    assert not state.should_summarize(threshold_tokens=100, keep_last_turns=5)


def test_should_not_summarize_while_summarising():
    state = ConversationState(latest_tokens=150, summarising=True)
    for i in range(6):
        state.append(Turn(role="user", item_id=str(i)))
    assert not state.should_summarize(threshold_tokens=100, keep_last_turns=5)


def test_memory_store_set_and_get():
    memory = MemoryStore()
    memory.set("color", "blue")
    assert memory.get("color") == "blue"
    assert memory.get("missing") is None

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.state.conversation import (
    ConversationState,
    SummaryPolicy,
    Turn,
)
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


def test_summary_policy_language_detection_and_trigger():
    policy = SummaryPolicy(threshold_tokens=100, keep_last_turns=2, language_policy="auto")
    state = ConversationState(latest_tokens=150)
    state.append(Turn(role="user", item_id="u1", text="hola"))
    state.append(Turn(role="assistant", item_id="a1", text="hola"))
    state.append(Turn(role="user", item_id="u2", text="gracias"))
    assert policy.should_summarize(state)
    assert policy.determine_language(state.history) == "es"

    policy_en = SummaryPolicy(threshold_tokens=100, keep_last_turns=2, language_policy="en")
    assert policy_en.determine_language(state.history) == "en"


def test_record_usage_retains_peak_tokens_until_summary():
    state = ConversationState()
    for i in range(6):
        state.append(Turn(role="user", item_id=str(i), text=f"t{i}"))

    state.record_usage(120)
    state.record_usage(5)

    assert state.latest_tokens == 5
    assert state.pending_summary_tokens == 120
    assert state.should_summarize(threshold_tokens=100, keep_last_turns=5)

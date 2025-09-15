import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.redaction import Redactor
from realtime_voicebot.state.conversation import ConversationState, Turn


def test_redaction_applies_to_state_and_logs(caplog):
    redactor = Redactor(enabled=True)
    state = ConversationState(redact=redactor.redact)
    with caplog.at_level(logging.DEBUG):
        state.append(
            Turn(
                role="user",
                item_id="1",
                text="contact me at a@example.com or 123-456-7890",
            )
        )
    stored = state.history[0].text
    assert "a@example.com" not in stored
    assert "123-456-7890" not in stored
    assert "[REDACTED]" in stored
    assert "a@example.com" not in caplog.text
    assert "123-456-7890" not in caplog.text
    assert caplog.records

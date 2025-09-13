from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["user", "assistant", "system"]


@dataclass
class Turn:
    role: Role
    item_id: str
    text: str | None = None


@dataclass
class ConversationState:
    history: list[Turn] = field(default_factory=list)
    latest_tokens: int = 0
    waiting: dict[str, object] = field(default_factory=dict)
    summarising: bool = False
    summary_count: int = 0

    def append(self, turn: Turn) -> None:
        self.history.append(turn)

    def should_summarize(self, threshold_tokens: int, keep_last_turns: int) -> bool:
        return (
            self.latest_tokens >= threshold_tokens
            and len(self.history) > keep_last_turns
            and not self.summarising
        )

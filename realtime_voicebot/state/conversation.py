from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..summarization.base import Summarizer

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

    async def summarize_and_prune(
        self,
        summarizer: Summarizer,
        keep_last_turns: int,
        language: str | None = None,
    ) -> None:
        """Summarize conversation and keep only the last ``keep_last_turns``.

        The produced summary is inserted as a ``system`` turn at the beginning
        of the history. ``summary_count`` is incremented each time this method is
        called.
        """
        self.summarising = True
        try:
            summary = await summarizer.summarize(self.history, language)
        finally:
            self.summarising = False

        self.summary_count += 1
        summary_turn = Turn(role="system", item_id=f"summary-{self.summary_count}", text=summary)
        self.history = [summary_turn] + self.history[-keep_last_turns:]
        self.latest_tokens = 0

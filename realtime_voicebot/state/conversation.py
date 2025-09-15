from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from ..summarization.base import Summarizer
from ..transport.client import RealtimeClient

Role = Literal["user", "assistant", "system"]


@dataclass
class Turn:
    role: Role
    item_id: str
    text: str | None = None


def _detect_language(texts: list[str]) -> str:
    """Very small heuristic language detector.

    This intentionally avoids heavy dependencies. It looks for common Spanish
    or French words in the recent turns and falls back to English.
    """
    sample = " ".join(t.lower() for t in texts)
    if re.search(r"\b(hola|gracias|por favor|adios)\b", sample):
        return "es"
    if re.search(r"\b(bonjour|merci|s'il|au revoir)\b", sample):
        return "fr"
    return "en"


@dataclass
class SummaryPolicy:
    threshold_tokens: int
    keep_last_turns: int
    language_policy: Literal["auto", "en", "force"] = "auto"

    def should_summarize(self, state: ConversationState) -> bool:
        return state.should_summarize(self.threshold_tokens, self.keep_last_turns)

    def determine_language(self, turns: list[Turn]) -> str | None:
        if self.language_policy == "en":
            return "en"
        if self.language_policy in {"auto", "force"}:
            texts = [t.text or "" for t in turns if t.text]
            return _detect_language(texts) if texts else "en"
        return None


@dataclass
class ConversationState:
    history: list[Turn] = field(default_factory=list)
    latest_tokens: int = 0
    pending_summary_tokens: int = 0
    waiting: dict[str, object] = field(default_factory=dict)
    summarising: bool = False
    summary_count: int = 0
    redact: Callable[[str], str] | None = None

    def record_usage(self, total_tokens: int | None) -> None:
        """Record the usage from a response and retain the peak token window."""

        tokens = int(total_tokens or 0)
        self.latest_tokens = tokens
        if tokens > self.pending_summary_tokens:
            self.pending_summary_tokens = tokens

    def append(self, turn: Turn) -> None:
        text = turn.text
        if text and self.redact:
            text = self.redact(text)
        new_turn = Turn(role=turn.role, item_id=turn.item_id, text=text)
        logging.getLogger(__name__).debug(
            "append_turn", extra={"role": new_turn.role, "text": text}
        )
        self.history.append(new_turn)

    def should_summarize(self, threshold_tokens: int, keep_last_turns: int) -> bool:
        effective_tokens = max(self.latest_tokens, self.pending_summary_tokens)
        return (
            effective_tokens >= threshold_tokens
            and len(self.history) > keep_last_turns
            and not self.summarising
        )

    async def summarize_and_prune(
        self,
        summarizer: Summarizer,
        keep_last_turns: int,
        language: str | None = None,
        client: RealtimeClient | None = None,
    ) -> None:
        """Summarize conversation and keep only the last ``keep_last_turns``.

        The produced summary is inserted as a ``system`` turn at the beginning
        of the history. ``summary_count`` is incremented each time this method is
        called.
        """

        # Defer summarization/pruning if any of the turns that would be pruned
        # are still missing transcripts. This avoids deleting server-side items
        # that have not yet been backfilled by conversation.item.retrieved.
        def _has_pending(turns: list[Turn]) -> bool:
            return any(
                t.role != "system" and (t.text is None or not str(t.text).strip()) for t in turns
            )

        old_turns = self.history[:-keep_last_turns]
        if _has_pending(old_turns):
            # Simply skip summarization for now; a later event (e.g. retrieved
            # transcripts or another response.done) can re-trigger it.
            return

        self.summarising = True
        try:
            summary = await summarizer.summarize(self.history, language)
        finally:
            self.summarising = False

        # Re-check after summarization in case new placeholder turns arrived.
        pruned_turns = self.history[:-keep_last_turns]
        if _has_pending(pruned_turns):
            return

        recent = self.history[-keep_last_turns:]
        self.summary_count += 1
        summary_id = f"summary-{self.summary_count}"
        summary_turn = Turn(role="system", item_id=summary_id, text=summary)
        self.history = [summary_turn] + recent
        self.latest_tokens = 0
        self.pending_summary_tokens = 0

        if client:
            await client.send_json(
                {
                    "type": "conversation.item.create",
                    "previous_item_id": "root",
                    "item": {
                        "id": summary_id,
                        "type": "message",
                        "role": "system",
                        "content": [{"type": "input_text", "text": summary}],
                    },
                }
            )
            for turn in pruned_turns:
                await client.send_json(
                    {"type": "conversation.item.delete", "item_id": turn.item_id}
                )

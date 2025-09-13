from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from ..config import get_settings
from ..metrics import Timer
from ..state.conversation import Turn
from .base import Summarizer


class OpenAISummarizer(Summarizer):
    """OpenAI-backed summarizer (scaffold).

    This is a stub that mirrors the async interface; it does not call the
    network in this initial scaffold to keep the project runnable without
    additional dependencies.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.log = logging.getLogger(__name__)

    async def summarize(self, turns: list[Turn], language: str | None = None) -> str:
        del language  # unused in stub
        timer = Timer()
        timer.start()
        self.log.info(
            "summarization_start",
            extra={
                "event_type": "summarization_start",
                "turn_id": None,
                "response_id": None,
                "latency_ms": None,
                "tokens_total": None,
                "dropped_frames": None,
            },
        )
        recent: Iterable[str] = (t.text or "" for t in turns[-3:])
        await asyncio.sleep(0)
        joined = " | ".join(s for s in recent if s)
        timer.stop()
        self.log.info(
            "summarization_end",
            extra={
                "event_type": "summarization_end",
                "turn_id": None,
                "response_id": None,
                "latency_ms": timer.last_ms,
                "tokens_total": None,
                "dropped_frames": None,
            },
        )
        return ("Summary:") + (" " + joined if joined else " (no content)")

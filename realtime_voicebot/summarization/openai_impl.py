from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from ..metrics import Timer
from ..state.conversation import Turn
from .base import Summarizer


class OpenAISummarizer(Summarizer):
    """OpenAI-backed summarizer (stub).

    The implementation avoids a real network call to keep tests hermetic. It
    still exposes the async interface so a real client can be wired in later
    without changing callers.
    """

    def __init__(self) -> None:
        # ``config`` depends on pydantic which may be missing in lightweight
        # test environments. Import lazily and fall back to defaults.
        try:  # pragma: no cover - configuration loading is trivial
            from ..config import get_settings

            self.settings = get_settings()
        except Exception:  # pragma: no cover - fallback for missing deps
            self.settings = type("_S", (), {"summary_model": "gpt-4o-mini"})()
        self.log = logging.getLogger(__name__)

    async def summarize(self, turns: list[Turn], language: str | None = None) -> str:
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
        joined = " ".join(s for s in recent if s)
        synopsis = joined if joined else "no content"
        summary = f"Synopsis: {synopsis}. Facts: none."
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
        return summary

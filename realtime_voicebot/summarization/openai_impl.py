from __future__ import annotations

import asyncio
from typing import Iterable

from ..config import get_settings
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

    async def summarize(self, turns: list[Turn], language: str | None = None) -> str:
        del language  # unused in stub
        # Produce a trivial synthetic summary for now.
        recent: Iterable[str] = (t.text or "" for t in turns[-3:])
        await asyncio.sleep(0)
        joined = " | ".join(s for s in recent if s)
        return ("Summary:") + (" " + joined if joined else " (no content)")


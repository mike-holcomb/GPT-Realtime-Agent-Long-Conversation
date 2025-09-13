from __future__ import annotations

from typing import Protocol

from ..state.conversation import Turn


class Summarizer(Protocol):
    async def summarize(self, turns: list[Turn], language: str | None = None) -> str:  # noqa: D401
        """Summarize the given turns into a compact system message."""


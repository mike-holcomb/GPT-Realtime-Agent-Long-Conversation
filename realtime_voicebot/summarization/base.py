from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ..state.conversation import Turn


class Summarizer(Protocol):
    async def summarize(self, turns: list[Turn], language: str | None = None) -> str:  # noqa: D401
        """Summarize the given turns into a compact system message."""

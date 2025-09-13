from __future__ import annotations

from collections.abc import Callable
from typing import Any

Tool = Callable[..., Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, tool: Tool) -> None:
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

"""Tool registry and dispatch helpers."""

from __future__ import annotations

import datetime as _dt
import inspect
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..transport.client import RealtimeClient


@dataclass
class Tool:
    """Description of an executable tool."""

    name: str
    description: str
    parameters: dict
    func: Callable[..., Any]

    async def call(self, **kwargs) -> Any:
        result = self.func(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


class ToolRegistry:
    """Simple in-memory tool registry."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict]:
        """Return tool specs suitable for session advertisement."""
        return [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]


# Sample tools --------------------------------------------------------------


def _clock() -> str:
    return _dt.datetime.utcnow().isoformat()


def _http_get(url: str) -> str:
    with urllib.request.urlopen(url) as resp:  # nosec - used in tests
        return resp.read().decode("utf-8")


clock_tool = Tool(
    name="clock",
    description="Current UTC time",
    parameters={"type": "object", "properties": {}, "required": []},
    func=_clock,
)

http_tool = Tool(
    name="http_get",
    description="Fetch a URL via HTTP GET",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
    func=_http_get,
)


async def handle_tool_call(event: dict, client: RealtimeClient, registry: ToolRegistry) -> None:
    """Dispatch ``tool_call`` events and return results."""

    item = event.get("item", {})
    if item.get("type") != "tool_call":
        return
    name = item.get("name")
    call_id = item.get("call_id")
    args = item.get("arguments", {})
    response_id = event.get("response_id")
    tool = registry.get(name or "")
    if not tool:
        return
    result = await tool.call(**args)
    await client.send_json(
        {
            "type": "response.output_item.create",
            "response_id": response_id,
            "item": {
                "type": "tool_result",
                "call_id": call_id,
                "content": [{"type": "output_text", "text": str(result)}],
            },
        }
    )

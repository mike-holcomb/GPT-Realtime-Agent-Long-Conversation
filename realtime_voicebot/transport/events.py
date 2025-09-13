from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass
class Event:
    type: str
    payload: dict


EventHandler = Callable[[dict], Awaitable[None]]


def get_type(ev: dict) -> str:
    return ev.get("type", "")


class EventDispatcher:
    """Minimal async event dispatcher.

    Handlers can be registered for event types and will be awaited when a
    matching event is dispatched. Unknown event types are ignored.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, EventHandler] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type] = handler

    async def dispatch(self, event: dict) -> None:
        etype = get_type(event)
        handler = self._handlers.get(etype)
        if handler:
            await handler(event)

from __future__ import annotations

from collections.abc import Awaitable, Callable

Handler = Callable[[dict], Awaitable[None]]


class Dispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type] = handler

    async def dispatch(self, event: dict) -> None:
        etype = event.get("type", "")
        handler = self._handlers.get(etype)
        if handler:
            await handler(event)

from __future__ import annotations

from ..transport.events import EventHandler, get_type

Handler = EventHandler


class Dispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type] = handler

    async def dispatch(self, event: dict) -> None:
        etype = get_type(event)
        handler = self._handlers.get(etype)
        if handler:
            await handler(event)

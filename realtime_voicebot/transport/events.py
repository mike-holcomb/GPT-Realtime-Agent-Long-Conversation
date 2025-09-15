from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass
class Event:
    type: str
    payload: dict


EventT = TypeVar("EventT", bound=dict)


EventHandler = Callable[[EventT], Awaitable[None]]


def get_type(ev: dict) -> str:
    return ev.get("type", "")


class Dispatcher(Generic[EventT]):
    """Minimal async event dispatcher.

    Handlers can be registered for event types and will be awaited when a
    matching event is dispatched. Unknown event types are ignored.

    The :meth:`on` method can be used either as a decorator::

        dispatcher = Dispatcher()


        @dispatcher.on("event.type")
        async def handler(event): ...

    or called directly::

        dispatcher.on("event.type", handler)

    """

    def __init__(self) -> None:
        self._handlers: dict[str, EventHandler[EventT]] = {}

    def on(
        self, event_type: str, handler: EventHandler[EventT] | None = None
    ) -> EventHandler[EventT] | Callable[[EventHandler[EventT]], EventHandler[EventT]]:
        """Register ``handler`` for ``event_type``.

        If ``handler`` is ``None`` this functions as a decorator factory.
        """

        if handler is not None:
            self._handlers[event_type] = handler
            return handler

        def decorator(func: EventHandler[EventT]) -> EventHandler[EventT]:
            self._handlers[event_type] = func
            return func

        return decorator

    # Backwards compatible alias
    register = on

    async def dispatch(self, event: EventT) -> None:
        handler = self._handlers.get(get_type(event))
        if handler:
            await handler(event)

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Awaitable, Any
from .types import Event, EventType

logger = logging.getLogger(__name__)


Handler = Callable[[Event], Awaitable[Any]]


class EventBus:
    def __init__(self, max_history: int = 1000):
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._global_handlers: list[Handler] = []
        self._event_history: list[Event] = []
        self._max_history = max_history

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)
        logger.debug(f"Subscribed handler to {event_type.value}")

    def subscribe_all(self, handler: Handler) -> None:
        self._global_handlers.append(handler)
        logger.debug("Subscribed handler to all events")

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
            logger.debug(f"Unsubscribed handler from {event_type.value}")

    def unsubscribe_all(self, handler: Handler) -> None:
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        logger.info(f"Event published: {event.event_type.value} | session={event.session_id}")

        tasks = []
        for handler in self._handlers[event.event_type]:
            tasks.append(asyncio.create_task(handler(event)))
        
        for handler in self._global_handlers:
            tasks.append(asyncio.create_task(handler(event)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_history(
        self,
        event_type: EventType | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if session_id:
            events = [e for e in events if e.session_id == session_id]
        
        events = events[-limit:]
        return [e.to_dict() for e in events]

    def clear_history(self) -> None:
        self._event_history.clear()
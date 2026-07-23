from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.events.base import DomainEvent


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[DomainEvent], None]]] = defaultdict(
            list
        )

    def subscribe(
        self, event_type: str, handler: Callable[[DomainEvent], None]
    ) -> None:
        self._subscribers[event_type].append(handler)

    def publish(
        self, event_name: str, payload: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        if payload is None:
            payload = kwargs
        event = DomainEvent(event_type=event_name, payload=payload)
        for handler in self._subscribers.get(event_name, []):
            handler(event)

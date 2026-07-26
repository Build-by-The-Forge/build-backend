from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DomainEvent:
    event_type: str
    payload: dict[str, Any] | None = None

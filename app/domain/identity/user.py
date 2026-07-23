from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(slots=True)
class User:
    id: str
    email: str
    password_hash: str
    is_active: bool = True
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.id == "":
            self.id = str(uuid4())
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

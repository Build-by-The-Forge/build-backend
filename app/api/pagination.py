"""The contract's list parameters and meta.pagination, shared by every list route."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, TypeVar

from fastapi import Depends, Query

T = TypeVar("T")

# Far past any real list, and well inside what the database can compare against.
MAX_OFFSET = 2_147_483_647


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int
    offset: int

    def meta(self, total: int) -> dict[str, int]:
        return {"total": total, "limit": self.limit, "offset": self.offset}

    def slice(self, items: Sequence[T]) -> list[T]:
        """For a bounded list already in memory, in its final order."""
        return list(items[self.offset : self.offset + self.limit])


def _page_request(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> PageRequest:
    return PageRequest(limit=limit, offset=offset)


Page = Annotated[PageRequest, Depends(_page_request)]

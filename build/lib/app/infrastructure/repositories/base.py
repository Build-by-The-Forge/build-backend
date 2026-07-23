from typing import Protocol, TypeVar

T = TypeVar("T")


class Repository(Protocol[T]):
    pass

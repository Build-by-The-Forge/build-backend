from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)


class Repository(Protocol[T_co]):
    pass

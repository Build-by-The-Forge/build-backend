from typing import Protocol


class CourseRepository(Protocol):
    async def save(self, course: object) -> object:
        raise NotImplementedError

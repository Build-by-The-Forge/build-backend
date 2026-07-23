from abc import ABC, abstractmethod


class AIClient(ABC):
    @abstractmethod
    async def ping(self) -> bool:
        raise NotImplementedError


class ChatClient(AIClient):
    async def ping(self) -> bool:
        return True


class OCRClient(AIClient):
    async def ping(self) -> bool:
        return True

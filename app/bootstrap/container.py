from app.events.event_bus import EventBus


class Container:
    def __init__(self) -> None:
        self._services: dict[type[object], object] = {}

    def register(self, service_type: type[object], implementation: object) -> None:
        self._services[service_type] = implementation

    def get(self, service_type: type[object]) -> object:
        if service_type not in self._services:
            raise KeyError(f"Service {service_type.__name__} is not registered")
        return self._services[service_type]


def build_container() -> Container:
    container = Container()
    container.register(EventBus, EventBus())
    return container

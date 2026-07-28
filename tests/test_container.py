from app.application.identity.user_service import UserService
from app.bootstrap.container import build_container


def test_build_container_uses_sqlalchemy_uow_for_identity() -> None:
    container = build_container()
    service = container.get(UserService)

    assert isinstance(service, UserService)
    assert service.repository is None
    assert service.uow_factory is not None

from collections.abc import Generator

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col

from sqlmodelservice import MultipleResultsFound, NotFound

from .database.player import DbPlayer, PlayerCreate, PlayerService, PlayerUpdate


@pytest.fixture(scope="function")
def service(session: Session) -> PlayerService:
    return PlayerService(session)


@pytest.fixture(scope="module")
def query_session(engine: Engine) -> Generator[Session, None, None]:
    """Secondary session only for querying data."""
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="module")
def query_service(query_session: Session) -> PlayerService:
    """Secondary service only for querying data."""
    return PlayerService(query_session)


class TestAddToSession:
    def test_all(self, service: PlayerService) -> None:
        service.add_to_session(
            (PlayerCreate(name="First"), PlayerCreate(name="Second")),
            operation="create",
            commit=True,
        )

        result = service.all(col(DbPlayer.name) == "First")
        assert len(result) == 1
        assert result[0].name == "First"

        result = service.all(order_by=(col(DbPlayer.name).desc(),))
        assert len(result) == 2
        assert result[0].name == "Second"
        assert result[1].name == "First"

        for player in service.all():
            service.delete_by_pk(player.id)  # type: ignore[arg-type]

        assert len(service.get_all()) == 0

    def test_create(self, service: PlayerService, query_service: PlayerService) -> None:
        service.add_to_session(
            (PlayerCreate(name="First"), PlayerCreate(name="Second")),
            operation="create",
            commit=False,
        )

        assert len(query_service.get_all()) == 0

        service.add_to_session((), commit=True, operation="update")
        players = query_service.get_all()
        assert len(players) == 2
        assert len(service.get_all()) == 2

        for player in players:
            service.delete_by_pk(player.id)  # type: ignore[arg-type]

        assert len(query_service.get_all()) == 0

    def test_update(self, service: PlayerService, query_service: PlayerService) -> None:
        service.add_to_session(
            (PlayerCreate(name="First"), PlayerCreate(name="Second")),
            operation="create",
            commit=True,
        )

        players = query_service.exec(query_service.select().order_by(DbPlayer.name)).all()
        assert players[0].name == "First"
        assert players[1].name == "Second"

        service.add_to_session(
            (
                (p, PlayerUpdate(name=f"{p.name} - {i}"))
                for i, p in enumerate(service.exec(service.select().order_by(DbPlayer.name)).all(), 1)
            ),
            operation="update",
            commit=False,
        )

        service.add_to_session((), commit=True, operation="create")

        query_service._session.expire_all()  # We need to make sure the data is fresh.
        players = query_service.exec(query_service.select().order_by(DbPlayer.name)).all()
        assert players[0].name == "First - 1"
        assert players[1].name == "Second - 2"

        # Simply comparing two lists would raise this exception (possible SQLModel bug):
        # AttributeError: 'DbPlayer' object has no attribute '__pydantic_private__'
        for first, second in zip(players, service.exec(service.select().order_by(DbPlayer.name)).all(), strict=True):
            assert first.id == second.id
            assert first.name == second.name

        for player in players:
            service.delete_by_pk(player.id)  # type: ignore[arg-type]

        assert len(query_service.get_all()) == 0

    def test_one(self, service: PlayerService) -> None:
        service.add_to_session(
            (PlayerCreate(name="First"), PlayerCreate(name="Second")),
            operation="create",
            commit=True,
        )

        result = service.one(col(DbPlayer.name) == "First")
        assert result.name == "First"

        with pytest.raises(NotFound):
            service.one(col(DbPlayer.name) == "Does Not Exist")

        with pytest.raises(MultipleResultsFound):
            service.one(True)

        for player in service.all():
            service.delete_by_pk(player.id)  # type: ignore[arg-type]

        assert len(service.get_all()) == 0

    def test_one_or_none(self, service: PlayerService) -> None:
        service.add_to_session(
            (PlayerCreate(name="First"), PlayerCreate(name="Second")),
            operation="create",
            commit=True,
        )

        result = service.one_or_none(col(DbPlayer.name) == "First")
        assert result is not None
        assert result.name == "First"

        assert service.one_or_none(col(DbPlayer.name) == "Does Not Exist") is None

        with pytest.raises(MultipleResultsFound):
            service.one_or_none(True)

        for player in service.all():
            service.delete_by_pk(player.id)  # type: ignore[arg-type]

        assert len(service.get_all()) == 0

from collections.abc import Generator

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]


def _init_db(engine: Engine) -> None:
    # Database model registration.
    from .player import DbPlayer  # noqa: F401

    # Table creation.
    SQLModel.metadata.create_all(engine)


def _ping_database(engine: Engine) -> bool:
    try:
        engine.connect()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    with PostgresContainer("postgres:18") as pg:
        connection_string = pg.get_connection_url(driver="psycopg")
        engine = create_engine(connection_string)
        _init_db(engine)
        yield engine


@pytest.fixture(scope="function")
def session(*, engine: Engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

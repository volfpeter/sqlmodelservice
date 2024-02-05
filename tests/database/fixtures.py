from collections.abc import Generator

import pytest
from pytest_docker.plugin import Services as DockerServices
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(scope="session")
def db_connect_string(*, docker_ip: str, docker_services: DockerServices) -> str:
    return f"postgresql://postgres:postgres@{docker_ip}:{docker_services.port_for('db', 5432)}"


@pytest.fixture(scope="session")
def engine(*, db_connect_string: str) -> Engine:
    return create_engine(db_connect_string)


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
def database(*, engine: Engine, docker_services: DockerServices) -> Engine:
    docker_services.wait_until_responsive(
        timeout=30,
        pause=0.5,
        check=lambda: _ping_database(engine),
    )

    _init_db(engine)

    return engine


@pytest.fixture(scope="function")
def session(*, database: Engine) -> Generator[Session, None, None]:
    with Session(database) as session:
        yield session

# FastAPI example

## Prerequisites

To follow and try this example, you will need:

- Python 3.10+;
- `fastapi` and `uvicorn` (`pip install fastapi uvicorn`);
- and of course this library.

The example will use (and automatically create) an on-disk `sqlite` database for you to work with. There is no need to set up anything in this regard.

## Project layout

Create the _root directory_ of your project, for example `player-app`.

Inside the _root directory_, create the root Python _package_ for the application -- `player_app` -- and add the following empty files to it:

- `__init__.py`
- `api.py`
- `database.py`
- `main.py`
- `model.py`
- `service.py`

In the end, your directory structure should look like this:

<ul>
    <li><code>player-app</code> (root directory)</li>
    <ul>
        <li><code>player_app</code> (root package)</li>
        <ul>
            <li><code>__init__.py</code></li>
            <li><code>api.py</code></li>
            <li><code>database.py</code></li>
            <li><code>main.py</code></li>
            <li><code>model.py</code></li>
            <li><code>service.py</code></li>
        </ul>
    </ul>
</ul>

## Database access (`database.py`)

We will start by creating some utilities for communicating with the database:

```python
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """FastAPI dependency that returns the database engine for the application."""
    return create_engine("sqlite:///example.db")


DependsEngine = Annotated[Engine, Depends(get_engine)]


def get_session(engine: DependsEngine) -> Session:
    """FastAPI dependency that returns the database session for the application."""
    with Session(engine) as session:
        yield session


DependsSession = Annotated[Session, Depends(get_session)]


def create_tables(engine: Engine) -> None:
    """Creates all tables known by SQLModel in the database if they don't exist."""
    SQLModel.metadata.create_all(engine)
```

## Model definitions (`model.py`)

We can now define all the models that are required for the application:

```python
from sqlmodel import Field, SQLModel


class PlayerBase(SQLModel):
    """Base player model with common properties."""

    name: str


class DbPlayer(PlayerBase, table=True):
    """Player database table model."""

    __tablename__ = "players"

    id: int | None = Field(default=None, primary_key=True)


class PlayerCreate(PlayerBase):
    """
    Player creation model.

    It doesn't have the `id` property as we want the database to automatically assign it.
    """

    ...


class PlayerRead(PlayerBase):
    """Player read model with a mandatory `id`."""

    id: int


class PlayerUpdate(SQLModel):
    """Player update model with optional properties for everything that could be updated."""

    name: str | None = None
```

## Services (`service.py`)

With the player model in place, we can create the corresponding service by simply subclassing `sqlmodelservice.Service`:

```python
from sqlmodel import Session
from sqlmodelservice import Service as Service

from .model import DbPlayer, PlayerCreate, PlayerUpdate


class PlayerService(Service[DbPlayer, PlayerCreate, PlayerUpdate, int]):
    """
    Player service.

    Generics:

    - Table model: `DbPlayer`.
    - Data creation model: `PlayerCreate`.
    - Update model: `PlayerUpdate`.
    - Primary key: `int`.
    """

    def __init__(self, session: Session) -> None:
        """
        Initialization.

        Arguments:
            session: The database session the service can use.
        """
        # Always initialize the service with the DbPlayer table model.
        super().__init__(session, model=DbPlayer)
```

## Routing (`api.py`)

With the data model and the service ready, we can move on creating the player API:

```python
from collections.abc import Iterable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodelservice import CommitFailed, NotFound

from .database import DependsSession
from .model import DbPlayer, PlayerCreate, PlayerRead, PlayerUpdate
from .service import PlayerService


player_api = APIRouter()


def get_service(session: DependsSession) -> PlayerService:
    """FastAPI dependency that returns a `PlayerService` instance."""
    return PlayerService(session)


DependsService = Annotated[PlayerService, Depends(get_service)]


@player_api.get("/", response_model=list[PlayerRead])
def get_all(service: DependsService, name: str | None = None) -> Iterable[DbPlayer]:
    """Get all route with optional name filtering to showcase query building using service.select()."""
    if name is None:
        return service.get_all()

    return service.exec(service.select().where(DbPlayer.name == name)).all()


@player_api.post("/", response_model=PlayerRead)
def create(player: PlayerCreate, service: DependsService) -> DbPlayer:
    """Player creation route."""
    return service.create(player)


@player_api.get("/{id}", response_model=PlayerRead)
def get_by_id(id: int, service: DependsService) -> DbPlayer:
    """Route for fetching a specific player from the database by its primary key."""
    player = service.get_by_pk(id)
    if player is None:
        raise HTTPException(404)

    return player


@player_api.put("/{id}", response_model=PlayerRead)
def update(id: int, data: PlayerUpdate, service: DependsService) -> DbPlayer:
    """Player update route."""
    try:
        return service.update(id, data)
    except NotFound as e:
        raise HTTPException(404) from e


@player_api.delete("/{id}", response_model=None, status_code=204)
def delete(id: int, service: DependsService) -> None:
    """Delete route."""
    try:
        service.delete_by_pk(id)
    except NotFound as e:
        raise HTTPException(404) from e
    except CommitFailed as e:
        raise HTTPException(400) from e
```

## The application (`main.py`)

We are now ready to create and configure the FastAPI application instance:

```python
from fastapi import FastAPI

from .api import player_api
from .database import create_tables, get_engine

# Create all known database tables so the app has something to work with.
create_tables(get_engine())

# Create the FastAPI application.
app = FastAPI()

# Add the player API router to the application under the /player prefix.
app.include_router(player_api, prefix="/player")
```

## Starting the application

With everything ready, we can start the application by executing `uvicorn player_app.main:app --reload` in the root directory and go to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to try the created REST API.

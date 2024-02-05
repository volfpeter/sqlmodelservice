from collections.abc import Sequence

from sqlmodel import Field, Session, SQLModel

from sqlmodelservice import Service


class PlayerBase(SQLModel):
    name: str


class DbPlayer(PlayerBase, table=True):
    __tablename__ = "players"

    id: int | None = Field(default=None, primary_key=True)


class PlayerCreate(PlayerBase):
    ...


class PlayerRead(PlayerBase):
    id: int


class PlayerUpdate(SQLModel):
    name: str | None = None


class PlayerService(Service[DbPlayer, PlayerCreate, PlayerUpdate, int]):
    __slots__ = ()

    def __init__(self, session: Session) -> None:
        super().__init__(session, model=DbPlayer)

    def get_by_name(self, name: str) -> Sequence[DbPlayer]:
        return self.exec(self.select().where(DbPlayer.name == name)).all()

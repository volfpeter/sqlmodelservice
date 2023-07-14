from collections.abc import Mapping
from typing import Any, Generic, Type, TypeVar, overload

from sqlmodel import Session, SQLModel, select
from sqlmodel.engine.result import Result, ScalarResult
from sqlmodel.sql.expression import SelectOfScalar

AtomicPrimaryKey = int | str
PrimaryKey = AtomicPrimaryKey | tuple[AtomicPrimaryKey, ...] | list[AtomicPrimaryKey] | Mapping[str, AtomicPrimaryKey]

T = TypeVar("T")
TM_1 = TypeVar("TM_1", bound=SQLModel)
TM_2 = TypeVar("TM_2", bound=SQLModel)
TM_3 = TypeVar("TM_3", bound=SQLModel)
TM_4 = TypeVar("TM_4", bound=SQLModel)

TModel = TypeVar("TModel", bound=SQLModel)
TCreate = TypeVar("TCreate", bound=SQLModel)
TUpdate = TypeVar("TUpdate", bound=SQLModel)
TPrimaryKey = TypeVar("TPrimaryKey", bound=PrimaryKey)


class ServiceException(Exception):
    """Base exception raise by services."""

    ...


class CommitFailed(ServiceException):
    """Raise by the service when a commit fails."""

    ...


class NotFound(ServiceException):
    """Raise by services when an item is not found."""

    ...


class Service(Generic[TModel, TCreate, TUpdate, TPrimaryKey]):
    """
    Base service implementation.

    It's a wrapper `sqlmodel`'s `Session`. When using the service, use the practices
    that are recommended in `sqlmodel`'s [documentation](https://sqlmodel.tiangolo.com/).
    For example don't reuse the same service instance across multiple requests.

    Generic types:
    - `TModel`: The SQLModel class on which `table=True` is set.
    - `TCreate`: The instance creation model. It may be the same as `TModel`, although it is
      usually different. The `TCreate` -> `TModel` conversion happens in `_prepare_for_create()`,
      which you may override.
    - `TUpdate`: The instance update model. It may be the same as `TModel`, although it is
      usually different. The `TUpdate` -> `dict` conversion for update operation happens in
      `_prepare_for_update()`, which you may override.
    - `TPrimaryKey`: The type definition of the primary key of `TModel`. Often simply `int` or
      `str`, or `tuple` for complex keys.
    """

    __slots__ = (
        "_model",
        "_session",
    )

    def __init__(self, session: Session, *, model: Type[TModel]) -> None:
        """
        Initialization.

        Arguments:
            session: The session instance the service will use. When the service is created,
                it becomes the sole owner of the session, it should only be used through the
                service from then on.
            model: The database *table* model.
        """
        self._model = model
        self._session = session

    def create(self, data: TCreate) -> TModel:
        """
        Creates a new database entry from the given data.

        Arguments:
            data: Creation data.

        Raises:
            CommitFailed: If the service fails to commit the operation.
        """
        session = self._session
        db_item = self._prepare_for_create(data)
        session.add(db_item)
        self._safe_commit("Commit failed.")
        session.refresh(db_item)
        return db_item

    def delete_by_pk(self, pk: TPrimaryKey) -> None:
        """
        Deletes the item with the given primary key from the database.

        Arguments:
            pk: The primary key.

        Raises:
            CommitFailed: If the service fails to commit the operation.
            NotFound: If the document with the given primary key does not exist.
        """
        session = self._session

        item = self.get_by_pk(pk)
        if item is None:
            raise NotFound(self._format_primary_key(pk))

        session.delete(item)
        self._safe_commit("Failed to delete item.")

    def exec(self, statement: SelectOfScalar[T]) -> Result[T] | ScalarResult[T]:
        """
        Executes the given statement.
        """
        return self._session.exec(statement)

    def get_all(self) -> list[TModel]:
        """
        Returns all items from the database.
        """
        return self._session.exec(select(self._model)).all()

    def get_by_pk(self, pk: PrimaryKey) -> TModel | None:
        """
        Returns the item with the given primary key if it exists.

        Arguments:
            pk: The primary key.
        """
        return self._session.get(self._model, pk)

    def refresh(self, instance: TModel) -> None:
        """
        Refreshes the given instance from the database.
        """
        self._session.refresh(instance)

    @overload
    def select(self) -> SelectOfScalar[TModel]:
        ...

    @overload
    def select(self, joined_1: Type[TM_1], /) -> SelectOfScalar[tuple[TModel, TM_1]]:
        ...

    @overload
    def select(self, joined_1: Type[TM_1], joined_2: Type[TM_2], /) -> SelectOfScalar[tuple[TModel, TM_1, TM_2]]:
        ...

    @overload
    def select(
        self, joined_1: Type[TM_1], joined_2: Type[TM_2], joined_3: Type[TM_3], /
    ) -> SelectOfScalar[tuple[TModel, TM_1, TM_2, TM_3]]:
        ...

    @overload
    def select(
        self,
        joined_1: Type[TM_1],
        joined_2: Type[TM_2],
        joined_3: Type[TM_3],
        joined_4: Type[TM_4],
        /,
    ) -> SelectOfScalar[tuple[TModel, TM_1, TM_2, TM_3, TM_4]]:
        ...

    def select(self, *joined: SQLModel) -> SelectOfScalar[SQLModel]:  # type: ignore[misc]
        """
        Creates a select statement on the service's table.

        Positional arguments (SQLModel table definitions) will be included in the select statement.
        You must specify the join condition for each included positional argument though.

        If `joined` is not empty, then a tuple will be returned with `len(joined) + 1` values
        in it. The first value will be an instance of `TModel`, the rest of the values will
        correspond to the positional arguments that were passed to the method.

        Example:

        ```python
        class A(SQLModel, table=True):
            id: int | None = Field(primary_key=True)
            a: str

        class B(SQLModel, table=True):
            id: int | None = Field(primary_key=True)
            b: str

        class AService(Service[A, A, A, int]):
            def __init__(self, session: Session) -> None:
                super().__init__(session, model=A)

        with Session(engine) as session:
            a_svc = AService(session)
            q = a_svc.select(B).where(A.a == B.b)
            result = svc.exec(q).one()
            print(result[0])  # A instance
            print(result[1])  # B instance
        ```
        """
        return select(self._model, *joined)

    def update(self, pk: TPrimaryKey, data: TUpdate) -> TModel:
        """
        Updates the item with the given primary key.

        Arguments:
            pk: The primary key.
            data: Update data.

        Raises:
            CommitFailed: If the service fails to commit the operation.
            NotFound: If the document with the given primary key does not exist.
        """
        session = self._session

        item = self.get_by_pk(pk)
        if item is None:
            raise NotFound(self._format_primary_key(pk))

        changes = self._prepare_for_update(data)
        for key, value in changes.items():
            setattr(item, key, value)

        session.add(item)
        self._safe_commit(f"Failed to update {self._format_primary_key(pk)}.")

        session.refresh(item)
        return item

    def _format_primary_key(self, pk: TPrimaryKey) -> str:
        """
        Returns the string-formatted version of the primary key.

        Arguments:
            pk: The primary key to format.

        Raises:
            ValueError: If formatting fails.
        """
        if isinstance(pk, (str, int)):
            return str(pk)
        elif isinstance(pk, (tuple, list)):
            return "|".join(str(i) for i in pk)
        elif isinstance(pk, dict):
            return "|".join(f"{k}:{v}" for k, v in pk.items())

        raise ValueError("Unrecognized primary key type.")

    def _prepare_for_create(self, data: TCreate) -> TModel:
        """
        Hook that is called before applying creating a model.

        The methods role is to convert certain attributes of the given model's before creating it.

        Arguments:
            data: The model to be created.
        """
        return self._model.from_orm(data)

    def _prepare_for_update(self, data: TUpdate) -> dict[str, Any]:
        """
        Hook that is called before applying the given update.

        The methods role is to convert the given data into a `dict` of
        attribute name - new value pairs, omitting unchanged values.

        The default implementation is `data.dict(exclude_unset=True)`.

        Arguments:
            data: The update data.
        """
        return data.dict(exclude_unset=True)

    def _safe_commit(self, error_msg: str) -> None:
        """
        Commits the session, making sure it is rolled back in case the commit fails.

        Arguments:
            error_msg: The message for the raised exception.
        """
        session = self._session
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise CommitFailed(error_msg) from e

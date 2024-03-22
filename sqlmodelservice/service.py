from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Generic, Literal, Type, TypeVar, cast, overload

from sqlalchemy import exc as sa_exc
from sqlalchemy.engine.result import ScalarResult, TupleResult
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, SQLModel, select
from sqlmodel.sql.expression import Select, SelectOfScalar

AtomicPrimaryKey = int | str
PrimaryKey = AtomicPrimaryKey | tuple[AtomicPrimaryKey, ...] | list[AtomicPrimaryKey] | Mapping[str, AtomicPrimaryKey]

T = TypeVar("T")
TM_1 = TypeVar("TM_1", bound=SQLModel)
TM_2 = TypeVar("TM_2", bound=SQLModel)
TM_3 = TypeVar("TM_3", bound=SQLModel)
TM_4 = TypeVar("TM_4", bound=SQLModel)
TM_5 = TypeVar("TM_5", bound=SQLModel)
TM_6 = TypeVar("TM_6", bound=SQLModel)

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
    """Raise by the service when an item is not found."""

    ...


class MultipleResultsFound(ServiceException):
    """Raised by the service when multiple results were found but at most one was expected."""

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

    @overload
    def add_to_session(
        self, items: Iterable[TCreate], *, commit: bool = False, operation: Literal["create"]
    ) -> list[TModel]:
        ...

    @overload
    def add_to_session(
        self, items: Iterable[tuple[TModel, TUpdate]], *, commit: bool = False, operation: Literal["update"]
    ) -> list[TModel]:
        ...

    def add_to_session(
        self,
        items: Iterable[TCreate] | Iterable[tuple[TModel, TUpdate]],
        *,
        commit: bool = False,
        operation: Literal["create", "update"],
    ) -> list[TModel]:
        """
        Adds all items to the session using the same flow as `create()` or `update()`,
        depending on the selected `operation`.

        If `commit` is `True`, the method will commit the transaction even if `items` is empty.
        The reason for this is to allow chaining `add_to_session()` calls without special
        attention to when and how the session must be committed at the end.

        Note: even if `commit` is `True`, the method *will not perform a refresh* on the items
        as it has to be done one by one which would be very inefficient with many items.

        Arguments:
            items: The items to add to the session.
            commit: Whether to also commit the changes to the database.
            operation: The desired operation.

        Returns:
            The list of items that were added to the session.

        Raises:
            CommitFailed: If the service fails to commit the operation.
        """
        if operation == "create":
            items = cast(Iterable[TCreate], items)
            db_items = [self._prepare_for_create(item) for item in items]
        elif operation == "update":
            items = cast(Iterable[tuple[TModel, TUpdate]], items)
            db_items = [self._apply_changes_to_item(item, changes) for item, changes in items]
        else:
            raise ServiceException(f"Unsupported operation: {operation}")

        self._session.add_all(db_items)
        if commit:
            self._safe_commit("Commit failed.")

        return db_items

    def all(
        self,
        where: ColumnElement[bool] | bool | None = None,
        *,
        order_by: Sequence[ColumnElement[Any]] | None = None,
    ) -> Sequence[TModel]:
        """
        Returns all items that match the given where clause.

        Arguments:
            where: An optional where clause for the query.
            order_by: An optional sequence of order by clauses.
        """
        stmt = self.select()

        if where is not None:
            stmt = stmt.where(where)

        if order_by:
            stmt = stmt.order_by(*order_by)

        return self.exec(stmt).all()

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

    @overload
    def exec(self, statement: Select[T]) -> TupleResult[T]:
        ...

    @overload
    def exec(self, statement: SelectOfScalar[T]) -> ScalarResult[T]:
        ...

    def exec(self, statement: SelectOfScalar[T] | Select[T]) -> ScalarResult[T] | TupleResult[T]:
        """
        Executes the given statement.
        """
        return self._session.exec(statement)

    def get_all(self) -> Sequence[TModel]:
        """
        Returns all items from the database.

        Deprecated. Use `all()` instead.
        """
        return self._session.exec(select(self._model)).all()

    def get_by_pk(self, pk: PrimaryKey) -> TModel | None:
        """
        Returns the item with the given primary key if it exists.

        Arguments:
            pk: The primary key.
        """
        return self._session.get(self._model, pk)

    def one(
        self,
        where: ColumnElement[bool] | bool,
    ) -> TModel:
        """
        Returns item that matches the given where clause.

        Arguments:
            where: The where clause of the query.

        Raises:
            MultipleResultsFound: If multiple items match the where clause.
            NotFound: If no items match the where clause.
        """
        try:
            return self.exec(self.select().where(where)).one()
        except sa_exc.MultipleResultsFound as e:
            raise MultipleResultsFound("Multiple items matched the where clause.") from e
        except sa_exc.NoResultFound as e:
            raise NotFound("No items matched the where clause") from e

    def one_or_none(
        self,
        where: ColumnElement[bool] | bool,
    ) -> TModel | None:
        """
        Returns item that matches the given where clause, if there is such an item.

        Arguments:
            where: The where clause of the query.

        Raises:
            MultipleResultsFound: If multiple items match the where clause.
        """
        try:
            return self.exec(self.select().where(where)).one_or_none()
        except sa_exc.MultipleResultsFound as e:
            raise MultipleResultsFound("Multiple items matched the where clause.") from e

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

    @overload
    def select(
        self,
        joined_1: Type[TM_1],
        joined_2: Type[TM_2],
        joined_3: Type[TM_3],
        joined_4: Type[TM_4],
        joined_5: Type[TM_5],
        /,
    ) -> SelectOfScalar[tuple[TModel, TM_1, TM_2, TM_3, TM_4, TM_5]]:
        ...

    @overload
    def select(
        self,
        joined_1: Type[TM_1],
        joined_2: Type[TM_2],
        joined_3: Type[TM_3],
        joined_4: Type[TM_4],
        joined_5: Type[TM_5],
        joined_6: Type[TM_6],
        /,
    ) -> SelectOfScalar[tuple[TModel, TM_1, TM_2, TM_3, TM_4, TM_5, TM_6]]:
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

        self._apply_changes_to_item(item, data)
        session.add(item)
        self._safe_commit(f"Failed to update {self._format_primary_key(pk)}.")

        session.refresh(item)
        return item

    def _apply_changes_to_item(self, item: TModel, data: TUpdate) -> TModel:
        """
        Applies the given changes to the given item without committing anything.

        Arguments:
            item: The item to update.
            data: The changes to make to `item`.

        Returns:
            The received item.
        """
        changes = self._prepare_for_update(data)
        for key, value in changes.items():
            setattr(item, key, value)

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
        return self._model.model_validate(data)

    def _prepare_for_update(self, data: TUpdate) -> dict[str, Any]:
        """
        Hook that is called before applying the given update.

        The method's role is to convert the given data into a `dict` of
        attribute name - new value pairs, omitting unchanged values.

        The default implementation is `data.model_dump(exclude_unset=True)`.

        Arguments:
            data: The update data.
        """
        return data.model_dump(exclude_unset=True)

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

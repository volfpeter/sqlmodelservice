from typing import TYPE_CHECKING

from .errors import CommitFailed

if TYPE_CHECKING:
    from sqlmodel import Session


def safe_commit(session: "Session", *, error_msg: str) -> None:
    """
    Commits the session, making sure it is rolled back in case the commit fails.

    Arguments:
        error_msg: The message for the raised exception.

    Raises:
        CommitFailed: If committing the session failed.
    """
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise CommitFailed(error_msg) from e

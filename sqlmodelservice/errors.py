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

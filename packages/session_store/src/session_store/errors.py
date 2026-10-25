"""The store's own failures, with no HTTP knowledge."""

from contracts import Turn


class SessionStoreError(Exception):
    """Base class for every failure the store raises."""


class NotFoundError(SessionStoreError):
    """The object does not exist for this owner, or the owner does not exist."""


class PreparationLockedError(SessionStoreError):
    """A preparation with at least one session can no longer be edited."""


class InvalidStateError(SessionStoreError):
    """The session or turn is not in the state this operation requires."""


class SessionFullError(SessionStoreError):
    """The session already holds the maximum number of turns."""


class OpenQuestionError(SessionStoreError):
    """The session already has a question waiting for an answer."""

    def __init__(self, turn: Turn) -> None:
        """Carry the open turn so a route can return it instead of asking again."""
        super().__init__("The session already has an open question.")
        self.turn = turn
        """The turn that is already waiting for an answer."""

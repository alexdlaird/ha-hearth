__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from typing import Any


class HearthError(Exception):
    """
    Raised when a general Hearth API error has occurred.
    """

    def __init__(self,
                 error: str | BaseException,
                 meta: dict[str, Any] | None = None) -> None:
        super(HearthError, self).__init__(error)

        #: Metadata for context around the error that was raised.
        self.meta: dict[str, Any] | None = meta


class HearthAuthError(HearthError):
    """
    Raised when Hearth doesn't accept the API key (it's wrong, it was replaced, or its home is gone).
    """
    pass


class HearthDemoHomeError(HearthError):
    """
    Raised when the API key belongs to a demo home, which runs on a simulated thermostat and takes no posts.
    """
    pass


class HearthRateLimitedError(HearthError):
    """
    Raised when Hearth asks for fewer posts. ``meta["retry_after"]`` is how many seconds to wait.
    """
    pass


class HearthRejectedError(HearthError):
    """
    Raised when Hearth can't read a post. The error's message is Hearth's reason.
    """
    pass


class HearthSettingError(HearthError):
    """
    Raised when a setting from Hearth can't be applied to the thermostat. The error's message says why.
    """
    pass


class HearthConnectionError(HearthError):
    """
    Raised when Hearth can't be reached (the network, a timeout, or an error on Hearth's side).
    """
    pass

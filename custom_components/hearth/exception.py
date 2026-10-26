__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from pyhearth.exception import HearthError


class HearthSettingError(HearthError):
    """
    Raised when a setting from Hearth can't be applied to the thermostat. The error's message says why.
    """
    pass

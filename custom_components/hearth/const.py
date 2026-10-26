__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from datetime import timedelta
from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "hearth"
NAME: Final = "Hearth"
MANUFACTURER: Final = NAME
DEFAULT_API_URL: Final = "https://api.meethearth.app"
SITE_URL: Final = "https://www.meethearth.app"

CONF_API_URL: Final = "api_url"
CONF_THERMOSTAT: Final = "thermostat"
CONF_SENSORS: Final = "sensors"

#: How this Home Assistant names itself as a readings source in Hearth.
READINGS_SOURCE: Final = "home-assistant"
READINGS_SOURCE_NAME: Final = "Home Assistant"
#: The most sensors Hearth's readings API takes in one post (and a home holds in all).
MAX_SENSORS: Final = 10

#: Hearth reads the thermostat each minute; a change is posted sooner, but never within ``MIN_POST_GAP`` of the last
#: post, so posts stay under Hearth's limit of 4 a minute.
SYNC_INTERVAL: Final = timedelta(seconds=60)
MIN_POST_GAP: Final = timedelta(seconds=20)
#: How long a climate action may take before it counts as failed (the thermostat's own integration may be slow).
SERVICE_TIMEOUT: Final = 30
#: How many times one setting from Hearth is tried when the thermostat fails to take it for a passing reason.
MAX_ATTEMPTS: Final = 3
#: A temperature or humidity not reported for this long is left out of a post (a reading older than a day makes Hearth
#: refuse the whole post). A battery reports rarely, so it isn't held to this.
SENSOR_STALE_AFTER: Final = timedelta(minutes=30)
#: Who refused a setting, as reported to Hearth: the integration's own checks, or the thermostat itself.
REFUSED_BY_CHECK: Final = "check"
REFUSED_BY_THERMOSTAT: Final = "thermostat"

#: Hearth's settings are applied only inside this band (and the thermostat's own limits), whatever Hearth sends.
SAFE_MIN_C: Final = 7.0
SAFE_MAX_C: Final = 32.0
SAFE_MIN_F: Final = 45.0
SAFE_MAX_F: Final = 90.0

PLATFORMS: Final[list[Platform]] = [Platform.SENSOR]


class BridgeStatus(StrEnum):
    """
    The bridge's self-check, most urgent first (the status sensor shows the first that applies).
    """

    SLOWED_DOWN = "slowed_down"
    UNREACHABLE = "unreachable"
    POST_REFUSED = "post_refused"
    THERMOSTAT_MISSING = "thermostat_missing"
    THERMOSTAT_UNAVAILABLE = "thermostat_unavailable"
    SETTING_REFUSED = "setting_refused"
    SENSORS_NOT_ADDED = "sensors_not_added"
    OK = "ok"

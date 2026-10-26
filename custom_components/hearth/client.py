__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from homeassistant.const import __version__ as ha_version
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration
from pyhearth.client import HearthClient

from custom_components.hearth.const import DOMAIN, READINGS_SOURCE, READINGS_SOURCE_NAME


async def async_hearth_client(hass: HomeAssistant, api_key: str, api_url: str) -> HearthClient:
    """
    A connection to the Hearth home [api_key] belongs to, posting as this Home Assistant.

    Its ``User-Agent`` names Home Assistant's version and this integration's, so Hearth's logs say what posted.

    :param hass: Home Assistant.
    :param api_key: The home's Hearth API key.
    :param api_url: Where Hearth's API is.
    :return: The connection.
    """
    integration = await async_get_integration(hass, DOMAIN)
    return HearthClient(async_get_clientsession(hass),
                        api_key,
                        api_url,
                        source=READINGS_SOURCE,
                        source_name=READINGS_SOURCE_NAME,
                        agent=f"HomeAssistant/{ha_version} ha-hearth/{integration.version or 'core'}")

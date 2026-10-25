__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.hearth.api import HearthClient
from custom_components.hearth.const import CONF_API_URL, DEFAULT_API_URL, PLATFORMS
from custom_components.hearth.coordinator import HearthCoordinator

type HearthConfigEntry = ConfigEntry[HearthCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HearthConfigEntry) -> bool:
    """
    Set up the bridge to a Hearth home.

    :param hass: Home Assistant.
    :param entry: The Hearth home's config entry.
    :return: ``True`` once it's set up.
    """
    client = HearthClient(async_get_clientsession(hass),
                          entry.data[CONF_API_KEY],
                          entry.data.get(CONF_API_URL) or DEFAULT_API_URL)
    coordinator = HearthCoordinator(hass, entry, client)
    coordinator.async_track_thermostat()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HearthConfigEntry) -> bool:
    """
    Unload the bridge to a Hearth home.

    :param hass: Home Assistant.
    :param entry: The Hearth home's config entry.
    :return: ``True`` once it's unloaded.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

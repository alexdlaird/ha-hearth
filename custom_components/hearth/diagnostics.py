__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from custom_components.hearth.const import DOMAIN

if TYPE_CHECKING:
    from custom_components.hearth import HearthConfigEntry

TO_REDACT = {CONF_API_KEY, "authorization", "unique_id"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: "HearthConfigEntry") -> dict[str, Any]:
    """
    Diagnostics for a Hearth home's bridge: its configuration and last sync, with the API key redacted.

    :param hass: Home Assistant.
    :param entry: The Hearth home's config entry.
    :return: The diagnostics.
    """
    integration = await async_get_integration(hass, DOMAIN)
    diagnostics: dict[str, Any] = {
        "integration_version": str(integration.version),
        "temperature_unit": hass.config.units.temperature_unit,
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
    }
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None or coordinator.data is None:
        return diagnostics

    return diagnostics | {"api_url": coordinator.client.base_url, "last_sync": asdict(coordinator.data)}

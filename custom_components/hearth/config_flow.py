__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.climate.const import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from pyhearth.client import HearthClient
from pyhearth.exception import (
    HearthAuthError,
    HearthConnectionError,
    HearthDemoHomeError,
    HearthError,
)

from custom_components.hearth.const import (
    CONF_API_URL,
    CONF_SENSORS,
    CONF_THERMOSTAT,
    DEFAULT_API_URL,
    DOMAIN,
    MAX_SENSORS,
    NAME,
    READINGS_SOURCE,
)

logger = logging.getLogger(__name__)


class HearthConfigFlow(ConfigFlow, domain=DOMAIN):
    """
    Connect a Hearth home: its API key, then the thermostat and room sensors Hearth gets.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "HearthOptionsFlow":
        """
        Get the flow that changes what Hearth gets.

        :param config_entry: The Hearth home's config entry.
        :return: The options flow.
        """
        return HearthOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """
        Ask for the home's Hearth API key (Hearth app: Settings, then Manage home).

        :param user_input: What was entered, once submitted.
        :return: The next step.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            api_url = _api_url(user_input)
            if (error := await _check_key(self.hass, user_input[CONF_API_KEY], api_url)) is None:
                self._data = {CONF_API_KEY: user_input[CONF_API_KEY], CONF_API_URL: api_url}
                return await self.async_step_devices()
            errors["base"] = error

        return self.async_show_form(step_id="user",
                                    data_schema=_key_schema(self.show_advanced_options),
                                    errors=errors)

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """
        Choose the thermostat and the room sensors Hearth gets.

        :param user_input: What was chosen, once submitted.
        :return: The created entry, or the form again.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := _choice_error(user_input)) is None:
                return self.async_create_entry(title=NAME, data=self._data, options=_options_from(user_input))
            errors["base"] = error

        return self.async_show_form(step_id="devices",
                                    data_schema=self.add_suggested_values_to_schema(_choice_schema(),
                                                                                    user_input or {}),
                                    errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """
        Start reauthentication when Hearth stops taking the API key.

        :param entry_data: The entry's current data.
        :return: The next step.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """
        Ask for the home's current API key.

        :param user_input: What was entered, once submitted.
        :return: The updated entry, or the form again.
        """
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_url = entry.data.get(CONF_API_URL) or DEFAULT_API_URL
            if (error := await _check_key(self.hass, user_input[CONF_API_KEY], api_url)) is None:
                return self.async_update_reload_and_abort(entry,
                                                          data_updates={CONF_API_KEY: user_input[CONF_API_KEY]})
            errors["base"] = error

        return self.async_show_form(step_id="reauth_confirm", data_schema=_key_schema(False), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """
        Change the API key (or, in advanced mode, the Hearth API address).

        :param user_input: What was entered, once submitted.
        :return: The updated entry, or the form again.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_url = _api_url(user_input, entry.data.get(CONF_API_URL))
            if (error := await _check_key(self.hass, user_input[CONF_API_KEY], api_url)) is None:
                return self.async_update_reload_and_abort(entry,
                                                          data_updates={CONF_API_KEY: user_input[CONF_API_KEY],
                                                                        CONF_API_URL: api_url})
            errors["base"] = error

        return self.async_show_form(step_id="reconfigure",
                                    data_schema=self.add_suggested_values_to_schema(
                                        _key_schema(self.show_advanced_options),
                                        {CONF_API_URL: entry.data.get(CONF_API_URL) or DEFAULT_API_URL}),
                                    errors=errors)


class HearthOptionsFlow(OptionsFlowWithReload):
    """
    Change the thermostat and room sensors Hearth gets.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """
        Choose again.

        :param user_input: What was chosen, once submitted.
        :return: The updated options, or the form again.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := _choice_error(user_input)) is None:
                return self.async_create_entry(data=_options_from(user_input))
            errors["base"] = error

        current = user_input or {key: value for key, value in self.config_entry.options.items()
                                 if value not in (None, [])}
        return self.async_show_form(step_id="init",
                                    data_schema=self.add_suggested_values_to_schema(_choice_schema(), current),
                                    errors=errors)


def _key_schema(advanced: bool) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
    }
    if advanced:
        fields[vol.Optional(CONF_API_URL, default=DEFAULT_API_URL)] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL))
    return vol.Schema(fields)


def _choice_schema() -> vol.Schema:
    return vol.Schema({
        vol.Optional(CONF_THERMOSTAT): EntitySelector(EntitySelectorConfig(domain=CLIMATE_DOMAIN)),
        vol.Optional(CONF_SENSORS, default=[]): EntitySelector(
            EntitySelectorConfig(domain=SENSOR_DOMAIN, device_class=SensorDeviceClass.TEMPERATURE, multiple=True)),
    })


def _api_url(user_input: Mapping[str, Any], current: str | None = None) -> str:
    return str(user_input.get(CONF_API_URL) or current or DEFAULT_API_URL).rstrip("/")


async def _check_key(hass: HomeAssistant,
                     api_key: str,
                     api_url: str) -> str | None:
    try:
        await HearthClient(async_get_clientsession(hass), api_key, api_url, source=READINGS_SOURCE).check_key()
    except HearthAuthError:
        return "invalid_auth"
    except HearthDemoHomeError:
        return "demo_home"
    except HearthConnectionError:
        return "cannot_connect"
    except HearthError:
        return "unknown"
    except Exception:
        logger.exception("An unexpected error occurred checking the Hearth API key")
        return "unknown"

    return None


def _choice_error(choice: Mapping[str, Any]) -> str | None:
    sensors = choice.get(CONF_SENSORS) or []
    if not choice.get(CONF_THERMOSTAT) and not sensors:
        return "nothing_chosen"
    elif len(sensors) > MAX_SENSORS:
        return "too_many_sensors"
    else:
        return None


def _options_from(user_input: Mapping[str, Any]) -> dict[str, Any]:
    return {
        CONF_THERMOSTAT: user_input.get(CONF_THERMOSTAT) or None,
        CONF_SENSORS: list(user_input.get(CONF_SENSORS) or []),
    }

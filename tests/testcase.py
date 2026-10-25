__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import DATA_COMPONENT
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hearth.const import (
    CONF_API_URL,
    CONF_SENSORS,
    CONF_THERMOSTAT,
    DEFAULT_API_URL,
    DOMAIN,
    SYNC_INTERVAL,
)
from tests.fakethermostat import FakeThermostat


class HearthTestCase:
    API_KEY = "test-hearth-api-key"
    BRIDGE_URL = f"{DEFAULT_API_URL}/v1/bridge"
    READINGS_URL = f"{DEFAULT_API_URL}/v1/readings"
    THERMOSTAT = "climate.hallway"
    STATUS = "sensor.hearth_bridge_status"
    LAST_SYNC = "sensor.hearth_last_sync"
    EXPIRES_AT = "2026-10-25T18:05:00+00:00"

    async def given_fahrenheit(self, hass: HomeAssistant) -> None:
        await hass.config.async_update(unit_system="us_customary")

    async def given_thermostat(self, hass: HomeAssistant, **options: Any) -> FakeThermostat:
        thermostat = FakeThermostat(**options)
        assert await async_setup_component(hass, "climate", {})
        await hass.data[DATA_COMPONENT].async_add_entities([thermostat])
        await hass.async_block_till_done()
        return thermostat

    def given_entry(self,
                    hass: HomeAssistant,
                    thermostat: str | None = THERMOSTAT,
                    sensors: list[str] | None = None) -> MockConfigEntry:
        entry = MockConfigEntry(domain=DOMAIN,
                                title="Hearth",
                                data={CONF_API_KEY: self.API_KEY, CONF_API_URL: DEFAULT_API_URL},
                                options={CONF_THERMOSTAT: thermostat, CONF_SENSORS: sensors or []})
        entry.add_to_hass(hass)
        return entry

    def given_hearth_answers(self,
                             aioclient_mock: AiohttpClientMocker,
                             *,
                             desired: dict[str, Any] | None = None,
                             bridge_status: int = 200,
                             readings_status: int = 204,
                             readings_json: Any = None,
                             headers: dict[str, str] | None = None,
                             exc: Exception | None = None,
                             bridge_exc: Exception | None = None) -> None:
        aioclient_mock.clear_requests()
        aioclient_mock.post(self.BRIDGE_URL,
                            status=bridge_status,
                            json={"protocol": 1, "desired": desired} if bridge_status == 200 else None,
                            headers=headers,
                            exc=bridge_exc or exc)
        aioclient_mock.post(self.READINGS_URL,
                            status=readings_status,
                            json=readings_json,
                            headers=headers,
                            exc=exc)

    def given_sensor_device(self,
                            hass: HomeAssistant,
                            *,
                            temperature: str = "70.5",
                            unit: str = "°F",
                            humidity: str | None = "45",
                            battery: str | None = "80") -> str:
        owner = MockConfigEntry(domain="test_sensors")
        owner.add_to_hass(hass)
        device = dr.async_get(hass).async_get_or_create(config_entry_id=owner.entry_id,
                                                        identifiers={("test", "office")})
        registry = er.async_get(hass)
        temperature_id = ""
        for device_class, value, measured_in in (("temperature", temperature, unit),
                                                 ("humidity", humidity, "%"),
                                                 ("battery", battery, "%")):
            if value is None:
                continue
            registered = registry.async_get_or_create("sensor",
                                                      "test",
                                                      f"office_{device_class}",
                                                      device_id=device.id,
                                                      original_device_class=device_class,
                                                      suggested_object_id=f"office_{device_class}")
            hass.states.async_set(registered.entity_id,
                                  value,
                                  {"unit_of_measurement": measured_in, "friendly_name": f"Office {device_class}"})
            if device_class == "temperature":
                temperature_id = registered.entity_id
        return temperature_id

    async def when_set_up(self, hass: HomeAssistant, entry: MockConfigEntry) -> bool:
        set_up = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return set_up

    async def when_time_passes(self,
                               hass: HomeAssistant,
                               freezer: FrozenDateTimeFactory,
                               delta: timedelta = SYNC_INTERVAL) -> None:
        freezer.tick(delta)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    def posts(self, aioclient_mock: AiohttpClientMocker, url: str) -> list[Any]:
        return [data for _method, called, data, _headers in aioclient_mock.mock_calls if str(called) == url]

    def assert_status(self,
                      hass: HomeAssistant,
                      expected: str,
                      detail: bool = False) -> None:
        state = hass.states.get(self.STATUS)
        assert state is not None
        assert expected == state.state
        if detail:
            assert state.attributes["detail"]

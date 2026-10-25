__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hearth.const import DOMAIN
from tests.testcase import HearthTestCase


class TestConfigFlow(HearthTestCase):
    async def start(self, hass: HomeAssistant, advanced: bool = False) -> Any:
        return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER,
                                                                          "show_advanced_options": advanced})

    def given_temperature_sensors(self, hass: HomeAssistant, count: int) -> list[str]:
        sensors = [f"sensor.room_{index}_temperature" for index in range(count)]
        for sensor in sensors:
            hass.states.async_set(sensor, "70", {"unit_of_measurement": "°F", "device_class": "temperature"})
        return sensors

    async def test_create_entry(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        sensors = self.given_temperature_sensors(hass, 1)
        self.given_hearth_answers(aioclient_mock)
        flow = await self.start(hass)

        # WHEN
        devices = await hass.config_entries.flow.async_configure(flow["flow_id"], {"api_key": self.API_KEY})
        created = await hass.config_entries.flow.async_configure(devices["flow_id"], {"thermostat": self.THERMOSTAT,
                                                                                      "sensors": sensors})
        await hass.async_block_till_done()

        # THEN
        assert "devices" == devices["step_id"]
        assert {"source": "home-assistant", "sensors": []} == self.posts(aioclient_mock, self.READINGS_URL)[0], \
            "an empty readings post checks the key"
        assert FlowResultType.CREATE_ENTRY == created["type"]
        assert {"api_key": self.API_KEY, "api_url": "https://api.meethearth.app"} == created["data"]
        assert {"thermostat": self.THERMOSTAT, "sensors": sensors} == created["options"]

    @pytest.mark.parametrize(("answer", "error"), [
        ({"readings_status": 401}, "invalid_auth"),
        ({"readings_status": 403}, "demo_home"),
        ({"readings_status": 503}, "cannot_connect"),
        ({"exc": TimeoutError()}, "cannot_connect"),
        ({"readings_status": 400}, "unknown"),
        ({"exc": RuntimeError("boom")}, "unknown"),
    ])
    async def test_invalid_key(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, answer: dict[str, Any],
            error: str) -> None:
        # GIVEN
        self.given_hearth_answers(aioclient_mock, **answer)
        flow = await self.start(hass)

        # WHEN
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"api_key": "wrong"})

        # THEN
        assert FlowResultType.FORM == result["type"]
        assert "user" == result["step_id"]
        assert {"base": error} == result["errors"]

    @pytest.mark.parametrize(("count", "error"), [(0, "nothing_chosen"), (11, "too_many_sensors")])
    async def test_invalid_choice(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, count: int, error: str) -> None:
        # GIVEN
        sensors = self.given_temperature_sensors(hass, count)
        self.given_hearth_answers(aioclient_mock)
        flow = await self.start(hass)
        devices = await hass.config_entries.flow.async_configure(flow["flow_id"], {"api_key": self.API_KEY})

        # WHEN
        result = await hass.config_entries.flow.async_configure(devices["flow_id"], {"sensors": sensors})

        # THEN
        assert FlowResultType.FORM == result["type"]
        assert {"base": error} == result["errors"]

    async def test_custom_api_url(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        sensors = self.given_temperature_sensors(hass, 1)
        aioclient_mock.post("https://hearth.example.com/v1/readings", status=204)
        flow = await self.start(hass, advanced=True)

        # WHEN
        devices = await hass.config_entries.flow.async_configure(flow["flow_id"], {
            "api_key": self.API_KEY,
            "api_url": "https://hearth.example.com/"
        })
        created = await hass.config_entries.flow.async_configure(devices["flow_id"], {"sensors": sensors})

        # THEN
        assert "https://hearth.example.com" == created["data"]["api_url"]

    async def test_single_instance(self, hass: HomeAssistant) -> None:
        # GIVEN
        self.given_entry(hass)

        # WHEN
        result = await self.start(hass)

        # THEN
        assert FlowResultType.ABORT == result["type"]
        assert "single_instance_allowed" == result["reason"]

    async def test_reauth(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        entry = self.given_entry(hass)
        self.given_hearth_answers(aioclient_mock, readings_status=401)
        flow = await entry.start_reauth_flow(hass)
        refused = await hass.config_entries.flow.async_configure(flow["flow_id"], {"api_key": "old"})
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"api_key": "new-key"})
        await hass.async_block_till_done()

        # THEN
        assert {"base": "invalid_auth"} == refused["errors"]
        assert FlowResultType.ABORT == result["type"]
        assert "reauth_successful" == result["reason"]
        assert "new-key" == entry.data["api_key"]

    async def test_reconfigure(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        entry = self.given_entry(hass)
        aioclient_mock.post("https://hearth.example.com/v1/readings", status=204)
        flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_RECONFIGURE,
                                                                          "entry_id": entry.entry_id,
                                                                          "show_advanced_options": True})

        # WHEN
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], {
            "api_key": "another-key",
            "api_url": "https://hearth.example.com"
        })
        await hass.async_block_till_done()

        # THEN
        assert FlowResultType.ABORT == result["type"]
        assert "reconfigure_successful" == result["reason"]
        assert "another-key" == entry.data["api_key"]
        assert "https://hearth.example.com" == entry.data["api_url"]

    async def test_options(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        sensors = self.given_temperature_sensors(hass, 1)
        self.given_hearth_answers(aioclient_mock)
        entry = self.given_entry(hass)
        await self.when_set_up(hass, entry)
        flow = await hass.config_entries.options.async_init(entry.entry_id)

        # WHEN
        refused = await hass.config_entries.options.async_configure(flow["flow_id"], {})
        result = await hass.config_entries.options.async_configure(flow["flow_id"], {"sensors": sensors})
        await hass.async_block_till_done()

        # THEN
        assert {"base": "nothing_chosen"} == refused["errors"]
        assert FlowResultType.CREATE_ENTRY == result["type"]
        assert {"thermostat": None, "sensors": sensors} == entry.options

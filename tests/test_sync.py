__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

import hashlib
import logging
from datetime import timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hearth.const import MAX_ATTEMPTS, REFUSED_BY_CHECK, REFUSED_BY_THERMOSTAT, BridgeStatus
from tests.testcase import HearthTestCase


class TestSync(HearthTestCase):
    def heat_cool(self, low: float = 68.0, high: float = 75.0, **extra: Any) -> dict[str, Any]:
        return {"hvac_mode": "heat_cool", "target_temp_low": low, "target_temp_high": high, "unit": "°F",
                "expires_at": self.EXPIRES_AT, **extra}

    def heat(self, temperature: float, unit: str = "°F") -> dict[str, Any]:
        return {"hvac_mode": "heat", "temperature": temperature, "unit": unit, "expires_at": self.EXPIRES_AT}

    async def test_thermostat_posted_with_converted_step(self, hass: HomeAssistant,
                                                         aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        posted = self.posts(aioclient_mock, self.BRIDGE_URL)[0]
        thermostat = posted["thermostat"]
        assert 1 == posted["protocol"]
        assert "climate.hallway" == thermostat["entity_id"]
        assert "Hallway" == thermostat["name"]
        assert "°F" == thermostat["unit"]
        assert "heat_cool" == thermostat["hvac_mode"]
        assert 66.0 == thermostat["target_temp_low"]
        assert 74.0 == thermostat["target_temp_high"]
        assert 0.9 == thermostat["target_temp_step"], "Home Assistant doesn't convert a 0.5 °C step"
        assert ClimateEntityFeature.TARGET_TEMPERATURE_RANGE in ClimateEntityFeature(thermostat["supported_features"])
        self.assert_status(hass, BridgeStatus.OK)

    async def test_setting_applied_once(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                        freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool())

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))
        await self.when_time_passes(hass, freezer)

        # THEN
        assert [{"target_temp_low": 20.0, "target_temp_high": pytest.approx(23.89, abs=0.01)}] == \
            thermostat.calls_to("set_temperature")
        assert [] == thermostat.calls_to("set_hvac_mode")
        state = hass.states.get(self.THERMOSTAT)
        assert state is not None
        assert 68.0 == state.attributes["target_temp_low"]
        assert 75.0 == state.attributes["target_temp_high"]

    async def test_mode_set_before_setpoints(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass, hvac_mode=HVACMode.HEAT, temperature=20.0,
                                                 mode_with_setpoints=False)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool())

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert ["set_hvac_mode", "set_temperature"] == [name for name, _ in thermostat.calls], \
            "some thermostat integrations ignore a mode passed along with setpoints"
        state = hass.states.get(self.THERMOSTAT)
        assert state is not None
        assert "heat_cool" == state.state

    async def test_off_and_fan_mode_set_separately(self, hass: HomeAssistant,
                                                   aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, desired={"hvac_mode": "off", "fan_mode": "on", "unit": "°F",
                                                           "expires_at": self.EXPIRES_AT})

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [("set_hvac_mode", {"hvac_mode": "off"}), ("set_fan_mode", {"fan_mode": "on"})] == thermostat.calls

    async def test_off_ignores_out_of_band_setpoints(self, hass: HomeAssistant,
                                                     aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool(low=10.0, high=99.0, hvac_mode="off"))

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [("set_hvac_mode", {"hvac_mode": "off"})] == thermostat.calls
        self.assert_status(hass, BridgeStatus.OK)

    async def test_fan_mode_only_change_applied(self, hass: HomeAssistant,
                                                aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool(low=66.0, high=74.0, fan_mode="on"))

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [("set_fan_mode", {"fan_mode": "on"})] == thermostat.calls, "the setpoints are already in place"

    async def test_unoffered_fan_mode_left_out(self, hass: HomeAssistant,
                                               aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool(fan_mode="circulate"))

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert ["set_temperature"] == [name for name, _ in thermostat.calls]
        self.assert_status(hass, BridgeStatus.OK)

    async def test_heat_only_thermostat_gets_single_temperature(self, hass: HomeAssistant,
                                                                aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass, hvac_mode=HVACMode.HEAT,
                                                 hvac_modes=[HVACMode.OFF, HVACMode.HEAT],
                                                 temperature=19.0, low=None, high=None,
                                                 features=ClimateEntityFeature.TARGET_TEMPERATURE)
        self.given_hearth_answers(aioclient_mock, desired=self.heat(68.0))

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [{"temperature": 20.0}] == thermostat.calls_to("set_temperature")

    @pytest.mark.parametrize(("changes", "why"), [
        ({"target_temp_high": 92.0}, "above the safe band, inside the thermostat's limits"),
        ({"target_temp_low": 43.0}, "below the safe band, inside the thermostat's limits"),
        ({"unit": "°C"}, "in a unit Home Assistant doesn't use"),
        ({"hvac_mode": "auto"}, "a mode the thermostat doesn't offer"),
        ({"target_temp_low": "warm"}, "not a number"),
        ({"hvac_mode": "heat"}, "a low/high range in heat"),
        ({"temperature": 70.0}, "one temperature and a range at once"),
    ])
    async def test_invalid_setting_refused(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                           freezer: FrozenDateTimeFactory, changes: dict[str, Any],
                                           why: str) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool(**changes))

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))
        await self.when_time_passes(hass, freezer)

        # THEN
        assert [] == thermostat.calls, f"never applied: {why}"
        self.assert_status(hass, BridgeStatus.SETTING_REFUSED, detail=True)

    async def test_range_refused_without_range_support(self, hass: HomeAssistant,
                                                       aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass, features=ClimateEntityFeature.TARGET_TEMPERATURE)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool())

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [] == thermostat.calls
        self.assert_status(hass, BridgeStatus.SETTING_REFUSED, detail=True)

    async def test_safe_band_in_celsius(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        thermostat = await self.given_thermostat(hass, hvac_mode=HVACMode.HEAT, temperature=20.0)
        self.given_hearth_answers(aioclient_mock, desired=self.heat(33.0, unit="°C"))

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [] == thermostat.calls, "33 °C is past the 32 °C safe band, inside the thermostat's 35 °C maximum"
        self.assert_status(hass, BridgeStatus.SETTING_REFUSED)

    async def test_refused_setting_not_retried(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                               freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass, fails_with=ServiceValidationError("deadband too small"))
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool())

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))
        await self.when_time_passes(hass, freezer)
        await self.when_time_passes(hass, freezer)

        # THEN
        assert 1 == len(thermostat.calls_to("set_temperature"))
        self.assert_status(hass, BridgeStatus.SETTING_REFUSED, detail=True)

    async def test_failed_setting_retried(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                          freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass, fails_with=RuntimeError("the thermostat's cloud timed out"))
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool())

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))
        for _ in range(MAX_ATTEMPTS + 1):
            await self.when_time_passes(hass, freezer)

        # THEN
        assert MAX_ATTEMPTS == len(thermostat.calls_to("set_temperature"))
        self.assert_status(hass, BridgeStatus.SETTING_REFUSED, detail=True)

    async def test_setting_already_shown_not_written(self, hass: HomeAssistant,
                                                     aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool(low=66.4, high=74.4))

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [] == thermostat.calls, "within half a 0.9 °F step of the 66/74 it shows"
        self.assert_status(hass, BridgeStatus.OK)

    async def test_unavailable_thermostat_not_set(self, hass: HomeAssistant,
                                                  aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        hass.states.async_set(self.THERMOSTAT, "unavailable", {"friendly_name": "Hallway"})
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool())

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert self.posts(aioclient_mock, self.BRIDGE_URL)[0]["thermostat"]["available"] is False
        self.assert_status(hass, BridgeStatus.THERMOSTAT_UNAVAILABLE)

    async def test_startup_placeholder_not_posted(self, hass: HomeAssistant,
                                                  aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        hass.states.async_set(self.THERMOSTAT, "unavailable", {"restored": True, "friendly_name": "Hallway"})
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [] == self.posts(aioclient_mock, self.BRIDGE_URL)
        self.assert_status(hass, BridgeStatus.THERMOSTAT_UNAVAILABLE)

    async def test_missing_thermostat(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        assert [] == self.posts(aioclient_mock, self.BRIDGE_URL)
        self.assert_status(hass, BridgeStatus.THERMOSTAT_MISSING)

    async def test_thermostat_change_posted_after_gap(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                                      freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock)
        await self.when_set_up(hass, self.given_entry(hass))

        # WHEN
        await thermostat.async_set_temperature(target_temp_low=21.0, target_temp_high=24.0)
        await hass.async_block_till_done()
        right_after = len(self.posts(aioclient_mock, self.BRIDGE_URL))
        await self.when_time_passes(hass, freezer, timedelta(seconds=21))

        # THEN
        bridge_posts = self.posts(aioclient_mock, self.BRIDGE_URL)
        assert 1 == right_after, "Hearth takes at most 4 posts a minute"
        assert 2 == len(bridge_posts)
        assert 70.0 == bridge_posts[-1]["thermostat"]["target_temp_low"]

    async def test_applied_setting_confirmed_after_gap(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                                       freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool())
        await self.when_set_up(hass, self.given_entry(hass))

        # WHEN
        await self.when_time_passes(hass, freezer, timedelta(seconds=21))

        # THEN
        shown = self.posts(aioclient_mock, self.BRIDGE_URL)[-1]["thermostat"]
        assert 68.0 == shown["target_temp_low"]
        assert 75.0 == shown["target_temp_high"]

    async def test_sensor_readings_include_device_humidity_and_battery(self, hass: HomeAssistant,
                                                                       aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        temperature = self.given_sensor_device(hass)
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass, thermostat=None, sensors=[temperature]))

        # THEN
        posted = self.posts(aioclient_mock, self.READINGS_URL)[0]
        reading = posted["sensors"][0]
        assert "home-assistant" == posted["source"]
        assert temperature == reading["id"]
        assert 70.5 == reading["temperature"]
        assert "F" == reading["unit"]
        assert 45.0 == reading["humidity"]
        assert 80.0 == reading["battery"]
        assert [] == self.posts(aioclient_mock, self.BRIDGE_URL)

    async def test_stale_battery_still_sent(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                            freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        temperature = self.given_sensor_device(hass)
        freezer.tick(timedelta(hours=6))
        hass.states.async_set(temperature, "71.0", {"unit_of_measurement": "°F"}, force_update=True)
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass, thermostat=None, sensors=[temperature]))

        # THEN
        reading = self.posts(aioclient_mock, self.READINGS_URL)[0]["sensors"][0]
        assert 80.0 == reading["battery"], "a battery often reports only when it changes"
        assert "humidity" not in reading

    @pytest.mark.parametrize(("device", "why"), [
        ({"temperature": "unavailable"}, "unavailable"),
        ({"temperature": "warm"}, "not a number"),
        ({"unit": "K"}, "a unit Hearth doesn't take"),
    ])
    async def test_unusable_sensor_left_out(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                            device: dict[str, str], why: str) -> None:
        # GIVEN
        temperature = self.given_sensor_device(hass, **device)
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass, thermostat=None, sensors=[temperature]))

        # THEN
        assert [] == self.posts(aioclient_mock, self.READINGS_URL), f"left out: {why}"

    async def test_stale_sensor_left_out(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                         freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        temperature = self.given_sensor_device(hass, humidity=None, battery=None)
        freezer.tick(timedelta(minutes=31))
        hass.states.async_set("sensor.porch_temperature", "55", {"unit_of_measurement": "°F"})
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass, thermostat=None,
                                                      sensors=[temperature, "sensor.porch_temperature"]))

        # THEN
        sent = [reading["id"] for reading in self.posts(aioclient_mock, self.READINGS_URL)[0]["sensors"]]
        assert ["sensor.porch_temperature"] == sent

    async def test_other_device_entities_ignored(self, hass: HomeAssistant,
                                                 aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        temperature = self.given_sensor_device(hass, humidity=None, battery=None)
        registry = er.async_get(hass)
        entry = registry.async_get(temperature)
        assert entry is not None
        switch = registry.async_get_or_create("switch", "test", "office_switch", device_id=entry.device_id)
        hass.states.async_set(switch.entity_id, "on")
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass, thermostat=None, sensors=[temperature]))

        # THEN
        reading = self.posts(aioclient_mock, self.READINGS_URL)[0]["sensors"][0]
        assert {"id", "name", "temperature", "unit", "time"} == set(reading)

    @pytest.mark.parametrize(("status", "body"), [
        (422, None),
        (200, {"not_added": ["sensor.porch_temperature"]}),
    ])
    async def test_sensors_not_added_status(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                            status: int, body: Any) -> None:
        # GIVEN
        hass.states.async_set("sensor.porch_temperature", "55", {"unit_of_measurement": "°F"})
        self.given_hearth_answers(aioclient_mock, readings_status=status, readings_json=body)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass, thermostat=None, sensors=["sensor.porch_temperature"]))

        # THEN
        self.assert_status(hass, BridgeStatus.SENSORS_NOT_ADDED)
        state = hass.states.get(self.STATUS)
        assert state is not None
        assert ["sensor.porch_temperature"] == state.attributes["sensors_not_added"]

    async def test_rejected_key_starts_reauth(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, bridge_status=401)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        flows = hass.config_entries.flow.async_progress_by_handler("hearth")
        assert [SOURCE_REAUTH] == [flow["context"]["source"] for flow in flows]

    async def test_rate_limited_pauses_posts(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                             freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        temperature = self.given_sensor_device(hass)
        self.given_hearth_answers(aioclient_mock, bridge_status=429, headers={"Retry-After": "150"})
        await self.when_set_up(hass, self.given_entry(hass, sensors=[temperature]))
        readings_after_429 = len(self.posts(aioclient_mock, self.READINGS_URL))

        # WHEN
        await self.when_time_passes(hass, freezer)
        paused = len(self.posts(aioclient_mock, self.BRIDGE_URL))
        self.given_hearth_answers(aioclient_mock)
        await self.when_time_passes(hass, freezer)
        await self.when_time_passes(hass, freezer)

        # THEN
        assert 0 == readings_after_429, "not another post right after Hearth asked to wait"
        assert 1 == paused
        assert 1 == len(self.posts(aioclient_mock, self.BRIDGE_URL)), "posting again once the wait is over"
        self.assert_status(hass, BridgeStatus.OK)

    async def test_malformed_answer_ignored(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                            freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        thermostat = await self.given_thermostat(hass)
        aioclient_mock.post(self.BRIDGE_URL, status=200, text="not json")
        await self.when_set_up(hass, self.given_entry(hass))
        ok = hass.states.get(self.STATUS)

        # WHEN
        self.given_hearth_answers(aioclient_mock, bridge_status=429, headers={"Retry-After": "soon"})
        await self.when_time_passes(hass, freezer)
        self.given_hearth_answers(aioclient_mock)
        await self.when_time_passes(hass, freezer, timedelta(seconds=59))

        # THEN
        assert ok is not None
        assert BridgeStatus.OK == ok.state
        assert [] == thermostat.calls
        assert [] == self.posts(aioclient_mock, self.BRIDGE_URL), "a Retry-After that isn't a number waits a minute"

    @pytest.mark.parametrize(("status", "expected"), [
        (500, BridgeStatus.UNREACHABLE),
        (503, BridgeStatus.UNREACHABLE),
        (400, BridgeStatus.POST_REFUSED),
        (403, BridgeStatus.POST_REFUSED),
    ])
    async def test_failed_post_reported(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int,
                                        expected: str) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, bridge_status=status)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        self.assert_status(hass, expected)

    async def test_problem_logged_once(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                       freezer: FrozenDateTimeFactory, caplog: pytest.LogCaptureFixture) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, bridge_status=400)
        caplog.set_level(logging.INFO, logger="custom_components.hearth")

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))
        await self.when_time_passes(hass, freezer)
        await self.when_time_passes(hass, freezer)
        self.given_hearth_answers(aioclient_mock)
        await self.when_time_passes(hass, freezer)

        # THEN
        refused = [record for record in caplog.records if "refused the bridge's post" in record.message]
        recovered = [record for record in caplog.records if "recovered" in record.message]
        assert 1 == len(refused)
        assert 1 == len(recovered)

    async def test_failed_thermostat_post_still_posts_readings(self, hass: HomeAssistant,
                                                               aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        temperature = self.given_sensor_device(hass)
        self.given_hearth_answers(aioclient_mock, bridge_exc=TimeoutError())

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass, sensors=[temperature]))

        # THEN
        assert 1 == len(self.posts(aioclient_mock, self.READINGS_URL))
        self.assert_status(hass, BridgeStatus.UNREACHABLE)

    async def test_recovers_after_outage(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                         freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock, exc=TimeoutError())
        await self.when_set_up(hass, self.given_entry(hass))
        during = hass.states.get(self.STATUS)

        # WHEN
        self.given_hearth_answers(aioclient_mock)
        await self.when_time_passes(hass, freezer)

        # THEN
        assert during is not None
        assert BridgeStatus.UNREACHABLE == during.state
        self.assert_status(hass, BridgeStatus.OK)

    async def test_last_sync_kept_through_outage(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                                 freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock)
        await self.when_set_up(hass, self.given_entry(hass))
        synced = hass.states.get(self.LAST_SYNC)

        # WHEN
        self.given_hearth_answers(aioclient_mock, exc=TimeoutError())
        await self.when_time_passes(hass, freezer)

        # THEN
        after = hass.states.get(self.LAST_SYNC)
        assert synced is not None
        assert after is not None
        assert synced.state == after.state

    async def test_thermostat_device_posted_as_a_hash(self, hass: HomeAssistant,
                                                      aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_thermostat(hass, unique_id="SN-4417-0092")
        self.given_hearth_answers(aioclient_mock)
        entry = er.async_get(hass).async_get(self.THERMOSTAT)
        assert entry is not None

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        thermostat = self.posts(aioclient_mock, self.BRIDGE_URL)[0]["thermostat"]
        expected = hashlib.sha256(f"{entry.platform}:{entry.unique_id}".encode()).hexdigest()
        assert expected == thermostat["device"]
        assert entry.unique_id not in str(thermostat), "the unique id itself never leaves Home Assistant"

    @pytest.mark.parametrize(("thermostat_options", "desired_changes", "by"), [
        ({"fails_with": ServiceValidationError("deadband too small")}, {}, REFUSED_BY_THERMOSTAT),
        ({}, {"hvac_mode": "auto"}, REFUSED_BY_CHECK),
    ])
    async def test_refused_setting_reported_once(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                                 freezer: FrozenDateTimeFactory, thermostat_options: dict[str, Any],
                                                 desired_changes: dict[str, Any], by: str) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        await self.given_thermostat(hass, **thermostat_options)
        desired = self.heat_cool(**desired_changes)
        self.given_hearth_answers(aioclient_mock, desired=desired)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))
        await self.when_time_passes(hass, freezer)
        await self.when_time_passes(hass, freezer)

        # THEN
        posts = self.posts(aioclient_mock, self.BRIDGE_URL)
        assert "refused" not in posts[0]
        refused = posts[1]["refused"]
        setting = {key: desired[key] for key in ("hvac_mode", "target_temp_low", "target_temp_high")}
        assert (setting, by) == (refused["setting"], refused["by"])
        assert refused["reason"]
        assert "refused" not in posts[2], "reported once; Hearth stops answering it"

    async def test_passing_failure_not_reported(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                                freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        await self.given_fahrenheit(hass)
        await self.given_thermostat(hass, fails_with=RuntimeError("the thermostat's cloud timed out"))
        self.given_hearth_answers(aioclient_mock, desired=self.heat_cool())

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))
        for _ in range(MAX_ATTEMPTS + 1):
            await self.when_time_passes(hass, freezer)

        # THEN
        posts = self.posts(aioclient_mock, self.BRIDGE_URL)
        assert not [post for post in posts if "refused" in post], "an outage mustn't teach Hearth anything"

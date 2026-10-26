__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hearth.const import DOMAIN, THERMOSTAT_MISSING_ISSUE, THERMOSTAT_MISSING_REPAIR_AFTER
from custom_components.hearth.diagnostics import async_get_config_entry_diagnostics
from tests.testcase import HearthTestCase


class TestInit(HearthTestCase):
    async def test_diagnostics_redact_api_key(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock)
        entry = self.given_entry(hass)
        await self.when_set_up(hass, entry)

        # WHEN
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

        # THEN
        assert self.API_KEY not in str(diagnostics)
        assert "**REDACTED**" == diagnostics["entry"]["data"]["api_key"]
        assert "ok" == diagnostics["last_sync"]["status"]
        assert "https://api.meethearth.app" == diagnostics["api_url"]

    async def test_diagnostics_before_first_sync(self, hass: HomeAssistant) -> None:
        # GIVEN
        entry = self.given_entry(hass)

        # WHEN
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

        # THEN
        assert "last_sync" not in diagnostics
        assert self.API_KEY not in str(diagnostics)

    async def test_unload(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                          freezer: FrozenDateTimeFactory) -> None:
        # GIVEN
        thermostat = await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock)
        entry = self.given_entry(hass)
        await self.when_set_up(hass, entry)
        before = len(self.posts(aioclient_mock, self.BRIDGE_URL))

        # WHEN
        assert await hass.config_entries.async_unload(entry.entry_id)
        await thermostat.async_set_temperature(target_temp_low=21.0, target_temp_high=24.0)
        await self.when_time_passes(hass, freezer)

        # THEN
        assert ConfigEntryState.NOT_LOADED == entry.state
        assert before == len(self.posts(aioclient_mock, self.BRIDGE_URL)), "nothing posted after unloading"

    async def test_remove_clears_repairs(self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                         freezer: FrozenDateTimeFactory, issue_registry: ir.IssueRegistry) -> None:
        # GIVEN
        entry = self.given_entry(hass)
        self.given_hearth_answers(aioclient_mock)
        await self.when_set_up(hass, entry)
        await self.when_time_passes(hass, freezer, THERMOSTAT_MISSING_REPAIR_AFTER + timedelta(minutes=5))
        raised = issue_registry.async_get_issue(DOMAIN, THERMOSTAT_MISSING_ISSUE)

        # WHEN
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()

        # THEN
        assert raised is not None
        assert issue_registry.async_get_issue(DOMAIN, THERMOSTAT_MISSING_ISSUE) is None

    async def test_posts_name_home_assistant_and_the_integration(
            self, hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
        # GIVEN
        await self.given_thermostat(hass)
        self.given_hearth_answers(aioclient_mock)

        # WHEN
        await self.when_set_up(hass, self.given_entry(hass))

        # THEN
        agent = next(headers["User-Agent"] for _method, url, _data, headers in aioclient_mock.mock_calls
                     if str(url) == self.BRIDGE_URL)
        assert agent.startswith("pyhearth/"), "so Hearth's logs say what posted"
        assert " HomeAssistant/" in agent and " ha-hearth/" in agent

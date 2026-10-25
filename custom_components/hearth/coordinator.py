__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.climate.const import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ServiceValidationError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from custom_components.hearth.api import HearthClient
from custom_components.hearth.const import (
    CONF_SENSORS,
    CONF_THERMOSTAT,
    DEFAULT_RETRY_AFTER,
    DOMAIN,
    MAX_ATTEMPTS,
    MIN_POST_GAP,
    REFUSED_BY_CHECK,
    REFUSED_BY_THERMOSTAT,
    SERVICE_TIMEOUT,
    SYNC_INTERVAL,
    BridgeStatus,
)
from custom_components.hearth.exception import (
    HearthAuthError,
    HearthConnectionError,
    HearthError,
    HearthRateLimitedError,
    HearthSettingError,
)
from custom_components.hearth.sync import (
    Setting,
    already_shows,
    check_setting,
    device_key,
    is_available,
    is_placeholder,
    sensor_readings,
    setpoint_step,
    setpoints_shown,
    thermostat_post,
)

if TYPE_CHECKING:
    from custom_components.hearth import HearthConfigEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    """
    One sync with Hearth, for the self-check sensors and diagnostics.
    """

    #: The self-check's verdict.
    status: BridgeStatus
    #: When the sync ran.
    at: datetime
    #: When Hearth last took a post.
    synced_at: datetime | None = None
    #: More about the status, such as why a setting wasn't applied.
    detail: str | None = None
    #: The setting Hearth last answered with.
    desired: dict[str, Any] | None = None
    #: The setting last applied to the thermostat.
    applied: dict[str, Any] | None = None
    #: How many sensors the last readings post carried.
    sensors_posted: int = 0
    #: The posted sensors that aren't added to a room in the Hearth app yet.
    sensors_not_added: list[str] = field(default_factory=list)


#: The answer's fields that make up a setting, as reported back to Hearth when it's refused.
_SETTING_KEYS = (ATTR_HVAC_MODE, ATTR_TEMPERATURE, ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH, ATTR_FAN_MODE)


class HearthCoordinator(DataUpdateCoordinator[SyncResult]):
    """
    One Home Assistant's bridge to one Hearth home. Each minute, and soon after the thermostat changes, it posts the
    thermostat and the room sensors to Hearth and applies the setting Hearth answers with, using Home Assistant's own
    climate actions.
    """

    config_entry: "HearthConfigEntry"

    def __init__(self,
                 hass: HomeAssistant,
                 entry: "HearthConfigEntry",
                 client: HearthClient) -> None:
        #: The connection to the Hearth home.
        self.client: HearthClient = client
        #: The thermostat Hearth runs, if one was chosen.
        self.thermostat: str | None = entry.options.get(CONF_THERMOSTAT) or None
        #: The room temperature sensors Hearth gets.
        self.sensors: list[str] = list(entry.options.get(CONF_SENSORS) or [])

        self._setting_key: tuple[tuple[str, Any], ...] | None = None
        self._attempts = 0
        self._refusal: str | None = None
        self._applied: dict[str, Any] | None = None
        self._refused: dict[str, Any] | None = None

        self._last_post: datetime | None = None
        self._wait_until: datetime | None = None
        self._last_synced: datetime | None = None
        self._deferred_post: CALLBACK_TYPE | None = None
        self._logged: set[BridgeStatus] = set()

        debouncer: Debouncer[Any] = Debouncer(hass, logger, cooldown=MIN_POST_GAP.total_seconds(), immediate=True)
        super(HearthCoordinator, self).__init__(hass,
                                                logger,
                                                config_entry=entry,
                                                name=DOMAIN,
                                                update_interval=SYNC_INTERVAL,
                                                request_refresh_debouncer=debouncer)

    @callback
    def async_track_thermostat(self) -> None:
        """
        Post soon after the thermostat changes, so Hearth sees changes (and its own settings landing) quickly.
        """
        if self.thermostat is not None:
            self.config_entry.async_on_unload(
                async_track_state_change_event(self.hass, [self.thermostat], self._on_thermostat_changed))
        self.config_entry.async_on_unload(self._cancel_deferred_post)

    async def _on_thermostat_changed(self, _event: Event[EventStateChangedData]) -> None:
        await self.async_request_refresh()

    async def _async_update_data(self) -> SyncResult:
        now = dt_util.utcnow()
        if self._wait_until is not None and now < self._wait_until:
            return self._result(BridgeStatus.SLOWED_DOWN, now)
        if self._last_post is not None and now - self._last_post < MIN_POST_GAP:
            self._defer_post((self._last_post + MIN_POST_GAP - now).total_seconds())
            return self.data if self.data is not None else self._result(BridgeStatus.OK, now)
        self._last_post = now

        statuses: list[tuple[BridgeStatus, str | None]] = []
        desired = None
        readings: list[dict[str, Any]] = []
        not_added: list[str] = []
        failed = False
        try:
            desired, thermostat_statuses = await self._sync_thermostat()
            statuses.extend(thermostat_statuses)
        except HearthError as e:
            statuses.append(self._failure(e, now))
            failed = True
        try:
            readings = [] if self._wait_until is not None else sensor_readings(self.hass, self.sensors, now)
            if readings:
                not_added = (await self.client.async_post_readings(readings)).not_added
                if not_added:
                    statuses.append((BridgeStatus.SENSORS_NOT_ADDED, ", ".join(not_added)))
        except HearthError as e:
            statuses.append(self._failure(e, now))
            failed = True

        if not failed:
            self._wait_until = None
            self._last_synced = now
        self._log_recoveries({status for status, _ in statuses})
        status, detail = min(statuses, key=_urgency, default=(BridgeStatus.OK, None))

        return SyncResult(status=status,
                          at=now,
                          synced_at=self._last_synced,
                          detail=detail,
                          desired=desired,
                          applied=self._applied,
                          sensors_posted=len(readings),
                          sensors_not_added=not_added)

    async def _sync_thermostat(self) -> tuple[dict[str, Any] | None, list[tuple[BridgeStatus, str | None]]]:
        if self.thermostat is None:
            return None, []

        state = self.hass.states.get(self.thermostat)
        if state is None:
            return None, [(BridgeStatus.THERMOSTAT_MISSING, self.thermostat)]
        if is_placeholder(state):
            return None, [(BridgeStatus.THERMOSTAT_UNAVAILABLE, "Home Assistant is starting")]

        unit = self.hass.config.units.temperature_unit
        step = setpoint_step(self.hass, state, unit)
        post = thermostat_post(state, unit, step, device_key(self.hass, self.thermostat))
        desired = await self.client.async_sync_thermostat(post, self._refused)
        self._refused = None
        if not is_available(state):
            return desired, [(BridgeStatus.THERMOSTAT_UNAVAILABLE, None)]
        if desired is not None and (refused := await self._apply(desired, state, step, unit)) is not None:
            return desired, [(BridgeStatus.SETTING_REFUSED, refused)]

        return desired, []

    async def _apply(self,
                     desired: dict[str, Any],
                     state: State,
                     step: float | None,
                     unit: str) -> str | None:
        key = tuple(sorted(desired.items()))
        if key != self._setting_key:
            self._setting_key, self._attempts, self._refusal = key, 0, None
        elif self._refusal is None and self._attempts > 0:
            return None
        elif self._refusal is not None and self._attempts >= MAX_ATTEMPTS:
            return self._refusal

        try:
            checked = check_setting(desired, state, unit)
        except HearthSettingError as e:
            logger.warning(f"Not applying Hearth's setting: {e}")
            return self._refuse(desired, str(e), REFUSED_BY_CHECK)

        self._attempts += 1
        try:
            if not already_shows(checked, state, step, unit):
                await self._call(checked, state, step, unit)
        except (ServiceValidationError, vol.Invalid) as e:
            logger.warning(f"The thermostat refused Hearth's setting: {e}")
            return self._refuse(desired, str(e), REFUSED_BY_THERMOSTAT)
        except Exception as e:
            logger.warning(f"The thermostat didn't take Hearth's setting "
                           f"(try {self._attempts} of {MAX_ATTEMPTS}): {e}")
            self._refusal = str(e) or type(e).__name__
            return self._refusal

        self._refusal = None
        self._applied = desired
        return None

    def _refuse(self,
                desired: dict[str, Any],
                reason: str,
                by: str) -> str:
        self._attempts, self._refusal = MAX_ATTEMPTS, reason
        setting = {key: value for key, value in desired.items() if key in _SETTING_KEYS}
        self._refused = {"setting": setting, "reason": reason, "by": by}
        return reason

    async def _call(self,
                    setting: Setting,
                    state: State,
                    step: float | None,
                    unit: str) -> None:
        # Mode first, on its own: some thermostat integrations ignore a mode passed along with setpoints
        target = {ATTR_ENTITY_ID: state.entity_id}
        mode_changes = setting.hvac_mode is not None and setting.hvac_mode != state.state
        if mode_changes:
            await self._service(SERVICE_SET_HVAC_MODE, {**target, ATTR_HVAC_MODE: setting.hvac_mode})
        if setting.temperatures and (mode_changes or not setpoints_shown(setting, state, step, unit)):
            await self._service(SERVICE_SET_TEMPERATURE, {**target, **setting.temperatures})
        if setting.fan_mode is not None and setting.fan_mode != state.attributes.get(ATTR_FAN_MODE):
            await self._service(SERVICE_SET_FAN_MODE, {**target, ATTR_FAN_MODE: setting.fan_mode})

    async def _service(self, service: str, data: dict[str, Any]) -> None:
        async with asyncio.timeout(SERVICE_TIMEOUT):
            await self.hass.services.async_call(CLIMATE_DOMAIN, service, data, blocking=True)

    def _failure(self, e: HearthError, now: datetime) -> tuple[BridgeStatus, str | None]:
        if isinstance(e, HearthAuthError):
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="auth_failed") from e
        elif isinstance(e, HearthRateLimitedError):
            retry_after = int((e.meta or {}).get("retry_after", DEFAULT_RETRY_AFTER))
            self._wait_until = now + timedelta(seconds=retry_after)
            self._log_once(BridgeStatus.SLOWED_DOWN, f"Hearth asked the bridge to slow down for {retry_after} s")
            return BridgeStatus.SLOWED_DOWN, None
        elif isinstance(e, HearthConnectionError):
            self._log_once(BridgeStatus.UNREACHABLE, f"Hearth is unreachable; retrying each minute: {e}")
            return BridgeStatus.UNREACHABLE, str(e)
        else:
            self._log_once(BridgeStatus.POST_REFUSED, f"Hearth refused the bridge's post: {e}")
            return BridgeStatus.POST_REFUSED, str(e)

    def _log_once(self, status: BridgeStatus, message: str) -> None:
        if status not in self._logged:
            logger.warning(message)
            self._logged.add(status)

    def _log_recoveries(self, statuses: set[BridgeStatus]) -> None:
        for status in self._logged - statuses:
            logger.info(f"The bridge recovered from {status.value.replace('_', ' ')}")
        self._logged &= statuses

    def _defer_post(self, delay: float) -> None:
        if self._deferred_post is None:
            self._deferred_post = async_call_later(self.hass, delay, self._post_deferred)

    async def _post_deferred(self, _now: datetime) -> None:
        self._deferred_post = None
        await self.async_request_refresh()

    @callback
    def _cancel_deferred_post(self) -> None:
        if self._deferred_post is not None:
            self._deferred_post()
            self._deferred_post = None

    def _result(self, status: BridgeStatus, now: datetime) -> SyncResult:
        return SyncResult(status=status, at=now, synced_at=self._last_synced, applied=self._applied)


def _urgency(item: tuple[BridgeStatus, str | None]) -> int:
    return list(BridgeStatus).index(item[0])

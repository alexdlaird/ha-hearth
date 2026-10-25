__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeGuard

from homeassistant.components.climate import DATA_COMPONENT as CLIMATE_DATA_COMPONENT
from homeassistant.components.climate.const import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_RESTORED,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from custom_components.hearth.const import SAFE_MAX_C, SAFE_MAX_F, SAFE_MIN_C, SAFE_MIN_F, SENSOR_STALE_AFTER
from custom_components.hearth.exception import HearthSettingError

_NUMBERS = (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_CURRENT_HUMIDITY,
    ATTR_TEMPERATURE,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_MIN_TEMP,
    ATTR_MAX_TEMP,
)
_SETPOINTS = (ATTR_TEMPERATURE, ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH)
_READINGS_UNITS: dict[str, str] = {UnitOfTemperature.FAHRENHEIT: "F", UnitOfTemperature.CELSIUS: "C"}
_SIBLINGS: dict[str, str] = {SensorDeviceClass.HUMIDITY: "humidity", SensorDeviceClass.BATTERY: "battery"}


@dataclass(frozen=True)
class Setting:
    """
    A setting from Hearth, checked against the thermostat: the climate actions that apply it.
    """

    #: The mode to set, if the setting changes it.
    hvac_mode: str | None
    #: The setpoints to set (``temperature``, or ``target_temp_low`` and ``target_temp_high``), in Home Assistant's
    #: unit.
    temperatures: dict[str, float]
    #: The fan mode to set, if the setting includes one the thermostat offers.
    fan_mode: str | None


def is_available(state: State | None) -> TypeGuard[State]:
    """
    Whether an entity has a usable state.

    :param state: The entity's state.
    :return: ``True`` unless it's missing, unavailable or unknown.
    """
    return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def is_placeholder(state: State) -> bool:
    """
    Whether a state is the placeholder Home Assistant restores at startup, before the entity's own integration has
    loaded.

    :param state: The entity's state.
    :return: ``True`` for a restored placeholder.
    """
    return bool(state.attributes.get(ATTR_RESTORED))


def setpoint_step(hass: HomeAssistant,
                  state: State,
                  unit: str) -> float | None:
    """
    The thermostat's setpoint step in Home Assistant's unit. Home Assistant converts a climate entity's temperatures to
    its own unit, but not its step: a 0.5 °C step is 0.9 °F in a °F home.

    :param hass: Home Assistant.
    :param state: The thermostat's state.
    :param unit: Home Assistant's temperature unit.
    :return: The step, or ``None`` when the thermostat doesn't say.
    """
    step = _number(state.attributes.get(ATTR_TARGET_TEMP_STEP))
    component = hass.data.get(CLIMATE_DATA_COMPONENT)
    entity = component.get_entity(state.entity_id) if component is not None else None
    if entity is None:
        return step

    if step is None:
        step = _number(entity.target_temperature_step)
    native = entity.temperature_unit
    if step is None or native == unit:
        return step
    elif native == UnitOfTemperature.CELSIUS and unit == UnitOfTemperature.FAHRENHEIT:
        return round(step * 9 / 5, 2)
    elif native == UnitOfTemperature.FAHRENHEIT and unit == UnitOfTemperature.CELSIUS:
        return round(step * 5 / 9, 2)
    else:
        return None


def thermostat_post(state: State,
                    unit: str,
                    step: float | None,
                    device: str | None = None) -> dict[str, Any]:
    """
    The thermostat as Hearth's ``/v1/bridge`` endpoint takes it: Home Assistant's climate state and attributes.

    :param state: The thermostat's state.
    :param unit: Home Assistant's temperature unit, which every climate entity's state reports in.
    :param step: The thermostat's setpoint step in ``unit`` (see :func:`setpoint_step`).
    :param device: The thermostat's device key (see :func:`device_key`), if it has one.
    :return: The thermostat to post.
    """
    attributes = state.attributes
    available = is_available(state)
    post: dict[str, Any] = {
        "entity_id": state.entity_id,
        "name": state.name,
        "available": available,
        "unit": unit,
        "hvac_mode": state.state if available else None,
        "hvac_modes": [str(mode) for mode in attributes.get(ATTR_HVAC_MODES) or []],
        "hvac_action": _text(attributes.get(ATTR_HVAC_ACTION)),
        "fan_mode": _text(attributes.get(ATTR_FAN_MODE)),
        "fan_modes": [str(mode) for mode in attributes.get(ATTR_FAN_MODES) or []],
        "supported_features": int(attributes.get(ATTR_SUPPORTED_FEATURES) or 0),
        ATTR_TARGET_TEMP_STEP: step,
    }
    if device is not None:
        post["device"] = device
    for key in _NUMBERS:
        post[key] = _number(attributes.get(key))

    return post


def device_key(hass: HomeAssistant,
               entity_id: str) -> str | None:
    """
    The thermostat's device, as Hearth tells one thermostat from another across homes: a SHA-256 of its integration
    and unique id, so no serial number leaves Home Assistant, and the same from any Home Assistant install.

    :param hass: Home Assistant.
    :param entity_id: The thermostat.
    :return: The key, or ``None`` when its integration gives it no unique id.
    """
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or not entry.unique_id:
        return None
    return hashlib.sha256(f"{entry.platform}:{entry.unique_id}".encode()).hexdigest()


def sensor_readings(hass: HomeAssistant,
                    entity_ids: list[str],
                    now: datetime) -> list[dict[str, Any]]:
    """
    The chosen temperature sensors as Hearth's ``/v1/readings`` endpoint takes them, each with the humidity and battery
    readings of the device it's on. A sensor that's unavailable, not a number, in a unit Hearth doesn't take, or not
    reported for ``SENSOR_STALE_AFTER`` is left out.

    :param hass: Home Assistant.
    :param entity_ids: The temperature sensors.
    :param now: The time of the post.
    :return: The readings to post.
    """
    registry = er.async_get(hass)
    readings = []
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if not is_available(state):
            continue

        temperature = _number(_float(state.state))
        unit = _READINGS_UNITS.get(str(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)))
        if temperature is None or unit is None or now - state.last_reported > SENSOR_STALE_AFTER:
            continue

        reading: dict[str, Any] = {
            "id": entity_id,
            "name": state.name,
            "temperature": temperature,
            "unit": unit,
            "time": state.last_reported.isoformat(),
        }
        reading.update(_siblings(hass, registry, entity_id, now))
        readings.append(reading)

    return readings


def check_setting(desired: Mapping[str, Any],
                  state: State,
                  unit: str) -> Setting:
    """
    Check a setting from Hearth against the thermostat. It's applied only in Home Assistant's unit, for a mode the
    thermostat offers, with setpoints of the shape it takes, and only inside its limits and the safe band. A fan mode
    the thermostat doesn't offer is left out.

    :param desired: The setting Hearth answered with.
    :param state: The thermostat's state.
    :param unit: Home Assistant's temperature unit.
    :return: The setting to apply.
    :raises: :class:`~custom_components.hearth.exception.HearthSettingError`: When the setting can't be applied.
    """
    if desired.get("unit") != unit:
        raise HearthSettingError(f"Hearth's setting is in {desired.get('unit')}, Home Assistant uses {unit}")

    attributes = state.attributes
    hvac_mode = desired.get(ATTR_HVAC_MODE)
    if hvac_mode is not None and hvac_mode not in [str(mode) for mode in attributes.get(ATTR_HVAC_MODES) or []]:
        raise HearthSettingError(f"The thermostat doesn't offer the mode {hvac_mode}")
    if hvac_mode == HVACMode.OFF:
        temperatures = {}
    else:
        _check_shape(desired, hvac_mode, state)
        temperatures = _setpoints(desired, state, unit)

    fan_mode = desired.get(ATTR_FAN_MODE)
    if fan_mode not in (attributes.get(ATTR_FAN_MODES) or []):
        fan_mode = None

    return Setting(hvac_mode=hvac_mode, temperatures=temperatures, fan_mode=fan_mode)


def already_shows(setting: Setting,
                  state: State,
                  step: float | None,
                  unit: str) -> bool:
    """
    Whether the thermostat already shows a setting, so writing it again would change nothing. Some thermostats end
    their own schedule on any write.

    :param setting: The setting.
    :param state: The thermostat's state.
    :param step: The thermostat's setpoint step in ``unit``; each setpoint may be off by half of it.
    :param unit: Home Assistant's temperature unit.
    :return: ``True`` when it already shows it.
    """
    if setting.hvac_mode is not None and setting.hvac_mode != state.state:
        return False
    if setting.fan_mode is not None and setting.fan_mode != state.attributes.get(ATTR_FAN_MODE):
        return False
    return setpoints_shown(setting, state, step, unit)


def setpoints_shown(setting: Setting,
                    state: State,
                    step: float | None,
                    unit: str) -> bool:
    """
    Whether the thermostat already shows a setting's setpoints.

    :param setting: The setting.
    :param state: The thermostat's state.
    :param step: The thermostat's setpoint step in ``unit``; each setpoint may be off by half of it.
    :param unit: Home Assistant's temperature unit.
    :return: ``True`` when it already shows them.
    """
    tolerance = (step or (1.0 if unit == UnitOfTemperature.FAHRENHEIT else 0.5)) / 2 + 1e-6
    for key, wanted in setting.temperatures.items():
        shown = _number(state.attributes.get(key))
        if shown is None or abs(shown - wanted) > tolerance:
            return False
    return True


def _check_shape(desired: Mapping[str, Any],
                 hvac_mode: Any,
                 state: State) -> None:
    single = ATTR_TEMPERATURE in desired
    ranged = ATTR_TARGET_TEMP_LOW in desired or ATTR_TARGET_TEMP_HIGH in desired
    mode = hvac_mode if hvac_mode is not None else state.state
    features = ClimateEntityFeature(int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0))
    if single and ranged:
        raise HearthSettingError("The setting has both one temperature and a range")
    elif ranged and mode != HVACMode.HEAT_COOL:
        raise HearthSettingError(f"A low/high range only applies in heat_cool, not {mode}")
    elif single and mode == HVACMode.HEAT_COOL:
        raise HearthSettingError("heat_cool takes a low/high range, not one temperature")
    elif ranged and ClimateEntityFeature.TARGET_TEMPERATURE_RANGE not in features:
        raise HearthSettingError("The thermostat doesn't take a low/high range")
    elif single and ClimateEntityFeature.TARGET_TEMPERATURE not in features:
        raise HearthSettingError("The thermostat doesn't take a single temperature")


def _setpoints(desired: Mapping[str, Any],
               state: State,
               unit: str) -> dict[str, float]:
    low, high = _safe_band(state, unit)
    setpoints: dict[str, float] = {}
    for key in _SETPOINTS:
        if key not in desired:
            continue
        value = _number(desired[key])
        if value is None or not low <= value <= high:
            raise HearthSettingError(f"{key} {desired[key]} is outside {low:g}-{high:g} {unit}")
        setpoints[key] = value
    return setpoints


def _safe_band(state: State, unit: str) -> tuple[float, float]:
    if unit == UnitOfTemperature.FAHRENHEIT:
        safe_low, safe_high = SAFE_MIN_F, SAFE_MAX_F
    else:
        safe_low, safe_high = SAFE_MIN_C, SAFE_MAX_C
    entity_low = _number(state.attributes.get(ATTR_MIN_TEMP))
    entity_high = _number(state.attributes.get(ATTR_MAX_TEMP))

    return (max(safe_low, entity_low) if entity_low is not None else safe_low,
            min(safe_high, entity_high) if entity_high is not None else safe_high)


def _siblings(hass: HomeAssistant,
              registry: er.EntityRegistry,
              entity_id: str,
              now: datetime) -> dict[str, float]:
    entry = registry.async_get(entity_id)
    if entry is None or entry.device_id is None:
        return {}

    found: dict[str, float] = {}
    for sibling in er.async_entries_for_device(registry, entry.device_id):
        key = _SIBLINGS.get(str(sibling.device_class or sibling.original_device_class))
        state = hass.states.get(sibling.entity_id)
        if sibling.domain != "sensor" or key is None or key in found or not is_available(state):
            continue

        value = _number(_float(state.state))
        fresh = key == "battery" or now - state.last_reported <= SENSOR_STALE_AFTER
        percentage = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE
        if value is not None and fresh and percentage and 0 <= value <= 100:
            found[key] = value

    return found


def _float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _text(value: Any) -> str | None:
    return str(value) if value is not None else None

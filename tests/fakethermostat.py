__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature


class FakeThermostat(ClimateEntity):
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self,
                 *,
                 name: str = "Hallway",
                 unique_id: str | None = None,
                 unit: str = UnitOfTemperature.CELSIUS,
                 step: float | None = 0.5,
                 hvac_mode: HVACMode = HVACMode.HEAT_COOL,
                 hvac_modes: list[HVACMode] | None = None,
                 low: float | None = 19.0,
                 high: float | None = 23.5,
                 temperature: float | None = None,
                 fan_mode: str | None = "auto",
                 fan_modes: list[str] | None = None,
                 features: ClimateEntityFeature | None = None,
                 mode_with_setpoints: bool = True,
                 fails_with: BaseException | None = None) -> None:
        self._attr_name = name
        self._attr_unique_id = unique_id or name.lower()
        self._attr_temperature_unit = unit
        self._attr_target_temperature_step = step
        self._attr_hvac_mode = hvac_mode
        self._attr_hvac_modes = hvac_modes or [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
        self._attr_target_temperature_low = low
        self._attr_target_temperature_high = high
        self._attr_target_temperature = temperature
        self._attr_fan_mode = fan_mode
        self._attr_fan_modes = ["auto", "on"] if fan_modes is None else fan_modes
        self._attr_current_temperature = 20.0
        self._attr_min_temp = 5.0 if unit == UnitOfTemperature.CELSIUS else 41.0
        self._attr_max_temp = 35.0 if unit == UnitOfTemperature.CELSIUS else 95.0
        self._attr_supported_features = features if features is not None else (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF)
        self.mode_with_setpoints = mode_with_setpoints
        self.fails_with = fails_with
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self.calls.append(("set_hvac_mode", {ATTR_HVAC_MODE: hvac_mode}))
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        self.calls.append(("set_temperature", {key: value for key, value in kwargs.items() if key != "entity_id"}))
        if self.fails_with is not None:
            raise self.fails_with
        if self.mode_with_setpoints and ATTR_HVAC_MODE in kwargs:
            self._attr_hvac_mode = kwargs[ATTR_HVAC_MODE]
        if ATTR_TEMPERATURE in kwargs:
            self._attr_target_temperature = kwargs[ATTR_TEMPERATURE]
        if ATTR_TARGET_TEMP_LOW in kwargs:
            self._attr_target_temperature_low = kwargs[ATTR_TARGET_TEMP_LOW]
            self._attr_target_temperature_high = kwargs[ATTR_TARGET_TEMP_HIGH]
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self.calls.append(("set_fan_mode", {"fan_mode": fan_mode}))
        self._attr_fan_mode = fan_mode
        self.async_write_ha_state()

    def calls_to(self, service: str) -> list[dict[str, Any]]:
        return [data for name, data in self.calls if name == service]

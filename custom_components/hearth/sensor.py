__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.hearth.const import DOMAIN, MANUFACTURER, NAME, SITE_URL, BridgeStatus
from custom_components.hearth.coordinator import HearthCoordinator, SyncResult

if TYPE_CHECKING:
    from custom_components.hearth import HearthConfigEntry

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HearthSensorDescription(SensorEntityDescription):
    """
    A self-check sensor and how it reads a sync.
    """

    #: The sensor's value from a sync.
    value: Callable[[SyncResult], Any]
    #: The sensor's attributes from a sync, if it has any.
    attributes: Callable[[SyncResult], dict[str, Any]] | None = None


def _status(result: SyncResult) -> str:
    return result.status.value


def _status_attributes(result: SyncResult) -> dict[str, Any]:
    return {
        "detail": result.detail,
        "sensors_posted": result.sensors_posted,
        "sensors_not_added": result.sensors_not_added,
    }


def _synced_at(result: SyncResult) -> datetime | None:
    return result.synced_at


SENSORS = (
    HearthSensorDescription(key="status",
                            translation_key="status",
                            device_class=SensorDeviceClass.ENUM,
                            options=[status.value for status in BridgeStatus],
                            entity_category=EntityCategory.DIAGNOSTIC,
                            value=_status,
                            attributes=_status_attributes),
    HearthSensorDescription(key="last_sync",
                            translation_key="last_sync",
                            device_class=SensorDeviceClass.TIMESTAMP,
                            entity_category=EntityCategory.DIAGNOSTIC,
                            value=_synced_at),
)


async def async_setup_entry(hass: HomeAssistant,
                            entry: "HearthConfigEntry",
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """
    Add the bridge's self-check sensors.

    :param hass: Home Assistant.
    :param entry: The Hearth home's config entry.
    :param async_add_entities: Adds the sensors.
    """
    async_add_entities(HearthSensor(entry.runtime_data, description) for description in SENSORS)


class HearthSensor(CoordinatorEntity[HearthCoordinator], SensorEntity):
    """
    One of the bridge's self-check sensors, on the Hearth service device.
    """

    _attr_has_entity_name = True
    entity_description: HearthSensorDescription

    def __init__(self,
                 coordinator: HearthCoordinator,
                 description: HearthSensorDescription) -> None:
        super(HearthSensor, self).__init__(coordinator)

        self.entity_description = description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)},
                                            name=NAME,
                                            manufacturer=MANUFACTURER,
                                            entry_type=DeviceEntryType.SERVICE,
                                            configuration_url=SITE_URL)

    @property
    def native_value(self) -> Any:
        """
        The sensor's value from the last sync.
        """
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """
        The sensor's attributes from the last sync, if it has any.
        """
        attributes = self.entity_description.attributes
        return attributes(self.coordinator.data) if attributes is not None else None

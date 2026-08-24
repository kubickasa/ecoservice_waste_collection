from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EcoserviceConfigEntry
from .const import VASA_API_URL
from .entity import EcoserviceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EcoserviceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([VasaConnectionSensor(entry)])


class ConnectionStatusEntity(EcoserviceEntity, BinarySensorEntity):
    """A diagnostic connection entity that remains visible after refresh failures."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:connection"

    @property
    def available(self) -> bool:
        return True


class VasaConnectionSensor(ConnectionStatusEntity):
    _attr_name = "VASA prisijungimas"
    _attr_suggested_object_id = "vasa_connection"

    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_vasa_connection"

    @property
    def is_on(self) -> bool:
        return self.coordinator.vasa_connected

    @property
    def extra_state_attributes(self):
        return {
            "endpoint": VASA_API_URL,
            "history_api_available": self.coordinator.vasa_available,
            "calendar_api_available": self.coordinator.vasa_calendar_available,
            "billing_api_available": self.coordinator.vasa_billing_available,
            "data_complete": self.coordinator.vasa_data_complete,
            "next_refresh_interval": str(self.coordinator.update_interval),
            "last_successful_update": self.coordinator.vasa_last_successful_update,
            "last_error": self.coordinator.vasa_error,
        }

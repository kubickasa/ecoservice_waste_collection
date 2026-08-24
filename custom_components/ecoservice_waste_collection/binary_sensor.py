from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EcoserviceConfigEntry
from .const import CONF_VASA_ENABLED, SOURCE_URL, VASA_API_URL
from .entity import EcoserviceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EcoserviceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities: list[BinarySensorEntity] = [EcoserviceApiConnectionSensor(entry)]
    if entry.data.get(CONF_VASA_ENABLED):
        entities.append(VasaConnectionSensor(entry))
    async_add_entities(entities)


class ConnectionStatusEntity(EcoserviceEntity, BinarySensorEntity):
    """A diagnostic connection entity that remains visible after refresh failures."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:connection"

    @property
    def available(self) -> bool:
        return True


class EcoserviceApiConnectionSensor(ConnectionStatusEntity):
    _attr_name = "Ecoservice API ryšys"
    _attr_suggested_object_id = "ecoservice_api_connection"

    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_ecoservice_api_connection"

    @property
    def is_on(self) -> bool:
        return self.coordinator.api_available

    @property
    def extra_state_attributes(self):
        return {
            "endpoint": SOURCE_URL,
            "last_successful_update": self.coordinator.last_successful_update,
            "last_error": self.coordinator.api_error,
        }


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
            "billing_api_available": self.coordinator.vasa_billing_available,
            "last_error": self.coordinator.vasa_error,
        }

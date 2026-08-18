from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EcoserviceConfigEntry
from .const import CONF_ADDRESS, DOMAIN
from .coordinator import EcoserviceCoordinator


class EcoserviceEntity(CoordinatorEntity[EcoserviceCoordinator]):
    _attr_has_entity_name = True
    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        self.entry = entry
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.data[CONF_ADDRESS], manufacturer="Ecoservice", model="Waste collection schedule", configuration_url="https://ecoservice.lt/grafikai/")


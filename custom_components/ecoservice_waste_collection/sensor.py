from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EcoserviceConfigEntry
from .const import CONF_ADDRESS, CONF_CONTAINERS, CONF_MUNICIPALITY, CONF_VASA_ENABLED, SOURCE_URL, VASA_BASE_URL
from .entity import EcoserviceEntity
from .models import WASTE_NAMES, WasteType, days_until, next_collection, yearly_serviced_weight


async def async_setup_entry(hass: HomeAssistant, entry: EcoserviceConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = [EcoserviceSensor(entry, inventory) for inventory in entry.data[CONF_CONTAINERS]]
    if entry.data.get(CONF_VASA_ENABLED):
        entities.append(VasaLastCollectionSensor(entry))
        entities.extend(
            VasaYearWeightSensor(entry, waste_type, slug)
            for waste_type, slug in (
                (WasteType.PAPER, "paper"),
                (WasteType.GLASS, "glass"),
                (WasteType.MIXED, "mixed_waste"),
            )
        )
    async_add_entities(entities)


class EcoserviceSensor(EcoserviceEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_icon = "mdi:trash-can-clock"
    def __init__(self, entry: EcoserviceConfigEntry, inventory: str) -> None:
        super().__init__(entry)
        self.inventory = inventory
        self._attr_unique_id = f"{entry.entry_id}_{inventory}_days"
        self._attr_name = f"{WASTE_NAMES[self.schedule.container.waste_type]} – {inventory} – Dienų iki išvežimo"

    @property
    def schedule(self): return self.coordinator.data[self.inventory]

    @property
    def native_value(self) -> int | None: return days_until(self.schedule.dates, date.today())

    @property
    def extra_state_attributes(self):
        upcoming = [d for d in self.schedule.dates if d >= date.today()][:10]
        history = self.coordinator.histories.get(self.inventory, ())
        return {"next_collection_date": (next_collection(self.schedule.dates, date.today()) or None), "waste_type": self.schedule.container.waste_type.value, "inventory_number": self.inventory, "municipality": self.entry.data[CONF_MUNICIPALITY], "address": self.entry.data[CONF_ADDRESS], "upcoming_collection_dates": upcoming, "last_successful_update": self.coordinator.last_successful_update, "data_source": SOURCE_URL, "collection_history": [{"date": item.date, "servicing": item.servicing, "reason": item.reason, "weight_kg": item.weight_kg} for item in history]}


class VasaLastCollectionSensor(EcoserviceEntity, SensorEntity):
    _attr_name = "Paskutinis faktinis išvežimas"
    _attr_icon = "mdi:weight-kilogram"

    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_vasa_last_collection"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.vasa_available

    @property
    def latest(self):
        serviced = [item for values in self.coordinator.histories.values() for item in values if item.servicing.casefold().strip() == "aptarnautas"]
        return max(serviced, key=lambda item: item.date, default=None)

    @property
    def native_value(self) -> str | None:
        latest = self.latest
        if latest is None:
            return None
        schedule = self.coordinator.data.get(latest.inventory_number)
        return WASTE_NAMES[schedule.container.waste_type] if schedule else "Nežinomos atliekos"

    @property
    def extra_state_attributes(self):
        latest = self.latest
        return {"collection_date": latest.date if latest else None, "weight_kg": latest.weight_kg if latest else None, "inventory_number": latest.inventory_number if latest else None, "servicing": latest.servicing if latest else None, "reason": latest.reason if latest else None, "data_source": f"{VASA_BASE_URL}/orders"}


class VasaYearWeightSensor(EcoserviceEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_device_class = "weight"
    _attr_state_class = "total_increasing"
    _attr_icon = "mdi:weight-kilogram"

    def __init__(self, entry: EcoserviceConfigEntry, waste_type: WasteType, slug: str) -> None:
        super().__init__(entry)
        self.waste_type = waste_type
        self._attr_unique_id = f"{entry.entry_id}_this_year_{slug}_weight"
        self._attr_suggested_object_id = f"this_year_{slug}_weight"
        self._attr_name = f"This year {slug.replace('_', ' ')} weight"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.vasa_available

    @property
    def native_value(self) -> float:
        inventories = {
            key
            for key, schedule in self.coordinator.data.items()
            if schedule.container.waste_type is self.waste_type
        }
        records = (
            item
            for key, values in self.coordinator.histories.items()
            if key in inventories
            for item in values
        )
        return yearly_serviced_weight(records, date.today().year)

    @property
    def extra_state_attributes(self):
        return {"year": date.today().year, "waste_type": self.waste_type.value, "data_source": f"{VASA_BASE_URL}/orders"}

from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EcoserviceConfigEntry
from .const import CONF_ADDRESS, CONF_CONTAINERS, CONF_MUNICIPALITY, CONF_VASA_ENABLED, SOURCE_URL, VASA_BASE_URL
from .entity import EcoserviceEntity
from .models import (
    WASTE_NAMES,
    WasteType,
    days_until,
    latest_serviced_record,
    next_collection,
    next_collection_for_waste,
    yearly_serviced_weight,
)

WASTE_SENSOR_TYPES = (
    (WasteType.PAPER, "paper"),
    (WasteType.GLASS, "glass"),
    (WasteType.MIXED, "mixed_waste"),
)
WASTE_SENSOR_NAMES = {
    WasteType.PAPER: "popieriaus atliekų",
    WasteType.GLASS: "stiklo atliekų",
    WasteType.MIXED: "bendrųjų atliekų",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: EcoserviceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities = [NextCollectionDateSensor(entry), EcoserviceLastUpdateSensor(entry)]
    entities.extend(
        NextWasteTypeCollectionDateSensor(entry, waste_type, slug) for waste_type, slug in WASTE_SENSOR_TYPES
    )
    entities.extend(EcoserviceSensor(entry, inventory) for inventory in entry.data[CONF_CONTAINERS])
    if entry.data.get(CONF_VASA_ENABLED):
        entities.append(VasaLastUpdateSensor(entry))
        entities.append(VasaLastCollectionSensor(entry))
        entities.extend(VasaYearWeightSensor(entry, waste_type, slug) for waste_type, slug in WASTE_SENSOR_TYPES)
        entities.extend(VasaLastWeightSensor(entry, waste_type, slug) for waste_type, slug in WASTE_SENSOR_TYPES)
        entities.extend(
            VasaLastCollectionDateSensor(entry, waste_type, slug) for waste_type, slug in WASTE_SENSOR_TYPES
        )
        entities.append(VasaPayableAmountSensor(entry))
    async_add_entities(entities)


class LastUpdateSensor(EcoserviceEntity, SensorEntity):
    """Keep the last successful source update visible during connection failures."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    @property
    def available(self) -> bool:
        return True


class EcoserviceLastUpdateSensor(LastUpdateSensor):
    _attr_name = "Last update from Ecoservice"
    _attr_suggested_object_id = "last_update_from_ecoservice"

    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_last_update_from_ecoservice"

    @property
    def native_value(self):
        return self.coordinator.ecoservice_last_successful_update

    @property
    def extra_state_attributes(self):
        return {"data_source": SOURCE_URL}


class VasaLastUpdateSensor(LastUpdateSensor):
    _attr_name = "Last update from VASA"
    _attr_suggested_object_id = "last_update_from_vasa"

    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_last_update_from_vasa"

    @property
    def native_value(self):
        return self.coordinator.vasa_last_successful_update

    @property
    def extra_state_attributes(self):
        return {"data_source": VASA_BASE_URL}


def _records_for_waste(entry: EcoserviceConfigEntry, waste_type: WasteType):
    inventories = {
        key for key, schedule in entry.runtime_data.data.items() if schedule.container.waste_type is waste_type
    }
    return (item for key, values in entry.runtime_data.histories.items() if key in inventories for item in values)


class NextCollectionDateSensor(EcoserviceEntity, SensorEntity):
    _attr_name = "Artimiausias atliekų surinkimas"
    _attr_suggested_object_id = "next_waste_collection"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_next_collection_date"

    @property
    def next_item(self):
        candidates = (
            (day, inventory, schedule)
            for inventory, schedule in self.coordinator.data.items()
            if (day := next_collection(schedule.dates, date.today())) is not None
        )
        return min(candidates, key=lambda item: item[0], default=None)

    @property
    def native_value(self):
        item = self.next_item
        return item[0] if item else None

    @property
    def extra_state_attributes(self):
        item = self.next_item
        return {
            "days_until_collection": (item[0] - date.today()).days if item else None,
            "inventory_number": item[1] if item else None,
            "waste_type": item[2].container.waste_type.value if item else None,
            "data_source": SOURCE_URL,
        }


class NextWasteTypeCollectionDateSensor(EcoserviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(self, entry: EcoserviceConfigEntry, waste_type: WasteType, slug: str) -> None:
        super().__init__(entry)
        self.waste_type = waste_type
        self._attr_unique_id = f"{entry.entry_id}_next_{slug}_collection_date"
        self._attr_suggested_object_id = f"next_{slug}_collection_date"
        self._attr_name = f"Kitas {WASTE_SENSOR_NAMES[waste_type]} surinkimas"

    @property
    def next_item(self):
        return next_collection_for_waste(self.coordinator.data.values(), self.waste_type, date.today())

    @property
    def native_value(self):
        item = self.next_item
        return item[0] if item else None

    @property
    def extra_state_attributes(self):
        item = self.next_item
        return {
            "days_until_collection": (item[0] - date.today()).days if item else None,
            "inventory_number": item[1] if item else None,
            "waste_type": self.waste_type.value,
            "data_source": SOURCE_URL,
        }


class EcoserviceSensor(EcoserviceEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_icon = "mdi:trash-can-clock"

    def __init__(self, entry: EcoserviceConfigEntry, inventory: str) -> None:
        super().__init__(entry)
        self.inventory = inventory
        self._attr_unique_id = f"{entry.entry_id}_{inventory}_days"
        self._attr_name = f"{WASTE_NAMES[self.schedule.container.waste_type]} – {inventory} – Dienų iki išvežimo"

    @property
    def schedule(self):
        return self.coordinator.data[self.inventory]

    @property
    def native_value(self) -> int | None:
        return days_until(self.schedule.dates, date.today())

    @property
    def extra_state_attributes(self):
        upcoming = [d for d in self.schedule.dates if d >= date.today()][:10]
        history = self.coordinator.histories.get(self.inventory, ())
        return {
            "next_collection_date": (next_collection(self.schedule.dates, date.today()) or None),
            "waste_type": self.schedule.container.waste_type.value,
            "inventory_number": self.inventory,
            "municipality": self.entry.data[CONF_MUNICIPALITY],
            "address": self.entry.data[CONF_ADDRESS],
            "upcoming_collection_dates": upcoming,
            "last_successful_update": self.coordinator.last_successful_update,
            "data_source": SOURCE_URL,
            "collection_history": [
                {"date": item.date, "servicing": item.servicing, "reason": item.reason, "weight_kg": item.weight_kg}
                for item in history
            ],
        }


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
        serviced = [
            item
            for values in self.coordinator.histories.values()
            for item in values
            if item.servicing.casefold().strip() == "aptarnautas"
        ]
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
        return {
            "collection_date": latest.date if latest else None,
            "weight_kg": latest.weight_kg if latest else None,
            "inventory_number": latest.inventory_number if latest else None,
            "servicing": latest.servicing if latest else None,
            "reason": latest.reason if latest else None,
            "data_source": f"{VASA_BASE_URL}/orders",
        }


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
            key for key, schedule in self.coordinator.data.items() if schedule.container.waste_type is self.waste_type
        }
        records = (item for key, values in self.coordinator.histories.items() if key in inventories for item in values)
        return yearly_serviced_weight(records, date.today().year)

    @property
    def extra_state_attributes(self):
        return {
            "year": date.today().year,
            "waste_type": self.waste_type.value,
            "data_source": f"{VASA_BASE_URL}/orders",
        }


class VasaLastWeightSensor(EcoserviceEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weight-kilogram"

    def __init__(self, entry: EcoserviceConfigEntry, waste_type: WasteType, slug: str) -> None:
        super().__init__(entry)
        self.waste_type = waste_type
        self._attr_unique_id = f"{entry.entry_id}_last_{slug}_weight"
        self._attr_suggested_object_id = f"last_{slug}_weight"
        self._attr_name = f"Paskutinis {WASTE_SENSOR_NAMES[waste_type]} svoris"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.vasa_available

    @property
    def latest(self):
        return latest_serviced_record(_records_for_waste(self.entry, self.waste_type))

    @property
    def native_value(self) -> float | None:
        latest = self.latest
        return latest.weight_kg if latest else None

    @property
    def extra_state_attributes(self):
        latest = self.latest
        return {
            "collection_date": latest.date if latest else None,
            "inventory_number": latest.inventory_number if latest else None,
            "waste_type": self.waste_type.value,
            "data_source": f"{VASA_BASE_URL}/orders",
        }


class VasaLastCollectionDateSensor(EcoserviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-check"

    def __init__(self, entry: EcoserviceConfigEntry, waste_type: WasteType, slug: str) -> None:
        super().__init__(entry)
        self.waste_type = waste_type
        self._attr_unique_id = f"{entry.entry_id}_last_{slug}_collection_date"
        self._attr_suggested_object_id = f"last_{slug}_collection_date"
        self._attr_name = f"Paskutinis {WASTE_SENSOR_NAMES[waste_type]} išvežimas"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.vasa_available

    @property
    def latest(self):
        return latest_serviced_record(_records_for_waste(self.entry, self.waste_type))

    @property
    def native_value(self):
        latest = self.latest
        return latest.date if latest else None

    @property
    def extra_state_attributes(self):
        latest = self.latest
        return {
            "weight_kg": latest.weight_kg if latest else None,
            "inventory_number": latest.inventory_number if latest else None,
            "waste_type": self.waste_type.value,
            "data_source": f"{VASA_BASE_URL}/orders",
        }


class VasaPayableAmountSensor(EcoserviceEntity, SensorEntity):
    _attr_name = "VASA mokėtina suma"
    _attr_suggested_object_id = "vasa_payable_amount"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash-clock"

    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_vasa_payable_amount"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.vasa_billing_available

    @property
    def native_value(self) -> float:
        return round(sum(item.amount for item in self.coordinator.payable_invoices), 2)

    @property
    def extra_state_attributes(self):
        return {
            "invoices": [
                {
                    "invoice_number": item.invoice_number,
                    "amount": item.amount,
                }
                for item in self.coordinator.payable_invoices
            ],
            "data_source": VASA_BASE_URL,
        }

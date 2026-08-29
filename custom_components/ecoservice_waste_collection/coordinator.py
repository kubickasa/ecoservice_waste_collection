from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CONTAINERS,
    DOMAIN,
    INCOMPLETE_UPDATE_INTERVAL,
    UPDATE_INTERVAL,
    VASA_BASE_URL,
    VASA_HISTORY_LIMIT,
)
from .models import (
    CollectionRecord,
    Container,
    PayableInvoice,
    Schedule,
    WasteType,
    schedules_have_upcoming_collections,
    waste_type_from_inventory,
)
from .vasa_api import VasaApi, VasaApiError

_LOGGER = logging.getLogger(__name__)


class EcoserviceCoordinator(DataUpdateCoordinator[dict[str, Schedule]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, vasa_api: VasaApi) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.entry, self.vasa_api = entry, vasa_api
        self.histories: dict[str, tuple[CollectionRecord, ...]] = {}
        self.payable_invoices: tuple[PayableInvoice, ...] = ()
        self.schedule_sources: dict[str, str] = {}
        self.vasa_available = False
        self.vasa_calendar_available = False
        self.vasa_billing_available = False
        self.vasa_connected = False
        self.vasa_error: str | None = None
        self.vasa_data_complete = False
        self.vasa_last_successful_update: datetime | None = None
        self.last_successful_update: datetime | None = None
        self.store: Store[dict[str, Any]] = Store(hass, 2, f"{DOMAIN}.{entry.entry_id}")

    async def async_load_cached(self) -> None:
        cached = await self.store.async_load()
        if not cached:
            return
        if vasa_updated := cached.get("vasa_updated"):
            self.vasa_last_successful_update = datetime.fromisoformat(vasa_updated)
            self.last_successful_update = self.vasa_last_successful_update
        vasa_source = f"{VASA_BASE_URL}/orders"
        vasa_schedules = {
            key: Schedule(
                Container(key, WasteType(value["waste_type"]), value.get("capacity")),
                tuple(date.fromisoformat(item) for item in value["dates"]),
            )
            for key, value in cached["schedules"].items()
            if value.get("source") == vasa_source
        }
        if vasa_schedules:
            self.data = vasa_schedules
        self.schedule_sources = {key: vasa_source for key in vasa_schedules}
        self.histories = {
            key: tuple(
                CollectionRecord(
                    date.fromisoformat(item["date"]), key, item["servicing"], item.get("reason"), item.get("weight_kg")
                )
                for item in values
            )
            for key, values in cached.get("histories", {}).items()
        }
        self.payable_invoices = tuple(
            PayableInvoice(item["invoice_number"], float(item["amount"])) for item in cached.get("payable_invoices", [])
        )

    async def _async_update_data(self) -> dict[str, Schedule]:
        inventories = list(self.entry.data[CONF_CONTAINERS])
        schedules: dict[str, Schedule] | None = None
        schedule_source = f"{VASA_BASE_URL}/orders"
        schedule_sources = {inventory: schedule_source for inventory in inventories}
        vasa_succeeded = False
        vasa_errors: list[str] = []
        try:
            histories, calendars = await self.vasa_api.histories_and_calendars(inventories)
            self.histories = {key: tuple(values[:VASA_HISTORY_LIMIT]) for key, values in histories.items()}
            self.vasa_available = True
            self.vasa_calendar_available = True
            vasa_succeeded = True
            schedules = {
                inventory: Schedule(
                    Container(inventory, waste_type_from_inventory(inventory)),
                    calendars.get(inventory, ()),
                )
                for inventory in inventories
            }
        except VasaApiError as err:
            self.vasa_available = False
            self.vasa_calendar_available = False
            vasa_errors.append(f"history/calendar: {err}")
            _LOGGER.warning("VASA history/calendar refresh failed; cached data was retained")
        try:
            self.payable_invoices = await self.vasa_api.payable_invoices()
            self.vasa_billing_available = True
            vasa_succeeded = True
        except VasaApiError as err:
            self.vasa_billing_available = False
            vasa_errors.append(f"billing: {err}")
            _LOGGER.warning("VASA billing refresh failed; cached invoices were retained")
        self.vasa_connected = self.vasa_available or self.vasa_billing_available
        self.vasa_error = "; ".join(vasa_errors) or None
        self.vasa_data_complete = (
            self.vasa_available
            and self.vasa_calendar_available
            and self.vasa_billing_available
            and schedules is not None
            and schedules_have_upcoming_collections(schedules, inventories, date.today())
        )
        schedules_complete = schedules is not None and schedules_have_upcoming_collections(
            schedules, inventories, date.today()
        )
        self.update_interval = (
            UPDATE_INTERVAL if schedules_complete and self.vasa_data_complete else INCOMPLETE_UPDATE_INTERVAL
        )
        if schedules is None:
            raise UpdateFailed(self.vasa_error or "VASA collection schedule was unavailable")
        updated = datetime.now(UTC)
        self.last_successful_update = updated
        if vasa_succeeded:
            self.vasa_last_successful_update = updated
        self.schedule_sources = schedule_sources
        await self.store.async_save(
            {
                "updated": updated.isoformat(),
                "vasa_updated": (
                    self.vasa_last_successful_update.isoformat() if self.vasa_last_successful_update else None
                ),
                "source": schedule_source,
                "schedules": {
                    key: {
                        "waste_type": value.container.waste_type.value,
                        "capacity": value.container.capacity,
                        "dates": [item.isoformat() for item in value.dates],
                        "source": schedule_sources[key],
                    }
                    for key, value in schedules.items()
                },
                "histories": {
                    key: [
                        {
                            "date": item.date.isoformat(),
                            "servicing": item.servicing,
                            "reason": item.reason,
                            "weight_kg": item.weight_kg,
                        }
                        for item in values
                    ]
                    for key, values in self.histories.items()
                },
                "payable_invoices": [
                    {"invoice_number": item.invoice_number, "amount": item.amount} for item in self.payable_invoices
                ],
            }
        )
        return schedules

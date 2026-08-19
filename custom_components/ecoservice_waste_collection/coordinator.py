from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EcoserviceApi, EcoserviceApiError
from .const import (
    CONF_ADDRESS,
    CONF_CONTAINERS,
    CONF_MUNICIPALITY,
    DOMAIN,
    SOURCE_URL,
    UPDATE_INTERVAL,
    VASA_HISTORY_LIMIT,
)
from .models import CollectionRecord, Container, PayableInvoice, Schedule, WasteType
from .vasa_api import VasaApi, VasaApiError

_LOGGER = logging.getLogger(__name__)


class EcoserviceCoordinator(DataUpdateCoordinator[dict[str, Schedule]]):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: EcoserviceApi, vasa_api: VasaApi | None = None
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.entry, self.api, self.vasa_api = entry, api, vasa_api
        self.histories: dict[str, tuple[CollectionRecord, ...]] = {}
        self.payable_invoices: tuple[PayableInvoice, ...] = ()
        self.vasa_available = vasa_api is None
        self.vasa_billing_available = vasa_api is None
        self.last_successful_update: datetime | None = None
        self.store: Store[dict[str, Any]] = Store(hass, 2, f"{DOMAIN}.{entry.entry_id}")

    async def async_load_cached(self) -> None:
        cached = await self.store.async_load()
        if not cached:
            return
        self.last_successful_update = datetime.fromisoformat(cached["updated"])
        self.data = {
            key: Schedule(
                Container(key, WasteType(value["waste_type"]), value.get("capacity")),
                tuple(date.fromisoformat(item) for item in value["dates"]),
            )
            for key, value in cached["schedules"].items()
        }
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
        try:
            schedules = await self.api.schedules(
                self.entry.data[CONF_MUNICIPALITY],
                self.entry.data[CONF_ADDRESS],
                list(self.entry.data[CONF_CONTAINERS]),
            )
        except EcoserviceApiError as err:
            raise UpdateFailed(str(err)) from err
        if self.vasa_api:
            try:
                histories = await self.vasa_api.histories(list(self.entry.data[CONF_CONTAINERS]))
                self.histories = {key: tuple(values[:VASA_HISTORY_LIMIT]) for key, values in histories.items()}
                self.vasa_available = True
            except VasaApiError:
                self.vasa_available = False
                _LOGGER.warning("VASA history refresh failed; cached history was retained")
            try:
                self.payable_invoices = await self.vasa_api.payable_invoices()
                self.vasa_billing_available = True
            except VasaApiError:
                self.vasa_billing_available = False
                _LOGGER.warning("VASA billing refresh failed; cached invoices were retained")
        self.last_successful_update = datetime.now(UTC)
        await self.store.async_save(
            {
                "updated": self.last_successful_update.isoformat(),
                "source": SOURCE_URL,
                "schedules": {
                    key: {
                        "waste_type": value.container.waste_type.value,
                        "capacity": value.container.capacity,
                        "dates": [item.isoformat() for item in value.dates],
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

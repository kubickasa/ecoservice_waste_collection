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
    INCOMPLETE_UPDATE_INTERVAL,
    SOURCE_URL,
    UPDATE_INTERVAL,
    VASA_HISTORY_LIMIT,
)
from .models import (
    CollectionRecord,
    Container,
    PayableInvoice,
    Schedule,
    WasteType,
    schedules_have_upcoming_collections,
)
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
        self.api_available = False
        self.api_error: str | None = None
        self.ecoservice_data_complete = False
        self.vasa_available = vasa_api is None
        self.vasa_billing_available = vasa_api is None
        self.vasa_connected = vasa_api is None
        self.vasa_error: str | None = None
        self.vasa_data_complete = vasa_api is None
        self.ecoservice_last_successful_update: datetime | None = None
        self.vasa_last_successful_update: datetime | None = None
        self.last_successful_update: datetime | None = None
        self.store: Store[dict[str, Any]] = Store(hass, 2, f"{DOMAIN}.{entry.entry_id}")

    async def async_load_cached(self) -> None:
        cached = await self.store.async_load()
        if not cached:
            return
        ecoservice_updated = cached.get("ecoservice_updated", cached.get("updated"))
        if ecoservice_updated:
            self.ecoservice_last_successful_update = datetime.fromisoformat(ecoservice_updated)
            self.last_successful_update = self.ecoservice_last_successful_update
        if vasa_updated := cached.get("vasa_updated"):
            self.vasa_last_successful_update = datetime.fromisoformat(vasa_updated)
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
            self.api_available = False
            self.api_error = str(err)
            self.ecoservice_data_complete = False
            schedules = None
        else:
            self.api_available = True
            self.api_error = None
            self.ecoservice_data_complete = schedules_have_upcoming_collections(
                schedules,
                self.entry.data[CONF_CONTAINERS],
                date.today(),
            )
        vasa_succeeded = False
        if self.vasa_api:
            vasa_errors: list[str] = []
            try:
                histories = await self.vasa_api.histories(list(self.entry.data[CONF_CONTAINERS]))
                self.histories = {key: tuple(values[:VASA_HISTORY_LIMIT]) for key, values in histories.items()}
                self.vasa_available = True
                vasa_succeeded = True
            except VasaApiError as err:
                self.vasa_available = False
                vasa_errors.append(f"history: {err}")
                _LOGGER.warning("VASA history refresh failed; cached history was retained")
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
            self.vasa_data_complete = self.vasa_available and self.vasa_billing_available
        all_data_complete = self.ecoservice_data_complete and self.vasa_data_complete
        self.update_interval = UPDATE_INTERVAL if all_data_complete else INCOMPLETE_UPDATE_INTERVAL
        if schedules is None:
            raise UpdateFailed(self.api_error or "Ecoservice API refresh failed")
        updated = datetime.now(UTC)
        self.ecoservice_last_successful_update = updated
        self.last_successful_update = updated
        if vasa_succeeded:
            self.vasa_last_successful_update = updated
        await self.store.async_save(
            {
                "updated": updated.isoformat(),
                "ecoservice_updated": updated.isoformat(),
                "vasa_updated": (
                    self.vasa_last_successful_update.isoformat() if self.vasa_last_successful_update else None
                ),
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

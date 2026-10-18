from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ecoservice_waste_collection.const import CONF_CONTAINERS, UPDATE_INTERVAL
from custom_components.ecoservice_waste_collection.coordinator import EcoserviceCoordinator
from custom_components.ecoservice_waste_collection.models import Container, Schedule, WasteType
from custom_components.ecoservice_waste_collection.vasa_api import VasaApiError


class FailingVasaApi:
    async def histories_and_calendars(self, inventories):
        raise VasaApiError("temporary history failure")

    async def payable_invoices(self):
        raise VasaApiError("temporary billing failure")


class MemoryStore:
    def __init__(self):
        self.saved = None

    async def async_save(self, value):
        self.saved = value


def make_coordinator(cached_data):
    coordinator = object.__new__(EcoserviceCoordinator)
    coordinator.entry = SimpleNamespace(data={CONF_CONTAINERS: ["13-L-1"]})
    coordinator.vasa_api = FailingVasaApi()
    coordinator.data = cached_data
    coordinator.histories = {"13-L-1": ()}
    coordinator.payable_invoices = ()
    coordinator.schedule_sources = {"13-L-1": "https://savitarna.vasa.lt/orders"}
    coordinator.vasa_available = True
    coordinator.vasa_calendar_available = True
    coordinator.vasa_billing_available = True
    coordinator.vasa_history_data_available = True
    coordinator.vasa_calendar_data_available = True
    coordinator.vasa_billing_data_available = True
    coordinator.vasa_connected = True
    coordinator.vasa_error = None
    coordinator.vasa_data_complete = True
    coordinator.vasa_last_successful_update = datetime(2026, 1, 2, tzinfo=UTC)
    coordinator.last_successful_update = datetime(2026, 1, 2, tzinfo=UTC)
    coordinator.store = MemoryStore()
    return coordinator


@pytest.mark.asyncio
async def test_refresh_failure_keeps_cached_schedules_available():
    cached = {
        "13-L-1": Schedule(
            Container("13-L-1", WasteType.MIXED),
            (date.today() + timedelta(days=7),),
        )
    }
    coordinator = make_coordinator(cached)

    result = await coordinator._async_update_data()

    assert result is cached
    assert coordinator.update_interval == UPDATE_INTERVAL
    assert coordinator.vasa_available is False
    assert coordinator.vasa_billing_available is False
    assert coordinator.vasa_history_data_available is True
    assert coordinator.vasa_billing_data_available is True
    assert coordinator.last_successful_update == datetime(2026, 1, 2, tzinfo=UTC)
    assert "temporary history failure" in coordinator.vasa_error
    assert coordinator.store.saved is not None


@pytest.mark.asyncio
async def test_first_refresh_failure_without_cache_still_fails():
    coordinator = make_coordinator(None)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

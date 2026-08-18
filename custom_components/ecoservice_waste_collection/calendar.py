from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EcoserviceConfigEntry
from .const import CONF_ADDRESS, CONF_MUNICIPALITY
from .entity import EcoserviceEntity
from .models import WASTE_NAMES


def build_events(entry: EcoserviceConfigEntry, start: datetime, end: datetime) -> list[CalendarEvent]:
    events = []
    start_date, end_date = start.date(), end.date()
    for schedule in entry.runtime_data.data.values():
        for day in schedule.dates:
            if start_date <= day < end_date:
                label = WASTE_NAMES[schedule.container.waste_type]
                events.append(CalendarEvent(start=day, end=day + timedelta(days=1), summary=f"{label} išvežimas – {schedule.container.inventory_number}", description=f"{entry.data[CONF_MUNICIPALITY]}, {entry.data[CONF_ADDRESS]}; {label}; {schedule.container.inventory_number}", location=entry.data[CONF_ADDRESS]))
    return sorted(events, key=lambda event: event.start)


async def async_setup_entry(hass: HomeAssistant, entry: EcoserviceConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([EcoserviceCalendar(entry)])


class EcoserviceCalendar(EcoserviceEntity, CalendarEntity):
    _attr_name = "Atliekų išvežimo kalendorius"
    def __init__(self, entry: EcoserviceConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_calendar"

    @property
    def event(self):
        now = datetime.now().astimezone()
        events = build_events(self.entry, now, now + timedelta(days=366))
        return events[0] if events else None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        return build_events(self.entry, start_date, end_date)

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
        self.async_update_listeners()


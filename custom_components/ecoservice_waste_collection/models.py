from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any


class WasteType(StrEnum):
    MIXED = "mixed"
    PAPER = "paper"
    GLASS = "glass"
    UNKNOWN = "unknown"


WASTE_NAMES = {
    WasteType.MIXED: "Bendrosios atliekos",
    WasteType.PAPER: "Popieriaus atliekos",
    WasteType.GLASS: "Stiklo atliekos",
    WasteType.UNKNOWN: "Nežinomos atliekos",
}


def waste_type_from_inventory(value: str) -> WasteType:
    """Find the first standalone meaningful letter, normally the code after a hyphen.

    Numeric prefixes and separators are skipped. If a source changes formatting,
    the first ASCII letter is used safely and unknown letters remain UNKNOWN.
    """
    match = re.search(r"[A-Za-z]", value or "")
    if not match:
        return WasteType.UNKNOWN
    return {"L": WasteType.MIXED, "P": WasteType.PAPER, "S": WasteType.GLASS}.get(
        match.group().upper(), WasteType.UNKNOWN
    )


def normalize_date(value: Any) -> date | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            timestamp = value / 1000 if abs(value) >= 100_000_000_000 else value
            return datetime.fromtimestamp(timestamp, UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("/Date("):
        try:
            return datetime.fromtimestamp(int(re.search(r"-?\d+", text).group()) / 1000, UTC).date()  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    return None


def normalize_dates(values: list[Any]) -> tuple[date, ...]:
    return tuple(sorted({parsed for value in values if (parsed := normalize_date(value))}))


@dataclass(frozen=True, slots=True)
class Container:
    inventory_number: str
    waste_type: WasteType
    capacity: str | None = None


@dataclass(frozen=True, slots=True)
class Schedule:
    container: Container
    dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class CollectionRecord:
    date: date
    inventory_number: str
    servicing: str
    reason: str | None
    weight_kg: float | None


@dataclass(frozen=True, slots=True)
class PayableInvoice:
    invoice_number: str
    amount: float


def next_collection(dates: tuple[date, ...], today: date) -> date | None:
    return next((item for item in dates if item >= today), None)


def next_collection_for_waste(
    schedules: Iterable[Schedule], waste_type: WasteType, today: date
) -> tuple[date, str] | None:
    candidates = (
        (day, schedule.container.inventory_number)
        for schedule in schedules
        if schedule.container.waste_type is waste_type and (day := next_collection(schedule.dates, today)) is not None
    )
    return min(candidates, key=lambda item: item[0], default=None)


def schedules_have_upcoming_collections(
    schedules: Mapping[str, Schedule], inventories: Iterable[str], today: date
) -> bool:
    """Return whether every selected container has at least one upcoming date."""
    return all(
        inventory in schedules and next_collection(schedules[inventory].dates, today) is not None
        for inventory in inventories
    )


def days_until(dates: tuple[date, ...], today: date) -> int | None:
    upcoming = next_collection(dates, today)
    return (upcoming - today).days if upcoming else None


def yearly_serviced_weight(records: Iterable[CollectionRecord], year: int) -> float:
    """Sum known weights for successful services in a calendar year."""
    return sum(
        item.weight_kg
        for item in records
        if item.date.year == year and item.servicing.casefold().strip() == "aptarnautas" and item.weight_kg is not None
    )


def latest_serviced_record(
    records: Iterable[CollectionRecord],
) -> CollectionRecord | None:
    """Return the latest successfully serviced collection record."""
    return max(
        (item for item in records if item.servicing.casefold().strip() == "aptarnautas"),
        key=lambda item: item.date,
        default=None,
    )
